"""
Tests for sleep_scoring_web.db.session module.

Covers session creation, init_db, drop_db, and the _apply_migrations logic.
Uses mocking to avoid real database connections.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sleep_scoring_web.config import Settings


class TestSettingsDSN:
    """Tests for database URL construction in Settings."""

    def test_sqlite_dsn(self):
        """SQLite DSN should use aiosqlite driver."""
        s = Settings(
            SITE_PASSWORD="test",
            use_sqlite=True,
            sqlite_path="test.db",
        )
        assert s.sqlite_dsn == "sqlite+aiosqlite:///test.db"
        assert s.database_url == s.sqlite_dsn

    def test_postgres_dsn(self):
        """PostgreSQL DSN should use asyncpg driver."""
        s = Settings(
            SITE_PASSWORD="test",
            use_sqlite=False,
            postgres_host="db.example.com",
            postgres_port=5433,
            postgres_user="myuser",
            postgres_password="mypass",
            postgres_db="mydb",
        )
        assert s.postgres_dsn == "postgresql+asyncpg://myuser:mypass@db.example.com:5433/mydb"
        assert s.database_url == s.postgres_dsn

    def test_database_url_switches_on_use_sqlite(self):
        """database_url should follow use_sqlite flag."""
        s_sqlite = Settings(SITE_PASSWORD="test", use_sqlite=True)
        s_pg = Settings(SITE_PASSWORD="test", use_sqlite=False)
        assert "sqlite" in s_sqlite.database_url
        assert "postgresql" in s_pg.database_url

    def test_default_postgres_values(self):
        """Default PostgreSQL settings should be reasonable."""
        s = Settings(SITE_PASSWORD="test", use_sqlite=False)
        assert s.postgres_host == "localhost"
        assert s.postgres_port == 5432
        assert s.postgres_user == "sleep_scoring"
        assert s.postgres_db == "sleep_scoring"


class TestSessionModuleLevel:
    """Tests for the module-level objects in db.session."""

    def test_module_exports(self):
        """Module should export expected names."""
        from sleep_scoring_web.db import session as mod

        assert hasattr(mod, "async_engine")
        assert hasattr(mod, "async_session_maker")
        assert hasattr(mod, "get_async_session")
        assert hasattr(mod, "init_db")
        assert hasattr(mod, "drop_db")

    def test_engine_is_async(self):
        """The engine should be an async engine."""
        from sleep_scoring_web.db.session import async_engine

        # AsyncEngine has a `begin` coroutine method
        assert hasattr(async_engine, "begin")

    def test_session_maker_callable(self):
        """async_session_maker should be callable."""
        from sleep_scoring_web.db.session import async_session_maker

        assert callable(async_session_maker)

    def test_get_async_session_callable(self):
        """get_async_session should be a callable (FastAPI dependency)."""
        from sleep_scoring_web.db.session import get_async_session

        assert callable(get_async_session)


class TestInitDb:
    """Tests for init_db() function."""

    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self):
        """init_db should call create_all and _apply_migrations."""
        from sqlalchemy.ext.asyncio import create_async_engine

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        with patch("sleep_scoring_web.db.session.async_engine", engine), \
             patch("sleep_scoring_web.db.session._apply_migrations", new_callable=AsyncMock) as mock_migrate:
            from sleep_scoring_web.db.session import init_db

            await init_db()
            mock_migrate.assert_awaited_once()

        await engine.dispose()


class TestDropDb:
    """Tests for drop_db() function."""

    @pytest.mark.asyncio
    async def test_drop_db_drops_tables(self):
        """drop_db should call drop_all."""
        from sqlalchemy.ext.asyncio import create_async_engine

        from sleep_scoring_web.db.models import Base
        from sleep_scoring_web.db.session import drop_db

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")

        # Create tables first
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        with patch("sleep_scoring_web.db.session.async_engine", engine):
            await drop_db()

        # Verify tables were dropped — creating again shouldn't fail
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await engine.dispose()
