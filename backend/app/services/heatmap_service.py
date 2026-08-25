"""Heatmap assembly."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Instrument
from app.services import market_enrichment as enr


class HeatmapService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        *,
        group_by: str = "sector",           # sector | type
        instrument_type=None,
        timeframe=None,
        only_with_signals: bool = False,
    ) -> dict:
        conds = [Instrument.is_active.is_(True)]
        if instrument_type is not None:
            conds.append(Instrument.instrument_type == instrument_type)

        instruments = (
            await self.db.execute(
                select(Instrument)
                .options(selectinload(Instrument.sector))
                .where(*conds)
                .order_by(Instrument.symbol)
            )
        ).scalars().all()

        enrichment = await enr.enrich(self.db, list(instruments), timeframe=timeframe)

        cells: list[dict] = []
        for i in instruments:
            e = enrichment.get(i.id, {})
            if only_with_signals and not e.get("bof_direction"):
                continue
            cells.append({
                "instrument_id": i.id,
                "symbol": i.symbol,
                "name": i.name,
                "instrument_type": i.instrument_type.value
                    if hasattr(i.instrument_type, "value") else str(i.instrument_type),
                "sector_name": i.sector.name if i.sector else None,
                "last_price": e.get("last_price"),
                "change_pct": e.get("change_pct"),
                "bof_direction": e.get("bof_direction"),
                "bof_strength": e.get("bof_strength"),
                "bof_status": e.get("bof_status"),
                "bof_timeframe": e.get("bof_timeframe"),
            })

        buckets: dict[str, list[dict]] = {}
        for c in cells:
            key = (c["sector_name"] or "Uncategorised") if group_by == "sector" else c["instrument_type"]
            buckets.setdefault(key, []).append(c)

        groups = [
            {"key": k, "label": k, "cells": v}
            for k, v in sorted(buckets.items(), key=lambda kv: (-len(kv[1]), kv[0]))
        ]
        return {
            "group_by": group_by,
            "groups": groups,
            "total_cells": len(cells),
            "updated_at": datetime.now(timezone.utc),
        }


__all__ = ["HeatmapService"]
