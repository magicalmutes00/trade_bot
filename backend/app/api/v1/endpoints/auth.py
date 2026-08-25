"""Authentication endpoints."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import DbSession, rate_limit_auth
from app.core import firebase
from app.schemas.auth import (
    AuthResponse,
    FirebaseAuthRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.common import ApiResponse, ok
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_meta(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip = request.client.host if request.client else None
    return user_agent, ip


@router.post(
    "/register",
    response_model=ApiResponse[AuthResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_auth)],
    summary="Create a new account",
)
async def register(payload: RegisterRequest, request: Request, db: DbSession) -> ApiResponse[AuthResponse]:
    ua, ip = _client_meta(request)
    result = await AuthService(db).register(payload, user_agent=ua, ip_address=ip)
    return ok(result)


@router.post(
    "/login",
    response_model=ApiResponse[AuthResponse],
    dependencies=[Depends(rate_limit_auth)],
    summary="Exchange credentials for an access + refresh token pair",
)
async def login(payload: LoginRequest, request: Request, db: DbSession) -> ApiResponse[AuthResponse]:
    ua, ip = _client_meta(request)
    result = await AuthService(db).login(
        email=payload.email, password=payload.password, user_agent=ua, ip_address=ip
    )
    return ok(result)


@router.post(
    "/firebase",
    response_model=ApiResponse[UserResponse],
    dependencies=[Depends(rate_limit_auth)],
    summary="Exchange a Firebase ID token (Google Sign-In) for the application user",
    description=(
        "Verifies the Firebase ID token server-side, creates or updates the "
        "PostgreSQL user, and returns application profile information. The "
        "token is never stored; only verified claims are trusted."
    ),
)
async def auth_firebase(payload: FirebaseAuthRequest, db: DbSession) -> ApiResponse[UserResponse]:
    info = await run_in_threadpool(firebase.verify_firebase_token, payload.id_token)
    user = await AuthService(db).firebase_sync(info)
    return ok(UserResponse.model_validate(user))


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenResponse],
    dependencies=[Depends(rate_limit_auth)],
    summary="Rotate refresh token and obtain a new access token",
)
async def refresh(payload: RefreshRequest, db: DbSession) -> ApiResponse[TokenResponse]:
    return ok(await AuthService(db).refresh(payload.refresh_token))


@router.post(
    "/logout",
    response_model=ApiResponse[dict],
    summary="Revoke the presented refresh token session",
)
async def logout(payload: LogoutRequest, db: DbSession) -> ApiResponse[dict]:
    revoked = await AuthService(db).logout(payload.refresh_token)
    return ok({"revoked": bool(revoked)})


@router.post(
    "/forgot-password",
    response_model=ApiResponse[dict],
    dependencies=[Depends(rate_limit_auth)],
    summary="Request a password reset (always returns success to avoid enumeration)",
)
async def forgot_password(payload: ForgotPasswordRequest, db: DbSession) -> ApiResponse[dict]:
    await AuthService(db).forgot_password(payload.email)
    return ok({"message": "If that account exists, a reset link has been sent"})


@router.post(
    "/reset-password",
    response_model=ApiResponse[dict],
    dependencies=[Depends(rate_limit_auth)],
    summary="Complete a password reset with a valid token",
)
async def reset_password(payload: ResetPasswordRequest, db: DbSession) -> ApiResponse[dict]:
    await AuthService(db).reset_password(token=payload.token, new_password=payload.new_password)
    return ok({"message": "Password updated. Please sign in again."})


