"""RealMarketDataProvider — REST vendor client with production hygiene.

Phase 8 scaffolding for a live vendor. The wire format is intentionally a
thin, documented convention (see ``docs/api.md`` § provider contract); a new
vendor only needs an adapter function mapping its JSON to our dicts.

Production behaviours:
- API key from ``MARKET_DATA_API_KEY`` (never hard-coded)
- token-bucket rate limiting (``MARKET_RATE_LIMIT_PER_SEC``)
- retries with exponential backoff on 5xx / transport errors
- 429 honours ``Retry-After``
- hard timeout per request
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.core.errors import AppError
from app.services.providers.base import MarketDataProvider


class ProviderUnavailableError(AppError):
    status_code = 503
    code = "PROVIDER_UNAVAILABLE"


class ProviderNotConfiguredError(ProviderUnavailableError):
    code = "PROVIDER_NOT_CONFIGURED"


class RealMarketDataProvider(MarketDataProvider):
    name = "real"
    is_demo = False

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        max_retries: int = 3,
        min_request_interval: float = 0.2,
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ProviderNotConfiguredError(
                "MARKET_DATA_API_KEY is required for the real provider"
            )
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._min_interval = min_request_interval
        self._timeout = timeout_seconds
        self._last_call = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            transport=transport,
            headers={"X-API-Key": api_key},
        )

    # ------------------------------------------------------------------ core

    async def _throttle(self) -> None:
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def _get(self, path: str, params: dict | None = None) -> dict:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                await self._throttle()
                response = await self._client.get(
                    path, params=params, timeout=self._timeout
                )
                if response.status_code == 429:
                    retry_after = float(response.headers.get("Retry-After", 2 ** attempt))
                    await asyncio.sleep(min(retry_after, 30.0))
                    last_error = ProviderUnavailableError("rate limited")
                    continue
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"upstream {response.status_code}", request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.TransportError,
                    httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    await asyncio.sleep(min(2 ** attempt * 0.5, 8.0))
            except httpx.HTTPError as exc:
                last_error = exc
                break

        raise ProviderUnavailableError(f"market-data upstream failed: {last_error}")

    # ------------------------------------------------------------- interface

    async def get_instruments(self) -> list[dict]:
        data = await self._get("/instruments")
        items = data if isinstance(data, list) else data.get("items", [])
        return [
            {
                "symbol": r["symbol"],
                "exchange": r.get("exchange", ""),
                "name": r.get("name", r["symbol"]),
                "instrument_type": r.get("instrument_type", "STOCK"),
                "sector": r.get("sector"),
            }
            for r in items
        ]

    def _map_quote(self, symbol: str, r: dict) -> dict:
        return {
            "symbol": symbol,
            "last_price": float(r["close"]),
            "previous_close": _opt_float(r.get("previous_close")),
            "change": _opt_float(r.get("change")),
            "change_pct": _opt_float(r.get("change_pct")),
            "day_open": _opt_float(r.get("open")),
            "day_high": _opt_float(r.get("high")),
            "day_low": _opt_float(r.get("low")),
            "volume": int(r.get("volume") or 0),
            "updated_at": _parse_ts(r.get("ts")) or datetime.now(timezone.utc),
            "is_demo": False,
        }

    async def get_quote(self, symbol: str) -> dict | None:
        data = await self._get("/quote", {"symbols": symbol})
        rows = data if isinstance(data, list) else data.get("items", [])
        return self._map_quote(symbol, rows[0]) if rows else None

    async def get_quotes(self, symbols: list[str]) -> list[dict]:
        data = await self._get("/quote", {"symbols": ",".join(symbols)})
        rows = data if isinstance(data, list) else data.get("items", [])
        return [self._map_quote(r.get("symbol", s), r)
                for s, r in zip(symbols, rows)]

    async def get_candles(
        self, symbol: str, timeframe: str, bars: int,
        *, end_exclusive_index: int | None = None,
    ) -> list[dict]:
        data = await self._get("/candles", {
            "symbol": symbol, "interval": timeframe, "bars": bars,
        })
        rows = data if isinstance(data, list) else data.get("items", [])
        return [self._map_candle(r) for r in rows[-bars:]]

    @staticmethod
    def _map_candle(r: dict) -> dict:
        ts = _parse_ts(r.get("ts")) or _parse_ts(r.get("t"))
        return {
            "ts": ts,
            "open": float(r["open"]),
            "high": float(r["high"]),
            "low": float(r["low"]),
            "close": float(r["close"]),
            "volume": int(r.get("volume") or 0),
        }

    async def aclose(self) -> None:
        await self._client.aclose()


def _opt_float(v) -> float | None:
    return float(v) if v is not None else None


def _parse_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            dt = datetime.fromtimestamp(int(text) / 1000, tz=timezone.utc)
        except (ValueError, OverflowError):
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


__all__ = ["RealMarketDataProvider", "ProviderUnavailableError", "ProviderNotConfiguredError"]
