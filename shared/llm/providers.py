import os

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from .exceptions import LLMConnectionError, LLMProviderError, LLMTimeoutError
from .interface import LLM, LLMRequest, LLMResponse


class OllamaLLM(LLM):
    def __init__(self, config):
        self.config = config
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
    def __init__(self, config):
        from langchain_community.llms import HuggingFaceHub

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