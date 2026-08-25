"""Signal statistics for one instrument (Phase 5 signal history)."""

import uuid

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Signal
from app.models.enums import SignalStatus, SignalStrength


class SignalStatsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def detailed(self, instrument_id: uuid.UUID) -> dict:
        base = select(func.count().label("total")).where(Signal.instrument_id == instrument_id)

        agg = select(
            func.count().label("total"),
            func.sum(case((Signal.direction == "BULLISH", 1), else_=0)).label("bullish"),
            func.sum(case((Signal.direction == "BEARISH", 1), else_=0)).label("bearish"),
            func.sum(case((Signal.status == SignalStatus.CONFIRMED, 1), else_=0)).label("confirmed"),
            func.sum(case((Signal.status == SignalStatus.INVALIDATED, 1), else_=0)).label("invalidated"),
            func.sum(case((Signal.status == SignalStatus.DETECTING, 1), else_=0)).label("detecting"),
            func.sum(case((Signal.status == SignalStatus.CLOSED, 1), else_=0)).label("closed"),
            func.avg(Signal.confidence).label("avg_confidence"),
        ).where(Signal.instrument_id == instrument_id)

        row = (await self.db.execute(agg)).one()
        total = int(row.total or 0)
        confirmed = int(row.confirmed or 0)

        by_strength_rows = (
            await self.db.execute(
                select(Signal.strength, func.count())
                .where(Signal.instrument_id == instrument_id)
                .group_by(Signal.strength)
            )
        ).all()
        by_tf_rows = (
            await self.db.execute(
                select(Signal.timeframe, func.count())
                .where(Signal.instrument_id == instrument_id)
                .group_by(Signal.timeframe)
            )
        ).all()

        def val(v):  # enum or str → str
            return v.value if hasattr(v, "value") else str(v)

        return {
            "total_signals": total,
            "bullish": int(row.bullish or 0),
            "bearish": int(row.bearish or 0),
            "confirmed": confirmed,
            "invalidated": int(row.invalidated or 0),
            "detecting": int(row.detecting or 0),
            "closed": int(row.closed or 0),
            "avg_confidence": round(float(row.avg_confidence), 4) if row.avg_confidence is not None else None,
            "confirmation_rate": round(confirmed / total, 4) if total else None,
            "by_strength": [
                {"strength": val(v), "count": int(c)} for v, c in by_strength_rows
            ],
            "by_timeframe": [
                {"timeframe": val(v), "count": int(c)} for v, c in by_tf_rows
            ],
        }


__all__ = ["SignalStatsService"]
