"""
Database session management.

Provides async SQLAlchemy engine and session factory using db-toolkit.
"""

from __future__ import annotations

from db_toolkit import create_engine, create_get_db, create_session_maker
from sqlalchemy.ext.asyncio import create_async_engine as sa_create_async_engine

from sleep_scoring_web.config import settings

# Configure engine based on database type
if settings.use_sqlite:
    # SQLite configuration (for development)
    # db-toolkit handles SQLite specially (no pooling)
    async_engine = sa_create_async_engine(
        settings.database_url,
        echo=settings.sql_echo,
    )
    async_session_maker = create_session_maker(async_engine)
else:
    # PostgreSQL configuration (production)
    # Use sa_create_async_engine directly to disable pool_pre_ping
    # (saves one roundtrip per connection checkout; connections are local + stable)
    async_engine = sa_create_async_engine(
        settings.database_url,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        pool_pre_ping=False,
        echo=settings.sql_echo,
        # asyncpg: cache prepared statements for faster repeated queries
        connect_args={"prepared_statement_cache_size": 256},
    )
    async_session_maker = create_session_maker(async_engine)

# Create get_db dependency using db-toolkit
get_async_session = create_get_db(async_session_maker)

# Attach slow query profiler (opt-in via SLOW_QUERY_THRESHOLD_MS env var)
try:
    from sleep_scoring_web.middleware.query_profiler import install_query_profiler

    install_query_profiler(async_engine)
except Exception:
    pass


async def init_db() -> None:
    """Initialize database tables and apply schema migrations."""
    from sleep_scoring_web.db.models import Base

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Schema migrations for columns added after initial table creation.
    # create_all() won't add columns to existing tables.
    await _apply_migrations()


async def _apply_migrations() -> None:
    """Add missing columns to existing tables (idempotent)."""
    from sqlalchemy import text

    migrations = [
        # Added 2026-02: is_no_sleep flag for dates with no sleep
        (
            "user_annotations",
            "is_no_sleep",
            "ALTER TABLE user_annotations ADD COLUMN is_no_sleep BOOLEAN NOT NULL DEFAULT false",
        ),
        # Added 2026-02: Nap periods in diary
        ("diary_entries", "nap_1_start", "ALTER TABLE diary_entries ADD COLUMN nap_1_start VARCHAR(10)"),
        ("diary_entries", "nap_1_end", "ALTER TABLE diary_entries ADD COLUMN nap_1_end VARCHAR(10)"),
        ("diary_entries", "nap_2_start", "ALTER TABLE diary_entries ADD COLUMN nap_2_start VARCHAR(10)"),
        ("diary_entries", "nap_2_end", "ALTER TABLE diary_entries ADD COLUMN nap_2_end VARCHAR(10)"),
        ("diary_entries", "nap_3_start", "ALTER TABLE diary_entries ADD COLUMN nap_3_start VARCHAR(10)"),
        ("diary_entries", "nap_3_end", "ALTER TABLE diary_entries ADD COLUMN nap_3_end VARCHAR(10)"),
        # Added 2026-02: Nonwear periods in diary
        ("diary_entries", "nonwear_1_start", "ALTER TABLE diary_entries ADD COLUMN nonwear_1_start VARCHAR(10)"),
        ("diary_entries", "nonwear_1_end", "ALTER TABLE diary_entries ADD COLUMN nonwear_1_end VARCHAR(10)"),
        ("diary_entries", "nonwear_1_reason", "ALTER TABLE diary_entries ADD COLUMN nonwear_1_reason TEXT"),
        ("diary_entries", "nonwear_2_start", "ALTER TABLE diary_entries ADD COLUMN nonwear_2_start VARCHAR(10)"),
        ("diary_entries", "nonwear_2_end", "ALTER TABLE diary_entries ADD COLUMN nonwear_2_end VARCHAR(10)"),
        ("diary_entries", "nonwear_2_reason", "ALTER TABLE diary_entries ADD COLUMN nonwear_2_reason TEXT"),
        ("diary_entries", "nonwear_3_start", "ALTER TABLE diary_entries ADD COLUMN nonwear_3_start VARCHAR(10)"),
        ("diary_entries", "nonwear_3_end", "ALTER TABLE diary_entries ADD COLUMN nonwear_3_end VARCHAR(10)"),
        ("diary_entries", "nonwear_3_reason", "ALTER TABLE diary_entries ADD COLUMN nonwear_3_reason TEXT"),
        # Added 2026-02: needs_consensus flag for dates needing second-scorer review
        (
            "user_annotations",
            "needs_consensus",
            "ALTER TABLE user_annotations ADD COLUMN needs_consensus BOOLEAN NOT NULL DEFAULT false",
        ),
        # Added 2026-03: detection_rule per annotation and metric
        (
            "user_annotations",
            "detection_rule",
            "ALTER TABLE user_annotations ADD COLUMN detection_rule VARCHAR(100)",
        ),
        (
            "sleep_metrics",
            "detection_rule",
            "ALTER TABLE sleep_metrics ADD COLUMN detection_rule VARCHAR(100)",
        ),
    ]

    # Type migrations: change INTEGER columns to FLOAT (for GENEActiv float data)
    type_migrations = [
        # Added 2026-03: Float activity columns for raw accelerometer data (GENEActiv g-force values)
        ("raw_activity_data", "axis_x", "DOUBLE PRECISION"),
        ("raw_activity_data", "axis_y", "DOUBLE PRECISION"),
        ("raw_activity_data", "axis_z", "DOUBLE PRECISION"),
        ("raw_activity_data", "vector_magnitude", "DOUBLE PRECISION"),
    ]

    async with async_engine.begin() as conn:
        for table, column, ddl in migrations:
            # Check if column already exists (works for both PostgreSQL and SQLite)
            if settings.use_sqlite:
                result = await conn.execute(text(f"PRAGMA table_info({table})"))
                columns = [row[1] for row in result.fetchall()]
                exists = column in columns
            else:
                result = await conn.execute(
                    text("SELECT 1 FROM information_schema.columns WHERE table_name = :table AND column_name = :column"),
                    {"table": table, "column": column},
                )
                exists = result.fetchone() is not None

            if not exists:
                await conn.execute(text(ddl))

        # Add unique constraint on audit_log (session_id, sequence) for dedup.
        # create_all() adds it for new tables; this handles tables created before the constraint was added.
        if settings.use_sqlite:
            result = await conn.execute(text("PRAGMA index_list(audit_log)"))
            index_names = [row[1] for row in result.fetchall()]
            if "uq_audit_session_sequence" not in index_names:
                await conn.execute(text("CREATE UNIQUE INDEX uq_audit_session_sequence ON audit_log (session_id, sequence)"))
        else:
            result = await conn.execute(
                text(
                    "SELECT 1 FROM information_schema.table_constraints "
                    "WHERE constraint_name = 'uq_audit_session_sequence' AND table_name = 'audit_log'"
                )
            )
            if result.fetchone() is None:
                await conn.execute(text("ALTER TABLE audit_log ADD CONSTRAINT uq_audit_session_sequence UNIQUE (session_id, sequence)"))

        # Apply type migrations (INTEGER → FLOAT for GENEActiv g-force data)
        for table, column, new_type in type_migrations:
            if settings.use_sqlite:
                # SQLite doesn't support ALTER COLUMN TYPE, but its type system
                # is flexible — REAL/NUMERIC columns accept float values regardless
                # of declared type. No migration needed for SQLite.
                pass
            else:
                # PostgreSQL: check current type and alter if needed
                result = await conn.execute(
                    text("SELECT data_type FROM information_schema.columns WHERE table_name = :table AND column_name = :column"),
                    {"table": table, "column": column},
                )
                row = result.fetchone()
                if row and row[0] not in ("double precision", "real", "numeric"):
                    await conn.execute(text(f"ALTER TABLE {table} ALTER COLUMN {column} TYPE {new_type} USING {column}::double precision"))


async def drop_db() -> None:
    """Drop all database tables (use with caution)."""
    from sleep_scoring_web.db.models import Base

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
