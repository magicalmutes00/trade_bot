"""Tests for channel and triangle pattern detectors per TRADEBOT spec §§11-15.

Spec rules enforced here:
  - channels: two parallel trendlines, requires ≥4 swing touches (2 per line)
  - ascending triangle: flat top + rising lows (≥3 sloped touches) → BEARISH on
    close below the flat top; target = 1:1 measured height below breakout
  - descending triangle: flat bottom + falling highs (≥3 sloped touches) →
    BULLISH on close above the flat bottom; target = 1:1 measured height above
  - symmetrical triangle: converging lines, direction determined by breakout
    (NEVER forced before breakout)
  - invalidation: two consecutive closes beyond a pattern line → INVALIDATED
"""

from datetime import datetime, timedelta, timezone

from app.engine.models import EngineCandle
from app.engine.patterns_channel_triangle import (
    detect_ascending_channel,
    detect_ascending_triangle,
    detect_descending_channel,
    detect_descending_triangle,
    detect_symmetrical_triangle,
)
from app.engine.patterns import PatternDirection, PatternStatus
from app.engine.swings import analyse


T0 = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)


def bar(i: int, h: float, l: float, c: float | None = None, vol: float = 1000.0) -> EngineCandle:
    o = (h + l) / 2
    if c is None:
        c = o
    return EngineCandle(ts=T0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=vol)


def series(pairs: list[tuple[float, float] | tuple[float, float, float]]) -> list[EngineCandle]:
    return [bar(i, *t) for i, t in enumerate(pairs)]


# ── Ascending triangle — SELL (spec §13) ─────────────────────────────────────

def test_ascending_triangle_sell_fully_formed():
    """Flat top (~100) + rising lows (90 → 92) + close below flat top → BEARISH.

    Target = 1:1 measured move: height (100 − 90 = 10) below the breakout.
    """
    pairs = [
        (98, 90.5), (100, 91), (96, 90),        # low ~90
        (100.2, 92), (98, 91),                  # high 100.2
        (100, 93), (97, 92),                    # low 92
        (100, 94),                              # high ~100
        (99, 95, 96), (98, 94, 96.5),           # two closes below flat top 100
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_ascending_triangle(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "ASCENDING_TRIANGLE"
    assert h.direction == PatternDirection.BEARISH
    assert h.status == PatternStatus.FULLY_FORMED
    assert round(h.neckline_price, 1) == 100.0      # flat top
    assert round(h.entry, 1) == 100.0
    assert round(h.stop_loss, 1) == 100.2           # previous high
    assert round(h.targets[0], 1) == 90.0           # 100 − height(10)
    assert "flat top" in h.invalidation


# ── Descending triangle — BUY (spec §14) ─────────────────────────────────────

def test_descending_triangle_buy_fully_formed():
    """Flat bottom (~95) + falling highs (100 → 98) + close above → BULLISH.

    Target = 1:1 measured move: height (100 − 95.2) above the breakout.
    """
    pairs = [
        (98, 96.5), (100, 96), (96, 94.8),          # high 100 / low 94.8
        (99, 96), (96, 95),                         # high 99 / low 95
        (98, 95.8), (96.5, 95.2),                   # high 98 / low 95.2
        (96.2, 95.4, 95.6), (96.0, 95.5, 95.7),     # two closes above flat bottom
        (95.8, 95.55, 95.5),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_descending_triangle(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "DESCENDING_TRIANGLE"
    assert h.direction == PatternDirection.BULLISH
    assert h.status == PatternStatus.FULLY_FORMED
    assert round(h.neckline_price, 1) == 95.2       # flat bottom
    assert round(h.entry, 1) == 95.2
    assert round(h.stop_loss, 1) == 94.8            # previous low
    assert round(h.targets[0], 1) == 100.0          # 95.2 + height(4.8)
    assert "flat bottom" in h.invalidation


# ── Symmetrical triangle (spec §15) ──────────────────────────────────────────

def test_symmetrical_triangle_forming_no_forced_direction():
    """Converging lines present but no breakout → FORMING, direction NEUTRAL."""
    pairs = [
        (98, 94.5), (100, 95), (97, 93),            # high 100 / low 93
        (99, 95), (96.5, 94),                       # high 99 / low 94
        (98, 96), (97, 95),                         # high 98 / low 95
        (98, 95.5, 96.5),                           # close inside the triangle
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_symmetrical_triangle(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "SYMMETRICAL_TRIANGLE"
    assert h.status == PatternStatus.FORMING
    assert h.direction == PatternDirection.NEUTRAL   # not forced before breakout
    assert h.confirm_index is None


def test_symmetrical_triangle_breakout_direction_matches():
    """Same triangle but two closes above the upper line → BULLISH breakout."""
    pairs = [
        (98, 94.5), (100, 95), (97, 93),
        (99, 95), (96.5, 94), (98, 96), (97, 95),
        (98.5, 95.5, 98.5), (99, 95.5, 99.0),       # two closes above upper line
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_symmetrical_triangle(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "SYMMETRICAL_TRIANGLE"
    assert h.status == PatternStatus.FULLY_FORMED
    assert h.direction == PatternDirection.BULLISH   # direction from breakout
    assert round(h.targets[0], 1) == round(103.5, 1)  # neckline 96.5 + height 7


# ── Channels (spec §11 / §12) ────────────────────────────────────────────────

def test_ascending_channel_invalidated_two_closes_beyond():
    """Two consecutive closes above the upper channel line → INVALIDATED."""
    pairs = [
        # rising highs (100→103) and rising lows (96→99) form an ascending channel
        (99.0, 96.5), (100.0, 97.5), (99.5, 96.0),   # high 100 / low 96
        (100.4, 96.8), (101.5, 97.8), (100.6, 97.5), # high 101.5 / low 97.5
        (101.2, 99.5), (103.0, 99.8), (102.0, 99.0), # high 103 / low 99
        (105.0, 100.0, 104.5), (105.5, 100.5, 105.0)  # two closes above upper line
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_ascending_channel(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "ASCENDING_CHANNEL"
    assert h.direction == PatternDirection.BULLISH
    assert h.status == PatternStatus.INVALIDATED
    assert h.confirm_index is None


def test_ascending_channel_forming():
    """Ascending channel recognised but closes stay inside → FORMING."""
    pairs = [
        (99.0, 96.5), (100.0, 97.5), (99.5, 96.0),
        (100.4, 96.8), (101.5, 97.8), (100.6, 97.5),
        (101.2, 99.5), (103.0, 99.8), (102.0, 99.0),
        (103.5, 99.8, 99.9), (104.0, 100.5, 100.2)  # closes stay inside channel
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_ascending_channel(s, candles)

    assert len(hits) == 1
    assert hits[0].status == PatternStatus.FORMING
    assert hits[0].confirm_index is None


def test_descending_channel_forming():
    """Descending channel recognised but no break → FORMING (mirror of §11)."""
    pairs = [
        (99.0, 95.8), (100.0, 96.5), (99.2, 96.0),   # high 100 / low 96
        (99.4, 96.2), (99.5, 95.9), (99.0, 95.5),    # high 99.5 / low 95.5
        (98.8, 95.7), (99.0, 95.2), (98.5, 95.0),    # high 99 / low 95
        (98.6, 95.1),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_descending_channel(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "DESCENDING_CHANNEL"
    assert h.direction == PatternDirection.BEARISH
    assert h.status == PatternStatus.FORMING


# ── Edge case: insufficient touches ──────────────────────────────────────────

def test_insufficient_touches_no_hit():
    """Too few swing touches on the sloped line → no pattern detected."""
    pairs = [
        (98, 92), (100, 91), (96, 90),   # high 100 / low 90
        (99, 93), (100, 92), (98, 93),   # high 100 / low 93 (only 2 lows total)
        (99.5, 94), (100, 95, 96),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)

    assert detect_ascending_triangle(s, candles) == []
    assert detect_descending_triangle(s, candles) == []
    assert detect_symmetrical_triangle(s, candles) == []
    assert detect_ascending_channel(s, candles) == []
    assert detect_descending_channel(s, candles) == []
