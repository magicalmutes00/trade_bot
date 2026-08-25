"""Tiny JSON cache over Redis with graceful no-Redis fallback.

Usage:
    data = cached_json("dash:v1", 10, lambda: build_dashboard_dict())

- Values must be JSON-serialisable (call sites pass plain dicts).
- Unset REDIS_URL / connection failure → producer runs directly (never fails
  a request because the cache is down).
- One shared sync client, lazily created; safe inside FastAPI threadpool deps.
"""

import json
import threading

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_client = None
_dead = False
_lock = threading.Lock()

stats = {"hits": 0, "misses": 0, "writes": 0, "errors": 0}


def _get_client():
    """Lazy singleton sync client; None when unconfigured/unreachable."""
    global _client, _dead
    if not settings.REDIS_URL:
        return None
    if _client is not None:
        return _client
    if _dead:
        return None

    with _lock:
        if _client is not None or _dead:
            return _client
        try:
            import redis

            client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            _client = client
            logger.info("redis cache connected")
            return client
        except Exception as exc:  # noqa: BLE001
            _dead = True
            logger.warning("redis cache unavailable (%s) — caches disabled",
                           type(exc).__name__)
            return None


def reset_cache_state() -> None:
    """Test helper."""
    global _client, _dead
    with _lock:
        _client = None
        _dead = False
    stats.update(hits=0, misses=0, writes=0, errors=0)


def cached_json(key: str, ttl_seconds: int, producer):
    """Sync variant — producer returns the value directly."""
    import inspect

    if inspect.iscoroutinefunction(producer) or _is_coro(producer):
        raise TypeError("use acached_json for async producers")
    return _cached_impl(key, ttl_seconds, producer)


async def acached_json(key: str, ttl_seconds: int, producer):
    """Async variant — `producer` may be sync or async."""
    client = _get_client()
    if client is not None:
        try:
            raw = client.get(key)
            if raw is not None:
                stats["hits"] += 1
                return json.loads(raw)
        except Exception:  # noqa: BLE001
            stats["errors"] += 1

    value = producer()
    if _is_coro(value):
        value = await value
    _store(client, key, ttl_seconds, value)
    stats["misses"] += 1
    return value


def _is_coro(value):
    import inspect

    return inspect.iscoroutine(value) or inspect.isawaitable(value)


def _cached_impl(key: str, ttl_seconds: int, producer):
    value = producer()
    client = _get_client()
    _store(client, key, ttl_seconds, value)
    stats["misses"] += 1
    return value


def _store(client, key: str, ttl_seconds: int, value) -> None:
    if client is not None:
        try:
            client.setex(key, ttl_seconds, json.dumps(value, default=str))
            stats["writes"] += 1
        except Exception:  # noqa: BLE001
            stats["errors"] += 1


__all__ = ["cached_json", "acached_json", "reset_cache_state", "stats"]
