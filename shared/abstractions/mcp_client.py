from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: Dict[str, Any]


@dataclass
class MCPToolResult:
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseMCPClient(ABC):
    """
    Interface trừu tượng cho MCP Client kết nối đến các MCP Server phân hệ.
    Phụ trách bởi: Thành viên 5 - Nhóm Core Chatbot.
    Tham chiếu: docs/AI_Plan.pdf (Mục 3.1 - Thành viên 5)
    """

    @abstractmethod
    async def list_tools(self, server_name: str) -> List[ToolDefinition]:
        """Lấy danh sách các tool từ MCP Server tương ứng."""
        raise NotImplementedError

    @abstractmethod
    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> MCPToolResult:
        """Thực thi một tool trên MCP Server chỉ định."""
        raise NotImplementedError
