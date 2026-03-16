"""
Pytest fixtures for Sleep Scoring Web API tests.

Provides test client, test database, and test user fixtures.
Uses httpx for async testing with FastAPI.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
from collections.abc import AsyncGenerator, Generator
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from sleep_scoring_web.db.models import Base, User
from sleep_scoring_web.main import app
from sleep_scoring_web.schemas.enums import MarkerType


@pytest.fixture(scope="session", autouse=True)
def _patch_settings_dirs() -> Generator[None, None, None]:
    """Patch settings directories to temp paths BEFORE any lifespan code runs.

    Uses environment variables so the patch survives ``get_settings.cache_clear()``
    (which test_schema_fuzzing.py calls at module level).  Env vars are read
    fresh each time Settings() is instantiated, making this approach robust
    against cache invalidation.
    """
    _tmp_uploads = tempfile.mkdtemp(prefix="test_session_uploads_")
    _tmp_tus = tempfile.mkdtemp(prefix="test_session_tus_")
    _tmp_data = tempfile.mkdtemp(prefix="test_session_data_")

    original_env = {
        "UPLOAD_DIR": os.environ.get("UPLOAD_DIR"),
        "TUS_UPLOAD_DIR": os.environ.get("TUS_UPLOAD_DIR"),
        "DATA_DIR": os.environ.get("DATA_DIR"),
    }

    os.environ["UPLOAD_DIR"] = _tmp_uploads
    os.environ["TUS_UPLOAD_DIR"] = _tmp_tus
    os.environ["DATA_DIR"] = _tmp_data

    # Also patch the current settings object if already cached
    try:
        from sleep_scoring_web.config import get_settings
        settings = get_settings()
        settings.upload_dir = _tmp_uploads
        settings.tus_upload_dir = _tmp_tus
        settings.data_dir = _tmp_data
    except Exception:  # noqa: BLE001
        pass

    yield

    # Restore original env vars
    for key, val in original_env.items():
        if val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = val

    shutil.rmtree(_tmp_uploads, ignore_errors=True)
    shutil.rmtree(_tmp_tus, ignore_errors=True)
    shutil.rmtree(_tmp_data, ignore_errors=True)


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    """Create a test database engine using in-memory SQLite."""
    from sqlalchemy import event

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        future=True,
    )

    # Enable foreign key enforcement (SQLite has it OFF by default)
    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Cleanup
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session_maker(test_engine):
    """Create a session maker for the test database."""
    return async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


@pytest_asyncio.fixture(scope="function")
async def test_session(test_session_maker) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session."""
    async with test_session_maker() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def setup_db(test_session_maker):
    """Override the database session dependency and set up test users.

    Also patches the module-level async_session_maker so that background
    tasks (_update_user_annotation, _calculate_and_store_metrics) use
    the test database instead of the production one.
    """
    import sleep_scoring_web.db.session as session_module

    from sleep_scoring_web.api.deps import get_db
    from sleep_scoring_web.db.models import UserRole

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with test_session_maker() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    # Patch the module-level session maker used by background tasks
    original_session_maker = session_module.async_session_maker
    session_module.async_session_maker = test_session_maker

    # Ensure test admin username is recognized as admin by the settings
    from sleep_scoring_web.config import get_settings
    settings = get_settings()

    # Override upload directories to use temp paths (avoids /app requirement)
    import shutil
    import tempfile
    original_upload_dir = settings.upload_dir
    original_tus_dir = settings.tus_upload_dir
    original_admin_usernames = settings.ADMIN_USERNAMES
    _tmp_uploads = tempfile.mkdtemp(prefix="test_uploads_")
    _tmp_tus = tempfile.mkdtemp(prefix="test_tus_")
    settings.upload_dir = _tmp_uploads
    settings.tus_upload_dir = _tmp_tus
    if "testadmin" not in settings.admin_usernames_list:
        settings.ADMIN_USERNAMES = f"{settings.ADMIN_USERNAMES},testadmin"
        # Clear cached property so it rebuilds with new value
        if "admin_usernames_list" in settings.__dict__:
            del settings.__dict__["admin_usernames_list"]

    # Create test users (site password auth - no hashed passwords)
    async with test_session_maker() as session:
        admin_user = User(
            username="testadmin",
            role=UserRole.ADMIN,
            is_active=True,
        )
        annotator_user = User(
            username="testannotator",
            role=UserRole.ANNOTATOR,
            is_active=True,
        )
        session.add(admin_user)
        session.add(annotator_user)
        await session.commit()

    yield

    app.dependency_overrides.clear()
    session_module.async_session_maker = original_session_maker
    settings.upload_dir = original_upload_dir
    settings.tus_upload_dir = original_tus_dir
    settings.ADMIN_USERNAMES = original_admin_usernames
    if "admin_usernames_list" in settings.__dict__:
        del settings.__dict__["admin_usernames_list"]
    shutil.rmtree(_tmp_uploads, ignore_errors=True)
    shutil.rmtree(_tmp_tus, ignore_errors=True)


@pytest_asyncio.fixture(scope="function")
async def client(setup_db) -> AsyncGenerator[AsyncClient, None]:
    """Create an async HTTP client for testing."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def admin_auth_headers() -> dict[str, str]:
    """Get auth headers for admin user (site password auth)."""
    return {"X-Username": "testadmin", "X-Site-Password": "testpass"}


@pytest_asyncio.fixture(scope="function")
async def annotator_auth_headers() -> dict[str, str]:
    """Get auth headers for annotator user (site password auth)."""
    return {"X-Username": "testannotator", "X-Site-Password": "testpass"}


@pytest_asyncio.fixture(scope="function")
async def test_admin_user(setup_db, test_session_maker) -> User:
    """Get the test admin user."""
    from sqlalchemy import select

    async with test_session_maker() as session:
        result = await session.execute(select(User).where(User.username == "testadmin"))
        return result.scalar_one()


@pytest_asyncio.fixture(scope="function")
async def test_annotator_user(setup_db, test_session_maker) -> User:
    """Get the test annotator user."""
    from sqlalchemy import select

    async with test_session_maker() as session:
        result = await session.execute(select(User).where(User.username == "testannotator"))
        return result.scalar_one()


@pytest.fixture(scope="session")
def sample_csv_content() -> str:
    """
    Generate sample CSV content for testing.

    Mimics ActiGraph format with 10 header rows followed by data.
    The loader skips the first 10 rows by default.
    """
    import datetime

    # ActiGraph-style header rows (10 rows)
    # Data starts at noon so it falls within the noon-to-noon view window
    # that the activity and scoring endpoints use.
    lines = [
        "------------ Data File Created By ActiGraph GT3X+ ActiLife v6.13.4 Firmware v3.2.1 date format M/d/yyyy Filter Normal -----------",
        "Serial Number: NEO1F00000000",
        "Start Time 12:00:00",
        "Start Date 1/1/2024",
        "Epoch Period (hh:mm:ss) 00:01:00",
        "Download Time 12:00:00",
        "Download Date 1/2/2024",
        "Current Memory Address: 0",
        "Current Battery Voltage: 4.20     Mode = 12",
        "--------------------------------------------------",
        # Row 11 is the actual header (skipped rows = 10)
        "Date,Time,Axis1,Axis2,Axis3,Vector Magnitude",
    ]

    # Generate 100 rows of sample data starting at noon
    base_time = datetime.datetime(2024, 1, 1, 12, 0, 0)
    for i in range(100):
        ts = base_time + datetime.timedelta(seconds=60 * i)
        date_str = ts.strftime("%m/%d/%Y")
        time_str = ts.strftime("%H:%M:%S")
        # Axis1 = Y (activity), Axis2 = X, Axis3 = Z
        lines.append(f"{date_str},{time_str},{(i * 2) % 150},{i % 100},{(i * 3) % 200},{i * 4}")

    return "\n".join(lines)


@pytest.fixture
def temp_csv_file(tmp_path: Path, sample_csv_content: str) -> Path:
    """Create a temporary CSV file for testing."""
    csv_path = tmp_path / "test_data.csv"
    csv_path.write_text(sample_csv_content)
    return csv_path


# =============================================================================
# Shared test helpers (used across multiple test files)
# =============================================================================

async def upload_and_get_date(
    client,
    auth_headers: dict[str, str],
    csv_content: str,
    filename: str | None = None,
    wait_ready: bool = True,
) -> tuple[int, str]:
    """Upload a CSV file and return (file_id, first_available_date).

    Args:
        client: httpx AsyncClient
        auth_headers: auth headers dict
        csv_content: CSV content string
        filename: optional filename (auto-generated if None)
        wait_ready: if True, poll until file status is "ready"

    Returns:
        (file_id, analysis_date) tuple
    """
    import asyncio
    import io
    import uuid

    if filename is None:
        filename = f"test_{uuid.uuid4().hex[:8]}.csv"

    files = {"file": (filename, io.BytesIO(csv_content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", files=files, headers=auth_headers)
    assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
    upload_data = resp.json()
    file_id = upload_data["file_id"]

    # The upload endpoint processes synchronously and returns status in the
    # response.  Verify the file reached "ready" status immediately.
    if wait_ready:
        assert upload_data.get("status") == "ready", (
            f"File {file_id} did not reach 'ready' status after upload: {upload_data}"
        )

    dates_resp = await client.get(
        f"/api/v1/files/{file_id}/dates", headers=auth_headers
    )
    dates = dates_resp.json()
    assert dates, f"No dates available for file {file_id}"
    return file_id, dates[0]


def make_sleep_marker(
    onset: float = 1704110400.0,
    offset: float = 1704135600.0,
    marker_type: str = MarkerType.MAIN_SLEEP,
    period_index: int = 0,
) -> dict:
    """Build a sleep marker dict for test payloads.

    Note: The SleepPeriod schema uses ``marker_index`` (not ``period_index``)
    as the field name.  We map ``period_index`` -> ``marker_index`` here so
    callers can use the more intuitive name.
    """
    return {
        "onset_timestamp": onset,
        "offset_timestamp": offset,
        "marker_type": marker_type,
        "marker_index": period_index,
    }


def make_nonwear_marker(
    start: float = 1704100000.0,
    end: float = 1704103600.0,
) -> dict:
    """Build a nonwear marker dict for test payloads."""
    return {
        "start_timestamp": start,
        "end_timestamp": end,
    }
