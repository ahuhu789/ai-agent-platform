"""Memory lưu trong RAM - dùng cho giai đoạn đầu và test."""
from __future__ import annotations

import copy
import logging
import threading
from typing import Optional

from shared.abstractions.memory import (
    DEFAULT_HISTORY_LIMIT,
    MemoryStore,
    Message,
    Conversation,
    clamp_history_limit,
)

logger = logging.getLogger(__name__)


class InMemoryStore(MemoryStore):
    def __init__(self) -> None:
        self._conversations: dict[str, Conversation] = {}
        self._user_context: dict[str, dict] = {}
        self._agent_context: dict[tuple[str, str], dict] = {}
        self._lock = threading.RLock()

    # ---- helpers -------------------------------------------------------
    def _owned(self, conversation_id: str, user_id: Optional[str]) -> Optional[Conversation]:
        """Conversation gốc (không copy) nếu tồn tại và đúng chủ. Gọi khi đã giữ lock."""
        conversation = self._conversations.get(conversation_id)
        if conversation is None:
            return None
        if user_id is not None and conversation.user_id != user_id:
            logger.warning("user %s truy cập conversation %s không thuộc về mình", user_id, conversation_id)
            return None
        return conversation

    # ---- Conversation --------------------------------------------------
    def create_conversation(self, user_id: str) -> Conversation:
        with self._lock:
            conversation = Conversation(user_id=user_id)
            self._conversations[conversation.conversation_id] = conversation
            logger.debug("created conversation %s for user %s", conversation.conversation_id, user_id)
            return copy.deepcopy(conversation)

    def get_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> Optional[Conversation]:
        with self._lock:
            conversation = self._owned(conversation_id, user_id)
            return copy.deepcopy(conversation) if conversation else None

    def list_conversations(self, user_id: str) -> list[Conversation]:
        with self._lock:
            mine = [s for s in self._conversations.values() if s.user_id == user_id]
            mine.sort(key=lambda s: s.updated_at, reverse=True)
            return [
                Conversation(
                    user_id=s.user_id,
                    conversation_id=s.conversation_id,
                    messages=[],
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
                for s in mine
            ]

    def delete_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> bool:
        with self._lock:
            if self._owned(conversation_id, user_id) is None:
                return False
            del self._conversations[conversation_id]
            logger.debug("deleted conversation %s", conversation_id)
            return True

    # ---- Message -------------------------------------------------------
    def append_message(self, conversation_id: str, message: Message, user_id: Optional[str] = None) -> None:
        with self._lock:
            conversation = self._owned(conversation_id, user_id)
            if conversation is None:
                raise KeyError(conversation_id)
            conversation.add_message(copy.deepcopy(message))

    def get_history(
        self, conversation_id: str, limit: int = DEFAULT_HISTORY_LIMIT, user_id: Optional[str] = None
    ) -> list[Message]:
        limit = clamp_history_limit(limit)
        with self._lock:
            conversation = self._owned(conversation_id, user_id)
            return copy.deepcopy(conversation.messages[-limit:]) if conversation else []

    def get_messages(self, conversation_id: str, user_id: Optional[str] = None) -> list[Message]:
        with self._lock:
            conversation = self._owned(conversation_id, user_id)
            return copy.deepcopy(conversation.messages) if conversation else []

    # ---- Context -------------------------------------------------------
    def get_user_context(self, user_id: str) -> dict:
        with self._lock:
            return copy.deepcopy(self._user_context.get(user_id, {}))

    def update_user_context(self, user_id: str, data: dict) -> None:
        with self._lock:
            self._user_context.setdefault(user_id, {}).update(copy.deepcopy(data))

    def get_agent_context(self, user_id: str, agent_name: str) -> dict:
        with self._lock:
            return copy.deepcopy(self._agent_context.get((user_id, agent_name), {}))

    def update_agent_context(self, user_id: str, agent_name: str, data: dict) -> None:
        with self._lock:
            self._agent_context.setdefault((user_id, agent_name), {}).update(copy.deepcopy(data))
