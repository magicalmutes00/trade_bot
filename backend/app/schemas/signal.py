"""Signal schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import SignalDirection, SignalStatus, SignalStrength, Timeframe


class SignalResponse(BaseModel):
    id: uuid.UUID
    instrument_id: uuid.UUID
    symbol: str
    instrument_name: str
    timeframe: str
    direction: SignalDirection
    strength: SignalStrength
    status: SignalStatus
    bof_level: float
    breakout_price: float | None = None
    failure_price: float | None = None
    entry_price: float | None = None
    stop_reference: float | None = None
    confidence: float
    detected_at: datetime
    confirmed_at: datetime | None = None


class PaginatedSignals(BaseModel):
    items: list[SignalResponse]
    total: int
    limit: int
    offset: int


class SignalEventResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    created_at: datetime


class SignalDetail(SignalResponse):
    events: list[SignalEventResponse] = []
    metadata: dict | None = None


_ = Timeframe  # referenced for API docs symmetry
