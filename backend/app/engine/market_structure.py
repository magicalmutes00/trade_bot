"""Fractal-pivot market structure: confirmed swing highs/lows = BOF levels."""

from collections.abc import Sequence

from app.engine.config import DEFAULT_CONFIG
from app.engine.models import EngineCandle, Pivot, Side


def confirm_pivots(
    candles: Sequence[EngineCandle],
    *,
    left: int = DEFAULT_CONFIG.pivot_left,
    right: int = DEFAULT_CONFIG.pivot_right,
) -> list[Pivot]:
    """Return pivots confirmed by `right` subsequent bars (no lookahead).

    Swing high at i  → high[i] strictly greater than every high to its left
    within the window and greater-or-equal to every high to its right (ties
    resolve to the leftmost bar). Swing low is the mirror image.
    """
    out: list[Pivot] = []
    n = len(candles)
    for i in range(left, n - right):
        c = candles[i]
        left_block = candles[i - left : i]
        right_block = candles[i + 1 : i + right + 1]

        if all(c.high > w.high for w in left_block) and all(c.high >= w.high for w in right_block):
            out.append(Pivot(ts=c.ts, index=i, price=c.high, side=Side.UP))

        if all(c.low < w.low for w in left_block) and all(c.low <= w.low for w in right_block):
            out.append(Pivot(ts=c.ts, index=i, price=c.low, side=Side.DOWN))

    out.sort(key=lambda p: p.index)
    return out


def active_levels(
    pivots: Sequence[Pivot],
    candles: Sequence[EngineCandle],
    as_of_index: int,
) -> dict[Side, Pivot]:
    """Most recent unmitigated pivot per side strictly before `as_of_index`.

    A pivot stays active until some candle between its formation and now has
    CLOSED through it (close > high-pivot or close < low-pivot).
    """
    result: dict[Side, Pivot] = {}
    for p in reversed(pivots):  # newest first
        if p.index >= as_of_index or p.side in result:
            continue
        mitigated = any(
            (c.close > p.price) if p.side is Side.UP else (c.close < p.price)
            for c in candles[p.index + 1 : as_of_index]
        )
        if not mitigated:
            result[p.side] = p
        if len(result) == len(Side):
            break
    return result


__all__ = ["confirm_pivots", "active_levels"]
