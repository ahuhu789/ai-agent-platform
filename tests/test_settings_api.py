"""
Unit tests cho Settings API (/settings) và tính năng tạo/cập nhật file .env từ giao diện.
"""
from pathlib import Path
import os
import pytest
from fastapi.testclient import TestClient

from apps.chatbot import agent_setup
from apps.chatbot.main import app
from apps.chatbot.services.chat_service import chat_service

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
def preserve_env_file():
    """Lưu lại nội dung .env trước test và khôi phục lại sau khi test kết thúc."""
    original_environment = dict(os.environ)
    env_existed = ENV_PATH.exists()
    original_content = ENV_PATH.read_text(encoding="utf-8") if env_existed else None
    original_llm_provider = agent_setup.llm_provider
    original_root_agent = agent_setup.root_agent
    original_chat_root_agent = chat_service.root_agent

    yield

    os.environ.clear()
    os.environ.update(original_environment)
    if env_existed:
        ENV_PATH.write_text(original_content, encoding="utf-8")
    else:
        ENV_PATH.unlink(missing_ok=True)
    agent_setup.llm_provider = original_llm_provider
    agent_setup.root_agent = original_root_agent
    chat_service.root_agent = original_chat_root_agent


def test_get_settings(client):
    """Kiểm tra endpoint GET /settings trả về thông tin cấu hình hợp lệ."""
    response = client.get("/settings")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "provider" in data
    assert "model" in data
    assert "has_api_key" in data


def test_save_settings_creates_standard_groq_env(client):
    """
    Kiểm tra endpoint POST /settings khi người dùng lưu cấu hình Groq API key:
    - Tạo file .env chuẩn với GROQ_API_KEY và OPENAI_MODEL=openai/gpt-oss-120b
    - Cập nhật os.environ
    - Trả về phản hồi thành công
    """
    test_key = "gsk_test_groq_api_key_sample_12345678"
    payload = {
        "provider": "groq",
        "api_key": test_key,
        "model": "openai/gpt-oss-120b",
    }
    response = client.post("/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "groq"
    assert data["model"] == "openai/gpt-oss-120b"
    assert data["base_url"] == "https://api.groq.com/openai/v1"
    assert data["has_api_key"] is True
    assert "gsk_" in data["masked_api_key"]

    # Kiểm tra file .env được tạo thực tế trên đĩa
    assert ENV_PATH.exists()
    env_content = ENV_PATH.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=groq" in env_content
    assert f"GROQ_API_KEY={test_key}" in env_content
    assert f"OPENAI_API_KEY={test_key}" in env_content
    assert "OPENAI_BASE_URL=https://api.groq.com/openai/v1" in env_content
    assert "OPENAI_MODEL=openai/gpt-oss-120b" in env_content
    assert "MEMORY_PROVIDER=in_memory" in env_content
    assert "MCP_TRANSPORT=stdio" in env_content
    assert "MCP_CONNECT_TIMEOUT_SECONDS=10" in env_content
    assert "MCP_OPERATION_TIMEOUT_SECONDS=30" in env_content
    assert "MCP_DISCOVERY_TTL_SECONDS=60" in env_content


def test_save_settings_auto_detect_groq_prefix(client):
    """Kiểm tra tự động nhận diện Groq khi API key có tiền tố gsk_."""
    test_key = "gsk_another_groq_key_998877"
    payload = {
        "provider": "",  # Để trống provider
        "api_key": test_key,
        "model": "",     # Để trống model
    }
    response = client.post("/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "groq"
    assert data["model"] == "openai/gpt-oss-120b"
    assert data["base_url"] == "https://api.groq.com/openai/v1"

    env_content = ENV_PATH.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=groq" in env_content
    assert "OPENAI_MODEL=openai/gpt-oss-120b" in env_content


def test_save_settings_openrouter(client):
    """Kiểm tra cấu hình OpenRouter."""
    test_key = "sk-or-v1-abcdef1234567890"
    payload = {
        "provider": "openrouter",
        "api_key": test_key,
        "model": "deepseek/deepseek-chat",
    }
    response = client.post("/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "openrouter"
    assert data["model"] == "deepseek/deepseek-chat"
    assert data["base_url"] == "https://openrouter.ai/api/v1"

    env_content = ENV_PATH.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=openrouter" in env_content
    assert f"OPENROUTER_API_KEY={test_key}" in env_content
    assert f"OPENAI_API_KEY={test_key}" in env_content
    assert "OPENAI_BASE_URL=https://openrouter.ai/api/v1" in env_content
    assert "OPENAI_MODEL=deepseek/deepseek-chat" in env_content


def test_save_settings_google_ai_studio(client):
    """Kiểm tra cấu hình Google AI Studio (Gemini)."""
    test_key = "AIzaSyTestGoogleKey123456789"
    payload = {
        "provider": "google",
        "api_key": test_key,
        "model": "gemini-2.0-flash",
    }
    response = client.post("/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "google"
    assert data["model"] == "gemini-2.0-flash"
    assert "generativelanguage.googleapis.com" in data["base_url"]

    env_content = ENV_PATH.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=google" in env_content
    assert f"GEMINI_API_KEY={test_key}" in env_content
    assert "OPENAI_MODEL=gemini-2.0-flash" in env_content


def test_save_settings_deepseek(client):
    """Kiểm tra cấu hình DeepSeek API."""
    test_key = "sk-deepseek-test-999888777"
    payload = {
        "provider": "deepseek",
        "api_key": test_key,
        "model": "deepseek-chat",
    }
    response = client.post("/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "deepseek"
    assert data["model"] == "deepseek-chat"
    assert data["base_url"] == "https://api.deepseek.com"

    env_content = ENV_PATH.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=deepseek" in env_content
    assert f"DEEPSEEK_API_KEY={test_key}" in env_content
    assert "OPENAI_BASE_URL=https://api.deepseek.com" in env_content


def test_save_settings_qwen(client):
    """Kiểm tra cấu hình Qwen API (DashScope)."""
    test_key = "sk-dashscope-test-888777666"
    payload = {
        "provider": "qwen",
        "api_key": test_key,
        "model": "qwen-plus",
    }
    response = client.post("/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "qwen"
    assert data["model"] == "qwen-plus"
    assert "dashscope" in data["base_url"]

    env_content = ENV_PATH.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=qwen" in env_content
    assert f"DASHSCOPE_API_KEY={test_key}" in env_content
    assert "OPENAI_MODEL=qwen-plus" in env_content


def test_save_settings_auto_detect_openrouter_prefix(client):
    """Kiểm tra tự động nhận diện OpenRouter khi API key có tiền tố sk-or-."""
    test_key = "sk-or-v1-auto-detected-key"
    payload = {
        "provider": "",
        "api_key": test_key,
        "model": "",
    }
    response = client.post("/settings", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["provider"] == "openrouter"
    assert data["model"] == "deepseek/deepseek-chat"
