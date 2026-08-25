"""Profile & settings endpoint tests."""

from tests.conftest import auth_headers, login_user, register_user


async def test_update_profile(client):
    await register_user(client)
    tokens = await login_user(client)

    resp = await client.patch(
        "/api/v1/profile",
        json={"display_name": "Pro Trader"},
        headers=auth_headers(tokens),
    )
    assert resp.status_code == 200
    assert resp.json()["data"]["display_name"] == "Pro Trader"


async def test_settings_defaults_created_on_first_get(client):
    await register_user(client)
    tokens = await login_user(client)

    resp = await client.get("/api/v1/settings", headers=auth_headers(tokens))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["theme"] == "SYSTEM"
    assert data["default_timeframe"] == "15m"


async def test_settings_patch_merges_preferences(client):
    await register_user(client)
    tokens = await login_user(client)
    h = auth_headers(tokens)

    resp = await client.patch(
        "/api/v1/settings",
        json={"theme": "DARK", "preferences": {"compact": True}},
        headers=h,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["theme"] == "DARK"
    assert data["preferences"]["compact"] is True

    # Second patch keeps earlier preference keys (merge, not replace).
    resp2 = await client.patch(
        "/api/v1/settings",
        json={"preferences": {"show_volume": False}},
        headers=h,
    )
    prefs = resp2.json()["data"]["preferences"]
    assert prefs["compact"] is True and prefs["show_volume"] is False


async def test_expired_or_garbage_token_rejected(client):
    resp = await client.get(
        "/api/v1/profile", headers={"Authorization": "Bearer not-a-jwt"}
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_TOKEN"
