"""Admin schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import InstrumentType, LogLevel, MarketName, SessionStatus


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    signals_today: int
    total_signals: int
    confirmed_signals: int
    invalidated_signals: int
    active_instruments: int
    database: str
    ws_connections: int
    provider: str
    environment: str


class AdminUserRow(BaseModel):
    id: uuid.UUID
    email: str
    username: str | None
    display_name: str | None
    role: str
    auth_provider: str
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class PaginatedAdminUsers(BaseModel):
    items: list[AdminUserRow]
    total: int
    limit: int
    offset: int


class AdminUserUpdateRequest(BaseModel):
    is_active: bool | None = None
    role: str | None = None  # USER | ADMIN (validated)


class AdminInstrumentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    instrument_type: InstrumentType | None = None
    sector_id: uuid.UUID | None = None
    is_active: bool | None = None


class AdminMarketDataCoverage(BaseModel):
    id: uuid.UUID
    symbol: str
    exchange: str
    is_active: bool = True
    m15_candles: int
    last_m15_ts: datetime | None = None
    quote_updated_at: datetime | None = None


class PaginatedCoverage(BaseModel):
    items: list[AdminMarketDataCoverage]
    total: int
    limit: int
    offset: int


class MarketSessionCreateRequest(BaseModel):
    session_date: str  # ISO date
    market: MarketName = MarketName.NSE
    status: SessionStatus
    note: str | None = Field(default=None, max_length=255)


class SystemEventRow(BaseModel):
    id: uuid.UUID
    level: LogLevel
    source: str
    message: str
    created_at: datetime


class PaginatedSystemEvents(BaseModel):
    items: list[SystemEventRow]
    total: int
    limit: int
    offset: int


class AdminHealth(BaseModel):
    status: str
    database_latency_ms: float | None = None
    ws_connections: int
    provider: str
    live_loop_enabled: bool
    version: str
