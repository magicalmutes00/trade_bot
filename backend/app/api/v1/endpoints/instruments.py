"""Instrument endpoints: list, detail, candles, signal history."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.models.enums import SignalDirection, SignalStatus
from app.models.enums import Timeframe
from app.repositories.signal_repository import SignalRepository
from app.schemas.common import ApiResponse, ok
from app.schemas.instrument import (
    InstrumentDetail,
    PaginatedCandles,
    PaginatedInstruments,
)
from app.schemas.signal import PaginatedSignals, SignalResponse
from app.services.instrument_service import (
    InstrumentService,
    parse_timeframe,
    parse_uuid,
)

router = APIRouter(prefix="/instruments", tags=["instruments"])


@router.get(
    "",
    response_model=ApiResponse[PaginatedInstruments],
    summary="Search instruments (public)",
    description=(
        "Reference data for the scanner. Filters: `q` (symbol/name contains), "
        "`type` (STOCK|INDEX|COMMODITY|FOREX|CRYPTO), `sector_id`, `exchange`. "
        "Sorts: `symbol`, `name`, `change_pct`, `volume` "
        "(signal-based sorts arrive with live signal aggregation)."
    ),
)
async def list_instruments(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=64)] = None,
    type: Annotated[str | None, Query()] = None,
    sector_id: str | None = None,
    exchange: str | None = Query(default=None, max_length=32),
    sort: str = "symbol",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaginatedInstruments]:
    parsed_sector = parse_uuid(sector_id, "sector_id") if sector_id else None
    result = await InstrumentService(db).list_instruments(
        q=q,
        instrument_type=type,
        sector_id=parsed_sector,
        exchange=exchange,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return ok(result)


def _signal_to_response(signal, instrument) -> SignalResponse:  # noqa: ANN001
    from app.schemas.signal import SignalResponse as R

    return R(
        id=signal.id,
        instrument_id=signal.instrument_id,
        symbol=instrument.symbol,
        instrument_name=instrument.name,
        timeframe=signal.timeframe.value if hasattr(signal.timeframe, "value") else str(signal.timeframe),
        direction=signal.direction,
        strength=signal.strength,
        status=signal.status,
        bof_level=float(signal.bof_level),
        breakout_price=float(signal.breakout_price) if signal.breakout_price is not None else None,
        failure_price=float(signal.failure_price) if signal.failure_price is not None else None,
        entry_price=float(signal.entry_price) if signal.entry_price is not None else None,
        stop_reference=float(signal.stop_reference) if signal.stop_reference is not None else None,
        confidence=float(signal.confidence),
        detected_at=signal.detected_at,
        confirmed_at=signal.confirmed_at,
    )


@router.get(
    "/{instrument_id}",
    response_model=ApiResponse[InstrumentDetail],
    summary="Instrument detail incl. latest quote (null until provider data) and signal stats",
)
async def get_instrument(instrument_id: str, db: DbSession) -> ApiResponse[InstrumentDetail]:
    result = await InstrumentService(db).get_detail(parse_uuid(instrument_id, "instrument_id"))
    return ok(result)


@router.get(
    "/{instrument_id}/signal-stats",
    response_model=ApiResponse,
    summary="Detailed signal statistics (counts, rates, breakdowns)",
)
async def get_signal_stats(instrument_id: str, db: DbSession):
    from app.schemas.heatmap_watchlist import SignalStatsDetailed
    from app.services.signal_stats_service import SignalStatsService

    data = await SignalStatsService(db).detailed(
        parse_uuid(instrument_id, "instrument_id")
    )
    return ok(SignalStatsDetailed.model_validate(data))


@router.get(
    "/{instrument_id}/candles",
    response_model=ApiResponse[PaginatedCandles],
    summary="OHLCV candles for the instrument",
)
async def get_candles(
    instrument_id: str,
    db: DbSession,
    timeframe: str = Query(default="15m"),
    limit: int = Query(default=500, ge=1, le=1000),
    before: datetime | None = None,
) -> ApiResponse[PaginatedCandles]:
    result = await InstrumentService(db).get_candles(
        instrument_id=parse_uuid(instrument_id, "instrument_id"),
        timeframe=parse_timeframe(timeframe),
        limit=limit,
        before=before,
    )
    return ok(result)


@router.get(
    "/{instrument_id}/signals",
    response_model=ApiResponse[PaginatedSignals],
    summary="Signal history for one instrument (public)",
)
async def get_instrument_signals(
    instrument_id: str,
    db: DbSession,
    direction: Annotated[SignalDirection | None, Query()] = None,
    status: Annotated[SignalStatus | None, Query()] = None,
    sort: str = Query(default="detected_at", pattern="^(detected_at|confidence)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaginatedSignals]:
    iid = parse_uuid(instrument_id, "instrument_id")
    rows, total = await SignalRepository(db).list(
        instrument_id=iid, direction=direction, status=status,
        sort=sort, limit=limit, offset=offset,
    )
    items = [_signal_to_response(s, i) for s, i in rows]
    return ok(PaginatedSignals(items=items, total=total, limit=limit, offset=offset))
