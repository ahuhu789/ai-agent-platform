import os
from typing import Optional

from .exceptions import LLMConnectionError, LLMProviderError, LLMTimeoutError
from .interface import LLM, LLMRequest, LLMResponse


from shared.logger import setup_logger

logger = setup_logger("fme.llm.openai")


class OpenAILLM(LLM):
    """
    Provider kết nối tới OpenAI hoặc bất kỳ API tương thích OpenAI nào (Groq, DeepSeek, v.v.).
    Sử dụng thư viện openai chính thức.
    """

    def __init__(self, config):
        self.config = config
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise LLMProviderError("Thư viện 'openai' chưa được cài đặt. Hãy chạy: pip install openai") from exc

        api_key = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("GROQ_API_KEY")
            or os.getenv("OPENROUTER_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
            or config.extra.get("api_key")
        )
        base_url = os.getenv("OPENAI_BASE_URL") or config.extra.get("base_url")
        timeout = float(os.getenv("OPENAI_TIMEOUT")) if os.getenv("OPENAI_TIMEOUT") else (config.timeout or 30)

        if not api_key:
            raise LLMProviderError(
                "Chưa cấu hình API Key. Vui lòng thiết lập OPENAI_API_KEY (hoặc biến môi trường tương ứng của provider) hoặc config.extra.api_key"
            )

        self.base_url = base_url
        self.provider_name = os.getenv("LLM_PROVIDER", "openai").lower()
        if "groq.com" in (base_url or "").lower() or self.provider_name == "groq":
            self.display_provider = "Groq"
        elif "openrouter.ai" in (base_url or "").lower() or self.provider_name == "openrouter":
            self.display_provider = "OpenRouter"
        elif "deepseek.com" in (base_url or "").lower() or self.provider_name == "deepseek":
            self.display_provider = "DeepSeek"
        elif "dashscope" in (base_url or "").lower() or self.provider_name in ("qwen", "dashscope"):
            self.display_provider = "Qwen"
        elif "googleapis.com" in (base_url or "").lower() or self.provider_name in ("google", "gemini"):
            self.display_provider = "Google AI Studio"
        else:
            self.display_provider = "OpenAI"

        client_kwargs = {
            "api_key": api_key,
            "timeout": timeout,
        }
        if base_url:
            client_kwargs["base_url"] = base_url

        try:
            self.client = OpenAI(**client_kwargs)
        except Exception as error:
            raise LLMConnectionError(f"Không thể khởi tạo OpenAI client: {error}") from error

    def generate(self, request: LLMRequest) -> LLMResponse:
        model = request.model or os.getenv("OPENAI_MODEL") or self.config.model or "gpt-4o-mini"
        temperature = request.temperature if request.temperature is not None else self.config.temperature

        kwargs = {
            "model": model,
            "messages": request.messages,
            "temperature": temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        url_endpoint = f"{self.base_url.rstrip('/') if self.base_url else 'https://api.openai.com/v1'}/chat/completions"
        logger.info("[LLM] generate() được gọi (provider=%s, model=%s)", self.display_provider.lower(), model)
        logger.info("[%s Provider] Đang gửi HTTP POST tới %s (model=%s)", self.display_provider, url_endpoint, model)

        try:
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            usage = None
            if response.usage:
                usage = {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            logger.info("[%s Provider] Nhận phản hồi thành công từ %s (status=200, tokens=%s)", self.display_provider, self.display_provider, usage)
            return LLMResponse(
                content=content,
                model=model,
                usage=usage,
                metadata={"provider": self.display_provider.lower(), "system_fingerprint": getattr(response, "system_fingerprint", None)},
            )
        except Exception as error:
            logger.error("[%s Provider] Lỗi HTTP khi gọi %s API: %s", self.display_provider, self.display_provider, error)
            text = str(error).lower()
            if "timeout" in text:
                raise LLMTimeoutError(f"OpenAI request timed out: {error}") from error
            if "connection" in text or "refused" in text:
                raise LLMConnectionError(f"Cannot connect to OpenAI/Groq API: {error}") from error
            raise LLMProviderError(f"OpenAI API error: {error}") from error


class OllamaLLM(LLM):
    """
    Provider kết nối tới mô hình Ollama cục bộ.
    Sử dụng lazy import để không crash khi môi trường chưa cài đặt langchain-ollama.
    """

    def __init__(self, config):
        self.config = config
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise LLMProviderError("Thư viện 'langchain-ollama' chưa được cài đặt. Hãy chạy: pip install langchain-ollama") from exc

        try:
            self.client = ChatOllama(
                model=config.model,
                base_url=config.extra.get("base_url", "http://localhost:11434"),
                temperature=config.temperature,
                timeout=config.timeout or 30,
            )
        except Exception as error:
            raise LLMConnectionError(f"Failed to initialize Ollama: {error}") from error

    def generate(self, request: LLMRequest) -> LLMResponse:
        try:
            from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
            messages = []
            for message in request.messages:
                role = message.get("role", "user")
                content = message.get("content", "")
                if role == "system":
                    messages.append(SystemMessage(content=content))
                elif role == "ai":
                    messages.append(AIMessage(content=content))
                else:
                    messages.append(HumanMessage(content=content))
        except ImportError:
            messages = request.messages

        options = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        invoke_kwargs = {"options": options} if options else {}

        try:
            response = self.client.invoke(messages, **invoke_kwargs)
        except Exception as error:
            text = str(error).lower()
            if "timeout" in text:
                raise LLMTimeoutError(f"Ollama request timed out: {error}") from error
            if "connection" in text or "refused" in text:
                raise LLMConnectionError(f"Cannot connect to Ollama server: {error}") from error
            raise LLMProviderError(f"Ollama error: {error}") from error

        return LLMResponse(
            content=response.content,
            model=request.model or self.config.model,
            metadata={"provider": "ollama"},
        )


class HuggingFaceLLM(LLM):
    """
    Provider kết nối tới HuggingFace Inference API.
    Sử dụng lazy import.
    """

    def __init__(self, config):
        try:
            from langchain_community.llms import HuggingFaceHub
        except ImportError as exc:
            raise LLMProviderError("Thư viện 'langchain-community' chưa được cài đặt. Hãy chạy: pip install langchain-community") from exc

        self.config = config
        token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
        if not token:
            raise LLMProviderError("HUGGINGFACEHUB_API_TOKEN environment variable is not set")
        try:
            self.client = HuggingFaceHub(
                repo_id=config.model,
                model_kwargs={"temperature": config.temperature},
                huggingfacehub_api_token=token,
                timeout=config.timeout or 30,
            )
        except Exception as error:
            raise LLMConnectionError(f"Failed to initialize HuggingFace: {error}") from error

    def generate(self, request: LLMRequest) -> LLMResponse:
        prompt = "".join(
            f"{message.get('role', 'user').capitalize()}: {message.get('content', '')}\n"
            for message in request.messages
        ) + "Assistant: "
        invoke_kwargs = {}
        if request.temperature is not None:
            invoke_kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            invoke_kwargs["max_new_tokens"] = request.max_tokens

        try:
            response = self.client.invoke(prompt, **invoke_kwargs)
        except Exception as error:
            if "timeout" in str(error).lower():
                raise LLMTimeoutError(f"HuggingFace request timed out: {error}") from error
            raise LLMProviderError(f"HuggingFace error: {error}") from error
        return LLMResponse(
            content=response,
            model=request.model or self.config.model,
            metadata={"provider": "huggingface"},
        )