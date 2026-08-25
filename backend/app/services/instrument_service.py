"""Instrument business logic."""

import uuid
from datetime import datetime

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
        rows = await self.repo.candles(
            instrument_id=instrument_id, timeframe=timeframe, limit=limit + 1, before=before
        )
        has_more = len(rows) > limit
        rows = rows[:limit]
        return PaginatedCandles(
            items=[CandleResponse.model_validate(c) for c in rows],
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
