"""Profile & settings schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ThemeMode, Timeframe


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    avatar_url: str | None = Field(default=None, max_length=512)


class UserSettingsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    theme: ThemeMode
    default_timeframe: Timeframe
    preferences: dict[str, Any] | None


class UserSettingsUpdateRequest(BaseModel):
    theme: ThemeMode | None = None
    default_timeframe: Timeframe | None = None
    preferences: dict[str, Any] | None = None


class SessionInfo(BaseModel):
    """Active-session summary (admin/self audit)."""

    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    ip_address: str | None
    user_agent: str | None

    model_config = ConfigDict(from_attributes=True)
