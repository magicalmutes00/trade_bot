"""Rate limiting on auth endpoints (in-memory sliding window)."""

from app.core.rate_limit import reset_rate_limits


async def test_login_rate_limited_per_ip(client):
    reset_rate_limits()
    payload = {"email": "nobody@example.com", "password": "whatever123"}
    codes = []
    for _ in range(12):
        resp = await client.post("/api/v1/auth/login", json=payload)
        codes.append(resp.status_code)
    # All attempts before the limit are 401; once exhausted it's 429.
    assert codes.count(401) >= 1
    assert 429 in codes
    limited = await client.post("/api/v1/auth/login", json=payload)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMITED"
    reset_rate_limits()
