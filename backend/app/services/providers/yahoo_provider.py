"""Yahoo Finance provider — real NSE/BSE market data via the free v8 chart API.

No API key needed. Data may be delayed up to 15 minutes for NSE.
Uses ``/v8/finance/chart/{symbol}`` for both candles AND live quotes
(the ``meta`` object carries ``regularMarketPrice`` etc.).

Symbol mapping: NSE → ``.NS``, BSE → ``.BO``.
"""

import asyncio
import time
from datetime import datetime, timezone

import httpx

from app.core.logging import get_logger
from app.services.providers.base import MarketDataProvider

logger = get_logger(__name__)

_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

_INTERVAL_MAP = {
    "15m": ("15m", "30d"),
    "1h": ("60m", "60d"),
    "4h": ("60m", "90d"),
    "1D": ("1d", "2y"),
}

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


class YahooFinanceProvider(MarketDataProvider):
    name = "yahoo"
    is_demo = False

    def __init__(self, reference_instruments: list[dict] | None = None) -> None:
        self._instruments = reference_instruments or []
        self._symbol_map = {r["symbol"]: r for r in self._instruments}
        self._client = httpx.AsyncClient(
            headers=_HEADERS,
            timeout=httpx.Timeout(15.0),
        )
        self._last_call = 0.0
        self._min_interval = 0.6

    async def aclose(self) -> None:
        await self._client.aclose()

    def _yf(self, symbol: str) -> str:
        inst = self._symbol_map.get(symbol)
        if inst and inst.get("exchange") == "BSE":
            return f"{symbol}.BO"
        return f"{symbol}.NS"

    async def _get_chart(self, symbol: str, interval: str, rng: str) -> dict | None:
        yf_sym = self._yf(symbol)
        wait = max(0, self._min_interval - (time.monotonic() - self._last_call))
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()

        try:
            resp = await self._client.get(
                _CHART_URL.format(symbol=yf_sym),
                params={"interval": interval, "range": rng},
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("chart", {}).get("result", [])
            if not results:
                return None
            result = results[0]
            meta = result.get("meta", {})
            ts_list = result.get("timestamp", [])
            indicators = result.get("indicators", {}).get("quote", [{}])[0]
            return {"meta": meta, "ts": ts_list, "indicators": indicators}
        except httpx.HTTPStatusError as exc:
            logger.warning("Yahoo %s returned %s", yf_sym, exc.response.status_code)
            return None
        except Exception as exc:
            logger.warning("Yahoo fetch failed for %s: %s", yf_sym, exc)
            return None

    # ------------------------------------------------------------- interface

    async def get_instruments(self) -> list[dict]:
        return list(self._instruments)

    async def get_quote(self, symbol: str) -> dict | None:
        data = await self._get_chart(symbol, "15m", "5d")
        if data is None:
            return None
        return self._extract_quote(symbol, data["meta"])

    async def get_quotes(self, symbols: list[str]) -> list[dict]:
        out = []
        for s in symbols:
            q = await self.get_quote(s)
            if q:
                out.append(q)
        return out

    async def get_candles(
        self, symbol: str, timeframe: str, bars: int,
        *, end_exclusive_index: int | None = None,
    ) -> list[dict]:
        interval, rng = _INTERVAL_MAP.get(timeframe, ("15m", "30d"))
        data = await self._get_chart(symbol, interval, rng)
        if data is None:
            return []

        meta = data["meta"]
        ts_list = data["ts"]
        ind = data["indicators"]
        opens = ind.get("open", [])
        highs = ind.get("high", [])
        lows = ind.get("low", [])
        closes = ind.get("close", [])
        volumes = ind.get("volume", [])

        bars_out = []
        for i in range(len(ts_list)):
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            if o is None or h is None or l is None or c is None:
                continue
            bars_out.append({
                "ts": datetime.fromtimestamp(ts_list[i], tz=timezone.utc),
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(l, 2),
                "close": round(c, 2),
                "volume": int(volumes[i] or 0),
            })

        return bars_out[-bars:]

    async def get_live_quotes(self, symbols: list[str]) -> list[dict]:
        """Real-time snapshot via chart meta.regularMarketPrice."""
        out = []
        for s in symbols[:10]:  # limit to avoid long loops
            data = await self._get_chart(s, "15m", "1d")
            if data is None:
                continue
            meta = data["meta"]
            price = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose") or meta.get("previousClose")
            if price is None:
                continue
            change_pct = ((price - prev) / prev * 100) if prev else None
            out.append({
                "symbol": s,
                "last_price": round(price, 2),
                "change_pct": round(change_pct, 2) if change_pct else None,
                "direction": "UP" if (change_pct or 0) > 0 else "DOWN" if (change_pct or 0) < 0 else "FLAT",
                "is_demo": False,
                "updated_at": datetime.now(timezone.utc),
            })
        return out

    # ------------------------------------------------------------------ helpers

    def _extract_quote(self, symbol: str, meta: dict) -> dict:
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose")
        change = (price - prev) if (price is not None and prev is not None) else None
        change_pct = (change / prev * 100) if (prev and change is not None) else None
        return {
            "symbol": symbol,
            "last_price": price,
            "previous_close": prev,
            "change": change,
            "change_pct": change_pct,
            "updated_at": datetime.now(timezone.utc),
            "is_demo": False,
        }


_INTERVAL_MAP = {
    "15m": ("15m", "30d"),
    "1h": ("60m", "60d"),
    "4h": ("60m", "90d"),
    "1D": ("1d", "2y"),
}

__all__ = ["YahooFinanceProvider"]
