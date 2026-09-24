"""
Khởi tạo AgentRegistry + RootAgent dùng chung cho toàn Chat API.
Inject MultiServerMCPClient kết nối tới cả 3 MCP Server phân hệ.
Inject BaseLLM được tạo từ LLMFactory (hỗ trợ OpenAI thật hoặc Mock LLM).
"""
import os
import sys
from pathlib import Path
from typing import Optional

from agents.root.agent_registry import AgentRegistry
from agents.root.root_agent import RootAgent
from agents.hiring.hiring_agent import HiringAgent
from agents.attendance.attendance_agent import AttendanceAgent
from agents.employee.employee_agent import EmployeeAgent
from shared.abstractions.llm import BaseLLM
from shared.clients.mcp_client import MultiServerMCPClient
from shared.llm.config import load_config
from shared.llm.factory import LLMFactory


def setup_mcp_client() -> MultiServerMCPClient:
    """Khởi tạo và kết nối MCP Client tới 3 MCP Server phân hệ."""
    python_exe = sys.executable
    configs = {
        "hiring": {
            "command": python_exe,
            "args": ["-m", "mcp_servers.hiring.server", "--transport", "stdio"],
        },
        "attendance": {
            "command": python_exe,
            "args": ["-m", "mcp_servers.attendance.server", "--transport", "stdio"],
        },
        "employee": {
            "command": python_exe,
            "args": ["-m", "mcp_servers.employee.server", "--transport", "stdio"],
        },
    }
    client = MultiServerMCPClient(configs)
    try:
        client.connect_all()
    except Exception as e:
        print(f"[AgentSetup] Cảnh báo: Không thể kết nối MCP Server ngay lúc khởi động ({e})")
    return client


def setup_llm() -> Optional[BaseLLM]:
    """Khởi tạo LLM Provider thông qua LLMFactory."""
    config_path = Path(__file__).resolve().parent.parent.parent / "shared" / "llm" / "config.yaml"
    try:
        config = load_config(str(config_path))
        # Cho phép chỉ định provider qua biến môi trường LLM_PROVIDER
        # Nếu có OPENAI_API_KEY và không chỉ định provider khác, kích hoạt provider openai
        env_provider = os.getenv("LLM_PROVIDER")
        if env_provider:
            config.active_provider = env_provider.lower().strip()
        elif os.getenv("OPENAI_API_KEY"):
            config.active_provider = "openai"

        llm_instance = LLMFactory.create(config)
        print(f"[AgentSetup] LLM Provider đã kích hoạt: {config.active_provider}")
        return llm_instance
    except Exception as e:
        print(f"[AgentSetup] Cảnh báo: Không thể tạo LLM từ config ({e}). Các Agent sẽ chạy fallback rule-based.")
        return None


# Instances dùng chung
mcp_client = setup_mcp_client()
llm_provider = setup_llm()


def build_root_agent(
    client: Optional[MultiServerMCPClient] = None,
    llm: Optional[BaseLLM] = None,
) -> RootAgent:
    registry = AgentRegistry()

    active_client = client if client is not None else mcp_client
    active_llm = llm if llm is not None else llm_provider

    # Đăng ký cả 3 Domain Agent thật vào AgentRegistry với MCP Client và LLM được inject qua DI
    registry.register(HiringAgent(mcp_client=active_client, llm=active_llm))
    registry.register(AttendanceAgent(mcp_client=active_client, llm=active_llm))
    registry.register(EmployeeAgent(mcp_client=active_client, llm=active_llm))

    return RootAgent(registry)


# Singleton dùng chung cho toàn bộ Chat API
root_agent = build_root_agent()
