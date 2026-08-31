"""Tests for the harmonic-pattern + Fibonacci engine (TRADEBOT spec §§26-29).

Spec rules enforced here:
  - exact XABCD swing geometry matched against the §26/§27 ratio tables
  - strictness: non-matching ratios yield no harmonic hit
  - harmonic hits are always FORMING (LTF entry pending, spec §28)
  - targets = fib reversal of BC (0.618 / 1.0 / 1.414)
  - direction: GARTLEY always BULLISH; others derived from D vs C
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.engine.models import EngineCandle
from app.engine.patterns import PatternDirection, PatternStatus
from app.engine.patterns_harmonics import detect_harmonics, fib_levels
from app.engine.swings import analyse


T0 = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)


def bar(i: int, h: float, l: float) -> EngineCandle:
    o = (h + l) / 2
    return EngineCandle(ts=T0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=o, volume=1000.0)


def series(pairs: list[tuple[float, float]]) -> list[EngineCandle]:
    return [bar(i, *t) for i, t in enumerate(pairs)]


def swing_series(points: list[tuple[float, bool]]) -> list[EngineCandle]:
    """Build candles whose alternating swing sequence is exactly *points*.

    Each element is (price, is_high).  Each swing becomes a single unambiguous
    local-extreme bar (so pivot detection with left=1/right=1 flags exactly
    it), with monotonic connector bars between and a lead/tail bar so the
    first and last swings are pivots too.
    """
    bars: list[tuple[float, float]] = []
    first_price, first_hi = points[0]
    bars.append((first_price - 2.0, first_price - 3.0) if first_hi
                else (first_price + 3.0, first_price + 2.0))

    for k, (price, hi) in enumerate(points):
        bars.append((price, price - 1.0) if hi else (price + 1.0, price))
        if k + 1 < len(points):
            nxt, _ = points[k + 1]
            hi2 = max(price, nxt)
            lo2 = min(price, nxt)
            bars.append((hi2, lo2))   # duplicated connector → never a strict pivot
            bars.append((hi2, lo2))

    last_price, last_hi = points[-1]
    bars.append((last_price - 2.0, last_price - 3.0) if last_hi
                else (last_price + 3.0, last_price + 2.0))
    return series(bars)


def harmonic_series(
    px: float, pa: float,
    ab_ratio: float, bc_ratio: float, cd_ratio: float,
) -> tuple[list[EngineCandle], tuple[float, float, float]]:
    """Bullish 5-swing harmonic: X(low) -> A(high) -> B(low) -> C(high) -> D(low).

    Magnitudes follow the exact spec fractions: AB = ab_ratio*XA,
    BC = bc_ratio*AB, CD = cd_ratio*BC.  Returns (candles, (B, C, bc)).
    """
    xa = pa - px
    ab = xa * ab_ratio
    bc = ab * bc_ratio
    cd = bc * cd_ratio
    pb = pa - ab
    pc = pb + bc
    pd = pc - cd
    points = [(px, False), (pa, True), (pb, False), (pc, True), (pd, False)]
    return swing_series(points), (pb, pc, bc)


# ── §29: fib_levels ─────────────────────────────────────────────────────────

def test_fib_levels_standard_projection():
    """start=100, end=200, ratios [0.382, 0.618, 1.0] -> standard projections."""
    levels = fib_levels(100.0, 200.0, [0.382, 0.618, 1.0])
    assert levels == pytest.approx([138.2, 161.8, 200.0])


# ── GARTLEY (bullish; AB=61.8% XA, BC=38.2% AB, CD=127.2% BC) ──────────────

def test_gartley_bullish_hit():
    """Clean bullish Gartley geometry -> GARTLEY hit, FORMING, BC fib targets."""
    candles, (pb, pc, bc) = harmonic_series(110.0, 210.0, 0.618, 0.382, 1.272)
    s = analyse(candles, left=1, right=1)
    hits = detect_harmonics(s, candles)

    gartleys = [h for h in hits if h.name == "GARTLEY"]
    assert gartleys, f"expected a GARTLEY, got {[h.name for h in hits]}"
    g = max(gartleys, key=lambda h: h.confidence)

    assert g.status == PatternStatus.FORMING
    assert g.confirm_index is None
    assert g.confidence <= 0.5                    # FORMING cap (spec §28)
    assert g.direction == PatternDirection.BULLISH  # GARTLEY always bullish
    # entry at Point D, neckline == D, peak == A (divergence swing)
    assert g.entry == pytest.approx(g.neckline_price)
    assert g.neckline_price < g.peak_price
    # targets = fib reversal of BC (0.618 / 1.0 / 1.414) projected from C
    assert g.targets == pytest.approx([pc + bc * r for r in (0.618, 1.0, 1.414)])
    # spec §28 trace: required vs actual, all PASS, full XABCD indices
    assert "valid=PASS" in g.notes
    assert "XABCD=" in g.notes


# ── PERFECT_HARMONIC (AB=61.8%, BC=61.8%, CD=161.8%) ───────────────────────

def test_perfect_harmonic_hit():
    """AB=61.8%, BC=61.8%, CD=161.8% -> PERFECT_HARMONIC detected."""
    candles, _ = harmonic_series(110.0, 210.0, 0.618, 0.618, 1.618)
    s = analyse(candles, left=1, right=1)
    hits = detect_harmonics(s, candles)

    perfect = [h for h in hits if h.name == "PERFECT_HARMONIC"]
    assert perfect, f"expected PERFECT_HARMONIC, got {[h.name for h in hits]}"
    ph = perfect[0]
    assert ph.status == PatternStatus.FORMING
    assert ph.confidence <= 0.5
    assert ph.direction == PatternDirection.BULLISH


# ── Strictness: a generic ABCD shape that matches no table → no hit ─────────

def test_no_hit_on_nonmatching_ratios():
    """A 5-swing shape whose ratios match NO table -> NO harmonic hit."""
    # AB/XA=0.9, BC/AB=0.9, CD/BC=2.0 — absent from every §26/§27 combo
    # (AB=0.9 only approaches SHARK's 0.886, but SHARK needs BC>1.1, which
    # this shape (BC=0.9) does not satisfy → strict rejection).
    candles, _ = harmonic_series(110.0, 210.0, 0.9, 0.9, 2.0)
    s = analyse(candles, left=1, right=1)

    assert len(s.swings) >= 5, f"expected >=5 swings, got {len(s.swings)}"
    hits = detect_harmonics(s, candles)
    assert hits == [], f"expected no harmonic, got {[(h.name, h.notes) for h in hits]}"


# ── CRAB (AB=38.2%, BC=88.6% of AB, CD=224%) ───────────────────────────────

def test_crab_hit():
    """AB=38.2%, BC=88.6%, CD=224% -> CRAB detected."""
    candles, _ = harmonic_series(110.0, 210.0, 0.382, 0.886, 2.240)
    s = analyse(candles, left=1, right=1)
    hits = detect_harmonics(s, candles)

    crabs = [h for h in hits if h.name == "CRAB"]
    assert crabs, f"expected a CRAB, got {[h.name for h in hits]}"
    cr = crabs[0]
    assert cr.status == PatternStatus.FORMING
    assert cr.confidence <= 0.5
    assert cr.entry == pytest.approx(cr.neckline_price)   # entry at D


# ── Direction from D-vs-C: a top (D above C) → BEARISH ──────────────────────

def test_bearish_top_direction():
    """Bearish BUTTERFLY (X high -> A low -> B high -> C low -> D high above C)
    -> direction BEARISH (non-Gartley dir is derived from D vs C)."""
    # Bearish top: X(low)? No — mirror of the bull: X(high), A(low), B(high),
    # C(low), D(high) where D > C (higher high = top).
    px, pa = 210.0, 110.0
    xa = px - pa
    ab = 0.786 * xa            # AB = 78.6% of XA (BUTTERFLY)
    bc = 0.382 * ab            # BC = 38.2% of AB
    cd = 1.618 * bc            # CD = 161.8% of BC
    pb = pa + ab
    pc = pb - bc
    pd = pc + cd               # D above C -> top
    points = [(px, True), (pa, False), (pb, True), (pc, False), (pd, True)]
    candles = swing_series(points)
    s = analyse(candles, left=1, right=1)
    hits = detect_harmonics(s, candles)

    butterflies = [h for h in hits if h.name == "BUTTERFLY"]
    assert butterflies, f"expected a BUTTERFLY, got {[h.name for h in hits]}"
    bf = butterflies[0]
    assert bf.direction == PatternDirection.BEARISH
    assert bf.entry == pytest.approx(pd)          # entry at Point D
