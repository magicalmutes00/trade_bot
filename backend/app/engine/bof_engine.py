"""BOF engine orchestrator — candles in, EngineSignals out (pure functions).

Pipeline: pivots → breakout candidates → failure resolution → classification
→ strength scoring → EngineSignal rows ready for persistence.

Full-history recompute per instrument+timeframe; deterministic and idempotent
(see docs/bof-engine.md §Processing model).
"""

from collections.abc import Sequence
import uuid

from app.engine import signal_classifier as classifier
from app.engine import signal_strength
from app.engine.breakout_detector import detect_breakouts
from app.engine.config import BOFConfig, DEFAULT_CONFIG
from app.engine.failure_detector import Outcome, failure_ts, resolve_failure
from app.engine.market_structure import confirm_pivots
from app.engine.models import EngineCandle, EngineSignal, strength_from_score


def run(
    *,
    instrument_id: uuid.UUID,
    timeframe: str,
    candles: Sequence[EngineCandle],
    config: BOFConfig = DEFAULT_CONFIG,
) -> list[EngineSignal]:
    cfg = config
    cfg.validate()
    if len(candles) < max(cfg.volume_sma, cfg.pivot_left + cfg.pivot_right) + 2:
        return []

    pivots = confirm_pivots(candles, left=cfg.pivot_left, right=cfg.pivot_right)
    candidates = detect_breakouts(candles, pivots, cfg)
    results = resolve_failure(candles, candidates, cfg)

    signals: list[EngineSignal] = []
    for res in results:
        score, factors = signal_strength.score(candles, res, cfg)
        direction = classifier.direction_for(res.candidate.side)
        status = classifier.status_for(res.outcome)
        f_ts = failure_ts(res, candles)

        signals.append(
            EngineSignal(
                instrument_id=instrument_id,
                timeframe=timeframe,
                direction=direction,
                bof_level=round(res.candidate.level, 8),
                breakout_price=round(res.candidate.breakout_close, 8),
                failure_price=round(res.failure_close, 8) if res.failure_close is not None else None,
                entry_price=round(res.failure_close, 8) if res.failure_close is not None else None,
                stop_reference=round(res.stop_reference, 8) if res.stop_reference is not None else None,
                confidence=round(score / 100.0, 4),
                strength=strength_from_score(score, cfg),
                status=status,
                detected_at=res.candidate.breakout_ts,
                confirmed_at=f_ts if res.outcome is Outcome.CONFIRMED else None,
                metadata={
                    "engine": "bof-v1",
                    "factors": factors,
                    "level_origin_ts": res.candidate.level_ts.isoformat(),
                    "breakout_index": res.candidate.breakout_index,
                    "failure_index": res.failure_index,
                    "outcome": res.outcome.value,
                },
            )
        )

    # Newest first — callers typically persist/display in this order.
    signals.sort(key=lambda s: s.detected_at, reverse=True)
    return signals


__all__ = ["run"]
