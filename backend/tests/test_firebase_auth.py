"""Firebase authentication tests.

The Firebase Admin SDK is never initialized in tests — ``app.core.firebase``
is stubbed at module level so tokens are classified without real credentials.
No production Firebase credentials are used anywhere in this suite.
"""

from typing import Any

import httpx
import pytest

from app.core import firebase
from app.core.errors import TokenError
from app.core.firebase import FirebaseUserInfo
from tests.conftest import auth_headers, login_user, register_user

VALID_TOKEN = "valid-firebase-id-token-aaaaaaaaaaaaaaaaaa"
EXPIRED_TOKEN = "expired-firebase-id-token-bbbbbbbbbbbbbb"
INVALID_TOKEN = "invalid-firebase-id-token-cccccccccccccc"


def make_info(uid: str = "fb-uid-123", email: str | None = "g.user@gmail.com",
              **overrides: Any) -> FirebaseUserInfo:
    return FirebaseUserInfo(
        uid=uid,
        email=email,
        display_name=overrides.get("display_name", "Google User"),
        photo_url=overrides.get("photo_url", "https://lh3.googleusercontent.com/a.jpg"),
        email_verified=overrides.get("email_verified", True),
        provider_id=overrides.get("provider_id", "google.com"),
    )


@pytest.fixture
def fake_firebase(monkeypatch):
    """Stub token verification: no real Firebase, deterministic outcomes."""
    def _verify(token: str) -> FirebaseUserInfo:
        if token == VALID_TOKEN:
            return make_info()
        if token == EXPIRED_TOKEN:
            raise TokenError("Your session has expired. Please sign in again.")
        raise TokenError("Invalid authentication token")

    monkeypatch.setattr(firebase, "verify_firebase_token", _verify)
    return _verify


async def test_firebase_login_creates_user(client, db, fake_firebase):
    resp = await client.post("/api/v1/auth/firebase", json={"id_token": VALID_TOKEN})
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    user = body["data"]
    assert user["firebase_uid"] == "fb-uid-123"
    assert user["email"] == "g.user@gmail.com"
    assert user["display_name"] == "Google User"
    assert user["auth_provider"] == "GOOGLE"
    # No password credential is ever created for Google users.
    assert "token" not in user and "password" not in user


async def test_returning_user_synchronized_not_duplicated(client, db, fake_firebase):
    first = (await client.post("/api/v1/auth/firebase",
                               json={"id_token": VALID_TOKEN})).json()["data"]
    second = (await client.post("/api/v1/auth/firebase",
                                json={"id_token": VALID_TOKEN})).json()["data"]
    assert first["id"] == second["id"]


async def test_invalid_token_rejected(client, fake_firebase):
    resp = await client.post("/api/v1/auth/firebase", json={"id_token": INVALID_TOKEN})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_TOKEN"


async def test_expired_token_rejected_with_clear_message(client, fake_firebase):
    resp = await client.post("/api/v1/auth/firebase", json={"id_token": EXPIRED_TOKEN})
    assert resp.status_code == 401
    assert "expired" in resp.json()["error"]["message"].lower()


async def test_protected_endpoint_rejects_missing_header(client):
    resp = await client.get("/api/v1/profile")
    assert resp.status_code == 401
    assert resp.json()["success"] is False


async def test_protected_endpoint_accepts_verified_firebase_bearer(client, db, fake_firebase):
    await client.post("/api/v1/auth/firebase", json={"id_token": VALID_TOKEN})
    resp = await client.get("/api/v1/profile", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["firebase_uid"] == "fb-uid-123"


async def test_firebase_bearer_without_provisioning_is_rejected(client, db, fake_firebase):
    """A valid Firebase token for a user that never synced must not silently pass."""
    resp = await client.get("/api/v1/profile", headers={"Authorization": f"Bearer {VALID_TOKEN}"})
    assert resp.status_code == 401


async def test_legacy_email_password_auth_still_works(client, db, fake_firebase):
    """Regression: existing custom JWT authority is untouched."""
    # Register a legacy account that uses the SAME email as the Google identity,
    # so account linking by verified email can kick in.
    await register_user(client, email="g.user@gmail.com")
    data = await login_user(client, email="g.user@gmail.com")
    resp = await client.get("/api/v1/profile", headers=auth_headers(data))
    assert resp.status_code == 200
    legacy_user = resp.json()["data"]
    assert legacy_user["firebase_uid"] is None

    # Google login with the same email links the existing account...
    linked = (await client.post("/api/v1/auth/firebase",
                                json={"id_token": VALID_TOKEN})).json()["data"]
    assert linked["id"] == legacy_user["id"]

    # ...and the old password login keeps working afterwards.
    again = await login_user(client, email="g.user@gmail.com")
    resp2 = await client.get("/api/v1/profile", headers=auth_headers(again))
    assert resp2.status_code == 200


async def test_google_account_cannot_use_password_login(client, db, fake_firebase):
    await client.post("/api/v1/auth/firebase", json={"id_token": VALID_TOKEN})
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "g.user@gmail.com", "password": "whatever-pass"},
    )
    assert resp.status_code == 401
