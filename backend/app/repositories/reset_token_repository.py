"""Password-reset token persistence."""

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PasswordResetToken


class ResetTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, *, user_id: uuid.UUID, token_hash: str,
                     expires_at: datetime) -> PasswordResetToken:
        row = PasswordResetToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.db.add(row)
        await self.db.flush()
        return row

    async def get_valid_by_token_hash(self, token_hash: str, now: datetime) -> PasswordResetToken | None:
        row = (
            await self.db.execute(
                select(PasswordResetToken).where(
                    PasswordResetToken.token_hash == token_hash,
                    PasswordResetToken.used_at.is_(None),
                    PasswordResetToken.expires_at > now,
                )
            )
        ).scalar_one_or_none()
        return row

    async def mark_used(self, row: PasswordResetToken, now: datetime) -> None:
        row.used_at = now
        await self.db.flush()
