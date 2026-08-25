"""Domain enumerations shared across models and schemas.

Stored as VARCHAR + CHECK constraints (``native_enum=False``) so the schema
stays portable and future enum additions are simple ALTER TABLE statements.
"""

import enum


class UserRole(str, enum.Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class AuthProvider(str, enum.Enum):
    PASSWORD = "PASSWORD"  # legacy email/password accounts
    GOOGLE = "GOOGLE"      # Firebase Google Sign-In


class InstrumentType(str, enum.Enum):
    STOCK = "STOCK"
    INDEX = "INDEX"
    COMMODITY = "COMMODITY"
    FOREX = "FOREX"
    CRYPTO = "CRYPTO"


class Timeframe(str, enum.Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1h"
    H4 = "4h"
    D1 = "1D"
    W1 = "1W"


class SignalDirection(str, enum.Enum):
    BULLISH = "BULLISH"
    BEARISH = "BEARISH"


class SignalType(str, enum.Enum):
    """Signal families produced by the BOF engine (see docs/bof-engine.md)."""

    BOF = "BOF"  # Breakout failure


class SignalStrength(str, enum.Enum):
    WEAK = "WEAK"
    MODERATE = "MODERATE"
    STRONG = "STRONG"
    VERY_STRONG = "VERY_STRONG"


class SignalStatus(str, enum.Enum):
    DETECTING = "DETECTING"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    CLOSED = "CLOSED"


class MarketName(str, enum.Enum):
    NSE = "NSE"
    BSE = "BSE"
    MCX = "MCX"
    CDS = "CDS"
    CRYPTO = "CRYPTO"


class SessionStatus(str, enum.Enum):
    PRE_OPEN = "PRE_OPEN"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALF_DAY = "HALF_DAY"
    HOLIDAY = "HOLIDAY"


class NotificationPlatform(str, enum.Enum):
    ANDROID = "ANDROID"
    IOS = "IOS"
    WEB = "WEB"


class LogLevel(str, enum.Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ThemeMode(str, enum.Enum):
    DARK = "DARK"
    LIGHT = "LIGHT"
    SYSTEM = "SYSTEM"
