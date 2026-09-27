"""
MultiServerMCPClient - Concrete implementation của BaseMCPClient.
Quản lý kết nối tới các MCP Server phân hệ (hiring, attendance, employee) qua stdio.
Hỗ trợ cả giao diện bất đồng bộ (async) và đồng bộ (sync) thông qua background event loop.
"""
import sys
import os
import json
import asyncio
import concurrent.futures
import logging
import math
import threading
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from shared.abstractions.mcp_client import BaseMCPClient, ToolDefinition, MCPToolResult

logger = logging.getLogger("mcp.client")


class MCPConnectionError(RuntimeError):
    """Raised when one or more MCP server connections fail."""


def _positive_number(value: Any, name: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be a positive finite number") from None
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be a positive finite number")
    return number


class MultiServerMCPClient(BaseMCPClient):
    """MCP Client kết nối nhiều MCP Server đồng thời."""

    def __init__(self, server_configs: Optional[Dict[str, Dict[str, Any]]] = None):
        self.server_configs = server_configs or {}
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()
        self._started = False
        self._lock = threading.Lock()
        self.connect_timeout = _positive_number(
            os.getenv("MCP_CONNECT_TIMEOUT_SECONDS", 10),
            "MCP_CONNECT_TIMEOUT_SECONDS",
        )
        self.operation_timeout = _positive_number(
            os.getenv("MCP_OPERATION_TIMEOUT_SECONDS", 30),
            "MCP_OPERATION_TIMEOUT_SECONDS",
        )
        self.discovery_ttl = _positive_number(
            os.getenv("MCP_DISCOVERY_TTL_SECONDS", 60),
            "MCP_DISCOVERY_TTL_SECONDS",
        )
        self.server_status = {
            name: "disconnected" for name in self.server_configs
        }

        self._loop = None
        self._thread = None

    @staticmethod
    def _run_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def _start_loop(self):
        if self._loop is not None:
            return
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(self._loop,),
            daemon=True,
            name="MCPClientLoop",
        )
        self._thread.start()

    def _stop_loop(self):
        loop, thread = self._loop, self._thread
        try:
            if loop is not None and not loop.is_closed():
                loop.call_soon_threadsafe(loop.stop)
            if thread is not None and thread.is_alive():
                thread.join()
            if loop is not None and not loop.is_closed():
                loop.close()
        finally:
            self._loop = None
            self._thread = None

    def _run_coroutine(self, coro, bridge_timeout: float):
        if self._loop is None:
            coro.close()
            raise RuntimeError("MCP client event loop is not running")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=bridge_timeout)
        except concurrent.futures.TimeoutError:
            future.cancel()
            raise

    # ------------------ Quản lý vòng đời kết nối ------------------

    async def _connect_server_async(self, name: str, config: Dict[str, Any]) -> None:
        if name in self.sessions:
            return

        command = config.get("command", sys.executable)
        args = config.get("args", [])
        env = {**os.environ, **config.get("env", {})}

        params = StdioServerParameters(command=command, args=args, env=env)
        read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(params))
        session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
        await session.initialize()
        self.sessions[name] = session
        logger.info("MCP Client kết nối thành công tới server: %s", name)

    async def _connect_all_async(self):
        failures = []
        for name, config in self.server_configs.items():
            self.server_status[name] = "connecting"
            try:
                await asyncio.wait_for(
                    self._connect_server_async(name, config),
                    timeout=self.connect_timeout,
                )
            except Exception as exc:
                self.server_status[name] = "failed"
                failures.append(name)
                logger.warning(
                    "MCP Client không thể kết nối tới server %s: %s", name, exc
                )
            else:
                self.server_status[name] = "connected"

        if failures:
            try:
                await asyncio.wait_for(
                    self._disconnect_all_async(preserve_failed=True),
                    timeout=self.operation_timeout,
                )
            except Exception as exc:
                logger.debug("Lỗi khi dọn dẹp MCP startup: %s", exc)
            raise MCPConnectionError(
                f"Failed to connect to MCP servers: {', '.join(failures)}"
            )
        self._started = True

    def connect_all(self):
        """Khởi động và kết nối toàn bộ MCP Servers được cấu hình (gọi đồng bộ)."""
        with self._lock:
            if self._started:
                return
            self._start_loop()
            bridge_timeout = (
                max(1, len(self.server_configs)) * self.connect_timeout
                + self.operation_timeout
                + 2
            )
            try:
                self._run_coroutine(self._connect_all_async(), bridge_timeout)
            except Exception:
                try:
                    if self._loop is not None:
                        self._run_coroutine(
                            self._disconnect_all_async(preserve_failed=True),
                            self.operation_timeout + 1,
                        )
                except Exception as exc:
                    logger.debug("Lỗi khi dọn dẹp MCP startup: %s", exc)
                finally:
                    self._stop_loop()
                raise

    async def _disconnect_all_async(self, preserve_failed: bool = False):
        try:
            await self._exit_stack.aclose()
        finally:
            self.sessions.clear()
            self._started = False
            self._exit_stack = AsyncExitStack()
            for name, status in self.server_status.items():
                if not preserve_failed or status != "failed":
                    self.server_status[name] = "disconnected"

    def disconnect_all(self):
        """Đóng toàn bộ kết nối MCP Servers."""
        with self._lock:
            try:
                if self._loop is not None:
                    self._run_coroutine(
                        self._disconnect_all_async(),
                        self.operation_timeout + 1,
                    )
            except Exception as exc:
                logger.debug("Lỗi khi đóng MCP sessions: %s", exc)
            finally:
                try:
                    self._stop_loop()
                finally:
                    self.sessions.clear()
                    self._started = False
                    for name in self.server_status:
                        self.server_status[name] = "disconnected"

    # ------------------ Thực thi Tool (BaseMCPClient) ------------------

    async def list_tools(self, server_name: str) -> List[ToolDefinition]:
        """Lấy danh sách các tool từ MCP Server chỉ định."""
        session = self.sessions.get(server_name)
        if not session:
            logger.warning("Server '%s' chưa được kết nối", server_name)
            return []

        try:
            response = await session.list_tools()
            results = []
            for t in response.tools:
                schema = getattr(t, "inputSchema", getattr(t, "input_schema", {}))
                results.append(ToolDefinition(
                    name=t.name,
                    description=t.description or "",
                    input_schema=schema,
                ))
            return results
        except Exception as e:
            logger.error("Lỗi khi lấy danh sách tools từ %s: %s", server_name, e)
            return []

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """Thực thi một tool trên MCP Server chỉ định (Async)."""
        session = self.sessions.get(server_name)
        if not session:
            return MCPToolResult(
                success=False,
                error=f"MCP Server '{server_name}' không tồn tại hoặc chưa kết nối.",
                metadata={"server": server_name, "tool": tool_name},
            )

        try:
            response = await session.call_tool(tool_name, arguments or {})

            # Tổng hợp nội dung trả về từ CallToolResult
            text_parts = []
            for item in getattr(response, "content", []):
                if getattr(item, "type", None) == "text":
                    text_parts.append(item.text)

            text_output = "\n".join(text_parts) if text_parts else ""

            # Giải mã JSON trả về từ MCP Server
            try:
                data = json.loads(text_output)
                if isinstance(data, dict):
                    # Schema ToolResponse chuẩn của dự án: {"success": bool, "data": ..., "error": ..., "metadata": ...}
                    if "success" in data:
                        return MCPToolResult(
                            success=bool(data.get("success", False)),
                            data=data.get("data"),
                            error=data.get("error"),
                            metadata={"server": server_name, **data.get("metadata", {})},
                        )
                    return MCPToolResult(
                        success=not getattr(response, "isError", False),
                        data=data,
                        metadata={"server": server_name},
                    )
            except (json.JSONDecodeError, TypeError):
                pass

            return MCPToolResult(
                success=not getattr(response, "isError", False),
                data=text_output,
                metadata={"server": server_name},
            )

        except Exception as e:
            logger.error("Lỗi thực thi tool '%s' trên server '%s': %s", tool_name, server_name, e)
            return MCPToolResult(
                success=False,
                error=f"Lỗi MCP: {str(e)}",
                metadata={"server": server_name, "tool": tool_name},
            )

    # ------------------ Giao diện Đồng bộ (Sync) ------------------

    def list_tools_sync(self, server_name: str) -> List[ToolDefinition]:
        """Lấy danh sách tools (gọi đồng bộ)."""
        return self._run_coroutine(
            self.list_tools(server_name), self.operation_timeout + 1
        )

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """Thực thi tool (gọi đồng bộ)."""
        return self._run_coroutine(
            self.call_tool(server_name, tool_name, arguments),
            self.operation_timeout + 1,
        )
