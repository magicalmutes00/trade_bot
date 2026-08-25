"""Notification endpoints (authenticated)."""

from fastapi import APIRouter, Query, status

from app.api.dependencies.auth import CurrentUser
from app.api.deps import DbSession
from app.repositories.notification_repository import NotificationRepository
from app.schemas.common import ApiResponse, ok
from app.schemas.notifications import (
    PreferencesUpdateRequest,
    NotificationsOverview,
    PreferencesResponse,
    TokenItem,
    TokenRegisterRequest,
)
from app.services.notification_service import send_test_push

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _prefs_response(row) -> PreferencesResponse:  # noqa: ANN001
    return PreferencesResponse(
        push_enabled=row.push_enabled,
        bullish_alerts=row.bullish_alerts,
        bearish_alerts=row.bearish_alerts,
        strong_only=row.strong_only,
        watchlist_only=row.watchlist_only,
        min_strength=row.min_strength,
    )


def _token_item(row) -> TokenItem:  # noqa: ANN001
    return TokenItem(
        id=row.id, platform=row.platform, device_id=row.device_id,
        is_active=row.is_active, created_at=row.created_at,
    )


@router.get("", response_model=ApiResponse[NotificationsOverview],
            summary="Notification settings summary (preferences + devices)")
async def overview(user: CurrentUser, db: DbSession) -> ApiResponse[NotificationsOverview]:
    repo = NotificationRepository(db)
    prefs = await repo.get_or_create_prefs(user.id)
    tokens = await repo.tokens_for_user(user.id)
    return ok(NotificationsOverview(
        preferences=_prefs_response(prefs),
        tokens=[_token_item(t) for t in tokens],
    ))


@router.post("/tokens", response_model=ApiResponse[TokenItem], status_code=status.HTTP_201_CREATED,
             summary="Register / refresh this device's FCM token")
async def register_token(
    payload: TokenRegisterRequest, user: CurrentUser, db: DbSession
) -> ApiResponse[TokenItem]:
    row = await NotificationRepository(db).register_token(
        user_id=user.id,
        fcm_token=payload.fcm_token,
        platform=payload.platform,
        device_id=payload.device_id,
    )
    return ok(_token_item(row))


@router.delete("/tokens", response_model=ApiResponse[dict],
               summary="Deactivate one of this account's device tokens")
async def deactivate_token(
    user: CurrentUser, db: DbSession,
    fcm_token: str = Query(min_length=8, max_length=4096),
) -> ApiResponse[dict]:
    removed = await NotificationRepository(db).deactivate_token(
        user_id=user.id, fcm_token=fcm_token
    )
    return ok({"deactivated": removed})


@router.get("/preferences", response_model=ApiResponse[PreferencesResponse],
            summary="Get notification preferences (defaults on first call)")
async def get_preferences(user: CurrentUser, db: DbSession) -> ApiResponse[PreferencesResponse]:
    from app.schemas.notifications import PreferencesUpdateRequest

    _ = PreferencesUpdateRequest
    row = await NotificationRepository(db).get_or_create_prefs(user.id)
    return ok(_prefs_response(row))


@router.patch("/preferences", response_model=ApiResponse[PreferencesResponse],
              summary="Update notification preferences")
async def update_preferences(
    payload: PreferencesUpdateRequest,
    user: CurrentUser,
    db: DbSession,
):
    row = await NotificationRepository(db).update_prefs(
        user.id,
        push_enabled=payload.push_enabled,
        bullish_alerts=payload.bullish_alerts,
        bearish_alerts=payload.bearish_alerts,
        strong_only=payload.strong_only,
        watchlist_only=payload.watchlist_only,
        min_strength=payload.min_strength,
    )
    return ok(_prefs_response(row))


@router.post("/test-push", response_model=ApiResponse[dict],
             summary="Send a test push to all active devices of the caller")
async def test_push(user: CurrentUser, db: DbSession,
                    symbol: str = Query(default="TCS", max_length=32)) -> ApiResponse[dict]:
    sent = await send_test_push(db, user.id, symbol=symbol)
    return ok({"sent": sent, "sender_configured": True})

