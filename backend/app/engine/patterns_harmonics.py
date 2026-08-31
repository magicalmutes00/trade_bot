"""Harmonic-pattern + Fibonacci engine (TRADEBOT spec §§26-29).

Pure functions that walk the alternating swing sequence looking for five-point
XABCD geometries whose leg ratios match the strict harmonic tables.  Every hit
is emitted as a FORMING-status ``PatternHit`` (spec §28: LTF entry is pending;
single-TF detector can never produce FULLY_FORMED).

Public API:
    detect_harmonics(structure, candles, cfg) -> list[PatternHit]
    fib_levels(start, end, ratios) -> list[float]

Mirror port: the Kotlin side must reproduce this logic exactly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from app.engine.config import DEFAULT_PATTERN_CONFIG, PatternConfig
from app.engine.models import EngineCandle
from app.engine.patterns import (
    PatternDirection,
    PatternHit,
    PatternStatus,
)
from app.engine.swings import Swing, SwingStructure


# ---------------------------------------------------------------------------
# §26  Harmonic ratio tables
# ---------------------------------------------------------------------------
# Each pattern stores every valid combination of (AB/XA, BC/AB, CD/BC).
# Ratios are fractions of the named leg (not percentages).
# E.g.  "AB = 61.8% of XA" is stored as 0.618.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _HarmonicSpec:
    """Specification for one harmonic pattern variant."""
    combos: list[tuple[float, float, float]]   # [(ab_xa, bc_ab, cd_bc), ...]
    is_perfect: bool = False


# Base patterns (§26) — each has multiple valid ratio combinations.
#
# Where the spec writes "A OR B;  C OR D;  E OR F" without coupling the legs
# (CRAB/BAT/BUTTERFLY/CYPHER/SHARK) we take the full cross product.  GARTLEY
# couples CD to BC ("CD = 127.2% if BC=38.2% OR 161.8% if BC=88.6%"), so it
# lists only the two valid pairs.

def _cross(ab_options, bc_options, cd_options):
    """Cross product of the per-leg ratio options into explicit combos."""
    return [
        (ab, bc, cd)
        for ab in ab_options
        for bc in bc_options
        for cd in cd_options
    ]

_GARTLEY_SPEC = _HarmonicSpec(combos=[
    # AB = 61.8% of XA;  BC = 38.2% OR 88.6% of AB
    # CD = 127.2% (if BC=38.2%) OR 161.8% (if BC=88.6%) — coupled
    (0.618, 0.382, 1.272),
    (0.618, 0.886, 1.618),
])

_CRAB_SPEC = _HarmonicSpec(combos=_cross(
    # AB = 38.2% OR 61.8% of XA;  BC = 38.2% OR 88.6% of AB
    # CD = 224% OR 361.8%
    (0.382, 0.618), (0.382, 0.886), (2.240, 3.618),
))

_BAT_SPEC = _HarmonicSpec(combos=_cross(
    # AB = 38.2% OR 50% of XA;  BC = 38.2% OR 88.6% of AB
    # CD = 161.8% OR 261.8%
    (0.382, 0.500), (0.382, 0.886), (1.618, 2.618),
))

_BUTTERFLY_SPEC = _HarmonicSpec(combos=_cross(
    # AB = 78.6% of XA;  BC = 38.2% OR 88.6% of AB
    # CD = 161.8% OR 261.8%
    (0.786,), (0.382, 0.886), (1.618, 2.618),
))

_CYPHER_SPEC = _HarmonicSpec(combos=_cross(
    # AB = 38.2% OR 61.8% of XA;  BC = 113.4% OR 141.4% of AB
    # CD = 141.4% OR 200%
    (0.382, 0.618), (1.134, 1.414), (1.414, 2.000),
))

_SHARK_SPEC = _HarmonicSpec(combos=_cross(
    # AB = 88.6% of XA;  BC = 113% OR 161.8% of AB
    # CD = 161.8% OR 224%
    (0.886,), (1.130, 1.618), (1.618, 2.240),
))

# Perfect variants (§27) — exact ratio combos.
_PERFECT_BUTTERFLY_SPEC = _HarmonicSpec(
    combos=[(0.786, 0.500, 1.618)],
    is_perfect=True,
)

_PERFECT_BAT_SPEC = _HarmonicSpec(
    combos=[
        (0.500, 0.500, 2.000),
        (0.500, 0.618, 2.000),
    ],
    is_perfect=True,
)

_PERFECT_CYPHER_SPEC = _HarmonicSpec(
    combos=[(0.500, 1.272, 1.414)],
    is_perfect=True,
)

_PERFECT_HARMONIC_SPEC = _HarmonicSpec(
    combos=[(0.618, 0.618, 1.618)],
    is_perfect=True,
)

# Ordered lookup — first match wins; perfect specs checked FIRST so they
# appear as their own hits, not shadowed by the base pattern that also matches.
PATTERN_SPECS: list[tuple[str, _HarmonicSpec]] = [
    ("PERFECT_HARMONIC", _PERFECT_HARMONIC_SPEC),
    ("PERFECT_BUTTERFLY", _PERFECT_BUTTERFLY_SPEC),
    ("PERFECT_BAT", _PERFECT_BAT_SPEC),
    ("PERFECT_CYPHER", _PERFECT_CYPHER_SPEC),
    ("GARTLEY", _GARTLEY_SPEC),
    ("CRAB", _CRAB_SPEC),
    ("BAT", _BAT_SPEC),
    ("BUTTERFLY", _BUTTERFLY_SPEC),
    ("CYPHER", _CYPHER_SPEC),
    ("SHARK", _SHARK_SPEC),
]

# GARTLEY direction is always BULLISH per spec §26.
_ALWAYS_BULLISH = {"GARTLEY"}


# ---------------------------------------------------------------------------
# §29  Fibonacci projection helper
# ---------------------------------------------------------------------------

def fib_levels(
    start: float,
    end: float,
    ratios: Sequence[float],
) -> list[float]:
    """Standard Fibonacci projections from *start* toward *end*.

    Returns ``[start + (end - start) * r for r in ratios]``.
    When ``end > start`` these are upward projections; when ``end < start``
    they project downward.  The caller controls the sign convention by
    choosing the order of ``start`` / ``end``.
    """
    return [start + (end - start) * r for r in ratios]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _leg_len(p1: float, p2: float) -> float:
    """Absolute leg length between two price points (sign-agnostic)."""
    return abs(p1 - p2)


def _ratio_near(actual: float, required: float, tol: float) -> bool:
    """True when ``actual`` is within ±tol of ``required``."""
    return abs(actual - required) <= tol


def _direction_from_dcd(d_price: float, c_price: float) -> PatternDirection:
    """Determine direction from the D-point position relative to C.

    * D below C (lower low after a prior swing low)  → BULLISH (bottom)
    * D above C (higher high after a prior swing high) → BEARISH (top)
    """
    if d_price < c_price:
        return PatternDirection.BULLISH
    return PatternDirection.BEARISH


def _confidence_for_match(
    actual_ratios: tuple[float, float, float],
    required_ratios: tuple[float, float, float],
    tol: float,
) -> float:
    """Compute a 0-1 confidence score for how well the ratios matched.

    Starts at 1.0 and subtracts a penalty proportional to the total
    deviation, normalised by tolerance.  FORMING hits are always capped
    at 0.5 (spec §28).
    """
    # Per-leg deviation: 0 if perfect, up to 1.0 if at tolerance boundary
    deviations = [
        min(abs(a - r) / tol, 1.0)
        for a, r in zip(actual_ratios, required_ratios)
    ]
    # Average deviation across three legs, scaled to [0, 1]
    avg_dev = sum(deviations) / 3.0
    raw = 1.0 - avg_dev
    # Harmonic hits are always FORMING (LTF entry pending) → cap at 0.5
    return round(max(0.0, min(0.5, raw)), 3)


def _build_notes(
    xa: float, ab: float, bc: float, cd: float,
    x_price: float, a_price: float, b_price: float, c_price: float, d_price: float,
    ab_req: float, bc_req: float, cd_req: float,
    tol: float,
    x_idx: int, a_idx: int, b_idx: int, c_idx: int, d_idx: int,
) -> str:
    """Build the validation-trace string for ``PatternHit.notes``.

    Records every required vs actual segment and the pass/fail verdict,
    plus the full XABCD indices for the Kotlin mirror.
    """
    ab_actual_pct = (ab / xa * 100.0) if xa else 0.0
    bc_actual_pct = (bc / ab * 100.0) if ab else 0.0
    cd_actual_pct = (cd / bc * 100.0) if bc else 0.0

    ab_ok = _ratio_near(ab / xa, ab_req, tol) if xa else False
    bc_ok = _ratio_near(bc / ab, bc_req, tol) if ab else False
    cd_ok = _ratio_near(cd / bc, cd_req, tol) if bc else False

    return (
        f"XA={xa:.1f} AB={ab_actual_pct:.1f}% "
        f"required={ab_req * 100:.1f} actual={ab_actual_pct:.1f} "
        f"valid={'PASS' if ab_ok else 'FAIL'}; "
        f"BC={bc_actual_pct:.1f}% "
        f"required={bc_req * 100:.1f} actual={bc_actual_pct:.1f} "
        f"valid={'PASS' if bc_ok else 'FAIL'}; "
        f"CD={cd_actual_pct:.1f}% "
        f"required={cd_req * 100:.1f} actual={cd_actual_pct:.1f} "
        f"valid={'PASS' if cd_ok else 'FAIL'}; "
        f"XABCD=({x_idx},{a_idx},{b_idx},{c_idx},{d_idx})"
    )


# ---------------------------------------------------------------------------
# Public detector
# ---------------------------------------------------------------------------

def detect_harmonics(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Detect harmonic patterns (§26-28) in the alternating swing sequence.

    Walks every group of five consecutive swings as a candidate XABCD and
    checks all ratio combinations.  Returns one ``PatternHit`` per matched
    combo (status always FORMING — single-TF detectors cannot confirm LTF
    entry).

    Multiple patterns may match the same swing window; each is emitted as
    a separate hit so downstream consumers can decide which to act on.
    """
    tol = cfg.harmonic_tolerance
    targets = list(cfg.harmonic_targets)
    swings = structure.swings
    n = len(swings)
    hits: list[PatternHit] = []

    if n < 5:
        return hits

    # Walk every consecutive 5-swing window
    for start_idx in range(n - 4):
        X = swings[start_idx]
        A = swings[start_idx + 1]
        B = swings[start_idx + 2]
        C = swings[start_idx + 3]
        D = swings[start_idx + 4]

        # Compute absolute leg lengths (sign-agnostic so bull/bear use the
        # same ratio tables)
        xa = _leg_len(X.price, A.price)
        ab = _leg_len(A.price, B.price)
        bc = _leg_len(B.price, C.price)
        cd = _leg_len(C.price, D.price)

        # Guard against degenerate swings (zero-length legs)
        if xa < 1e-9:
            continue

        # Compute actual ratios
        ab_ratio = ab / xa
        bc_ratio = bc / ab if ab > 1e-9 else 0.0
        cd_ratio = cd / bc if bc > 1e-9 else 0.0

        actual_ratios = (ab_ratio, bc_ratio, cd_ratio)

        # Evaluate every pattern against this window
        for pname, spec in PATTERN_SPECS:
            for req_combo in spec.combos:
                ab_req, bc_req, cd_req = req_combo

                # All three legs must be within tolerance
                if not _ratio_near(ab_ratio, ab_req, tol):
                    continue
                if not _ratio_near(bc_ratio, bc_req, tol):
                    continue
                if not _ratio_near(cd_ratio, cd_req, tol):
                    continue

                # --- Match confirmed ---

                # Direction: GARTLEY is always BULLISH; others determined by
                # D relative to C (below = BULLISH bottom, above = BEARISH top)
                if pname in _ALWAYS_BULLISH:
                    direction = PatternDirection.BULLISH
                else:
                    direction = _direction_from_dcd(D.price, C.price)

                conf = _confidence_for_match(actual_ratios, req_combo, tol)

                # Trade plan (§28):
                #   entry  = Point D price (LTF entry)
                #   neckline_price = Point D
                #   peak_price = Point A (the divergence swing)
                #   targets = fib reversal of BC projected from B/C
                #   stop_loss = prior structural extreme that invalidates

                # Target calculation: fib reversal of BC
                # For BULLISH: project upward from C (the last swing low)
                # For BEARISH: project downward from C (the last swing high)
                if direction is PatternDirection.BULLISH:
                    # Bullish: targets above C
                    target_prices = fib_levels(C.price, C.price + bc, targets)
                else:
                    # Bearish: targets below C
                    target_prices = fib_levels(C.price, C.price - bc, targets)

                # Stop loss: the prior structural extreme
                # Bullish → stop above the X high (invalidation if price exceeds X)
                # Bearish → stop below the X low
                if direction is PatternDirection.BULLISH:
                    stop_loss = X.price  # invalidate if price closes above X
                    invalidation = (
                        f"A candle CLOSES above the X swing high {X.price:.2f} "
                        "(spec §28: harmonic invalidation)"
                    )
                else:
                    stop_loss = X.price
                    invalidation = (
                        f"A candle CLOSES below the X swing low {X.price:.2f} "
                        "(spec §28: harmonic invalidation)"
                    )

                notes = _build_notes(
                    xa, ab, bc, cd,
                    X.price, A.price, B.price, C.price, D.price,
                    ab_req, bc_req, cd_req, tol,
                    X.index, A.index, B.index, C.index, D.index,
                )

                hits.append(PatternHit(
                    name=pname,
                    direction=direction,
                    status=PatternStatus.FORMING,
                    confirm_index=None,        # LTF entry pending
                    neckline_price=D.price,     # entry at D (§28)
                    entry=D.price,
                    stop_loss=stop_loss,
                    targets=target_prices,
                    invalidation=invalidation,
                    peak_price=A.price,         # divergence swing (§28)
                    # Dataclass type is tuple[int,int,int]; store first three
                    # key indices (X, A, B).  Full XABCD in notes.
                    swing_indices=(X.index, A.index, B.index),
                    confidence=conf,
                    notes=notes,
                ))

    return hits


__all__ = [
    "detect_harmonics",
    "fib_levels",
]
