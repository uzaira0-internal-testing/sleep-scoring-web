"""
Application configuration using Pydantic Settings.

Single source of configuration for the web application.
Loads from environment variables with .env file support.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from global_auth import AuthSettingsMixin
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(AuthSettingsMixin, BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Sleep Scoring Web"
    app_version: str = "0.1.0"
    sql_echo: bool = False  # Log all SQL statements (very verbose, disable by default)
    environment: Literal["development", "staging", "production"] = "development"

    # API Settings
    api_prefix: str = "/api/v1"  # Standardized prefix matching other apps
    cors_origins: str = "http://localhost:5173,http://localhost:3000"  # Comma-separated string

    # Rate Limiting
    rate_limit_default: str = "100/minute"
    rate_limit_upload: str = "60/minute"

    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as a list."""
        if self.cors_origins == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Session settings (custom for this app)
    session_expire_hours: int = 24 * 7  # 1 week default

    # Database - PostgreSQL (primary)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "sleep_scoring"
    postgres_password: str = "sleep_scoring"  # noqa: S105
    postgres_db: str = "sleep_scoring"

    # Database - SQLite (backup/development)
    sqlite_path: str = "sleep_scoring_web.db"
    use_sqlite: bool = True  # Use SQLite for development, PostgreSQL for production

    # File Upload
    upload_dir: str = "/app/uploads"
    max_upload_size_mb: int = 5000
    upload_api_key: str = ""  # API key for programmatic uploads (pipeline integration)

    # TUS Resumable Upload
    tus_upload_dir: str = "/app/uploads/tus"
    tus_max_upload_size_gb: int = 5
    tus_stale_days: int = 1

    # Data directory - use POST /api/v1/files/scan to import files
    data_dir: str = "/app/data"
    scan_data_dir_on_startup: bool = False  # Never block startup - use background tasks

    # Data Processing
    default_epoch_length: int = 60
    default_skip_rows: int = 10

    @computed_field
    @property
    def postgres_dsn(self) -> str:
        """Build PostgreSQL connection string."""
        return f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    @computed_field
    @property
    def sqlite_dsn(self) -> str:
        """Build SQLite connection string."""
        return f"sqlite+aiosqlite:///{self.sqlite_path}"

    @computed_field
    @property
    def database_url(self) -> str:
        """Get the active database URL based on configuration."""
        if self.use_sqlite:
            return self.sqlite_dsn
        return self.postgres_dsn


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
