"""Deployment settings mixin - standardized config for all apps."""

from __future__ import annotations

from functools import cached_property
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class DeploySettings(BaseSettings):
    """Base settings class with deployment configuration.

    Inherit from this in your app's Settings class:

        from deploy_toolkit import DeploySettings

        class Settings(DeploySettings):
            # App-specific settings only
            MY_CUSTOM_SETTING: str = "default"

    All standard settings are already defined:
        APP_NAME, SECRET_KEY, DEBUG, CORS_ORIGINS, DATABASE_URL,
        REDIS_URL, LOG_LEVEL, ADMIN_USERNAMES

    Environment variables are automatically loaded from .env file.
    """

    # === Application Identity ===
    APP_NAME: str = Field(
        default="",
        description="Application identifier, used for path prefix (e.g., 'flash-processing')",
    )

    # === Security ===
    SECRET_KEY: str = Field(
        default="",
        description="Secret key for signing tokens/sessions. REQUIRED in production (min 32 chars)",
    )
    ADMIN_USERNAMES: str = Field(
        default="admin",
        description="Comma-separated list of admin usernames",
    )

    # === Database ===
    DATABASE_URL: str = Field(
        default="sqlite:///./app.db",
        description="Database connection URL (postgres://user:pass@host:port/db or sqlite:///path)",
    )

    # === Redis (optional) ===
    REDIS_URL: str = Field(
        default="",
        description="Redis connection URL for caching/rate-limiting (redis://host:port/db)",
    )

    # === CORS ===
    CORS_ORIGINS: str = Field(
        default="*",
        description="Comma-separated list of allowed CORS origins, or '*' for all",
    )

    # === Logging & Debug ===
    DEBUG: bool = Field(
        default=False,
        description="Enable debug mode (verbose logging, detailed errors)",
    )
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging level",
    )

    # === Rate Limiting ===
    RATE_LIMIT_DEFAULT: str = Field(
        default="100/minute",
        description="Default rate limit for API endpoints",
    )
    RATE_LIMIT_UPLOAD: str = Field(
        default="60/minute",
        description="Rate limit for upload endpoints",
    )

    # === API Keys ===
    UPLOAD_API_KEY: str = Field(
        default="",
        description="API key for protecting upload endpoints (leave empty to disable)",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    # === Validators ===

    @field_validator("CORS_ORIGINS")
    @classmethod
    def validate_cors_origins(cls, v: str) -> str:
        """Validate CORS origins format."""
        origins = [o.strip() for o in v.split(",") if o.strip()]
        if "*" in origins and len(origins) > 1:
            raise ValueError("Cannot mix wildcard '*' with other CORS origins")
        return v

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Validate database URL format."""
        if not v:
            return v
        valid_prefixes = ("postgresql://", "postgres://", "sqlite:///", "mysql://")
        if not any(v.startswith(p) for p in valid_prefixes):
            raise ValueError(f"DATABASE_URL must start with one of: {valid_prefixes}")
        return v

    # === Computed Properties ===

    @property
    def app_name(self) -> str:
        """Get app name (lowercase, normalized)."""
        return self.APP_NAME.lower().strip()

    @property
    def root_path(self) -> str:
        """Get root path for reverse proxy configuration."""
        return f"/{self.app_name}" if self.app_name else ""

    @cached_property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as a list."""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @cached_property
    def admin_usernames_list(self) -> list[str]:
        """Get admin usernames as a list."""
        return [u.strip() for u in self.ADMIN_USERNAMES.split(",") if u.strip()]

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.DEBUG

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL."""
        return self.DATABASE_URL.startswith(("postgresql://", "postgres://"))

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self.DATABASE_URL.startswith("sqlite:///")

    # === Validation ===

    def validate_production(self) -> None:
        """Validate settings for production use. Call during startup."""
        errors = []

        if self.is_production:
            if not self.SECRET_KEY:
                errors.append("SECRET_KEY is required in production")
            elif len(self.SECRET_KEY) < 32:
                errors.append("SECRET_KEY should be at least 32 characters")

            if self.CORS_ORIGINS == "*":
                # Warning, not error - allow but log
                import logging
                logging.warning("CORS_ORIGINS='*' in production is not recommended")

        if errors:
            raise ValueError(f"Production validation failed: {'; '.join(errors)}")
