"""User persistence."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return (
            await self.db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()

    async def get_by_firebase_uid(self, firebase_uid: str) -> User | None:
        return (
            await self.db.execute(
                select(User).where(User.firebase_uid == firebase_uid)
            )
        ).scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        return (
            await self.db.execute(select(User).where(func.lower(User.email) == normalized))
        ).scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        return (
            await self.db.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        hashed_password: str | None = None,
        username: str | None = None,
        display_name: str | None = None,
    ) -> User:
        user = User(
            email=email.strip().lower(),
            username=username,
            display_name=display_name or username or email.split("@")[0],
            hashed_password=hashed_password,
        )
        self.db.add(user)
        await self.db.flush()
        return user
