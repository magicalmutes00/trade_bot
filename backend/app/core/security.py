"""Password hashing (Argon2) and JWT creation/validation.

- Passwords: Argon2id via argon2-cffi.
- Access tokens: short-lived JWTs, type claim `access`.
- Refresh tokens: longer-lived JWTs, type claim `refresh`, bound to a
  server-side session row (only a SHA-256 hash of the raw token is stored).
"""

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt as pyjwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_password_hasher = PasswordHasher()

TokenType = Literal["access", "refresh"]


# ---------------------------------------------------------------- passwords

def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _password_hasher.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except (InvalidHashError, ValueError):
        return False


def needs_rehash(hashed: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(hashed)
    except InvalidHashError:
        return True


# ---------------------------------------------------------------- tokens


@dataclass(frozen=True)
class DecodedToken:
    subject: str          # user id (str UUID)
    session_id: str       # session id (str UUID)
    token_type: TokenType
    expires_at: datetime
    payload: dict[str, Any]


def _create_token(
    *,
    subject: str,
    session_id: str,
    token_type: TokenType,
    lifetime: timedelta,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + lifetime
    payload: dict[str, Any] = {
        "sub": subject,
        "sid": session_id,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    encoded = pyjwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded, expires_at


def create_access_token(*, subject: str, session_id: str) -> tuple[str, datetime]:
    return _create_token(
        subject=subject,
        session_id=session_id,
        token_type="access",
        lifetime=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(*, subject: str, session_id: str) -> tuple[str, datetime]:
    return _create_token(
        subject=subject,
        session_id=session_id,
        token_type="refresh",
        lifetime=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType | None = None) -> DecodedToken:
    """Decode + validate a JWT. Raises ``InvalidTokenError`` on any failure."""
    payload = pyjwt.decode(
        token,
        settings.JWT_SECRET,
        algorithms=[settings.JWT_ALGORITHM],
        options={"require": ["sub", "exp", "type", "sid"]},
    )
    token_type = payload.get("type")
    if token_type not in ("access", "refresh"):
        raise pyjwt.InvalidTokenError("Unknown token type")
    if expected_type is not None and token_type != expected_type:
        raise pyjwt.InvalidTokenError(
            f"Expected {expected_type} token, got {token_type}"
        )
    return DecodedToken(
        subject=str(payload["sub"]),
        session_id=str(payload["sid"]),
        token_type=token_type,  # type: ignore[arg-type]
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=timezone.utc),
        payload=payload,
    )


# ---------------------------------------------------------------- opaque helpers

def sha256_hex(value: str) -> str:
    """Used to store refresh / reset tokens at rest — never store the raw value."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def new_secure_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex
