"""NSE India provider tests via httpx.MockTransport — no network, no sidecar."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.services.providers.factory import build_provider
from app.services.providers.nse_provider import NseIndiaProvider

TCS_INFO = {"symbol": "TCS", "scripcode": "11536"}


def _ts(h: int, m: int = 0) -> datetime:
    return datetime(2026, 9, 28, h, m, tzinfo=timezone.utc)  # a Monday


def _chart_payload(bars: list[dict]) -> dict:
    return {
        "status": True,
        "data": [
            {
                "time": int(b["ts"].timestamp() * 1000),
                "open": b["open"], "high": b["high"], "low": b["low"],
                "close": b["close"], "volume": b["volume"],
            }
            for b in bars
        ],
    }


BARS_15M = [
    {"ts": _ts(10, 0), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
    {"ts": _ts(10, 15), "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.75, "volume": 1200},
    {"ts": _ts(10, 30), "open": 101.75, "high": 103.0, "low": 101.0, "close": 102.4, "volume": 1400},
]


def _provider(handler) -> NseIndiaProvider:
    return NseIndiaProvider(
        "https://nse.test", transport=httpx.MockTransport(handler)
    )


def _with_symbol_info(handler, info=None):
    """Route symbol-info to a canned response, delegate everything else."""
    def routed(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/charts/symbol-info":
            return httpx.Response(200, json=info or TCS_INFO)
        return handler(request)
    return routed


@pytest.mark.asyncio
async def test_get_candles_maps_chart_payload():
    seen = {}

    def chart(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_chart_payload(BARS_15M))

    p = _provider(_with_symbol_info(chart))
    bars = await p.get_candles("TCS", "15m", 100)

    assert seen["path"] == "/api/charts/equity-historical-data"
    assert seen["params"]["symbol"] == "TCS"
    assert seen["params"]["token"] == "11536"
    assert seen["params"]["chartType"] == "I"
    assert seen["params"]["timeInterval"] == "15"
    span_days = (int(seen["params"]["end"]) - int(seen["params"]["start"])) / 86400
    assert 0 < span_days <= 15          # epoch window sized to the request
    assert len(bars) == 3
    assert all(b["ts"].tzinfo is not None for b in bars)          # UTC-aware
    assert [b["ts"] for b in bars] == sorted(b["ts"] for b in bars)  # oldest-first
    assert bars[0]["open"] == 100.0 and bars[-1]["close"] == 102.4
    assert bars[0]["volume"] == 1000
    await p.aclose()


@pytest.mark.asyncio
async def test_get_candles_refuses_symbol_mismatch():
    """RELIANCE resolves to RCOM-BE on the charting API — the provider must
    refuse to serve another company's candles instead of poisoning charts."""
    called = {"chart": 0}

    def chart(request: httpx.Request) -> httpx.Response:
        called["chart"] += 1
        return httpx.Response(200, json=_chart_payload(BARS_15M))

    p = _provider(_with_symbol_info(
        chart, {"symbol": "RCOM-BE", "scripcode": "13188"}
    ))
    assert await p.get_candles("TCS", "15m", 100) == []
    assert called["chart"] == 0          # never even asked for candles
    await p.aclose()


@pytest.mark.asyncio
async def test_get_candles_daily_uses_chart_type_d():
    seen = {}

    def chart(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_chart_payload(BARS_15M[:1]))

    p = _provider(_with_symbol_info(chart))
    bars = await p.get_candles("TCS", "1D", 200)

    assert seen["params"]["chartType"] == "D"
    assert "timeInterval" not in seen["params"]
    assert len(bars) == 1
    await p.aclose()


@pytest.mark.asyncio
async def test_get_candles_intraday_window_capped_at_14_days():
    seen = {}

    def chart(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_chart_payload(BARS_15M[:1]))

    p = _provider(_with_symbol_info(chart))
    await p.get_candles("TCS", "15m", 5000)   # would want ~200 days of history

    span_days = (int(seen["params"]["end"]) - int(seen["params"]["start"])) / 86400
    assert span_days <= 14.5
    await p.aclose()


@pytest.mark.asyncio
async def test_get_candles_aggregates_4h_from_hourly():
    hourly = [
        {"ts": _ts(h), "open": 100 + h, "high": 101 + h, "low": 99 + h,
         "close": 100.5 + h, "volume": 100}
        for h in range(3, 9)   # 03:00 … 08:00 UTC, hourly
    ]

    def chart(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chart_payload(hourly))

    p = _provider(_with_symbol_info(chart))
    bars = await p.get_candles("TCS", "4h", 10)

    assert len(bars) == 2
    first, second = bars
    assert first["ts"] == _ts(3) and second["ts"] == _ts(7)
    assert first["high"] == 107.0 and first["low"] == 102.0   # max/min across fold
    assert first["close"] == 106.5 and first["volume"] == 400
    assert second["volume"] == 200 and second["close"] == 108.5
    await p.aclose()


@pytest.mark.asyncio
async def test_get_candles_aggregates_weekly_from_daily():
    daily = [
        {"ts": datetime(2026, 9, 21, tzinfo=timezone.utc) + timedelta(days=i),
         "open": 100, "high": 102, "low": 98, "close": 101, "volume": 100}
        for i in range(5)   # Mon–Fri, one ISO week
    ]

    def chart(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_chart_payload(daily))

    p = _provider(_with_symbol_info(chart))
    bars = await p.get_candles("TCS", "1W", 10)

    assert len(bars) == 1
    assert bars[0]["volume"] == 500 and bars[0]["close"] == 101
    await p.aclose()


@pytest.mark.asyncio
async def test_get_candles_drops_invalid_rows():
    payload = _chart_payload(BARS_15M)
    payload["data"].insert(1, {"time": int(_ts(10, 7).timestamp() * 1000),
                               "open": 100, "high": 101, "low": 99})   # no close
    payload["data"].append({"time": int(_ts(10, 45).timestamp() * 1000),
                            "open": 0, "high": 0, "low": 0, "close": 0, "volume": 5})

    def chart(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    p = _provider(_with_symbol_info(chart))
    bars = await p.get_candles("TCS", "15m", 100)
    assert len(bars) == 3   # missing-close and zero-price rows dropped
    await p.aclose()


@pytest.mark.asyncio
async def test_get_candles_http_error_returns_empty():
    def chart(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "NSE down"})

    p = _provider(_with_symbol_info(chart))
    assert await p.get_candles("TCS", "15m", 100) == []
    await p.aclose()


@pytest.mark.asyncio
async def test_get_quote_maps_price_info():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/equity/TCS"
        return httpx.Response(200, json={
            "priceInfo": {
                "lastPrice": 3123.45, "previousClose": 3100.0,
                "change": 23.45, "pChange": 0.76,
                "open": 3105.0, "dayHigh": 3130.0, "dayLow": 3095.0,
            },
            "tradeInfo": {"totalTradedVolume": 2500000},
        })

    p = _provider(handler)
    q = await p.get_quote("TCS")

    assert q["symbol"] == "TCS"
    assert q["last_price"] == 3123.45
    assert q["previous_close"] == 3100.0
    assert q["change_pct"] == 0.76
    assert q["day_open"] == 3105.0 and q["day_high"] == 3130.0
    assert q["volume"] == 2500000
    assert q["is_demo"] is False
    await p.aclose()


@pytest.mark.asyncio
async def test_get_quote_missing_price_returns_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"priceInfo": {}})

    p = _provider(handler)
    assert await p.get_quote("TCS") is None
    await p.aclose()


def test_factory_nse_india_with_url(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "nse_india")
    monkeypatch.setenv("NSE_PROVIDER_URL", "https://nse.test")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        p = build_provider()
        assert type(p).__name__ == "NseIndiaProvider" and p.is_demo is False
    finally:
        get_settings.cache_clear()


def test_factory_nse_india_without_url_falls_back_to_yahoo(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "nse_india")
    monkeypatch.setenv("NSE_PROVIDER_URL", "")   # explicit empty — overrides local .env
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        p = build_provider()
        assert type(p).__name__ == "YahooFinanceProvider" and p.is_demo is False
    finally:
        get_settings.cache_clear()
