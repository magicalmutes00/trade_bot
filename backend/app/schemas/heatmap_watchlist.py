"""Heatmap + watchlist schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# --------------------------------------------------------------------- heatmap

class HeatmapCell(BaseModel):
    instrument_id: uuid.UUID
    symbol: str
    name: str
    instrument_type: str
    sector_name: str | None = None
    last_price: float | None = None
    change_pct: float | None = None
    bof_direction: str | None = None
    bof_strength: str | None = None
    bof_status: str | None = None
    bof_timeframe: str | None = None


class HeatmapGroup(BaseModel):
    key: str
    label: str
    cells: list[HeatmapCell]


class HeatmapResponse(BaseModel):
    group_by: str
    groups: list[HeatmapGroup]
    total_cells: int
    updated_at: datetime


# ------------------------------------------------------------------ watchlists

class WatchlistCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class WatchlistRenameRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)


class WatchlistItemAddRequest(BaseModel):
    instrument_id: uuid.UUID
    alert_enabled: bool = False


class WatchlistItemUpdateRequest(BaseModel):
    alert_enabled: bool | None = None
    position: int | None = Field(default=None, ge=0, le=10_000)


class WatchlistItemResponse(BaseModel):
    instrument_id: uuid.UUID
    symbol: str
    name: str
    instrument_type: str
    sector_name: str | None = None
    position: int
    alert_enabled: bool
    last_price: float | None = None
    change_pct: float | None = None
    bof_direction: str | None = None
    bof_strength: str | None = None
    bof_status: str | None = None


class WatchlistResponse(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    items: list[WatchlistItemResponse]


# ------------------------------------------------------------- signal stats

class StrengthCount(BaseModel):
    strength: str
    count: int


class TimeframeCount(BaseModel):
    timeframe: str
    count: int


class SignalStatsDetailed(BaseModel):
    total_signals: int = 0
    bullish: int = 0
    bearish: int = 0
    confirmed: int = 0
    invalidated: int = 0
    detecting: int = 0
    closed: int = 0
    avg_confidence: float | None = None
    confirmation_rate: float | None = None
    by_strength: list[StrengthCount] = []
    by_timeframe: list[TimeframeCount] = []
