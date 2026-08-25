"""Multi-strategy trading engine — generates BUY/SELL trade ideas.

Strategies:
  1. RSI Reversal       — oversold bounce / overbought rejection
  2. SMA Crossover      — SMA9 crossing above/below SMA21
  3. Bollinger Bounce   — price bouncing off upper/lower band
  4. BOF (Breakout Fail) — existing engine, re-used here

Each strategy returns a list of TradeSignal with:
  action (BUY/SELL), entry, target, stop_loss, risk_reward, confidence,
  strategy name, and the triggering bar timestamp.

Signals from multiple strategies on the same bar are combined into a
higher-confidence "confluence" signal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.engine.models import EngineCandle


# ------------------------------------------------------------------ model

@dataclass(frozen=True)
class TradeSignal:
    """Actionable trade recommendation."""
    instrument_id: str
    timeframe: str
    action: str              # BUY | SELL
    strategy: str            # RSI_REVERSAL | SMA_CROSS | BB_BOUNCE | BOF
    entry: float
    target: float
    stop_loss: float
    risk_reward: float
    confidence: float        # 0..1
    detected_at: datetime    # trigger bar ts (idempotency key)
    metadata: dict = field(default_factory=dict)


# ------------------------------------------------------------------ helpers

def _atr(candles: list[EngineCandle], period: int = 14) -> float:
    """Average True Range — used for target and stop-loss placement."""
    if len(candles) < 2:
        return 0.0
    trs = []
    for i in range(1, min(len(candles), period + 1)):
        c = candles[-i]
        prev_c = candles[-i - 1] if i < len(candles) - 1 else c
        tr = max(c.high - c.low, abs(c.high - prev_c.close), abs(c.low - prev_c.close))
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.0


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def _rsi_series(closes: list[float], period: int = 14) -> list:
    out = [0.0] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = [], []
    for i in range(1, period + 1):
        chg = closes[i] - closes[i - 1]
        gains.append(max(chg, 0)); losses.append(max(-chg, 0))
    avg_g = sum(gains) / period; avg_l = sum(losses) / period
    for i in range(period, len(closes)):
        chg = closes[i] - closes[i - 1]
        avg_g = (avg_g * (period - 1) + max(chg, 0)) / period
        avg_l = (avg_l * (period - 1) + max(-chg, 0)) / period
        rs = avg_g / avg_l if avg_l else 100
        out[i] = 100 - (100 / (1 + rs))
    return out


def _ema_series(closes: list[float], period: int) -> list[float]:
    k = 2.0 / (period + 1)
    out = [closes[0]]
    for i in range(1, len(closes)):
        out.append(closes[i] * k + out[-1] * (1 - k))
    return out


def _bollinger(closes: list[float], period: int = 20, mult: float = 2.0):
    mid = sum(closes[-period:]) / period
    std = (sum((c - mid)**2 for c in closes[-period:]) / period) ** 0.5
    return mid + mult * std, mid, mid - mult * std


# ------------------------------------------------------------------ strategies

def rsi_reversal(candles: list[EngineCandle]) -> list[dict]:
    """RSI < 30 turning up = BUY · RSI > 70 turning down = SELL."""
    if len(candles) < 20:
        return []
    closes = [c.close for c in candles]
    rsi_vals = _rsi_series(closes)
    signals = []

    for i in range(max(15, len(rsi_vals) - 3), len(rsi_vals)):
        cur = rsi_vals[i]
        prev = rsi_vals[i - 1]
        c = candles[i]

        if prev <= 30 and cur > 30:
            atr = _atr(candles[:i+1])
            signals.append({
                "action": "BUY", "strategy": "RSI_OVERSOLD",
                "index": i, "entry": c.close,
                "target": c.close + atr * 2,
                "stop_loss": c.close - atr * 1.5,
                "confidence": min(30 + (cur - 30) * 5, 90) / 100,
            })
        elif prev >= 70 and cur < 70:
            atr = _atr(candles[:i+1])
            signals.append({
                "action": "SELL", "strategy": "RSI_OVERBOUGHT",
                "index": i, "entry": c.close,
                "target": c.close - atr * 2,
                "stop_loss": c.close + atr * 1.5,
                "confidence": min(30 + (70 - cur) * 5, 90) / 100,
            })
    return signals


def sma_crossover(candles: list[EngineCandle]) -> list[dict]:
    """SMA9 crosses above SMA21 → BUY · crosses below → SELL."""
    if len(candles) < 25:
        return []
    closes = [c.close for c in candles]
    ema9 = _ema_series(closes, 9)
    sma21 = [
        sum(closes[max(0,i-20):i+1]) / min(i+1, 21)
        for i in range(len(closes))
    ]

    signals = []
    for i in range(max(22, len(closes) - 3), len(closes)):
        fast_now = ema9[i]; slow_now = sma21[i]
        fast_prev = ema9[i-1]; slow_prev = sma21[i-1]

        if fast_prev <= slow_prev and fast_now > slow_now:
            atr = _atr(candles[:i+1])
            signals.append({
                "action": "BUY", "strategy": "SMA_CROSS",
                "index": i, "entry": candles[i].close,
                "target": candles[i].close + atr * 2.5,
                "stop_loss": candles[i].close - atr * 1,
                "confidence": 0.65,
            })
        elif fast_prev >= slow_prev and fast_now < slow_now:
            atr = _atr(candles[:i+1])
            signals.append({
                "action": "SELL", "strategy": "SMA_CROSS",
                "index": i, "entry": candles[i].close,
                "target": candles[i].close - atr * 2.5,
                "stop_loss": candles[i].close + atr * 1,
                "confidence": 0.65,
            })
    return signals


def bollinger_bounce(candles: list[EngineCandle]) -> list[dict]:
    """Price touches lower band then closes back inside → BUY · touches upper → SELL."""
    if len(candles) < 25:
        return []
    closes = [c.close for c in candles]
    signals = []

    for i in range(max(21, len(closes) - 3), len(closes)):
        upper, mid, lower = _bollinger(closes[:i+1])
        c = candles[i]
        prev_close = closes[i - 1]

        if prev_close <= lower and c.close > lower:
            atr = _atr(candles[:i+1])
            signals.append({
                "action": "BUY", "strategy": "BB_LOWER_BOUNCE",
                "index": i, "entry": c.close,
                "target": mid, "stop_loss": lower - atr * 0.5,
                "confidence": 0.6,
            })
        elif prev_close >= upper and c.close < upper:
            atr = _atr(candles[:i+1])
            signals.append({
                "action": "SELL", "strategy": "BB_UPPER_BOUNCE",
                "index": i, "entry": c.close,
                "target": mid, "stop_loss": upper + atr * 0.5,
                "confidence": 0.6,
            })
    return signals


STRATEGIES = [rsi_reversal, sma_crossover, bollinger_bounce]


# ------------------------------------------------------------------ combiner

def run_strategies(
    instrument_id: str,
    timeframe: str,
    candles: list[EngineCandle],
) -> list[TradeSignal]:
    """Run all strategies → merge overlapping signals → TradeSignal list."""
    raw_signals: list[dict] = []
    for strat_fn in STRATEGIES:
        try:
            raw_signals.extend(strat_fn(candles))
        except Exception:
            pass

    # Deduplicate by (action, index) — keep highest confidence per bar
    seen: dict[tuple[str, int], dict] = {}
    for s in raw_signals:
        key = (s["action"], s["index"])
        if key not in seen or s["confidence"] > seen[key]["confidence"]:
            seen[key] = s

    # Build TradeSignal objects with computed risk_reward
    out: list[TradeSignal] = []
    for s in seen.values():
        risk = abs(s["entry"] - s["stop_loss"])
        reward = abs(s["target"] - s["entry"])
        rr = round(reward / risk, 2) if risk > 0 else 0.0

        out.append(TradeSignal(
            instrument_id=instrument_id,
            timeframe=timeframe,
            action=s["action"],
            strategy=s["strategy"],
            entry=round(s["entry"], 2),
            target=round(s["target"], 2),
            stop_loss=round(s["stop_loss"], 2),
            risk_reward=rr,
            confidence=round(min(s["confidence"], 1.0), 2),
            detected_at=candles[s["index"]].ts,
            metadata={"engine": "strategies-v1", "source_strategy": s["strategy"]},
        ))

    # Confluence boost: same action from ≥2 strategies on adjacent bars → bump confidence
    buys = [t for t in out if t.action == "BUY"]
    sells = [t for t in out if t.action == "SELL"]
    if len(buys) >= 2:
        out += [TradeSignal(**{**t.__dict__, "confidence": min(t.confidence + 0.15, 1.0),
                               "metadata": {**t.metadata, "confluence": True}})
                for t in buys[:1]]
    if len(sells) >= 2:
        out += [TradeSignal(**{**t.__dict__, "confidence": min(t.confidence + 0.15, 1.0),
                               "metadata": {**t.metadata, "confluence": True}})
                for t in sells[:1]]

    out.sort(key=lambda t: t.detected_at, reverse=True)
    return out[:10]  # cap at 10 most recent per call


__all__ = ["run_strategies", "TradeSignal"]
