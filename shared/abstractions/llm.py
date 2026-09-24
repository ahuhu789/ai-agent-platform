import asyncio
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class LLMRequest:
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    extra_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str
    model: Optional[str] = None
    raw_response: Optional[Any] = None
    usage: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


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

    async def generate_async(self, request: LLMRequest) -> LLMResponse:
        """Sinh phản hồi bất đồng bộ từ LLM provider (mặc định ủy thác sang generate)."""
        return await asyncio.to_thread(self.generate, request)


# Alias tương thích ngược cho các module dùng LLM thay vì BaseLLM
LLM = BaseLLM
