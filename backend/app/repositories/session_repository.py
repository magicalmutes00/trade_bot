"""Refresh-token session persistence."""

import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserSession


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, *, user_id: uuid.UUID, refresh_token_hash: str,
                     expires_at: datetime, user_agent: str | None,
                     ip_address: str | None) -> UserSession:
        session_row = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            user_agent=user_agent[:512] if user_agent else None,
            ip_address=ip_address[:64] if ip_address else None,
        )
        self.db.add(session_row)
        await self.db.flush()
        return session_row

    async def get_active_by_token_hash(self, token_hash: str) -> UserSession | None:
        row = (
            await self.db.execute(
                select(UserSession).where(
                    UserSession.refresh_token_hash == token_hash,
                    UserSession.revoked_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        return row

    async def revoke(self, session_row: UserSession, at: datetime) -> None:
        if session_row.revoked_at is None:
            session_row.revoked_at = at
            await self.db.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID, at: datetime) -> int:
        result = await self.db.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=at)
        )
        return result.rowcount or 0
