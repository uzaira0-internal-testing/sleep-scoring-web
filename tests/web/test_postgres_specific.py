"""
PostgreSQL-specific integration tests using testcontainers.

Tests behavior that differs between SQLite and PostgreSQL:
- JSON column operations
- Strict type enforcement
- Concurrent write handling / unique constraints
- Timezone-aware datetime handling
- Large batch inserts
- CASCADE delete semantics
- Unique constraint violation error types

Requires Docker to be available. Run with:
    pytest tests/web/test_postgres_specific.py -m integration
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sleep_scoring_web.db.models import (
    Base,
    File,
    Marker,
    RawActivityData,
    SleepMetric,
    User,
    UserAnnotation,
)
from sleep_scoring_web.schemas.enums import (
    FileStatus,
    MarkerCategory,
    MarkerType,
    UserRole,
    VerificationStatus,
)

# ---------------------------------------------------------------------------
# Skip the entire module if Docker / testcontainers are unavailable
# ---------------------------------------------------------------------------
try:
    from testcontainers.postgres import PostgresContainer

    _HAS_TESTCONTAINERS = True
except ImportError:
    _HAS_TESTCONTAINERS = False

# Also verify Docker daemon is reachable at import time so we skip fast
_DOCKER_AVAILABLE = False
if _HAS_TESTCONTAINERS:
    try:
        import docker
        from docker.errors import DockerException

        docker.from_env().ping()
        _DOCKER_AVAILABLE = True
    except (ImportError, DockerException, ConnectionError, OSError) as exc:
        import warnings
        warnings.warn(f"Docker not available, skipping PostgreSQL tests: {exc}", stacklevel=1)
        _DOCKER_AVAILABLE = False

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _HAS_TESTCONTAINERS,
        reason="testcontainers[postgres] not installed",
    ),
    pytest.mark.skipif(
        not _DOCKER_AVAILABLE,
        reason="Docker daemon not available",
    ),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def postgres_container():
    """Spin up a PostgreSQL 16 container for the test module."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest_asyncio.fixture(scope="function")
async def pg_engine(postgres_container):
    """Create an async SQLAlchemy engine connected to the container."""
    sync_url = postgres_container.get_connection_url()
    async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(async_url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def pg_session_maker(pg_engine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to the per-test engine."""
    return async_sessionmaker(
        pg_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(scope="function")
async def pg_session(pg_session_maker) -> AsyncSession:
    """Provide a single session for simple tests."""
    async with pg_session_maker() as session:
        yield session


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_user(username: str = "testuser", role: UserRole = UserRole.ANNOTATOR) -> User:
    return User(username=username, role=role, is_active=True)


def _make_file(
    filename: str = "participant_001.csv",
    status: str = FileStatus.READY,
    uploaded_by: str = "testuser",
    metadata_json: dict[str, Any] | None = None,
) -> File:
    return File(
        filename=filename,
        file_type="csv",
        status=status,
        uploaded_by=uploaded_by,
        metadata_json=metadata_json,
    )


def _make_marker(
    file_id: int,
    analysis_date: date,
    *,
    category: str = MarkerCategory.SLEEP,
    marker_type: str = MarkerType.MAIN_SLEEP,
    start: float = 1704070800.0,
    end: float = 1704074400.0,
    period_index: int = 1,
    created_by: str = "testuser",
) -> Marker:
    return Marker(
        file_id=file_id,
        analysis_date=analysis_date,
        marker_category=category,
        marker_type=marker_type,
        start_timestamp=start,
        end_timestamp=end,
        period_index=period_index,
        created_by=created_by,
    )


# ---------------------------------------------------------------------------
# 1. JSON operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestJsonOperations:
    """PostgreSQL JSON/JSONB column operations that differ from SQLite."""

    async def test_annotation_json_round_trip(self, pg_session: AsyncSession) -> None:
        """Sleep markers stored as JSON in UserAnnotation must round-trip with
        full fidelity, including nested structures."""
        user = _make_user()
        pg_session.add(user)
        await pg_session.flush()

        file = _make_file()
        pg_session.add(file)
        await pg_session.flush()

        sleep_markers = [
            {
                "onset_timestamp": 1704070800.123,
                "offset_timestamp": 1704074400.456,
                "marker_type": "MAIN_SLEEP",
                "period_index": 1,
                "metadata": {"confidence": 0.95, "algorithm": "sadeh_1994"},
            },
            {
                "onset_timestamp": 1704085200.0,
                "offset_timestamp": 1704088800.0,
                "marker_type": "NAP",
                "period_index": 2,
                "metadata": None,
            },
        ]
        nonwear_markers = [
            {"start_timestamp": 1704100000.0, "end_timestamp": 1704103600.0},
        ]

        annotation = UserAnnotation(
            file_id=file.id,
            analysis_date=date(2024, 1, 1),
            username="testuser",
            sleep_markers_json=sleep_markers,
            nonwear_markers_json=nonwear_markers,
            is_no_sleep=False,
            needs_consensus=False,
            status=VerificationStatus.DRAFT,
        )
        pg_session.add(annotation)
        await pg_session.commit()

        # Re-fetch from DB
        result = await pg_session.execute(
            select(UserAnnotation).where(UserAnnotation.id == annotation.id)
        )
        loaded = result.scalar_one()

        assert loaded.sleep_markers_json == sleep_markers
        assert loaded.nonwear_markers_json == nonwear_markers
        # Verify nested dict survived
        assert loaded.sleep_markers_json[0]["metadata"]["confidence"] == 0.95
        assert loaded.sleep_markers_json[1]["metadata"] is None

    async def test_json_null_vs_empty_list(self, pg_session: AsyncSession) -> None:
        """PostgreSQL correctly distinguishes JSON null from empty array []."""
        file = _make_file(filename="json_null_test.csv")
        pg_session.add(file)
        await pg_session.flush()

        # Annotation with NULL json
        ann_null = UserAnnotation(
            file_id=file.id,
            analysis_date=date(2024, 1, 1),
            username="user_null",
            sleep_markers_json=None,
            is_no_sleep=False,
            needs_consensus=False,
            status=VerificationStatus.DRAFT,
        )
        # Annotation with empty list
        ann_empty = UserAnnotation(
            file_id=file.id,
            analysis_date=date(2024, 1, 2),
            username="user_empty",
            sleep_markers_json=[],
            is_no_sleep=False,
            needs_consensus=False,
            status=VerificationStatus.DRAFT,
        )
        pg_session.add_all([ann_null, ann_empty])
        await pg_session.commit()

        result = await pg_session.execute(
            select(UserAnnotation).order_by(UserAnnotation.analysis_date)
        )
        rows = result.scalars().all()
        assert rows[0].sleep_markers_json is None
        assert rows[1].sleep_markers_json == []

    async def test_file_metadata_json_query(self, pg_session: AsyncSession) -> None:
        """Verify that JSON metadata stored on File can be persisted and retrieved."""
        metadata = {
            "device": "ActiGraph GT3X+",
            "firmware": "3.2.1",
            "epoch_length": 60,
            "axes": ["x", "y", "z"],
            "settings": {"filter": "normal", "sample_rate": 100},
        }
        file = _make_file(filename="metadata_query.csv", metadata_json=metadata)
        pg_session.add(file)
        await pg_session.commit()

        result = await pg_session.execute(select(File).where(File.id == file.id))
        loaded = result.scalar_one()
        assert loaded.metadata_json == metadata
        assert loaded.metadata_json["settings"]["sample_rate"] == 100


# ---------------------------------------------------------------------------
# 2. Type enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTypeEnforcement:
    """PostgreSQL enforces types more strictly than SQLite."""

    async def test_string_length_enforcement(self, pg_session: AsyncSession) -> None:
        """PostgreSQL enforces VARCHAR(N) length limits; SQLite does not."""
        # Username column is String(100) — inserting >100 chars should fail
        long_username = "a" * 150
        user = User(username=long_username, role=UserRole.ANNOTATOR, is_active=True)
        pg_session.add(user)
        with pytest.raises(Exception):
            # PostgreSQL raises DataError for value too long
            await pg_session.commit()
        await pg_session.rollback()

    async def test_not_null_enforcement(self, pg_session: AsyncSession) -> None:
        """NOT NULL columns must reject None values at the database level."""
        # Marker.file_id is non-nullable
        marker = Marker(
            file_id=None,  # type: ignore[arg-type]
            analysis_date=date(2024, 1, 1),
            marker_category=MarkerCategory.SLEEP,
            marker_type=MarkerType.MAIN_SLEEP,
            start_timestamp=1704070800.0,
            end_timestamp=1704074400.0,
            period_index=1,
            created_by="testuser",
        )
        pg_session.add(marker)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
        await pg_session.rollback()

    async def test_foreign_key_enforcement(self, pg_session: AsyncSession) -> None:
        """PostgreSQL enforces foreign key constraints strictly."""
        # Insert a marker referencing a non-existent file_id
        marker = Marker(
            file_id=99999,
            analysis_date=date(2024, 1, 1),
            marker_category=MarkerCategory.SLEEP,
            marker_type=MarkerType.MAIN_SLEEP,
            start_timestamp=1704070800.0,
            end_timestamp=1704074400.0,
            period_index=1,
            created_by="testuser",
        )
        pg_session.add(marker)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
        await pg_session.rollback()


# ---------------------------------------------------------------------------
# 3. Concurrent writes / unique constraint behavior
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConcurrentWrites:
    """Concurrent marker saves to the same file/date — unique constraint behavior."""

    async def test_concurrent_marker_same_user_same_period(
        self, pg_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Two sessions inserting the same (file, date, user, category, period)
        must result in exactly one row; the second must raise IntegrityError."""
        # Setup: create file in a shared session
        async with pg_session_maker() as setup_session:
            file = _make_file(filename="concurrent_test.csv")
            setup_session.add(file)
            await setup_session.commit()
            file_id = file.id

        analysis = date(2024, 1, 1)

        # Session A inserts first
        async with pg_session_maker() as session_a:
            marker_a = _make_marker(file_id, analysis, period_index=1, created_by="userA")
            session_a.add(marker_a)
            await session_a.commit()

        # Session B inserts same unique key — must fail
        async with pg_session_maker() as session_b:
            marker_b = _make_marker(file_id, analysis, period_index=1, created_by="userA")
            session_b.add(marker_b)
            with pytest.raises(IntegrityError):
                await session_b.commit()
            await session_b.rollback()

    async def test_concurrent_marker_different_users_same_period(
        self, pg_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Two different users can each insert a marker at the same period_index
        because the unique constraint includes created_by."""
        async with pg_session_maker() as setup_session:
            file = _make_file(filename="concurrent_diff_users.csv")
            setup_session.add(file)
            await setup_session.commit()
            file_id = file.id

        analysis = date(2024, 1, 1)

        async with pg_session_maker() as session_a:
            marker_a = _make_marker(file_id, analysis, period_index=1, created_by="alice")
            session_a.add(marker_a)
            await session_a.commit()

        async with pg_session_maker() as session_b:
            marker_b = _make_marker(file_id, analysis, period_index=1, created_by="bob")
            session_b.add(marker_b)
            await session_b.commit()  # Should succeed — different user

        # Verify both exist
        async with pg_session_maker() as verify_session:
            result = await verify_session.execute(
                select(Marker).where(Marker.file_id == file_id)
            )
            markers = result.scalars().all()
            assert len(markers) == 2
            users = {m.created_by for m in markers}
            assert users == {"alice", "bob"}

    async def test_truly_concurrent_inserts(
        self, pg_session_maker: async_sessionmaker[AsyncSession]
    ) -> None:
        """Fire two inserts concurrently using asyncio.gather; one must succeed
        and the other must fail due to the unique constraint."""
        async with pg_session_maker() as setup_session:
            file = _make_file(filename="truly_concurrent.csv")
            setup_session.add(file)
            await setup_session.commit()
            file_id = file.id

        analysis = date(2024, 1, 1)
        results: list[str] = []

        async def insert_marker(label: str) -> None:
            async with pg_session_maker() as session:
                marker = _make_marker(
                    file_id, analysis, period_index=1, created_by="same_user"
                )
                session.add(marker)
                try:
                    await session.commit()
                    results.append(f"{label}:ok")
                except IntegrityError:
                    await session.rollback()
                    results.append(f"{label}:conflict")

        await asyncio.gather(insert_marker("A"), insert_marker("B"))

        ok_count = sum(1 for r in results if r.endswith(":ok"))
        conflict_count = sum(1 for r in results if r.endswith(":conflict"))
        assert ok_count == 1, f"Exactly one insert should succeed, got results: {results}"
        assert conflict_count == 1, f"Exactly one insert should conflict, got results: {results}"


# ---------------------------------------------------------------------------
# 4. Date/timestamp handling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDateTimestampHandling:
    """PostgreSQL timezone-aware datetime handling differs from SQLite."""

    async def test_timezone_aware_datetime_stored(self, pg_session: AsyncSession) -> None:
        """DateTime(timezone=True) columns should preserve timezone info in PostgreSQL."""
        user = User(
            username="tz_test_user",
            role=UserRole.ANNOTATOR,
            is_active=True,
        )
        pg_session.add(user)
        await pg_session.commit()

        result = await pg_session.execute(
            select(User).where(User.username == "tz_test_user")
        )
        loaded = result.scalar_one()
        # created_at uses server_default=func.now() with timezone=True
        assert loaded.created_at is not None
        # PostgreSQL returns timezone-aware datetimes
        assert loaded.created_at.tzinfo is not None

    async def test_date_column_rejects_datetime(self, pg_session: AsyncSession) -> None:
        """Date columns in PostgreSQL accept date objects; verify correct storage."""
        file = _make_file(filename="date_col_test.csv")
        pg_session.add(file)
        await pg_session.flush()

        analysis = date(2024, 6, 15)
        marker = _make_marker(file.id, analysis, period_index=1)
        pg_session.add(marker)
        await pg_session.commit()

        result = await pg_session.execute(
            select(Marker.analysis_date).where(Marker.file_id == file.id)
        )
        stored_date = result.scalar_one()
        assert stored_date == date(2024, 6, 15)
        # Should be a date, not a datetime
        assert isinstance(stored_date, date)

    async def test_server_default_now_generates_timestamp(
        self, pg_session: AsyncSession
    ) -> None:
        """server_default=func.now() should generate a timestamp on INSERT in PostgreSQL."""
        file = _make_file(filename="server_default_test.csv")
        pg_session.add(file)
        await pg_session.commit()

        result = await pg_session.execute(select(File).where(File.id == file.id))
        loaded = result.scalar_one()
        assert loaded.uploaded_at is not None
        # Verify it's reasonably recent (within last minute)
        now = datetime.now(timezone.utc)
        delta = now - loaded.uploaded_at.replace(tzinfo=timezone.utc)
        assert delta.total_seconds() < 60

    async def test_multiple_dates_ordering(self, pg_session: AsyncSession) -> None:
        """Verify DATE column sorts correctly across month/year boundaries."""
        file = _make_file(filename="date_ordering.csv")
        pg_session.add(file)
        await pg_session.flush()

        dates = [date(2024, 12, 31), date(2024, 1, 1), date(2025, 1, 1), date(2023, 6, 15)]
        for i, d in enumerate(dates):
            marker = _make_marker(
                file.id, d, period_index=i + 1, created_by=f"user_{i}"
            )
            pg_session.add(marker)
        await pg_session.commit()

        result = await pg_session.execute(
            select(Marker.analysis_date)
            .where(Marker.file_id == file.id)
            .order_by(Marker.analysis_date)
        )
        sorted_dates = [row[0] for row in result.all()]
        assert sorted_dates == sorted(dates)


# ---------------------------------------------------------------------------
# 5. Large batch insert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLargeBatchInsert:
    """Insert 1440 activity data rows (full 24h at 1-min epochs) and verify."""

    async def test_full_day_activity_insert(self, pg_session: AsyncSession) -> None:
        """Insert 1440 rows of RawActivityData and verify count + ordering."""
        file = _make_file(filename="full_day_batch.csv")
        pg_session.add(file)
        await pg_session.flush()

        base_time = datetime(2024, 1, 1, 0, 0, 0)
        rows: list[RawActivityData] = []
        for i in range(1440):
            ts = datetime(
                2024, 1, 1,
                i // 60,
                i % 60,
                0,
            )
            rows.append(
                RawActivityData(
                    file_id=file.id,
                    timestamp=ts,
                    epoch_index=i,
                    axis_x=float(i % 100),
                    axis_y=float((i * 2) % 150),
                    axis_z=float((i * 3) % 200),
                    vector_magnitude=float(i * 4),
                )
            )

        pg_session.add_all(rows)
        await pg_session.commit()

        # Verify count
        result = await pg_session.execute(
            select(RawActivityData)
            .where(RawActivityData.file_id == file.id)
            .order_by(RawActivityData.epoch_index)
        )
        all_rows = result.scalars().all()
        assert len(all_rows) == 1440

        # Verify ordering
        assert all_rows[0].epoch_index == 0
        assert all_rows[-1].epoch_index == 1439

        # Verify data integrity at specific points
        row_100 = all_rows[100]
        assert row_100.epoch_index == 100
        assert row_100.axis_x == 0.0  # 100 % 100
        assert row_100.axis_y == 50.0  # (100*2) % 150
        assert row_100.vector_magnitude == 400.0  # 100 * 4

    async def test_batch_insert_with_nulls(self, pg_session: AsyncSession) -> None:
        """Activity rows with NULL axis values should be stored correctly."""
        file = _make_file(filename="batch_nulls.csv")
        pg_session.add(file)
        await pg_session.flush()

        rows = []
        for i in range(100):
            rows.append(
                RawActivityData(
                    file_id=file.id,
                    timestamp=datetime(2024, 1, 1, i // 60, i % 60, 0),
                    epoch_index=i,
                    axis_x=float(i) if i % 2 == 0 else None,
                    axis_y=float(i) if i % 3 == 0 else None,
                    axis_z=None,
                    vector_magnitude=float(i),
                )
            )
        pg_session.add_all(rows)
        await pg_session.commit()

        result = await pg_session.execute(
            select(RawActivityData).where(RawActivityData.file_id == file.id)
        )
        all_rows = result.scalars().all()
        assert len(all_rows) == 100

        # Verify nulls are actually None, not 0
        row_1 = next(r for r in all_rows if r.epoch_index == 1)
        assert row_1.axis_x is None  # odd index
        assert row_1.axis_z is None


# ---------------------------------------------------------------------------
# 6. CASCADE delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCascadeDelete:
    """Deleting a File must cascade-delete all related data."""

    async def test_cascade_deletes_all_related_data(
        self, pg_session: AsyncSession
    ) -> None:
        """When a File row is deleted, all activity data, markers, annotations,
        and metrics referencing it must also be deleted (ON DELETE CASCADE)."""
        # Create file
        file = _make_file(filename="cascade_test.csv")
        pg_session.add(file)
        await pg_session.flush()
        file_id = file.id

        analysis = date(2024, 1, 1)

        # Add activity data
        for i in range(10):
            pg_session.add(
                RawActivityData(
                    file_id=file_id,
                    timestamp=datetime(2024, 1, 1, i // 60, i % 60, 0),
                    epoch_index=i,
                    axis_y=float(i),
                )
            )

        # Add marker
        pg_session.add(
            _make_marker(file_id, analysis, period_index=1, created_by="testuser")
        )

        # Add annotation
        pg_session.add(
            UserAnnotation(
                file_id=file_id,
                analysis_date=analysis,
                username="testuser",
                sleep_markers_json=[{"onset": 100.0, "offset": 200.0}],
                is_no_sleep=False,
                needs_consensus=False,
                status=VerificationStatus.DRAFT,
            )
        )

        # Add metric
        pg_session.add(
            SleepMetric(
                file_id=file_id,
                analysis_date=analysis,
                period_index=0,
                total_sleep_time_minutes=420.0,
                sleep_efficiency=85.5,
                verification_status=VerificationStatus.DRAFT,
            )
        )

        await pg_session.commit()

        # Verify all data exists
        act_count = await pg_session.execute(
            select(RawActivityData).where(RawActivityData.file_id == file_id)
        )
        assert len(act_count.scalars().all()) == 10

        marker_count = await pg_session.execute(
            select(Marker).where(Marker.file_id == file_id)
        )
        assert len(marker_count.scalars().all()) == 1

        ann_count = await pg_session.execute(
            select(UserAnnotation).where(UserAnnotation.file_id == file_id)
        )
        assert len(ann_count.scalars().all()) == 1

        metric_count = await pg_session.execute(
            select(SleepMetric).where(SleepMetric.file_id == file_id)
        )
        assert len(metric_count.scalars().all()) == 1

        # Delete the file
        await pg_session.delete(file)
        await pg_session.commit()

        # Verify everything is gone
        for model in (RawActivityData, Marker, UserAnnotation, SleepMetric):
            result = await pg_session.execute(
                select(model).where(model.file_id == file_id)  # type: ignore[attr-defined]
            )
            assert result.scalars().all() == [], (
                f"{model.__tablename__} rows should have been cascade-deleted"
            )

        # File itself should also be gone
        file_result = await pg_session.execute(select(File).where(File.id == file_id))
        assert file_result.scalar_one_or_none() is None

    async def test_cascade_does_not_affect_other_files(
        self, pg_session: AsyncSession
    ) -> None:
        """Deleting one file must not touch data belonging to other files."""
        file_a = _make_file(filename="cascade_file_a.csv")
        file_b = _make_file(filename="cascade_file_b.csv")
        pg_session.add_all([file_a, file_b])
        await pg_session.flush()

        analysis = date(2024, 1, 1)

        # Both files get activity data and markers
        for f in (file_a, file_b):
            for i in range(5):
                pg_session.add(
                    RawActivityData(
                        file_id=f.id,
                        timestamp=datetime(2024, 1, 1, i // 60, i % 60, 0),
                        epoch_index=i,
                        axis_y=float(i),
                    )
                )
            pg_session.add(
                _make_marker(f.id, analysis, period_index=1, created_by="testuser")
            )
        await pg_session.commit()

        file_a_id = file_a.id
        file_b_id = file_b.id

        # Delete file A
        await pg_session.delete(file_a)
        await pg_session.commit()

        # File B data must be untouched
        result_b_act = await pg_session.execute(
            select(RawActivityData).where(RawActivityData.file_id == file_b_id)
        )
        assert len(result_b_act.scalars().all()) == 5

        result_b_markers = await pg_session.execute(
            select(Marker).where(Marker.file_id == file_b_id)
        )
        assert len(result_b_markers.scalars().all()) == 1

        # File A data must be gone
        result_a_act = await pg_session.execute(
            select(RawActivityData).where(RawActivityData.file_id == file_a_id)
        )
        assert len(result_a_act.scalars().all()) == 0


# ---------------------------------------------------------------------------
# 7. Unique constraint violations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUniqueConstraintViolations:
    """Verify unique constraints are enforced at the database level."""

    async def test_duplicate_filename_rejected(self, pg_session: AsyncSession) -> None:
        """File.filename has a unique constraint — duplicates must raise IntegrityError."""
        file_1 = _make_file(filename="unique_test.csv")
        pg_session.add(file_1)
        await pg_session.commit()

        file_2 = _make_file(filename="unique_test.csv")
        pg_session.add(file_2)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
        await pg_session.rollback()

    async def test_duplicate_username_rejected(self, pg_session: AsyncSession) -> None:
        """User.username has a unique constraint — duplicates must raise IntegrityError."""
        user_1 = _make_user(username="unique_user")
        pg_session.add(user_1)
        await pg_session.commit()

        user_2 = _make_user(username="unique_user")
        pg_session.add(user_2)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
        await pg_session.rollback()

    async def test_duplicate_annotation_file_date_user_rejected(
        self, pg_session: AsyncSession
    ) -> None:
        """UserAnnotation has a unique index on (file_id, analysis_date, username).
        Duplicates must raise IntegrityError."""
        file = _make_file(filename="dup_annotation.csv")
        pg_session.add(file)
        await pg_session.flush()

        ann_1 = UserAnnotation(
            file_id=file.id,
            analysis_date=date(2024, 1, 1),
            username="scorer1",
            is_no_sleep=False,
            needs_consensus=False,
            status=VerificationStatus.DRAFT,
        )
        pg_session.add(ann_1)
        await pg_session.commit()

        ann_2 = UserAnnotation(
            file_id=file.id,
            analysis_date=date(2024, 1, 1),
            username="scorer1",
            is_no_sleep=True,
            needs_consensus=False,
            status=VerificationStatus.SUBMITTED,
        )
        pg_session.add(ann_2)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
        await pg_session.rollback()

    async def test_same_user_different_dates_allowed(
        self, pg_session: AsyncSession
    ) -> None:
        """Same user can annotate the same file on different dates."""
        file = _make_file(filename="multi_date_ann.csv")
        pg_session.add(file)
        await pg_session.flush()

        for d in [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]:
            pg_session.add(
                UserAnnotation(
                    file_id=file.id,
                    analysis_date=d,
                    username="scorer1",
                    is_no_sleep=False,
                    needs_consensus=False,
                    status=VerificationStatus.DRAFT,
                )
            )
        await pg_session.commit()

        result = await pg_session.execute(
            select(UserAnnotation).where(UserAnnotation.file_id == file.id)
        )
        assert len(result.scalars().all()) == 3

    async def test_marker_unique_constraint_composite(
        self, pg_session: AsyncSession
    ) -> None:
        """Marker unique constraint: (file_id, analysis_date, created_by,
        marker_category, period_index). Same combo must fail; different
        period_index must succeed."""
        file = _make_file(filename="marker_uq_composite.csv")
        pg_session.add(file)
        await pg_session.flush()
        file_id = file.id  # capture before rollback expires the object

        analysis = date(2024, 1, 1)

        # First marker — period 1
        m1 = _make_marker(file_id, analysis, period_index=1, created_by="scorer1")
        pg_session.add(m1)
        await pg_session.commit()

        # Same composite key — must fail
        m2 = _make_marker(file_id, analysis, period_index=1, created_by="scorer1")
        pg_session.add(m2)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
        await pg_session.rollback()

        # Different period_index — must succeed
        m3 = _make_marker(
            file_id,
            analysis,
            period_index=2,
            created_by="scorer1",
            category=MarkerCategory.SLEEP,
            marker_type=MarkerType.NAP,
        )
        pg_session.add(m3)
        await pg_session.commit()

        result = await pg_session.execute(
            select(Marker).where(Marker.file_id == file_id)
        )
        assert len(result.scalars().all()) == 2

    async def test_sleep_metric_unique_constraint(
        self, pg_session: AsyncSession
    ) -> None:
        """SleepMetric has a unique index on (file_id, analysis_date, period_index,
        scored_by). Duplicates must fail."""
        file = _make_file(filename="metric_uq.csv")
        pg_session.add(file)
        await pg_session.flush()

        analysis = date(2024, 1, 1)

        sm1 = SleepMetric(
            file_id=file.id,
            analysis_date=analysis,
            period_index=0,
            scored_by="scorer1",
            total_sleep_time_minutes=420.0,
            verification_status=VerificationStatus.DRAFT,
        )
        pg_session.add(sm1)
        await pg_session.commit()

        sm2 = SleepMetric(
            file_id=file.id,
            analysis_date=analysis,
            period_index=0,
            scored_by="scorer1",
            total_sleep_time_minutes=400.0,
            verification_status=VerificationStatus.SUBMITTED,
        )
        pg_session.add(sm2)
        with pytest.raises(IntegrityError):
            await pg_session.flush()
        await pg_session.rollback()
