"""Dashboard endpoint (public)."""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.common import ApiResponse, ok
from app.schemas.dashboard import DashboardResponse
from app.core import rediscache
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get(
    "",
    response_model=ApiResponse[DashboardResponse],
    summary="Market overview, BOF summary and signal feeds",
    description=(
        "Index quotes populate once the market-data provider (Phase 3) starts "
        "publishing; until then `indices` is empty and `bof_summary` is zeroed â€” "
        "clients must render honest empty states, never placeholder prices."
    ),
)
async def dashboard(db: DbSession) -> ApiResponse[DashboardResponse]:
    data = await rediscache.acached_json(
        "dashboard:v1", 10,
        lambda: DashboardService(db).build(),
    )
    return ok(DashboardResponse.model_validate(data))



