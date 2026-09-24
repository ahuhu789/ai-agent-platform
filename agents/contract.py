"""
Agent contract definitions.
Re-exports from shared.abstractions.agent for compatibility across subsystems.
"""

try:
    from shared.abstractions.agent import AgentRequest, AgentResponse, BaseAgent
except ImportError:
    from abc import ABC, abstractmethod
    from dataclasses import dataclass, field
    from typing import Any, Optional

    @dataclass
    class AgentRequest:
        message: str
        conversation_id: Optional[str] = None
        user_id: Optional[str] = None
        context: dict = field(default_factory=dict)

    @dataclass
    class AgentResponse:
        success: bool
        data: Optional[Any] = None
        error: Optional[str] = None
        metadata: dict = field(default_factory=dict)

    class BaseAgent(ABC):
        name: str = "base"

        @abstractmethod
        def handle(self, request: AgentRequest) -> AgentResponse:
            raise NotImplementedError

__all__ = ["AgentRequest", "AgentResponse", "BaseAgent"]
