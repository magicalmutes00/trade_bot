"""Twelve Data provider — real-time market data with free + paid tiers.

API: https://twelvedata.com/docs
Free tier: 8 credits/min · 800/day · 1 credit = 1 symbol per request.
Batch endpoints accept comma-separated symbols (N symbols = N credits).

Set ``MARKET_DATA_API_KEY`` to your key from twelvedata.com/dashboard.
"""

import asyncio
import time
from datetime import datetime, timezone

import httpx

from app.core.errors import AppError
from app.services.providers.base import MarketDataProvider


class ProviderNotConfiguredError(AppError):
    status_code = 503
    code = "PROVIDER_NOT_CONFIGURED"


class ProviderUnavailableError(AppError):
    status_code = 503
    code = "PROVIDER_UNAVAILABLE"


_BASE = "https://api.twelvedata.com"

_INTERVAL_MAP = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "1h": "1h",
    "4h": "4h",
    "1D": "1day",
    "1W": "1week",
}


class TwelveDataProvider(MarketDataProvider):
    name = "twelve_data"
    is_demo = False

    def __init__(
        self,
        *,
        api_key: str,
        max_retries: int = 3,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
        reference_instruments: list[dict] | None = None,
    ) -> None:
        self._key = api_key
        self._max_retries = max_retries
        self._timeout = timeout_seconds
        self._client = httpx.AsyncClient(transport=transport)
        self._last_call = 0.0
        self._min_interval = 60.0 / 8  # free tier: 8 credits/min
        self._instruments = reference_instruments or []
        self._exchange_by_symbol = {
            r["symbol"]: r.get("exchange") for r in self._instruments
            if r.get("exchange") in ("NSE", "BSE")
        }

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_instruments(self) -> list[dict]:
        return list(self._instruments)

    async def _get(self, path: str, params: dict) -> dict:
        params["apikey"] = self._key

        last_err = None
        for attempt in range(self._max_retries + 1):
            try:
                wait = self._min_interval - (time.monotonic() - self._last_call)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_call = time.monotonic()

                resp = await self._client.get(
                    f"{_BASE}{path}", params=params,
                    timeout=self._timeout,
                )
                body = resp.json()

                if body.get("code") == 429 or resp.status_code == 429:
                    await asyncio.sleep(min(2 ** attempt * 2, 30))
                    last_err = ProviderUnavailableError("rate limited by Twelve Data")
                    continue
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"upstream {resp.status_code}", request=resp.request, response=resp,
                    )
                resp.raise_for_status()
                return body
            except (httpx.TimeoutException, httpx.TransportError,
                    httpx.HTTPStatusError) as exc:
                last_err = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2 ** attempt * 0.5, 8))
            except httpx.HTTPError as exc:
                last_err = exc
                break

        raise ProviderUnavailableError(f"Twelve Data failed: {last_err}")

    # ------------------------------------------------------------------ quotes

    async def get_quote(self, symbol: str) -> dict | None:
        quotes = await self.get_quotes([symbol])
        return quotes[0] if quotes else None

    async def get_quotes(self, symbols: list[str]) -> list[dict]:
        """Batch quote — N symbols = N credits."""
        joined = ",".join(symbols)
        params: dict = {"symbol": joined}
        ex = self._exchange_for(symbols[0])
        if ex:
            params["exchange"] = ex
        data = await self._get("/quote", params)

        # Response is keyed by symbol when batch; single object when one symbol
        if len(symbols) == 1 and data.get("symbol"):
            return [self._map_quote(data)]

        out = []
        for s in symbols:
            r = data.get(s)
            if r and r.get("close") is not None:
                out.append(self._map_quote(r))
        return out

    def _map_quote(self, r: dict) -> dict:
        close = float(r.get("close", 0))
        prev = float(r.get("previous_close", 0)) if r.get("previous_close") else None
        change = (close - prev) if prev else None
        change_pct = (change / prev * 100) if prev else None
        return {
            "symbol": r.get("symbol", ""),
            "last_price": close,
            "previous_close": prev,
            "change": change,
            "change_pct": round(change_pct, 4) if change_pct is not None else None,
            "day_open": float(r["open"]) if r.get("open") else None,
            "day_high": float(r["high"]) if r.get("high") else None,
            "day_low": float(r["low"]) if r.get("low") else None,
            "volume": int(r.get("volume", 0)),
            "updated_at": datetime.now(timezone.utc),
            "is_demo": False,
        }

    # ------------------------------------------------------------------ candles

    async def get_candles(
        self, symbol: str, timeframe: str, bars: int,
        *, end_exclusive_index: int | None = None,
    ) -> list[dict]:
        interval = _INTERVAL_MAP.get(timeframe, "15min")
        params: dict = {
            "symbol": symbol, "interval": interval, "outputsize": bars,
        }
        ex = self._exchange_for(symbol)
        if ex:
            params["exchange"] = ex
        data = await self._get("/time_series", params)

        values = data.get("values", [])

        out = []
        for v in reversed(values):  # API returns newest-first → flip to oldest-first
            out.append({
                "ts": datetime.fromisoformat(v["datetime"] + " UTC".replace("UTC", "+00:00")),
                "open": float(v["open"]),
                "high": float(v["high"]),
                "low": float(v["low"]),
                "close": float(v["close"]),
                "volume": int(v.get("volume") or 0),
            })
        return out

    def _yf(self, symbol: str) -> str:
        """Twelve Data uses plain tickers for NSE — pass through."""
        return symbol

    def _exchange_for(self, symbol: str) -> str | None:
        return self._exchange_by_symbol.get(symbol)

    # ------------------------------------------------------------------ live

    async def get_live_quotes(self, symbols: list[str]) -> list[dict]:
        return await self.get_quotes(symbols)


__all__ = ["TwelveDataProvider"]
