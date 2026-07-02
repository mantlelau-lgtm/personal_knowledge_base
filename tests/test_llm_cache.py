import time

from common.llm_cache import LLMCache


def test_make_key_deterministic():
    a = LLMCache.make_key("summarize", "m1", "prompt", "ctx")
    b = LLMCache.make_key("summarize", "m1", "prompt", "ctx")
    c = LLMCache.make_key("summarize", "m1", "prompt", "ctx2")
    d = LLMCache.make_key("chat", "m1", "prompt", "ctx")
    e = LLMCache.make_key("summarize", "m2", "prompt", "ctx")
    assert a == b
    assert a != c
    assert a != d
    assert a != e
    assert len(a) == 64  # sha256 hex


def test_set_get_roundtrip(settings):
    cache = LLMCache(settings)
    key = LLMCache.make_key("chat", "m", "hi", "")
    cache.set(key, "chat", "m", "answer", ttl_seconds=60)
    assert cache.get(key) == "answer"


def test_ttl_expiry(settings):
    cache = LLMCache(settings)
    key = LLMCache.make_key("chat", "m", "expire-me", "")
    cache.set(key, "chat", "m", "answer", ttl_seconds=1)
    time.sleep(1.1)
    assert cache.get(key) is None
    stats = cache.stats()
    assert stats["expired"] > 0


def test_clear_expired_returns_count(settings):
    cache = LLMCache(settings)
    for i in range(3):
        cache.set(
            LLMCache.make_key("chat", "m", f"prompt-{i}", ""),
            "chat",
            "m",
            f"resp-{i}",
            ttl_seconds=1,
        )
    live_key = LLMCache.make_key("chat", "m", "live", "")
    cache.set(live_key, "chat", "m", "live-resp", ttl_seconds=60)
    time.sleep(1.1)
    removed = cache.clear_expired()
    assert removed == 3
    stats = cache.stats()
    assert stats["total"] == 1
    assert stats["expired"] == 0
    assert cache.get(live_key) == "live-resp"
