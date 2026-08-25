"""Application settings, loaded from environment / .env file.

All secrets come from the environment â€” nothing is hard-coded.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    APP_NAME: str = "BOF Edge API"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    API_V1_PREFIX: str = "/api/v1"

    # --- Database ---
    DATABASE_URL: str = "postgresql+asyncpg://bof:bof_dev_password@localhost:5432/bof_scanner"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # --- Auth / JWT ---
    JWT_SECRET: str = "dev-only-insecure-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=14, gt=0)
    RESET_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)

    # --- CORS ---
    CORS_ORIGINS: list[str] | str = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    # --- Rate limiting (in-memory; swap for Redis later without API change) ---
    AUTH_RATE_LIMIT_PER_MINUTE: int = 10

    # --- Redis (optional; rate limiting + future caching) ---
    REDIS_URL: str | None = None

    # --- Live demo loop (Phase 4) ---
    LIVE_DEMO_ENABLED: bool = True
    DEMO_TICK_SECONDS: int = Field(default=10, ge=2, le=3600)

    # --- Firebase (Phase 6) ---
    FIREBASE_PROJECT_ID: str | None = None
    FIREBASE_CLIENT_EMAIL: str | None = None
    FIREBASE_PRIVATE_KEY: str | None = None

    # --- Market data (Phase 3/8) ---
    MARKET_DATA_PROVIDER: Literal["demo", "real", "yahoo"] = "yahoo"
    MARKET_DATA_API_KEY: str | None = None
    MARKET_BASE_URL: str = "https://api.example-ohlcv.com/v1"
    MARKET_MAX_RETRIES: int = 3

    # --- Seed admin ---
    SEED_ADMIN_EMAIL: str | None = None
    SEED_ADMIN_PASSWORD: str | None = None

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()


