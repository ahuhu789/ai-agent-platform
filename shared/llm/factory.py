from .exceptions import UnsupportedProviderError
from .interface import LLM
from .mock import MockLLM
from .providers import OpenAILLM, OllamaLLM, HuggingFaceLLM


class LLMFactory:
    @staticmethod
    def create(config) -> LLM:
        provider_name = config.active_provider.lower().strip()
        provider_config = config.providers.get(provider_name)
        if not provider_config:
            raise UnsupportedProviderError(f"Unsupported provider: {provider_name}")

        if provider_name == "mock":
            response = provider_config.extra.get("response", "Mock response from factory.")
            return MockLLM(response_content=response)
        if provider_name in {"openai", "groq"}:
            return OpenAILLM(provider_config)
        if provider_name == "ollama":
            return OllamaLLM(provider_config)
        if provider_name == "huggingface":
            return HuggingFaceLLM(provider_config)
        raise UnsupportedProviderError(f"Unsupported provider: {provider_name}")