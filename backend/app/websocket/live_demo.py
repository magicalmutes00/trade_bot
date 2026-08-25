"""Live demo broadcasting loop.

Two rhythms:
- **Ticks** every ``DEMO_TICK_SECONDS``: interpolated live quotes for all
  instruments (derived from the deterministic demo path — still DEMO data).
- **Bar closes**: when the 15-minute grid advances, persist new candles,
  re-run the BOF engine incrementally, broadcast fresh CONFIRMED signals and
  market-status flips.

Started from app lifespan when MARKET_DATA_PROVIDER == "demo" and
LIVE_DEMO_ENABLED is true. All state is in-memory; a restart simply resumes.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Instrument
from app.services.providers.demo_provider import BASE_INTERVAL, DemoMarketDataProvider
from app.websocket import events
from app.websocket.manager import manager
from app.workers.candle_processing import normalise
from app.workers.demo_pipeline import run_pipeline

logger = get_logger(__name__)


class LiveDemoLoop:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._provider: DemoMarketDataProvider | None = None
        self._symbols: list[str] = []
        self._last_index: int | None = None
        self._last_status: str | None = None
        self._bar_task: asyncio.Task | None = None

    # ------------------------------------------------------------- lifecycle

    async def start(self) -> None:
        if settings.MARKET_DATA_PROVIDER != "demo" or not getattr(
            settings, "LIVE_DEMO_ENABLED", True
        ):
            logger.info("live demo loop disabled (provider=%s)", settings.MARKET_DATA_PROVIDER)
            return

        reference = await self._load_reference()
        if not reference:
            logger.warning("live demo loop found no instruments — run seed-instruments")
            return

        self._provider = DemoMarketDataProvider(reference)
        self._symbols = [r["symbol"] for r in reference]
        self._last_index = self._provider.current_index()

        self._task = asyncio.create_task(self._run(), name="live-demo-loop")
        logger.info("live demo loop started (%d symbols, tick=%ss)",
                    len(self._symbols), settings.DEMO_TICK_SECONDS)

    async def stop(self) -> None:
        for task in (self._task, self._bar_task):
            if task is not None:
                task.cancel()
        self._task = None
        self._bar_task = None
        logger.info("live demo loop stopped")

    async def _load_reference(self) -> list[dict]:
        from app.db.session import SessionFactory

        async with SessionFactory() as db:
            rows = (
                await db.execute(select(Instrument).where(Instrument.is_active.is_(True)))
            ).scalars().all()
            return [
                {"symbol": i.symbol, "exchange": i.exchange, "name": i.name,
                 "instrument_type": i.instrument_type.value}
                for i in rows
            ]

    # ------------------------------------------------------------------ loop

    async def _run(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.DEMO_TICK_SECONDS)
                await self.tick()
                await self._maybe_process_bar()
            except asyncio.CancelledError:
                raise
            except Exception:  # never let the loop die silently
                logger.exception("live tick iteration failed")

    # ------------------------------------------------------------------ ticks

    async def tick(self) -> int:
        if self._provider is None:
            return 0
        quotes = await self._interpolated_quotes()
        sent = await manager.broadcast(events.quote_ticks_payload(quotes))
        return sent

    async def _interpolated_quotes(self) -> list[dict]:
        """Intrabar price estimate between consecutive path closes (DEMO)."""
        provider = self._provider
        now = datetime.now(timezone.utc)
        idx = provider.current_index()
        frac = min(max((now - provider.index_to_ts(idx)) / BASE_INTERVAL, 0.0), 1.0)

        quotes: list[dict] = []
        for symbol in self._symbols:
            series = provider._close_series(symbol, idx - 1, idx)
            prev_close = series.get(idx - 1)
            cur_close = series.get(idx)
            if prev_close is None or cur_close is None:
                continue

            smooth = frac * frac * (3 - 2 * frac)  # smoothstep
            last_price = round(prev_close + (cur_close - prev_close) * smooth, 4)

            day_ref = prev_close  # demo change baseline: previous bar close
            change_pct = ((last_price - day_ref) / day_ref * 100) if day_ref else None
            direction = ("UP" if change_pct > 0 else "DOWN" if change_pct < 0 else "FLAT") \
                if change_pct is not None else None

            quotes.append({
                "symbol": symbol,
                "last_price": last_price,
                "change_pct": round(change_pct, 4) if change_pct is not None else None,
                "direction": direction,
                "is_demo": True,
                "ts": now.isoformat(),
            })
        return quotes

    # ------------------------------------------------------------ bar closing

    async def _maybe_process_bar(self) -> None:
        if self._provider is None or self._bar_task is not None and not self._bar_task.done():
            return

        current = self._provider.current_index()
        if self._last_index is not None and current <= self._last_index:
            await self._broadcast_status_if_changed()
            return

        crossed_to = current
        previous = self._last_index if self._last_index is not None else current - 1
        self._last_index = current
        self._bar_task = asyncio.create_task(
            self._process_bar(previous, crossed_to), name="bar-close-processing"
        )

    async def _process_bar(self, previous_index: int, current_index: int) -> None:
        bar_ts = self._provider.index_to_ts(current_index)
        logger.info("bar close detected (index=%s ts=%s) — incremental pipeline",
                    current_index, bar_ts.isoformat())
        try:
            await run_pipeline(days=3)  # small window; upserts are idempotent
        except Exception:
            logger.exception("incremental bar processing failed")
            return

        await self._broadcast_new_signals(since=bar_ts - BASE_INTERVAL)
        await self._broadcast_status_if_changed(force=True)

    async def _broadcast_new_signals(self, *, since: datetime) -> None:
        from app.db.session import SessionFactory

        async with SessionFactory() as db:
            rows = (
                await db.execute(_new_confirmed_query(since))
            ).all()
        cards = [_signal_card(r[0], r[1]) for r in rows]
        if cards:
            await manager.broadcast(events.signals_payload(cards[:20]))

        # Phase 6 — preference-driven push fan-out (best-effort, never fatal)
        if rows:
            try:
                async with SessionFactory() as db:
                    from app.services.notification_service import NotificationDispatcher

                    dispatcher = NotificationDispatcher(db)
                    for signal, instrument in rows[:20]:
                        try:
                            await dispatcher.notify_new_signal(signal, instrument)
                        except Exception:
                            logger.exception("push for %s failed", instrument.symbol)
                    await db.commit()
            except Exception:
                logger.exception("push dispatch failed")

    async def _broadcast_status_if_changed(self, *, force: bool = False) -> None:
        from app.services.dashboard_service import market_status

        status = market_status()
        if force or self._last_status != status.status.value:
            self._last_status = status.status.value
            await manager.broadcast(
                events.market_status_payload(status.market.value, status.status.value)
            )


def _new_confirmed_query(since: datetime):
    """Newest CONFIRMED signals since `since`, joined with instrument."""
    from app.models import Signal, SignalStatus

    return (
        select(Signal, Instrument)
        .join(Instrument, Instrument.id == Signal.instrument_id)
        .where(Signal.status == SignalStatus.CONFIRMED, Signal.detected_at >= since)
        .order_by(Signal.detected_at.desc())
        .limit(50)
    )


def _signal_card(signal, instrument) -> dict:  # noqa: ANN001
    return {
        "id": str(signal.id),
        "instrument_id": str(instrument.id),
        "symbol": instrument.symbol,
        "direction": signal.direction.value if hasattr(signal.direction, "value") else signal.direction,
        "strength": signal.strength.value if hasattr(signal.strength, "value") else signal.strength,
        "status": signal.status.value if hasattr(signal.status, "value") else signal.status,
        "bof_level": float(signal.bof_level),
        "confidence": float(signal.confidence),
        "timeframe": signal.timeframe.value if hasattr(signal.timeframe, "value") else signal.timeframe,
        "detected_at": signal.detected_at.isoformat(),
    }


__all__ = ["LiveDemoLoop"]
