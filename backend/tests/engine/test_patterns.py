"""Tests for double top / bottom pattern detectors per TRADEBOT spec §8/§9.

Spec rules enforced here:
  - slippage between tops/bottoms ≤ 0.32%
  - time between tops/bottoms < 9 months
  - one candle CLOSE beyond the neckline = FULLY_FORMED
  - wicks considered (confirmation on close, not wick)
  - target = measured height of the pattern
"""

from datetime import datetime, timedelta, timezone

from app.engine.models import EngineCandle
from app.engine.patterns import (
    PatternDirection,
    PatternStatus,
    detect_double_bottom,
    detect_double_top,
    detect_patterns,
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


# ── Double Top ──────────────────────────────────────────────────────────────

def test_double_top_fully_formed():
    """Two tops within 0.32%, valley between, one close below neckline."""
    # peak1=100.0, peak2=100.2 → slippage 0.20% ≤ 0.32%
    pairs = [
        (98, 96), (99, 97), (100, 98),        # peak1 ~100 (idx 2)
        (99, 91), (98, 92), (96, 90),         # valley ~90 (idx 5)
        (95, 93), (97, 94.6), (100.2, 96),    # peak2 ~100.2 (idx 8)
        (99, 88, 88), (96, 85, 85),           # close below neckline 90 → FULLY_FORMED
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_double_top(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "DOUBLE_TOP"
    assert h.direction == PatternDirection.BEARISH
    assert h.status == PatternStatus.FULLY_FORMED
    assert h.neckline_price == 90.0
    assert h.entry == 90.0
    assert h.confirm_index == 9                  # first close at 88 < 90
    # target = measured height: avg_peak (100.1) − neckline (90) → 90 − 10.1
    assert h.targets == [round(90.0 - 10.1, 4)]
    assert h.stop_loss == 100.2                  # higher of the two tops
    assert "CLOSES above" in h.invalidation


def test_double_top_forming_no_break():
    """Geometry valid but no close below neckline → FORMING, no confirmed entry."""
    pairs = [
        (98, 96), (99, 97), (100, 98),
        (99, 91), (98, 92), (96, 90),
        (95, 93), (97, 94.6), (100.2, 96),
        # price consolidates between neckline (90) and tops (100.2): no confirm, no invalidation
        (97, 92), (96, 93), (97, 94),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_double_top(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.status == PatternStatus.FORMING
    assert h.confirm_index is None
    assert h.confidence <= 0.5                    # FORMING caps confidence


def test_double_top_peak_tolerance_rejects():
    """Slippage > 0.32% → not a traditional double top."""
    pairs = [
        (90, 88), (95, 92), (100, 98),           # peak1 ~100
        (99, 91), (98, 92), (96, 90),            # valley ~90
        (95, 93), (97, 94), (105, 102),          # peak2 ~105 → 4.9% slippage
        (103, 88, 88),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_double_top(s, candles)
    assert hits == []


def test_double_top_nine_month_window():
    """Tops more than 9 months apart → not a TRADITIONAL double top (spec §8)."""
    # peak1 at days 0..8, then a long gap, peak2 far in time
    pairs = [
        (98, 96), (99, 97), (100, 98),           # peak1 ~100
        (99, 91), (98, 92), (96, 89),            # valley ~89
        (95, 93), (97, 95), (100.2, 96),         # peak2 ~100.2 → 300 days later
        (99, 88, 88),
    ]
    # use a huge step so peak1 (idx 2) → peak2 (idx 8) spans > 274 days
    step_minutes = 50 * 24 * 60                   # 50 days per bar → 6 intervals = 300 days > 274
    candles = mk_series_timed(pairs, step_minutes=step_minutes)
    s = analyse(candles, left=1, right=1)
    hits = detect_double_top(s, candles)
    assert hits == []


def test_double_top_wick_cross_does_not_confirm():
    """A wick that pierces the neckline but the candle CLOSES above it → FORMING."""
    pairs = [
        (98, 96), (99, 97), (100, 98),
        (99, 91), (98, 92), (96, 90),
        (95, 93), (97, 94.6), (100.2, 96),
        (98, 89, 96),                            # low 89 < 90 (wick) but close 96 > 90
        (97, 94, 95),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_double_top(s, candles)
    assert len(hits) == 1
    assert hits[0].status == PatternStatus.FORMING   # wick alone does not confirm


# ── Double Bottom ───────────────────────────────────────────────────────────

def test_double_bottom_fully_formed():
    """Two bottoms within 0.32%, peak between, one close above neckline."""
    # valley1=80.0, valley2=80.2 → slippage 0.25% ≤ 0.32%
    pairs = [
        (88, 84), (86, 82), (84, 80),           # bottom1 ~80 (idx 2)
        (86, 83), (90, 88), (95, 93),           # peak ~95 (idx 5)
        (94, 88), (89, 82), (86, 80.2),         # bottom2 ~80.2 (idx 8)
        (97, 95, 96),                           # close above neckline 95
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_double_bottom(s, candles)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "DOUBLE_BOTTOM"
    assert h.direction == PatternDirection.BULLISH
    assert h.status == PatternStatus.FULLY_FORMED
    assert h.neckline_price == 95.0
    assert h.entry == 95.0
    assert h.confirm_index == 9
    # target = measured height: 95 − avg_valley(80.1) = 14.9 → 95 + 14.9
    assert h.targets == [round(95.0 + 14.9, 4)]
    assert h.stop_loss == 80.0                  # lower of the two bottoms
    assert "CLOSES below" in h.invalidation


def test_double_bottom_forming_no_break():
    pairs = [
        (88, 84), (86, 82), (84, 80),
        (86, 83), (90, 88), (95, 93),
        (94, 88), (89, 82), (86, 80.2),
        (90, 88), (92, 90), (93, 91),           # no close above 95
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_double_bottom(s, candles)
    assert len(hits) == 1
    assert hits[0].status == PatternStatus.FORMING


# ── Combined ────────────────────────────────────────────────────────────────

def test_detect_patterns_returns_both_sorted_by_confirm():
    """Both patterns detected; newer confirm index sorts first."""
    pairs = [
        # Double bottom FIRST (confirms at idx 9)
        (88, 84), (86, 82), (84, 80),
        (86, 83), (90, 88), (95, 93),
        (94, 88), (89, 82), (86, 80.2),
        (97, 95, 96),
        # Double top LATER (confirms at idx ~20)
        (96, 94), (97, 95), (100, 98),
        (99, 91), (98, 92), (96, 90),
        (95, 93), (97, 94.6), (100.2, 96),
        (99, 88, 88), (96, 85, 85),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_patterns(s, candles)

    # Hits with confirm_index=19 are the newest confirmed patterns;
    # hits with confirm_index=9 are older (double bottom).
    assert len(hits) >= 2
    names = {h.name for h in hits}
    assert "DOUBLE_TOP" in names
    assert "DOUBLE_BOTTOM" in names
    # The newest confirmed hits must come first (highest confirm_index)
    top_confirm = hits[0].confirm_index
    assert top_confirm == 19
    for h in hits:
        if h.confirm_index is not None:
            assert h.confirm_index <= top_confirm


# ── Edge cases ──────────────────────────────────────────────────────────────

def test_no_patterns_when_insufficient_swings():
    pairs = [(100, 99)] * 50
    candles = series(pairs)
    s = analyse(candles, left=2, right=2)
    assert detect_patterns(s, candles) == []


def test_confidence_in_unit_range():
    pairs = [
        (98, 96), (99, 97), (100, 98),
        (99, 91), (98, 92), (96, 90),
        (95, 93), (97, 94.6), (100.2, 96),
        (99, 88, 88), (96, 85, 85),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_patterns(s, candles)
    assert hits
    for h in hits:
        assert 0.0 <= h.confidence <= 1.0