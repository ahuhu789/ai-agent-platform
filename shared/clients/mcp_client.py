from copy import deepcopy

from shared.abstractions.mcp_client import BaseMCPClient, MCPToolResult, ToolDefinition

from .mcp_integration import MCPClientManager


class PlatformMCPClient(BaseMCPClient):
    """Adapt the MCP v2 manager to the platform's existing client contract."""

    def __init__(self, manager: MCPClientManager) -> None:
        self._manager = manager

    async def __aenter__(self) -> "PlatformMCPClient":
        await self._manager.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> bool | None:
        return await self._manager.__aexit__(exc_type, exc, traceback)

    async def list_tools(self, server_name: str) -> list[ToolDefinition]:
        tools = await self._manager.list_server_tools(server_name)
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description or "",
                input_schema=deepcopy(dict(tool.input_schema)),
            )
            for tool in tools
        ]

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict,
    ) -> MCPToolResult:
        result = await self._manager.call_server_tool(
            server_name,
            tool_name,
            arguments,
        )
        payload = result.structured_content
        if isinstance(payload, dict) and isinstance(payload.get("success"), bool):
            metadata = payload.get("metadata")
            return MCPToolResult(
                success=payload["success"],
                data=deepcopy(payload.get("data")),
                error=payload.get("error"),
                metadata=deepcopy(metadata) if isinstance(metadata, dict) else {},
            )

        return MCPToolResult(
            success=not result.is_error,
            data=deepcopy(payload) if payload is not None else deepcopy(result.content),
            error="MCP tool returned an error" if result.is_error else None,
            metadata={"server_name": server_name, "tool_name": tool_name},
        )
