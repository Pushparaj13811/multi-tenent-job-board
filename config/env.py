"""
Validated environment configuration using pydantic-settings.
Import this in settings files instead of using os.environ directly.

Usage in config/settings/base.py:
    from config.env import env
    SECRET_KEY = env.SECRET_KEY
"""

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class HireFlowSettings(BaseSettings):
    """
    All environment variables for the HireFlow application.
    Validated at startup — the app will refuse to start with missing or invalid config.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Django Core ──
    SECRET_KEY: str = Field(
        ...,
        min_length=50,
        description="Django secret key. Must be at least 50 characters.",
    )
    DEBUG: bool = Field(default=False)
    ALLOWED_HOSTS: list[str] = Field(
        default=["localhost", "127.0.0.1"],
    )
    DJANGO_SETTINGS_MODULE: str = Field(default="config.settings.development")

    # ── Database (PostgreSQL) ──
    DATABASE_URL: PostgresDsn = Field(
        ...,
        description="Full PostgreSQL connection string.",
    )

    # ── Redis ──
    REDIS_URL: RedisDsn = Field(
        default="redis://redis:6379/0",
    )

    # ── Celery ──
    CELERY_BROKER_URL: RedisDsn = Field(default="redis://redis:6379/0")
    CELERY_TASK_TIME_LIMIT: int = Field(default=300, ge=30, le=3600)
    CELERY_TASK_SOFT_TIME_LIMIT: int = Field(default=240, ge=30, le=3600)

    # ── JWT ──
    JWT_ACCESS_TOKEN_LIFETIME_MINUTES: int = Field(default=30, ge=5, le=1440)
    JWT_REFRESH_TOKEN_LIFETIME_DAYS: int = Field(default=7, ge=1, le=30)

    # ── Email (SMTP) ──
    EMAIL_BACKEND: str = Field(default="django.core.mail.backends.smtp.EmailBackend")
    EMAIL_HOST: str = Field(default="smtp.gmail.com")
    EMAIL_PORT: int = Field(default=587, ge=1, le=65535)
    EMAIL_USE_TLS: bool = Field(default=True)
    EMAIL_HOST_USER: str = Field(default="")
    EMAIL_HOST_PASSWORD: str = Field(default="")
    DEFAULT_FROM_EMAIL: str = Field(default="noreply@hireflow.io")

    # ── File Uploads ──
    MAX_RESUME_SIZE_MB: int = Field(default=5, ge=1, le=25)
    ALLOWED_RESUME_TYPES: list[str] = Field(
        default=[
            "application/pdf",
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
    )

    # ── CORS ──
    CORS_ALLOWED_ORIGINS: list[str] = Field(
        default=["http://localhost:3000"],
    )

    # ── Validators ──
    @field_validator("CELERY_TASK_SOFT_TIME_LIMIT")
    @classmethod
    def soft_limit_must_be_less_than_hard_limit(cls, v, info):
        hard_limit = info.data.get("CELERY_TASK_TIME_LIMIT", 300)
        if v >= hard_limit:
            raise ValueError(
                f"CELERY_TASK_SOFT_TIME_LIMIT ({v}) must be less than "
                f"CELERY_TASK_TIME_LIMIT ({hard_limit})"
            )
        return v


# Singleton — instantiated once at import time.
env = HireFlowSettings()
