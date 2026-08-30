"""Swing-point market structure: fractal pivots -> alternating HH/HL/LH/LL ->
trend state machine.

This is the pure, stack-agnostic foundation the pattern detectors build on
(double top/bottom, H&S, triangles, harmonics, fib levels). It reuses the
existing fractal-pivot detection from ``market_structure.confirm_pivots`` and
adds the swinging high/low abstraction plus the HH/HL/LH/LL labels and a trend
classification. No I/O, fully deterministic, independently unit-testable.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.engine.config import DEFAULT_CONFIG
from app.engine.market_structure import confirm_pivots
from app.engine.models import EngineCandle, Pivot, Side


class SwingLabel(str, Enum):
    """Structure label of a swing point relative to the previous swing of the
    same polarity: a higher-high (HH), higher-low (HL), lower-high (LH) or
    lower-low (LL)."""

    HIGH_HIGH = "HH"
    HIGH_LOW = "HL"
    LOW_HIGH = "LH"
    LOW_LOW = "LL"


class Trend(str, Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class Swing:
    """A single swing point in the alternating sequence, labelled against the
    previous swing of the same polarity (``None`` for the first of each)."""

    ts: datetime
    index: int
    price: float
    side: Side                 # UP = swing high, DOWN = swing low
    label: SwingLabel | None


@dataclass(frozen=True)
class SwingStructure:
    """The full read of a candle series: alternating swings + derived trend."""

    swings: list[Swing]
    trend: Trend
    highs: list[Swing]         # swing highs in chronological order
    lows: list[Swing]          # swing lows in chronological order


def swing_sequence(
    candles: Sequence[EngineCandle],
    *,
    left: int = DEFAULT_CONFIG.pivot_left,
    right: int = DEFAULT_CONFIG.pivot_right,
) -> list[Swing]:
    """Return the alternating high/low swing sequence with HH/HL/LH/LL labels.

    Pipeline: fractal pivots -> collapse same-side runs to the most extreme
    pivot -> label each swing against the prior swing of its polarity.
    """
    pivots = confirm_pivots(candles, left=left, right=right)
    merged = _merge_same_side(pivots)
    return _label_sequence(merged)


def analyse(
    candles: Sequence[EngineCandle],
    *,
    left: int = DEFAULT_CONFIG.pivot_left,
    right: int = DEFAULT_CONFIG.pivot_right,
) -> SwingStructure:
    """Convenience wrapper: swing sequence + trend in one call."""
    swings = swing_sequence(candles, left=left, right=right)
    highs = [s for s in swings if s.side is Side.UP]
    lows = [s for s in swings if s.side is Side.DOWN]
    return SwingStructure(
        swings=swings,
        trend=trend_from_swings(highs, lows),
        highs=highs,
        lows=lows,
    )


def trend_from_swings(
    highs: Sequence[Swing],
    lows: Sequence[Swing],
) -> Trend:
    """Classic structure rule over the last two swings of each polarity.

    * two higher highs AND two higher lows  -> BULLISH
    * two lower highs AND two lower lows    -> BEARISH
    * otherwise (or insufficient swings)    -> NEUTRAL
    """
    if len(highs) >= 2 and len(lows) >= 2:
        last_high, prev_high = highs[-1].price, highs[-2].price
        last_low, prev_low = lows[-1].price, lows[-2].price

        if last_high > prev_high and last_low > prev_low:
            return Trend.BULLISH
        if last_high < prev_high and last_low < prev_low:
            return Trend.BEARISH
    return Trend.NEUTRAL


def _merge_same_side(pivots: Sequence[Pivot]) -> list[Pivot]:
    """Collapse consecutive same-side pivots to the most extreme (highest high /
    lowest low), keeping the resulting sequence strictly alternating.

    ``confirm_pivots`` can emit back-to-back highs or back-to-back lows when a
    run does not make a clean alternating structure; for structure analysis we
    keep only the dominant pivot of each contiguous run.
    """
    merged: list[Pivot] = []
    for p in pivots:  # confirm_pivots already returns index-sorted
        if merged and merged[-1].side == p.side:
            prev = merged[-1]
            more_extreme = (
                p.price > prev.price if p.side is Side.UP else p.price < prev.price
            )
            if more_extreme:
                merged[-1] = p  # later bar is the more extreme swing
        else:
            merged.append(p)
    return merged


def _label_sequence(swings: Sequence[Pivot]) -> list[Swing]:
    """Attach HH/HL/LH/LL labels by comparing each swing to the previous swing
    of the same polarity."""
    out: list[Swing] = []
    last_high: float | None = None
    last_low: float | None = None
    for p in swings:
        if p.side is Side.UP:
            label = (
                None
                if last_high is None
                else SwingLabel.HIGH_HIGH if p.price > last_high else SwingLabel.LOW_HIGH
            )
            last_high = p.price
        else:
            label = (
                None
                if last_low is None
                else SwingLabel.LOW_LOW if p.price < last_low else SwingLabel.HIGH_LOW
            )
            last_low = p.price
        out.append(
            Swing(ts=p.ts, index=p.index, price=p.price, side=p.side, label=label)
        )
    return out


__all__ = [
    "Swing",
    "SwingLabel",
    "SwingStructure",
    "Trend",
    "swing_sequence",
    "analyse",
    "trend_from_swings",
]
