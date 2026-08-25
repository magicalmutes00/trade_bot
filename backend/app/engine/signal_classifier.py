"""BOF taxonomy: breakout side → signal direction & lifecycle status."""

from app.engine.failure_detector import Outcome
from app.engine.models import Side


def direction_for(side: Side) -> str:
    """Break above resistance that fails → BEARISH (longs trapped);
    breakdown below support that fails → BULLISH (shorts trapped)."""
    return "BEARISH" if side is Side.UP else "BULLISH"


def status_for(outcome: Outcome) -> str:
    return {
        Outcome.CONFIRMED: "CONFIRMED",
        Outcome.INVALIDATED_REBREAK: "INVALIDATED",
        Outcome.INVALIDATED_TIMEOUT: "INVALIDATED",
        Outcome.DETECTING: "DETECTING",
    }[outcome]


__all__ = ["direction_for", "status_for"]
