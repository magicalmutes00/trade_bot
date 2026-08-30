"""Tests for the swing-point / HH-HL-LH-LL / trend state machine (pure, no DB)."""

from datetime import datetime, timedelta, timezone

from app.engine.models import EngineCandle, Pivot, Side
from app.engine.swings import (
    SwingLabel,
    Trend,
    _merge_same_side,
    analyse,
    swing_sequence,
)

T0 = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)


def bar(i: int, h: float, l: float, vol: float = 1000.0) -> EngineCandle:
    o = (h + l) / 2
    return EngineCandle(ts=T0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=o, volume=vol)


def series(pairs: list[tuple[float, float]]) -> list[EngineCandle]:
    return [bar(i, h, l) for i, (h, l) in enumerate(pairs)]


# ---- merge: consecutive same-side pivots collapse to the most extreme ----

def test_merge_same_side_keeps_most_extreme():
    pivots = [
        Pivot(ts=T0, index=1, price=100.0, side=Side.UP),
        Pivot(ts=T0, index=3, price=105.0, side=Side.UP),   # higher high supersedes
        Pivot(ts=T0, index=4, price=99.0, side=Side.DOWN),
    ]
    merged = _merge_same_side(pivots)
    assert [(p.index, p.price) for p in merged] == [(3, 105.0), (4, 99.0)]


def test_swing_sequence_is_strictly_alternating():
    # Two rising bumps with no swing low between (plateau low) => the two
    # adjacent highs must collapse to a single (higher) swing high.
    pairs = [
        (100, 99), (103, 100), (106, 102), (104, 102), (107, 105),
        (106, 103), (103, 101), (104, 103),
    ]
    swings = swing_sequence(series(pairs), left=1, right=1)
    assert swings and swings[0].price == 107.0  # dominant high survives
    assert swings[0].side is Side.UP
    for a, b in zip(swings, swings[1:]):
        assert a.side is not b.side  # no two consecutive same-side swings


# ---- labels + trend over a crafted uptrend ----

def test_uptrend_bullish_with_hh_hl_labels():
    pairs = [
        (100, 99), (102, 100), (105, 103), (104, 101),
        (107, 106), (114, 110), (112, 108), (113, 111),
    ]
    s = analyse(series(pairs), left=1, right=1)
    assert s.trend is Trend.BULLISH
    assert [sw.label for sw in s.swings] == [None, None, SwingLabel.HIGH_HIGH, SwingLabel.HIGH_LOW]


def test_downtrend_bearish_with_lh_ll_labels():
    pairs = [
        (100, 99), (99, 98), (100, 97), (97, 94), (95, 95),
        (96, 95), (94, 91), (91, 90), (92, 88), (90, 87), (91, 90),
    ]
    s = analyse(series(pairs), left=1, right=1)
    assert s.trend is Trend.BEARISH
    assert [(sw.price, sw.label) for sw in s.swings] == [
        (100.0, None), (94.0, None), (96.0, SwingLabel.LOW_HIGH), (87.0, SwingLabel.LOW_LOW),
    ]


def test_flat_series_neutral():
    s = analyse(series([(100, 99)] * 30), left=2, right=2)
    assert s.trend is Trend.NEUTRAL
    assert s.swings == []


def test_insufficient_swings_neutral():
    rising = series([(10 + i, 9 + i) for i in range(20)])  # monotonic => no pivots
    s = analyse(rising, left=2, right=2)
    assert s.trend is Trend.NEUTRAL
