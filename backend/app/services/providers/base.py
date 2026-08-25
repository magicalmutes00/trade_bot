"""MarketDataProvider abstraction (spec §17) — swap providers without touching callers."""

import abc


class MarketDataProvider(abc.ABC):
    """Contract every market-data source must fulfil.

    All methods return plain dicts/dataclasses; nothing here knows about ORM
    models so providers stay testable and swappable (demo → real in Phase 8).
    """

    name: str = "abstract"
    is_demo: bool = False

    @abc.abstractmethod
    async def get_instruments(self) -> list[dict]:
        """Reference catalogue: [{symbol, exchange, name, instrument_type, sector}]"""

    @abc.abstractmethod
    async def get_quote(self, symbol: str) -> dict | None:
        """Latest quote snapshot for one symbol."""

    @abc.abstractmethod
    async def get_quotes(self, symbols: list[str]) -> list[dict]:
        """Batch quote snapshot."""

    @abc.abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str,
        bars: int,
        *,
        end_exclusive_index: int | None = None,
    ) -> list[dict]:
        """Most recent OHLCV bars, oldest-first:
        [{ts, open, high, low, close, volume}, …]"""

    def subscribe_realtime(self):  # pragma: no cover - Phase 4 (WebSocket)
        raise NotImplementedError("Realtime streaming arrives in Phase 4")


__all__ = ["MarketDataProvider"]
