"""Stage 3 integration tests: pattern engine → persistence → REST endpoint.

Crafts a clean daily double top (peak1=159.6 idx5, plateau, peak2=159.2 idx18,
neckline valley=144 idx12, close 139 < 144 at idx23) built for the engine's
left=right=3 pivot windows, then verifies the spec-§35 response shape, the
PATTERN signal rows, and idempotent replay.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.engine.models import EngineCandle
from app.models import Instrument, InstrumentType, Signal, Timeframe
from app.services.signal_persistence import store_candles

T0 = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)

# (high, low) per day; closes default to (h+l)/2 unless a 3rd tuple element.
DOUBLE_TOP_DAYS = [
    (150, 148), (153, 149), (155, 150), (157, 152), (158, 155.5),
    (159.6, 157), (158, 156), (156, 154), (153, 151), (151, 149),
    (149, 147), (148, 145), (147, 144), (150, 147), (153, 148),
    (155, 150), (156, 152), (158, 153), (159.2, 154), (157, 155),
    (154, 152), (151, 150), (149, 147), (148, 140, 139),   # close 139 < 144 → confirm
]


def _daily_candles() -> list[EngineCandle]:
    out = []
    for i, (h, l, *rest) in enumerate(DOUBLE_TOP_DAYS):
        c = rest[0] if rest else (h + l) / 2
        out.append(EngineCandle(
            ts=T0 + timedelta(days=i), open=(h + l) / 2,
            high=h, low=l, close=c, volume=1000.0,
        ))
    return out


async def _mk_stock(db, symbol: str = "PAT1") -> Instrument:
    inst = Instrument(symbol=symbol, exchange="NSE", name=f"{symbol} Ltd",
                      instrument_type=InstrumentType.STOCK)
    db.add(inst)
    await db.commit()
    return inst


async def _store_double_top(db, inst: Instrument) -> None:
    await store_candles(db, instrument_id=inst.id, timeframe=Timeframe.D1, candles=_daily_candles())
    await db.commit()


async def test_patterns_endpoint_spec_shape(client, db):
    inst = await _mk_stock(db, "PAT1")
    await _store_double_top(db, inst)

    resp = await client.get(f"/api/v1/instruments/{inst.id}/patterns?timeframe=1D")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["symbol"] == "PAT1"
    assert len(data["timeframes"]) == 1
    tf = data["timeframes"][0]

    # spec §35 shape
    assert tf["timeframe"] == "1D"
    assert tf["pattern_detected"] == "DOUBLE_TOP"
    assert tf["status"] == "FULLY_FORMED"
    assert tf["direction"] == "BEARISH"
    assert 0.0 <= float(tf["confidence"]) <= 1.0
    assert tf["entry"] == "144.00"
    assert tf["stop_loss"] == "159.60"
    assert tf["target_1"] == "128.60 (measured height)"
    assert tf["target_2"] == "N/A"
    assert tf["target_3"] == "N/A"
    assert "CLOSES above" in tf["invalidation"]
    assert tf["reasoning"]
    assert tf["additional_notes"]
    assert tf["neckline_price"] == 144.0
    assert tf["confirm_index"] == 23


async def test_patterns_scans_stored_mandatory_timeframes(client, db):
    """Default (no ?timeframe) returns both stored mandatory TFs (4h, 1D)."""
    inst = await _mk_stock(db, "PAT2")
    await store_candles(db, instrument_id=inst.id, timeframe=Timeframe.D1, candles=_daily_candles())
    await db.commit()

    resp = await client.get(f"/api/v1/instruments/{inst.id}/patterns")
    assert resp.status_code == 200, resp.text
    tfs = [t["timeframe"] for t in resp.json()["data"]["timeframes"]]
    assert "1D" in tfs
    assert "4h" in tfs


async def test_patterns_persists_patent_signal_rows(client, db):
    inst = await _mk_stock(db, "PAT3")
    await _store_double_top(db, inst)

    await client.get(f"/api/v1/instruments/{inst.id}/patterns?timeframe=1D")

    rows = (
        await db.execute(
            select(Signal).where(
                Signal.instrument_id == inst.id,
                Signal.signal_type == "PATTERN",
            )
        )
    ).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.timeframe == Timeframe.D1
    assert row.status == "CONFIRMED"                     # FULLY_FORMED → CONFIRMED
    assert row.bof_level == 144.0                        # neckline stored in bof_level
    assert row.entry_price == 144.0
    assert row.direction == "BEARISH"
    assert row.signal_metadata["pattern"] == "DOUBLE_TOP"
    assert row.signal_metadata["target_1"] == "128.60 (measured height)"

    # replay must not duplicate (idempotent upsert)
    await client.get(f"/api/v1/instruments/{inst.id}/patterns?timeframe=1D")
    count = (
        await db.execute(
            select(func.count()).select_from(Signal).where(
                Signal.instrument_id == inst.id,
                Signal.signal_type == "PATTERN",
            )
        )
    ).scalar_one()
    assert count == 1


async def test_patterns_no_patterns_flat_series(client, db):
    inst = await _mk_stock(db, "FLAT")
    candles = [EngineCandle(
        ts=T0 + timedelta(days=i), open=100, high=101, low=99, close=100, volume=1000,
    ) for i in range(60)]
    await store_candles(db, instrument_id=inst.id, timeframe=Timeframe.D1, candles=candles)
    await db.commit()

    resp = await client.get(f"/api/v1/instruments/{inst.id}/patterns?timeframe=1D")
    assert resp.status_code == 200, resp.text
    tfs = resp.json()["data"]["timeframes"]
    assert len(tfs) == 1
    assert tfs[0]["pattern_detected"] == "None"
    assert tfs[0]["status"] == "Forming"
    assert tfs[0]["confidence"] == 0.0


async def test_patterns_unknown_instrument_404(client, db):
    import uuid

    resp = await client.get(f"/api/v1/instruments/{uuid.uuid4()}/patterns")
    assert resp.status_code == 404