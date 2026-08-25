"""Admin service: platform statistics, user management, coverage reports."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationError
from app.models import (
    Candle,
    Instrument,
    MarketData,
    Signal,
    SignalStatus,
    Timeframe,
    User,
)
from app.models.enums import UserRole


def _utc_day_start() -> datetime:
    ist = timezone(timedelta(hours=5, minutes=30))  # NSE day boundary (no DST)
    now = datetime.now(timezone.utc).astimezone(ist)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


class AdminService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------ stats

    async def stats(self, *, ws_connections: int, provider: str) -> dict:
        day_start = _utc_day_start()

        users = (
            await self.db.execute(
                select(
                    func.count().label("total"),
                    func.sum(case_active()).label("active"),
                )
            )
        ).one()

        signals = (
            await self.db.execute(
                select(
                    func.count().label("total"),
                    func.sum(_case(Signal.detected_at >= day_start)).label("today"),
                    func.sum(_case(Signal.status == "CONFIRMED")).label("confirmed"),
                    func.sum(_case(Signal.status == "INVALIDATED")).label("invalidated"),
                )
            )
        ).one()

        active_instruments = (
            await self.db.execute(
                select(func.count()).select_from(Instrument).where(Instrument.is_active.is_(True))
            )
        ).scalar_one()

        db_ok = True
        try:
            await self.db.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            db_ok = False

        from app.core.config import settings

        return {
            "total_users": int(users.total or 0),
            "active_users": int(users.active or 0),
            "signals_today": int(signals.today or 0),
            "total_signals": int(signals.total or 0),
            "confirmed_signals": int(signals.confirmed or 0),
            "invalidated_signals": int(signals.invalidated or 0),
            "active_instruments": int(active_instruments),
            "database": "up" if db_ok else "down",
            "ws_connections": ws_connections,
            "provider": provider,
            "environment": settings.ENVIRONMENT,
        }

    # ------------------------------------------------------------------ users

    async def list_users(self, *, q: str | None, limit: int, offset: int):
        conds = []
        if q:
            like = f"%{q.lower()}%"
            from sqlalchemy import or_

            conds.append(or_(func.lower(User.email).like(like),
                             func.lower(func.coalesce(User.username, "")).like(like)))

        rows = (
            await self.db.execute(
                select(User).where(*conds).order_by(User.created_at.desc())
                .limit(limit).offset(offset)
            )
        ).scalars().all()
        total = (
            await self.db.execute(select(func.count()).select_from(User).where(*conds))
        ).scalar_one()
        return list(rows), int(total)

    async def update_user(self, user_id: uuid.UUID, *, is_active: bool | None,
                          role: str | None) -> User:
        user = (
            await self.db.execute(select(User).where(User.id == user_id))
        ).scalar_one_or_none()
        if user is None:
            raise NotFoundError("User not found")
        if role is not None:
            if role not in ("USER", "ADMIN"):
                raise ValidationError("role must be USER or ADMIN")
            user.role = UserRole(role)
        if is_active is not None:
            user.is_active = is_active
        await self.db.flush()
        return user

    async def coverage_payload(self, *, limit: int, offset: int) -> dict:
        total = (
            await self.db.execute(select(func.count()).select_from(Instrument))
        ).scalar_one()
        insts = (
            await self.db.execute(
                select(Instrument).order_by(Instrument.symbol).limit(limit).offset(offset)
            )
        ).scalars().all()

        cov_rows = (
            await self.db.execute(
                select(Candle.instrument_id, func.count(), func.max(Candle.ts))
                .where(Candle.timeframe == Timeframe.M15)
                .group_by(Candle.instrument_id)
            )
        ).all()
        counts = {r[0]: (int(r[1]), r[2]) for r in cov_rows}
        quotes = {
            r[0]: r[1]
            for r in (
                await self.db.execute(
                    select(MarketData.instrument_id, MarketData.updated_at)
                )
            ).all()
        }

        def val(v):  # enum → str for JSON caching
            return v.value if hasattr(v, "value") else str(v)

        items = []
        for i in insts:
            cnt, last_ts = counts.get(i.id, (0, None))
            items.append({
                "id": str(i.id),
                "symbol": i.symbol,
                "exchange": i.exchange,
                "is_active": i.is_active,
                "m15_candles": cnt,
                "last_m15_ts": last_ts.isoformat() if last_ts else None,
                "quote_updated_at": quotes.get(i.id).isoformat()
                    if quotes.get(i.id) else None,
                "_type": val(i.instrument_type),
            })

        return {
            "items": items,
            "total": int(total),
            "limit": limit,
            "offset": offset,
        }


def _case(condition):  # noqa: ANN001 â€” tiny helper for conditional sums
    from sqlalchemy import case

    return case((condition, 1), else_=0)


def case_active():
    return _case(User.is_active.is_(True))


__all__ = ["AdminService"]

