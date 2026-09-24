"""
Adapter kết nối Chat API với module Memory chính thức (shared.memory.factory).
Cung cấp các phương thức cần thiết cho /chat và /conversations,
đồng thời ủy quyền lưu trữ cho MemoryStore (InMemoryStore hoặc RedisMemoryStore).
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.abstractions.memory import Message
from shared.memory.factory import create_memory_store


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatbotMemoryAdapter:
    def __init__(self, provider: Optional[str] = None):
        self._store = create_memory_store(provider)
        self._titles: Dict[str, str] = {}  # conversation_id -> title

    def create_conversation(self, title: Optional[str] = None, user_id: str = "default_user") -> str:
        conv = self._store.create_conversation(user_id=user_id)
        conv_id = conv.conversation_id
        self._titles[conv_id] = title or "Cuộc trò chuyện mới"
        return conv_id

    def get_conversation_meta(self, conversation_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        conv = self._store.get_conversation(conversation_id, user_id=user_id)
        if not conv:
            return None
        return {
            "id": conv.conversation_id,
            "title": self._titles.get(conv.conversation_id, "Cuộc trò chuyện mới"),
            "created_at": conv.created_at,
            "updated_at": conv.updated_at,
        }

    def list_conversations(self, user_id: str = "default_user") -> List[Dict[str, Any]]:
        conversations = self._store.list_conversations(user_id=user_id)
        result = []
        for c in conversations:
            result.append({
                "id": c.conversation_id,
                "title": self._titles.get(c.conversation_id, "Cuộc trò chuyện mới"),
                "created_at": c.created_at,
                "updated_at": c.updated_at,
            })
        return result

    def delete_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> bool:
        self._titles.pop(conversation_id, None)
        return self._store.delete_conversation(conversation_id, user_id=user_id)

    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
    ) -> None:
        msg = Message(role=role, content=content, metadata=metadata or {})
        self._store.append_message(conversation_id, msg, user_id=user_id)

    def get_messages(self, conversation_id: str, limit: Optional[int] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        messages = self._store.get_messages(conversation_id, user_id=user_id)
        if limit:
            messages = messages[-limit:]
        return [
            {
                "id": m.metadata.get("id") or str(uuid.uuid4()),
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at,
            }
            for m in messages
        ]

    def set_user_context(self, user_id: str, key: str, value: Any) -> None:
        self._store.update_user_context(user_id, {key: value})

    def get_user_context(self, user_id: str, key: str) -> Optional[Any]:
        return self._store.get_user_context(user_id).get(key)

    def set_agent_context(self, user_id: str, agent_name: str, key: str, value: Any) -> None:
        self._store.update_agent_context(user_id, agent_name, {key: value})

    def get_agent_context(self, user_id: str, agent_name: str, key: str) -> Optional[Any]:
        return self._store.get_agent_context(user_id, agent_name).get(key)


# Singleton dùng chung trong toàn bộ Chat API
memory_store = ChatbotMemoryAdapter()
