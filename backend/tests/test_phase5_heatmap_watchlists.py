"""Phase 5 tests: heatmap, watchlists CRUD/ownership, signal stats."""

import uuid

from app.models import Instrument, InstrumentType, Sector
from tests.conftest import auth_headers, login_user, register_user


async def _seed_market(db):
    it = Sector(name="Information Technology")
    fin = Sector(name="Banking & Financial Services")
    db.add_all([it, fin])
    await db.flush()
    insts = [
        Instrument(symbol="TCS", exchange="NSE", name="Tata Consultancy",
                   instrument_type=InstrumentType.STOCK, sector_id=it.id),
        Instrument(symbol="INFY", exchange="NSE", name="Infosys",
                   instrument_type=InstrumentType.STOCK, sector_id=it.id),
        Instrument(symbol="NIFTY 50", exchange="NSE", name="Nifty 50",
                   instrument_type=InstrumentType.INDEX),
    ]
    db.add_all(insts)
    await db.commit()
    return {i.symbol: i for i in insts}


async def _mk_user_with_token(client):
    await register_user(client)
    return await login_user(client)


# ------------------------------------------------------------------- heatmap

async def test_heatmap_groups_by_sector(client, db):
    from datetime import datetime, timezone
    from decimal import Decimal

    m = await _seed_market(db)
    from app.models import MarketData

    db.add(MarketData(instrument_id=m["TCS"].id, last_price=Decimal("3500"),
                      change_pct=Decimal("1.25"), previous_close=Decimal("3457")))
    await db.commit()

    resp = await client.get("/api/v1/heatmap?group_by=sector")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["group_by"] == "sector"
    keys = {g["key"]: g for g in body["groups"]}
    assert "Information Technology" in keys
    tcs_cell = next(c for c in keys["Information Technology"]["cells"] if c["symbol"] == "TCS")
    assert tcs_cell["last_price"] == 3500.0
    assert tcs_cell["bof_direction"] is None  # no signals yet â€” honest nulls


async def test_heatmap_group_by_type_and_filters(client, db):
    await _seed_market(db)
    r = await client.get("/api/v1/heatmap?group_by=type&type=index")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_cells"] == 1
    assert data["groups"][0]["cells"][0]["instrument_type"] == "INDEX"


async def test_heatmap_only_with_signals_flag(client, db):
    await _seed_market(db)
    r = await client.get("/api/v1/heatmap?only_with_signals=true")
    assert r.status_code == 200
    assert r.json()["data"]["total_cells"] == 0


# ---------------------------------------------------------------- watchlists

async def test_watchlists_require_auth(client):
    resp = await client.get("/api/v1/watchlists")
    assert resp.status_code == 401
    resp = await client.post("/api/v1/watchlists", json={"name": "x"})
    assert resp.status_code == 401


async def test_watchlist_crud_flow(client, db):
    tokens = await _mk_user_with_token(client)
    h = auth_headers(tokens)

    created = await client.post("/api/v1/watchlists", json={"name": "Core"}, headers=h)
    assert created.status_code == 201
    wl = created.json()["data"]
    assert wl["name"] == "Core" and wl["items"] == []

    dup = await client.post("/api/v1/watchlists", json={"name": "Core"}, headers=h)
    assert dup.status_code == 409

    renamed = await client.patch(f"/api/v1/watchlists/{wl['id']}",
                                 json={"name": "Core v2"}, headers=h)
    assert renamed.json()["data"]["name"] == "Core v2"

    deleted = await client.delete(f"/api/v1/watchlists/{wl['id']}", headers=h)
    assert deleted.status_code == 200
    empty = (await client.get("/api/v1/watchlists", headers=h)).json()["data"]
    assert empty == []


async def test_watchlist_items_add_remove_alert_reorder(client, db):
    m = await _seed_market(db)
    tokens = await _mk_user_with_token(client)
    h = auth_headers(tokens)

    wl = (await client.post("/api/v1/watchlists", json={"name": "Movers"}, headers=h)).json()["data"]

    added = await client.post(
        f"/api/v1/watchlists/{wl['id']}/items",
        json={"instrument_id": str(m["TCS"].id), "alert_enabled": True},
        headers=h,
    )
    assert added.status_code == 200
    items = added.json()["data"]["items"]
    assert len(items) == 1 and items[0]["alert_enabled"] is True and items[0]["position"] == 0

    again = await client.post(
        f"/api/v1/watchlists/{wl['id']}/items",
        json={"instrument_id": str(m["TCS"].id)},
        headers=h,
    )
    assert again.status_code == 409

    # second item then reorder first to position 5
    await client.post(f"/api/v1/watchlists/{wl['id']}/items",
                      json={"instrument_id": str(m["INFY"].id)}, headers=h)
    moved = await client.patch(
        f"/api/v1/watchlists/{wl['id']}/items/{m['TCS'].id}",
        json={"position": 5},
        headers=h,
    )
    positions = {i["symbol"]: i["position"] for i in moved.json()["data"]["items"]}
    assert positions["TCS"] == 5

    # alert toggle off
    toggled = await client.patch(
        f"/api/v1/watchlists/{wl['id']}/items/{m['TCS'].id}",
        json={"alert_enabled": False},
        headers=h,
    )
    tcs_item = next(i for i in toggled.json()["data"]["items"] if i["symbol"] == "TCS")
    assert tcs_item["alert_enabled"] is False

    removed = await client.delete(
        f"/api/v1/watchlists/{wl['id']}/items/{m['INFY'].id}", headers=h
    )
    assert removed.status_code == 200
    final = (await client.get(f"/api/v1/watchlists/{wl['id']}", headers=h)).json()["data"]
    assert [i["symbol"] for i in final["items"]] == ["TCS"]


async def test_watchlist_ownership_is_enforced(client, db):
    m = await _seed_market(db)
    owner_tokens = await _mk_user_with_token(client)
    owner_h = auth_headers(owner_tokens)

    wl = (await client.post("/api/v1/watchlists", json={"name": "Private"},
                            headers=owner_h)).json()["data"]
    await client.post(f"/api/v1/watchlists/{wl['id']}/items",
                      json={"instrument_id": str(m["TCS"].id)}, headers=owner_h)

    # second user cannot see / modify / delete the first user's list
    other_payload = {
        "email": "intruder@example.com",
        "password": "OtherPass123",
        "username": "intruder",
    }
    await client.post("/api/v1/auth/register", json=other_payload)
    other_login = await client.post(
        "/api/v1/auth/login",
        json={"email": other_payload["email"], "password": other_payload["password"]},
    )
    intruder_h = {"Authorization": f"Bearer {other_login.json()['data']['tokens']['access_token']}"}

    listed = (await client.get("/api/v1/watchlists", headers=intruder_h)).json()["data"]
    assert all(w["id"] != wl["id"] for w in listed)

    assert (await client.get(f"/api/v1/watchlists/{wl['id']}", headers=intruder_h)).status_code == 404
    assert (await client.patch(f"/api/v1/watchlists/{wl['id']}", json={"name": "hax"},
                               headers=intruder_h)).status_code == 404
    assert (await client.delete(f"/api/v1/watchlists/{wl['id']}", headers=intruder_h)).status_code == 404
    assert (await client.post(f"/api/v1/watchlists/{wl['id']}/items",
                              json={"instrument_id": str(m["INFY"].id)},
                              headers=intruder_h)).status_code == 404


async def test_add_unknown_instrument_404(client):
    tokens = await _mk_user_with_token(client)
    h = auth_headers(tokens)
    wl = (await client.post("/api/v1/watchlists", json={"name": "X"}, headers=h)).json()["data"]
    resp = await client.post(f"/api/v1/watchlists/{wl['id']}/items",
                             json={"instrument_id": str(uuid.uuid4())}, headers=h)
    assert resp.status_code == 404


# -------------------------------------------------------------- signal stats

async def test_signal_stats_zero_state(client, db):
    inst = Instrument(symbol="ZERO", exchange="NSE", name="Zero Signals",
                      instrument_type=InstrumentType.STOCK)
    db.add(inst)
    await db.commit()
    resp = await client.get(f"/api/v1/instruments/{inst.id}/signal-stats")
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["total_signals"] == 0 and d["avg_confidence"] is None


async def test_signal_stats_populated_after_pipeline(client, db):
    from app.workers.demo_pipeline import run_pipeline

    inst = Instrument(symbol="STAT", exchange="NSE", name="Stats Co",
                      instrument_type=InstrumentType.STOCK)
    db.add(inst)
    await db.commit()
    await run_pipeline(db, symbols={"STAT"}, days=30)

    resp = await client.get(f"/api/v1/instruments/{inst.id}/signal-stats")
    d = resp.json()["data"]
    assert d["total_signals"] > 0
    assert d["bullish"] + d["bearish"] == d["total_signals"]
    assert d["confirmation_rate"] is not None and 0 <= d["confirmation_rate"] <= 1
    strengths = {s["strength"] for s in d["by_strength"]}
    assert strengths <= {"WEAK", "MODERATE", "STRONG", "VERY_STRONG"}

