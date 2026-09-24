import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class Cache(Protocol):
    async def get(self, key: str) -> object | None: ...

    async def set(
        self,
        key: str,
        value: object,
        ttl_seconds: float | None = None,
    ) -> None: ...

    async def delete(self, key: str) -> None: ...


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    value: object
    expires_at: float | None


class MemoryTTLCache:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, _CacheEntry] = {}

    async def get(self, key: str) -> object | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if entry.expires_at is not None and self._clock() >= entry.expires_at:
            del self._entries[key]
            return None
        return entry.value

    async def set(
        self,
        key: str,
        value: object,
        ttl_seconds: float | None = None,
    ) -> None:
        if value is None:
            raise ValueError("None is not a cacheable value")
        if ttl_seconds is not None and (
            ttl_seconds <= 0 or not math.isfinite(ttl_seconds)
        ):
            raise ValueError("ttl_seconds must be positive and finite")

        expires_at = None if ttl_seconds is None else self._clock() + ttl_seconds
        self._entries[key] = _CacheEntry(value, expires_at)

    async def delete(self, key: str) -> None:
        self._entries.pop(key, None)
