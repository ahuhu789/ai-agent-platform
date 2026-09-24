"""
Unit tests cho Settings API (/settings) và tính năng tạo/cập nhật file .env từ giao diện.
"""
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from apps.chatbot.main import app

ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT_DIR / ".env"


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def preserve_env_file():
    """Lưu lại nội dung .env trước test và khôi phục lại sau khi test kết thúc."""
    original_content = None
    if ENV_PATH.exists():
        original_content = ENV_PATH.read_text(encoding="utf-8")

    yield

    if original_content is not None:
        ENV_PATH.write_text(original_content, encoding="utf-8")


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
