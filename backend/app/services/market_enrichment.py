"""Shared market enrichment: attach quotes + current BOF state to instruments."""

import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, MarketData, Signal, SignalStatus


async def latest_signals_by_instrument(
    db: AsyncSession,
    instrument_ids: list[uuid.UUID] | None = None,
    *,
    timeframe=None,
) -> dict[uuid.UUID, Signal]:
    """Most recent DETECTING/CONFIRMED signal per instrument (portable SQL)."""
    conds = [Signal.status.in_([SignalStatus.CONFIRMED, SignalStatus.DETECTING])]
    if instrument_ids is not None:
        if not instrument_ids:
            return {}
        conds.append(Signal.instrument_id.in_(instrument_ids))
    if timeframe is not None:
        conds.append(Signal.timeframe == timeframe)

    maxes = (
        await db.execute(
            select(Signal.instrument_id.label("iid"), func.max(Signal.detected_at).label("md"))
            .where(*conds)
            .group_by(Signal.instrument_id)
        )
    ).all()
    if not maxes:
        return {}

    pairs = [(m.iid, m.md) for m in maxes]
    rows = (
        await db.execute(
            select(Signal).where(
                *[
                    and_(
                        Signal.instrument_id.in_([p[0] for p in pairs]),
                        Signal.detected_at.in_([p[1] for p in pairs]),
                    )
                ]
            )
        )
    ).scalars().all()

    out: dict[uuid.UUID, Signal] = {}
    wanted = set(pairs)
    for s in rows:
        if (s.instrument_id, s.detected_at) in wanted:
            # keep the newest row per instrument on tie
            cur = out.get(s.instrument_id)
            if cur is None or s.detected_at >= cur.detected_at:
                out[s.instrument_id] = s
    return out


async def quotes_by_instrument(
    db: AsyncSession,
    instrument_ids: list[uuid.UUID] | None = None,
) -> dict[uuid.UUID, MarketData]:
    conds = []
    if instrument_ids is not None:
        if not instrument_ids:
            return {}
        conds.append(MarketData.instrument_id.in_(instrument_ids))
    rows = (
        await db.execute(select(MarketData).where(*conds) if conds else select(MarketData))
    ).scalars().all()
    return {r.instrument_id: r for r in rows}


def quote_fields(md: MarketData | None) -> dict:
    if md is None:
        return {"last_price": None, "change_pct": None, "updated_at": None}
    return {
        "last_price": float(md.last_price),
        "change_pct": float(md.change_pct) if md.change_pct is not None else None,
        "updated_at": md.updated_at,
    }


def bof_fields(signal: Signal | None) -> dict:
    if signal is None:
        return {"bof_direction": None, "bof_strength": None, "bof_status": None,
                "bof_timeframe": None, "bof_detected_at": None}
    return {
        "bof_direction": signal.direction.value if hasattr(signal.direction, "value") else signal.direction,
        "bof_strength": signal.strength.value if hasattr(signal.strength, "value") else signal.strength,
        "bof_status": signal.status.value if hasattr(signal.status, "value") else signal.status,
        "bof_timeframe": signal.timeframe.value if hasattr(signal.timeframe, "value") else signal.timeframe,
        "bof_detected_at": signal.detected_at,
    }


async def enrich(db: AsyncSession, instruments: list[Instrument], *, timeframe=None) -> dict[uuid.UUID, dict]:
    """{instrument_id: {quote…, bof…}} for the given instruments."""
    ids = [i.id for i in instruments]
    quotes = await quotes_by_instrument(db, ids)
    signals = await latest_signals_by_instrument(db, ids, timeframe=timeframe)
    return {
        i.id: {**quote_fields(quotes.get(i.id)), **bof_fields(signals.get(i.id))}
        for i in instruments
    }


__all__ = [
    "latest_signals_by_instrument", "quotes_by_instrument",
    "quote_fields", "bof_fields", "enrich",
]
