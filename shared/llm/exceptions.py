class LLMError(Exception):
    """Base exception cho tất cả lỗi liên quan đến LLM."""


class LLMProviderError(LLMError):
    """Lỗi phát sinh từ provider hoặc SDK của provider."""


class LLMConnectionError(LLMError):
    """Không thể kết nối tới provider."""


class LLMTimeoutError(LLMError):
    """Provider không phản hồi trong thời gian cho phép."""


class UnsupportedProviderError(LLMError):
    """Provider chưa được factory hỗ trợ."""


class LLMConfigError(LLMError):
    """Lỗi cấu hình (ví dụ: thiếu trường bắt buộc)."""
