"""Admin endpoints â€” every route requires an ADMIN-role user (spec Â§20)."""

from datetime import datetime
from typing import Annotated

import jwt as pyjwt
from fastapi import APIRouter, Query, status as http_status

from app.api.deps import DbSession
from app.api.dependencies.auth import AdminUser
from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.models import LogLevel, MarketSession, Signal
from app.repositories.signal_repository import SignalRepository
from app.schemas.admin import (
    AdminHealth,
    AdminInstrumentUpdateRequest,
    AdminMarketDataCoverage,
    AdminStats,
    AdminUserRow,
    AdminUserUpdateRequest,
    MarketSessionCreateRequest,
    PaginatedAdminUsers,
    PaginatedCoverage,
    PaginatedSystemEvents,
    SystemEventRow,
)
from app.schemas.common import ApiResponse, ok
from app.services.admin_service import AdminService
from app.services.instrument_service import parse_timeframe, parse_uuid
from app.services.system_events import list_events
from sqlalchemy import select

router = APIRouter(prefix="/admin", tags=["admin"])


def _user_row(u) -> AdminUserRow:  # noqa: ANN001
    return AdminUserRow(
        id=u.id,
        email=u.email,
        username=u.username,
        display_name=u.display_name,
        role=u.role.value if hasattr(u.role, "value") else str(u.role),
        auth_provider=(u.auth_provider.value if hasattr(u.auth_provider, "value")
                       else str(u.auth_provider)),
        is_active=u.is_active,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
    )


# ------------------------------------------------------------------- stats

@router.get("/stats", response_model=ApiResponse[AdminStats],
            summary="Platform-wide dashboard statistics")
async def stats(admin: AdminUser, db: DbSession) -> ApiResponse[AdminStats]:
    from app.websocket.manager import manager

    data = await AdminService(db).stats(
        ws_connections=manager.count,
        provider=settings.MARKET_DATA_PROVIDER,
    )
    return ok(AdminStats.model_validate(data))


@router.get("/health", response_model=ApiResponse[AdminHealth],
            summary="Operational health incl. DB latency + WS load")
async def admin_health(admin: AdminUser, db: DbSession) -> ApiResponse[AdminHealth]:
    import time

    start = time.perf_counter()
    latency = None
    try:
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))
        latency = round((time.perf_counter() - start) * 1000, 1)
    except Exception:  # noqa: BLE001
        pass

    from app.websocket.manager import manager

    return ok(AdminHealth(
        status="ok" if latency is not None else "degraded",
        database_latency_ms=latency,
        ws_connections=manager.count,
        provider=settings.MARKET_DATA_PROVIDER,
        live_loop_enabled=bool(settings.LIVE_DEMO_ENABLED),
        version="0.1.0",
    ))


# -------------------------------------------------------------------- users

@router.get("/users", response_model=ApiResponse[PaginatedAdminUsers],
            summary="Search users (email/username)")
async def list_users(
    admin: AdminUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=64)] = None,
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaginatedAdminUsers]:
    rows, total = await AdminService(db).list_users(q=q, limit=limit, offset=offset)
    return ok(PaginatedAdminUsers(
        items=[_user_row(u) for u in rows], total=total, limit=limit, offset=offset,
    ))


@router.patch("/users/{user_id}", response_model=ApiResponse[AdminUserRow],
              summary="Enable/disable or promote/demote a user")
async def update_user(
    user_id: str,
    payload: AdminUserUpdateRequest,
    admin: AdminUser,
    db: DbSession,
) -> ApiResponse[AdminUserRow]:
    updated = await AdminService(db).update_user(
        parse_uuid(user_id, "user_id"),
        is_active=payload.is_active,
        role=payload.role,
    )
    return ok(_user_row(updated))


# -------------------------------------------------------------- instruments

@router.get("/instruments", response_model=ApiResponse[PaginatedCoverage],
            summary="Instruments with M15 candle coverage + quote freshness")
async def instruments_coverage(
    admin: AdminUser,
    db: DbSession,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaginatedCoverage]:
    insts, total, counts, quotes = (
        await AdminService(db).instruments_with_coverage(limit=limit, offset=offset)
    )
    items = []
    for i in insts:
        cnt, last_ts = counts.get(i.id, (0, None))
        items.append(AdminMarketDataCoverage(
            id=i.id,
            symbol=i.symbol,
            exchange=i.exchange,
            is_active=i.is_active,
            m15_candles=cnt,
            last_m15_ts=last_ts,
            quote_updated_at=quotes.get(i.id),
        ))
    return ok(PaginatedCoverage(items=items, total=total, limit=limit, offset=offset))


@router.patch("/instruments/{instrument_id}", response_model=ApiResponse[dict],
              summary="Update instrument metadata / deactivate")
async def update_instrument(
    instrument_id: str,
    payload: AdminInstrumentUpdateRequest,
    admin: AdminUser,
    db: DbSession,
):
    from app.models import Instrument
    from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401

    inst = (
        await db.execute(select(Instrument).where(Instrument.id == parse_uuid(instrument_id)))
    ).scalar_one_or_none()
    if inst is None:
        raise NotFoundError("Instrument not found")

    if payload.name is not None and payload.name.strip():
        inst.name = payload.name.strip()
    if payload.instrument_type is not None:
        inst.instrument_type = payload.instrument_type
    if payload.sector_id is not None:
        inst.sector_id = payload.sector_id
    if payload.is_active is not None:
        inst.is_active = payload.is_active
    await db.flush()
    return ok({"id": str(inst.id), "symbol": inst.symbol, "is_active": inst.is_active})


# ------------------------------------------------------------------ signals

@router.get("/signals", response_model=ApiResponse[dict],
            summary="All signals incl. DETECTING (admin view)")
async def admin_signals(
    admin: AdminUser,
    db: DbSession,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    direction: Annotated[str | None, Query()] = None,
    sort: str = Query(default="detected_at", pattern="^(detected_at|confidence)$"),
    limit: int = Query(default=25, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    from app.models.enums import SignalDirection, SignalStatus

    rows, total = await SignalRepository(db).list(
        direction=SignalDirection(direction) if direction else None,
        status=SignalStatus(status_filter) if status_filter else None,
        sort=sort, limit=limit, offset=offset,
    )
    items = []
    for s, i in rows:
        items.append({
            "id": str(s.id), "symbol": i.symbol,
            "direction": s.direction.value if hasattr(s.direction, "value") else str(s.direction),
            "strength": s.strength.value if hasattr(s.strength, "value") else str(s.strength),
            "status": s.status.value if hasattr(s.status, "value") else str(s.status),
            "timeframe": s.timeframe.value if hasattr(s.timeframe, "value") else str(s.timeframe),
            "confidence": float(s.confidence),
            "detected_at": s.detected_at.isoformat(),
        })
    return ok({"items": items, "total": total, "limit": limit, "offset": offset})


# ---------------------------------------------------------- market sessions

@router.get("/market-sessions", response_model=ApiResponse[list],
            summary="Trading calendar entries")
async def market_sessions(admin: AdminUser, db: DbSession,
                          limit: int = Query(default=60, ge=1, le=366)) -> ApiResponse[list]:
    rows = (
        await db.execute(
            select(MarketSession)
            .order_by(MarketSession.session_date.desc())
            .limit(limit)
        )
    ).scalars().all()

    def row_dict(ms):  # noqa: ANN001
        return {
            "id": str(ms.id),
            "session_date": ms.session_date.isoformat(),
            "market": ms.market.value if hasattr(ms.market, "value") else str(ms.market),
            "status": ms.status.value if hasattr(ms.status, "value") else str(ms.status),
            "note": ms.note,
        }

    return ok([row_dict(m) for m in rows])


@router.post("/market-sessions", response_model=ApiResponse[dict], status_code=201,
             summary="Create/update a session entry (holiday, half-day, â€¦)")
async def upsert_market_session(
    payload: MarketSessionCreateRequest, admin: AdminUser, db: DbSession
):
    try:
        session_date = datetime.strptime(payload.session_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValidationError("session_date must be YYYY-MM-DD") from exc

    existing = (
        await db.execute(
            select(MarketSession).where(
                MarketSession.market == payload.market,
                MarketSession.session_date == session_date,
            )
        )
    ).scalar_one_or_none()

    if existing is None:
        ms = MarketSession(session_date=session_date, market=payload.market,
                           status=payload.status, note=payload.note)
        db.add(ms)
        created = True
    else:
        existing.status = payload.status
        existing.note = payload.note
        created = False
    await db.flush()
    return ok({"created": created, "date": payload.session_date,
               "market": payload.market.value, "status": payload.status.value})


# ---------------------------------------------------------- system events

@router.get("/events", response_model=ApiResponse[PaginatedSystemEvents],
            summary="Operational event log")
async def admin_events(
    admin: AdminUser,
    db: DbSession,
    level: Annotated[LogLevel | None, Query()] = None,
    source: Annotated[str | None, Query(max_length=120)] = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[PaginatedSystemEvents]:
    rows, total = await list_events(db, level=level, source=source,
                                    limit=limit, offset=offset)
    return ok(PaginatedSystemEvents(
        items=[SystemEventRow(
            id=e.id, level=e.level, source=e.source, message=e.message,
            created_at=e.created_at,
        ) for e in rows],
        total=total, limit=limit, offset=offset,
    ))


_ = pyjwt  # reserved

