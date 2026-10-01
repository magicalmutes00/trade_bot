"""NSE India provider — live candles + quotes via the stock-nse-india sidecar.

The sidecar (vendored ``stock-nse-india/``, deployed as ``bof-nse-provider``)
fronts NSE's own charting/quote endpoints and handles the cookie/session dance
that api.nseindia.com requires. This provider speaks plain HTTP to it:

- Candles: ``GET /api/charts/equity-historical-data``
  → ``{status, data: [{time(ms), open, high, low, close, volume}, …]}``
  ``timeInterval`` is plain minutes ('1','5','15','30','60'); ``chartType``
  'I' intraday / 'D' daily. There is no native 4h — aggregated from hourly.
- Quotes:  ``GET /api/equity/{symbol}``
  → ``{priceInfo: {lastPrice, change, pChange, open, dayHigh, dayLow,
  previousClose, …}, tradeInfo: {totalTradedVolume, …}}``

Notes:
- NSE timestamps are absolute epoch milliseconds — UTC-safe to convert.
- Intraday chart queries are capped at ~2 weeks per request (charting API
  limit), which still yields 250+ 15-minute bars per call.
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.core.logging import get_logger
from app.services.providers.base import MarketDataProvider

logger = get_logger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

# timeframe value → (chart timeInterval in minutes, chartType)
_INTERVAL_MAP = {
    "1m": (1, "I"),
    "5m": (5, "I"),
    "15m": (15, "I"),
    "30m": (30, "I"),
    "1h": (60, "I"),
    "4h": (60, "I"),      # aggregated from hourly below
    "1D": (None, "D"),
    "1W": (None, "D"),    # aggregated from daily below
}

_TRADING_MINUTES_PER_DAY = 375   # 09:15–15:30 IST
_MAX_INTRADAY_DAYS = 14


class NseIndiaProvider(MarketDataProvider):
    name = "nse_india"
    is_demo = False

    def __init__(
        self,
        base_url: str,
        reference_instruments: list[dict] | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._instruments = reference_instruments or []
        self._client = httpx.AsyncClient(
            headers=_HEADERS,
            timeout=httpx.Timeout(20.0),
            transport=transport,
        )
        self._last_call = 0.0
        self._min_interval = 0.55
        # symbol → scripcode (or None = lookup mismatched, refuse to serve)
        self._token_cache: dict[str, str | None] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    # ------------------------------------------------------------- transport

    async def _get(self, path: str, params: dict) -> dict | list | None:
        wait = max(0, self._min_interval - (time.monotonic() - self._last_call))
        if wait > 0:
            await asyncio.sleep(wait)
        self._last_call = time.monotonic()
        try:
            resp = await self._client.get(f"{self._base}{path}", params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as exc:
            logger.warning("NSE sidecar %s returned %s", path, exc.response.status_code)
            return None
        except Exception as exc:
            logger.warning("NSE sidecar %s failed: %s", path, str(exc)[:160])
            return None

    async def _token_for(self, symbol: str) -> str | None:
        """Scripcode for ``symbol`` via the sidecar's symbol-info lookup.

        The lookup is only trusted when the RESOLVED symbol matches the
        requested one — NSE's charting symbolsDynamic falls back to the first
        list entry, which silently serves another company's candles (querying
        RELIANCE resolves to RCOM-BE, Reliance Communications, at ₹0.85).
        A mismatch caches None and the provider refuses to serve that symbol.
        """
        if symbol in self._token_cache:
            return self._token_cache[symbol]
        info = await self._get("/api/charts/symbol-info", {"symbol": symbol})
        token: str | None = None
        if isinstance(info, dict) and info.get("scripcode"):
            resolved = str(info.get("symbol") or "").upper()
            base = symbol.upper()
            if resolved == base or resolved.split("-")[0] == base:
                token = str(info["scripcode"])
            else:
                logger.warning(
                    "NSE symbol-info mismatch for %s (resolved %s) — refusing to serve",
                    symbol, resolved,
                )
        self._token_cache[symbol] = token
        return token

    async def _chart_bars(
        self, symbol: str, minutes: int | None, chart_type: str, days: int
    ) -> list[dict]:
        """Raw OHLCV dicts (oldest-first) for one chart query."""
        token = await self._token_for(symbol)
        if token is None:
            return []
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        data = await self._get(
            "/api/charts/equity-historical-data",
            {
                "symbol": symbol,
                "token": token,
                # epoch seconds — date-only `end` truncates the current session
                "start": str(int(start.timestamp())),
                "end": str(int(end.timestamp())),
                "chartType": chart_type,
                **({"timeInterval": str(minutes)} if minutes else {}),
            },
        )
        if not data:
            return []
        items = data.get("data", []) if isinstance(data, dict) else data
        bars: list[dict] = []
        for item in items or []:
            try:
                ts_ms = int(item["time"])
                o = float(item["open"])
                h = float(item["high"])
                low = float(item["low"])
                c = float(item["close"])
            except (KeyError, TypeError, ValueError):
                continue
            if min(o, h, low, c) <= 0 or not ts_ms:
                continue
            bars.append({
                "ts": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc),
                "open": round(o, 2),
                "high": round(h, 2),
                "low": round(low, 2),
                "close": round(c, 2),
                "volume": int(item.get("volume") or 0),
            })
        return bars

    # ------------------------------------------------------------- interface

    async def get_instruments(self) -> list[dict]:
        return list(self._instruments)

    async def get_quote(self, symbol: str) -> dict | None:
        data = await self._get(f"/api/equity/{symbol}", {})
        if not isinstance(data, dict):
            return None
        price = data.get("priceInfo") or {}
        last = price.get("lastPrice")
        if last is None:
            return None
        prev = price.get("previousClose")
        change = (last - prev) if (prev is not None and last is not None) else None
        trade_info = data.get("tradeInfo") or {}
        volume = price.get("totalTradedVolume") or trade_info.get("totalTradedVolume")
        return {
            "symbol": symbol,
            "last_price": round(float(last), 2),
            "previous_close": prev,
            "change": change,
            "change_pct": price.get("pChange"),
            "day_open": price.get("open"),
            "day_high": price.get("dayHigh"),
            "day_low": price.get("dayLow"),
            "volume": int(volume or 0),
            "updated_at": datetime.now(timezone.utc),
            "is_demo": False,
        }

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
        minutes, chart_type = _INTERVAL_MAP.get(timeframe, (15, "I"))
        if chart_type == "I":
            days = min(
                _MAX_INTRADAY_DAYS,
                max(1, -(-bars * (minutes or 15) // _TRADING_MINUTES_PER_DAY) + 1),
            )
        else:
            days = min(366, max(7, int(bars * 1.5) + 2))

        raw = await self._chart_bars(symbol, minutes, chart_type, days)
        if timeframe == "4h":
            raw = _aggregate_4h(raw)
        elif timeframe == "1W":
            raw = _aggregate_weekly(raw)
        return raw[-bars:] if bars else raw


def _aggregate_4h(bars: list[dict]) -> list[dict]:
    """Fold consecutive hourly bars into 4-hour candles (oldest-first input)."""
    out: list[dict] = []
    for b in bars:
        if out and (b["ts"] - out[-1]["ts"]).total_seconds() < 4 * 3600 \
                and out[-1]["ts"].date() == b["ts"].date():
            last = out[-1]
            last["high"] = max(last["high"], b["high"])
            last["low"] = min(last["low"], b["low"])
            last["close"] = b["close"]
            last["volume"] += b["volume"]
        else:
            out.append(dict(b))
    return out


def _aggregate_weekly(bars: list[dict]) -> list[dict]:
    """Fold daily bars into ISO-week candles (oldest-first input)."""
    out: list[dict] = []
    for b in bars:
        iso = b["ts"].isocalendar()[:2]
        if out and out[-1]["_week"] == iso:
            last = out[-1]
            last["high"] = max(last["high"], b["high"])
            last["low"] = min(last["low"], b["low"])
            last["close"] = b["close"]
            last["volume"] += b["volume"]
        else:
            merged = dict(b)
            merged["_week"] = iso
            out.append(merged)
    for bar in out:
        bar.pop("_week", None)
    return out


__all__ = ["NseIndiaProvider"]
