from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LLMRequest:
    messages: List[Dict[str, str]]
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None


@dataclass
class LLMResponse:
    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


class LLM(ABC):
    """Interface chung cho mọi LLM provider."""

    @abstractmethod
    def generate(self, request: LLMRequest) -> LLMResponse:
        """Thực hiện generate và trả về response chuẩn hóa."""
        raise NotImplementedError