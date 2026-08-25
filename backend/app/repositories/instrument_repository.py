"""Instrument queries: search, filters, sorting, pagination, detail."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Candle, Instrument, MarketData, Signal, SignalStatus, Timeframe
from app.models.enums import InstrumentType


class InstrumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(
        self,
        *,
        q: str | None = None,
        instrument_type: InstrumentType | None = None,
        sector_id: uuid.UUID | None = None,
        exchange: str | None = None,
        sort: str = "symbol",
        limit: int,
        offset: int,
    ) -> tuple[list[Instrument], int]:
        base = select(Instrument).outerjoin(MarketData, MarketData.instrument_id == Instrument.id)
        conditions = [Instrument.is_active.is_(True)]

        if q:
            like = f"%{q.strip().lower()}%"
            conditions.append(
                or_(
                    func.lower(Instrument.symbol).like(like),
                    func.lower(Instrument.name).like(like),
                )
            )
        if instrument_type is not None:
            conditions.append(Instrument.instrument_type == instrument_type)
        if sector_id is not None:
            conditions.append(Instrument.sector_id == sector_id)
        if exchange:
            conditions.append(func.upper(Instrument.exchange) == exchange.upper())

        stmt = (
            base.where(*conditions)
            .options(selectinload(Instrument.sector))
            .limit(limit)
            .offset(offset)
        )
        stmt = _apply_sort(stmt, sort)

        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(Instrument)
                .where(*conditions)
            )
        ).scalar_one()
        return list(rows), int(total)

    async def get(self, instrument_id: uuid.UUID) -> Instrument | None:
        return (
            await self.db.execute(
                select(Instrument)
                .options(selectinload(Instrument.sector), selectinload(Instrument.market_data))
                .where(Instrument.id == instrument_id)
            )
        ).scalar_one_or_none()

    async def signal_stats(self, instrument_id: uuid.UUID) -> dict[str, int]:
        bullish = func.sum(case((Signal.direction == "BULLISH", 1), else_=0))
        bearish = func.sum(case((Signal.direction == "BEARISH", 1), else_=0))
        confirmed = func.sum(case((Signal.status.in_([SignalStatus.CONFIRMED, SignalStatus.CLOSED]), 1), else_=0))
        invalidated = func.sum(case((Signal.status == SignalStatus.INVALIDATED, 1), else_=0))
        row = (
            await self.db.execute(
                select(
                    func.count().label("total"),
                    bullish.label("bullish"),
                    bearish.label("bearish"),
                    confirmed.label("confirmed"),
                    invalidated.label("invalidated"),
                ).where(Signal.instrument_id == instrument_id)
            )
        ).one()
        return {
            "total_signals": int(row.total or 0),
            "bullish": int(row.bullish or 0),
            "bearish": int(row.bearish or 0),
            "confirmed": int(row.confirmed or 0),
            "invalidated": int(row.invalidated or 0),
        }

    async def candles(
        self,
        *,
        instrument_id: uuid.UUID,
        timeframe: Timeframe,
        limit: int,
        before: datetime | None,
    ) -> list[Candle]:
        stmt = (
            select(Candle)
            .where(Candle.instrument_id == instrument_id, Candle.timeframe == timeframe)
            .order_by(Candle.ts.desc())
            .limit(limit)
        )
        if before is not None:
            stmt = stmt.where(Candle.ts < before)
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows)

    async def index_quotes(self) -> list[tuple[Instrument, MarketData]]:
        rows = (
            await self.db.execute(
                select(Instrument, MarketData)
                .join(MarketData, MarketData.instrument_id == Instrument.id)
                .where(
                    Instrument.instrument_type == InstrumentType.INDEX,
                    Instrument.is_active.is_(True),
                )
                .order_by(Instrument.symbol.asc())
            )
        ).all()
        return [(r[0], r[1]) for r in rows]


def _apply_sort(stmt, sort: str):  # noqa: ANN001
    mapping = {
        "symbol": Instrument.symbol.asc(),
        "name": Instrument.name.asc(),
        # NULLS LAST keeps instruments without live data below populated ones.
        "change_pct": MarketData.change_pct.desc().nulls_last(),
        "volume": MarketData.volume.desc().nulls_last(),
    }
    order = mapping.get(sort, mapping["symbol"])
    return stmt.order_by(order)


__all__ = ["InstrumentRepository"]
