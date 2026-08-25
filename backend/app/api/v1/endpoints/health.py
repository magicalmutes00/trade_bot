"""Health & readiness endpoints (unauthenticated)."""

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings
from app.schemas.common import ApiResponse, ok

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ApiResponse[dict], summary="API + database health")
async def health(db: DbSession) -> ApiResponse[dict]:
    try:
        await db.execute(text("SELECT 1"))
        db_status = "up"
    except Exception:
        db_status = "down"
    return ok({
        "status": "ok" if db_status == "up" else "degraded",
        "database": db_status,
        "environment": settings.ENVIRONMENT,
        "time": datetime.now(timezone.utc).isoformat(),
    })
