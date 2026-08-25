"""Instrument schemas."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import InstrumentType, Timeframe


class QuoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    instrument_id: uuid.UUID
    last_price: Decimal
    previous_close: Decimal | None = None
    change: Decimal | None = None
    change_pct: Decimal | None = None
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    volume: int | None = None
    updated_at: datetime


class SignalStats(BaseModel):
    total_signals: int = 0
    bullish: int = 0
    bearish: int = 0
    confirmed: int = 0
    invalidated: int = 0


class InstrumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    symbol: str
    name: str
    instrument_type: InstrumentType
    exchange: str
    currency: str
    sector_name: str | None = None


class PaginatedInstruments(BaseModel):
    items: list[InstrumentListItem]
    total: int
    limit: int
    offset: int


class CandleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timeframe: Timeframe
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None = None


class PaginatedCandles(BaseModel):
    items: list[CandleResponse]
    timeframe: Timeframe
    limit: int
    has_more: bool = False


class InstrumentDetail(InstrumentListItem):
    tick_size: Decimal | None = None
    lot_size: int | None = None
    is_active: bool = True
    quote: QuoteResponse | None = None
    stats: SignalStats = SignalStats()
