"""Candle validation, normalisation and helpers shared by ingestion workers."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from app.engine.models import EngineCandle


def normalise(raw: Sequence[dict]) -> list[EngineCandle]:
    """Provider dicts → clean, sorted EngineCandles.

    - drops rows with non-finite/non-positive prices
    - repairs OHLC ordering (high ≥ max(o,c), low ≤ min(o,c))
    - deduplicates by timestamp (last wins) and sorts ascending
    """
    cleaned: dict[datetime, EngineCandle] = {}
    for r in raw:
        try:
            o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if not all(x > 0 and x == x and x != float("inf") for x in (o, h, l, c)):
            continue
        h = max(h, o, c)
        l = min(l, o, c)
        ts: datetime = r["ts"]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        vol = float(r.get("volume") or 0)
        cleaned[ts] = EngineCandle(ts=ts, open=o, high=h, low=l, close=c, volume=vol)

    return [cleaned[ts] for ts in sorted(cleaned)]


def align_to_grid(ts: datetime, interval: timedelta) -> datetime:
    """Floor a timestamp onto the bar grid."""
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = ts - epoch
    return epoch + (delta // interval) * interval


__all__ = ["normalise", "align_to_grid"]
