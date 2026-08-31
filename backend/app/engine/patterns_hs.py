"""Head & Shoulders pattern detectors (TRADEBOT spec §5, §6).

Detects BOTH bearish Head & Shoulders (§5) and bullish Inverted Head &
Shoulders (§6). Pure functions: take a SwingStructure (alternating swings) and
return PatternHit list with a full trade plan and an explicit invalidation.

This module mirrors ``app.engine.patterns`` style and is the backend source of
truth — the Kotlin port mirrors this file EXACTLY, so the logic is kept simple,
deterministic and well-commented. Do NOT apply textbook TA on top of the spec.

Spec rules enforced here (§5 / §6):
  - Head must be distinguishably the highest (bearish) / lowest (bullish)
    point: head >= (1 + tolerance) x average shoulder height (bearish), or
    head <= (1 - tolerance) x average shoulder height (bullish).
  - The two swing lows (peaks) between the shoulders define the neckline.
  - Entry only after a candle CLOSE beyond the neckline -> FULLY_FORMED;
    before the break -> FORMING (no confirmed entry).
  - Stop loss = right shoulder extreme; a CLOSE beyond it invalidates.
  - Target 1 = measured height reversed beyond the neckline.
  - Target 2 = pattern start (the left shoulder's prior swing of opposite side).
"""

from collections.abc import Sequence

from app.engine.config import DEFAULT_PATTERN_CONFIG, PatternConfig
from app.engine.models import EngineCandle
from app.engine.patterns import (
    PatternDirection,
    PatternHit,
    PatternStatus,
    _any_close_above,
    _any_close_below,
    _between,
    _confidence,
    _find_close_break,
    _span_days,
)
from app.engine.swings import Swing, SwingStructure


def detect_head_shoulders(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig = DEFAULT_PATTERN_CONFIG,
) -> list[PatternHit]:
    """Detect bearish H&S (§5) and bullish inverted H&S (§6) and return hits."""
    hits: list[PatternHit] = []
    hits.extend(_detect_bearish_hs(structure, candles, cfg))
    hits.extend(_detect_bullish_inverted_hs(structure, candles, cfg))
    return hits


def _detect_bearish_hs(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig,
) -> list[PatternHit]:
    """Bearish Head & Shoulders (spec §5)."""
    highs = structure.highs
    lows = structure.lows
    if len(highs) < 3:
        return []

    hits: list[PatternHit] = []
    for i in range(len(highs) - 2):
        ls = highs[i]        # left shoulder
        head = highs[i + 1]  # head
        rs = highs[i + 2]    # right shoulder

        # §5: head must be the highest, distinguishably above the shoulders.
        avg_shoulder = (ls.price + rs.price) / 2
        if head.price <= avg_shoulder * (1 + cfg.hs_shoulder_tolerance):
            continue

        # Noise filter: minimum candle spacing between the pattern swing points.
        if abs(head.index - ls.index) < cfg.hs_min_bars_between:
            continue
        if abs(rs.index - head.index) < cfg.hs_min_bars_between:
            continue

        # §5: the two valley lows between the shoulders define the neckline.
        v1 = _between(lows, ls.index, head.index)  # valley after left shoulder
        v2 = _between(lows, head.index, rs.index)  # valley after the head
        if v1 is None or v2 is None:
            continue

        # Neckline (trendline) = flat mean of the two valley lows.
        neckline = (v1.price + v2.price) / 2
        height = head.price - neckline
        if height <= 0:
            continue

        # §5: requires an uptrend into the pattern — at least one prior swing
        # high lower than the left shoulder (price was rising into the LS).
        uptrend_ok = any(h.price < ls.price for h in highs if h.index < ls.index)
        if not uptrend_ok:
            continue

        # Targets: height measured from the neckline, reversed below it.
        target_1 = neckline - height                      # measured move below
        start = _find_prior_swing_price(lows, ls.index)   # pattern start price
        targets = [target_1] + ([start] if start is not None else [])

        # Stop loss: right shoulder top (a close above it invalidates).
        stop_loss = rs.price

        # Confirmation: one candle CLOSE below the neckline after the RS.
        confirm_idx = _find_close_break(
            candles, start=rs.index + 1, level=neckline,
            direction="below", consecutive=cfg.hs_confirm_bars,
        )
        upper_close = _any_close_above(candles, start=rs.index + 1, level=rs.price)

        if confirm_idx is not None:
            status = PatternStatus.FULLY_FORMED
        elif upper_close:
            status = PatternStatus.INVALIDATED
        else:
            status = PatternStatus.FORMING

        # Confidence: how far the head stands above the shoulders (tolerance
        # normalised) + how deep the pattern is relative to the neckline.
        head_margin = ((head.price - avg_shoulder) / avg_shoulder) if avg_shoulder else 0.0
        slippage_ratio = min(cfg.hs_shoulder_tolerance / head_margin, 2.0) if head_margin > 0 else 1.0
        depth_ratio = (height / neckline) / 0.05 if neckline else 1.0
        conf = _confidence(slippage_ratio=slippage_ratio, depth_ratio=depth_ratio, status=status)

        hits.append(PatternHit(
            name="HEAD_AND_SHOULDERS",
            direction=PatternDirection.BEARISH,
            status=status,
            confirm_index=confirm_idx,
            neckline_price=neckline,
            entry=neckline,
            stop_loss=stop_loss,
            targets=targets,
            invalidation=(
                f"A candle CLOSES above the right shoulder top {rs.price:.2f} "
                "(spec §5 right-shoulder breakout)"
            ),
            peak_price=head.price,
            swing_indices=(ls.index, head.index, rs.index),
            confidence=conf,
            notes=(
                f"head_above_shoulders, neckline={neckline:.2f}, "
                f"time_gap_days={_span_days(ls.ts, rs.ts):.0f}, "
                f"target=measured_height"
            ),
        ))

    return hits


def _detect_bullish_inverted_hs(
    structure: SwingStructure,
    candles: Sequence[EngineCandle],
    cfg: PatternConfig,
) -> list[PatternHit]:
    """Bullish Inverted Head & Shoulders (spec §6) — mirror of §5."""
    highs = structure.highs
    lows = structure.lows
    if len(lows) < 3:
        return []

    hits: list[PatternHit] = []
    for i in range(len(lows) - 2):
        ls = lows[i]        # left shoulder (higher low)
        head = lows[i + 1]  # head (lowest point)
        rs = lows[i + 2]    # right shoulder (higher low)

        # §6: head must be the lowest, distinguishably below the shoulders.
        avg_shoulder = (ls.price + rs.price) / 2
        if head.price >= avg_shoulder * (1 - cfg.hs_shoulder_tolerance):
            continue

        # Noise filter: minimum candle spacing between the pattern swing points.
        if abs(head.index - ls.index) < cfg.hs_min_bars_between:
            continue
        if abs(rs.index - head.index) < cfg.hs_min_bars_between:
            continue

        # §6: the two swing highs between the shoulders define the neckline.
        p1 = _between(highs, ls.index, head.index)  # peak after left shoulder
        p2 = _between(highs, head.index, rs.index)  # peak after the head
        if p1 is None or p2 is None:
            continue

        # Neckline (trendline) = flat mean of the two peak highs.
        neckline = (p1.price + p2.price) / 2
        height = neckline - head.price
        if height <= 0:
            continue

        # §6: requires a downtrend into the pattern — at least one prior swing
        # low higher than the left shoulder (price was falling into the LS).
        downtrend_ok = any(l.price > ls.price for l in lows if l.index < ls.index)
        if not downtrend_ok:
            continue

        # Targets: height measured from the neckline, reversed above it.
        target_1 = neckline + height                      # measured move above
        start = _find_prior_swing_price(highs, ls.index)  # pattern start price
        targets = [target_1] + ([start] if start is not None else [])

        # Stop loss: right shoulder bottom (a close below it invalidates).
        stop_loss = rs.price

        # Confirmation: one candle CLOSE above the neckline after the RS.
        confirm_idx = _find_close_break(
            candles, start=rs.index + 1, level=neckline,
            direction="above", consecutive=cfg.hs_confirm_bars,
        )
        lower_close = _any_close_below(candles, start=rs.index + 1, level=rs.price)

        if confirm_idx is not None:
            status = PatternStatus.FULLY_FORMED
        elif lower_close:
            status = PatternStatus.INVALIDATED
        else:
            status = PatternStatus.FORMING

        # Confidence: how far the head stands below the shoulders + pattern depth.
        head_margin = ((avg_shoulder - head.price) / avg_shoulder) if avg_shoulder else 0.0
        slippage_ratio = min(cfg.hs_shoulder_tolerance / head_margin, 2.0) if head_margin > 0 else 1.0
        depth_ratio = (height / neckline) / 0.05 if neckline else 1.0
        conf = _confidence(slippage_ratio=slippage_ratio, depth_ratio=depth_ratio, status=status)

        hits.append(PatternHit(
            name="INVERTED_HEAD_AND_SHOULDERS",
            direction=PatternDirection.BULLISH,
            status=status,
            confirm_index=confirm_idx,
            neckline_price=neckline,
            entry=neckline,
            stop_loss=stop_loss,
            targets=targets,
            invalidation=(
                f"A candle CLOSES below the right shoulder bottom {rs.price:.2f} "
                "(spec §6 right-shoulder breakdown)"
            ),
            peak_price=head.price,
            swing_indices=(ls.index, head.index, rs.index),
            confidence=conf,
            notes=(
                f"head_below_shoulders, neckline={neckline:.2f}, "
                f"time_gap_days={_span_days(ls.ts, rs.ts):.0f}, "
                f"target=measured_height"
            ),
        ))

    return hits


def _find_prior_swing_price(swings: Sequence[Swing], shoulder_index: int) -> float | None:
    """Price of the swing immediately before the left shoulder (pattern start)."""
    prev: Swing | None = None
    for sw in swings:
        if sw.index >= shoulder_index:
            break
        prev = sw
    return prev.price if prev is not None else None


__all__ = ["detect_head_shoulders"]
