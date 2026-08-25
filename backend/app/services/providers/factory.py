"""Provider factory + registry (Phase 8 selection point)."""

from app.core.config import settings
from app.services.providers.base import MarketDataProvider
from app.services.providers.demo_provider import DemoMarketDataProvider


def build_provider(reference_instruments: list[dict] | None = None) -> MarketDataProvider:
    """Return the configured provider.

    - ``MARKET_DATA_PROVIDER=demo``  → deterministic demo data (default).
    - ``MARKET_DATA_PROVIDER=real``  → REST vendor; requires MARKET_DATA_API_KEY,
      raises ProviderNotConfiguredError otherwise.
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
    return DemoMarketDataProvider(reference_instruments)


__all__ = ["build_provider"]
