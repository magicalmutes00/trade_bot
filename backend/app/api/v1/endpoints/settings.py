"""User settings endpoints (authenticated)."""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.dependencies.auth import CurrentUser
from app.schemas.common import ApiResponse, ok
from app.schemas.user import UserSettingsResponse, UserSettingsUpdateRequest
from app.services.profile_service import SettingsService

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=ApiResponse[UserSettingsResponse], summary="Get user settings")
async def get_settings(user: CurrentUser, db: DbSession) -> ApiResponse[UserSettingsResponse]:
    row = await SettingsService(db).get_or_create(user)
    return ok(UserSettingsResponse.model_validate(row))


@router.patch("", response_model=ApiResponse[UserSettingsResponse], summary="Update user settings")
async def update_settings(
    payload: UserSettingsUpdateRequest, user: CurrentUser, db: DbSession
) -> ApiResponse[UserSettingsResponse]:
    row = await SettingsService(db).update(user, payload)
    return ok(UserSettingsResponse.model_validate(row))


