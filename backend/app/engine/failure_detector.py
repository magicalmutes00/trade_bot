"""Failure resolution: does a breakout fail back through its level in time?

For each candidate, scan the `failure_window` bars after the breakout bar:
- first opposite-side close through the level → CONFIRMED failure
- a further same-side close ≥ rebreak_pct beyond the level → INVALIDATED
- window elapses with neither → INVALIDATED (timeout)
Candidates still inside their window at series end remain DETECTING.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
import math

from app.engine.config import BOFConfig, DEFAULT_CONFIG
from app.engine.models import BreakoutCandidate, EngineCandle, Side


class Outcome(str, Enum):
    CONFIRMED = "CONFIRMED"
    INVALIDATED_TIMEOUT = "INVALIDATED_TIMEOUT"
    INVALIDATED_REBREAK = "INVALIDATED_REBREAK"
    DETECTING = "DETECTING"


@dataclass(frozen=True)
class FailureResult:
    candidate: BreakoutCandidate
    outcome: Outcome
    failure_index: int | None = None
    failure_close: float | None = None
    stop_reference: float | None = None


def resolve_failure(
    candles: Sequence[EngineCandle],
    candidates: Sequence[BreakoutCandidate],
    cfg: BOFConfig = DEFAULT_CONFIG,
) -> list[FailureResult]:
    results: list[FailureResult] = []
    last_index = len(candles) - 1

    for cand in candidates:
        lvl = cand.level
        window_end = min(cand.breakout_index + cfg.failure_window, last_index)

        stop = cand.breakout_close
        # Track how far price has pulled back TOWARD the level since breakout;
        # a re-break invalidation only counts once price has approached the
        # level and then violently extended again past the rebreak threshold.
        best_pullback = math.inf if cand.side is Side.UP else -math.inf
        outcome: Outcome | None = None
        f_idx: int | None = None
        f_close: float | None = None

        for i in range(cand.breakout_index + 1, window_end + 1):
            c = candles[i]
            if cand.side is Side.UP:
                stop = max(stop, c.high)
                best_pullback = min(best_pullback, c.close)
                failed_back = c.close < lvl
                rebreak = best_pullback <= lvl * (1 + cfg.min_break_pct) and c.close >= lvl * (1 + cfg.rebreak_pct)
            else:
                stop = min(stop, c.low)
                best_pullback = max(best_pullback, c.close)
                failed_back = c.close > lvl
                rebreak = best_pullback >= lvl * (1 - cfg.min_break_pct) and c.close <= lvl * (1 - cfg.rebreak_pct)

            if failed_back:
                outcome, f_idx, f_close = Outcome.CONFIRMED, i, c.close
                break
            if rebreak:
                outcome = Outcome.INVALIDATED_REBREAK
                f_idx, f_close = i, c.close
                break

        if outcome is None:
            outcome = (
                Outcome.DETECTING
                if cand.breakout_index + cfg.failure_window > last_index
                else Outcome.INVALIDATED_TIMEOUT
            )

        results.append(
            FailureResult(
                candidate=cand,
                outcome=outcome,
                failure_index=f_idx,
                failure_close=f_close,
                stop_reference=stop,
            )
        )

    return results


def failure_ts(result: FailureResult, candles: Sequence[EngineCandle]):
    """Timestamp of the resolution bar (None while DETECTING)."""
    return candles[result.failure_index].ts if result.failure_index is not None else None


__all__ = ["resolve_failure", "Outcome", "FailureResult", "failure_ts"]
