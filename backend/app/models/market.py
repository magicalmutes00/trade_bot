"""Market reference data: sectors, instruments, latest quotes, candles, sessions."""

import uuid
from datetime import date, datetime

import sqlalchemy as sa
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import InstrumentType, MarketName, SessionStatus, Timeframe


class Sector(Base):
    __tablename__ = "sectors"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    instruments: Mapped[list["Instrument"]] = relationship(back_populates="sector")


class Instrument(TimestampMixin, Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("symbol", "exchange", name="uq_instruments_symbol_exchange"),
        Index("ix_instruments_type_active", "instrument_type", "is_active"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    symbol: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), default="NSE", nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    instrument_type: Mapped[InstrumentType] = mapped_column(
        sa.Enum(InstrumentType, native_enum=False, length=16), nullable=False
    )
    sector_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("sectors.id", ondelete="SET NULL")
    )
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    tick_size: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    lot_size: Mapped[int | None] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    sector: Mapped[Sector | None] = relationship(back_populates="instruments")
    market_data: Mapped["MarketData | None"] = relationship(
        back_populates="instrument", uselist=False, cascade="all, delete-orphan",
        passive_deletes=True,
    )


class MarketData(TimestampMixin, Base):
    """Latest quote snapshot per instrument (heatmap / dashboard friendly).

    Raw high-frequency ticks are intentionally NOT persisted here; historical
    series live in ``candles``. This table is safe to upsert frequently and can
    be moved to a dedicated time-series store later without schema changes.
    """

    __tablename__ = "market_data"

    id: Mapped[uuid.UUID] = uuid_pk()
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("instruments.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    last_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    change: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    day_open: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    day_high: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    day_low: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        index=True,
        nullable=False,
    )

    instrument: Mapped[Instrument] = relationship(back_populates="market_data")


class Candle(Base):
    """OHLCV bar. Primary key prevents duplicate candles per timeframe.

    Designed so the table can later be moved to a time-series engine while
    keeping the same access pattern (range scans by instrument + timeframe).
    """

    __tablename__ = "candles"
    __table_args__ = (
        Index("ix_candles_ts", "ts"),
    )

    instrument_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("instruments.id", ondelete="CASCADE"), primary_key=True
    )
    timeframe: Mapped[Timeframe] = mapped_column(
        sa.Enum(Timeframe, native_enum=False, length=4), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)


class MarketSession(Base):
    """Trading-calendar rows: open/closed/holiday per market per date."""

    __tablename__ = "market_sessions"

    id: Mapped[uuid.UUID] = uuid_pk()
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    market: Mapped[MarketName] = mapped_column(
        sa.Enum(MarketName, native_enum=False, length=16),
        default=MarketName.NSE, nullable=False,
    )
    status: Mapped[SessionStatus] = mapped_column(
        sa.Enum(SessionStatus, native_enum=False, length=16), nullable=False
    )
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("market", "session_date", name="uq_market_sessions_market_date"),)



