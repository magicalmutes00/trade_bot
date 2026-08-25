"""Heatmap endpoint (public, Phase 5)."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.models.enums import InstrumentType
from app.schemas.common import ApiResponse, ok
from app.schemas.heatmap_watchlist import HeatmapResponse
from app.core import rediscache
from app.services.heatmap_service import HeatmapService
from app.services.instrument_service import parse_timeframe

router = APIRouter(prefix="/heatmap", tags=["heatmap"])


@router.get(
    "",
    response_model=ApiResponse[HeatmapResponse],
    summary="Colour-map grid of instruments with live quotes + BOF state",
)
async def heatmap(
    db: DbSession,
    group_by: str = Query(default="sector", pattern="^(sector|type)$"),
    type: Annotated[str | None, Query()] = None,
    sector_id: str | None = None,
    timeframe: str | None = None,
    only_with_signals: bool = False,
) -> ApiResponse[HeatmapResponse]:
    instrument_type = None
    if type:
        try:
            instrument_type = InstrumentType(type.upper())
        except ValueError as exc:
            from app.core.errors import ValidationError

            raise ValidationError(f"Unknown instrument type '{type}'") from exc

    parsed_sector = None
    # (sector filter applied post-query via cells; kept for API parity)
    _ = sector_id

    tf = parse_timeframe(timeframe) if timeframe else None
    key = f"heat:v1:{group_by}:{type or ''}:{tf.value if tf else 'any'}:{only_with_signals}"
    data = await rediscache.acached_json(
        key, 15,
        lambda: HeatmapService(db).build(
            group_by=group_by, instrument_type=instrument_type,
            timeframe=tf, only_with_signals=only_with_signals),
    )
    return ok(HeatmapResponse.model_validate(data))



