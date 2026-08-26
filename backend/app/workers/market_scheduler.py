"""Market scheduler — keeps quotes, candles and signals fresh intraday.

Two independent loops (both gated on NSE regular hours via
``dashboard_service.market_status``):

- **Quote loop**   every ``QUOTE_REFRESH_SECONDS``: parallel batched quote
  fetch → idempotent upsert into ``market_data`` (feeds heatmap/dashboard).
- **Pipeline loop** every ``PIPELINE_REFRESH_SECONDS``: full
  ``run_pipeline(days=PIPELINE_DAYS)`` pass — candles + BOF signals +
  strategy ideas. Skipped automatically if the previous run is still going.

Zero new dependencies; same asyncio-task pattern as ``LiveLoop``.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Instrument
from app.services import signal_persistence
from app.services.dashboard_service import market_status
from app.services.providers.factory import build_verified_provider

logger = get_logger(__name__)

_BATCH_SIZE = 10       # symbols per get_quotes call / concurrent batch
_BATCH_PAUSE = 0.3     # pause between batches (seconds)


class MarketScheduler:
    def __init__(self) -> None:
        self._quote_task: asyncio.Task | None = None
        self._pipeline_task: asyncio.Task | None = None
        self._provider = None
        self._pipeline_running = False

    async def start(self) -> None:
        if not settings.MARKET_SCHEDULER_ENABLED or settings.MARKET_DATA_PROVIDER == "none":
            logger.info("market scheduler disabled")
            return

        reference = await self._load_reference()
        if not reference:
            logger.warning("market scheduler: no instruments found")
            return

        self._provider = await build_verified_provider(reference)
        self._quote_task = asyncio.create_task(self._quote_loop(), name="scheduler-quotes")
        self._pipeline_task = asyncio.create_task(self._pipeline_loop(), name="scheduler-pipeline")
        logger.info(
            "market scheduler started (provider=%s, quotes=%ss, pipeline=%ss)",
            self._provider.name, settings.QUOTE_REFRESH_SECONDS,
            settings.PIPELINE_REFRESH_SECONDS,
        )

    async def stop(self) -> None:
        for t in (self._quote_task, self._pipeline_task):
            if t:
                t.cancel()
        if hasattr(self._provider, "aclose"):
            await self._provider.aclose()
        self._quote_task = self._pipeline_task = None
        logger.info("market scheduler stopped")

    # ------------------------------------------------------------- reference

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

    async def _symbol_ids(self) -> dict[str, object]:
        """{symbol: instrument_id} for active instruments (re-read each cycle)."""
        from app.db.session import SessionFactory

        async with SessionFactory() as db:
            rows = (
                await db.execute(
                    select(Instrument.symbol, Instrument.id)
                    .where(Instrument.is_active.is_(True))
                )
            ).all()
            return {sym: iid for sym, iid in rows}

    @staticmethod
    def _market_open() -> bool:
        try:
            return market_status().status.value == "OPEN"
        except Exception:  # noqa: BLE001 — never kill the loop over a status hiccup
            return False

    # ------------------------------------------------------------ quote loop

    async def _quote_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.QUOTE_REFRESH_SECONDS)
                if not self._market_open():
                    continue
                written = await self._refresh_quotes()
                logger.info("scheduler quote refresh: %d quotes persisted", written)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("scheduler quote cycle failed")

    async def _refresh_quotes(self) -> int:
        """Fetch all active-instrument quotes in batches and persist them."""
        symbol_ids = await self._symbol_ids()
        if not symbol_ids:
            return 0

        symbols = list(symbol_ids)
        quotes: dict[str, dict] = {}
        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = symbols[i : i + _BATCH_SIZE]
            try:
                results = await self._provider.get_quotes(batch)
            except Exception as exc:  # noqa: BLE001 — one bad batch ≠ dead cycle
                logger.warning("quote batch %s failed: %s", batch[:2], exc)
                results = []
            for q in results or []:
                sym = q.get("symbol")
                if sym in symbol_ids and q.get("last_price") is not None:
                    quotes[sym] = q
            if i + _BATCH_SIZE < len(symbols):
                await asyncio.sleep(_BATCH_PAUSE)

        if not quotes:
            return 0

        now = datetime.now(timezone.utc)
        from app.db.session import SessionFactory

        async with SessionFactory() as db:
            for sym, q in quotes.items():
                await signal_persistence.refresh_market_data(
                    db,
                    instrument_id=symbol_ids[sym],
                    last_close=q.get("last_price") or 0,
                    previous_close=q.get("previous_close"),
                    day_open=q.get("day_open"),
                    day_high=q.get("day_high"),
                    day_low=q.get("day_low"),
                    volume=int(q.get("volume") or 0) or None,
                    updated_at=now,
                )
            await db.commit()
        return len(quotes)

    # --------------------------------------------------------- pipeline loop

    async def _pipeline_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.PIPELINE_REFRESH_SECONDS)
                if not self._market_open() or self._pipeline_running:
                    continue

                self._pipeline_running = True
                try:
                    from app.db.session import SessionFactory

                    async with SessionFactory() as db:
                        from app.workers.demo_pipeline import run_pipeline

                        totals = await run_pipeline(
                            db, days=settings.PIPELINE_DAYS, provider=self._provider,
                        )
                    logger.info("scheduler pipeline refresh: %s", totals)
                finally:
                    self._pipeline_running = False
            except asyncio.CancelledError:
                raise
            except Exception:
                self._pipeline_running = False
                logger.exception("scheduler pipeline cycle failed")


__all__ = ["MarketScheduler"]
