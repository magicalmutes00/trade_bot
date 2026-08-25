"""Dashboard schemas."""

from datetime import datetime

from pydantic import BaseModel

from app.models.enums import MarketName, SessionStatus, SignalDirection, SignalStrength


class MarketStatus(BaseModel):
    market: MarketName = MarketName.NSE
    status: SessionStatus
    as_of: datetime
    note: str | None = None


class QuoteCard(BaseModel):
    """Compact quote for dashboard index cards."""

    instrument_id: str
    symbol: str
    name: str
    last_price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    direction: str | None = None  # UP | DOWN | FLAT | null (no data)
    updated_at: datetime | None = None


class BofSummary(BaseModel):
    active_total: int = 0
    bullish: int = 0
    bearish: int = 0
    strong: int = 0
    new_today: int = 0
    detected_today: int = 0


class SignalCard(BaseModel):
    """Compact signal representation shared by dashboard sections."""

    id: str
    instrument_id: str
    symbol: str
    instrument_name: str
    direction: SignalDirection
    strength: SignalStrength
    bof_level: float
    price: float | None = None
    timeframe: str
    detected_at: datetime


class DashboardResponse(BaseModel):
    market_status: MarketStatus
    indices: list[QuoteCard]
    bof_summary: BofSummary
    latest_signals: list[SignalCard]
    strongest_signals: list[SignalCard]
