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
from shared.logger import setup_logger

logger = setup_logger("fme.agent_setup")


def setup_mcp_client() -> MultiServerMCPClient:
    """Khởi tạo MCP Client cho 3 MCP Server phân hệ."""
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
    return MultiServerMCPClient(configs)


def setup_llm() -> Optional[BaseLLM]:
    """Khởi tạo LLM Provider thông qua LLMFactory.
    Hỗ trợ Groq, OpenRouter, Google AI Studio, DeepSeek, Qwen, OpenAI hoặc Mock LLM.
    Khi chưa cấu hình API key, trả về None để các Agent chạy ở chế độ Rule-based
    và Template Formatter với đầy đủ dữ liệu thực tế thay vì trả về Mock response.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)
    except ImportError:
        pass

    config_path = Path(__file__).resolve().parent.parent.parent / "shared" / "llm" / "config.yaml"
    try:
        config = load_config(str(config_path))
        env_provider = os.getenv("LLM_PROVIDER")
        api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )

        if env_provider and env_provider.lower().strip() != "mock":
            p = env_provider.lower().strip()
            config.active_provider = "google" if p == "gemini" else p
        elif api_key:
            # Tự động nhận diện provider theo tiền tố API key
            if api_key.startswith("gsk_"):
                config.active_provider = "groq"
            elif api_key.startswith("sk-or-"):
                config.active_provider = "openrouter"
            elif api_key.startswith("AIzaSy"):
                config.active_provider = "google"
            else:
                config.active_provider = "openai"
        elif env_provider and env_provider.lower().strip() == "mock":
            config.active_provider = "mock"
        else:
            logger.info("[AgentSetup] No API key set. Running in offline Rule-based & Template mode.")
            return None

        # Đảm bảo nếu provider chưa có trong config.providers thì tự động cấu hình theo OpenAILLM
        if config.active_provider not in config.providers:
            from shared.llm.config import ProviderConfig
            base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            config.providers[config.active_provider] = ProviderConfig(
                model=model,
                temperature=0.7,
                timeout=30,
                extra={"base_url": base_url},
            )

        llm_instance = LLMFactory.create(config)
        active_p_config = config.providers.get(config.active_provider)
        active_model = os.getenv("OPENAI_MODEL", getattr(active_p_config, "model", "default"))
        logger.info("[AgentSetup] LLM Provider active: %s (model=%s)", config.active_provider, active_model)
        return llm_instance
    except Exception as e:
        logger.warning("[AgentSetup] Could not create LLM from config (%s). Falling back to rule-based.", e)
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


def reload_agent_setup():
    """Tải lại LLM Provider và tái khởi tạo RootAgent/DomainAgents khi cấu hình .env thay đổi."""
    global llm_provider, root_agent
    llm_provider = setup_llm()
    root_agent = build_root_agent(llm=llm_provider)
    try:
        from apps.chatbot.services.chat_service import chat_service
        chat_service.root_agent = root_agent
        logger.info("[AgentSetup] Successfully reloaded ChatService root_agent.")
    except Exception as exc:
        logger.warning("[AgentSetup] Could not update chat_service.root_agent (%s)", exc)
    return root_agent
