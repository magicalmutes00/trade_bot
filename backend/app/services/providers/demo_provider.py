"""DemoMarketDataProvider - deterministic synthetic OHLCV for development.

DEMO DATA: every bar produced here is SYNTHETIC. It exists so the pipeline
(storage -> BOF engine -> API -> UI) can be exercised without paid feeds.
It must never be presented as real market data.

Determinism: prices are a PURE FUNCTION of (symbol, bar_index) on a fixed
15-minute grid anchored to DEMO_ANCHOR_UTC. Backfill and incremental
"update" calls produce identical, reproducible history with no RNG state.
"""

import hashlib
import math
from datetime import datetime, timedelta, timezone

from app.services.providers.base import MarketDataProvider

BASE_INTERVAL = timedelta(minutes=15)
DEMO_ANCHOR_UTC = datetime(2026, 1, 1, tzinfo=timezone.utc)

_REGIME_LEN = 64          # bars per drift regime (~16h of 15m bars)
_SIGMA = 0.0018           # per-bar volatility as fraction of price


def _hash_uniform(token: bytes) -> float:
    digest = hashlib.blake2b(token, digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2**64


class DemoMarketDataProvider(MarketDataProvider):
    name = "demo"
    is_demo = True

    def __init__(self, reference_instruments: list[dict] | None = None) -> None:
        # Reference metadata comes from the caller (DB seed), not invented.
        self._instruments = reference_instruments or []
        self._types = {
            r["symbol"]: r.get("instrument_type", "STOCK") for r in self._instruments
        }

    async def get_instruments(self) -> list[dict]:
        return list(self._instruments)

    async def get_quote(self, symbol: str) -> dict | None:
        candles = await self.get_candles(symbol, "15m", 2)
        if not candles:
            return None
        last = candles[-1]
        prev_close = candles[-2]["close"] if len(candles) > 1 else last["open"]
        change = last["close"] - prev_close
        return {
            "symbol": symbol,
            "last_price": last["close"],
            "previous_close": prev_close,
            "change": change,
            "change_pct": (change / prev_close * 100) if prev_close else None,
            "day_open": last["open"],
            "day_high": last["high"],
            "day_low": last["low"],
            "volume": last["volume"],
            "updated_at": last["ts"],
            "is_demo": True,
        }

    async def get_quotes(self, symbols: list[str]) -> list[dict]:
        out = []
        for s in symbols:
            q = await self.get_quote(s)
            if q:
                out.append(q)
        return out

    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        bars: int,
        *,
        end_exclusive_index: int | None = None,
    ) -> list[dict]:
        end_idx = end_exclusive_index if end_exclusive_index is not None else self.current_index()
        start_idx = max(0, end_idx - bars)
        closes = self._close_series(symbol, start_idx, end_idx)
        base = []
        for i in range(start_idx, end_idx):
            o = closes[i - 1] if i > start_idx else closes[i]
            base.append(self._base_bar_from(symbol, i, open_px=o, close_px=closes[i]))
        return _aggregate(base, timeframe)

    # ------------------------------------------------------------------ core

    def current_index(self) -> int:
        now = datetime.now(timezone.utc)
        return int((now - DEMO_ANCHOR_UTC) / BASE_INTERVAL) - 1

    def index_to_ts(self, index: int) -> datetime:
        return DEMO_ANCHOR_UTC + BASE_INTERVAL * index

    def ts_to_index(self, ts: datetime) -> int:
        return int((ts - DEMO_ANCHOR_UTC) / BASE_INTERVAL)

    def _seed(self, symbol: str) -> int:
        return int.from_bytes(hashlib.blake2b(symbol.encode(), digest_size=4).digest(), "big")

    def base_price(self, symbol: str, instrument_type: str = "STOCK") -> float:
        h = _hash_uniform(f"price:{symbol}".encode())
        if instrument_type == "INDEX":
            return round(15000 + h * 60000, 2)
        return round(120 + h * 3800, 2)

    def _regime_drift(self, symbol_seed: int, regime_index: int) -> float:
        u = _hash_uniform(f"regime:{symbol_seed}:{regime_index}".encode())
        # drifts in [-3, +3] sigma-per-bar; zero drift ~30% of the time
        if u < 0.30:
            return 0.0
        sign = 1.0 if u > 0.5 else -1.0
        magnitude = (u - 0.30) / 0.70 * 3.0
        return sign * magnitude * _SIGMA

    def _innovation(self, symbol_seed: int, index: int) -> float:
        u = _hash_uniform(f"innov:{symbol_seed}:{index}".encode())
        # roughly normal via sum of 3 uniforms (Irwin-Hall), centred
        return (u - 0.5) * 2.0

    def _path_price(self, symbol: str, seed: int, p0: float, target_index: int) -> float:
        """Deterministic walk from anchor to target index.

        Walks forward in chunks from the nearest multiple of _CACHE_STEP and
        applies gentle mean-reversion toward ``p0`` so synthetic prices stay
        in a believable band around the instrument's reference level.
        """
        step = 512
        start = (target_index // step) * step
        price = p0
        lo, hi = p0 * 0.55, p0 * 1.9
        for i in range(max(0, start - step), start):  # warm-up chunk for smoothness
            price *= 1.0 + self._step_return(seed, i)
            price += (p0 - price) * 0.01
        price = min(max(price, lo), hi)
        for i in range(start, target_index + 1):
            price *= 1.0 + self._step_return(seed, i)
            price += (p0 - price) * 0.01
        return min(max(price, lo), hi)

    def _step_return(self, seed: int, index: int) -> float:
        regime = index // _REGIME_LEN
        drift = self._regime_drift(seed, regime)
        shock = self._innovation(seed, index) * _SIGMA
        return drift + shock

    def _close_series(self, symbol: str, start_idx: int, end_idx: int) -> dict[int, float]:
        """One contiguous walk from the fixed demo anchor â€” fully deterministic.

        The walk ALWAYS starts at index 0 regardless of the requested window,
        so identical (symbol, index) pairs yield identical prices forever.
        ~17k iterations for years of history â€” negligible cost.
        """
        seed = self._seed(symbol)
        p0 = self.base_price(symbol, self._types.get(symbol, "STOCK"))
        lo, hi = p0 * 0.55, p0 * 1.9

        price = p0
        out: dict[int, float] = {}
        for i in range(0, max(end_idx, 0) + 1):  # inclusive of end index
            price *= 1.0 + self._step_return(seed, i)
            price += (p0 - price) * 0.01
            price = min(max(price, lo), hi)
            if i >= start_idx - 1:
                out[i] = round(price, 4)
        return out

    def _base_bar_from(self, symbol: str, index: int, *, open_px: float, close_px: float) -> dict:
        seed = self._seed(symbol)

        intra_hi = abs(self._innovation(seed + 11, index)) * _SIGMA * 1.6
        intra_lo = abs(self._innovation(seed + 23, index)) * _SIGMA * 1.6
        high = max(open_px, close_px) * (1 + intra_hi)
        low = min(open_px, close_px) * (1 - intra_lo)

        u = _hash_uniform(f"vol:{seed}:{index}".encode())
        minute_of_day = index % 96
        ushape = 1.0 + 0.8 * math.cos((minute_of_day / 96) * 2 * math.pi) ** 2
        volume = int(50_000 * (0.4 + u) * ushape)

        return {
            "ts": self.index_to_ts(index),
            "open": round(open_px, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close_px, 4),
            "volume": volume,
        }


_AGG_FACTOR = {"15m": 1, "30m": 2, "1h": 4, "4h": 16}


def _aggregate(base_bars: list[dict], timeframe: str) -> list[dict]:
    """Aggregate consecutive base bars; '1D' groups by UTC date, '1W' by ISO week."""
    if timeframe in _AGG_FACTOR:
        f = _AGG_FACTOR[timeframe]
        out = []
        for i in range(0, len(base_bars), f):
            chunk = base_bars[i : i + f]
            out.append(_merge(chunk))
        return out

    buckets: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for b in base_bars:
        ts = b["ts"]
        if timeframe == "1D":
            key = (ts.year, ts.month, ts.day)
        elif timeframe == "1W":
            iso = ts.isocalendar()
            key = (iso.year, iso.week)
        else:
            raise ValueError(f"unsupported demo timeframe '{timeframe}'")
        if key not in buckets:
            buckets[key] = []
            order.append(key)
        buckets[key].append(b)
    return [_merge(buckets[k]) for k in order]


def _merge(chunk: list[dict]) -> dict:
    return {
        "ts": chunk[0]["ts"],
        "open": chunk[0]["open"],
        "high": max(b["high"] for b in chunk),
        "low": min(b["low"] for b in chunk),
        "close": chunk[-1]["close"],
        "volume": sum(b["volume"] for b in chunk),
    }


__all__ = ["DemoMarketDataProvider", "BASE_INTERVAL", "DEMO_ANCHOR_UTC"]

