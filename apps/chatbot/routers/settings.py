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
    api_key = _read_env_key("OPENAI_API_KEY") or _read_env_key("GROQ_API_KEY")
    provider = _read_env_key("LLM_PROVIDER") or ("groq" if api_key.startswith("gsk_") else "openai")
    model = _read_env_key("OPENAI_MODEL") or ("openai/gpt-oss-120b" if provider == "groq" else "gpt-4o-mini")
    base_url = _read_env_key("OPENAI_BASE_URL") or ("https://api.groq.com/openai/v1" if provider == "groq" else "https://api.openai.com/v1")

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
    provider = (payload.provider or "groq").lower().strip()
    model = (payload.model or "").strip()
    base_url = (payload.base_url or "").strip()

    # Nếu người dùng không nhập key mới và trong .env đã có key thì giữ lại key cũ
    existing_key = _read_env_key("OPENAI_API_KEY") or _read_env_key("GROQ_API_KEY")
    api_key = raw_key if raw_key else existing_key

    # Tự động nhận diện provider & model chuẩn nếu dùng Groq (gsk_...) hoặc OpenAI
    if provider == "groq" or api_key.startswith("gsk_"):
        provider = "groq"
        if not model:
            model = "openai/gpt-oss-120b"
        if not base_url:
            base_url = "https://api.groq.com/openai/v1"
    elif provider == "openai" or api_key.startswith("sk-"):
        provider = "openai"
        if not model:
            model = "gpt-4o-mini"
        if not base_url:
            base_url = "https://api.openai.com/v1"
    else:
        if not model:
            model = "openai/gpt-oss-120b"
        if not base_url:
            base_url = "https://api.groq.com/openai/v1"

    # Tạo nội dung file .env chuẩn theo cấu trúc dự án
    env_content = (
        "# =====================================================================\n"
        "# AI Agent Platform (FME) - Cấu hình Môi trường (.env)\n"
        "# Tự động sinh và cập nhật từ Chatbot UI Settings Modal\n"
        "# =====================================================================\n\n"
        "# 1. Cấu hình LLM Provider (LLMFactory)\n"
        f"LLM_PROVIDER={provider}\n"
        f"GROQ_API_KEY={api_key}\n"
        f"OPENAI_API_KEY={api_key}\n"
        f"OPENAI_BASE_URL={base_url}\n"
        f"OPENAI_MODEL={model}\n"
        "OPENAI_TIMEOUT=30\n\n"
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
        logger.info("[Settings] Successfully wrote updated .env to %s", ENV_PATH)

        # Cập nhật biến môi trường runtime
        os.environ["LLM_PROVIDER"] = provider
        os.environ["GROQ_API_KEY"] = api_key
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["OPENAI_BASE_URL"] = base_url
        os.environ["OPENAI_MODEL"] = model
        os.environ["OPENAI_TIMEOUT"] = "30"

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
