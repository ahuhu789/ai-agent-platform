"""Hiring MCP Server implementation supporting stdio and HTTP transports."""

import argparse
import asyncio
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger("mcp.hiring")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)

# Ensure project root is in sys.path so direct execution (e.g. `python mcp_servers/hiring/server.py`) works
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
    from .function_support import HiringFunctionSupport, MockHiringSupport, RealHiringSupport
    from .tools import HiringTools
except (ImportError, ValueError):
    from mcp_servers.hiring.function_support import HiringFunctionSupport, MockHiringSupport, RealHiringSupport
    from mcp_servers.hiring.tools import HiringTools

# Create MCPServer instance
mcp_server = MCPServer(
    name="Hiring MCP Server",
    instructions="MCP Server cung cấp các Tool truy vấn dữ liệu Tuyển dụng (Hiring) cho AI Chatbot FME.",
)

# Initialize function support: use Real API if HIRING_API_BASE_URL is configured, otherwise fallback to Mock
_api_base_url = os.getenv("HIRING_API_BASE_URL")
if _api_base_url:
    _support = RealHiringSupport(api_base_url=_api_base_url, api_key=os.getenv("HIRING_API_KEY"))
else:
    _support = MockHiringSupport()

_tools_instance = HiringTools(_support)


def set_function_support(support: HiringFunctionSupport):
    """Allow dependency injection of function support."""
    global _tools_instance
    _tools_instance = HiringTools(support)


def get_tools_instance() -> HiringTools:
    """Get the active HiringTools instance."""
    return _tools_instance


@mcp_server.tool(
    name="search_candidates",
    description="Tìm kiếm ứng viên theo từ khóa (tên, email, kỹ năng), trạng thái (applied, pending_interview, interviewing, offered, rejected) hoặc mã vị trí tuyển dụng.",
)
def search_candidates(
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    job_id: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    return _tools_instance.search_candidates(keyword=keyword, status=status, job_id=job_id, limit=limit)


@mcp_server.tool(
    name="get_candidate_detail",
    description="Lấy thông tin chi tiết hồ sơ ứng viên bằng mã ứng viên (candidate_id, ví dụ: UV001).",
)
def get_candidate_detail(candidate_id: str) -> Dict[str, Any]:
    return _tools_instance.get_candidate_detail(candidate_id=candidate_id)


@mcp_server.tool(
    name="list_job_openings",
    description="Lấy danh sách các vị trí tuyển dụng (job openings) đang mở hoặc theo phòng ban.",
)
def list_job_openings(
    status: Optional[str] = "open",
    department: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    return _tools_instance.list_job_openings(status=status, department=department, limit=limit)


@mcp_server.tool(
    name="get_interview_schedule",
    description="Tra cứu lịch phỏng vấn theo mã ứng viên hoặc khoảng ngày (từ ngày from_date đến ngày to_date theo định dạng YYYY-MM-DD).",
)
def get_interview_schedule(
    candidate_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    return _tools_instance.get_interview_schedule(candidate_id=candidate_id, from_date=from_date, to_date=to_date)


@mcp_server.tool(
    name="get_recruitment_summary",
    description="Tổng hợp số liệu thống kê tình hình tuyển dụng (số lượng vị trí đang tuyển, số lượng ứng viên theo trạng thái, phòng ban).",
)
def get_recruitment_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
) -> Dict[str, Any]:
    return _tools_instance.get_recruitment_summary(from_date=from_date, to_date=to_date)


def main():
    parser = argparse.ArgumentParser(description="Hiring MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport protocol to use (stdio, sse, or streamable-http)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="Host for HTTP transports",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_PORT", "8001")),
        help="Port for HTTP transports",
    )

    args = parser.parse_args()

    try:
        if args.transport == "sse":
            logger.info(f"Starting Hiring MCP Server with SSE on {args.host}:{args.port}...")
            if hasattr(mcp_server, "run_sse_async"):
                asyncio.run(mcp_server.run_sse_async(host=args.host, port=args.port))
            else:
                mcp_server.run(transport="sse")
        elif args.transport == "streamable-http":
            logger.info(
                f"Starting Hiring MCP Server with Streamable HTTP on {args.host}:{args.port}/mcp..."
            )
            if hasattr(mcp_server, "run_streamable_http_async"):
                asyncio.run(
                    mcp_server.run_streamable_http_async(
                        host=args.host,
                        port=args.port,
                    )
                )
            else:
                mcp_server.run(transport="streamable-http")
        else:
            logger.info("Starting Hiring MCP Server with stdio...")
            if hasattr(mcp_server, "run_stdio_async"):
                asyncio.run(mcp_server.run_stdio_async())
            else:
                mcp_server.run(transport="stdio")
    except (KeyboardInterrupt, SystemExit):
        logger.info("Hiring MCP Server stopped gracefully.")


if __name__ == "__main__":
    main()
