"""Employee MCP Server implementation supporting stdio and SSE transports."""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("mcp.employee")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

# Ensure project root is in sys.path
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.abspath(os.path.join(_current_dir, "..", ".."))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP as MCPServer
    except ImportError:
        from mcp.server import Server as MCPServer

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from .function_support import EmployeeFunctionSupport, MockEmployeeSupport, RealEmployeeSupport
    from .tools import EmployeeTools
except (ImportError, ValueError):
    from mcp_servers.employee.function_support import EmployeeFunctionSupport, MockEmployeeSupport, RealEmployeeSupport
    from mcp_servers.employee.tools import EmployeeTools

# Create MCPServer instance
mcp_server = MCPServer(
    name="Employee MCP Server",
    instructions="MCP Server cung cấp các Tool truy vấn dữ liệu Nhân sự (Employee) cho AI Chatbot FME.",
)

_api_url = os.getenv("EMPLOYEE_API_URL")
if _api_url:
    _support = RealEmployeeSupport(api_url=_api_url, api_token=os.getenv("EMPLOYEE_API_TOKEN"))
else:
    _support = MockEmployeeSupport()

_tools_instance = EmployeeTools(_support)


def set_function_support(support: EmployeeFunctionSupport):
    """Dynamically replace function support (useful for switching mock/real or testing)."""
    global _support, _tools_instance
    _support = support
    _tools_instance = EmployeeTools(_support)


@mcp_server.tool(
    name="search_employees",
    description="Tìm kiếm danh sách nhân viên theo từ khóa (tên, chức danh, mã NV), phòng ban hoặc trạng thái làm việc.",
)
async def search_employees(
    keyword: Optional[str] = None,
    department_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    return _tools_instance.search_employees(keyword=keyword, department_id=department_id, status=status, limit=limit)


@mcp_server.tool(
    name="get_employee_profile",
    description="Lấy thông tin chi tiết hồ sơ nhân viên theo mã nhân viên (ví dụ: NV001).",
)
async def get_employee_profile(employee_id: str) -> Dict[str, Any]:
    return _tools_instance.get_employee_profile(employee_id=employee_id)


@mcp_server.tool(
    name="get_department_list",
    description="Lấy danh sách tất cả các phòng ban trong công ty kèm thông tin trưởng phòng và số lượng nhân sự.",
)
async def get_department_list() -> Dict[str, Any]:
    return _tools_instance.get_department_list()


@mcp_server.tool(
    name="get_employee_department",
    description="Tra cứu nhân viên thuộc phòng ban nào hoặc tìm phòng ban theo mã/tên nhân viên (ví dụ: 'NV001' hoặc 'Nguyễn Văn A').",
)
async def get_employee_department(identifier: str) -> Dict[str, Any]:
    return _tools_instance.get_employee_department(identifier=identifier)


@mcp_server.tool(
    name="get_employee_summary",
    description="Lấy báo cáo thống kê nhân sự toàn công ty hoặc theo từng phòng ban.",
)
async def get_employee_summary(department_id: Optional[str] = None) -> Dict[str, Any]:
    return _tools_instance.get_employee_summary(department_id=department_id)


def main():
    parser = argparse.ArgumentParser(description="Chạy Employee MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="Giao thức truyền thông (mặc định: stdio)")
    parser.add_argument("--port", type=int, default=8002, help="Cổng chạy SSE server (mặc định: 8002)")
    parser.add_argument("--host", default="0.0.0.0", help="Host bind cho SSE server")
    parser.add_argument("--real-api", action="store_true", help="Kết nối API backend thật thay vì mock data")
    args = parser.parse_args()

    if args.real_api:
        set_function_support(RealEmployeeSupport())
        logger.info("Đang sử dụng RealEmployeeSupport kết nối backend API.")
    else:
        logger.info("Đang sử dụng MockEmployeeSupport với dữ liệu giả lập.")

    if args.transport == "sse":
        logger.info("Khởi động Employee MCP Server qua SSE tại http://%s:%d/sse", args.host, args.port)
        if hasattr(mcp_server, "run_sse_async"):
            asyncio.run(mcp_server.run_sse_async(host=args.host, port=args.port))
        else:
            mcp_server.run(transport="sse")
    else:
        logger.info("Khởi động Employee MCP Server qua stdio...")
        if hasattr(mcp_server, "run_stdio_async"):
            asyncio.run(mcp_server.run_stdio_async())
        else:
            mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()
