"""Firebase Admin SDK integration — initialization + ID-token verification.

Credentials come exclusively from environment variables:
    FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY

Private-key newlines pasted as literal ``\\n`` sequences are normalized safely.
No secret material is ever logged.
"""

import threading
from dataclasses import dataclass

from fastapi import status

from app.core.config import settings
from app.core.errors import AppError, TokenError
from app.core.logging import get_logger

logger = get_logger(__name__)

_APP_NAME = "bof-edge-api"


class FirebaseNotConfiguredError(AppError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    code = "FIREBASE_NOT_CONFIGURED"


@dataclass(frozen=True)
class FirebaseUserInfo:
    """Only the verified claims we need — never raw tokens or credentials."""

    uid: str
    email: str | None
    display_name: str | None
    photo_url: str | None
    email_verified: bool
    provider_id: str  # e.g. "google.com", "password"


_lock = threading.Lock()
_initialized = False


def normalize_private_key(raw: str) -> str:
    """Handle the common 'literal \\n' paste problem safely."""
    key = raw.strip().strip('"').strip("'")
    if "\\n" in key:
        key = key.replace("\\n", "\n")
    return key


def is_configured() -> bool:
    return bool(
        settings.FIREBASE_PROJECT_ID
        and settings.FIREBASE_CLIENT_EMAIL
        and settings.FIREBASE_PRIVATE_KEY
    )


def _ensure_app():  # noqa: ANN202
    """Lazily initialize the Admin SDK exactly once."""
    global _initialized
    if not is_configured():
        raise FirebaseNotConfiguredError(
            "Firebase authentication is not configured on this server"
        )
    with _lock:
        if _initialized:
            return
        import firebase_admin
        from firebase_admin import credentials

        try:
            firebase_admin.get_app(name=_APP_NAME)
            _initialized = True
            return
        except ValueError:
            pass

        cert = credentials.Certificate(
            {
                "type": "service_account",
                "project_id": settings.FIREBASE_PROJECT_ID,
                "private_key": normalize_private_key(settings.FIREBASE_PRIVATE_KEY),
                "client_email": settings.FIREBASE_CLIENT_EMAIL,
                # Required fields for Certificate validation completeness.
                "token_uri": "https://oauth2.googleapis.com/token",
                "universe_domain": "googleapis.com",
            }
        )
        firebase_admin.initialize_app(
            cert, {"projectId": settings.FIREBASE_PROJECT_ID}, name=_APP_NAME
        )
        _initialized = True
        logger.info("Firebase Admin SDK initialized project=%s", settings.FIREBASE_PROJECT_ID)


def verify_firebase_token(id_token: str) -> FirebaseUserInfo:
    """Verify a Firebase ID token and return trusted claims.

    Raises TokenError for any invalid/expired/revoked token and
    FirebaseNotConfiguredError when the server has no Firebase credentials.
    """
    try:
        from firebase_admin import auth as fb_auth
        from firebase_admin.exceptions import FirebaseError
    except ImportError as exc:  # pragma: no cover
        raise FirebaseNotConfiguredError("firebase-admin is not installed") from exc

    _ensure_app()
    app = __import__("firebase_admin").get_app(name=_APP_NAME)
    try:
        decoded = fb_auth.verify_id_token(id_token, app=app, check_revoked=True)
    except fb_auth.ExpiredIdTokenError as exc:
        raise TokenError("Your session has expired. Please sign in again.") from exc
    except fb_auth.RevokedIdTokenError as exc:
        raise TokenError("Token has been revoked. Please sign in again.") from exc
    except (fb_auth.InvalidIdTokenError, ValueError) as exc:
        raise TokenError("Invalid authentication token") from exc
    except FirebaseError as exc:
        logger.error("Firebase verification failure: %s", type(exc).__name__)
        raise TokenError("Authentication service error") from exc

    uid = decoded.get("uid")
    if not uid:
        raise TokenError("Invalid authentication token")

    firebase_claims = decoded.get("firebase", {})
    return FirebaseUserInfo(
        uid=str(uid),
        email=(decoded.get("email") or None),
        display_name=(decoded.get("name") or None),
        photo_url=(decoded.get("picture") or None),
        email_verified=bool(decoded.get("email_verified", False)),
        provider_id=str(firebase_claims.get("sign_in_provider", "unknown")),
    )
