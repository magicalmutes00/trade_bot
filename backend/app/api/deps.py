"""Shared FastAPI dependencies: DB session, current user, rate limiting."""

import uuid
from typing import Annotated

import jwt as pyjwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AuthorizationError, TokenError
from app.core.rate_limit import check_rate_limit
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.repositories.user_repository import UserRepository

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


def rate_limit_auth(request: Request) -> None:
    """Per-IP sliding-window limiter for sensitive auth endpoints.

    In-memory in Phase 1; swap storage inside core/rate_limit.py for Redis
    later without touching any caller.
    """
    client_ip = request.client.host if request.client else "unknown"
    check_rate_limit(f"auth:{client_ip}", settings.AUTH_RATE_LIMIT_PER_MINUTE)


RateLimited = Annotated[None, Depends(rate_limit_auth)]


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    if credentials is None:
        raise TokenError("Missing bearer token")
    try:
        decoded = decode_token(credentials.credentials, expected_type="access")
    except pyjwt.ExpiredSignatureError as exc:
        raise TokenError("Access token expired") from exc
    except pyjwt.InvalidTokenError as exc:
        raise TokenError("Invalid access token") from exc

    user = await UserRepository(db).get_by_id(uuid.UUID(decoded.subject))
    if user is None:
        raise TokenError("Account no longer exists")
    if not user.is_active:
        raise AuthorizationError("Account is disabled")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
