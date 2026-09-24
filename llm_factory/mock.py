from .exceptions import LLMProviderError
from .interface import LLM, LLMRequest, LLMResponse


class MockLLM(LLM):
    """LLM giả lập, dùng để test không cần kết nối thật."""

    def __init__(self, response_content="This is a mock response.", raise_error=None):
        """Cấu hình nội dung trả về hoặc lỗi cần giả lập."""
        self.response_content = response_content
        self.raise_error = raise_error

    def generate(self, request: LLMRequest) -> LLMResponse:
        if self.raise_error:
            if isinstance(self.raise_error, Exception):
                raise self.raise_error
            raise LLMProviderError(self.raise_error)
        return LLMResponse(
            content=self.response_content,
            model=request.model or "mock-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            metadata={"mock": True},
        )
