"""Provider factory + registry (Phase 8 selection point)."""

import logging

from app.core.config import settings
from app.services.providers.base import MarketDataProvider
from app.services.providers.demo_provider import DemoMarketDataProvider

logger = logging.getLogger(__name__)


def build_provider(reference_instruments: list[dict] | None = None) -> MarketDataProvider:
    """Return the configured provider.

    - ``MARKET_DATA_PROVIDER=demo``  → deterministic demo data (default).
    - ``MARKET_DATA_PROVIDER=real``  → REST vendor; requires MARKET_DATA_API_KEY,
      raises ProviderNotConfiguredError otherwise.
    - ``MARKET_DATA_PROVIDER=twelve_data`` → Twelve Data; without an API key it
      degrades to the keyless Yahoo provider (never silently synthetic).
    """
    from app.core.config import get_settings

    current = get_settings()
    if current.MARKET_DATA_PROVIDER == "real":
        from app.services.providers.real_provider import (
            ProviderNotConfiguredError,
            RealMarketDataProvider,
        )

        return RealMarketDataProvider(
            api_key=current.MARKET_DATA_API_KEY,
            base_url=current.MARKET_BASE_URL,
            max_retries=current.MARKET_MAX_RETRIES,
        )
    if current.MARKET_DATA_PROVIDER == "yahoo":
        from app.services.providers.yahoo_provider import YahooFinanceProvider

        return YahooFinanceProvider(reference_instruments)
    if current.MARKET_DATA_PROVIDER == "twelve_data":
        from app.services.providers.twelve_provider import (
            TwelveDataProvider,
        )

        if current.MARKET_DATA_API_KEY:
            return TwelveDataProvider(
                api_key=current.MARKET_DATA_API_KEY,
                reference_instruments=reference_instruments,
            )
        # Graceful degradation — real keyless data beats silent demo data.
        import logging

        logging.getLogger(__name__).warning(
            "MARKET_DATA_PROVIDER=twelve_data but MARKET_DATA_API_KEY not set — "
            "falling back to Yahoo Finance provider"
        )
        from app.services.providers.yahoo_provider import YahooFinanceProvider

        return YahooFinanceProvider(reference_instruments)
    return DemoMarketDataProvider(reference_instruments)


async def build_verified_provider(
    reference_instruments: list[dict] | None = None,
) -> MarketDataProvider:
    """Build the configured provider and PROBE it with one real request.

    Guards against misconfigured plans (e.g. Twelve Data free tier doesn't
    include NSE — every request 404s). If the primary provider can't serve
    our instruments we degrade to Yahoo, keeping real data flowing, and log
    the reason prominently. Re-run after fixing config + restarting service.
    """
    provider = build_provider(reference_instruments)
    if provider.is_demo or not reference_instruments:
        return provider

    symbol = reference_instruments[0]["symbol"]
    try:
        quote = await provider.get_quote(symbol)
        if quote and quote.get("last_price") is not None:
            logger.info("provider probe OK (%s → %s)", provider.name, symbol)
            return provider
        logger.warning(
            "provider %s returned no quote for %s — degrading to Yahoo",
            provider.name, symbol,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "provider %s probe failed (%s) — degrading to Yahoo",
            provider.name, str(exc)[:160],
        )

    if hasattr(provider, "aclose"):
        try:
            await provider.aclose()
        except Exception:  # noqa: BLE001
            pass
    from app.services.providers.yahoo_provider import YahooFinanceProvider

    return YahooFinanceProvider(reference_instruments)


__all__ = ["build_provider", "build_verified_provider"]
