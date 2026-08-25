"""Authentication flow tests: register, login, refresh rotation, logout,
password reset, validation and error-envelope contract."""

import httpx
from tests.conftest import REGISTER_PAYLOAD, auth_headers, login_user, register_user


async def test_register_returns_tokens_and_user(client):
    data = await register_user(client)
    assert data["user"]["email"] == REGISTER_PAYLOAD["email"]
    assert data["user"]["role"] == "USER"
    assert "hashed_password" not in data["user"]
    assert data["tokens"]["access_token"]
    assert data["tokens"]["refresh_token"]
    assert data["tokens"]["token_type"] == "bearer"


async def test_register_duplicate_email_conflict(client):
    await register_user(client)
    resp = await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
    assert resp.status_code == 409
    body = resp.json()
    assert body["success"] is False
    assert body["error"]["code"] == "CONFLICT"


async def test_register_short_password_rejected(client):
    resp = await client.post("/api/v1/auth/register", json={
        "email": "shortpw@example.com", "password": "short",
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_login_success(client):
    await register_user(client)
    data = await login_user(client)
    assert data["user"]["username"] == "trader"


async def test_login_wrong_password_uniform_error(client):
    await register_user(client)
    resp = await client.post("/api/v1/auth/login", json={
        "email": REGISTER_PAYLOAD["email"], "password": "wrong-password",
    })
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    # Unknown email must produce the identical error (no enumeration).
    resp2 = await client.post("/api/v1/auth/login", json={
        "email": "ghost@example.com", "password": "wrong-password",
    })
    assert resp2.status_code == 401
    assert resp2.json() == resp.json()


async def test_refresh_rotates_tokens(client):
    await register_user(client)
    tokens = (await login_user(client))["tokens"]

    resp = await client.post("/api/v1/auth/refresh",
                             json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    new_tokens = resp.json()["data"]
    assert new_tokens["refresh_token"] != tokens["refresh_token"]

    # The old refresh token was rotated → reuse must fail.
    resp_old = await client.post("/api/v1/auth/refresh",
                                 json={"refresh_token": tokens["refresh_token"]})
    assert resp_old.status_code == 401

    # And the theft guard revokes ALL sessions → even the new token dies.
    resp_new = await client.post("/api/v1/auth/refresh",
                                 json={"refresh_token": new_tokens["refresh_token"]})
    assert resp_new.status_code == 401


async def test_logout_revokes_session(client):
    await register_user(client)
    tokens = (await login_user(client))["tokens"]
    resp = await client.post("/api/v1/auth/logout",
                             json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 200
    assert resp.json()["data"]["revoked"] is True

    resp2 = await client.post("/api/v1/auth/refresh",
                              json={"refresh_token": tokens["refresh_token"]})
    assert resp2.status_code == 401


async def test_access_token_grants_profile_access(client):
    await register_user(client)
    tokens = await login_user(client)
    resp = await client.get("/api/v1/profile", headers=auth_headers(tokens))
    assert resp.status_code == 200
    assert resp.json()["data"]["email"] == REGISTER_PAYLOAD["email"]


async def test_profile_requires_auth(client):
    resp = await client.get("/api/v1/profile")
    assert resp.status_code == 401
    assert resp.json()["success"] is False


async def test_forgot_password_never_enumerates(client):
    await register_user(client)
    for email in (REGISTER_PAYLOAD["email"], "missing@example.com"):
        resp = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert resp.status_code == 200
        assert resp.json()["data"]["message"].startswith("If that account exists")


async def test_reset_password_with_invalid_token(client):
    resp = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": "0" * 32 + "invalidtokenvalue", "new_password": "NewPassword1!"},
    )
    assert resp.status_code == 422
