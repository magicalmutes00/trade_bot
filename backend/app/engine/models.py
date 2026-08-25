"""Engine-internal value objects (decoupled from ORM models on purpose)."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.engine.config import BOFConfig, DEFAULT_CONFIG


class Side(str, Enum):
    UP = "UP"      # breakout above resistance → bearish BOF when it fails
    DOWN = "DOWN"  # breakdown below support  → bullish BOF when it fails


@dataclass(frozen=True)
class EngineCandle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Pivot:
    ts: datetime
    index: int          # index into the candle series at confirmation time
    price: float
    side: Side          # UP = swing high (resistance), DOWN = swing low (support)


@dataclass
class BreakoutCandidate:
    side: Side
    level: float
    level_ts: datetime
    breakout_index: int
    breakout_ts: datetime
    breakout_close: float
    max_excursion: float = 0.0   # furthest adverse distance beyond the level (abs)

    def excursion_bars(self, current_index: int) -> int:
        return current_index - self.breakout_index


@dataclass(frozen=True)
class EngineSignal:
    """Final output — maps 1:1 onto the `signals` table."""

    instrument_id: uuid.UUID
    timeframe: str
    direction: str                      # BULLISH | BEARISH
    bof_level: float
    breakout_price: float
    failure_price: float | None
    entry_price: float | None
    stop_reference: float | None
    confidence: float                   # 0..1
    strength: str                       # WEAK..VERY_STRONG
    status: str                         # DETECTING | CONFIRMED | INVALIDATED
    detected_at: datetime               # breakout bar timestamp (idempotency key)
    confirmed_at: datetime | None
    metadata: dict = field(default_factory=dict)


def strength_from_score(score: float, cfg: BOFConfig = DEFAULT_CONFIG) -> str:
    if score < cfg.weak_below:
        return "WEAK"
    if score < cfg.moderate_below:
        return "MODERATE"
    if score < cfg.strong_below:
        return "STRONG"
    return "VERY_STRONG"
