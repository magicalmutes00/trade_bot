"""Cyclic double top / double bottom detectors (TRADEBOT spec §10).

These are SEPARATE from the Traditional double top/bottom (§8/§9). The cyclic
method trades a LONG time separation (>= 9 months, UNLIMITED maximum) instead
of the traditional < 9-month window, and does NOT require a neckline.

Because this pure single-timeframe detector cannot observe a lower-timeframe
(LTF) trend reversal, and §10 makes an LTF reversal the *entry* trigger, every
pattern reported here is marked FORMING with an explicit note that the LTF
entry confirmation is pending. We never mark FULLY_FORMED from single-TF
structure alone.

Deterministic, no I/O. Logic is kept deliberately simple and mirrors the
Kotlin port.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.engine.config import DEFAULT_PATTERN_CONFIG, PatternConfig
from app.engine.models import EngineCandle
from app.engine.patterns import (
    PatternStatus, PatternDirection, PatternHit,
    _pct_diff, _span_days, _find_close_break, _between, _any_close_above,
    _any_close_below, _confidence,
)
from app.engine.swings import Swing, SwingStructure


@dataclass(frozen=True)
class CyclicConfig:
    """Thresholds for the cyclic method (§10), separate from the traditional
    PatternConfig. Not neckline-based, so slippage is looser and the minimum
    duration is the defining rule."""
    cyclic_slippage: float = 0.0125    # <= 1.25% slippage between the two peaks / bottoms
    cyclic_min_days: float = 274.0     # >= 9 months between the two tops / bottoms (max UNLIMITED)
    cyclic_confirm_bars: int = 1       # reserved: one LTF reversal bar (not observable here)


DEFAULT_CYCLIC_CONFIG = CyclicConfig()


# Cyclic double top / bottom are neckline-less -> the "reference range" is the
# average of the two extrema. Targets are simple % projections of that range:
#   bottom: from the valley upward, target_n = avg_valley * (1 + k)
#   top:    from the peak downward,  target_n = avg_peak  * (1 - k)
_CYCLIC_BOTTOM_KS = (0.20, 0.30, 0.60, 0.80, 1.00)  # 20%, 30%, 60%, 80%, 100%
_CYCLIC_TOP_KS = (0.20, 0.40, 0.60)                # 20%, 40%, 60%


def detect_cyclic_double_top(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Cyclic Double Top (spec §10).

    Rules (all mandatory, and distinct from the Traditional method §8):
    1. Two swing highs >= cfg.cyclic_min_days (9 months) apart; NO max duration.
    2. Slippage between the two tops <= cfg.cyclic_slippage (1.25%).
    3. NO neckline required, NO neckline breakout for status.
    4. Entry requires a lower-timeframe trend reversal; unobservable here, so
       every pattern is reported FORMING (LTF confirmation pending).
    5. Invalidation: a candle CLOSES above the higher of the two tops.
    """
    if len(structure.highs) < 2:
        return []

    hits: list[PatternHit] = []
    highs = structure.highs
    lows = structure.lows

    for i in range(len(highs) - 1):
        peak1 = highs[i]
        peak2 = highs[i + 1]

        # The valley between the tops is NOT a neckline (no breakout needed),
        # but it must structurally sit between the two tops.
        valley = _between(lows, peak1.index, peak2.index)
        if valley is None:
            continue

        # 2. slippage <= 1.25% (cyclic threshold from CyclicConfig)
        avg_peak = (peak1.price + peak2.price) / 2
        if _pct_diff(peak1.price, peak2.price) > DEFAULT_CYCLIC_CONFIG.cyclic_slippage:
            continue

        # 1. time between tops >= 9 months (max UNLIMITED); cyclic threshold
        if _span_days(peak1.ts, peak2.ts) < DEFAULT_CYCLIC_CONFIG.cyclic_min_days:
            continue

        # 4. LTF reversal not observable on a single timeframe -> FORMING.
        status = PatternStatus.FORMING

        # Trade plan (§10): neckline-less. Targets project the % levels of the
        # avg peak downward; the LTF reversal sets the true entry later.
        targets = [avg_peak * (1 - k) for k in _CYCLIC_TOP_KS]
        entry = valley.price               # reference level (LTF-reversal entry pending)
        higher_top = max(peak1.price, peak2.price)
        stop_loss = higher_top             # structural: closing above invalidates

        conf = _confidence(
            slippage_ratio=_pct_diff(peak1.price, peak2.price) / DEFAULT_CYCLIC_CONFIG.cyclic_slippage,
            depth_ratio=((avg_peak - valley.price) / avg_peak) / 0.05 if avg_peak else 1.0,
            status=status,
        )

        hits.append(PatternHit(
            name="CYCLIC_DOUBLE_TOP",
            direction=PatternDirection.BEARISH,
            status=status,
            confirm_index=None,                        # pending LTF reversal confirmation
            neckline_price=valley.price,               # reference valley (no neckline rule)
            entry=entry,
            stop_loss=stop_loss,
            targets=targets,
            invalidation=(
                f"A candle CLOSES above the higher cyclic top {higher_top:.2f} (spec §10)"
            ),
            peak_price=avg_peak,
            swing_indices=(peak1.index, valley.index, peak2.index),
            confidence=conf,
            notes=(
                f"CYCLIC: time_gap_days={_span_days(peak1.ts, peak2.ts):.0f} >= 9 months, "
                f"slippage={_pct_diff(peak1.price, peak2.price):.4%} (no neckline), "
                f"status=FORMING; LTF trend-reversal entry confirmation pending"
            ),
        ))

    return hits


def detect_cyclic_double_bottom(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Cyclic Double Bottom (spec §10) — mirror of Cyclic Double Top.

    1. Two swing lows >= 9 months apart; NO max duration.
    2. Slippage between the two bottoms <= 1.25%.
    3. NO neckline required.
    4. LTF reversal entry confirmation pending -> FORMING.
    5. Invalidation: a candle CLOSES below the lower of the two bottoms.
    """
    if len(structure.lows) < 2:
        return []

    hits: list[PatternHit] = []
    lows = structure.lows
    highs = structure.highs

    for i in range(len(lows) - 1):
        valley1 = lows[i]
        valley2 = lows[i + 1]

        # The peak between the bottoms is a reference, NOT a neckline.
        peak = _between(highs, valley1.index, valley2.index)
        if peak is None:
            continue

        # 2. slippage <= 1.25% (cyclic threshold from CyclicConfig)
        avg_valley = (valley1.price + valley2.price) / 2
        if _pct_diff(valley1.price, valley2.price) > DEFAULT_CYCLIC_CONFIG.cyclic_slippage:
            continue

        # 1. time between bottoms >= 9 months (max UNLIMITED); cyclic threshold
        if _span_days(valley1.ts, valley2.ts) < DEFAULT_CYCLIC_CONFIG.cyclic_min_days:
            continue

        # 4. LTF reversal not observable on a single timeframe -> FORMING.
        status = PatternStatus.FORMING

        # Trade plan (§10): neckline-less. Targets project the % levels of the
        # avg valley upward; the LTF reversal sets the true entry later.
        targets = [avg_valley * (1 + k) for k in _CYCLIC_BOTTOM_KS]
        entry = peak.price                  # reference level (LTF-reversal entry pending)
        lower_bottom = min(valley1.price, valley2.price)
        stop_loss = lower_bottom            # structural: closing below invalidates

        conf = _confidence(
            slippage_ratio=_pct_diff(valley1.price, valley2.price) / DEFAULT_CYCLIC_CONFIG.cyclic_slippage,
            depth_ratio=((peak.price - avg_valley) / avg_valley) / 0.05 if avg_valley else 1.0,
            status=status,
        )

        hits.append(PatternHit(
            name="CYCLIC_DOUBLE_BOTTOM",
            direction=PatternDirection.BULLISH,
            status=status,
            confirm_index=None,                        # pending LTF reversal confirmation
            neckline_price=peak.price,                 # reference peak (no neckline rule)
            entry=entry,
            stop_loss=stop_loss,
            targets=targets,
            invalidation=(
                f"A candle CLOSES below the lower cyclic bottom {lower_bottom:.2f} (spec §10)"
            ),
            peak_price=avg_valley,
            swing_indices=(valley1.index, peak.index, valley2.index),
            confidence=conf,
            notes=(
                f"CYCLIC: time_gap_days={_span_days(valley1.ts, valley2.ts):.0f} >= 9 months, "
                f"slippage={_pct_diff(valley1.price, valley2.price):.4%} (no neckline), "
                f"status=FORMING; LTF trend-reversal entry confirmation pending"
            ),
        ))

    return hits


__all__ = [
    "CyclicConfig",
    "DEFAULT_CYCLIC_CONFIG",
    "detect_cyclic_double_top",
    "detect_cyclic_double_bottom",
]
