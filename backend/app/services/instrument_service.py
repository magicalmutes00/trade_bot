"""Instrument business logic."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.models import Instrument
from app.models.enums import InstrumentType, Timeframe
from app.repositories.instrument_repository import InstrumentRepository
from app.schemas.instrument import (
    CandleResponse,
    InstrumentDetail,
    InstrumentListItem,
    PaginatedCandles,
    PaginatedInstruments,
    QuoteResponse,
    SignalStats,
)
from app.services.providers.nse_provider import NseIndiaProvider
from app.services.signal_persistence import store_candles
from app.workers.candle_processing import normalise

logger = logging.getLogger(__name__)


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

    # Max age of a candle before we force-refresh from NSE.
    # Guards against stale/mixed DB data (e.g. RELIANCE candles inserted under
    # AXISBANK instrument_id) that would otherwise render on the chart.
    _MAX_CANDLE_AGE_DAYS = 7

    async def get_candles(
        self,
        *,
        instrument_id: uuid.UUID,
        timeframe: Timeframe,
        limit: int,
        before: datetime | None,
    ) -> PaginatedCandles:
        instrument = await self.repo.get(instrument_id)
        if instrument is None:
            raise NotFoundError("Instrument not found")

        # Primary: DB candles
        rows = await self.repo.candles(
            instrument_id=instrument_id, timeframe=timeframe, limit=limit + 1, before=before
        )

        # Freshness gate: if the newest DB candle is older than _MAX_CANDLE_AGE_DAYS,
        # discard it and pull live from the stock-nse-india sidecar instead.
        # Guards against stale DB data AND against contaminated rows (wrong
        # prices inserted under the correct instrument_id).
        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=self._MAX_CANDLE_AGE_DAYS)
        db_stale = bool(rows) and rows[0].ts.replace(tzinfo=timezone.utc) < cutoff

        if rows and not db_stale:
            candles = list(rows[: limit + 1])
        elif settings.NSE_PROVIDER_URL:
            candles = await self._fetch_nse_candles(instrument, timeframe, limit)
        else:
            candles = list(rows[: limit + 1])

        items = [
            CandleResponse(
                timeframe=timeframe,
                ts=c.ts,
                open=round(float(c.open), 2),
                high=round(float(c.high), 2),
                low=round(float(c.low), 2),
                close=round(float(c.close), 2),
                volume=int(c.volume or 0),
            )
            for c in candles
        ]
        items = _median_guard(items)

        has_more = len(items) > limit
        items = items[:limit]
        return PaginatedCandles(
            items=items,
            timeframe=timeframe,
            limit=limit,
            has_more=has_more,
        )

    async def _fetch_nse_candles(
        self, instrument: Instrument, timeframe: Timeframe, limit: int
    ) -> list:
        """Live fetch from the stock-nse-india sidecar.

        Whatever comes back is persisted (idempotent upserts) before it is
        served, so live NSE candles accumulate in the DB instead of being
        re-fetched on every request.
        """
        symbol = instrument.symbol
        provider = NseIndiaProvider(settings.NSE_PROVIDER_URL)
        try:
            raw = await provider.get_candles(symbol, timeframe.value, limit)
        finally:
            await provider.aclose()

        candles = normalise(raw)
        if not candles:
            logger.warning("NSE live fetch returned no candles for %s %s", symbol, timeframe.value)
            return []

        try:
            written = await store_candles(
                self.db, instrument_id=instrument.id, timeframe=timeframe, candles=candles
            )
            await self.db.commit()
            logger.info(
                "NSE live fetch for %s %s: %d candles served, %d stored",
                symbol, timeframe.value, len(candles), written,
            )
        except Exception as exc:  # noqa: BLE001 — serving matters more than storing
            logger.warning("NSE candle persistence failed for %s: %s", symbol, exc)
        return candles


def _median_guard(items: list[CandleResponse]) -> list[CandleResponse]:
    """Drop items whose mid price is wildly outside the returned series'
    median (protects against symbol-mix contamination). Kept only when at
    least two rows survive, mirroring the DB-path behaviour."""
    if not items:
        return items
    mids = sorted((i.open + i.close) / 2.0 for i in items)
    median = mids[len(mids) // 2]
    if median <= 0:
        return items
    clean = [
        i for i in items
        if median / 2 <= (i.open + i.close) / 2.0 <= median * 2
    ]
    return clean if len(clean) >= 2 else items


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
