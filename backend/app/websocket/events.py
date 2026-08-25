"""WebSocket event payload builders (pure functions — unit-testable)."""

from datetime import datetime, timezone


def hello_payload(interval_seconds: int, provider: str) -> dict:
    return {
        "type": "hello",
        "data": {
            "server_time": datetime.now(timezone.utc).isoformat(),
            "tick_interval_seconds": interval_seconds,
            "provider": provider,
            "is_demo": provider == "demo",
        },
    }


def quote_ticks_payload(quotes: list[dict]) -> dict:
    """quotes: [{symbol,last_price,change_pct,direction,is_demo}]"""
    return {"type": "quotes", "data": quotes}


def signals_payload(signals: list[dict]) -> dict:
    """signals: newest-first compact cards (same shape as dashboard SignalCard)."""
    return {"type": "signals", "data": signals}


def market_status_payload(market: str, status: str) -> dict:
    return {
        "type": "market_status",
        "data": {"market": market, "status": status,
                 "as_of": datetime.now(timezone.utc).isoformat()},
    }


def pong_payload() -> dict:
    return {"type": "pong"}


__all__ = [
    "hello_payload", "quote_ticks_payload", "signals_payload",
    "market_status_payload", "pong_payload",
]
