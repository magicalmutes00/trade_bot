"""Notification persistence: FCM tokens + per-user preferences."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationPreference, NotificationToken
from app.models.enums import NotificationPlatform


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ tokens

    async def register_token(
        self, *, user_id: uuid.UUID, fcm_token: str,
        platform: NotificationPlatform, device_id: str | None,
    ) -> NotificationToken:
        """Upsert by token (unique). Re-registering on another account detaches it."""
        row = (
            await self.db.execute(
                select(NotificationToken).where(NotificationToken.fcm_token == fcm_token)
            )
        ).scalar_one_or_none()

        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        if row is None:
            row = NotificationToken(
                user_id=user_id,
                fcm_token=fcm_token,
                platform=platform,
                device_id=device_id,
                is_active=True,
                last_seen_at=now,
            )
            self.db.add(row)
        else:
            row.user_id = user_id
            row.platform = platform
            if device_id is not None:
                row.device_id = device_id
            row.is_active = True
            row.last_seen_at = now
        await self.db.flush()
        return row

    async def deactivate_token(self, *, user_id: uuid.UUID, fcm_token: str) -> bool:
        row = (
            await self.db.execute(
                select(NotificationToken).where(
                    NotificationToken.fcm_token == fcm_token,
                    NotificationToken.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None or not row.is_active:
            return False
        row.is_active = False
        await self.db.flush()
        return True

    async def active_tokens_for_user(self, user_id: uuid.UUID) -> list[NotificationToken]:
        rows = (
            await self.db.execute(
                select(NotificationToken)
                .where(
                    NotificationToken.user_id == user_id,
                    NotificationToken.is_active.is_(True),
                )
                .order_by(NotificationToken.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    async def tokens_for_user(self, user_id: uuid.UUID) -> list[NotificationToken]:
        rows = (
            await self.db.execute(
                select(NotificationToken)
                .where(NotificationToken.user_id == user_id)
                .order_by(NotificationToken.created_at.desc())
            )
        ).scalars().all()
        return list(rows)

    # ------------------------------------------------------------- preferences

    async def get_or_create_prefs(self, user_id: uuid.UUID) -> NotificationPreference:
        row = (
            await self.db.execute(
                select(NotificationPreference).where(
                    NotificationPreference.user_id == user_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = NotificationPreference(user_id=user_id)
            self.db.add(row)
            await self.db.flush()
        return row

    async def update_prefs(self, user_id: uuid.UUID, **fields) -> NotificationPreference:
        row = await self.get_or_create_prefs(user_id)
        for k, v in fields.items():
            if v is not None:
                setattr(row, k, v)
        await self.db.flush()
        return row

    # ------------------------------------------------------- delivery fan-out

    async def eligible_deliveries(self, *, direction: str, strength_value: int,
                                  instrument_id: uuid.UUID):
        """Rows of (fcm_token, prefs) for every device that should receive a
        signal with the given direction/strength. Python-side filtering keeps
        the SQL portable; volumes are small (prefs × tokens)."""
        rows = (
            await self.db.execute(
                select(NotificationPreference, NotificationToken)
                .join(NotificationToken, NotificationToken.user_id == NotificationPreference.user_id)
                .where(
                    NotificationPreference.push_enabled.is_(True),
                    NotificationToken.is_active.is_(True),
                )
            )
        ).all()

        watchlist_user_ids: set[uuid.UUID] | None = None  # lazy when needed

        out = []
        for prefs, token in rows:
            if direction == "BULLISH" and not prefs.bullish_alerts:
                continue
            if direction == "BEARISH" and not prefs.bearish_alerts:
                continue
            if prefs.strong_only and strength_value < _strength_rank("STRONG"):
                continue
            if _strength_rank(prefs.min_strength.value
                              if hasattr(prefs.min_strength, "value") else str(prefs.min_strength)) > strength_value:
                continue
            if prefs.watchlist_only:
                if watchlist_user_ids is None:
                    watchlist_user_ids = await self._users_with_alert_on(instrument_id)
                if prefs.user_id not in watchlist_user_ids:
                    continue
            out.append((prefs, token))

        return out

    async def _users_with_alert_on(self, instrument_id: uuid.UUID) -> set[uuid.UUID]:
        from app.models import WatchlistItem

        rows = (
            await self.db.execute(
                select(WatchlistItem.watchlist_id).where(
                    WatchlistItem.instrument_id == instrument_id,
                    WatchlistItem.alert_enabled.is_(True),
                )
            )
        ).all()
        if not rows:
            return set()
        wl_ids = [r[0] for r in rows]
        from app.models import Watchlist

        owners = (
            await self.db.execute(
                select(Watchlist.user_id).where(Watchlist.id.in_(wl_ids))
            )
        ).scalars().all()
        return set(owners)


_STRENGTH_ORDER = {"WEAK": 0, "MODERATE": 1, "STRONG": 2, "VERY_STRONG": 3}


def _strength_rank(name: str) -> int:
    return _STRENGTH_ORDER.get(str(name).upper(), 0)


__all__ = ["NotificationRepository", "_strength_rank"]
