"""Instrument business logic."""

import logging
import os
import uuid
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models import Instrument
from app.models.enums import InstrumentType, Timeframe
from app.repositories.instrument_repository import InstrumentRepository
from app.schemas.common import ok  # noqa: F401 (kept for parity)
from app.schemas.instrument import (
    CandleResponse,
    InstrumentDetail,
    InstrumentListItem,
    PaginatedCandles,
    PaginatedInstruments,
    QuoteResponse,
    SignalStats,
)

logger = logging.getLogger(__name__)

NSE_PROVIDER_URL = os.environ.get("NSE_PROVIDER_URL", "").rstrip("/")


class InstrumentService:
    ALLOWED_SORTS = {"symbol", "name", "change_pct", "volume"}

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = InstrumentRepository(db)

    async def list_instruments(
        self,
        *,
        q: str | None,
        instrument_type: str | None,
        sector_id: uuid.UUID | None,
        exchange: str | None,
        sort: str,
        limit: int,
        offset: int,
    ) -> PaginatedInstruments:
        if sort not in self.ALLOWED_SORTS:
            raise ValidationError(
                f"Unsupported sort '{sort}'. Allowed: {', '.join(sorted(self.ALLOWED_SORTS))}"
            )
        parsed_type: InstrumentType | None = None
        if instrument_type:
            try:
                parsed_type = InstrumentType(instrument_type.upper())
            except ValueError as exc:
                raise ValidationError(f"Unknown instrument type '{instrument_type}'") from exc

        rows, total = await self.repo.list(
            q=q,
            instrument_type=parsed_type,
            sector_id=sector_id,
            exchange=exchange,
            sort=sort,
            limit=limit,
            offset=offset,
        )
        items = [
            InstrumentListItem(
                id=r.id,
                symbol=r.symbol,
                name=r.name,
                instrument_type=r.instrument_type,
                exchange=r.exchange,
                currency=r.currency,
                sector_name=r.sector.name if r.sector else None,
            )
            for r in rows
        ]
        return PaginatedInstruments(items=items, total=total, limit=limit, offset=offset)

    async def get_detail(self, instrument_id: uuid.UUID) -> InstrumentDetail:
        instrument = await self.repo.get(instrument_id)
        if instrument is None:
            raise NotFoundError("Instrument not found")
        stats = await self.repo.signal_stats(instrument.id)
        return InstrumentDetail(
            id=instrument.id,
            symbol=instrument.symbol,
            name=instrument.name,
            instrument_type=instrument.instrument_type,
            exchange=instrument.exchange,
            currency=instrument.currency,
            sector_name=instrument.sector.name if instrument.sector else None,
            tick_size=instrument.tick_size,
            lot_size=instrument.lot_size,
            is_active=instrument.is_active,
            quote=(
                QuoteResponse.model_validate(instrument.market_data)
                if instrument.market_data
                else None
            ),
            stats=SignalStats(**stats),
        )

    async def get_candles(
        self,
        *,
        instrument_id: uuid.UUID,
        timeframe: Timeframe,
        limit: int,
        before: datetime | None,
    ) -> PaginatedCandles:
        if await self.repo.get(instrument_id) is None:
            raise NotFoundError("Instrument not found")

        # Primary: DB candles
        rows = await self.repo.candles(
            instrument_id=instrument_id, timeframe=timeframe, limit=limit + 1, before=before
        )

        # Fallback to NSE provider when DB has no candles (backend 500 / empty feed)
        if not rows and NSE_PROVIDER_URL:
            try:
                instrument = await self.repo.get(instrument_id)
                symbol = instrument.symbol if instrument else "RELIANCE"
                # Map timeframe to NSE interval
                interval = "1minute" if timeframe == Timeframe.MINUTE_1 else \
                           "5minute" if timeframe == Timeframe.MINUTE_5 else \
                           "15minute" if timeframe == Timeframe.MINUTE_15 else \
                           "30minute" if timeframe == Timeframe.MINUTE_30 else \
                           "1hour" if timeframe in (Timeframe.HOUR_1, Timeframe.HOUR_4) else "1day"
                url = (
                    f"{NSE_PROVIDER_URL}/api/charts/equity-historical-data"
                    f"?symbol={symbol}&start=2024-01-01&end=2025-12-31&timeInterval={interval}"
                )
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        data = resp.json()
                        # NSE returns {time: ms, open, high, low, close, volume}
                        # Convert to CandleResponse format
                        nse_items = data if isinstance(data, list) else data.get("data", [])
                        if not nse_items and isinstance(data, dict) and "time" in data:
                            nse_items = [data]
                        rows = []
                        for item in nse_items[-limit:]:
                            # time in ms from NSE; convert to datetime
                            ts = datetime.fromtimestamp(int(item.get("time", 0)) / 1000)
                            # Create a mock candle object that CandleResponse can use
                            class MockCandle:
                                pass
                            c = MockCandle()
                            c.timeframe = timeframe
                            c.ts = ts
                            c.open = float(item.get("open", 0))
                            c.high = float(item.get("high", 0))
                            c.low = float(item.get("low", 0))
                            c.close = float(item.get("close", 0))
                            c.volume = int(item.get("volume", 0) or 0)
                            rows.append(c)
                        logger.info("NSE provider returned %d candles for %s / %s", len(rows), symbol, timeframe)
            except Exception as exc:
                logger.warning("NSE provider fallback failed: %s", exc)

        has_more = len(rows) > limit
        rows = rows[:limit]
        items = [
            CandleResponse(
                timeframe=c.timeframe,
                ts=c.ts,
                open=round(float(c.open), 2),
                high=round(float(c.high), 2),
                low=round(float(c.low), 2),
                close=round(float(c.close), 2),
                volume=int(c.volume or 0),
            )
            for c in rows
        ]
        return PaginatedCandles(
            items=items,
            timeframe=timeframe,
            limit=limit,
            has_more=has_more,
        )


def parse_timeframe(value: str) -> Timeframe:
    try:
        return Timeframe(value)
    except ValueError as exc:
        raise ValidationError(
            f"Unknown timeframe '{value}'. Allowed: {', '.join(t.value for t in Timeframe)}"
        ) from exc


def parse_uuid(value: str, field: str = "identifier") -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError(f"Invalid {field}") from exc
