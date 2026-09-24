"""Attendance MCP Server implementation supporting stdio and SSE transports."""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("mcp.attendance")
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
    from .function_support import AttendanceFunctionSupport, MockAttendanceSupport, RealAttendanceSupport
    from .tools import AttendanceTools
except (ImportError, ValueError):
    from mcp_servers.attendance.function_support import AttendanceFunctionSupport, MockAttendanceSupport, RealAttendanceSupport
    from mcp_servers.attendance.tools import AttendanceTools

# Create MCPServer instance
mcp_server = MCPServer(
    name="Attendance MCP Server",
    instructions="MCP Server cung cấp các Tool truy vấn dữ liệu Chuyên cần (Attendance) cho AI Chatbot FME.",
)

_api_url = os.getenv("ATTENDANCE_API_URL")
if _api_url:
    _support = RealAttendanceSupport(api_url=_api_url, api_token=os.getenv("ATTENDANCE_API_TOKEN"))
else:
    _support = MockAttendanceSupport()

_tools_instance = AttendanceTools(_support)


def set_function_support(support: AttendanceFunctionSupport):
    """Dynamically replace function support (useful for switching mock/real or testing)."""
    global _support, _tools_instance
    _support = support
    _tools_instance = AttendanceTools(_support)


@mcp_server.tool(
    name="get_attendance_history",
    description="Tra cứu lịch sử chấm công của nhân viên theo mã nhân viên và khoảng thời gian (from_date, to_date).",
)
async def get_attendance_history(
    employee_id: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 30,
) -> Dict[str, Any]:
    return _tools_instance.get_attendance_history(employee_id=employee_id, from_date=from_date, to_date=to_date, limit=limit)


@mcp_server.tool(
    name="get_monthly_attendance",
    description="Tổng hợp số ngày đi làm, vắng mặt, tỷ lệ chuyên cần theo tháng của nhân viên.",
)
async def get_monthly_attendance(
    employee_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    return _tools_instance.get_monthly_attendance(employee_id=employee_id, month=month, year=year)


@mcp_server.tool(
    name="get_late_arrival_summary",
    description="Thống kê số lần đi trễ và tổng số phút trễ trong tháng của nhân viên.",
)
async def get_late_arrival_summary(
    employee_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    return _tools_instance.get_late_arrival_summary(employee_id=employee_id, month=month, year=year)


@mcp_server.tool(
    name="get_absence_summary",
    description="Thống kê số ngày vắng mặt, nghỉ phép năm hoặc nghỉ không phép của nhân viên.",
)
async def get_absence_summary(
    employee_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    return _tools_instance.get_absence_summary(employee_id=employee_id, month=month, year=year)


@mcp_server.tool(
    name="get_attendance_statistics",
    description="Lấy báo cáo tỷ lệ chuyên cần chung toàn công ty hoặc theo phòng ban.",
)
async def get_attendance_statistics(
    month: Optional[int] = None,
    year: Optional[int] = None,
    department_id: Optional[str] = None,
) -> Dict[str, Any]:
    return _tools_instance.get_attendance_statistics(month=month, year=year, department_id=department_id)


def main():
    parser = argparse.ArgumentParser(description="Chạy Attendance MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="Giao thức truyền thông (mặc định: stdio)")
    parser.add_argument("--port", type=int, default=8003, help="Cổng chạy SSE server (mặc định: 8003)")
    parser.add_argument("--host", default="0.0.0.0", help="Host bind cho SSE server")
    parser.add_argument("--real-api", action="store_true", help="Kết nối API backend thật thay vì mock data")
    args = parser.parse_args()

    if args.real_api:
        set_function_support(RealAttendanceSupport())
        logger.info("Đang sử dụng RealAttendanceSupport kết nối backend API.")
    else:
        logger.info("Đang sử dụng MockAttendanceSupport với dữ liệu giả lập.")

    if args.transport == "sse":
        logger.info("Khởi động Attendance MCP Server qua SSE tại http://%s:%d/sse", args.host, args.port)
        if hasattr(mcp_server, "run_sse_async"):
            asyncio.run(mcp_server.run_sse_async(host=args.host, port=args.port))
        else:
            mcp_server.run(transport="sse")
    else:
        logger.info("Khởi động Attendance MCP Server qua stdio...")
        if hasattr(mcp_server, "run_stdio_async"):
            asyncio.run(mcp_server.run_stdio_async())
        else:
            mcp_server.run(transport="stdio")


if __name__ == "__main__":
    main()
