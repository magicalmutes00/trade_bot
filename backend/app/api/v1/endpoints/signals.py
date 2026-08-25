"""Signal endpoints."""

import math
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.models.enums import SignalDirection, SignalStatus, SignalStrength, Timeframe
from app.repositories.signal_repository import SignalRepository
from app.schemas.common import ApiResponse, ok
from app.services.instrument_service import parse_timeframe, parse_uuid  # validators
from app.schemas.signal import (
    PaginatedSignals,
    SignalDetail,
    SignalEventResponse,
    SignalResponse,
)

router = APIRouter(prefix="/signals", tags=["signals"])


def _to_response(signal, instrument) -> SignalResponse:  # noqa: ANN001
    return SignalResponse(
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
    "",
    response_model=ApiResponse[PaginatedSignals],
    summary="Query BOF signals (public)",
)
async def list_signals(
    db: DbSession,
    instrument_id: str | None = None,
    direction: Annotated[SignalDirection | None, Query()] = None,
    status: Annotated[SignalStatus | None, Query()] = None,
    strength: Annotated[SignalStrength | None, Query()] = None,
    min_confidence: Annotated[float | None, Query(ge=0, le=1)] = None,
    timeframe: str | None = None,
    detected_from: datetime | None = None,
    detected_to: datetime | None = None,
    sort: str = Query(default="detected_at", pattern="^(detected_at|confidence)$"),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaginatedSignals]:
    rows, total = await SignalRepository(db).list(
        instrument_id=parse_uuid(instrument_id, "instrument_id") if instrument_id else None,
        direction=direction,
        status=status,
        strength=strength,
        min_confidence=min_confidence,
        timeframe=parse_timeframe(timeframe) if timeframe else None,
        detected_from=detected_from,
        detected_to=detected_to,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items = [_to_response(s, i) for s, i in rows]
    return ok(PaginatedSignals(items=items, total=total, limit=limit, offset=offset))


@router.get(
    "/{signal_id}",
    response_model=ApiResponse[SignalDetail],
    summary="Signal detail incl. lifecycle event trail",
)
async def get_signal(signal_id: str, db: DbSession) -> ApiResponse[SignalDetail]:
    signal, instrument, events = await SignalRepository(db).get_with_events(
        parse_uuid(signal_id, "signal_id")
    )
    detail = SignalDetail(
        **_to_response(signal, instrument).model_dump(),
        events=[SignalEventResponse(id=e.id, event_type=e.event_type, created_at=e.created_at)
                for e in events],
        metadata=signal.signal_metadata,
    )
    return ok(detail)

