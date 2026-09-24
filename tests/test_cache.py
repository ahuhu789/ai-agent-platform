import time
from shared.cache.in_memory_cache import InMemoryCache


def test_in_memory_cache_basic_operations():
    cache = InMemoryCache()

    # Test set and get
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"
    assert cache.exists("key1") is True

    # Test delete
    assert cache.delete("key1") is True
    assert cache.get("key1") is None
    assert cache.delete("non_existent") is False


def test_in_memory_cache_ttl():
    cache = InMemoryCache()

    # Set with 1 second TTL
    cache.set("short_lived", "data", ttl_seconds=1)
    assert cache.get("short_lived") == "data"

    # Wait for expiry
    time.sleep(1.1)
    assert cache.get("short_lived") is None
    assert cache.exists("short_lived") is False


def test_in_memory_cache_clear():
    cache = InMemoryCache()
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
