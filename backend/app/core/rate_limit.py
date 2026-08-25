"""Simple in-memory sliding-window rate limiter.

This is intentionally dependency-free for Phase 1. The public interface
(``check`` raising :class:`RateLimitError`) is the only thing callers see,
so the storage can be swapped for Redis later by replacing this one file.
"""

import threading
import time
from collections import defaultdict, deque

from app.core.errors import RateLimitError

_lock = threading.Lock()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, limit: int, window_seconds: float = 60.0) -> None:
    now = time.monotonic()
    with _lock:
        bucket = _buckets[key]
        cutoff = now - window_seconds
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            raise RateLimitError("Too many requests. Please slow down.")
        bucket.append(now)


def reset_rate_limits() -> None:
    """Test helper."""
    with _lock:
        _buckets.clear()
