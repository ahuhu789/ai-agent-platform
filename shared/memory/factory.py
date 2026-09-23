"""Chọn implementation Memory bằng config, Chat Service không cần biết loại nào.

    store = create_memory_store()                 # đọc MEMORY_PROVIDER, REDIS_URL từ env
    store = create_memory_store("redis", redis_url="redis://localhost:6379/0")
    store = create_memory_store("in_memory")
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from shared.abstractions.memory import MemoryStore
from .in_memory_store import InMemoryStore
from .redis_store import RedisMemoryStore

logger = logging.getLogger(__name__)

_IN_MEMORY_NAMES = {"in_memory", "inmemory", "memory"}


def create_memory_store(provider: Optional[str] = None, **kwargs) -> MemoryStore:
    """provider: "in_memory" (mặc định) hoặc "redis".

    Với redis: truyền ``redis_client`` (khuyến nghị khi test) hoặc ``redis_url``.
    Các kwargs còn lại (conversation_ttl_seconds, context_ttl_seconds) chuyển cho RedisMemoryStore.
    """
    name = (provider or os.getenv("MEMORY_PROVIDER", "in_memory")).strip().lower()

    if name in _IN_MEMORY_NAMES:
        logger.info("Memory provider: in_memory")
        return InMemoryStore()

    if name == "redis":
        client = kwargs.pop("redis_client", None)
        url = kwargs.pop("redis_url", None) or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        if client is None:
            try:
                import redis  # import muộn để môi trường không dùng Redis không cần cài
            except ImportError as exc:
                raise RuntimeError("Cần cài thư viện 'redis' để dùng provider redis") from exc
            client = redis.Redis.from_url(url)
        logger.info("Memory provider: redis")
        return RedisMemoryStore(client, **kwargs)

    raise ValueError(f"Memory provider không tồn tại: {name!r} (hỗ trợ: in_memory, redis)")
