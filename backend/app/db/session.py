"""Async SQLAlchemy engine/session management."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base with deterministic constraint naming (Alembic-friendly)."""

    naming_convention = {
        "ix": "ix_%(column_0_label)s",
        "uq": "uq_%(table_name)s_%(column_0_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


def _normalise_driver(url: str) -> str:
    """Force the asyncpg driver for Postgres URLs regardless of pasted form.

    Render/Heroku-style URLs arrive as ``postgresql://…``; SQLAlchemy would
    then default to the (uninstalled) psycopg2 dialect. Also accepts
    ``postgres://``. Other schemes pass through untouched.
    """
    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


def _make_engine(url: str | None = None) -> AsyncEngine:
    final_url = _normalise_driver(url or settings.DATABASE_URL)
    kwargs: dict = {"pool_pre_ping": True, "echo": False}
    if not final_url.startswith("sqlite"):
        kwargs.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
        )
    else:
        from sqlalchemy.pool import StaticPool

        kwargs.update(poolclass=StaticPool, connect_args={"check_same_thread": False})
    return create_async_engine(final_url, **kwargs)


engine: AsyncEngine = _make_engine()

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — one session per request."""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
