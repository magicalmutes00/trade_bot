"""Watchlist CRUD + item management (user-scoped, ownership enforced)."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.errors import ConflictError, NotFoundError
from app.models import Instrument, Watchlist, WatchlistItem
from app.services import market_enrichment as enr


class WatchlistService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---------------------------------------------------------------- helpers

    async def _owned(self, user_id: uuid.UUID, watchlist_id: uuid.UUID) -> Watchlist:
        wl = (
            await self.db.execute(select(Watchlist).where(Watchlist.id == watchlist_id))
        ).scalar_one_or_none()
        if wl is None or wl.user_id != user_id:
            raise NotFoundError("Watchlist not found")
        return wl

    async def _items_with_instruments(self, watchlist_id: uuid.UUID):
        return (
            await self.db.execute(
                select(WatchlistItem, Instrument)
                .join(Instrument, Instrument.id == WatchlistItem.instrument_id)
                .options(selectinload(Instrument.sector))
                .where(WatchlistItem.watchlist_id == watchlist_id)
                .order_by(WatchlistItem.position, WatchlistItem.added_at)
            )
        ).all()

    async def _to_response(self, wl: Watchlist) -> dict:
        pairs = await self._items_with_instruments(wl.id)
        ids = [item.instrument_id for item, _ in pairs]
        quotes = await enr.quotes_by_instrument(self.db, ids)
        signals = await enr.latest_signals_by_instrument(self.db, ids)

        items = []
        for item, inst in pairs:
            q = enr.quote_fields(quotes.get(item.instrument_id))
            b = enr.bof_fields(signals.get(item.instrument_id))
            items.append({
                "instrument_id": item.instrument_id,
                "symbol": inst.symbol,
                "name": inst.name,
                "instrument_type": inst.instrument_type.value
                    if hasattr(inst.instrument_type, "value") else str(inst.instrument_type),
                "sector_name": inst.sector.name if inst.sector else None,
                "position": item.position,
                "alert_enabled": item.alert_enabled,
                **q, **b,
            })
        return {"id": wl.id, "name": wl.name, "created_at": wl.created_at, "items": items}

    # ------------------------------------------------------------------ CRUD

    async def list_for_user(self, user_id: uuid.UUID) -> list[dict]:
        """All watchlists with enriched items — batched (no per-list N+1)."""
        wls = (
            await self.db.execute(
                select(Watchlist)
                .where(Watchlist.user_id == user_id)
                .order_by(Watchlist.position, Watchlist.created_at)
            )
        ).scalars().all()
        if not wls:
            return []

        wl_ids = [w.id for w in wls]
        pairs_all = (
            await self.db.execute(
                select(WatchlistItem, Instrument)
                .join(Instrument, Instrument.id == WatchlistItem.instrument_id)
                .options(selectinload(Instrument.sector))
                .where(WatchlistItem.watchlist_id.in_(wl_ids))
                .order_by(WatchlistItem.position, WatchlistItem.added_at)
            )
        ).all()

        by_watchlist: dict[uuid.UUID, list] = {}
        for pair in pairs_all:
            by_watchlist.setdefault(pair[0].watchlist_id, []).append(pair)

        ids = [p[0].instrument_id for p in pairs_all]
        quotes = await enr.quotes_by_instrument(self.db, ids)
        signals = await enr.latest_signals_by_instrument(self.db, ids)

        def fmt(item, inst):
            return {
                "instrument_id": item.instrument_id,
                "symbol": inst.symbol,
                "name": inst.name,
                "instrument_type": inst.instrument_type.value
                    if hasattr(inst.instrument_type, "value") else str(inst.instrument_type),
                "sector_name": inst.sector.name if inst.sector else None,
                "position": item.position,
                "alert_enabled": item.alert_enabled,
                **enr.quote_fields(quotes.get(item.instrument_id)),
                **enr.bof_fields(signals.get(item.instrument_id)),
            }

        return [
            {
                "id": wl.id,
                "name": wl.name,
                "created_at": wl.created_at,
                "items": [fmt(i, inst) for i, inst in by_watchlist.get(wl.id, [])],
            }
            for wl in wls
        ]

    async def get(self, user_id: uuid.UUID, watchlist_id: uuid.UUID) -> dict:
        wl = await self._owned(user_id, watchlist_id)
        return await self._to_response(wl)

    async def create(self, user_id: uuid.UUID, name: str) -> dict:
        name = name.strip()
        dup = (
            await self.db.execute(
                select(Watchlist).where(
                    Watchlist.user_id == user_id, Watchlist.name == name
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise ConflictError("A watchlist with this name already exists")

        pos = (
            await self.db.execute(
                select(func.coalesce(func.max(Watchlist.position), -1) + 1)
                .where(Watchlist.user_id == user_id)
            )
        ).scalar_one()

        wl = Watchlist(user_id=user_id, name=name, position=int(pos))
        self.db.add(wl)
        await self.db.flush()
        return await self._to_response(wl)

    async def rename(self, user_id: uuid.UUID, watchlist_id: uuid.UUID, new_name: str) -> dict:
        wl = await self._owned(user_id, watchlist_id)
        new_name = new_name.strip()
        clash = (
            await self.db.execute(
                select(Watchlist).where(
                    Watchlist.user_id == user_id,
                    Watchlist.name == new_name,
                    Watchlist.id != wl.id,
                )
            )
        ).scalar_one_or_none()
        if clash is not None:
            raise ConflictError("A watchlist with this name already exists")
        wl.name = new_name
        await self.db.flush()
        return await self._to_response(wl)

    async def delete(self, user_id: uuid.UUID, watchlist_id: uuid.UUID) -> None:
        wl = await self._owned(user_id, watchlist_id)
        await self.db.delete(wl)
        await self.db.flush()

    # ------------------------------------------------------------------ items

    async def add_item(self, user_id: uuid.UUID, watchlist_id: uuid.UUID,
                       instrument_id: uuid.UUID, alert_enabled: bool) -> dict:
        wl = await self._owned(user_id, watchlist_id)

        inst = (
            await self.db.execute(select(Instrument).where(Instrument.id == instrument_id))
        ).scalar_one_or_none()
        if inst is None:
            raise NotFoundError("Instrument not found")

        dup = (
            await self.db.execute(
                select(WatchlistItem).where(
                    WatchlistItem.watchlist_id == wl.id,
                    WatchlistItem.instrument_id == instrument_id,
                )
            )
        ).scalar_one_or_none()
        if dup is not None:
            raise ConflictError("Instrument is already in this watchlist")

        pos = (
            await self.db.execute(
                select(func.coalesce(func.max(WatchlistItem.position), -1) + 1)
                .where(WatchlistItem.watchlist_id == wl.id)
            )
        ).scalar_one()

        self.db.add(WatchlistItem(
            watchlist_id=wl.id,
            instrument_id=instrument_id,
            alert_enabled=alert_enabled,
            position=int(pos),
        ))
        await self.db.flush()
        return await self._to_response(wl)

    async def update_item(self, user_id: uuid.UUID, watchlist_id: uuid.UUID,
                          instrument_id: uuid.UUID, *,
                          alert_enabled: bool | None, position: int | None) -> dict:
        wl = await self._owned(user_id, watchlist_id)
        item = (
            await self.db.execute(
                select(WatchlistItem).where(
                    WatchlistItem.watchlist_id == wl.id,
                    WatchlistItem.instrument_id == instrument_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise NotFoundError("Item not found")
        if alert_enabled is not None:
            item.alert_enabled = alert_enabled
        if position is not None:
            item.position = position
        await self.db.flush()
        return await self._to_response(wl)

    async def remove_item(self, user_id: uuid.UUID, watchlist_id: uuid.UUID,
                          instrument_id: uuid.UUID) -> None:
        wl = await self._owned(user_id, watchlist_id)
        item = (
            await self.db.execute(
                select(WatchlistItem).where(
                    WatchlistItem.watchlist_id == wl.id,
                    WatchlistItem.instrument_id == instrument_id,
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise NotFoundError("Item not found")
        await self.db.delete(item)
        await self.db.flush()


__all__ = ["WatchlistService"]
