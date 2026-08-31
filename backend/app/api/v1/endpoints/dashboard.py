"""Dashboard endpoint (public)."""

import logging

from fastapi import APIRouter

from app.api.deps import DbSession
from app.schemas.common import ApiResponse, ok
from app.schemas.dashboard import (
    BofSummary,
    DashboardResponse,
    MarketStatus,
)
from app.services.dashboard_service import DashboardService, market_status

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=ApiResponse[DashboardResponse],
    summary="Market overview, BOF summary and signal feeds",
)
async def dashboard(db: DbSession) -> ApiResponse[DashboardResponse]:
    """Build dashboard with graceful fallback — never 500 on partial data.

    If indices / signals / bof summary raise, return an empty dashboard
    with market status so the client renders an honest empty state.
    """
    try:
        data = await DashboardService(db).build()
    except Exception as exc:
        logger.exception("dashboard build failed, returning empty: %s", exc)
        data = DashboardResponse(
            market_status=market_status(),
            indices=[],
            bof_summary=BofSummary(
                active_total=0, bullish=0, bearish=0,
                strong=0, new_today=0, detected_today=0,
            ),
            latest_signals=[],
            strongest_signals=[],
        )
    return ok(DashboardResponse.model_validate(data.model_dump()))



