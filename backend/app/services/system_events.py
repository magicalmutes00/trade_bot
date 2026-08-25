"""System-event recorder + query helpers (admin Logs page)."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import LogLevel, SystemEvent

logger = get_logger(__name__)


async def record_event(
    db: AsyncSession,
    *,
    level: LogLevel,
    source: str,
    message: str,
    details: dict | None = None,
) -> None:
    """Best-effort operational event — never raises into caller paths."""
    try:
        db.add(SystemEvent(level=level, source=source, message=message, details=details))
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("failed to record system event: %s", message)


async def record_event_standalone(db_factory, *, level: LogLevel, source: str,
                                  message: str, details: dict | None = None) -> None:
    """Same as record_event but opens its own session (worker contexts)."""
    try:
        async with db_factory() as db:
            await record_event(db, level=level, source=source,
                               message=message, details=details)
    except Exception:  # noqa: BLE001
        logger.exception("standalone system-event write failed")


async def list_events(
    db: AsyncSession,
    *,
    level: LogLevel | None = None,
    source: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[SystemEvent], int]:
    conds = []
    if level is not None:
        conds.append(SystemEvent.level == level)
    if source is not None:
        conds.append(SystemEvent.source == source)

    stmt = select(SystemEvent).where(*conds).order_by(
        SystemEvent.created_at.desc()).limit(limit).offset(offset)
    rows = (await db.execute(stmt)).scalars().all()
    total = (
        await db.execute(select(func.count()).select_from(SystemEvent).where(*conds))
    ).scalar_one()
    return list(rows), int(total)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


_ = uuid  # reserved


__all__ = ["record_event", "record_event_standalone", "list_events"]
