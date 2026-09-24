import os
from typing import Optional

from .exceptions import LLMConnectionError, LLMProviderError, LLMTimeoutError
from .interface import LLM, LLMRequest, LLMResponse


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

        api_key = config.extra.get("api_key") or os.getenv("OPENAI_API_KEY")
        base_url = config.extra.get("base_url") or os.getenv("OPENAI_BASE_URL")
        timeout = config.timeout or float(os.getenv("OPENAI_TIMEOUT", 30))

        if not api_key:
            raise LLMProviderError(
                "Chưa cấu hình API Key cho OpenAI/Groq. Vui lòng thiết lập biến môi trường OPENAI_API_KEY hoặc config.extra.api_key"
            )

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
        model = request.model or self.config.model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        temperature = request.temperature if request.temperature is not None else self.config.temperature

        kwargs = {
            "model": model,
            "messages": request.messages,
            "temperature": temperature,
        }
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

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
            return LLMResponse(
                content=content,
                model=model,
                usage=usage,
                metadata={"provider": "openai", "system_fingerprint": getattr(response, "system_fingerprint", None)},
            )
        except Exception as error:
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
        except ImportError as exc:
            raise LLMProviderError("Cần thư viện 'langchain-core'. Hãy chạy: pip install langchain-core") from exc

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