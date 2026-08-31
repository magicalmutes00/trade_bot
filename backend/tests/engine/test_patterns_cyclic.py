"""Tests for cyclic double top / bottom pattern detectors per TRADEBOT spec §10.

The cyclic method is SEPARATE from the traditional §8/§9 detectors:
  - requires >= 9 months between the two tops/bottoms (max UNLIMITED)
  - slippage <= 1.25% (looser than traditional 0.32%)
  - NO neckline required
  - entry depends on a lower-timeframe reversal -> all hits reported FORMING
  - targets are simple % projections of the avg peak/valley (no neckline)

Spec rules asserted here:
  - CYCLIC_DOUBLE_TOP -> BEARISH, FORMING, confidence <= 0.5
  - CYCLIC_DOUBLE_BOTTOM -> BULLISH
  - gap < 9 months (even with identical geometry) must NOT emit
  - slippage > 1.25% must NOT emit
  - a valid TRADITIONAL double top (tops < 9 months, slippage < 0.32%) must
    NOT be misclassified as cyclic
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.engine.models import EngineCandle
from app.engine.patterns import PatternDirection, PatternStatus
from app.engine.patterns_cyclic import (
    detect_cyclic_double_bottom,
    detect_cyclic_double_top,
)
from app.engine.swings import analyse


T0 = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)


def bar(i: int, h: float, l: float, c: float | None = None, vol: float = 1000.0) -> EngineCandle:
    o = (h + l) / 2
    if c is None:
        c = o
    return EngineCandle(ts=T0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=vol)


def series(pairs: list[tuple[float, float] | tuple[float, float, float]]) -> list[EngineCandle]:
    return [bar(i, *t) for i, t in enumerate(pairs)]


def mk_series_timed(pairs, step_minutes=15, t0=None) -> list[EngineCandle]:
    """Like series but with a configurable bar spacing (for the 9-month rule)."""
    base = t0 or T0
    out = []
    for i, (h, l, *rest) in enumerate(pairs):
        c = rest[0] if rest else (h + l) / 2
        out.append(bar(i, h, l, c))
        # rewrite ts with step spacing — cheap reconstruction
        out[-1] = EngineCandle(
            ts=base + timedelta(minutes=step_minutes * i), open=(h + l) / 2,
            high=h, low=l, close=c, volume=1000.0,
        )
    return out


# ── Cyclic Double Top ───────────────────────────────────────────────────────

def test_cyclic_double_top_detected():
    """Two peaks >= 9 months apart, slippage <= 1.25%, no neckline required."""
    # peak1=100.0 (idx 2), peak2=100.1 (idx 7) -> slippage ~0.10% <= 1.25%
    pairs = [
        (98, 96), (99, 97), (100, 98),        # peak1 ~100 (idx 2)
        (99, 91), (98, 89),                   # descent
        (97, 85),                             # valley ~85 (idx 5)
        (99, 93),                             # rebound
        (100.1, 96),                          # peak2 ~100.1 (idx 7)
        (99, 97), (98, 96), (97, 95),
    ]
    # 60 days/bar; peak1 (idx 2) -> peak2 (idx 7) = 5 bars = 300 days >= 274
    step_minutes = 60 * 24 * 60
    candles = mk_series_timed(pairs, step_minutes=step_minutes)
    s = analyse(candles, left=1, right=1)
    hits = detect_cyclic_double_top(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "CYCLIC_DOUBLE_TOP"
    assert h.direction == PatternDirection.BEARISH
    assert h.status == PatternStatus.FORMING      # LTF reversal pending
    assert h.confirm_index is None
    assert h.confidence <= 0.5                    # FORMING caps confidence

    # targets are the 3 downward % levels of the avg peak (100.05)
    avg_peak = 100.05
    expected = [avg_peak * (1 - k) for k in (0.20, 0.40, 0.60)]
    assert len(h.targets) == 3
    assert h.targets == pytest.approx(expected, abs=1e-9)
    assert "higher cyclic top" in h.invalidation


def test_cyclic_double_bottom_detected():
    """Two bottoms >= 9 months apart, slippage <= 1.25%, no neckline required."""
    # bottom1=80.0 (idx 2), bottom2=80.2 (idx 7) -> slippage ~0.25% <= 1.25%
    pairs = [
        (88, 84), (86, 82), (84, 80),         # bottom1 ~80 (idx 2)
        (86, 83), (89, 81),                   # bounce
        (98, 95),                             # peak ~95 (idx 5)
        (90, 88),                             # pullback
        (86, 80.2),                           # bottom2 ~80.2 (idx 7)
        (89, 83), (92, 85), (94, 87),
    ]
    step_minutes = 60 * 24 * 60               # bottom1 (idx 2) -> bottom2 (idx 7) = 300 days >= 274
    candles = mk_series_timed(pairs, step_minutes=step_minutes)
    s = analyse(candles, left=1, right=1)
    hits = detect_cyclic_double_bottom(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "CYCLIC_DOUBLE_BOTTOM"
    assert h.direction == PatternDirection.BULLISH
    assert h.status == PatternStatus.FORMING
    assert h.confidence <= 0.5

    # targets are the 5 upward % levels of the avg valley (80.1)
    avg_valley = 80.1
    expected = [avg_valley * (1 + k) for k in (0.20, 0.30, 0.60, 0.80, 1.00)]
    assert len(h.targets) == 5
    assert h.targets == pytest.approx(expected, abs=1e-9)
    assert "lower cyclic bottom" in h.invalidation


def test_cyclic_rejects_gap_under_9_months():
    """Identical geometry but tops < 9 months apart -> NOT cyclic (proves the
    cyclic method is separate from the traditional < 9-month window)."""
    pairs = [
        (98, 96), (99, 97), (100, 98),        # peak1 ~100
        (99, 91), (98, 89), (97, 85),         # valley ~85
        (99, 93), (100.1, 96),                # peak2 ~100.1
        (99, 97), (98, 96), (97, 95),
    ]
    # 20 days/bar; peak1 (idx 2) -> peak2 (idx 7) = 5 bars = 100 days < 274
    step_minutes = 20 * 24 * 60
    candles = mk_series_timed(pairs, step_minutes=step_minutes)
    s = analyse(candles, left=1, right=1)
    hits = detect_cyclic_double_top(s, candles)

    assert hits == []


def test_cyclic_rejects_slippage_over_1_25_pct():
    """Peaks >= 9 months apart BUT slippage > 1.25% -> no cyclic hit."""
    # peak1=100.0, peak2=102.0 -> slippage ~1.98% > 1.25%
    pairs = [
        (98, 96), (99, 97), (100, 98),        # peak1 ~100
        (99, 91), (95, 89), (97, 85),         # valley ~85
        (99, 93), (102, 96),                  # peak2 ~102 (slippage too high)
        (100, 98), (99, 97), (98, 96),
    ]
    step_minutes = 60 * 24 * 60               # 60 days/bar -> 5 bars = 300 days >= 274
    candles = mk_series_timed(pairs, step_minutes=step_minutes)
    s = analyse(candles, left=1, right=1)
    hits = detect_cyclic_double_top(s, candles)

    assert hits == []


def test_traditional_double_top_not_misclassified_as_cyclic():
    """A valid TRADITIONAL double top (tops < 9 months, slippage ~0.2% < 0.32%)
    must NOT be misclassified as a cyclic pattern."""
    pairs = [
        (98, 96), (99, 97), (100, 98),        # peak1 ~100
        (99, 91), (98, 92), (96, 89),         # valley ~89
        (95, 93), (97, 95), (100.2, 96),      # peak2 ~100.2 (slippage ~0.20%)
        (99, 91), (98, 92), (97, 93),         # consolidation below the tops
    ]
    # 20 days/bar; peak1 (idx 2) -> peak2 (idx 8) = 6 bars = 120 days < 274
    step_minutes = 20 * 24 * 60
    candles = mk_series_timed(pairs, step_minutes=step_minutes)
    s = analyse(candles, left=1, right=1)

    # Sanity: this IS a valid traditional double top...
    from app.engine.patterns import detect_double_top
    trad = detect_double_top(s, candles)
    assert trad and trad[0].name == "DOUBLE_TOP"

    # ...but must NOT be a cyclic one (cyclic needs >= 9 months).
    hits = detect_cyclic_double_top(s, candles)
    assert hits == []
