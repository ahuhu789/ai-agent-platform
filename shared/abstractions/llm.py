from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class LLMRequest:
    messages: List[Dict[str, str]]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str
    raw_response: Optional[Any] = None
    usage: Dict[str, Any] = field(default_factory=dict)


class BaseLLM(ABC):
    """
    Interface trừu tượng cho các nhà cung cấp LLM (LLM Provider).
    Phụ trách bởi: Hoàng Minh Anh (LLM-01 -> LLM-04).
    Tham chiếu: docs/AI_Plan.pdf (Mục 3.1 - Thành viên 3)
    """

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Sinh phản hồi đồng bộ từ LLM provider."""
        raise NotImplementedError

    @abstractmethod
    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        """Sinh phản hồi bất đồng bộ từ LLM provider."""
        raise NotImplementedError
