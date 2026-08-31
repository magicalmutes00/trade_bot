"""Tests for the Head & Shoulders pattern engine (TRADEBOT spec §5, §6).

Covers both bearish HEAD_AND_SHOULDERS and bullish INVERTED_HEAD_AND_SHOULDERS.
The helper style mirrors tests/engine/test_patterns.py.
"""

from datetime import datetime, timedelta, timezone

from app.engine.config import PatternConfig
from app.engine.models import EngineCandle
from app.engine.patterns import PatternDirection, PatternStatus
from app.engine.patterns_hs import detect_head_shoulders
from app.engine.swings import analyse


T0 = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)


def bar(i: int, h: float, l: float, c: float | None = None, vol: float = 1000.0) -> EngineCandle:
    o = (h + l) / 2
    if c is None:
        c = o
    return EngineCandle(ts=T0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=vol)


def series(pairs: list[tuple[float, float] | tuple[float, float, float]]) -> list[EngineCandle]:
    return [bar(i, *t) for i, t in enumerate(pairs)]


# Compact config: disable the spacing noise filter so tests can use tight series
# (the default hs_min_bars_between=10 is exercised in a dedicated test).
CFG = PatternConfig(hs_min_bars_between=1, hs_confirm_bars=1)


# ── Bearish Head & Shoulders (§5) ─────────────────────────────────────────

def test_bearish_hs_fully_formed():
    """LS/head/RS swing highs + two valleys + close below neckline → FULLY_FORMED."""
    pairs = [
        (90, 86), (95, 90), (93, 88), (100, 95), (97, 92),   # uptrend into pattern
        (103, 97),        # 5  left shoulder
        (99, 93),
        (95, 89),         # 7  valley v1 = 89
        (99, 93),
        (109, 102),       # 9  head (highest)
        (102, 96),
        (97, 91),         # 11 valley v2 = 91
        (105, 99),        # 12 right shoulder
        (102, 96),
        (98, 92, 92),     # 14
        (95, 89, 89),     # 15 close 89 < neckline 90 → breaks
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_head_shoulders(s, candles, CFG)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "HEAD_AND_SHOULDERS"
    assert h.direction == PatternDirection.BEARISH
    assert h.status == PatternStatus.FULLY_FORMED
    assert h.confirm_index == 15
    assert h.neckline_price == 90.0          # (89 + 91) / 2
    assert h.entry == 90.0                   # entry == neckline
    assert h.stop_loss == 105.0              # right shoulder top
    # target1 = neckline − (head − neckline) = 90 − (109 − 90) = 71
    assert h.targets[0] == round(90.0 - 19.0, 4)
    assert h.targets[1] == 92.0              # pattern start (prior swing low)
    assert h.swing_indices == (5, 9, 12)
    assert "CLOSES above the right shoulder top" in h.invalidation


def test_bearish_hs_forming_no_break():
    """Geometry present but no close below neckline → FORMING, no confirmed entry."""
    pairs = [
        (90, 86), (95, 90), (93, 88), (100, 95), (97, 92),
        (103, 97), (99, 93), (95, 89), (99, 93), (109, 102),
        (102, 96), (97, 91), (105, 99),
        (104, 97),        # 13 consolidates above neckline
        (103, 95, 96),    # 14 close 96 > 90
        (101, 95, 95),    # 15 close 95 > 90
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_head_shoulders(s, candles, CFG)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "HEAD_AND_SHOULDERS"
    assert h.status == PatternStatus.FORMING
    assert h.confirm_index is None
    assert h.confidence <= 0.5                # FORMING cap


# ── Bullish Inverted Head & Shoulders (§6) ─────────────────────────────────

def test_inverted_hs_fully_formed():
    """Inverted (bullish) H&S: head lowest, close above neckline → FULLY_FORMED."""
    pairs = [
        (100, 96), (95, 91), (97, 93), (90, 86), (93, 89),   # downtrend
        (87, 83),         # 5  left shoulder = 83
        (91, 87),
        (95, 91),         # 7  peak p1 = 95
        (91, 87),
        (84, 79),         # 9  head (lowest)
        (88, 84),
        (93, 88),         # 11 peak p2 = 93
        (88, 84),         # 12 right shoulder = 84
        (92, 88),
        (94, 90, 94),     # 14 close 94
        (96, 92, 95),     # 15 close 95 > neckline 94 → breaks
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_head_shoulders(s, candles, CFG)

    assert len(hits) == 1
    h = hits[0]
    assert h.name == "INVERTED_HEAD_AND_SHOULDERS"
    assert h.direction == PatternDirection.BULLISH
    assert h.status == PatternStatus.FULLY_FORMED
    assert h.confirm_index == 15
    assert h.neckline_price == 94.0          # (95 + 93) / 2
    assert h.entry == 94.0
    assert h.stop_loss == 84.0               # right shoulder bottom
    # target1 = neckline + (neckline − head) = 94 + (94 − 79) = 109
    assert h.targets[0] == round(94.0 + 15.0, 4)
    assert h.targets[1] == 93.0              # pattern start (prior swing high)
    assert h.swing_indices == (5, 9, 12)


# ── Strictness / rejection ─────────────────────────────────────────────────

def test_head_not_highest_rejected():
    """Right shoulder higher than the head (beyond tolerance) → no H&S hit."""
    pairs = [
        (96, 92), (98, 93), (95, 91), (99, 94), (96, 92),
        (100, 95),        # 5  left shoulder
        (97, 92),
        (93, 89),         # 7  valley v1 = 89
        (97, 92),
        (102, 96),        # 9  head
        (98, 93),
        (94, 90),         # 11 valley v2 = 90
        (105, 99),        # 12 right shoulder HIGHER than head
        (103, 97),
        (100, 94, 94),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_head_shoulders(s, candles, CFG)
    assert hits == []


def test_plain_double_top_not_hs():
    """Two equal highs (no distinct head) must NOT produce an H&S hit."""
    pairs = [
        (94, 90), (96, 91), (93, 89),
        (100, 95),        # 3 peak1
        (97, 92),
        (92, 88),         # 5 valley
        (96, 92),
        (100, 95),        # 7 peak2 (equal to peak1)
        (98, 93),
        (95, 91, 91),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    hits = detect_head_shoulders(s, candles, CFG)
    assert hits == []


def test_default_min_bars_filter_rejects_compact():
    """Default hs_min_bars_between=10 filters out the compact (4-bar) spacing."""
    pairs = [
        (90, 86), (95, 90), (93, 88), (100, 95), (97, 92),
        (103, 97), (99, 93), (95, 89), (99, 93), (109, 102),
        (102, 96), (97, 91), (105, 99), (102, 96),
        (98, 92, 92), (95, 89, 89),
    ]
    candles = series(pairs)
    s = analyse(candles, left=1, right=1)
    assert detect_head_shoulders(s, candles) == []   # default cfg (min_bars=10)
