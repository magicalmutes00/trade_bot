"""Profile and user-settings services."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import User, UserSetting
from app.repositories.user_repository import UserRepository
from app.schemas.user import ProfileUpdateRequest, UserSettingsUpdateRequest


class ProfileService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)

    async def get_profile(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Account not found")
        return user

    async def update_profile(self, user: User, payload: ProfileUpdateRequest) -> User:
        if payload.display_name is not None:
            user.display_name = payload.display_name.strip() or None
        if payload.avatar_url is not None:
            avatar = payload.avatar_url.strip()
            if avatar and not avatar.lower().startswith(("http://", "https://")):
                from app.core.errors import ValidationError

                raise ValidationError("avatar_url must be an http(s) URL")
            user.avatar_url = avatar or None
        self.db.add(user)
        await self.db.flush()
        return user


class SettingsService:
    DEFAULTS = {"theme": None, "default_timeframe": None}

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create(self, user: User) -> UserSetting:
        from sqlalchemy import select

        row = (
            await self.db.execute(select(UserSetting).where(UserSetting.user_id == user.id))
        ).scalar_one_or_none()
        if row is None:
            row = UserSetting(user_id=user.id)
            self.db.add(row)
            await self.db.flush()
        return row

    async def update(self, user: User, payload: UserSettingsUpdateRequest) -> UserSetting:
        row = await self.get_or_create(user)
        if payload.theme is not None:
            row.theme = payload.theme
        if payload.default_timeframe is not None:
            row.default_timeframe = payload.default_timeframe
        if payload.preferences is not None:
            merged = dict(row.preferences or {})
            merged.update(payload.preferences)
            row.preferences = merged
        self.db.add(row)
        await self.db.flush()
        return row
