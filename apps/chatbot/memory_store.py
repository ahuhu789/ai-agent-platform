"""
Cài đặt TẠM THỜI của BaseMemoryStore, chỉ để Chat API (/chat, /conversations)
chạy độc lập trong lúc chờ `shared/memory/` (task MEM-01, phụ trách: Vũ Công
Nguyên Khang) hoàn thiện.

KHI shared/memory/InMemoryStore (hoặc RedisMemoryStore) đã sẵn sàng:
    - Xóa file này (hoặc giữ lại làm fallback cho môi trường test).
    - Trong agent_setup.py / main.py, đổi:
          from apps.chatbot.memory_store import memory_store
      thành:
          from shared.memory import InMemoryStore  # hoặc RedisMemoryStore
          memory_store = InMemoryStore()

Lưu ý: BaseMemoryStore (shared/abstractions/memory.py) chỉ định nghĩa lưu
message + context, KHÔNG có khái niệm "danh sách conversation". Vì vậy lớp
này có thêm các method quản lý conversation (create/list/get_meta/delete)
nằm NGOÀI interface chuẩn — cần cho GET /conversations của Chat API.
Nếu bản memory chính thức không hỗ trợ các method này, giữ lại lớp này
làm lớp quản lý conversation riêng, chỉ ủy quyền save_message/get_messages
sang memory store chính thức.
"""
import uuid
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from shared.abstractions.memory import BaseMemoryStore


def _now() -> datetime:
    return datetime.now(timezone.utc)


class InMemoryStore(BaseMemoryStore):
    def __init__(self):
        self._lock = Lock()
        self._conversations: Dict[str, Dict[str, Any]] = {}       # conversation_id -> meta
        self._messages: Dict[str, List[Dict[str, Any]]] = {}      # conversation_id -> [message]
        self._user_context: Dict[str, Dict[str, Any]] = {}        # user_id -> {key: value}
        self._agent_context: Dict[str, Dict[str, Any]] = {}       # f"{conv_id}:{agent}" -> {key: value}

    # ---------- Quản lý Conversation (bổ sung ngoài BaseMemoryStore) ----------
    def create_conversation(self, title: Optional[str] = None) -> str:
        conversation_id = str(uuid.uuid4())
        now = _now()
        with self._lock:
            self._conversations[conversation_id] = {
                "id": conversation_id,
                "title": title or "Cuộc trò chuyện mới",
                "created_at": now,
                "updated_at": now,
            }
            self._messages[conversation_id] = []
        return conversation_id

    def get_conversation_meta(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        return self._conversations.get(conversation_id)

    def list_conversations(self) -> List[Dict[str, Any]]:
        return sorted(self._conversations.values(), key=lambda c: c["updated_at"], reverse=True)

    def delete_conversation(self, conversation_id: str) -> bool:
        with self._lock:
            existed = conversation_id in self._conversations
            self._conversations.pop(conversation_id, None)
            self._messages.pop(conversation_id, None)
            return existed

    # ---------- BaseMemoryStore (bắt buộc) ----------
    def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._messages.setdefault(conversation_id, []).append(
                {
                    "id": str(uuid.uuid4()),
                    "role": role,
                    "content": content,
                    "metadata": metadata or {},
                    "created_at": _now(),
                }
            )
            if conversation_id in self._conversations:
                self._conversations[conversation_id]["updated_at"] = _now()

    def get_messages(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        messages = self._messages.get(conversation_id, [])
        return messages[-limit:] if limit else list(messages)

    def set_user_context(self, user_id: str, key: str, value: Any) -> None:
        with self._lock:
            self._user_context.setdefault(user_id, {})[key] = value

    def get_user_context(self, user_id: str, key: str) -> Optional[Any]:
        return self._user_context.get(user_id, {}).get(key)

    def set_agent_context(self, conversation_id: str, agent_name: str, key: str, value: Any) -> None:
        scope = f"{conversation_id}:{agent_name}"
        with self._lock:
            self._agent_context.setdefault(scope, {})[key] = value

    def get_agent_context(self, conversation_id: str, agent_name: str, key: str) -> Optional[Any]:
        scope = f"{conversation_id}:{agent_name}"
        return self._agent_context.get(scope, {}).get(key)


# Singleton dùng chung trong toàn bộ Chat API (giữ state trong 1 process).
# Khi đổi sang RedisMemoryStore, state sẽ ở Redis nên singleton kiểu này
# không còn cần thiết (nhiều process/worker vẫn thấy chung 1 dữ liệu).
memory_store = InMemoryStore()
