"""Demo pipeline: provider → validation → candles → quotes → BOF engine → persistence.

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
from app.models import Instrument, Timeframe
from app.services.providers.demo_provider import DemoMarketDataProvider
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
) -> dict:
    """Ingest + analyse every active instrument (or a filtered subset).

    ``progress(symbol, done, totals)`` fires after each instrument.
    ``skip_existing`` drops instruments that already hold a full M15 window —
    makes long backfills resumable after interruptions.
    """
    reference = await _load_reference(db)
    provider = DemoMarketDataProvider(reference)
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
        raw = await provider.get_candles(inst.symbol, "15m", history_bars)

        for tf in STORAGE_TIMEFRAMES:
            series = normalise(_aggregate(raw, tf.value))
            totals["candles"] += await store_candles(
                db, instrument_id=inst.id, timeframe=tf, candles=series
            )

        # BOF engine on the two primary intraday timeframes
        for tf in ENGINE_TIMEFRAMES:
            series = normalise(_aggregate(raw, tf.value))
            if len(series) < MIN_BARS_FOR_ENGINE:
                continue
            signals = bof_engine.run(instrument_id=inst.id, timeframe=tf.value, candles=series)
            stats = await persist_signals(db, signals)
            for k in ("signals_created", "signals_updated", "events_added"):
                totals[k] += stats[k]

        await _refresh_quote(db, provider, inst)
        await db.commit()

        if progress is not None:
            progress(inst.symbol, done, totals)

    logger.info("demo pipeline finished: %s", totals)
    return totals


async def _refresh_quote(
    db: AsyncSession, provider: DemoMarketDataProvider, inst: Instrument
) -> None:
    """Latest-quote row from recent base bars (feeds dashboard + heatmap)."""
    bars = normalise(await provider.get_candles(inst.symbol, "15m", 2))
    if not bars:
        return
    last = bars[-1]
    prev_close = bars[-2].close if len(bars) > 1 else None

    day_start = last.ts.replace(hour=0, minute=0, second=0, microsecond=0)
    day_count = provider.current_index() - provider.ts_to_index(day_start) + 1
    day_bars = normalise(await provider.get_candles(inst.symbol, "15m", max(day_count, 1)))

    await refresh_market_data(
        db,
        instrument_id=inst.id,
        last_close=last.close,
        previous_close=prev_close,
        day_open=day_bars[0].open if day_bars else None,
        day_high=max((b.high for b in day_bars), default=None),
        day_low=min((b.low for b in day_bars), default=None),
        volume=sum(int(b.volume or 0) for b in day_bars) or None,
        updated_at=datetime.now(timezone.utc),
    )


__all__ = ["run_pipeline", "ENGINE_TIMEFRAMES", "STORAGE_TIMEFRAMES"]
