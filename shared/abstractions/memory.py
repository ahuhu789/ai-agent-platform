"""Abstraction cho hệ thống Memory của Chatbot.

Chat Service và các Agent chỉ được phụ thuộc vào file này, không import trực
tiếp Redis hay database. Muốn đổi nơi lưu trữ chỉ cần thay implementation.

Hai mức memory:
  * user context : dùng chung khi người dùng chuyển qua nhiều Agent.
  * agent context: chỉ lưu ngữ cảnh của một Agent (phân hệ) cho một user.

Tham số ``user_id`` ở các hàm thao tác conversation là TÙY CHỌN.
Khi truyền vào, store sẽ kiểm tra conversation có thuộc user đó không.
Chat Service nên luôn truyền ``user_id``.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

DEFAULT_HISTORY_LIMIT = 10
MAX_HISTORY_LIMIT = 100  # trần số message đưa vào LLM


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def clamp_history_limit(limit: int) -> int:
    """Chuẩn hóa ``limit``: phải >= 1 và không vượt MAX_HISTORY_LIMIT."""
    if limit is None or limit < 1:
        raise ValueError("limit phải >= 1 (dùng get_messages() để lấy toàn bộ)")
    return min(limit, MAX_HISTORY_LIMIT)


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    agent_name: Optional[str] = None
    created_at: str = field(default_factory=_now)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            role=data["role"],
            content=data["content"],
            agent_name=data.get("agent_name"),
            created_at=data.get("created_at") or _now(),
            metadata=data.get("metadata") or {},
        )


@dataclass
class Conversation:
    """Một cuộc hội thoại của user. ``conversation_id`` dùng chung với API /conversations/{id}."""

    user_id: str
    conversation_id: str = field(default_factory=_new_id)
    messages: list[Message] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)
        self.updated_at = _now()


class MemoryStore(ABC):
    """Interface chung cho mọi nơi lưu memory (in-memory, Redis, DB...)."""

    # ---- Conversation --------------------------------------------------
    @abstractmethod
    def create_conversation(self, user_id: str) -> Conversation:
        """Tạo conversation mới cho user."""

    @abstractmethod
    def get_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> Optional[Conversation]:
        """Trả về conversation kèm messages, hoặc None nếu không có / không thuộc user."""

    @abstractmethod
    def list_conversations(self, user_id: str) -> list[Conversation]:
        """Danh sách conversation của user, mới cập nhật nhất trước. KHÔNG kèm messages."""

    @abstractmethod
    def delete_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> bool:
        """Xóa conversation. Trả True nếu đã xóa, False nếu không tồn tại / sai chủ."""

    # ---- Message -------------------------------------------------------
    @abstractmethod
    def append_message(self, conversation_id: str, message: Message, user_id: Optional[str] = None) -> None:
        """Thêm message. Raise KeyError nếu conversation không tồn tại / sai chủ."""

    @abstractmethod
    def get_history(
        self, conversation_id: str, limit: int = DEFAULT_HISTORY_LIMIT, user_id: Optional[str] = None
    ) -> list[Message]:
        """``limit`` message gần nhất (dùng để đưa vào LLM). Tối đa MAX_HISTORY_LIMIT."""

    @abstractmethod
    def get_messages(self, conversation_id: str, user_id: Optional[str] = None) -> list[Message]:
        """Toàn bộ message của conversation (dùng cho API xem history, không đưa vào LLM)."""

    # ---- Context -------------------------------------------------------
    @abstractmethod
    def get_user_context(self, user_id: str) -> dict:
        """Context dùng chung theo user."""

    @abstractmethod
    def update_user_context(self, user_id: str, data: dict) -> None:
        """Gộp ``data`` vào context chung của user."""

    @abstractmethod
    def get_agent_context(self, user_id: str, agent_name: str) -> dict:
        """Context riêng của một Agent cho user."""

    @abstractmethod
    def update_agent_context(self, user_id: str, agent_name: str, data: dict) -> None:
        """Gộp ``data`` vào context riêng của Agent."""


# Alias for backward compatibility
BaseMemoryStore = MemoryStore
