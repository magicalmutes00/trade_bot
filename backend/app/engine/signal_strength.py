"""Strength scoring (docs/bof-engine.md §Strength score)."""

from collections.abc import Sequence

from app.engine.config import BOFConfig, DEFAULT_CONFIG
from app.engine.failure_detector import FailureResult
from app.engine.models import EngineCandle, Side, strength_from_score


def _sma(values: Sequence[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def score(
    candles: Sequence[EngineCandle],
    result: FailureResult,
    cfg: BOFConfig = DEFAULT_CONFIG,
) -> tuple[float, dict[str, float]]:
    """Composite 0–100 score with per-factor breakdown (audit trail)."""
    cand = result.candidate
    lvl = cand.level

    # 1. re-entry speed — faster failure = stronger trap
    bars_to_resolve = (
        (result.failure_index - cand.breakout_index)
        if result.failure_index is not None
        else cfg.failure_window
    )
    speed = max(0.0, 1.0 - bars_to_resolve / cfg.failure_window)

    # 2. penetration depth — normalised against the cap
    depth = min(cand.max_excursion / cfg.depth_cap_pct, 1.0)

    # 3. volume expansion on the breakout bar vs SMA20(volume)
    vol_factor = 0.5  # neutral default when volume history is unavailable
    if cand.breakout_index >= cfg.volume_sma:
        window = candles[cand.breakout_index - cfg.volume_sma : cand.breakout_index]
        avg = sum(c.volume or 0.0 for c in window) / cfg.volume_sma
        if avg > 0:
            vol_factor = min(
                (candles[cand.breakout_index].volume or 0.0) / avg / cfg.vol_expansion_cap,
                1.0,
            )

    # 4. wick rejection on the resolution bar
    wick = 0.0
    if result.failure_index is not None:
        c = candles[result.failure_index]
        rng = c.high - c.low
        if rng > 0:
            raw = (
                (c.high - max(c.open, c.close)) / rng
                if cand.side is Side.UP
                else (min(c.open, c.close) - c.low) / rng
            )
            wick = max(0.0, min(raw, 1.0))

    # 5. trend context — counter-trend traps score higher
    trend = 0.5  # neutral when insufficient history
    closes = [c.close for c in candles[: cand.breakout_index]]
    sma20, sma50 = _sma(closes, 20), _sma(closes, 50)
    if sma20 is not None and sma50 is not None and sma50 != 0:
        uptrend = sma20 > sma50
        trend = 1.0 if (
            (cand.side is Side.UP and not uptrend) or (cand.side is Side.DOWN and uptrend)
        ) else 0.0

    factors = {
        "speed": round(speed, 4),
        "depth": round(depth, 4),
        "volume": round(vol_factor, 4),
        "wick": round(wick, 4),
        "trend": round(trend, 4),
    }
    total = (
        cfg.w_speed * speed
        + cfg.w_depth * depth
        + cfg.w_volume * vol_factor
        + cfg.w_wick * wick
        + cfg.w_trend * trend
    ) * 100.0
    return round(total, 2), factors


__all__ = ["score", "strength_from_score"]
