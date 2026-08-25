"""Live broadcasting loop — works with ANY provider (demo or real).

Two rhythms:
- **Ticks** every ``DEMO_TICK_SECONDS``: batch quotes broadcast to WS clients.
- **Pipeline refresh**: every ``PIPELINE_INTERVAL_SECONDS`` (default 120 s),
  ingests new candles + re-runs the BOF engine + pushes notifications.

Started from app lifespan when MARKET_DATA_PROVIDER != "none" and
LIVE_DEMO_ENABLED is true. All state is in-memory; restart resumes cleanly.
"""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.models import Instrument
from app.services.providers.factory import build_provider
from app.websocket import events
from app.websocket.manager import manager

logger = get_logger(__name__)


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

        self._provider = build_provider(reference)
        self._symbols = [r["symbol"] for r in reference]
        self._task = asyncio.create_task(self._run(), name="live-loop")
        logger.info("live loop started (%d symbols, %s provider)",
                     len(self._symbols), self._provider.name)

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
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("tick failed")

    async def tick(self) -> int:
        """Fetch current quotes and broadcast them."""
        if self._provider is None or not manager.count:
            return 0
        try:
            quotes = await self._provider.get_quotes(self._symbols)
            if quotes:
                return await manager.broadcast(events.quote_ticks_payload(quotes))
        except Exception:
            logger.exception("quote fetch failed")
        return 0


__all__ = ["LiveLoop"]
