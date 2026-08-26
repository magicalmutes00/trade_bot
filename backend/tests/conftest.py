"""Shared pytest fixtures.

Default backend: isolated in-memory SQLite (aiosqlite) — zero services needed.
Set TEST_DATABASE_URL to run the identical suite against PostgreSQL:

    TEST_DATABASE_URL=postgresql://user:pass@host:5432/bof_scanner_test?ssl=require

All models use cross-dialect column types (sa.Uuid, sa.JSON, non-native
enums) so both backends exercise identical code paths.

Loop-safety notes:
- PostgreSQL uses NullPool: no socket ever survives across pytest-asyncio
  event loops (each operation dials fresh on the currently-running loop).
- SQLite keeps StaticPool (single shared in-memory connection).
- Remote DDL runs exactly once per session (autouse _schema fixture);
  per-test isolation comes from row cleanup instead of re-DDL.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.rate_limit import reset_rate_limits
from app.db.session import Base, get_db
from app.main import app as fastapi_app


def _resolve_url() -> tuple[str, bool]:
    """Returns (url, is_postgres)."""
    import os

    url = os.environ.get("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url, url.startswith("postgresql")


def _make_engine(url: str, is_pg: bool) -> AsyncEngine:
    if is_pg:
        return create_async_engine(url, poolclass=NullPool)
    return create_async_engine(
        url,
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


@pytest.fixture(autouse=True)
def _force_demo_provider(monkeypatch):
    """Keep the suite hermetic: default every test to the demo provider so no
    test dials real market-data APIs. Tests that exercise provider selection
    override this with their own monkeypatch.setenv (applied later → wins)."""
    from app.core.config import get_settings

    monkeypatch.setenv("MARKET_DATA_PROVIDER", "demo")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def _pg_schema() -> None:
    """Create the full schema once on the remote database."""
    url, is_pg = _resolve_url()
    if not is_pg:
        return None

    async def _build() -> None:
        eng = _make_engine(url, True)
        try:
            async with eng.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
        finally:
            await eng.dispose()

    asyncio.run(_build())
    return None


@pytest_asyncio.fixture
async def engine(_pg_schema: None) -> AsyncEngine:
    url, is_pg = _resolve_url()
    eng = _make_engine(url, is_pg)

    if not is_pg:
        # Local SQLite: cheap to (re)create per test.
        from sqlalchemy import event

        @event.listens_for(eng.sync_engine, "connect")
        def _enable_sqlite_fk(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Per-test session on a clean table set."""
    is_pg = engine.url.get_backend_name() == "postgresql"
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
        # Clean slate per test.
        await session.rollback()
        if is_pg:
            # Single round trip; CASCADE ignores FK ordering.
            from sqlalchemy import text

            names = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
            await session.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
            await session.commit()
        else:
            for table in reversed(Base.metadata.sorted_tables):
                await session.execute(table.delete())
            await session.commit()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    async def _override_get_db() -> AsyncIterator[AsyncSession]:
        yield db

    fastapi_app.dependency_overrides[get_db] = _override_get_db
    reset_rate_limits()
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    fastapi_app.dependency_overrides.clear()


# ---------------------------------------------------------------- helpers

REGISTER_PAYLOAD = {
    "email": "trader@example.com",
    "password": "S3curePass!x",
    "username": "trader",
    "display_name": "Test Trader",
}


async def register_user(client: httpx.AsyncClient, **overrides: Any) -> dict[str, Any]:
    payload = {**REGISTER_PAYLOAD, **overrides}
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()["data"]


async def login_user(client: httpx.AsyncClient, email: str | None = None,
                     password: str | None = None) -> dict[str, Any]:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email or REGISTER_PAYLOAD["email"], "password": password or REGISTER_PAYLOAD["password"]},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def auth_headers(auth_data: dict[str, Any]) -> dict[str, str]:
    """Accepts either a full AuthResponse payload or a bare token dict."""
    tokens = auth_data.get("tokens", auth_data)
    return {"Authorization": f"Bearer {tokens['access_token']}"}
