"""
MultiServerMCPClient - Concrete implementation của BaseMCPClient.
Quản lý kết nối tới các MCP Server phân hệ (hiring, attendance, employee) qua stdio.
Hỗ trợ cả giao diện bất đồng bộ (async) và đồng bộ (sync) thông qua background event loop.
"""
import sys
import os
import json
import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack

from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

from shared.abstractions.mcp_client import BaseMCPClient, ToolDefinition, MCPToolResult

logger = logging.getLogger("mcp.client")


class MultiServerMCPClient(BaseMCPClient):
    """MCP Client kết nối nhiều MCP Server đồng thời."""

    def __init__(self, server_configs: Optional[Dict[str, Dict[str, Any]]] = None):
        self.server_configs = server_configs or {}
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()
        self._started = False
        self._lock = threading.Lock()

        # Dedicated background loop & thread để hỗ trợ gọi sync an toàn từ mọi thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="MCPClientLoop")
        self._thread.start()

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_coroutine(self, coro, timeout: float = 30.0):
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ------------------ Quản lý vòng đời kết nối ------------------

    async def _connect_server_async(self, name: str, config: Dict[str, Any]) -> bool:
        if name in self.sessions:
            return True

        command = config.get("command", sys.executable)
        args = config.get("args", [])
        env = {**os.environ, **config.get("env", {})}

        try:
            params = StdioServerParameters(command=command, args=args, env=env)
            read_stream, write_stream = await self._exit_stack.enter_async_context(stdio_client(params))
            session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            self.sessions[name] = session
            logger.info("MCP Client kết nối thành công tới server: %s", name)
            return True
        except Exception as e:
            logger.warning("MCP Client không thể kết nối tới server %s: %s", name, e)
            return False

    async def _connect_all_async(self):
        for name, config in self.server_configs.items():
            await self._connect_server_async(name, config)
        self._started = True

    def connect_all(self, timeout: float = 30.0):
        """Khởi động và kết nối toàn bộ MCP Servers được cấu hình (gọi đồng bộ)."""
        with self._lock:
            if not self._started:
                self._run_coroutine(self._connect_all_async(), timeout=timeout)

    async def _disconnect_all_async(self):
        try:
            await self._exit_stack.aclose()
        except Exception as e:
            logger.debug("Lỗi khi đóng MCP sessions: %s", e)
        finally:
            self.sessions.clear()
            self._started = False

    def disconnect_all(self, timeout: float = 10.0):
        """Đóng toàn bộ kết nối MCP Servers."""
        with self._lock:
            if self._started:
                try:
                    self._run_coroutine(self._disconnect_all_async(), timeout=timeout)
                except Exception:
                    pass

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

    def list_tools_sync(self, server_name: str, timeout: float = 15.0) -> List[ToolDefinition]:
        """Lấy danh sách tools (gọi đồng bộ)."""
        return self._run_coroutine(self.list_tools(server_name), timeout=timeout)

    def call_tool_sync(self, server_name: str, tool_name: str, arguments: Dict[str, Any], timeout: float = 30.0) -> MCPToolResult:
        """Thực thi tool (gọi đồng bộ)."""
        return self._run_coroutine(self.call_tool(server_name, tool_name, arguments), timeout=timeout)
