"""Pattern analysis for instruments — compute on stored candles, persist as PATTERN signals.

Two entry points with identical semantics:
- ``analyze_instrument`` — read-only: latest pattern hits for one timeframe.
- ``sync_instrument`` / ``sync_all`` — compute + persist (idempotent upsert
  keyed by signal_type + detected_at) so the scheduled worker keeps pattern
  rows current and push/dashboard consumers can rely on them.

Timeframe scope: the mandatory TRADEBOT timeframes (§1) with stored candle
coverage today — H4 and D1. Weekly/Monthly aggregation is wired in a later
stage (needs a longer stored history than the demo backfill provides).
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.config import DEFAULT_PATTERN_CONFIG, PatternConfig
from app.engine.models import EngineCandle
from app.engine.patterns import detect_patterns, hit_to_engine_signal, hit_to_json
from app.engine.swings import analyse
from app.models import Instrument, Timeframe
from app.repositories.instrument_repository import InstrumentRepository
from app.schemas.pattern import PatternResponse
from app.services.signal_persistence import persist_signals

logger = logging.getLogger(__name__)

# Spec §1 mandatory timeframes; those with stored candles today get scanned.
MANDATORY_TIMEFRAMES = (Timeframe.H4, Timeframe.D1, Timeframe.W1, Timeframe.MO)
SCAN_TIMEFRAMES = (Timeframe.H4, Timeframe.D1)

PATTERN_BARS = 250
PIVOT_LEFT = 3          # fractal confirmation window (as in the BOF engine)
PIVOT_RIGHT = 3


@dataclass(frozen=True)
class AnalyzedPattern:
    """A pattern hit enriched with when it fired (persistence + display key)."""

    timeframe: Timeframe
    hit: object                    # app.engine.patterns.PatternHit
    detected_at: datetime          # anchor bar ts — confirm bar, else last top/bottom


def _to_engine_candles(rows) -> list[EngineCandle]:
    rows = list(rows)
    return [
        EngineCandle(
            ts=c.ts, open=float(c.open), high=float(c.high),
            low=float(c.low), close=float(c.close), volume=float(c.volume or 0),
        )
        for c in reversed(rows)    # repository returns newest-first
    ]


async def analyze_instrument(
    db: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    timeframe: Timeframe,
    bars: int = PATTERN_BARS,
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[AnalyzedPattern]:
    """Run the pattern detectors over the stored candles (read-only)."""
    rows = await InstrumentRepository(db).candles(
        instrument_id=instrument_id, timeframe=timeframe, limit=bars, before=None
    )
    candles = _to_engine_candles(rows)
    if len(candles) < 2:
        return []

    structure = analyse(candles, left=PIVOT_LEFT, right=PIVOT_RIGHT)
    hits = detect_patterns(structure, candles, cfg)

    out: list[AnalyzedPattern] = []
    for h in hits:
        anchor = h.confirm_index if h.confirm_index is not None else h.swing_indices[2]
        detected_at = candles[anchor].ts if 0 <= anchor < len(candles) else candles[-1].ts
        out.append(AnalyzedPattern(timeframe=timeframe, hit=h, detected_at=detected_at))
    return out


def empty_response(timeframe: Timeframe) -> PatternResponse:
    """Spec §32/§36 'None' shape — served for scanned TFs without a pattern
    so clients always see uniform per-timeframe state."""
    return PatternResponse(
        timeframe=timeframe.value,
        pattern_detected="None",
        status="Forming",
        direction="Neutral",
        confidence=0.0,
        entry="N/A",
        stop_loss="N/A",
        target_1="N/A",
        target_2="N/A",
        target_3="N/A",
        invalidation="N/A",
        additional_notes="No pattern detected on this timeframe.",
        reasoning="Structure, swing and confirmation checks did not match any rule in the engine spec.",
    )


def analyzed_to_response(ap: AnalyzedPattern) -> PatternResponse:
    """Spec-§35 JSON shape served over REST."""
    j = hit_to_json(ap.hit)
    return PatternResponse(
        timeframe=ap.timeframe.value,
        pattern_detected=j["pattern_detected"],
        status=j["status"],
        direction=j["direction"],
        confidence=j["confidence"],
        entry=j["entry"],
        stop_loss=j["stop_loss"],
        target_1=j["target_1"],
        target_2=j["target_2"],
        target_3=j["target_3"],
        invalidation=j["invalidation"],
        additional_notes=j["additional_notes"],
        reasoning=j["reasoning"],
        neckline_price=j["neckline_price"],
        peak_price=j["peak_price"],
        swing_indices=j["swing_indices"],
        confirm_index=j["confirm_index"],
        detected_at=ap.detected_at,
    )


async def sync_instrument(
    db: AsyncSession,
    *,
    instrument_id: uuid.UUID,
    timeframe: Timeframe,
    bars: int = PATTERN_BARS,
) -> tuple[list[AnalyzedPattern], dict]:
    """Compute the latest hits, upsert them as PATTERN signals, return both."""
    analyzed = await analyze_instrument(db, instrument_id=instrument_id, timeframe=timeframe, bars=bars)
    signals = [
        hit_to_engine_signal(instrument_id, timeframe.value, ap.hit, ap.detected_at)
        for ap in analyzed
    ]
    stats = await persist_signals(db, signals)
    return analyzed, {
        "hits": len(signals),
        "created": stats["signals_created"],
        "updated": stats["signals_updated"],
    }


async def sync_all(
    db: AsyncSession,
    *,
    timeframes: tuple[Timeframe, ...] = SCAN_TIMEFRAMES,
    progress=None,
) -> dict:
    """Scan every active instrument across the given timeframes.

    ``progress(symbol, done, total)`` fires after each instrument; one bad
    instrument/timeframe is logged and skipped rather than killing the pass.
    """
    instruments = (
        await db.execute(select(Instrument).where(Instrument.is_active.is_(True)))
    ).scalars().all()

    totals = {"instruments": len(instruments), "hits": 0, "created": 0, "updated": 0, "failed": 0}
    for done, inst in enumerate(instruments, start=1):
        try:
            for tf in timeframes:
                _analyzed, stats = await sync_instrument(db, instrument_id=inst.id, timeframe=tf)
                totals["hits"] += stats["hits"]
                totals["created"] += stats["created"]
                totals["updated"] += stats["updated"]
            await db.commit()
        except Exception:  # noqa: BLE001 — one bad instrument ≠ dead pass
            await db.rollback()
            totals["failed"] += 1
            logger.warning("pattern scan failed for %s", inst.symbol, exc_info=True)
        if progress is not None:
            progress(inst.symbol, done, totals)

    logger.info("pattern scan finished: %s", totals)
    return totals