"""
Router quản lý cấu hình hệ thống và file .env (Settings API).
Cho phép đọc cấu hình hiện tại và cập nhật trực tiếp file .env từ giao diện Web.
"""
import os
from pathlib import Path
from fastapi import APIRouter, HTTPException

from apps.chatbot import schemas
from apps.chatbot.agent_setup import reload_agent_setup
from shared.logger import setup_logger

logger = setup_logger("fme.settings_router")

router = APIRouter(prefix="/settings", tags=["Settings"])

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"


PROVIDER_DEFAULTS = {
    "groq": {
        "name": "Groq Cloud",
        "default_model": "openai/gpt-oss-120b",
        "default_base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
    },
    "openrouter": {
        "name": "OpenRouter",
        "default_model": "deepseek/deepseek-chat",
        "default_base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
    },
    "google": {
        "name": "Google AI Studio",
        "default_model": "gemini-2.0-flash",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "key_env": "GEMINI_API_KEY",
    },
    "deepseek": {
        "name": "DeepSeek",
        "default_model": "deepseek-chat",
        "default_base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
    },
    "qwen": {
        "name": "Qwen API (Alibaba DashScope)",
        "default_model": "qwen-plus",
        "default_base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
        "key_env": "DASHSCOPE_API_KEY",
    },
    "openai": {
        "name": "OpenAI",
        "default_model": "gpt-4o-mini",
        "default_base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
    },
    "ollama": {
        "name": "Ollama (Local LLM)",
        "default_model": "llama3.2",
        "default_base_url": "http://localhost:11434/v1",
        "key_env": "OLLAMA_API_KEY",
    },
}


def _mask_api_key(key: str) -> str:
    """Ẩn phần lớn ký tự của API Key để bảo mật hiển thị."""
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return f"{key[:6]}...{key[-4:]}"


def _read_env_key(key_name: str) -> str:
    """Đọc giá trị từ os.environ hoặc trực tiếp từ file .env nếu có."""
    val = os.getenv(key_name)
    if val:
        return val.strip()

    if ENV_PATH.exists():
        try:
            with open(ENV_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(f"{key_name}="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return ""


@router.get(
    "",
    response_model=schemas.SettingsResponse,
    summary="Lấy cấu hình LLM hiện tại của hệ thống",
)
def get_settings():
    """Trả về trạng thái cấu hình LLM hiện tại (đã che API Key)."""
    api_key = (
        _read_env_key("OPENAI_API_KEY")
        or _read_env_key("GROQ_API_KEY")
        or _read_env_key("OPENROUTER_API_KEY")
        or _read_env_key("DEEPSEEK_API_KEY")
        or _read_env_key("DASHSCOPE_API_KEY")
        or _read_env_key("GEMINI_API_KEY")
    )
    provider = _read_env_key("LLM_PROVIDER")
    if not provider:
        if api_key.startswith("gsk_"):
            provider = "groq"
        elif api_key.startswith("sk-or-"):
            provider = "openrouter"
        elif api_key.startswith("AIzaSy"):
            provider = "google"
        else:
            provider = "openai"

    if provider == "gemini":
        provider = "google"

    info = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["openai"])
    model = _read_env_key("OPENAI_MODEL") or info["default_model"]
    base_url = _read_env_key("OPENAI_BASE_URL") or info["default_base_url"]

    return schemas.SettingsResponse(
        success=True,
        message="Lấy cấu hình thành công.",
        provider=provider,
        model=model,
        base_url=base_url,
        has_api_key=bool(api_key),
        masked_api_key=_mask_api_key(api_key),
    )


@router.post(
    "",
    response_model=schemas.SettingsResponse,
    summary="Lưu cấu hình LLM và tạo/cập nhật file .env chuẩn",
)
def save_settings(payload: schemas.SettingsUpdateRequest):
    """
    Cập nhật cấu hình LLM từ giao diện, ghi đè file .env chuẩn của dự án,
    cập nhật os.environ và reload Agent Setup trong bộ nhớ ngay lập tức.
    """
    raw_key = (payload.api_key or "").strip()
    raw_provider = (payload.provider or "").lower().strip()
    if raw_provider == "gemini":
        raw_provider = "google"

    model = (payload.model or "").strip()
    base_url = (payload.base_url or "").strip()

    # Nếu người dùng không nhập key mới và trong .env đã có key thì giữ lại key cũ
    existing_key = (
        _read_env_key("OPENAI_API_KEY")
        or _read_env_key("GROQ_API_KEY")
        or _read_env_key("OPENROUTER_API_KEY")
        or _read_env_key("DEEPSEEK_API_KEY")
        or _read_env_key("DASHSCOPE_API_KEY")
        or _read_env_key("GEMINI_API_KEY")
    )
    api_key = raw_key if raw_key else existing_key

    # Tự động nhận diện provider nếu người dùng dán key có prefix đặc trưng
    if api_key.startswith("sk-or-") and raw_provider in ("", "groq", "openai"):
        provider = "openrouter"
    elif api_key.startswith("AIza") and raw_provider in ("", "groq", "openai"):
        provider = "google"
    elif api_key.startswith("gsk_") and raw_provider in ("", "openai"):
        provider = "groq"
    elif raw_provider:
        provider = raw_provider
    else:
        provider = "groq"

    # Lấy thông tin mặc định cho provider đã chọn
    info = PROVIDER_DEFAULTS.get(provider, PROVIDER_DEFAULTS["groq"])
    if not model:
        model = info["default_model"]
    if not base_url:
        base_url = info["default_base_url"]

    # Đọc hoặc gán các provider keys tương ứng
    groq_key = api_key if provider == "groq" else _read_env_key("GROQ_API_KEY")
    openrouter_key = api_key if provider == "openrouter" else _read_env_key("OPENROUTER_API_KEY")
    deepseek_key = api_key if provider == "deepseek" else _read_env_key("DEEPSEEK_API_KEY")
    dashscope_key = api_key if provider == "qwen" else _read_env_key("DASHSCOPE_API_KEY")
    gemini_key = api_key if provider == "google" else _read_env_key("GEMINI_API_KEY")

    # Tạo nội dung file .env chuẩn theo cấu trúc dự án
    env_content = (
        "# =====================================================================\n"
        "# AI Agent Platform (FME) - Cấu hình Môi trường (.env)\n"
        "# Tự động sinh và cập nhật từ Chatbot UI Settings Modal\n"
        "# =====================================================================\n\n"
        "# 1. Cấu hình LLM Provider (LLMFactory)\n"
        f"LLM_PROVIDER={provider}\n"
        f"OPENAI_API_KEY={api_key}\n"
        f"OPENAI_BASE_URL={base_url}\n"
        f"OPENAI_MODEL={model}\n"
        "OPENAI_TIMEOUT=30\n\n"
        "# Provider-specific API Keys\n"
        f"GROQ_API_KEY={groq_key}\n"
        f"OPENROUTER_API_KEY={openrouter_key}\n"
        f"DEEPSEEK_API_KEY={deepseek_key}\n"
        f"DASHSCOPE_API_KEY={dashscope_key}\n"
        f"GEMINI_API_KEY={gemini_key}\n\n"
        "# 2. Cấu hình Memory & Cache\n"
        "MEMORY_PROVIDER=in_memory\n"
        "REDIS_URL=redis://localhost:6379/0\n\n"
        "# 3. Cấu hình MCP Servers (stdio)\n"
        "MCP_TRANSPORT=stdio\n"
        "MCP_HOST=0.0.0.0\n"
        "MCP_PORT=8001\n\n"
        "# 4. Cấu hình Chat API (FastAPI)\n"
        "APP_HOST=0.0.0.0\n"
        "APP_PORT=8000\n"
        "LOG_LEVEL=INFO\n"
    )

    try:
        # Ghi trực tiếp vào file .env tại thư mục gốc
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(env_content)
        logger.info("[Settings] Successfully wrote updated .env to %s (provider=%s, model=%s)", ENV_PATH, provider, model)

        # Cập nhật biến môi trường runtime
        os.environ["LLM_PROVIDER"] = provider
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASE_URL"] = base_url
        os.environ["OPENAI_MODEL"] = model
        os.environ["OPENAI_TIMEOUT"] = "30"

        if groq_key: os.environ["GROQ_API_KEY"] = groq_key
        if openrouter_key: os.environ["OPENROUTER_API_KEY"] = openrouter_key
        if deepseek_key: os.environ["DEEPSEEK_API_KEY"] = deepseek_key
        if dashscope_key: os.environ["DASHSCOPE_API_KEY"] = dashscope_key
        if gemini_key: os.environ["GEMINI_API_KEY"] = gemini_key

        # Tải lại RootAgent & DomainAgents trong bộ nhớ
        reload_agent_setup()

        return schemas.SettingsResponse(
            success=True,
            message="Đã lưu cấu hình và tạo file .env chuẩn thành công!",
            provider=provider,
            model=model,
            base_url=base_url,
            has_api_key=bool(api_key),
            masked_api_key=_mask_api_key(api_key),
        )

    except Exception as exc:
        logger.error("[Settings] Lỗi khi ghi file .env: %s", exc)
        raise HTTPException(status_code=500, detail=f"Không thể ghi file .env: {str(exc)}")
