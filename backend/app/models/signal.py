"""BOF signal models: signals and their immutable event trail."""

import uuid
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import SignalDirection, SignalStatus, SignalStrength, SignalType, Timeframe


class Signal(TimestampMixin, Base):
    """A BOF (breakout-failure) signal produced by the engine.

    ``metadata`` is a reserved attribute name in SQLAlchemy's declarative API,
    so the column is exposed as ``signal_metadata`` while the DB column stays
    ``metadata`` as per the product schema.
    """

    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_instrument_timeframe", "instrument_id", "timeframe"),
        Index("ix_signals_detected_at", "detected_at"),
        Index("ix_signals_status_strength", "status", "strength"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("instruments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    timeframe: Mapped[Timeframe] = mapped_column(
        sa.Enum(Timeframe, native_enum=False, length=4), nullable=False
    )
    signal_type: Mapped[SignalType] = mapped_column(
        sa.Enum(SignalType, native_enum=False, length=16),
        default=SignalType.BOF, nullable=False,
    )
    direction: Mapped[SignalDirection] = mapped_column(
        sa.Enum(SignalDirection, native_enum=False, length=8), nullable=False
    )
    bof_level: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    breakout_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    failure_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    stop_reference: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    strength: Mapped[SignalStrength] = mapped_column(
        sa.Enum(SignalStrength, native_enum=False, length=12),
        default=SignalStrength.WEAK, nullable=False,
    )
    status: Mapped[SignalStatus] = mapped_column(
        sa.Enum(SignalStatus, native_enum=False, length=12),
        default=SignalStatus.DETECTING, nullable=False,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    signal_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)

    instrument = relationship("Instrument", lazy="raise")
    events: Mapped[list["SignalEvent"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan", passive_deletes=True,
        lazy="selectin",
    )


class SignalEvent(Base):
    """Append-only lifecycle trail for a signal (DETECTED â†’ CONFIRMED â†’ â€¦)."""

    __tablename__ = "signal_events"
    __table_args__ = (Index("ix_signal_events_signal_created", "signal_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    signal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("signals.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str | None] = mapped_column(Text)
    event_data: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    signal: Mapped[Signal] = relationship(back_populates="events")

