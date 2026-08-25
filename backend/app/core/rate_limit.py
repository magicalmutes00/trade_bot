"""Sliding/fixed-window rate limiting with pluggable storage.

Storage selection (spec §21 — Redis-ready):
    - ``REDIS_URL`` set   → Redis fixed-window counters (INCR + EXPIRE).
    - unset / unreachable → in-memory sliding window (single-process dev).

Both paths share one public entry point (:func:`check_rate_limit`) so callers
never change. Redis failures degrade gracefully to memory with a one-time
warning — availability beats strictness for this control.
"""

import threading
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import RateLimitError
from app.core.logging import get_logger

logger = get_logger(__name__)

_KEY_PREFIX = "rl:"

# ------------------------------------------------------------------ memory

_mem_lock = threading.Lock()
_mem_buckets: defaultdict[str, deque[float]] = defaultdict(deque)

# ------------------------------------------------------------------ redis

_redis_client = None
_redis_dead = False  # one warning per process lifetime


def _get_redis():
    """Lazy singleton sync client; None when unconfigured/unreachable."""
    global _redis_client, _redis_dead
    url = settings.REDIS_URL
    if not url:
        return None
    if _redis_client is not None:
        return _redis_client
    if _redis_dead:
        return None

    try:
        import redis  # sync client — safe inside FastAPI's threadpool deps

        client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        _redis_client = client
        logger.info("rate limiter backend: redis (%s)", _safe_host(url))
        return client
    except Exception as exc:  # noqa: BLE001
        _redis_dead = True
        logger.warning("redis unavailable (%s) — falling back to in-memory limiter",
                       type(exc).__name__)
        return None


def _safe_host(url: str) -> str:
    try:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(url)
        return urlunparse((parsed.scheme, parsed.netloc.split("@")[-1], "", "", "", ""))
    except Exception:  # noqa: BLE001
        return "<redis>"


def backend_name() -> str:
    """'redis' | 'memory' — reflects the *active* backend for admin/health."""
    if settings.REDIS_URL and _get_redis() is not None:
        return "redis"
    return "memory"


def reset_rate_limits() -> None:
    """Test helper — wipes every counter."""
    with _mem_lock:
        _mem_buckets.clear()
    client = _redis_client
    if client is not None:
        try:
            for key in client.scan_iter(f"{_KEY_PREFIX}*"):
                client.delete(key)
        except Exception:  # noqa: BLE001
            pass


def _memory_check(key: str, limit: int, window_seconds: float) -> None:
    now = time.monotonic()
    with _mem_lock:
        bucket = _mem_buckets[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise RateLimitError("Too many requests. Please slow down.")
        bucket.append(now)


def check_rate_limit(key: str, limit: int, window_seconds: float = 60.0) -> None:
    """Enforce `limit` calls per window for `key`; raises RateLimitError."""
    client = _get_redis()

    if client is None:
        _memory_check(key, limit, window_seconds)
        return

    full_key = f"{_KEY_PREFIX}{key}"
    try:
        pipe = client.pipeline(transaction=True)
        pipe.incr(full_key)
        pipe.ttl(full_key)
        current, ttl = pipe.execute()
        if current == 1 or ttl < 0:
            client.expire(full_key, max(1, int(window_seconds)))
        if int(current) > limit:
            raise RateLimitError("Too many requests. Please slow down.")
    except RateLimitError:
        raise
    except Exception:  # noqa: BLE001 — redis blip: degrade, don't block traffic
        global _redis_dead
        _redis_dead = True
        logger.warning("redis error during rate-limit check — memory fallback engaged")
        _memory_check(key, limit, window_seconds)


__all__ = ["check_rate_limit", "reset_rate_limits", "backend_name"]
