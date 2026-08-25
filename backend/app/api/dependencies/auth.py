"""Authentication dependencies.

Two authentication authorities coexist by design:

1. **Firebase ID tokens** (Google Sign-In from the Android app) — preferred.
2. **Legacy internal JWT access tokens** (email/password accounts) — kept so
   existing clients keep working; see section 24 of the auth spec.

``get_current_firebase_user``  → strictly verifies a Firebase ID token and
returns trusted claims (never client-supplied values).
``get_current_user``           → resolves the DB ``User`` from *either*
authority; used to protect user-scoped endpoints.
"""

import uuid
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import DbSession
from app.core import firebase
from app.core.errors import AuthorizationError, TokenError
from app.core.security import decode_token
from app.models import User
from app.repositories.user_repository import UserRepository

_bearer = HTTPBearer(auto_error=False, scheme_name="FirebaseOrLegacyJWT")


async def get_current_firebase_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> firebase.FirebaseUserInfo:
    """Verify the ``Authorization: Bearer <Firebase ID Token>`` header."""
    if credentials is None:
        raise TokenError("Missing bearer token")
    # verify_id_token does RSA work → run off the event loop.
    return await run_in_threadpool(firebase.verify_firebase_token, credentials.credentials)


CurrentUserFromFirebase = Annotated[firebase.FirebaseUserInfo, Depends(get_current_firebase_user)]


async def _resolve_legacy_user(token: str, db: AsyncSession) -> User | None:
    try:
        decoded = decode_token(token, expected_type="access")
    except pyjwt.InvalidTokenError:
        return None
    user = await UserRepository(db).get_by_id(uuid.UUID(decoded.subject))
    return user


async def _resolve_firebase_user(token: str, db: AsyncSession) -> User | None:
    try:
        info = await run_in_threadpool(firebase.verify_firebase_token, token)
    except firebase.FirebaseNotConfiguredError as exc:
        # Protected endpoints must answer 401 for bad tokens even when this
        # deployment has no Firebase credentials; configuration issues are
        # reported by the explicit /auth/firebase exchange endpoint.
        raise TokenError("Invalid access token") from exc
    repo = UserRepository(db)
    user = await repo.get_by_firebase_uid(info.uid)
    if user is None and info.email:
        # Linked legacy accounts are matched by verified email only.
        candidate = await repo.get_by_email(info.email)
        if candidate is not None and candidate.firebase_uid is None:
            user = candidate
    return user


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    """Resolve the application user from a Firebase ID token or legacy JWT."""
    if credentials is None:
        raise TokenError("Missing bearer token")
    token = credentials.credentials

    # Authority 1: internal access JWT (has an explicit `type` claim).
    user = await _resolve_legacy_user(token, db)
    if user is not None:
        if not user.is_active:
            raise AuthorizationError("Account is disabled")
        return user

    # Authority 2: Firebase ID token (verified server-side; UIDs/emails inside
    # the request body are never trusted).
    user = await _resolve_firebase_user(token, db)
    if user is None:
        raise TokenError("Session expired or account missing. Please sign in again.")
    if not user.is_active:
        raise AuthorizationError("Account is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUser) -> User:
    """Admin guard — every /admin route must depend on this."""
    from app.models.enums import UserRole

    if user.role != UserRole.ADMIN:
        raise AuthorizationError("Administrator privileges required")
    return user


AdminUser = Annotated[User, Depends(require_admin)]
