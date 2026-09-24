"""
InMemoryCache - Bộ nhớ đệm trong RAM với hỗ trợ thời gian hết hạn (TTL) và thread-safe.
Triển khai BaseCache theo AI_Plan (Mục 3.1 - Thành viên 5).
"""
import time
import threading
from typing import Any, Dict, Optional, Tuple

from shared.abstractions.cache import BaseCache


class InMemoryCache(BaseCache):
    """Lớp cache lưu trong bộ nhớ RAM, hỗ trợ TTL và thread-safe."""

    def __init__(self):
        # Lưu trữ dạng: key -> (value, expires_at_timestamp)
        self._store: Dict[str, Tuple[Any, Optional[float]]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[Any]:
        """Lấy giá trị từ cache theo key. Trả về None nếu không có hoặc đã hết hạn."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at is not None and time.time() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Lưu giá trị vào cache kèm thời gian sống (TTL) tính bằng giây."""
        with self._lock:
            expires_at = (time.time() + ttl_seconds) if (ttl_seconds is not None and ttl_seconds > 0) else None
            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """Xóa key khỏi cache. Trả về True nếu key tồn tại và đã xóa, False nếu không tồn tại."""
        with self._lock:
            return self._store.pop(key, None) is not None

    def clear(self) -> None:
        """Xóa sạch toàn bộ cache."""
        with self._lock:
            self._store.clear()

    def exists(self, key: str) -> bool:
        """Kiểm tra key có tồn tại và chưa hết hạn hay không."""
        return self.get(key) is not None
