"""Profile endpoints (authenticated)."""

from fastapi import APIRouter

from app.api.deps import DbSession
from app.api.dependencies.auth import CurrentUser
from app.schemas.auth import UserResponse
from app.schemas.common import ApiResponse, ok
from app.schemas.user import ProfileUpdateRequest
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ApiResponse[UserResponse], summary="Get the current user's profile")
async def get_profile(user: CurrentUser) -> ApiResponse[UserResponse]:
    return ok(UserResponse.model_validate(user))


@router.patch("", response_model=ApiResponse[UserResponse], summary="Update the current user's profile")
async def update_profile(
    payload: ProfileUpdateRequest, user: CurrentUser, db: DbSession
) -> ApiResponse[UserResponse]:
    updated = await ProfileService(db).update_profile(user, payload)
    return ok(UserResponse.model_validate(updated))


