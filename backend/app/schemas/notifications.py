"""Notification schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import NotificationPlatform, SignalStrength


class TokenRegisterRequest(BaseModel):
    fcm_token: str = Field(min_length=8, max_length=4096)
    platform: NotificationPlatform = NotificationPlatform.ANDROID
    device_id: str | None = Field(default=None, max_length=128)


class TokenItem(BaseModel):
    id: uuid.UUID
    platform: NotificationPlatform
    device_id: str | None
    is_active: bool
    created_at: datetime


class PreferencesResponse(BaseModel):
    push_enabled: bool
    bullish_alerts: bool
    bearish_alerts: bool
    strong_only: bool
    watchlist_only: bool
    min_strength: SignalStrength


class PreferencesUpdateRequest(BaseModel):
    push_enabled: bool | None = None
    bullish_alerts: bool | None = None
    bearish_alerts: bool | None = None
    strong_only: bool | None = None
    watchlist_only: bool | None = None
    min_strength: SignalStrength | None = None


class NotificationsOverview(BaseModel):
    preferences: PreferencesResponse
    tokens: list[TokenItem]
