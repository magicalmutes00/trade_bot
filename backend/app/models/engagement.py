"""User-scoped models: watchlists, notifications, settings, system events."""

import uuid
from datetime import datetime

import sqlalchemy as sa

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.base import TimestampMixin, uuid_pk
from app.models.enums import LogLevel, NotificationPlatform, SignalStrength, ThemeMode, Timeframe


class Watchlist(TimestampMixin, Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_watchlists_user_name"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    items: Mapped[list["WatchlistItem"]] = relationship(
        back_populates="watchlist",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WatchlistItem.position",
        lazy="selectin",
    )


class WatchlistItem(Base):
    __tablename__ = "watchlist_items"
    __table_args__ = (
        UniqueConstraint("watchlist_id", "instrument_id", name="uq_watchlist_items_unique"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    watchlist_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("watchlists.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instrument_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("instruments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    alert_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    watchlist: Mapped[Watchlist] = relationship(back_populates="items")


class NotificationToken(Base):
    """FCM device tokens. Tokens are device-scoped, never shared."""

    __tablename__ = "notification_tokens"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    fcm_token: Mapped[str] = mapped_column(String(4096), unique=True, nullable=False)
    platform: Mapped[NotificationPlatform] = mapped_column(
        sa.Enum(NotificationPlatform, native_enum=False, length=8),
        default=NotificationPlatform.ANDROID, nullable=False,
    )
    device_id: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class NotificationPreference(TimestampMixin, Base):
    __tablename__ = "notification_preferences"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    push_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    bullish_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    bearish_alerts: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    strong_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    watchlist_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_strength: Mapped[SignalStrength] = mapped_column(
        sa.Enum(SignalStrength, native_enum=False, length=12),
        default=SignalStrength.MODERATE, nullable=False,
    )


class UserSetting(TimestampMixin, Base):
    __tablename__ = "user_settings"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    theme: Mapped[ThemeMode] = mapped_column(
        sa.Enum(ThemeMode, native_enum=False, length=8),
        default=ThemeMode.SYSTEM, nullable=False,
    )
    default_timeframe: Mapped[Timeframe] = mapped_column(
        sa.Enum(Timeframe, native_enum=False, length=4),
        default=Timeframe.M15, nullable=False,
    )
    preferences: Mapped[dict | None] = mapped_column(JSON)


class SystemEvent(Base):
    """Operational log entries surfaced in the admin panel (Phase 7)."""

    __tablename__ = "system_events"
    __table_args__ = (Index("ix_system_events_source_created", "source", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    level: Mapped[LogLevel] = mapped_column(
        sa.Enum(LogLevel, native_enum=False, length=10), nullable=False
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

