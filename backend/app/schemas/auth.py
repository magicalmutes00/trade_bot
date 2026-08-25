"""Auth request/response schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models.enums import UserRole


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    username: str | None = Field(default=None, min_length=3, max_length=64)
    display_name: str | None = Field(default=None, max_length=120)

    @field_validator("username")
    @classmethod
    def username_charset(cls, v: str | None) -> str | None:
        if v is None:
            return None
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.")
        if not set(v) <= allowed:
            raise ValueError("username may only contain letters, digits, '_' and '.'")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20, max_length=2048)


class LogoutRequest(RefreshRequest):
    pass


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class FirebaseAuthRequest(BaseModel):
    """The Android client exchanges a verified Firebase ID token for an app user."""

    id_token: str = Field(min_length=20, max_length=8192)


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    firebase_uid: str | None = None
    email: EmailStr
    username: str | None
    display_name: str | None
    avatar_url: str | None
    photo_url: str | None = None
    auth_provider: str = "PASSWORD"
    role: UserRole
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds until access-token expiry


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: TokenResponse
