"""Signal queries + persistence-facing reads."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models import Instrument, Signal, SignalEvent, Timeframe
from app.models.enums import SignalDirection, SignalStatus, SignalStrength


class SignalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        *,
        instrument_id: uuid.UUID | None = None,
        direction: SignalDirection | None = None,
        status: SignalStatus | None = None,
        strength: SignalStrength | None = None,
        min_confidence: float | None = None,
        timeframe: Timeframe | None = None,
        detected_from=None,
        detected_to=None,
        sort: str = "detected_at",
        limit: int,
        offset: int,
    ) -> tuple[list[tuple[Signal, Instrument]], int]:
        base = select(Signal, Instrument).join(Instrument, Instrument.id == Signal.instrument_id)
        conds = []
        if instrument_id is not None:
            conds.append(Signal.instrument_id == instrument_id)
        if direction is not None:
            conds.append(Signal.direction == direction)
        if status is not None:
            conds.append(Signal.status == status)
        if strength is not None:
            conds.append(Signal.strength == strength)
        if min_confidence is not None:
            conds.append(Signal.confidence >= min_confidence)
        if timeframe is not None:
            conds.append(Signal.timeframe == timeframe)
        if detected_from is not None:
            conds.append(Signal.detected_at >= detected_from)
        if detected_to is not None:
            conds.append(Signal.detected_at <= detected_to)

        stmt = base.where(*conds).limit(limit).offset(offset)
        stmt = stmt.order_by(
            Signal.confidence.desc() if sort == "confidence" else Signal.detected_at.desc()
        )
        rows = (await self.db.execute(stmt)).all()

        total = (
            await self.db.execute(
                select(func.count())
                .select_from(Signal)
                .where(*conds)
            )
        ).scalar_one()
        return [(r[0], r[1]) for r in rows], int(total)

    async def get_with_events(self, signal_id: uuid.UUID):
        row = (
            await self.db.execute(
                select(Signal, Instrument)
                .join(Instrument, Instrument.id == Signal.instrument_id)
                .where(Signal.id == signal_id)
            )
        ).first()
        if row is None:
            raise NotFoundError("Signal not found")
        events = (
            await self.db.execute(
                select(SignalEvent)
                .where(SignalEvent.signal_id == signal_id)
                .order_by(SignalEvent.created_at.asc())
            )
        ).scalars().all()
        return row[0], row[1], list(events)


__all__ = ["SignalRepository"]
