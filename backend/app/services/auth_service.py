"""Authentication business logic.

Flows: register, login, refresh (with rotation + reuse detection), logout,
forgot/reset password (architecture ready; email delivery pluggable).

Refresh-token design
--------------------
The refresh JWT itself is the credential. Each issued refresh JWT is bound to
a ``user_sessions`` row whose ``refresh_token_hash`` is SHA-256(raw JWT).
On refresh the presented JWT's hash must match an active, unexpired session;
that session is revoked and a brand-new pair is issued (rotation). Presenting
a rotated/unknown refresh token revokes ALL sessions for the user (theft guard).
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import (
    AuthorizationError,
    ConflictError,
    InvalidCredentialsError,
    NotFoundError,
    TokenError,
    ValidationError,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    needs_rehash,
    new_secure_token,
    sha256_hex,
    verify_password,
)
from app.models import User
from app.repositories.reset_token_repository import ResetTokenRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import AuthResponse, RegisterRequest, TokenResponse, UserResponse

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(value: datetime) -> datetime:
    """SQLite returns naive datetimes; treat them as UTC for safe comparison."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.sessions = SessionRepository(db)
        self.resets = ResetTokenRepository(db)

    # ------------------------------------------------------------------ register

    async def register(
        self,
        payload: RegisterRequest,
        *,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthResponse:
        if await self.users.get_by_email(payload.email):
            raise ConflictError("An account with this email already exists")
        if payload.username and await self.users.get_by_username(payload.username):
            raise ConflictError("This username is already taken")

        user = await self.users.create(
            email=payload.email,
            hashed_password=hash_password(payload.password),
            username=payload.username,
            display_name=payload.display_name,
        )
        tokens = await self._issue_session_and_tokens(user, user_agent=user_agent, ip_address=ip_address)
        logger.info("user registered user_id=%s", user.id)
        return AuthResponse(user=UserResponse.model_validate(user), tokens=tokens)

    # ------------------------------------------------------------------ login

    async def login(
        self,
        *,
        email: str,
        password: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> AuthResponse:
        user = await self.users.get_by_email(email)
        # Uniform error path: never reveal whether the email exists.
        if (
            user is None
            or user.hashed_password is None  # Google-only account
            or not verify_password(password, user.hashed_password)
        ):
            raise InvalidCredentialsError("Incorrect email or password")
        if not user.is_active:
            raise AuthorizationError("Account is disabled")

        # Transparent Argon2 parameter upgrades on successful login.
        if needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        tokens = await self._issue_session_and_tokens(user, user_agent=user_agent, ip_address=ip_address)
        logger.info("user logged in user_id=%s", user.id)
        return AuthResponse(user=UserResponse.model_validate(user), tokens=tokens)

    # ------------------------------------------------------------------ refresh

    async def refresh(self, refresh_token: str) -> TokenResponse:
        try:
            decoded = decode_token(refresh_token, expected_type="refresh")
        except pyjwt.ExpiredSignatureError as exc:
            raise TokenError("Refresh token expired") from exc
        except pyjwt.InvalidTokenError as exc:
            raise TokenError("Invalid refresh token") from exc

        now = _utcnow()
        session_row = await self.sessions.get_active_by_token_hash(sha256_hex(refresh_token))

        if session_row is None:
            # Unknown or already-rotated token → possible theft: kill all sessions.
            await self.sessions.revoke_all_for_user(uuid.UUID(decoded.subject), now)
            await self.db.commit()
            raise TokenError("Refresh token has been revoked")

        if _ensure_utc(session_row.expires_at) <= now:
            await self.sessions.revoke(session_row, now)
            await self.db.commit()
            raise TokenError("Refresh token expired")

        user = await self.users.get_by_id(uuid.UUID(decoded.subject))
        if user is None or not user.is_active:
            raise TokenError("Account unavailable")

        await self.sessions.revoke(session_row, now)  # rotate
        tokens = await self._issue_session_and_tokens(user, user_agent=None, ip_address=None)
        logger.info("session refreshed user_id=%s", user.id)
        return tokens

    # ------------------------------------------------------------------ logout

    async def logout(self, refresh_token: str) -> int:
        try:
            decoded = decode_token(refresh_token, expected_type="refresh")
        except pyjwt.InvalidTokenError:
            return 0  # logging out with an invalid/expired token is idempotent
        row = await self.sessions.get_active_by_token_hash(sha256_hex(refresh_token))
        if row is None:
            return 0
        await self.sessions.revoke(row, _utcnow())
        logger.info("user logged out user_id=%s", decoded.subject)
        return 1

    # ------------------------------------------------------------------ password reset

    async def forgot_password(self, email: str) -> None:
        """Create a reset token. Always succeeds to avoid account enumeration."""
        user = await self.users.get_by_email(email)
        if user is None:
            return
        raw = new_secure_token()
        await self.resets.create(
            user_id=user.id,
            token_hash=sha256_hex(raw),
            expires_at=_utcnow() + timedelta(minutes=settings.RESET_TOKEN_EXPIRE_MINUTES),
        )
        # Delivery adapter (SMTP/SendGrid) plugs in here; Phase 6+ wires FCM.
        logger.info("password reset requested user_id=%s", user.id)

    async def reset_password(self, *, token: str, new_password: str) -> None:
        row = await self.resets.get_valid_by_token_hash(sha256_hex(token), _utcnow())
        if row is None:
            raise ValidationError("Reset link is invalid or has expired")
        await self.resets.mark_used(row, _utcnow())
        user = await self.users.get_by_id(row.user_id)
        if user is None:
            raise NotFoundError("Account not found")
        user.hashed_password = hash_password(new_password)
        await self.sessions.revoke_all_for_user(user.id, _utcnow())
        logger.info("password reset completed user_id=%s", user.id)

    # ------------------------------------------------------------------ firebase

    async def firebase_sync(self, info) -> User:
        """Create or update the application user from a *verified* Firebase token.

        - Existing Firebase-linked account → refresh profile + last_login_at.
        - Legacy email/password account with the same email → link it (keeps
          provider PASSWORD so password login continues to work).
        - Otherwise → provision a new Google-authenticated user (no password).
        """
        from app.models.enums import AuthProvider

        now = _utcnow()
        user = await self.users.get_by_firebase_uid(info.uid)

        if user is None and info.email:
            existing = await self.users.get_by_email(info.email)
            if existing is not None:
                user = existing  # link legacy account to Firebase identity

        if user is None:
            email = info.email or f"{info.uid}@users.noreply.BoFEdge.invalid"
            user = await self.users.create(
                email=email,
                hashed_password=None,
                display_name=info.display_name,
            )
            user.auth_provider = AuthProvider.GOOGLE
            logger.info("firebase user created user_id=%s", user.id)

        user.firebase_uid = info.uid
        user.last_login_at = now
        if info.photo_url:
            user.photo_url = info.photo_url
            if not user.avatar_url:
                user.avatar_url = info.photo_url
        if not user.display_name and info.display_name:
            user.display_name = info.display_name
        self.db.add(user)
        await self.db.flush()
        return user

    # ------------------------------------------------------------------ helpers

    async def _issue_session_and_tokens(
        self, user: User, *, user_agent: str | None, ip_address: str | None
    ) -> TokenResponse:
        """Create the session row first, then bind both JWTs to its id."""
        session_row = await self.sessions.create(
            user_id=user.id,
            refresh_token_hash="pending",
            expires_at=_utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            user_agent=user_agent,
            ip_address=ip_address,
        )
        access, _ = create_access_token(subject=str(user.id), session_id=str(session_row.id))
        refresh, _ = create_refresh_token(subject=str(user.id), session_id=str(session_row.id))
        session_row.refresh_token_hash = sha256_hex(refresh)
        await self.db.flush()
        return TokenResponse(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )
