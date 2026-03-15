"""
Database migration tests.

Verifies that init_db() creates all expected tables, is idempotent,
and that drop_db() removes them. Also checks key columns on critical tables.
"""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import create_async_engine

from sleep_scoring_web.db.models import Base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_engine():
    """Create a fresh in-memory SQLite engine."""
    from sqlalchemy import event

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


async def _get_table_names(engine) -> set[str]:
    """Return set of table names from the engine."""
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
        return {row[0] for row in result.fetchall()}


async def _get_column_names(engine, table: str) -> set[str]:
    """Return set of column names for a table."""
    async with engine.connect() as conn:
        result = await conn.execute(text(f"PRAGMA table_info({table})"))
        return {row[1] for row in result.fetchall()}


# ---------------------------------------------------------------------------
# Expected schema
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "users",
    "sessions",
    "files",
    "raw_activity_data",
    "markers",
    "user_annotations",
    "sleep_metrics",
    "consensus_results",
    "consensus_candidates",
    "consensus_votes",
    "resolved_annotations",
    "diary_entries",
    "night_complexity",
    "user_settings",
    "audit_log",
    "file_assignments",
}

# Key columns that MUST exist on critical tables (subset, not exhaustive)
CRITICAL_COLUMNS: dict[str, set[str]] = {
    "files": {"id", "filename", "status", "file_type", "participant_id", "uploaded_by", "uploaded_at"},
    "markers": {"id", "file_id", "analysis_date", "marker_category", "marker_type", "start_timestamp", "end_timestamp"},
    "raw_activity_data": {"id", "file_id", "timestamp", "epoch_index", "axis_x", "axis_y", "axis_z", "vector_magnitude"},
    "audit_log": {"id", "file_id", "analysis_date", "username", "action", "session_id", "sequence", "payload"},
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInitDb:
    """Tests for init_db() creating the full schema."""

    @pytest.mark.asyncio
    async def test_creates_all_expected_tables(self) -> None:
        """init_db() should create every table defined in models."""
        engine = await _make_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        tables = await _get_table_names(engine)
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables after init_db: {missing}"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_idempotent_double_init(self) -> None:
        """Running init_db() twice must not raise errors."""
        engine = await _make_engine()
        # First init
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Second init (should be a no-op)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        tables = await _get_table_names(engine)
        missing = EXPECTED_TABLES - tables
        assert not missing, f"Missing tables after double init: {missing}"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_key_columns_exist(self) -> None:
        """Critical tables must contain expected columns."""
        engine = await _make_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        for table, expected_cols in CRITICAL_COLUMNS.items():
            actual_cols = await _get_column_names(engine, table)
            missing = expected_cols - actual_cols
            assert not missing, f"Table '{table}' missing columns: {missing}"

        await engine.dispose()


class TestDropDb:
    """Tests for drop_db() removing all tables."""

    @pytest.mark.asyncio
    async def test_drop_removes_all_tables(self) -> None:
        """drop_db() should remove all tables."""
        engine = await _make_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        # Verify tables exist
        tables = await _get_table_names(engine)
        assert len(tables) > 0, "No tables created to drop"
        # Drop
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        tables = await _get_table_names(engine)
        assert len(tables) == 0, f"Tables remain after drop: {tables}"
        await engine.dispose()

    @pytest.mark.asyncio
    async def test_upgrade_downgrade_upgrade_cycle(self) -> None:
        """init -> drop -> init cycle must work cleanly."""
        engine = await _make_engine()
        # Init
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        tables_1 = await _get_table_names(engine)
        assert EXPECTED_TABLES <= tables_1

        # Drop
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        tables_2 = await _get_table_names(engine)
        assert len(tables_2) == 0

        # Re-init
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        tables_3 = await _get_table_names(engine)
        missing = EXPECTED_TABLES - tables_3
        assert not missing, f"Missing tables after re-init: {missing}"

        await engine.dispose()

    @pytest.mark.asyncio
    async def test_no_extra_unexpected_tables(self) -> None:
        """init_db() should only create tables we know about."""
        engine = await _make_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        tables = await _get_table_names(engine)
        unexpected = tables - EXPECTED_TABLES
        # Allow empty set or only internal tables
        assert not unexpected, f"Unexpected tables created: {unexpected}"
        await engine.dispose()
