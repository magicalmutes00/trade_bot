"""Shared types for pattern detection to avoid circular imports."""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.engine.models import EngineCandle
from app.engine.swings import Swing


class PatternStatus(str, Enum):
    FORMING = "FORMING"           # structure developing, confirmation pending
    FULLY_FORMED = "FULLY_FORMED" # mandatory structure + confirmation satisfied
    INVALIDATED = "INVALIDATED"   # an explicit invalidation condition occurred


class PatternDirection(str, Enum):
    BULLISH = "BULLISH"           # double bottom, inverse H&S, …
    BEARISH = "BEARISH"           # double top, H&S, …
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class PatternHit:
    """A single pattern hit with geometry + trade plan + invalidation."""
    name: str                           # e.g. "DOUBLE_TOP", "DOUBLE_BOTTOM"
    direction: PatternDirection
    status: PatternStatus
    confirm_index: int | None           # candle index where the pattern fired (None while FORMING)
    neckline_price: float               # breakout level (entry = neckline after breakout)
    entry: float                        # price or zone where the trade triggers
    stop_loss: float | None             # structural level (configurable policy, spec §8/§9 silent on SL)
    targets: list[float]                # measured-move targets per spec
    invalidation: str                   # exact condition that invalidates (§33)
    peak_price: float                   # average of the two tops (double top) / bottoms (double bottom)
    swing_indices: tuple[int, int, int] # (point1_idx, valley/peak_idx, point2_idx) candle indices
    confidence: float                   # 0.0-1.0 rule-satisfaction score
    notes: str = ""                     # rule trace / additional notes


# Helper functions that are used across multiple pattern modules
def _between(swings: Sequence[Swing], lo_idx: int, hi_idx: int) -> Swing | None:
    """First swing with a candle index strictly inside (lo_idx, hi_idx)."""
    for sw in swings:
        if lo_idx < sw.index < hi_idx:
            return sw
    return None


def _pct_diff(a: float, b: float) -> float:
    mid = (a + b) / 2
    return abs(a - b) / mid if mid else 0.0


def _span_days(t1: datetime, t2: datetime) -> float:
    return abs((t2 - t1).total_seconds()) / 86_400.0


def _find_close_break(
    candles: Sequence[EngineCandle],
    start: int,
    level: float,
    direction: str,
    consecutive: int,
) -> int | None:
    """First candle index whose CLOSE has broken `level` for `consecutive` closes."""
    seen = 0
    for i in range(start, len(candles)):
        c = candles[i].close
        hit = (c < level) if direction == "below" else (c > level)
        seen = seen + 1 if hit else 0
        if seen >= consecutive:
            return i - consecutive + 1
    return None


def _any_close_above(candles: Sequence[EngineCandle], start: int, level: float) -> bool:
    return any(c.close > level for c in candles[start:])


def _any_close_below(candles: Sequence[EngineCandle], start: int, level: float) -> bool:
    return any(c.close < level for c in candles[start:])


def _confidence(*args, **kwargs) -> float:
    """Rule-satisfaction score in [0,1].

    Two call signatures are accepted:

      _confidence(status, quality=1.0)
          FORMING hits cap at 0.5; FULLY_FORMED / INVALIDATED are scored
          straight from the supplied 0..1 geometry signal.

      _confidence(slippage_ratio, depth_ratio, status)
          Backwards-compat for the double-top / channel family. The geometry
          score is 0.6*slip_score + 0.4*depth_score (FORMING caps at 0.5).
    """
    if kwargs and "status" in kwargs and "quality" in kwargs:
        geo = max(0.0, min(1.0, kwargs["quality"]))
        if kwargs["status"] is PatternStatus.FORMING:
            geo *= 0.5
        return round(max(0.0, min(1.0, geo)), 3)

    if len(args) == 3:
        slippage_ratio, depth_ratio, status = args
        slip_score = max(0.0, 1.0 - slippage_ratio)
        depth_score = min(1.0, depth_ratio)
        geo = 0.6 * slip_score + 0.4 * depth_score
        if status is PatternStatus.FORMING:
            geo *= 0.5
        return round(max(0.0, min(1.0, geo)), 3)

    if len(args) == 2:
        return _confidence(args[0], args[1], **kwargs)
    if len(args) == 1 and "status" not in kwargs:
        return _confidence(status=args[0], quality=kwargs.get("quality", 1.0))
    return _confidence(status=kwargs.get("status", PatternStatus.FORMING), quality=kwargs.get("quality", 1.0))