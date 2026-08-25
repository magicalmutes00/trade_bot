"""Model package — importing this module registers all tables on Base.metadata.

Alembic and tests should import from here so every table is discovered.
"""

from app.db.session import Base
from app.models.base import TimestampMixin
from app.models.enums import (
    AuthProvider,
    InstrumentType,
    LogLevel,
    MarketName,
    NotificationPlatform,
    SessionStatus,
    SignalDirection,
    SignalStatus,
    SignalStrength,
    SignalType,
    ThemeMode,
    Timeframe,
    UserRole,
)
from app.models.user import PasswordResetToken, User, UserSession
from app.models.market import Candle, Instrument, MarketData, MarketSession, Sector
from app.models.signal import Signal, SignalEvent
from app.models.engagement import (
    NotificationPreference,
    NotificationToken,
    SystemEvent,
    UserSetting,
    Watchlist,
    WatchlistItem,
)

__all__ = [
    "Base",
    "TimestampMixin",
    "AuthProvider",
    "UserRole",
    "InstrumentType",
    "Timeframe",
    "SignalDirection",
    "SignalType",
    "SignalStrength",
    "SignalStatus",
    "MarketName",
    "SessionStatus",
    "NotificationPlatform",
    "LogLevel",
    "ThemeMode",
    "User",
    "UserSession",
    "PasswordResetToken",
    "Sector",
    "Instrument",
    "MarketData",
    "Candle",
    "MarketSession",
    "Signal",
    "SignalEvent",
    "Watchlist",
    "WatchlistItem",
    "NotificationToken",
    "NotificationPreference",
    "UserSetting",
    "SystemEvent",
]
