"""Pattern analysis schemas (TRADEBOT spec §35 output shape)."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class PatternResponse(BaseModel):
    """Per-timeframe pattern state — mirrors spec §35's JSON exactly for the
    fields the engine produces (prices are strings so the method annotation
    like 'measured height' is preserved)."""

    timeframe: str
    pattern_detected: str = "None"        # "DOUBLE_TOP" | "Forming - DOUBLE_TOP" | "None"
    status: str = "Forming"               # FULLY_FORMED | FORMING | INVALIDATED
    direction: str = "Neutral"            # BULLISH | BEARISH | NEUTRAL
    confidence: float = 0.0
    entry: str = "N/A"
    stop_loss: str = "N/A"
    target_1: str = "N/A"
    target_2: str = "N/A"
    target_3: str = "N/A"
    invalidation: str = "N/A"
    additional_notes: str = ""
    reasoning: str = ""
    # machine-readable extras for chart markers / the mobile engine
    neckline_price: float | None = None
    peak_price: float | None = None
    swing_indices: list[int] = []
    confirm_index: int | None = None
    detected_at: datetime | None = None


class InstrumentPatterns(BaseModel):
    """Pattern state across the scanned timeframes for one instrument."""

    instrument_id: uuid.UUID
    symbol: str
    name: str
    scanned_at: datetime
    timeframes: list[PatternResponse]