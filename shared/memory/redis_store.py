"""Memory lưu trong Redis.

Cấu trúc key (message nằm trong Redis list nên ghi đồng thời không bị mất):
  conversation:{cid}:meta         hash  : user_id, created_at, updated_at
  conversation:{cid}:messages     list  : mỗi phần tử là 1 message dạng JSON
  user_conversations:{uid}        zset  : cid -> thời điểm cập nhật (để list_conversations)
  user_context:{uid}         hash  : field -> giá trị JSON
  agent_context:{uid}:{agent} hash : field -> giá trị JSON

Redis client được inject qua constructor, module này KHÔNG import thư viện redis.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from shared.abstractions.memory import (
    DEFAULT_HISTORY_LIMIT,
    MemoryStore,
    Message,
    Conversation,
    _now,
    clamp_history_limit,
)

logger = logging.getLogger(__name__)


def _s(value: Any) -> str:
    """Chuẩn hóa bytes -> str (client có thể bật hoặc tắt decode_responses)."""
    return value.decode("utf-8") if isinstance(value, bytes) else value


class RedisMemoryStore(MemoryStore):
    def __init__(
        self,
        redis_client,
        conversation_ttl_seconds: Optional[int] = 86400,
        context_ttl_seconds: Optional[int] = None,
    ) -> None:
        """
        conversation_ttl_seconds: thời gian sống của conversation (làm mới mỗi lần có message).
        context_ttl_seconds: thời gian sống của user/agent context, None = không hết hạn.
        """
        self._r = redis_client
        self._conversation_ttl = conversation_ttl_seconds
        self._context_ttl = context_ttl_seconds

    # ---- key builders --------------------------------------------------
    @staticmethod
    def _meta_key(cid: str) -> str:
        return f"conversation:{cid}:meta"

    @staticmethod
    def _msgs_key(cid: str) -> str:
        return f"conversation:{cid}:messages"

    @staticmethod
    def _index_key(uid: str) -> str:
        return f"user_conversations:{uid}"

    @staticmethod
    def _user_ctx_key(uid: str) -> str:
        return f"user_context:{uid}"

    @staticmethod
    def _agent_ctx_key(uid: str, agent: str) -> str:
        return f"agent_context:{uid}:{agent}"

    # ---- helpers -------------------------------------------------------
    def _meta(self, conversation_id: str, user_id: Optional[str]) -> Optional[dict]:
        """Metadata của conversation nếu tồn tại và đúng chủ, ngược lại None."""
        raw = self._r.hgetall(self._meta_key(conversation_id))
        if not raw:
            return None
        meta = {_s(k): _s(v) for k, v in raw.items()}
        if user_id is not None and meta.get("user_id") != user_id:
            logger.warning("user %s truy cập conversation %s không thuộc về mình", user_id, conversation_id)
            return None
        return meta

    def _expire(self, pipe, *keys: str) -> None:
        if self._conversation_ttl:
            for key in keys:
                pipe.expire(key, self._conversation_ttl)

    def _read_context(self, key: str) -> dict:
        raw = self._r.hgetall(key)
        return {_s(k): json.loads(_s(v)) for k, v in raw.items()}

    def _write_context(self, key: str, data: dict) -> None:
        if not data:
            return
        # HSET theo từng field nên hai lần update khác key không ghi đè nhau.
        pipe = self._r.pipeline()
        pipe.hset(key, mapping={k: json.dumps(v, ensure_ascii=False) for k, v in data.items()})
        if self._context_ttl:
            pipe.expire(key, self._context_ttl)
        pipe.execute()

    # ---- Conversation --------------------------------------------------
    def create_conversation(self, user_id: str) -> Conversation:
        conversation = Conversation(user_id=user_id)
        pipe = self._r.pipeline()
        pipe.hset(
            self._meta_key(conversation.conversation_id),
            mapping={
                "user_id": user_id,
                "created_at": conversation.created_at,
                "updated_at": conversation.updated_at,
            },
        )
        pipe.zadd(self._index_key(user_id), {conversation.conversation_id: time.time()})
        self._expire(pipe, self._meta_key(conversation.conversation_id))
        pipe.execute()
        logger.debug("created conversation %s for user %s", conversation.conversation_id, user_id)
        return conversation

    def get_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> Optional[Conversation]:
        meta = self._meta(conversation_id, user_id)
        if meta is None:
            return None
        return Conversation(
            user_id=meta["user_id"],
            conversation_id=conversation_id,
            messages=self.get_messages(conversation_id, user_id),
            created_at=meta["created_at"],
            updated_at=meta["updated_at"],
        )

    def list_conversations(self, user_id: str) -> list[Conversation]:
        conversations: list[Conversation] = []
        for raw_cid in self._r.zrevrange(self._index_key(user_id), 0, -1):
            cid = _s(raw_cid)
            meta = self._meta(cid, user_id)
            if meta is None:  # conversation đã hết hạn -> dọn index
                self._r.zrem(self._index_key(user_id), cid)
                continue
            conversations.append(
                Conversation(
                    user_id=user_id,
                    conversation_id=cid,
                    messages=[],
                    created_at=meta["created_at"],
                    updated_at=meta["updated_at"],
                )
            )
        return conversations

    def delete_conversation(self, conversation_id: str, user_id: Optional[str] = None) -> bool:
        meta = self._meta(conversation_id, user_id)
        if meta is None:
            return False
        pipe = self._r.pipeline()
        pipe.delete(self._meta_key(conversation_id), self._msgs_key(conversation_id))
        pipe.zrem(self._index_key(meta["user_id"]), conversation_id)
        pipe.execute()
        logger.debug("deleted conversation %s", conversation_id)
        return True

    # ---- Message -------------------------------------------------------
    def append_message(self, conversation_id: str, message: Message, user_id: Optional[str] = None) -> None:
        meta = self._meta(conversation_id, user_id)
        if meta is None:
            raise KeyError(conversation_id)
        payload = json.dumps(message.to_dict(), ensure_ascii=False)
        pipe = self._r.pipeline()
        pipe.rpush(self._msgs_key(conversation_id), payload)  # atomic, không mất message
        pipe.hset(self._meta_key(conversation_id), "updated_at", _now())
        pipe.zadd(self._index_key(meta["user_id"]), {conversation_id: time.time()})
        self._expire(pipe, self._meta_key(conversation_id), self._msgs_key(conversation_id))
        pipe.execute()

    def get_history(
        self, conversation_id: str, limit: int = DEFAULT_HISTORY_LIMIT, user_id: Optional[str] = None
    ) -> list[Message]:
        limit = clamp_history_limit(limit)
        if self._meta(conversation_id, user_id) is None:
            return []
        raw = self._r.lrange(self._msgs_key(conversation_id), -limit, -1)
        return [Message.from_dict(json.loads(_s(item))) for item in raw]

    def get_messages(self, conversation_id: str, user_id: Optional[str] = None) -> list[Message]:
        if self._meta(conversation_id, user_id) is None:
            return []
        raw = self._r.lrange(self._msgs_key(conversation_id), 0, -1)
        return [Message.from_dict(json.loads(_s(item))) for item in raw]

    # ---- Context -------------------------------------------------------
    def get_user_context(self, user_id: str) -> dict:
        return self._read_context(self._user_ctx_key(user_id))

    def update_user_context(self, user_id: str, data: dict) -> None:
        self._write_context(self._user_ctx_key(user_id), data)

    def get_agent_context(self, user_id: str, agent_name: str) -> dict:
        return self._read_context(self._agent_ctx_key(user_id, agent_name))

    def update_agent_context(self, user_id: str, agent_name: str, data: dict) -> None:
        self._write_context(self._agent_ctx_key(user_id, agent_name), data)
