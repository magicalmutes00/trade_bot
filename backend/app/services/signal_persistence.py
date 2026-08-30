"""Signal & candle persistence — idempotent upserts (Phase 3 pipeline tail).

Two execution paths, identical semantics:
- PostgreSQL: native ``INSERT … ON CONFLICT DO UPDATE`` (bulk, fast).
- Other dialects (SQLite test harness): row-wise ORM merge.

Idempotency keys:
    candles  → (instrument_id, timeframe, ts)
    signals  → (instrument_id, timeframe, signal_type, detected_at)  # trigger bar
The signal_type is part of the key so BOF and PATTERN families can share a
trigger bar without colliding.
Status convergence rule: CONFIRMED never regresses to DETECTING.
Timestamp comparison keys are normalised because SQLite round-trips naive
datetimes while PostgreSQL keeps timestamptz.
"""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.engine.models import EngineSignal
from app.models import Candle, MarketData, Signal, SignalEvent, Timeframe


def _is_pg(db: AsyncSession) -> bool:
    return db.bind is not None and db.bind.dialect.name == "postgresql"


def _norm_ts(dt: datetime) -> datetime:
    """Comparison key that survives SQLite's naive-datetime round-trip."""
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


# --------------------------------------------------------------------- candles

async def store_candles(
    db: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    timeframe: Timeframe,
    candles: list,
) -> int:
    if not candles:
        return 0

    rows = [
        {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "ts": c.ts,
            "open": c.open,
            "high": c.high,
            "low": c.low,
            "close": c.close,
            "volume": int(c.volume or 0),
        }
        for c in candles
    ]

    if _is_pg(db):
        total = 0
        for i in range(0, len(rows), 3000):  # asyncpg 32k bind-param ceiling / 8 params
            stmt = pg_insert(Candle).values(rows[i : i + 3000])
            stmt = stmt.on_conflict_do_update(
                index_elements=["instrument_id", "timeframe", "ts"],
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                },
            )
            await db.execute(stmt)
            total += min(3000, len(rows) - i)
        return total

    written = 0
    for r in rows:
        existing = (
            await db.execute(
                select(Candle).where(
                    Candle.instrument_id == instrument_id,
                    Candle.timeframe == timeframe,
                    Candle.ts == _norm_ts(r["ts"]),
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(Candle(**r))
        else:
            existing.open, existing.high = r["open"], r["high"]
            existing.low, existing.close = r["low"], r["close"]
            existing.volume = r["volume"]
        written += 1
    await db.flush()
    return written


# ------------------------------------------------------------------ market data

async def refresh_market_data(
    db: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    last_close: float,
    previous_close: float | None,
    day_open: float | None,
    day_high: float | None,
    day_low: float | None,
    volume: int | None,
    updated_at: datetime,
) -> None:
    change = (last_close - previous_close) if previous_close is not None else None
    change_pct = (change / previous_close * 100) if previous_close else None

    values = dict(
        instrument_id=instrument_id,
        last_price=last_close,
        previous_close=previous_close,
        change=change,
        change_pct=change_pct,
        day_open=day_open,
        day_high=day_high,
        day_low=day_low,
        volume=volume,
        updated_at=updated_at,
    )

    if _is_pg(db):
        stmt = pg_insert(MarketData).values(**values)
        stmt = stmt.on_conflict_do_update(index_elements=["instrument_id"], set_=values)
        await db.execute(stmt)
        return

    existing = (
        await db.execute(select(MarketData).where(MarketData.instrument_id == instrument_id))
    ).scalar_one_or_none()
    if existing is None:
        db.add(MarketData(**values))
    else:
        for k, v in values.items():
            setattr(existing, k, v)
    await db.flush()


# ---------------------------------------------------------------------- signals

async def persist_signals(db: AsyncSession, signals: list[EngineSignal]) -> dict[str, int]:
    """Batched upsert — O(1) query groups per call instead of per-signal I/O."""
    stats = {"signals_created": 0, "signals_updated": 0, "events_added": 0}
    if not signals:
        return stats

    tf = Timeframe(signals[0].timeframe)
    stype = signals[0].signal_type

    existing_rows = (
        await db.execute(
            select(Signal).where(
                Signal.instrument_id == signals[0].instrument_id,
                Signal.timeframe == tf,
                Signal.signal_type == stype,
            )
        )
    ).scalars().all()
    by_key = {(r.signal_type, _norm_ts(r.detected_at)): r for r in existing_rows}

    pending_events: list[tuple[uuid.UUID | None, list[str], dict]] = []
    new_rows: list[Signal] = []

    for s in signals:
        wanted = ["DETECTED"]
        if s.status == "CONFIRMED":
            wanted.append("CONFIRMED")
        elif s.status.startswith("INVALIDATED"):
            wanted.append("INVALIDATED")

        existing = by_key.get((s.signal_type, _norm_ts(s.detected_at)))

        if existing is None:
            row = Signal(
                instrument_id=s.instrument_id,
                timeframe=tf,
                signal_type=s.signal_type,
                direction=s.direction,
                bof_level=s.bof_level,
                breakout_price=s.breakout_price,
                failure_price=s.failure_price,
                entry_price=s.entry_price,
                stop_reference=s.stop_reference,
                confidence=s.confidence,
                strength=s.strength,
                status=s.status,
                detected_at=s.detected_at,
                confirmed_at=s.confirmed_at,
                signal_metadata=s.metadata,
            )
            new_rows.append(row)
            db.add(row)
            stats["signals_created"] += 1
            pending_events.append((None, wanted, s.metadata))  # id assigned at flush
            continue

        prior_status = existing.status
        existing.status = (
            prior_status if (prior_status == "CONFIRMED" and s.status == "DETECTING")
            else s.status
        )
        existing.confirmed_at = existing.confirmed_at or s.confirmed_at
        existing.failure_price = existing.failure_price or s.failure_price
        existing.entry_price = existing.entry_price or s.entry_price
        existing.stop_reference = existing.stop_reference or s.stop_reference
        existing.confidence = s.confidence
        existing.strength = s.strength
        existing.signal_metadata = s.metadata

        # Pre-existing rows always carry their DETECTED event; only terminal
        # events can be genuinely missing after a status transition.
        missing = [w for w in ("CONFIRMED", "INVALIDATED") if w in wanted]
        if missing and prior_status != "CONFIRMED":
            pending_events.append((existing.id, missing, s.metadata))
        stats["signals_updated"] += 1

    await db.flush()  # assigns ids to new rows

    new_ids = iter([r.id for r in new_rows])
    resolved: list[tuple[uuid.UUID, list[str], dict]] = []
    for sid, wanted, meta in pending_events:
        resolved.append((sid if sid is not None else next(new_ids), wanted, meta))

    if resolved:
        all_ids = [sid for sid, _, _ in resolved]
        have = set(
            (
                await db.execute(
                    select(SignalEvent.signal_id, SignalEvent.event_type)
                    .where(SignalEvent.signal_id.in_(all_ids))
                )
            ).all()
        )
        for sid, wanted, meta in resolved:
            for evt in wanted:
                if (sid, evt) in have:
                    continue
                db.add(SignalEvent(signal_id=sid, event_type=evt, event_data=meta))
                stats["events_added"] += 1

    await db.flush()
    return stats


__all__ = ["store_candles", "refresh_market_data", "persist_signals"]
