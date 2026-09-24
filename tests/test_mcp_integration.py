import asyncio
import math
from dataclasses import FrozenInstanceError
from typing import Any

import httpx2
import pytest
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool
from pydantic import ValidationError

from shared.clients.mcp_integration.cache import Cache, MemoryTTLCache
from shared.clients.mcp_integration.models import (
    DuplicateToolError,
    MCPClientError,
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


def test_model_values_are_frozen_and_slotted() -> None:
    config = MCPServerConfig("one", "https://one.test/mcp")
    tool = MCPTool(
        "search",
        "Search",
        "Search records",
        {"type": "object"},
        {"type": "string"},
    )
    result = ToolResult(({"type": "text", "text": "found"},), {"count": 1}, False)

    assert config == MCPServerConfig("one", "https://one.test/mcp", 30.0, {})
    assert tool.input_schema == {"type": "object"}
    assert tool.output_schema == {"type": "string"}
    assert result.content == ({"type": "text", "text": "found"},)
    assert result.structured_content == {"count": 1}
    with pytest.raises(FrozenInstanceError):
        config.name = "other"  # type: ignore[misc]
    assert not hasattr(config, "__dict__")


def test_server_config_hides_headers() -> None:
    config = MCPServerConfig(
        "one",
        "https://one.test/mcp",
        10,
        {"Authorization": "secret"},
    )

    assert "Authorization" not in repr(config)
    assert "secret" not in repr(config)


def test_configuration_error_retains_message() -> None:
    error = MCPConfigurationError("exactly three servers are required")

    assert isinstance(error, MCPClientError)
    assert error.message == "exactly three servers are required"
    assert str(error) == error.message


@pytest.mark.parametrize(
    ("error", "fields", "message"),
    [
        (
            MCPClientStateError("list tools"),
            {"operation": "list tools"},
            "MCP client is not active for operation 'list tools'",
        ),
        (
            MCPConnectionError("one", "connect"),
            {"server_name": "one", "operation": "connect"},
            "MCP server 'one' failed to connect during 'connect'",
        ),
        (
            MCPTimeoutError("one", "list tools"),
            {"server_name": "one", "operation": "list tools"},
            "MCP server 'one' timed out during 'list tools'",
        ),
        (
            MCPProtocolError("one", "call tool"),
            {"server_name": "one", "operation": "call tool"},
            "MCP server 'one' returned a protocol error during 'call tool'",
        ),
        (
            DuplicateToolError("search", ("one", "two")),
            {"tool_name": "search", "sources": ("one", "two")},
            "MCP tool 'search' is duplicated across: one, two",
        ),
        (
            ToolNotFoundError("missing"),
            {"tool_name": "missing"},
            "MCP tool 'missing' was not found",
        ),
    ],
)
def test_public_errors_retain_context(
    error: MCPClientError,
    fields: dict[str, object],
    message: str,
) -> None:
    assert isinstance(error, MCPClientError)
    assert str(error) == message
    for name, value in fields.items():
        assert getattr(error, name) == value


def test_model_and_error_types_are_exported() -> None:
    from shared.clients import mcp_integration

    for name in (
        "JSONValue",
        "MCPServerConfig",
        "MCPTool",
        "ToolResult",
        "MCPClientError",
        "MCPConfigurationError",
        "MCPClientStateError",
        "MCPConnectionError",
        "MCPTimeoutError",
        "MCPProtocolError",
        "DuplicateToolError",
        "ToolNotFoundError",
    ):
        assert hasattr(mcp_integration, name)


@pytest.mark.asyncio
async def test_cache_miss_persistent_value_and_deletion() -> None:
    cache = MemoryTTLCache()

    assert await cache.get("tools") is None
    await cache.delete("tools")

    tools = ("search",)
    await cache.set("tools", tools)
    assert await cache.get("tools") is tools

    await cache.delete("tools")
    assert await cache.get("tools") is None


@pytest.mark.asyncio
async def test_cache_ttl_hit_and_expiration() -> None:
    now = [10.0]
    cache = MemoryTTLCache(clock=lambda: now[0])

    await cache.set("tools", ("search",), ttl_seconds=5)
    now[0] = 14.0
    assert await cache.get("tools") == ("search",)

    now[0] = 15.0
    assert await cache.get("tools") is None


@pytest.mark.asyncio
async def test_cache_rejects_none_value() -> None:
    cache = MemoryTTLCache()

    with pytest.raises(ValueError, match="None"):
        await cache.set("tools", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ttl_seconds",
    [0.0, -1.0, math.nan, math.inf, -math.inf],
)
async def test_cache_rejects_non_positive_or_non_finite_ttl(
    ttl_seconds: float,
) -> None:
    cache = MemoryTTLCache()

    with pytest.raises(ValueError, match="positive and finite"):
        await cache.set("tools", ("search",), ttl_seconds=ttl_seconds)


def test_cache_types_are_exported() -> None:
    from shared.clients import mcp_integration

    assert mcp_integration.Cache is Cache
    assert mcp_integration.MemoryTTLCache is MemoryTTLCache


class _FakeSDKClient:
    def __init__(
        self,
        *,
        pages: dict[str | None, ListToolsResult] | None = None,
        call_result: CallToolResult | None = None,
        list_error: BaseException | None = None,
        call_error: BaseException | None = None,
        enter_error: BaseException | None = None,
        exit_error: BaseException | None = None,
        list_delay_seconds: float = 0,
        events: list[str] | None = None,
    ) -> None:
        self.pages = pages or {}
        self.call_result = call_result
        self.list_error = list_error
        self.call_error = call_error
        self.enter_error = enter_error
        self.exit_error = exit_error
        self.list_delay_seconds = list_delay_seconds
        self.events = events
        self.cursors: list[str | None] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "_FakeSDKClient":
        if self.events is not None:
            self.events.append("sdk enter")
        if self.enter_error is not None:
            raise self.enter_error
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self.events is not None:
            self.events.append("sdk exit")
        if self.exit_error is not None:
            raise self.exit_error

    async def list_tools(self, *, cursor: str | None) -> ListToolsResult:
        self.cursors.append(cursor)
        if self.list_delay_seconds:
            await asyncio.sleep(self.list_delay_seconds)
        if self.list_error is not None:
            raise self.list_error
        return self.pages[cursor]

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> CallToolResult:
        self.calls.append((name, arguments))
        if self.call_error is not None:
            raise self.call_error
        assert self.call_result is not None
        return self.call_result


class _FakeHTTPClient:
    def __init__(
        self,
        events: list[str] | None = None,
        *,
        exit_error: BaseException | None = None,
    ) -> None:
        self.events = events
        self.exit_error = exit_error

    async def __aenter__(self) -> "_FakeHTTPClient":
        if self.events is not None:
            self.events.append("http enter")
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        if self.events is not None:
            self.events.append("http exit")
        if self.exit_error is not None:
            raise self.exit_error


def _patch_adapter_seams(
    monkeypatch: pytest.MonkeyPatch,
    sdk_client: _FakeSDKClient,
    http_client: _FakeHTTPClient | None = None,
) -> tuple[dict[str, object], object]:
    import shared.clients.mcp_integration.client as client_module

    construction: dict[str, object] = {}
    transport = object()
    fake_http_client = http_client or _FakeHTTPClient()

    def make_http_client(**kwargs: object) -> _FakeHTTPClient:
        construction["http_kwargs"] = kwargs
        return fake_http_client

    def make_transport(url: str, *, http_client: object) -> object:
        construction["transport_args"] = (url, http_client)
        return transport

    def make_sdk_client(received_transport: object, *, cache: object) -> _FakeSDKClient:
        construction["sdk_args"] = (received_transport, cache)
        return sdk_client

    monkeypatch.setattr(client_module.httpx2, "AsyncClient", make_http_client)
    monkeypatch.setattr(client_module, "streamable_http_client", make_transport)
    monkeypatch.setattr(client_module, "Client", make_sdk_client)
    return construction, transport


@pytest.mark.asyncio
async def test_adapter_pagination_converts_and_copies_real_tool_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    first = Tool(
        name="search",
        title="Search",
        description="Search records",
        inputSchema={"type": "object", "properties": {"query": {"type": "string"}}},
        outputSchema={"type": "array", "items": {"type": "string"}},
    )
    second = Tool(
        name="report",
        inputSchema={"type": "object"},
    )
    sdk_client = _FakeSDKClient(
        pages={
            None: ListToolsResult(tools=[first], nextCursor="page-2"),
            "page-2": ListToolsResult(tools=[second]),
        }
    )
    _patch_adapter_seams(monkeypatch, sdk_client)

    async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")) as client:
        tools = await client.list_tools()

    assert sdk_client.cursors == [None, "page-2"]
    assert tools == [
        MCPTool(
            "search",
            "Search",
            "Search records",
            {"type": "object", "properties": {"query": {"type": "string"}}},
            {"type": "array", "items": {"type": "string"}},
        ),
        MCPTool("report", None, None, {"type": "object"}, None),
    ]
    assert tools[0].input_schema is not first.input_schema
    assert tools[0].output_schema is not first.output_schema
    tools[0].input_schema["properties"]["query"]["type"] = "number"  # type: ignore[index]
    assert first.input_schema["properties"]["query"]["type"] == "string"


@pytest.mark.asyncio
@pytest.mark.parametrize("structured_content", [7, ["one", {"two": 2}], {"count": 1}])
async def test_adapter_conversion_preserves_tool_results_and_copies_arguments(
    monkeypatch: pytest.MonkeyPatch,
    structured_content: object,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    sdk_result = CallToolResult(
        content=[TextContent(text="failed safely")],
        structuredContent=structured_content,
        isError=True,
    )
    sdk_client = _FakeSDKClient(call_result=sdk_result)
    _patch_adapter_seams(monkeypatch, sdk_client)
    arguments = {"nested": {"values": [1, 2]}}

    async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")) as client:
        result = await client.call_tool("search", arguments)
        sdk_client.calls[0][1]["nested"]["values"].append(3)

    assert arguments == {"nested": {"values": [1, 2]}}
    assert result == ToolResult(
        (
            {
                "type": "text",
                "text": "failed safely",
                "annotations": None,
                "_meta": None,
            },
        ),
        structured_content,
        True,
    )
    if isinstance(structured_content, (dict, list)):
        assert result.structured_content is not sdk_result.structured_content


@pytest.mark.asyncio
async def test_adapter_lifecycle_owns_exact_sdk_v2_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    events: list[str] = []
    http_client = _FakeHTTPClient(events)
    sdk_client = _FakeSDKClient(events=events)
    construction, transport = _patch_adapter_seams(
        monkeypatch,
        sdk_client,
        http_client,
    )
    config = MCPServerConfig(
        "one",
        "https://one.test/mcp",
        7.5,
        {"Authorization": "Bearer secret"},
    )

    async with MCPServerClient(config):
        assert events == ["http enter", "sdk enter"]

    assert events == ["http enter", "sdk enter", "sdk exit", "http exit"]
    assert construction["http_kwargs"] == {
        "headers": {"Authorization": "Bearer secret"},
        "timeout": httpx2.Timeout(7.5),
    }
    assert construction["transport_args"] == (config.url, http_client)
    assert construction["sdk_args"] == (transport, None)


@pytest.mark.asyncio
async def test_adapter_lifecycle_preserves_entry_error_when_cleanup_also_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    events: list[str] = []
    entry_error = RuntimeError("sdk entry failed")
    sdk_client = _FakeSDKClient(enter_error=entry_error, events=events)
    http_client = _FakeHTTPClient(
        events,
        exit_error=RuntimeError("http cleanup failed"),
    )
    _patch_adapter_seams(monkeypatch, sdk_client, http_client)

    with pytest.raises(RuntimeError) as caught:
        async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")):
            pass

    assert caught.value is entry_error
    assert events == ["http enter", "sdk enter", "http exit"]


def _validation_error() -> ValidationError:
    return ValidationError.from_exception_data(
        "MCP response",
        [{"type": "missing", "loc": ("result",), "input": {}}],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_error", "expected_type"),
    [
        (TimeoutError("deadline"), MCPTimeoutError),
        (httpx2.ReadTimeout("read deadline"), MCPTimeoutError),
        (httpx2.ConnectError("connection refused"), MCPConnectionError),
        (MCPError(-32603, "bad response"), MCPProtocolError),
        (_validation_error(), MCPProtocolError),
    ],
)
async def test_adapter_error_mapping_has_stable_fields_and_cause(
    monkeypatch: pytest.MonkeyPatch,
    source_error: Exception,
    expected_type: type[Exception],
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    sdk_client = _FakeSDKClient(list_error=source_error)
    _patch_adapter_seams(monkeypatch, sdk_client)

    async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")) as client:
        with pytest.raises(expected_type) as caught:
            await client.list_tools()

    assert caught.value.server_name == "one"  # type: ignore[attr-defined]
    assert caught.value.operation == "list tools"  # type: ignore[attr-defined]
    assert caught.value.__cause__ is source_error


@pytest.mark.asyncio
async def test_adapter_maps_singleton_transport_exception_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    source_error = ExceptionGroup(
        "task group",
        [ExceptionGroup("nested", [httpx2.ConnectError("connection refused")])],
    )
    _patch_adapter_seams(monkeypatch, _FakeSDKClient(enter_error=source_error))

    with pytest.raises(MCPConnectionError) as caught:
        async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")):
            pass

    assert caught.value.__cause__ is source_error


@pytest.mark.asyncio
async def test_adapter_leaves_mixed_exception_group_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    source_error = ExceptionGroup(
        "task group",
        [httpx2.ConnectError("connection refused"), RuntimeError("unexpected")],
    )
    _patch_adapter_seams(monkeypatch, _FakeSDKClient(enter_error=source_error))

    with pytest.raises(ExceptionGroup) as caught:
        async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")):
            pass

    assert caught.value is source_error


@pytest.mark.asyncio
async def test_adapter_pagination_uses_one_total_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    sdk_client = _FakeSDKClient(
        pages={
            None: ListToolsResult(tools=[], nextCursor="page-2"),
            "page-2": ListToolsResult(tools=[]),
        },
        list_delay_seconds=0.04,
    )
    _patch_adapter_seams(monkeypatch, sdk_client)

    async with MCPServerClient(
        MCPServerConfig("one", "https://one.test/mcp", timeout_seconds=0.06)
    ) as client:
        with pytest.raises(MCPTimeoutError):
            await client.list_tools()

    assert sdk_client.cursors == [None, "page-2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source_error",
    [RuntimeError("SDK output schema mismatch"), asyncio.CancelledError()],
)
async def test_adapter_error_does_not_wrap_runtime_or_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    source_error: BaseException,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    sdk_client = _FakeSDKClient(call_error=source_error)
    _patch_adapter_seams(monkeypatch, sdk_client)

    async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")) as client:
        with pytest.raises(type(source_error)) as caught:
            await client.call_tool("search", {})

    assert caught.value is source_error


@pytest.mark.asyncio
async def test_adapter_error_does_not_swallow_shutdown_cancellation_with_body_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from shared.clients.mcp_integration.client import MCPServerClient

    cancellation = asyncio.CancelledError()
    sdk_client = _FakeSDKClient(exit_error=cancellation)
    _patch_adapter_seams(monkeypatch, sdk_client)

    with pytest.raises(asyncio.CancelledError) as caught:
        async with MCPServerClient(MCPServerConfig("one", "https://one.test/mcp")):
            raise RuntimeError("body failed")

    assert caught.value is cancellation


class _FakeServerClient:
    def __init__(
        self,
        name: str,
        events: list[str],
        tools: list[MCPTool] | None = None,
        *,
        enter_error: BaseException | None = None,
        exit_error: BaseException | None = None,
        list_error: BaseException | None = None,
        call_error: BaseException | None = None,
        call_result: ToolResult | None = None,
    ) -> None:
        self.name = name
        self.events = events
        self.tools = tools or []
        self.enter_error = enter_error
        self.exit_error = exit_error
        self.list_error = list_error
        self.call_error = call_error
        self.call_result = call_result or ToolResult((), None, False)
        self.list_count = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __aenter__(self) -> "_FakeServerClient":
        self.events.append(f"enter:{self.name}")
        if self.enter_error is not None:
            raise self.enter_error
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        self.events.append(f"exit:{self.name}")
        if self.exit_error is not None:
            raise self.exit_error

    async def list_tools(self) -> list[MCPTool]:
        self.events.append(f"list:{self.name}")
        self.list_count += 1
        if self.list_error is not None:
            raise self.list_error
        return list(self.tools)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> ToolResult:
        self.calls.append((name, arguments))
        if self.call_error is not None:
            raise self.call_error
        return self.call_result


def _manager_configs() -> list[MCPServerConfig]:
    return [
        MCPServerConfig("one", "https://one.test/mcp"),
        MCPServerConfig("two", "http://two.test/mcp", 5),
        MCPServerConfig("three", "https://three.test/mcp", 10),
    ]


def _tool(name: str) -> MCPTool:
    return MCPTool(name, None, None, {"type": "object"}, None)


def _manager_constructor(
    clients: dict[str, _FakeServerClient],
):
    return lambda config: clients[config.name]


@pytest.mark.parametrize(
    "configs",
    [
        _manager_configs()[:2],
        _manager_configs() + [MCPServerConfig("four", "https://four.test/mcp")],
        [
            MCPServerConfig("one", "https://one.test/mcp"),
            MCPServerConfig("one", "https://two.test/mcp"),
            MCPServerConfig("three", "https://three.test/mcp"),
        ],
        [
            MCPServerConfig(" ", "https://one.test/mcp"),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig("one", "/relative"),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig("one", "ftp://one.test/mcp"),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig("one", "https:///missing-host"),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig("one", "https://one.test/mcp", 0),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig("one", "https://one.test/mcp", -1),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig("one", "https://one.test/mcp", math.nan),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig("one", "https://one.test/mcp", math.inf),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig(
                "one",
                "https://one.test/mcp",
                headers={"Authorization": 7},  # type: ignore[dict-item]
            ),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig(
                "one",
                "https://one.test/mcp",
                headers={7: "secret"},  # type: ignore[dict-item]
            ),
            *_manager_configs()[1:],
        ],
        [
            MCPServerConfig(
                "one",
                "https://one.test/mcp",
                headers=[],  # type: ignore[arg-type]
            ),
            *_manager_configs()[1:],
        ],
    ],
)
def test_manager_config_rejects_invalid_server_configuration(
    configs: list[MCPServerConfig],
) -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    with pytest.raises(MCPConfigurationError):
        MCPClientManager(configs, MemoryTTLCache())


@pytest.mark.parametrize("ttl", [0, -1, math.nan, math.inf, -math.inf])
def test_manager_config_rejects_invalid_discovery_ttl(ttl: float) -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    with pytest.raises(MCPConfigurationError):
        MCPClientManager(_manager_configs(), MemoryTTLCache(), ttl)


def test_manager_config_rejects_non_callable_constructor() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    with pytest.raises(MCPConfigurationError):
        MCPClientManager(
            _manager_configs(),
            MemoryTTLCache(),
            client_constructor=None,  # type: ignore[arg-type]
        )


def test_manager_snapshots_mutable_headers_at_construction() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    headers = {"Authorization": "Bearer original"}
    configs = [
        MCPServerConfig("one", "https://one.test/mcp", headers=headers),
        *_manager_configs()[1:],
    ]
    captured: list[MCPServerConfig] = []
    events: list[str] = []
    clients = {
        name: _FakeServerClient(name, events)
        for name in ("one", "two", "three")
    }

    MCPClientManager(
        configs,
        MemoryTTLCache(),
        client_constructor=lambda config: (
            captured.append(config) or clients[config.name]
        ),
    )
    headers["Authorization"] = "Bearer changed"

    assert captured[0].headers == {"Authorization": "Bearer original"}


@pytest.mark.asyncio
async def test_manager_lifecycle_enters_discovers_and_exits_in_order() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events, [_tool("zeta")]),
        "two": _FakeServerClient("two", events, [_tool("alpha")]),
        "three": _FakeServerClient("three", events, [_tool("middle")]),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        assert events == [
            "enter:one",
            "enter:two",
            "enter:three",
            "list:one",
            "list:two",
            "list:three",
        ]
        assert [tool.name for tool in await manager.list_tools()] == [
            "alpha",
            "middle",
            "zeta",
        ]

    assert events[-3:] == ["exit:three", "exit:two", "exit:one"]


@pytest.mark.asyncio
async def test_manager_lifecycle_requires_active_single_use_context() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    clients = {
        config.name: _FakeServerClient(config.name, events)
        for config in _manager_configs()
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    with pytest.raises(MCPClientStateError):
        await manager.list_tools()
    with pytest.raises(MCPClientStateError):
        await manager.refresh_tools()

    async with manager:
        pass

    with pytest.raises(MCPClientStateError):
        await manager.list_tools()
    with pytest.raises(MCPClientStateError):
        async with manager:
            pass


@pytest.mark.asyncio
async def test_manager_lifecycle_closes_partial_startup() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    startup_error = RuntimeError("second enter failed")
    clients = {
        "one": _FakeServerClient("one", events),
        "two": _FakeServerClient("two", events, enter_error=startup_error),
        "three": _FakeServerClient("three", events),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    with pytest.raises(RuntimeError) as caught:
        async with manager:
            pass

    assert caught.value is startup_error
    assert events == ["enter:one", "enter:two", "exit:one"]


@pytest.mark.asyncio
async def test_manager_lifecycle_closes_all_clients_after_discovery_failure() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    discovery_error = RuntimeError("discovery failed")
    clients = {
        "one": _FakeServerClient("one", events),
        "two": _FakeServerClient("two", events, list_error=discovery_error),
        "three": _FakeServerClient("three", events),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    with pytest.raises(RuntimeError) as caught:
        async with manager:
            pass

    assert caught.value is discovery_error
    assert events == [
        "enter:one",
        "enter:two",
        "enter:three",
        "list:one",
        "list:two",
        "exit:three",
        "exit:two",
        "exit:one",
    ]


@pytest.mark.asyncio
async def test_manager_lifecycle_preserves_startup_error_over_cleanup_error() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    startup_error = RuntimeError("second enter failed")
    clients = {
        "one": _FakeServerClient(
            "one",
            events,
            exit_error=RuntimeError("cleanup failed"),
        ),
        "two": _FakeServerClient("two", events, enter_error=startup_error),
        "three": _FakeServerClient("three", events),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    with pytest.raises(RuntimeError) as caught:
        async with manager:
            pass

    assert caught.value is startup_error
    assert events == ["enter:one", "enter:two", "exit:one"]


@pytest.mark.asyncio
async def test_manager_discovery_uses_cache_then_force_refreshes_all_servers() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events, [_tool("zeta")]),
        "two": _FakeServerClient("two", events, [_tool("alpha")]),
        "three": _FakeServerClient("three", events, [_tool("middle")]),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        clients["one"].tools = [_tool("beta")]
        cached = await manager.refresh_tools()
        assert [tool.name for tool in cached] == ["alpha", "middle", "zeta"]
        assert [client.list_count for client in clients.values()] == [1, 1, 1]

        refreshed = await manager.refresh_tools(force=True)
        assert [tool.name for tool in refreshed] == ["alpha", "beta", "middle"]
        assert [client.list_count for client in clients.values()] == [2, 2, 2]


@pytest.mark.asyncio
async def test_manager_discovery_treats_invalid_cached_object_as_miss() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    cache = MemoryTTLCache()
    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events, [_tool("live-one")]),
        "two": _FakeServerClient("two", events, [_tool("live-two")]),
        "three": _FakeServerClient("three", events, [_tool("live-three")]),
    }
    manager = MCPClientManager(
        _manager_configs(),
        cache,
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        await cache.set("mcp:tools:one", ["not-a-tool"])
        clients["one"].tools = [_tool("new-live-one")]
        assert [tool.name for tool in await manager.refresh_tools()] == [
            "live-three",
            "live-two",
            "new-live-one",
        ]

    assert [client.list_count for client in clients.values()] == [2, 1, 1]
    assert await cache.get("mcp:tools:one") == (_tool("new-live-one"),)


@pytest.mark.asyncio
async def test_manager_startup_ignores_warm_cache_and_primes_live_clients() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    cache = MemoryTTLCache()
    for name in ("one", "two", "three"):
        await cache.set(f"mcp:tools:{name}", (_tool(f"stale-{name}"),))
    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events, [_tool("live-one")]),
        "two": _FakeServerClient("two", events, [_tool("live-two")]),
        "three": _FakeServerClient("three", events, [_tool("live-three")]),
    }
    manager = MCPClientManager(
        _manager_configs(),
        cache,
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        assert [tool.name for tool in await manager.list_tools()] == [
            "live-one",
            "live-three",
            "live-two",
        ]
        await manager.call_tool("live-one", {})

    assert [client.list_count for client in clients.values()] == [1, 1, 1]
    assert clients["one"].calls == [("live-one", {})]


@pytest.mark.asyncio
async def test_manager_discovery_failed_refresh_retains_published_registry() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    cache = MemoryTTLCache()
    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events, [_tool("one-old")]),
        "two": _FakeServerClient("two", events, [_tool("two-old")]),
        "three": _FakeServerClient("three", events, [_tool("three-old")]),
    }
    manager = MCPClientManager(
        _manager_configs(),
        cache,
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        clients["one"].tools = [_tool("one-new")]
        refresh_error = RuntimeError("refresh failed")
        clients["two"].list_error = refresh_error

        with pytest.raises(RuntimeError) as caught:
            await manager.refresh_tools(force=True)

        assert caught.value is refresh_error
        assert [tool.name for tool in await manager.list_tools()] == [
            "one-old",
            "three-old",
            "two-old",
        ]
        assert await cache.get("mcp:tools:one") == (_tool("one-old"),)


@pytest.mark.asyncio
async def test_manager_discovery_duplicate_refresh_is_not_published_or_cached() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    cache = MemoryTTLCache()
    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events, [_tool("one-old")]),
        "two": _FakeServerClient("two", events, [_tool("two-old")]),
        "three": _FakeServerClient("three", events, [_tool("three-old")]),
    }
    manager = MCPClientManager(
        _manager_configs(),
        cache,
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        clients["one"].tools = [_tool("duplicate")]
        clients["two"].tools = [_tool("duplicate")]

        with pytest.raises(DuplicateToolError):
            await manager.refresh_tools(force=True)

        assert [tool.name for tool in await manager.list_tools()] == [
            "one-old",
            "three-old",
            "two-old",
        ]
        assert await cache.get("mcp:tools:one") == (_tool("one-old"),)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tools_by_server", "sources"),
    [
        ({"one": [_tool("same"), _tool("same")]}, ("one", "one")),
        (
            {
                "one": [_tool("same"), _tool("same")],
                "two": [_tool("same")],
            },
            ("one", "one", "two"),
        ),
    ],
)
async def test_manager_discovery_duplicate_sources_keep_every_ordered_occurrence(
    tools_by_server: dict[str, list[MCPTool]],
    sources: tuple[str, ...],
) -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    clients = {
        config.name: _FakeServerClient(
            config.name,
            events,
            tools_by_server.get(config.name, []),
        )
        for config in _manager_configs()
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    with pytest.raises(DuplicateToolError) as caught:
        async with manager:
            pass

    assert caught.value.tool_name == "same"
    assert caught.value.sources == sources
    assert events[-3:] == ["exit:three", "exit:two", "exit:one"]


def test_manager_is_exported() -> None:
    from shared.clients import mcp_integration
    from shared.clients.mcp_integration.client import MCPClientManager

    assert mcp_integration.MCPClientManager is MCPClientManager


@pytest.mark.asyncio
async def test_manager_routing_delegates_once_to_owner_and_preserves_result() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    expected = ToolResult(({"type": "text", "text": "failed"},), ["detail"], True)
    clients = {
        "one": _FakeServerClient("one", events, [_tool("first")]),
        "two": _FakeServerClient(
            "two", events, [_tool("target")], call_result=expected
        ),
        "three": _FakeServerClient("three", events, [_tool("last")]),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )
    arguments = {"nested": {"value": 7}}

    async with manager:
        result = await manager.call_tool("target", arguments)

    assert result is expected
    assert clients["two"].calls == [("target", arguments)]
    assert clients["one"].calls == clients["three"].calls == []


@pytest.mark.asyncio
async def test_manager_routing_unknown_tool_is_entirely_local() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    cache = MemoryTTLCache()
    clients = {
        config.name: _FakeServerClient(config.name, events, [_tool(config.name)])
        for config in _manager_configs()
    }
    manager = MCPClientManager(
        _manager_configs(),
        cache,
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        list_counts = [client.list_count for client in clients.values()]

        async def unexpected_cache_access(*args: object, **kwargs: object) -> None:
            raise AssertionError("unknown-tool lookup accessed discovery cache")

        cache.get = unexpected_cache_access  # type: ignore[method-assign]
        cache.set = unexpected_cache_access  # type: ignore[method-assign]
        cache.delete = unexpected_cache_access  # type: ignore[method-assign]
        with pytest.raises(ToolNotFoundError) as caught:
            await manager.call_tool("missing", {})

        assert caught.value.tool_name == "missing"
        assert [client.list_count for client in clients.values()] == list_counts
        assert all(not client.calls for client in clients.values())


@pytest.mark.asyncio
async def test_manager_routing_failed_refresh_keeps_previous_owner() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events, [_tool("stable")]),
        "two": _FakeServerClient("two", events),
        "three": _FakeServerClient("three", events),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    async with manager:
        clients["one"].tools = [_tool("replacement")]
        clients["two"].list_error = RuntimeError("refresh failed")
        with pytest.raises(RuntimeError, match="refresh failed"):
            await manager.refresh_tools(force=True)

        await manager.call_tool("stable", {})

    assert clients["one"].calls == [("stable", {})]


@pytest.mark.asyncio
async def test_manager_routing_requires_active_context() -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    events: list[str] = []
    clients = {
        config.name: _FakeServerClient(config.name, events)
        for config in _manager_configs()
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    with pytest.raises(MCPClientStateError) as before:
        await manager.call_tool("missing", {})
    async with manager:
        pass
    with pytest.raises(MCPClientStateError) as after:
        await manager.call_tool("missing", {})

    assert before.value.operation == after.value.operation == "call tool"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "application_error",
    [
        MCPTimeoutError("two", "call tool"),
        MCPConnectionError("two", "call tool"),
        MCPProtocolError("two", "call tool"),
        asyncio.CancelledError(),
    ],
)
async def test_manager_error_propagates_adapter_errors_unchanged(
    application_error: BaseException,
) -> None:
    from shared.clients.mcp_integration.client import MCPClientManager

    cause = RuntimeError("adapter cause")
    application_error.__cause__ = cause
    events: list[str] = []
    clients = {
        "one": _FakeServerClient("one", events),
        "two": _FakeServerClient(
            "two", events, [_tool("target")], call_error=application_error
        ),
        "three": _FakeServerClient("three", events),
    }
    manager = MCPClientManager(
        _manager_configs(),
        MemoryTTLCache(),
        client_constructor=_manager_constructor(clients),
    )

    with pytest.raises(type(application_error)) as caught:
        async with manager:
            await manager.call_tool("target", {})

    assert caught.value is application_error
    assert caught.value.__cause__ is cause
    if not isinstance(application_error, asyncio.CancelledError):
        assert application_error.server_name == "two"  # type: ignore[attr-defined]
        assert application_error.operation == "call tool"  # type: ignore[attr-defined]
    assert clients["two"].calls == [("target", {})]
