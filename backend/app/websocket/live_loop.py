"""Live broadcasting loop — parallel quote fetching + WS broadcast.

Fetches all instrument quotes in PARALLEL batches (not sequential) and
broadcasts the batch to every WebSocket client. With Yahoo Finance this
completes in ~3-5 seconds for 50 instruments instead of 30+.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Instrument
from app.services.providers.factory import build_verified_provider
from app.websocket import events
from app.websocket.manager import manager

logger = get_logger(__name__)

_BATCH_SIZE = 10       # concurrent requests per batch
_BATCH_PAUSE = 0.3     # pause between batches (seconds)


class LiveLoop:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._provider = None
        self._symbols: list[str] = []
        self._last_status: str | None = None

    async def start(self) -> None:
        if settings.MARKET_DATA_PROVIDER == "none" or not getattr(
            settings, "LIVE_DEMO_ENABLED", True
        ):
            logger.info("live loop disabled")
            return

        reference = await self._load_reference()
        if not reference:
            logger.warning("live loop: no instruments found")
            return

        self._provider = await build_verified_provider(reference)
        self._symbols = [r["symbol"] for r in reference]
        self._task = asyncio.create_task(self._run(), name="live-loop")
        logger.info("live loop started (%d symbols, %s, tick=%ss)",
                     len(self._symbols), self._provider.name,
                     settings.DEMO_TICK_SECONDS)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
        if hasattr(self._provider, "aclose"):
            await self._provider.aclose()
        self._task = None
        logger.info("live loop stopped")

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
                sent = await self.tick()
                if sent:
                    logger.debug("broadcast %d quotes to %d clients", sent, manager.count)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("tick failed")

    async def tick(self) -> int:
        """Parallel quote fetch → broadcast."""
        if self._provider is None or not manager.count:
            return 0
        try:
            quotes = await self._fetch_all_quotes(self._symbols)
            if quotes:
                return await manager.broadcast(events.quote_ticks_payload(quotes))
        except Exception:
            logger.exception("tick broadcast failed")
        return 0

    async def _fetch_all_quotes(self, symbols: list[str]) -> list[dict]:
        """Fetch quotes in parallel batches of _BATCH_SIZE."""
        all_quotes: list[dict] = []

        for i in range(0, len(symbols), _BATCH_SIZE):
            batch = symbols[i : i + _BATCH_SIZE]
            tasks = [self._provider.get_quote(s) for s in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, dict) and r.get("last_price") is not None:
                    all_quotes.append(r)

            # brief pause between batches to be polite
            if i + _BATCH_SIZE < len(symbols):
                await asyncio.sleep(_BATCH_PAUSE)

        return all_quotes


__all__ = ["LiveLoop"]
