"""Phase 7 â€” admin API tests: guard, users, instruments, sessions, events."""

import uuid

from app.core.security import hash_password
from app.models import User
from tests.conftest import auth_headers, login_user, register_user


async def _mk_admin(client) -> dict:
    await register_user(client, email="admin@example.com", password="AdminPass1!",
                        username="admin")
    tokens = await login_user(client, email="admin@example.com", password="AdminPass1!")
    # promote via direct DB (the CLI does the same in real deployments)
    from sqlalchemy import select
    from tests.conftest import db  # noqa: F401

    user = (
        await client._scope.db.execute(select(User).where(User.email == "admin@example.com"))
    )
    return tokens


async def test_admin_requires_auth(client):
    resp = await client.get("/api/v1/admin/stats")
    assert resp.status_code == 401


async def test_admin_forbidden_for_regular_user(client):
    await register_user(client)
    tokens = await login_user(client)
    resp = await client.get("/api/v1/admin/stats", headers=auth_headers(tokens))
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN"


async def test_stats_shape_for_admin(client, db, monkeypatch):
    # create admin directly in the DB then log in
    db.add(User(email="root@example.com", username="root",
                hashed_password=hash_password("RootPass123!"),
                role=__import__("app.models.enums", fromlist=["UserRole"]).UserRole.ADMIN))
    await db.commit()

    tokens = await login_user(client, email="root@example.com", password="RootPass123!")
    h = auth_headers(tokens)

    resp = await client.get("/api/v1/admin/stats", headers=h)
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert {"total_users", "active_users", "signals_today", "total_signals",
            "active_instruments", "database", "ws_connections",
            "provider"} <= set(d)
    assert d["database"] in ("up", "down")


async def test_users_list_and_toggle(client, db):
    from app.models.enums import UserRole

    db.add(User(email="root2@example.com", hashed_password=hash_password("RootPass123!"),
                role=UserRole.ADMIN))
    target = User(email="victim@example.com", hashed_password=hash_password("VictimPass1!"))
    db.add(target)
    await db.commit()

    tokens = await login_user(client, email="root2@example.com", password="RootPass123!")
    h = auth_headers(tokens)

    listed = (await client.get("/api/v1/admin/users?q=victim", headers=h)).json()["data"]
    assert listed["total"] == 1
    uid = listed["items"][0]["id"]

    off = (await client.patch(f"/api/v1/admin/users/{uid}",
                              json={"is_active": False}, headers=h)).json()["data"]
    assert off["is_active"] is False

    promoted = (await client.patch(f"/api/v1/admin/users/{uid}",
                                   json={"role": "ADMIN"}, headers=h)).json()["data"]
    assert promoted["role"] == "ADMIN"

    bad = await client.patch(f"/api/v1/admin/users/{uid}", json={"role": "SUPERGOD"}, headers=h)
    assert bad.status_code == 422


async def test_instruments_coverage_and_deactivate(client, db):
    from app.models import Instrument, InstrumentType
    from app.models.enums import UserRole

    db.add(User(email="root3@example.com", hashed_password=hash_password("RootPass123!"),
                role=UserRole.ADMIN))
    inst = Instrument(symbol="COV", exchange="NSE", name="Coverage Co",
                      instrument_type=InstrumentType.STOCK)
    db.add(inst)
    await db.commit()

    tokens = await login_user(client, email="root3@example.com", password="RootPass123!")
    h = auth_headers(tokens)

    cov = (await client.get("/api/v1/admin/instruments", headers=h)).json()["data"]
    row = next(i for i in cov["items"] if i["symbol"] == "COV")
    assert row["m15_candles"] == 0 and row["last_m15_ts"] is None

    off = (await client.patch(f"/api/v1/admin/instruments/{inst.id}",
                              json={"is_active": False}, headers=h)).json()["data"]
    assert off["is_active"] is False


async def test_market_sessions_upsert(client, db):
    from app.models.enums import UserRole

    db.add(User(email="root4@example.com", hashed_password=hash_password("RootPass123!"),
                role=UserRole.ADMIN))
    await db.commit()
    tokens = await login_user(client, email="root4@example.com", password="RootPass123!")
    h = auth_headers(tokens)

    created = await client.post(
        "/api/v1/admin/market-sessions",
        json={"session_date": "2026-10-02", "market": "NSE",
              "status": "HOLIDAY", "note": "Gandhi Jayanti"},
        headers=h,
    )
    assert created.status_code == 201
    assert created.json()["data"]["created"] is True

    again = await client.post(
        "/api/v1/admin/market-sessions",
        json={"session_date": "2026-10-02", "market": "NSE",
              "status": "HALF_DAY"},
        headers=h,
    )
    assert again.json()["data"]["created"] is False

    listed = (await client.get("/api/v1/admin/market-sessions", headers=h)).json()["data"]
    entry = next(e for e in listed if e["session_date"] == "2026-10-02")
    assert entry["status"] == "HALF_DAY"


async def test_bad_session_date_rejected(client, db):
    from app.models.enums import UserRole

    db.add(User(email="root5@example.com", hashed_password=hash_password("RootPass123!"),
                role=UserRole.ADMIN))
    await db.commit()
    tokens = await login_user(client, email="root5@example.com", password="RootPass123!")
    h = auth_headers(tokens)

    resp = await client.post("/api/v1/admin/market-sessions",
                             json={"session_date": "not-a-date", "status": "HOLIDAY"},
                             headers=h)
    assert resp.status_code == 422


async def test_admin_signals_view(client, db):
    from app.models import Instrument, InstrumentType, Signal
    from datetime import datetime, timezone
    from app.models.enums import SignalDirection, SignalStatus, SignalStrength, Timeframe
    from app.models.enums import UserRole

    db.add(User(email="root6@example.com", hashed_password=hash_password("RootPass123!"),
                role=UserRole.ADMIN))
    inst = Instrument(symbol="ADM", exchange="NSE", name="Admin Co",
                      instrument_type=InstrumentType.STOCK)
    db.add(inst)
    await db.flush()
    db.add(Signal(instrument_id=inst.id, timeframe=Timeframe.H1, signal_type="BOF",
                  direction=SignalDirection.BEARISH, strength=SignalStrength.STRONG,
                  status=SignalStatus.DETECTING, bof_level=100,
                  confidence=0.55, detected_at=datetime.now(timezone.utc)))
    await db.commit()

    tokens = await login_user(client, email="root6@example.com", password="RootPass123!")
    h = auth_headers(tokens)

    resp = await client.get("/api/v1/admin/signals?status=DETECTING", headers=h)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] >= 1
    assert data["items"][0]["status"] == "DETECTING"



