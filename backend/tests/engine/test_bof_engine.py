"""Golden-scenario tests for the BOF engine (pure functions, no DB)."""

import uuid
from datetime import datetime, timedelta, timezone

from app.engine import bof_engine
from app.engine.config import BOFConfig
from app.engine.market_structure import confirm_pivots
from app.engine.models import EngineCandle

T0 = datetime(2026, 1, 5, 9, 15, tzinfo=timezone.utc)
CFG = BOFConfig(pivot_left=2, pivot_right=2)


def bar(i: int, o: float, h: float, l: float, c: float, vol: float = 1000.0) -> EngineCandle:
    assert h >= max(o, c) and l <= min(o, c), f"invalid OHLC at {i}"
    return EngineCandle(ts=T0 + timedelta(minutes=15 * i), open=o, high=h, low=l, close=c, volume=vol)


def chop(n: int, start: int = 0) -> list[EngineCandle]:
    """Sideways range ~100 with slightly varied extremes so pivots confirm."""
    out = []
    for k in range(n):
        bump_h = 0.08 if k % 5 == 0 else 0.0
        dip_l = 0.08 if k % 5 == 2 else 0.0
        out.append(bar(start + k, 100.0, 100.30 + bump_h, 99.70 - dip_l, 100.0))
    return out


def run(candles: list[EngineCandle]):
    return bof_engine.run(instrument_id=uuid.uuid4(), timeframe="15m", candles=candles, config=CFG)


def test_flat_series_yields_nothing():
    flat = [bar(i, 100, 100.01, 99.99, 100) for i in range(40)]
    assert run(flat) == []


def test_bearish_bof_confirmed():
    candles = chop(24)
    # breakout above the ~100.38 pivot-high zone
    candles.append(bar(24, 100.2, 102.0, 100.1, 101.5))
    candles.append(bar(25, 101.4, 102.2, 101.0, 101.8))
    # failure: close back below level within the window
    candles.append(bar(26, 101.0, 101.2, 99.0, 99.5))

    signals = run(candles)
    bearish = [s for s in signals if s.direction == "BEARISH" and s.status == "CONFIRMED"]
    assert bearish, signals
    s = bearish[0]
    assert s.bof_level >= 100.2                       # pivot high zone
    assert s.breakout_price >= s.bof_level * 1.0005
    assert s.failure_price < s.bof_level
    assert s.stop_reference is not None and s.stop_reference > s.bof_level
    assert s.confirmed_at is not None and s.detected_at < s.confirmed_at
    assert 0.0 <= s.confidence <= 1.0


def test_bullish_bof_confirmed():
    candles = chop(24)
    # breakdown below the ~99.62 pivot-low zone
    candles.append(bar(24, 99.8, 99.9, 98.0, 98.5))
    candles.append(bar(25, 98.6, 98.8, 97.8, 98.2))
    # failure: snap back above support within the window
    candles.append(bar(26, 98.4, 101.0, 98.3, 100.6))

    signals = run(candles)
    bullish = [s for s in signals if s.direction == "BULLISH" and s.status == "CONFIRMED"]
    assert bullish, signals
    s = bullish[0]
    assert s.breakout_price <= s.bof_level * 0.9995
    assert s.failure_price > s.bof_level
    assert s.stop_reference is not None and s.stop_reference < s.bof_level


def test_breakout_without_failure_times_out_invalidated():
    candles = chop(24)
    breakout_ts = T0 + timedelta(minutes=15 * 24)
    candles.append(bar(24, 100.2, 103.0, 100.1, 102.5))            # strong breakout
    candles.extend(bar(25 + k, 102.5, 104.0, 102.0, 103.5) for k in range(4))

    signals = run(candles)
    relevant = [s for s in signals if s.detected_at == breakout_ts]
    assert relevant, signals
    s = relevant[0]
    assert s.status == "INVALIDATED"
    assert s.confirmed_at is None and s.entry_price is None


def test_open_candidate_stays_detecting():
    candles = chop(24)
    candles.append(bar(24, 100.2, 103.0, 100.1, 102.5))            # series ends mid-window

    signals = run(candles)
    live = [s for s in signals if s.status == "DETECTING"]
    assert live and live[0].direction == "BEARISH"


def test_pivot_confirmation_requires_right_bars():
    rising = [bar(i, 10 + i * 0.2, 10.3 + i * 0.2, 10.0 + i * 0.2, 10.1 + i * 0.2) for i in range(20)]
    pivots = confirm_pivots(rising, left=2, right=2)
    # monotonic rise: no swing high can be strictly greater than later highs…
    assert not any(p.side.value == "UP" and p.index >= len(rising) - 2 for p in pivots)


def test_strength_bounds_and_metadata():
    candles = chop(26)
    candles.append(bar(26, 100.2, 102.0, 100.1, 101.5, vol=4000))
    candles.append(bar(27, 101.0, 101.3, 98.5, 98.8, vol=3500))

    signals = run(candles)
    confirmed = [s for s in signals if s.status == "CONFIRMED"]
    assert confirmed
    for s in confirmed:
        assert 0 <= s.confidence <= 1
        assert set(s.metadata["factors"]) == {"speed", "depth", "volume", "wick", "trend"}
        assert s.metadata["engine"] == "bof-v1"
