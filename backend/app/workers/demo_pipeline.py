"""Demo pipeline: provider â†’ validation â†’ candles â†’ quotes â†’ BOF engine â†’ persistence.

Runs offline via CLI (`backfill-demo`); Phase 4 wires the same functions into
a live loop that also broadcasts over WebSocket. Safe to re-run any time:
storage is idempotent and the provider's price paths are pure functions of
(symbol, bar-index), so replays converge instead of duplicating.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import bof_engine
from app.engine.strategies import run_strategies
from app.models import Instrument, Timeframe
from app.services.providers.factory import build_provider
from app.services.signal_persistence import persist_signals, refresh_market_data, store_candles
from app.workers.candle_processing import normalise

logger = logging.getLogger(__name__)

ENGINE_TIMEFRAMES = (Timeframe.M15, Timeframe.H1)   # signals per timeframe
STORAGE_TIMEFRAMES = (Timeframe.M15, Timeframe.H1, Timeframe.H4, Timeframe.D1)
MIN_BARS_FOR_ENGINE = 30


async def _load_reference(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Instrument).where(Instrument.is_active.is_(True)))
    return [
        {
            "symbol": i.symbol,
            "exchange": i.exchange,
            "name": i.name,
            "instrument_type": i.instrument_type.value,
        }
        for i in result.scalars().all()
    ]


def _aggregate(raw: list[dict], tf_value: str) -> list[dict]:
    from app.services.providers.demo_provider import _aggregate as agg

    return raw if tf_value == "15m" else agg(raw, tf_value)


async def run_pipeline(
    db: AsyncSession,
    *,
    symbols: set[str] | None = None,
    days: int = 45,
    progress=None,
    skip_existing: bool = False,
    provider=None,
) -> dict:
    """Ingest + analyse every active instrument (or a filtered subset).

    ``progress(symbol, done, totals)`` fires after each instrument.
    ``skip_existing`` drops instruments that already hold a full M15 window â€”
    makes long backfills resumable after interruptions.
    ``provider`` — pre-built provider (verified); built fresh when omitted.
    """
    reference = await _load_reference(db)
    if provider is None:
        provider = build_provider(reference)
    history_bars = int(timedelta(days=days).total_seconds() // (15 * 60)) + 2

    result = await db.execute(select(Instrument).where(Instrument.is_active.is_(True)))
    instruments = [i for i in result.scalars().all() if symbols is None or i.symbol in symbols]

    if skip_existing and instruments:
        from sqlalchemy import func

        from app.models import Candle

        counts = dict(
            (
                await db.execute(
                    select(Instrument.symbol, func.count())
                    .join(Candle, Candle.instrument_id == Instrument.id)
                    .where(Candle.timeframe == Timeframe.M15)
                    .group_by(Instrument.symbol)
                )
            ).all()
        )
        threshold = max(history_bars - 64, 1)
        before = len(instruments)
        instruments = [i for i in instruments if counts.get(i.symbol, 0) < threshold]
        logger.info("skip_existing: %d/%d already complete", before - len(instruments), before)

    totals = {
        "instruments": len(instruments), "candles": 0,
        "signals_created": 0, "signals_updated": 0, "events_added": 0,
    }

    for done, inst in enumerate(instruments, start=1):
        try:
            raw = await provider.get_candles(inst.symbol, "15m", history_bars)
        except Exception as exc:  # noqa: BLE001 — one bad symbol ≠ dead run
            logger.warning(
                "pipeline: no candles for %s (%s) — skipped",
                inst.symbol, str(exc)[:120],
            )
            totals["instruments_failed"] = totals.get("instruments_failed", 0) + 1
            if progress is not None:
                progress(inst.symbol, done, totals)
            continue
        if not raw:
            logger.warning("pipeline: empty candle series for %s — skipped", inst.symbol)
            totals["instruments_failed"] = totals.get("instruments_failed", 0) + 1
            if progress is not None:
                progress(inst.symbol, done, totals)
            continue

        for tf in STORAGE_TIMEFRAMES:
            series = normalise(_aggregate(raw, tf.value))
            totals["candles"] += await store_candles(
                db, instrument_id=inst.id, timeframe=tf, candles=series
            )

        # BOF engine + multi-strategy engine on the two primary intraday timeframes
        for tf in ENGINE_TIMEFRAMES:
            series = normalise(_aggregate(raw, tf.value))
            if len(series) < MIN_BARS_FOR_ENGINE:
                continue

            # BOF signals
            signals = bof_engine.run(instrument_id=inst.id, timeframe=tf.value, candles=series)
            stats = await persist_signals(db, signals)
            for k in ("signals_created", "signals_updated", "events_added"):
                totals[k] += stats[k]

            # Multi-strategy trade ideas (RSI / crossover / Bollinger)
            from app.engine.models import EngineCandle as _EC
            ec_candles = [
                _EC(ts=c.ts, open=c.open, high=c.high,
                    low=c.low, close=c.close, volume=float(c.volume or 0))
                for c in series
            ]
            trades = run_strategies(str(inst.id), tf.value, ec_candles)
            totals["trade_ideas"] = totals.get("trade_ideas", 0) + len(trades)

        # Chart-pattern signals (spec §8/§9) on the stored mandatory timeframes
        from app.services.pattern_service import SCAN_TIMEFRAMES, sync_instrument

        for ptf in SCAN_TIMEFRAMES:
            _ap, pstat = await sync_instrument(db, instrument_id=inst.id, timeframe=ptf)
            totals["patterns_hits"] = totals.get("patterns_hits", 0) + pstat["hits"]
            totals["patterns_created"] = totals.get("patterns_created", 0) + pstat["created"]
            totals["patterns_updated"] = totals.get("patterns_updated", 0) + pstat["updated"]

        await _refresh_quote(db, provider, inst)
        await db.commit()

        if progress is not None:
            progress(inst.symbol, done, totals)

    logger.info("demo pipeline finished: %s", totals)
    return totals


async def _refresh_quote(
    db: AsyncSession, provider, inst: Instrument
) -> None:
    """Latest-quote row from recent bars (feeds dashboard + heatmap)."""
    try:
        quote = await provider.get_quote(inst.symbol)
    except Exception as exc:  # noqa: BLE001 — quote failure shouldn't kill the pass
        logger.warning("pipeline: quote failed for %s (%s)", inst.symbol, str(exc)[:120])
        return
    if quote is None:
        return

    await refresh_market_data(
        db,
        instrument_id=inst.id,
        last_close=quote.get("last_price") or 0,
        previous_close=quote.get("previous_close"),
        day_open=quote.get("day_open"),
        day_high=quote.get("day_high"),
        day_low=quote.get("day_low"),
        volume=int(quote.get("volume") or 0) or None,
        updated_at=datetime.now(timezone.utc),
    )


__all__ = ["run_pipeline", "ENGINE_TIMEFRAMES", "STORAGE_TIMEFRAMES"]

