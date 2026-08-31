"""Pattern detectors built on swing structure.

Pure functions: take a SwingStructure (alternating swings + HH/HL/LH/LL labels)
and return pattern hits with a full trade plan (entry / SL / targets) and an
explicit invalidation condition.

This module implements TRADEBOT's strict rules only. Do NOT apply textbook
pattern definitions that are not specified in the engine spec.

Status vocabulary (spec §4): FORMING → FULLY_FORMED → INVALIDATED.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta

from app.engine.config import DEFAULT_PATTERN_CONFIG, PatternConfig
from app.engine.models import EngineCandle, EngineSignal, strength_from_score
from app.engine.swings import Swing, SwingLabel, SwingStructure, analyse
from app.engine.types import (
    PatternStatus,
    PatternDirection,
    PatternHit,
    _between,
    _pct_diff,
    _span_days,
    _find_close_break,
    _any_close_above,
    _any_close_below,
    _confidence,
)

from app.engine.patterns_channel_triangle import (
    detect_ascending_channel,
    detect_descending_channel,
    detect_ascending_triangle,
    detect_descending_triangle,
    detect_symmetrical_triangle,
)
from app.engine.patterns_continuation import (
    detect_bull_flag,
    detect_bear_flag,
    detect_bull_pennant,
    detect_bear_pennant,
    detect_rising_wedge,
    detect_falling_wedge,
    detect_wolfe_wave,
    detect_elliott_wave,
    detect_drive,
    detect_diamond,
)
from app.engine.patterns_cyclic import (
    detect_cyclic_double_top,
    detect_cyclic_double_bottom,
)
from app.engine.patterns_harmonics import (
    detect_harmonics,
    fib_levels,
)
from app.engine.patterns_hs import detect_head_shoulders


def detect_double_top(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Traditional Double Top (spec §8).

    Rules (all mandatory):
    1. Two swing highs (tops/wicks) within ≤ cfg.double_slippage (0.32%) of each other
    2. Time between the two tops is LESS than 9 months
    3. One swing low (valley) between them → neckline
    4. One candle CLOSE below the neckline → FULLY_FORMED; else FORMING
    5. Wick-free confirmation: neckline break counts on CLOSE, not wick
    6. Invalidation: a candle closes above the higher of the two tops
    """
    if len(structure.highs) < 2:
        return []

    hits: list[PatternHit] = []
    highs = structure.highs
    lows = structure.lows

    for i in range(len(highs) - 1):
        peak1 = highs[i]
        peak2 = highs[i + 1]

        # 3. valley strictly between the two tops
        valley = _between(lows, peak1.index, peak2.index)
        if valley is None:
            continue

        # 1. slippage ≤ 0.32%
        avg_peak = (peak1.price + peak2.price) / 2
        if _pct_diff(peak1.price, peak2.price) > cfg.double_slippage:
            continue

        # 2. time between tops < 9 months
        if _span_days(peak1.ts, peak2.ts) >= cfg.double_max_days:
            continue

        # 4. confirmation: one CLOSE beyond the neckline
        neckline = valley.price
        confirm_idx = _find_close_break(
            candles, start=peak2.index + 1, level=neckline,
            direction="below", consecutive=cfg.double_confirm_bars,
        )

        higher_top = max(peak1.price, peak2.price)
        upper_close = _any_close_above(candles, start=peak2.index + 1, level=higher_top)

        if confirm_idx is not None:
            status = PatternStatus.FULLY_FORMED
        elif upper_close:
            status = PatternStatus.INVALIDATED
        else:
            status = PatternStatus.FORMING

        # Trade plan (spec §8): entry = neckline breakout, target = measured height
        height = avg_peak - neckline
        target_1 = neckline - height
        entry = neckline
        stop_loss = higher_top  # structural: price closing above higher top invalidates (configurable)

        conf = _confidence(
            slippage_ratio=_pct_diff(peak1.price, peak2.price) / cfg.double_slippage,
            depth_ratio=(height / avg_peak) / 0.05 if avg_peak else 1.0,
            status=status,
        )

        hits.append(PatternHit(
            name="DOUBLE_TOP",
            direction=PatternDirection.BEARISH,
            status=status,
            confirm_index=confirm_idx,
            neckline_price=neckline,
            entry=entry,
            stop_loss=stop_loss,
            targets=[target_1],
            invalidation=(
                f"A candle CLOSES above the higher top {higher_top:.2f} "
                "(spec §8: structural peak breakout)"
            ),
            peak_price=avg_peak,
            swing_indices=(peak1.index, valley.index, peak2.index),
            confidence=conf,
            notes=(
                f"time_gap_days={_span_days(peak1.ts, peak2.ts):.0f}, "
                f"slippage={_pct_diff(peak1.price, peak2.price):.4%}, "
                f"target=measured_height ({height:.2f})"
            ),
        ))

    return hits


def detect_double_bottom(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Traditional Double Bottom (spec §9) — mirror of Double Top."""
    if len(structure.lows) < 2:
        return []

    hits: list[PatternHit] = []
    lows = structure.lows
    highs = structure.highs

    for i in range(len(lows) - 1):
        valley1 = lows[i]
        valley2 = lows[i + 1]

        peak = _between(highs, valley1.index, valley2.index)
        if peak is None:
            continue

        avg_valley = (valley1.price + valley2.price) / 2
        if _pct_diff(valley1.price, valley2.price) > cfg.double_slippage:
            continue

        if _span_days(valley1.ts, valley2.ts) >= cfg.double_max_days:
            continue

        neckline = peak.price
        confirm_idx = _find_close_break(
            candles, start=valley2.index + 1, level=neckline,
            direction="above", consecutive=cfg.double_confirm_bars,
        )

        lower_bottom = min(valley1.price, valley2.price)
        lower_close = _any_close_below(candles, start=valley2.index + 1, level=lower_bottom)

        if confirm_idx is not None:
            status = PatternStatus.FULLY_FORMED
        elif lower_close:
            status = PatternStatus.INVALIDATED
        else:
            status = PatternStatus.FORMING

        height = neckline - avg_valley
        target_1 = neckline + height
        entry = neckline
        stop_loss = lower_bottom

        conf = _confidence(
            slippage_ratio=_pct_diff(valley1.price, valley2.price) / cfg.double_slippage,
            depth_ratio=(height / avg_valley) / 0.05 if avg_valley else 1.0,
            status=status,
        )

        hits.append(PatternHit(
            name="DOUBLE_BOTTOM",
            direction=PatternDirection.BULLISH,
            status=status,
            confirm_index=confirm_idx,
            neckline_price=neckline,
            entry=entry,
            stop_loss=stop_loss,
            targets=[target_1],
            invalidation=(
                f"A candle CLOSES below the lower bottom {lower_bottom:.2f} "
                "(spec §9: structural valley breakout)"
            ),
            peak_price=avg_valley,
            swing_indices=(valley1.index, peak.index, valley2.index),
            confidence=conf,
            notes=(
                f"time_gap_days={_span_days(valley1.ts, valley2.ts):.0f}, "
                f"slippage={_pct_diff(valley1.price, valley2.price):.4%}, "
                f"target=measured_height ({height:.2f})"
            ),
        ))

    return hits


def detect_patterns(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Run all pattern detectors and return combined hits (newest first)."""
    all_hits: list[PatternHit] = []
    # Core (spec §8-9)
    all_hits.extend(detect_double_top(structure, candles, cfg))
    all_hits.extend(detect_double_bottom(structure, candles, cfg))
    # H&S (spec §5-6)
    all_hits.extend(detect_head_shoulders(structure, candles, cfg))
    # Cyclic (spec §10)
    all_hits.extend(detect_cyclic_double_top(structure, candles, cfg))
    all_hits.extend(detect_cyclic_double_bottom(structure, candles, cfg))
    # Channels & Triangles (spec §11-15)
    all_hits.extend(detect_ascending_channel(structure, candles, cfg))
    all_hits.extend(detect_descending_channel(structure, candles, cfg))
    all_hits.extend(detect_ascending_triangle(structure, candles, cfg))
    all_hits.extend(detect_descending_triangle(structure, candles, cfg))
    all_hits.extend(detect_symmetrical_triangle(structure, candles, cfg))
    # Continuation (spec §16-25)
    all_hits.extend(detect_bull_flag(structure, candles, cfg))
    all_hits.extend(detect_bear_flag(structure, candles, cfg))
    all_hits.extend(detect_bull_pennant(structure, candles, cfg))
    all_hits.extend(detect_bear_pennant(structure, candles, cfg))
    all_hits.extend(detect_rising_wedge(structure, candles, cfg))
    all_hits.extend(detect_falling_wedge(structure, candles, cfg))
    all_hits.extend(detect_wolfe_wave(structure, candles, cfg))
    all_hits.extend(detect_elliott_wave(structure, candles, cfg))
    all_hits.extend(detect_drive(structure, candles, cfg))
    all_hits.extend(detect_diamond(structure, candles, cfg))
    # Harmonics (spec §26-29)
    all_hits.extend(detect_harmonics(structure, candles, cfg))
    all_hits.sort(key=lambda h: (h.confirm_index or 0, h.name), reverse=True)
    return all_hits


# ── output mapping (spec §32 / §35) ──────────────────────────────────────────

def detected_label(hit: PatternHit) -> str:
    """pattern_detected string per spec §32 ('Name' / 'Forming - Name' / 'None')."""
    if hit.status is PatternStatus.FULLY_FORMED:
        return hit.name
    if hit.status is PatternStatus.FORMING:
        return f"Forming - {hit.name}"
    return f"Invalidated - {hit.name}"


def hit_to_json(hit: PatternHit) -> dict:
    """Spec §35 output shape — strings for prices, exact invalidation, traceable reasoning."""
    def _price(x: float | None) -> str:
        return f"{x:.2f}" if x is not None else "N/A"

    targets = hit.targets or []

    def _t(i: int) -> str:
        if i < len(targets):
            label = " (measured height)" if len(targets) == 1 else ""
            return _price(targets[i]) + label
        return "N/A"

    return {
        "pattern": hit.name,
        "pattern_detected": detected_label(hit),
        "status": hit.status.value,
        "direction": hit.direction.value,
        "confidence": hit.confidence,
        "entry": _price(hit.entry),
        "stop_loss": _price(hit.stop_loss),
        "target_1": _t(0),
        "target_2": _t(1),
        "target_3": _t(2),
        "invalidation": hit.invalidation,
        "additional_notes": hit.notes,
        "reasoning": _reasoning(hit),
        # machine-readable extras for chart markers / the mobile engine
        "neckline_price": hit.neckline_price,
        "peak_price": hit.peak_price,
        "swing_indices": list(hit.swing_indices),
        "confirm_index": hit.confirm_index,
    }


def _reasoning(hit: PatternHit) -> str:
    p0, pv, p1 = hit.swing_indices
    trace = (f"{hit.name}: swings at indices {p0}/{pv}/{p1}; "
             f"neckline={hit.neckline_price:.2f}; "
             f"status={hit.status.value} "
             f"(confirm_index={hit.confirm_index if hit.confirm_index is not None else '—'}).")
    if hit.notes:
        trace += f" {hit.notes}."
    return trace


def hit_to_engine_signal(
    instrument_id: object,
    timeframe: str,
    hit: PatternHit,
    detected_at: object,
) -> EngineSignal:
    """Maps a hit onto the shared `signals` row (signal_type=PATTERN).

    TRADEBOT status → SignalStatus, so the existing lifecycle pipeline treats
    FULLY_FORMED (CONFIRMED) as the terminal confirmation state:
        FORMING      → DETECTING
        FULLY_FORMED → CONFIRMED
        INVALIDATED  → INVALIDATED
    `bof_level` holds the neckline (the pattern's key trade level).
    """
    status_map = {
        PatternStatus.FORMING: "DETECTING",
        PatternStatus.FULLY_FORMED: "CONFIRMED",
        PatternStatus.INVALIDATED: "INVALIDATED",
    }
    return EngineSignal(
        instrument_id=instrument_id,
        timeframe=timeframe,
        signal_type="PATTERN",
        direction=hit.direction.value,
        bof_level=hit.neckline_price,
        breakout_price=hit.entry,
        failure_price=None,
        entry_price=hit.entry,
        stop_reference=hit.stop_loss,
        confidence=hit.confidence,
        strength=strength_from_score(hit.confidence * 100.0),
        status=status_map[hit.status],
        detected_at=detected_at,
        confirmed_at=detected_at if hit.status is PatternStatus.FULLY_FORMED else None,
        metadata=hit_to_json(hit),
    )


# ── helpers ─────────────────────────────────────────────────────────────────

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


def _confidence(slippage_ratio: float, depth_ratio: float, status: PatternStatus) -> float:
    """Rule-satisfaction score in [0,1]. Tighter slippage + deeper valley → higher.

    FORMING hits cap at 0.5 (structure there, confirmation pending); levels that
    reach FULLY_FORMED or INVALIDATED are scored by geometry only.
    """
    slip_score = max(0.0, 1.0 - slippage_ratio)
    depth_score = min(1.0, depth_ratio)
    geo = 0.6 * slip_score + 0.4 * depth_score
    if status is PatternStatus.FORMING:
        geo *= 0.5
    return round(max(0.0, min(1.0, geo)), 3)


__all__ = [
    "PatternStatus",
    "PatternDirection",
    "PatternHit",
    "detect_double_top",
    "detect_double_bottom",
    "detect_patterns",
    "detected_label",
    "hit_to_json",
    "hit_to_engine_signal",
]