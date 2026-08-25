"""Breakout detection — single-pass O(n) over candles + precomputed pivots.

A pivot becomes *confirmed* `right` bars after it forms (no lookahead).
Each bar, freshly-confirmed pivots replace the previous same-side level.
Any close through the level mitigates it; only closes through it by at least
`min_break_pct` additionally spawn a BreakoutCandidate (wicks never count).
"""

from collections import defaultdict
from collections.abc import Sequence

from app.engine.config import BOFConfig, DEFAULT_CONFIG
from app.engine.models import BreakoutCandidate, EngineCandle, Pivot, Side


def group_pivots_by_confirmation(pivots: Sequence[Pivot], right: int) -> dict[int, list[Pivot]]:
    """Pivot formed at index p is usable from index p + right."""
    out: defaultdict[int, list[Pivot]] = defaultdict(list)
    for p in pivots:
        out[p.index + right].append(p)
    return dict(out)


def detect_breakouts(
    candles: Sequence[EngineCandle],
    pivots: Sequence[Pivot],
    cfg: BOFConfig = DEFAULT_CONFIG,
) -> list[BreakoutCandidate]:
    due = group_pivots_by_confirmation(pivots, cfg.pivot_right)
    levels: dict[Side, Pivot] = {}
    candidates: list[BreakoutCandidate] = []
    vol_sma = _rolling_volume_sma(candles, cfg.volume_sma)

    for i, c in enumerate(candles):
        for p in due.get(i, ()):  # confirm pivots whose window completes here
            levels[p.side] = p

        for side in (Side.UP, Side.DOWN):
            level_pivot = levels.get(side)
            if level_pivot is None:
                continue
            lvl = level_pivot.price

            if side is Side.UP:
                through = c.close > lvl
                strong_through = c.close >= lvl * (1 + cfg.min_break_pct)
            else:
                through = c.close < lvl
                strong_through = c.close <= lvl * (1 - cfg.min_break_pct)

            if not through:
                continue

            levels.pop(side)  # any close through mitigates the level

            if not strong_through:
                continue
            if not _volume_ok(c, vol_sma[i], cfg.volume_mult_min):
                continue

            exc = (c.close - lvl) / lvl if side is Side.UP else (lvl - c.close) / lvl
            candidates.append(
                BreakoutCandidate(
                    side=side,
                    level=lvl,
                    level_ts=level_pivot.ts,
                    breakout_index=i,
                    breakout_ts=c.ts,
                    breakout_close=c.close,
                    max_excursion=exc,
                )
            )

    return candidates


def update_excursions(
    candles: Sequence[EngineCandle],
    candidate: BreakoutCandidate,
    upto_index: int,
) -> float:
    """Track furthest excursion beyond the level while the candidate lives."""
    best = candidate.max_excursion
    for c in candles[candidate.breakout_index + 1 : upto_index + 1]:
        exc = (
            (c.high - candidate.level) / candidate.level
            if candidate.side is Side.UP
            else (candidate.level - c.low) / candidate.level
        )
        best = max(best, exc)
    return best


def _volume_ok(candle: EngineCandle, avg_volume: float | None, mult_min: float) -> bool:
    if mult_min <= 0 or not avg_volume:
        return True
    return candle.volume >= mult_min * avg_volume


def _rolling_volume_sma(candles: Sequence[EngineCandle], window: int) -> list[float | None]:
    prefix = [0.0]
    for c in candles:
        prefix.append(prefix[-1] + (c.volume or 0.0))
    out: list[float | None] = []
    for i in range(len(candles)):
        out.append(None if i < window else (prefix[i] - prefix[i - window]) / window)
    return out


__all__ = ["detect_breakouts", "group_pivots_by_confirmation", "update_excursions"]
