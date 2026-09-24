# llm_factory/test_llm.py

import pytest
import shutil
from pathlib import Path
from .config import load_config
from .factory import LLMFactory
from .interface import LLMRequest
from .exceptions import LLMConnectionError, LLMTimeoutError, UnsupportedProviderError, LLMConfigError
from .providers import OllamaLLM

CONFIG_PATH = Path(__file__).with_name("config.yaml")

# Test với Mock LLM (không cần kết nối)
def test_mock_llm():
    config = load_config(str(CONFIG_PATH))
    config.active_provider = "mock"  # override
    factory = LLMFactory()
    llm = factory.create(config)

    request = LLMRequest(
        messages=[{"role": "user", "content": "Hello"}],
        model="mock-model"
    )
    response = llm.generate(request)
    assert response.content == "Mock response from factory."
    assert response.model == "mock-model"
    assert response.usage is not None

# Test với Ollama (yêu cầu Ollama đang chạy và có model)
@pytest.mark.skipif(shutil.which("ollama") is None, reason="Ollama not installed")
def test_ollama_llm():
    config = load_config(str(CONFIG_PATH))
    config.active_provider = "ollama"
    factory = LLMFactory()
    llm = factory.create(config)

    request = LLMRequest(
        messages=[{"role": "user", "content": "Nói một câu chào"}],
        model=config.providers["ollama"].model
    )
    response = llm.generate(request)
    assert response.content is not None
    assert len(response.content) > 0

# Test lỗi khi provider không tồn tại
def test_unsupported_provider():
    config = load_config(str(CONFIG_PATH))
    config.active_provider = "unknown"
    factory = LLMFactory()
    with pytest.raises(UnsupportedProviderError, match="Unsupported provider: unknown"):
        factory.create(config)


def test_ollama_request_overrides(monkeypatch):
    class FakeResponse:
        content = "ok"

    class FakeClient:
        def __init__(self):
            self.calls = []

        def invoke(self, messages, **kwargs):
            self.calls.append((messages, kwargs))
            return FakeResponse()

    config = load_config(str(CONFIG_PATH)).providers["ollama"]
    llm = OllamaLLM.__new__(OllamaLLM)
    llm.config = config
    llm.client = FakeClient()

    response = llm.generate(
        LLMRequest(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.2,
            max_tokens=64,
        )
    )

    assert response.content == "ok"
    assert llm.client.calls[0][1] == {
        "options": {"temperature": 0.2, "num_predict": 64}
    }

# Test lỗi cấu hình
def test_config_error(tmp_path):
    # Tạo file config sai
    bad_config = tmp_path / "bad_config.yaml"
    bad_config.write_text("active_provider: ollama\n")  # thiếu providers
    with pytest.raises(LLMConfigError):
        load_config(str(bad_config))
