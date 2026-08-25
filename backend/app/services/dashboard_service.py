"""Dashboard aggregation: market status, index quotes, BOF summary."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Instrument, MarketData, Signal
from app.models.enums import (
    MarketName,
    SessionStatus,
    SignalDirection,
    SignalStatus,
    SignalStrength,
)
from app.repositories.instrument_repository import InstrumentRepository
from app.schemas.dashboard import (
    BofSummary,
    DashboardResponse,
    MarketStatus,
    QuoteCard,
    SignalCard,
)

# NSE regular session (IST, UTC+5:30 — India has no DST).
_IST_OFFSET = timedelta(hours=5, minutes=30)
_PRE_OPEN_START = 9 * 60 + 0        # 09:00 IST
_OPEN_START = 9 * 60 + 15           # 09:15 IST
_OPEN_END = 15 * 60 + 30            # 15:30 IST


def _ist_now() -> tuple[datetime, int]:
    now = datetime.now(timezone.utc).astimezone(timezone(_IST_OFFSET))
    return now, now.hour * 60 + now.minute


def market_status() -> MarketStatus:
    """Derived from the real clock; holiday overrides come from market_sessions."""
    now, minutes = _ist_now()
    weekend = now.weekday() >= 5
    if weekend or minutes < _PRE_OPEN_START or minutes >= _OPEN_END:
        status = SessionStatus.CLOSED
    elif minutes < _OPEN_START:
        status = SessionStatus.PRE_OPEN
    else:
        status = SessionStatus.OPEN
    return MarketStatus(
        market=MarketName.NSE,
        status=status,
        as_of=datetime.now(timezone.utc),
        note=None,
    )


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(self) -> DashboardResponse:
        repo = InstrumentRepository(self.db)
        return DashboardResponse(
            market_status=market_status(),
            indices=await self._index_cards(repo),
            bof_summary=await self._bof_summary(),
            latest_signals=await self._latest_signals(),
            strongest_signals=await self._strongest_signals(),
        )

    async def _index_cards(self, repo: InstrumentRepository) -> list[QuoteCard]:
        cards: list[QuoteCard] = []
        for instrument, md in await repo.index_quotes():
            change_pct = float(md.change_pct) if md.change_pct is not None else None
            direction = (
                "UP" if (change_pct or 0) > 0
                else "DOWN" if (change_pct or 0) < 0
                else "FLAT"
            )
            cards.append(
                QuoteCard(
                    instrument_id=str(instrument.id),
                    symbol=instrument.symbol,
                    name=instrument.name,
                    last_price=float(md.last_price),
                    change=float(md.change) if md.change is not None else None,
                    change_pct=change_pct,
                    direction=direction if md.change is not None else None,
                    updated_at=md.updated_at,
                )
            )
        return cards

    async def _bof_summary(self) -> BofSummary:
        start_of_day_utc = _utc_day_start()
        bullish = func.sum(case((Signal.direction == SignalDirection.BULLISH, 1), else_=0))
        bearish = func.sum(case((Signal.direction == SignalDirection.BEARISH, 1), else_=0))
        strong = func.sum(
            case((Signal.strength.in_([SignalStrength.STRONG, SignalStrength.VERY_STRONG]), 1), else_=0)
        )
        active = func.sum(
            case((Signal.status.in_([SignalStatus.CONFIRMED, SignalStatus.DETECTING]), 1), else_=0)
        )
        new_today = func.sum(case((Signal.detected_at >= start_of_day_utc, 1), else_=0))
        row = (
            await self.db.execute(
                select(
                    func.count().label("detected_today"),
                    bullish.label("bullish"),
                    bearish.label("bearish"),
                    strong.label("strong"),
                    active.label("active"),
                    new_today.label("new_today"),
                ).where(Signal.detected_at >= start_of_day_utc - timedelta(days=30))
            )
        ).one()
        return BofSummary(
            active_total=int(row.active or 0),
            bullish=int(row.bullish or 0),
            bearish=int(row.bearish or 0),
            strong=int(row.strong or 0),
            new_today=int(row.new_today or 0),
            detected_today=int(row.detected_today or 0),
        )

    async def _latest_signals(self, limit: int = 20) -> list[SignalCard]:
        return await self._signal_cards(order=Signal.detected_at.desc(), limit=limit)

    async def _strongest_signals(self, limit: int = 10) -> list[SignalCard]:
        stmt = (
            select(Signal, Instrument)
            .join(Instrument, Instrument.id == Signal.instrument_id)
            .where(Signal.strength.in_([SignalStrength.STRONG, SignalStrength.VERY_STRONG]))
        )
        return await self._signal_cards_from(stmt, order=Signal.confidence.desc(), limit=limit)

    async def _signal_cards(self, *, order, limit: int) -> list[SignalCard]:  # noqa: ANN001
        stmt = select(Signal, Instrument).join(Instrument, Instrument.id == Signal.instrument_id)
        return await self._signal_cards_from(stmt, order=order, limit=limit)

    async def _signal_cards_from(self, stmt, *, order, limit: int) -> list[SignalCard]:  # noqa: ANN001
        rows = (
            await self.db.execute(stmt.order_by(order).limit(limit))
        ).all()
        return [
            SignalCard(
                id=str(s.id),
                instrument_id=str(i.id),
                symbol=i.symbol,
                instrument_name=i.name,
                direction=s.direction,
                strength=s.strength,
                bof_level=float(s.bof_level),
                price=float(s.entry_price) if s.entry_price is not None else None,
                timeframe=s.timeframe.value,
                detected_at=s.detected_at,
            )
            for s, i in rows
        ]


def _utc_day_start(now: datetime | None = None) -> datetime:
    """Start of the current IST trading day expressed in UTC."""
    ist_now = now or datetime.now(timezone.utc).astimezone(timezone(_IST_OFFSET))
    day_start_ist = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start_ist.astimezone(timezone.utc)
