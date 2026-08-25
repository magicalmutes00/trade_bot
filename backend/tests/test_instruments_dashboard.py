"""Phase 2 endpoint tests: instruments list/detail/candles + dashboard."""

from app.models import Instrument, InstrumentType, Sector
from tests.conftest import auth_headers, login_user, register_user


async def _seed(db):
    it = Sector(name="Information Technology")
    fin = Sector(name="Banking & Financial Services")
    db.add_all([it, fin])
    await db.flush()
    db.add_all([
        Instrument(symbol="TCS", exchange="NSE", name="Tata Consultancy Services",
                   instrument_type=InstrumentType.STOCK, sector_id=it.id),
        Instrument(symbol="INFY", exchange="NSE", name="Infosys Limited",
                   instrument_type=InstrumentType.STOCK, sector_id=it.id),
        Instrument(symbol="HDFCBANK", exchange="NSE", name="HDFC Bank Limited",
                   instrument_type=InstrumentType.STOCK, sector_id=fin.id),
        Instrument(symbol="NIFTY 50", exchange="NSE", name="Nifty 50",
                   instrument_type=InstrumentType.INDEX),
        Instrument(symbol="SENSEX", exchange="BSE", name="S&P BSE Sensex",
                   instrument_type=InstrumentType.INDEX),
    ])
    await db.commit()


async def test_instruments_list_paginates(client, db):
    await _seed(db)
    resp = await client.get("/api/v1/instruments?limit=2&offset=0")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 5
    assert len(data["items"]) == 2


async def test_instruments_search_by_symbol_and_name(client, db):
    await _seed(db)
    r1 = (await client.get("/api/v1/instruments?q=tcs")).json()["data"]
    assert r1["total"] == 1 and r1["items"][0]["symbol"] == "TCS"

    r2 = (await client.get("/api/v1/instruments?q=hdfc")).json()["data"]
    assert r2["total"] == 1 and r2["items"][0]["symbol"] == "HDFCBANK"


async def test_instruments_filter_by_type(client, db):
    await _seed(db)
    data = (await client.get("/api/v1/instruments?type=index")).json()["data"]
    symbols = {i["symbol"] for i in data["items"]}
    assert symbols == {"NIFTY 50", "SENSEX"}


async def test_instruments_invalid_type_rejected(client, db):
    resp = await client.get("/api/v1/instruments?type=NOPE")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_instruments_invalid_sort_rejected(client, db):
    resp = await client.get("/api/v1/instruments sort=x".replace(" ", "?"))
    # malformed path -> 404; use proper query instead:
    resp = await client.get("/api/v1/instruments", params={"sort": "moon_phase"})
    assert resp.status_code == 422


async def test_instruments_sort_alphabetical(client, db):
    await _seed(db)
    items = (await client.get("/api/v1/instruments?sort=symbol")).json()["data"]["items"]
    symbols = [i["symbol"] for i in items]
    assert symbols == sorted(symbols)


async def test_instruments_requires_no_auth(client, db):
    """Market reference data is public per spec §13."""
    await _seed(db)
    resp = await client.get("/api/v1/instruments")
    assert resp.status_code == 200


async def test_instrument_detail_shape(client, db):
    await _seed(db)
    listing = (await client.get("/api/v1/instruments?q=TCS")).json()["data"]["items"][0]
    detail = (await client.get(f"/api/v1/instruments/{listing['id']}")).json()["data"]
    assert detail["symbol"] == "TCS"
    assert detail["sector_name"] == "Information Technology"
    assert detail["quote"] is None  # no provider yet — honest null, not fake prices
    assert detail["stats"]["total_signals"] == 0


async def test_instrument_detail_not_found(client, db):
    from uuid import uuid4

    resp = await client.get(f"/api/v1/instruments/{uuid4()}")
    assert resp.status_code == 404


async def test_candles_empty_until_provider(client, db):
    await _seed(db)
    listing = (await client.get("/api/v1/instruments?q=TCS")).json()["data"]["items"][0]
    resp = await client.get(
        f"/api/v1/instruments/{listing['id']}/candles?timeframe=15m&limit=100"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["items"] == [] and data["has_more"] is False


async def test_candles_bad_timeframe_rejected(client, db):
    await _seed(db)
    listing = (await client.get("/api/v1/instruments?q=TCS")).json()["data"]["items"][0]
    resp = await client.get(f"/api/v1/instruments/{listing['id']}/candles?timeframe=7m")
    assert resp.status_code == 422


async def test_dashboard_shape_with_empty_markets(client, db):
    await _seed(db)
    resp = await client.get("/api/v1/dashboard")
    assert resp.status_code == 200
    d = resp.json()["data"]
    assert d["market_status"]["market"] == "NSE"
    assert d["market_status"]["status"] in {"OPEN", "PRE_OPEN", "CLOSED"}
    # No market_data rows yet → zero fabricated quotes.
    assert d["indices"] == []
    assert d["bof_summary"] == {
        "active_total": 0, "bullish": 0, "bearish": 0,
        "strong": 0, "new_today": 0, "detected_today": 0,
    }
    assert d["latest_signals"] == [] and d["strongest_signals"] == []


async def test_profile_still_protected_after_new_routes(client, db):
    resp = await client.get("/api/v1/profile")
    assert resp.status_code == 401
    await register_user(client)
    tokens = await login_user(client)
    ok = await client.get("/api/v1/profile", headers=auth_headers(tokens))
    assert ok.status_code == 200
