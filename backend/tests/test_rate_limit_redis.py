"""Redis-backed limiter: graceful degradation when the cache is unreachable."""

import pytest

from app.core import rate_limit
from app.core.rate_limit import check_rate_limit, reset_rate_limits
from app.core.errors import RateLimitError


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Force a dead-redis URL for every test here; restore afterwards."""
    monkeypatch.setattr("app.core.config.settings.REDIS_URL", "redis://127.0.0.1:1/0")
    # reset module-level singletons so each test re-attempts connection
    rate_limit._redis_client = None
    rate_limit._redis_dead = False
    yield
    rate_limit._redis_client = None
    rate_limit._redis_dead = False


async def test_dead_redis_degrades_to_memory_and_still_enforces():
    limits_hit = 0
    for _ in range(10):
        try:
            check_rate_limit("degraded", 3, 60)
            limits_hit += 1
        except RateLimitError:
            break
    assert limits_hit == 3, "memory fallback must keep enforcing the limit"
    assert rate_limit.backend_name() == "memory"
