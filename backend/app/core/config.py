from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read exclusively from environment variables / .env.

    No secret has a usable default: SECRET_KEY must be provided explicitly in production.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENV: Literal["development", "test", "production"] = "development"
    APP_NAME: str = "Immo Agence"
    SECRET_KEY: str = ""
    DATABASE_URL: str = "postgresql+psycopg://immo@localhost:5434/immo"

    # Public URL of the frontend, used to build invitation / reset links.
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    SESSION_COOKIE_NAME: str = "immo_session"
    CSRF_COOKIE_NAME: str = "immo_csrf"
    SESSION_TTL_HOURS: int = 12
    COOKIE_SECURE: bool = False
    INVITE_TTL_HOURS: int = 72

    LOGIN_MAX_FAILURES: int = 5
    LOGIN_WINDOW_MINUTES: int = 15
    PUBLIC_FORM_MAX_PER_HOUR: int = 10
    TRUST_PROXY_HEADERS: bool = False

    STORAGE_BACKEND: Literal["local", "s3"] = "local"
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_MB: int = 15
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_REGION: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""

    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_STARTTLS: bool = True

    SCHEDULER_INTERVAL_SECONDS: int = 300
    LOG_LEVEL: str = "INFO"

    @field_validator("SECRET_KEY")
    @classmethod
    def _secret_required_in_prod(cls, v: str, info):
        env = info.data.get("ENV", "development")
        if env == "production" and len(v) < 32:
            raise ValueError("SECRET_KEY must be set (>= 32 chars) in production")
        return v or "dev-only-insecure-secret-key-change-me"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def smtp_configured(self) -> bool:
        return bool(self.SMTP_HOST and self.SMTP_FROM)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
