# BOF Engine Design (Phase 3)

**BOF = Breakout Failure.** Price breaks a structural level, traps breakout
traders, and snaps back — the failure itself becomes the tradeable signal.
This document fixes the algorithm contract before implementation so the
engine, persistence and UI agree on semantics.

## Pipeline

```
candles (validated, normalized)
  → MarketStructure        rolling swing highs/lows, levels
  → BreakoutDetector       close beyond level + filters
  → FailureDetector        re-entry inside level within N bars
  → SignalClassifier       BULLISH / BEARISH BOF taxonomy
  → SignalStrength         confidence score → WEAK…VERY_STRONG
  → persistence            signals + signal_events (append-only)
  → broadcast              WebSocket (Phase 4) + FCM (Phase 6)
```

Modules: `app/engine/{market_structure,breakout_detector,failure_detector,
signal_classifier,signal_strength,bof_engine}.py`. Pure functions in, dataclasses
out — no I/O, fully unit-testable.

## Definitions

- **Level**: last confirmed swing high (resistance) or swing low (support)
  from fractal pivots (default `left=3, right=3` bars), unmitigated at
  detection time.
- **Breakout**: candle **close** beyond the level by ≥ `min_break_pct`
  (default 0.05% of price; wicks don't count).
  Optional volume filter: breakout volume ≥ `vol_mult` × SMA20(volume).
- **Failure**: within `failure_window` bars (default 3), a candle **close**
  back on the origin side of the level.
- **Invalidation of the signal** (not the trade): price closes beyond level
  again by ≥ `rebreak_pct` before failing, or `max_age` bars elapse.

## Classification

| Sequence | Direction | Meaning |
|---|---|---|
| break above → fail back below | **BEARISH BOF** | longs trapped at highs |
| break below → fail back above | **BULLISH BOF** | shorts trapped at lows |

Signal lifecycle (`status`): `DETECTING` while breakout is open → `CONFIRMED`
on failure print → `INVALIDATED` on re-break/timeout → `CLOSED` when stop or
target reference is tagged (Phase 5 statistics).

## Strength score (0–100)

Weighted sum, each factor normalised to [0,1]:

| Factor | Weight | Measures |
|---|---|---|
| Re-entry speed | 0.30 | faster failure = stronger trap |
| Penetration depth | 0.20 | deeper false break = more trapped traders |
| Volume expansion | 0.20 | breakout vs 20-bar average |
| Wick rejection | 0.15 | failure-candle wick ratio against the level |
| Trend context | 0.15 | alignment with higher-timeframe trend (200-SMA slope) |

Mapping: <40 `WEAK` · 40–59 `MODERATE` · 60–79 `STRONG` · ≥80 `VERY_STRONG`.
`confidence` = raw score ÷ 100. All weights/thresholds live in one
`BOFConfig` dataclass — tunable per timeframe, no magic numbers in logic.

## Data contract

```python
@dataclass(frozen=True)
class BOFSignal:
    instrument_id: UUID
    timeframe: Timeframe
    direction: SignalDirection          # BULLISH | BEARISH
    bof_level: Decimal
    breakout_price: Decimal             # closing price of the breakout bar
    failure_price: Decimal              # closing price of the failure bar
    entry_price: Decimal                # failure bar close (reference)
    stop_reference: Decimal             # extreme of the failed excursion
    confidence: float                   # 0..1
    strength: SignalStrength
    detected_at: datetime               # breakout bar ts
    confirmed_at: datetime | None      # failure bar ts
    metadata: dict                      # factor breakdown for auditability
```

Persistence rules:
- One row per `(instrument, timeframe, breakout-bar)` — idempotent upsert;
  replays never duplicate signals.
- Every state transition appends a `signal_events` row
  (`DETECTED`, `CONFIRMED`, `INVALIDATED`, …) with the triggering bar ts.
- Only confirmed+ signals are broadcast/notified; `DETECTING` rows are
  internal working state.

## Processing model

Batch-first: the worker aggregates candles per timeframe, then runs the pure
pipeline over new bars since the last watermark (per instrument+timeframe),
flushing signals transactionally. Live ticks only update the forming candle —
the engine never sees partial bars. This keeps the engine deterministic and
makes Redis/streaming an additive later change, not a rewrite.

## Testing strategy

Golden fixtures: synthetic OHLCV sequences per scenario (clean bull/bear BOF,
re-break invalidation, timeout invalidation, no-break noise, gap handling)
assert classification + scores ±ε. Property tests: random walks must produce
zero signals without both a qualifying breakout AND failure. Performance:
10k bars/instrument processed in-memory in <100 ms (pure NumPy/pandas ops,
no per-bar Python loops on hot paths).

> No fake signals exist anywhere in production code paths; demo data comes
> exclusively from the clearly-labelled `DemoMarketDataProvider` (Phase 3).
