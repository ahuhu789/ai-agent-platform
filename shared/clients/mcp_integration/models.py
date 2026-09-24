from dataclasses import dataclass, field
from typing import Mapping, TypeAlias


JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


@dataclass(frozen=True, slots=True)
class MCPServerConfig:
    name: str
    url: str
    timeout_seconds: float = 30.0
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)


@dataclass(frozen=True, slots=True)
class MCPTool:
    name: str
    title: str | None
    description: str | None
    input_schema: Mapping[str, JSONValue]
    output_schema: Mapping[str, JSONValue] | None


@dataclass(frozen=True, slots=True)
class ToolResult:
    content: tuple[Mapping[str, JSONValue], ...]
    structured_content: JSONValue
    is_error: bool


class MCPClientError(Exception):
    """Base class for stable application-facing MCP errors."""


class MCPConfigurationError(MCPClientError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class MCPClientStateError(MCPClientError):
    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(f"MCP client is not active for operation '{operation}'")


class MCPConnectionError(MCPClientError):
    def __init__(self, server_name: str, operation: str) -> None:
        self.server_name = server_name
        self.operation = operation
        super().__init__(f"MCP server '{server_name}' failed to connect during '{operation}'")


class MCPTimeoutError(MCPClientError):
    def __init__(self, server_name: str, operation: str) -> None:
        self.server_name = server_name
        self.operation = operation
        super().__init__(f"MCP server '{server_name}' timed out during '{operation}'")


class MCPProtocolError(MCPClientError):
    def __init__(self, server_name: str, operation: str) -> None:
        self.server_name = server_name
        self.operation = operation
        super().__init__(
            f"MCP server '{server_name}' returned a protocol error during '{operation}'"
        )


class DuplicateToolError(MCPClientError):
    def __init__(self, tool_name: str, sources: tuple[str, ...]) -> None:
        self.tool_name = tool_name
        self.sources = sources
        super().__init__(f"MCP tool '{tool_name}' is duplicated across: {', '.join(sources)}")


class ToolNotFoundError(MCPClientError):
    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"MCP tool '{tool_name}' was not found")
