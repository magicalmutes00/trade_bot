"""Real provider tests via httpx.MockTransport — no network, no keys."""

import httpx
import pytest

from app.services.providers.factory import build_provider
from app.services.providers.real_provider import (
    ProviderNotConfiguredError,
    RealMarketDataProvider,
)


def make_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


CANDLES_JSON = {
    "items": [
        {"ts": "2026-08-20T10:00:00Z", "open": 100, "high": 101,
         "low": 99, "close": 100.5, "volume": 1234},
        {"ts": "2026-08-20T10:15:00Z", "open": 100.5, "high": 102,
         "low": 100, "close": 101.75, "volume": 1500},
    ]
}


@pytest.mark.asyncio
async def test_get_candles_maps_and_trims():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        seen["key_header"] = request.headers.get("X-API-Key")
        return httpx.Response(200, json=CANDLES_JSON)

    p = RealMarketDataProvider(api_key="k", base_url="https://v.test",
                              transport=httpx.MockTransport(handler))
    bars = await p.get_candles("TCS", "15m", 5)

    assert seen["path"] == "/candles"
    assert seen["params"]["symbol"] == "TCS"
    assert seen["key_header"] == "k"
    assert len(bars) == 2
    assert bars[-1]["close"] == pytest.approx(101.75)
    assert bars[0]["high"] >= bars[0]["close"]
    await p.aclose()


@pytest.mark.asyncio
async def test_retries_on_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"items": []})

    p = RealMarketDataProvider(api_key="k", base_url="https://v.test",
                              max_retries=3,
                              transport=httpx.MockTransport(handler))
    instruments = await p.get_instruments()
    assert instruments == [] and calls["n"] == 3
    await p.aclose()


@pytest.mark.asyncio
async def test_gives_up_after_max_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    from app.services.providers.real_provider import ProviderUnavailableError

    p = RealMarketDataProvider(api_key="k", base_url="https://v.test",
                               max_retries=1,
                               transport=httpx.MockTransport(handler))
    try:
        await p.get_quote("TCS")
        raised = False
    except ProviderUnavailableError:
        raised = True
    assert raised
    await p.aclose()


def test_missing_api_key_raises_not_configured():
    with pytest.raises(ProviderNotConfiguredError):
        RealMarketDataProvider(api_key=None, base_url="https://v.test")


def test_factory_selects_demo_by_default():
    p = build_provider()
    assert p.is_demo is True and type(p).__name__ == "DemoMarketDataProvider"


def test_factory_builds_real_when_configured(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "real")
    monkeypatch.setenv("MARKET_DATA_API_KEY", "test-key")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        p = build_provider()
        assert p.is_demo is False and type(p).__name__ == "RealMarketDataProvider"
    finally:
        get_settings.cache_clear()


def test_factory_twelve_data_with_key(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelve_data")
    monkeypatch.setenv("MARKET_DATA_API_KEY", "td-key")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        p = build_provider()
        assert type(p).__name__ == "TwelveDataProvider" and p.is_demo is False
    finally:
        get_settings.cache_clear()


def test_factory_twelve_data_without_key_falls_back_to_yahoo(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "twelve_data")
    monkeypatch.setenv("MARKET_DATA_API_KEY", "")   # explicit empty — overrides local .env
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        p = build_provider()
        assert type(p).__name__ == "YahooFinanceProvider" and p.is_demo is False
    finally:
        get_settings.cache_clear()


def test_factory_yahoo_selected_explicitly(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "yahoo")
    from app.core.config import get_settings

    get_settings.cache_clear()
    try:
        p = build_provider()
        assert type(p).__name__ == "YahooFinanceProvider" and p.is_demo is False
    finally:
        get_settings.cache_clear()
