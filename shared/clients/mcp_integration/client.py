import asyncio
import math
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack
from copy import deepcopy
from typing import Any, NoReturn, Protocol, Self
from urllib.parse import urlparse

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from pydantic import ValidationError

from .cache import Cache
from .models import (
    DuplicateToolError,
    JSONValue,
    MCPClientStateError,
    MCPConfigurationError,
    MCPConnectionError,
    MCPProtocolError,
    MCPServerConfig,
    MCPTimeoutError,
    MCPTool,
    ToolNotFoundError,
    ToolResult,
)


class _ServerClient(Protocol):
    async def __aenter__(self) -> Self: ...

    async def __aexit__(self, exc_type, exc, traceback) -> bool | None: ...

    async def list_tools(self) -> list[MCPTool]: ...

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, JSONValue],
    ) -> ToolResult: ...


class MCPServerClient:
    """Application-facing adapter for one Streamable HTTP MCP server."""

    def __init__(self, config: MCPServerConfig) -> None:
        self._config = _snapshot_config(config)
        self._stack: AsyncExitStack | None = None
        self._client: Any = None

    async def __aenter__(self) -> "MCPServerClient":
        stack = AsyncExitStack()
        try:
            async with asyncio.timeout(self._config.timeout_seconds):
                http_client = await stack.enter_async_context(
                    httpx2.AsyncClient(
                        headers=dict(self._config.headers),
                        timeout=httpx2.Timeout(self._config.timeout_seconds),
                    )
                )
                transport = streamable_http_client(
                    self._config.url,
                    http_client=http_client,
                )
                self._client = await stack.enter_async_context(
                    Client(transport, cache=None)
                )
        except BaseException as error:
            self._client = None
            try:
                await stack.aclose()
            except BaseException:
                pass
            self._raise_mapped(error, "connect")

        self._stack = stack
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool | None:
        stack, self._stack = self._stack, None
        self._client = None
        if stack is None:
            return None
        try:
            async with asyncio.timeout(self._config.timeout_seconds):
                await stack.__aexit__(exc_type, exc, traceback)
        except BaseException as error:
            if isinstance(error, asyncio.CancelledError):
                raise
            if exc is not None:
                return False
            self._raise_mapped(error, "shutdown")
        return False

    async def list_tools(self) -> list[MCPTool]:
        client = self._require_client()
        tools: list[MCPTool] = []
        cursor: str | None = None

        try:
            async with asyncio.timeout(self._config.timeout_seconds):
                while True:
                    page = await client.list_tools(cursor=cursor)
                    tools.extend(
                        MCPTool(
                            name=tool.name,
                            title=tool.title,
                            description=tool.description,
                            input_schema=deepcopy(tool.input_schema),
                            output_schema=deepcopy(tool.output_schema),
                        )
                        for tool in page.tools
                    )
                    cursor = page.next_cursor
                    if cursor is None:
                        return tools
        except BaseException as error:
            self._raise_mapped(error, "list tools")

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, JSONValue],
    ) -> ToolResult:
        client = self._require_client()
        try:
            async with asyncio.timeout(self._config.timeout_seconds):
                result = await client.call_tool(name, deepcopy(dict(arguments)))
        except BaseException as error:
            self._raise_mapped(error, "call tool")

        return ToolResult(
            content=tuple(
                deepcopy(block.model_dump(mode="json", by_alias=True))
                for block in result.content
            ),
            structured_content=deepcopy(result.structured_content),
            is_error=result.is_error,
        )

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("MCPServerClient must be used within an async context")
        return self._client

    def _raise_mapped(self, error: BaseException, operation: str) -> NoReturn:
        original = error
        while isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
            error = error.exceptions[0]

        if isinstance(error, asyncio.CancelledError):
            raise error
        if isinstance(error, (TimeoutError, httpx2.TimeoutException)):
            raise MCPTimeoutError(self._config.name, operation) from original
        if isinstance(error, httpx2.TransportError):
            raise MCPConnectionError(self._config.name, operation) from original
        if isinstance(error, (MCPError, ValidationError)):
            raise MCPProtocolError(self._config.name, operation) from original
        raise original


class MCPClientManager:
    def __init__(
        self,
        server_configs: list[MCPServerConfig],
        cache: Cache,
        discovery_ttl_seconds: float = 300.0,
        *,
        client_constructor: Callable[[MCPServerConfig], _ServerClient] = MCPServerClient,
    ) -> None:
        configs = tuple(server_configs)
        self._validate(configs, discovery_ttl_seconds, client_constructor)
        self._configs = tuple(_snapshot_config(config) for config in configs)
        self._cache = cache
        self._discovery_ttl_seconds = discovery_ttl_seconds
        self._clients = tuple(client_constructor(config) for config in self._configs)
        self._active_clients: tuple[_ServerClient, ...] = ()
        self._stack: AsyncExitStack | None = None
        self._entered = False
        self._active = False
        self._tools: tuple[MCPTool, ...] = ()
        self._owners: dict[str, _ServerClient] = {}
        self._server_tools: dict[str, tuple[MCPTool, ...]] = {}

    async def __aenter__(self) -> "MCPClientManager":
        if self._entered:
            raise MCPClientStateError("enter")
        self._entered = True
        stack = AsyncExitStack()
        try:
            opened = []
            for client in self._clients:
                opened.append(await stack.enter_async_context(client))
            clients = tuple(opened)
            await self._discover(clients, force=True)
        except BaseException:
            try:
                await stack.aclose()
            except BaseException:
                pass
            raise

        self._active_clients = clients
        self._stack = stack
        self._active = True
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool | None:
        self._active = False
        stack, self._stack = self._stack, None
        if stack is None:
            return None
        return await stack.__aexit__(exc_type, exc, traceback)

    async def list_tools(self) -> tuple[MCPTool, ...]:
        self._require_active("list tools")
        return self._tools

    async def refresh_tools(self, force: bool = False) -> tuple[MCPTool, ...]:
        self._require_active("refresh tools")
        return await self._discover(self._active_clients, force=force)

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, JSONValue],
    ) -> ToolResult:
        self._require_active("call tool")
        try:
            owner = self._owners[name]
        except KeyError:
            raise ToolNotFoundError(name) from None
        return await owner.call_tool(name, arguments)

    async def list_server_tools(self, server_name: str) -> tuple[MCPTool, ...]:
        self._require_active("list server tools")
        try:
            return self._server_tools[server_name]
        except KeyError:
            raise MCPConfigurationError(f"unknown MCP server '{server_name}'") from None

    async def call_server_tool(
        self,
        server_name: str,
        name: str,
        arguments: Mapping[str, JSONValue],
    ) -> ToolResult:
        self._require_active("call server tool")
        tools = await self.list_server_tools(server_name)
        if not any(tool.name == name for tool in tools):
            raise ToolNotFoundError(name)
        return await self._owners[name].call_tool(name, arguments)

    async def _discover(
        self,
        clients: tuple[_ServerClient, ...],
        *,
        force: bool,
    ) -> tuple[MCPTool, ...]:
        candidates: list[tuple[str, _ServerClient, tuple[MCPTool, ...]]] = []
        live_entries: list[tuple[str, tuple[MCPTool, ...]]] = []

        for config, client in zip(self._configs, clients, strict=True):
            key = f"mcp:tools:{config.name}"
            cached = None if force else await self._cache.get(key)
            if isinstance(cached, tuple) and all(
                isinstance(tool, MCPTool) for tool in cached
            ):
                tools = cached
            else:
                tools = tuple(await client.list_tools())
                live_entries.append((key, tools))
            candidates.append((config.name, client, tools))

        occurrences: dict[str, list[str]] = {}
        for server_name, _, tools in candidates:
            for tool in tools:
                if (
                    not isinstance(tool, MCPTool)
                    or not isinstance(tool.name, str)
                    or not tool.name.strip()
                ):
                    raise MCPProtocolError(server_name, "list tools")
                occurrences.setdefault(tool.name, []).append(server_name)

        for tool_name, sources in occurrences.items():
            if len(sources) > 1:
                raise DuplicateToolError(tool_name, tuple(sources))

        tools = tuple(
            sorted(
                (tool for _, _, server_tools in candidates for tool in server_tools),
                key=lambda tool: tool.name,
            )
        )
        owners = {
            tool.name: client
            for _, client, server_tools in candidates
            for tool in server_tools
        }

        for key, server_tools in live_entries:
            await self._cache.set(
                key,
                server_tools,
                ttl_seconds=self._discovery_ttl_seconds,
            )

        self._tools, self._owners = tools, owners
        self._server_tools = {
            server_name: server_tools
            for server_name, _, server_tools in candidates
        }
        return tools

    def _require_active(self, operation: str) -> None:
        if not self._active:
            raise MCPClientStateError(operation)

    @staticmethod
    def _validate(
        configs: tuple[MCPServerConfig, ...],
        discovery_ttl_seconds: float,
        client_constructor: Callable[[MCPServerConfig], _ServerClient],
    ) -> None:
        if len(configs) != 3:
            raise MCPConfigurationError("exactly three servers are required")
        if not callable(client_constructor):
            raise MCPConfigurationError("client_constructor must be callable")
        if not _is_positive_finite(discovery_ttl_seconds):
            raise MCPConfigurationError(
                "discovery_ttl_seconds must be positive and finite"
            )

        names: set[str] = set()
        for config in configs:
            if not isinstance(config.name, str) or not config.name.strip():
                raise MCPConfigurationError("server names must be non-empty strings")
            if config.name in names:
                raise MCPConfigurationError("server names must be unique")
            names.add(config.name)

            if not isinstance(config.url, str):
                raise MCPConfigurationError("server URLs must be absolute HTTP URLs")
            try:
                parsed_url = urlparse(config.url)
            except ValueError:
                parsed_url = None
            if (
                parsed_url is None
                or parsed_url.scheme not in {"http", "https"}
                or not parsed_url.netloc
            ):
                raise MCPConfigurationError("server URLs must be absolute HTTP URLs")

            if not _is_positive_finite(config.timeout_seconds):
                raise MCPConfigurationError("server timeouts must be positive and finite")
            if not isinstance(config.headers, Mapping) or not all(
                isinstance(name, str) and isinstance(value, str)
                for name, value in config.headers.items()
            ):
                raise MCPConfigurationError("server headers must contain only strings")


def _is_positive_finite(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and value > 0
        and math.isfinite(value)
    )


def _snapshot_config(config: MCPServerConfig) -> MCPServerConfig:
    return MCPServerConfig(
        config.name,
        config.url,
        config.timeout_seconds,
        dict(config.headers),
    )
