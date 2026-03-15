"""
Unit tests for the file watcher service.

Tests CSVFileHandler event handling, WatcherStatus tracking,
scan logic, path normalization, and start/stop lifecycle.
Uses mocks for filesystem and database operations.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sleep_scoring_web.services.file_watcher import (
    CSVFileHandler,
    WatcherStatus,
    _watcher_status,
    get_watcher_status,
    scan_existing_files,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_watcher_status():
    """Reset global watcher status before each test."""
    _watcher_status.is_running = False
    _watcher_status.total_ingested = 0
    _watcher_status.total_skipped = 0
    _watcher_status.total_failed = 0
    _watcher_status.last_scan_time = None
    _watcher_status.watched_directory = ""
    _watcher_status.pending_files.clear()
    _watcher_status.errors.clear()
    yield


# ---------------------------------------------------------------------------
# WatcherStatus
# ---------------------------------------------------------------------------


class TestWatcherStatus:
    """Tests for the WatcherStatus dataclass."""

    def test_default_values(self) -> None:
        status = WatcherStatus()
        assert status.is_running is False
        assert status.total_ingested == 0
        assert status.total_skipped == 0
        assert status.total_failed == 0
        assert status.last_scan_time is None
        assert status.watched_directory == ""
        assert status.pending_files == []
        assert status.errors == []

    def test_mutable_lists_are_independent(self) -> None:
        """Each instance should have its own lists."""
        s1 = WatcherStatus()
        s2 = WatcherStatus()
        s1.pending_files.append("file.csv")
        assert "file.csv" not in s2.pending_files


# ---------------------------------------------------------------------------
# get_watcher_status
# ---------------------------------------------------------------------------


class TestGetWatcherStatus:
    """Tests for get_watcher_status()."""

    def test_returns_dict(self) -> None:
        result = get_watcher_status()
        assert isinstance(result, dict)

    def test_contains_expected_keys(self) -> None:
        result = get_watcher_status()
        expected_keys = {
            "is_running",
            "watched_directory",
            "total_ingested",
            "total_skipped",
            "total_failed",
            "pending_files",
            "last_scan_time",
            "recent_errors",
        }
        assert set(result.keys()) == expected_keys

    def test_reflects_status_changes(self) -> None:
        _watcher_status.is_running = True
        _watcher_status.watched_directory = "/data"
        _watcher_status.total_ingested = 5
        _watcher_status.total_skipped = 2
        _watcher_status.total_failed = 1

        result = get_watcher_status()
        assert result["is_running"] is True
        assert result["watched_directory"] == "/data"
        assert result["total_ingested"] == 5
        assert result["total_skipped"] == 2
        assert result["total_failed"] == 1

    def test_pending_files_capped_at_10(self) -> None:
        for i in range(15):
            _watcher_status.pending_files.append(f"file_{i}.csv")
        result = get_watcher_status()
        assert len(result["pending_files"]) == 10

    def test_errors_capped_at_5(self) -> None:
        for i in range(10):
            _watcher_status.errors.append(f"error_{i}")
        result = get_watcher_status()
        assert len(result["recent_errors"]) == 5

    def test_last_scan_time_none(self) -> None:
        result = get_watcher_status()
        assert result["last_scan_time"] is None

    def test_last_scan_time_iso_format(self) -> None:
        from datetime import datetime

        _watcher_status.last_scan_time = datetime(2024, 1, 15, 10, 30, 0)
        result = get_watcher_status()
        assert result["last_scan_time"] == "2024-01-15T10:30:00"


# ---------------------------------------------------------------------------
# CSVFileHandler
# ---------------------------------------------------------------------------


class TestCSVFileHandler:
    """Tests for the CSVFileHandler event handler."""

    def test_normalize_path_string(self) -> None:
        path = CSVFileHandler._normalize_path("/data/test.csv")
        assert isinstance(path, Path)
        assert str(path) == "/data/test.csv"

    def test_normalize_path_bytes(self) -> None:
        path = CSVFileHandler._normalize_path(b"/data/test.csv")
        assert isinstance(path, Path)
        assert str(path) == "/data/test.csv"

    def test_normalize_path_other_type(self) -> None:
        path = CSVFileHandler._normalize_path(42)
        assert isinstance(path, Path)
        assert str(path) == "42"

    def test_on_created_ignores_directories(self) -> None:
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = True
        event.src_path = "/data/subdir"

        handler.on_created(event)
        assert queue.empty()
        loop.close()

    def test_on_created_ignores_non_csv(self) -> None:
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/data/test.txt"

        # on_created checks suffix — .txt should be ignored
        # It won't call loop.call_soon_threadsafe for non-csv files
        handler.on_created(event)
        # queue should still be empty since .txt is not .csv
        assert queue.empty()
        loop.close()

    def test_on_moved_ignores_directories(self) -> None:
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = True
        event.dest_path = "/data/subdir"

        handler.on_moved(event)
        assert queue.empty()
        loop.close()

    def test_on_moved_ignores_non_csv(self) -> None:
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = False
        event.dest_path = "/data/test.txt"

        handler.on_moved(event)
        assert queue.empty()
        loop.close()

    def test_on_moved_without_dest_path_attr(self) -> None:
        """Events without dest_path should not crash."""
        loop = asyncio.new_event_loop()
        queue = asyncio.Queue()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock(spec=[])  # No attributes
        event.is_directory = False

        # Should not raise
        handler.on_moved(event)
        assert queue.empty()
        loop.close()


# ---------------------------------------------------------------------------
# scan_existing_files
# ---------------------------------------------------------------------------


class TestScanExistingFiles:
    """Tests for scan_existing_files()."""

    @pytest.mark.asyncio
    async def test_nonexistent_data_dir(self, tmp_path: Path) -> None:
        """Should return 0 when data dir does not exist."""
        nonexistent = tmp_path / "does_not_exist"
        with patch("sleep_scoring_web.services.file_watcher.settings") as mock_settings:
            mock_settings.data_dir = str(nonexistent)
            result = await scan_existing_files()
        assert result == 0

    @pytest.mark.asyncio
    async def test_empty_data_dir(self, tmp_path: Path) -> None:
        """Should return 0 when data dir has no CSV files."""
        with patch("sleep_scoring_web.services.file_watcher.settings") as mock_settings:
            mock_settings.data_dir = str(tmp_path)
            with patch(
                "sleep_scoring_web.services.file_watcher._ingest_file",
                new_callable=AsyncMock,
            ):
                result = await scan_existing_files()
        assert result == 0

    @pytest.mark.asyncio
    async def test_scans_csv_files(self, tmp_path: Path) -> None:
        """Should find and attempt to ingest CSV files."""
        # Create test CSV files
        (tmp_path / "data1.csv").write_text("a,b,c\n1,2,3\n")
        (tmp_path / "data2.csv").write_text("a,b,c\n4,5,6\n")
        (tmp_path / "readme.txt").write_text("not a csv")

        with patch("sleep_scoring_web.services.file_watcher.settings") as mock_settings:
            mock_settings.data_dir = str(tmp_path)
            with patch(
                "sleep_scoring_web.services.file_watcher._ingest_file",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ingest:
                result = await scan_existing_files()

        assert result == 2
        assert mock_ingest.call_count == 2

    @pytest.mark.asyncio
    async def test_counts_only_ingested(self, tmp_path: Path) -> None:
        """Should only count files that were actually ingested (return True)."""
        (tmp_path / "data1.csv").write_text("a,b,c\n1,2,3\n")
        (tmp_path / "data2.csv").write_text("a,b,c\n4,5,6\n")

        # First file ingested, second skipped
        with patch("sleep_scoring_web.services.file_watcher.settings") as mock_settings:
            mock_settings.data_dir = str(tmp_path)
            with patch(
                "sleep_scoring_web.services.file_watcher._ingest_file",
                new_callable=AsyncMock,
                side_effect=[True, False],
            ):
                result = await scan_existing_files()

        assert result == 1

    @pytest.mark.asyncio
    async def test_updates_last_scan_time(self, tmp_path: Path) -> None:
        """Should update last_scan_time in watcher status."""
        assert _watcher_status.last_scan_time is None

        with patch("sleep_scoring_web.services.file_watcher.settings") as mock_settings:
            mock_settings.data_dir = str(tmp_path)
            await scan_existing_files()

        assert _watcher_status.last_scan_time is not None

    @pytest.mark.asyncio
    async def test_scans_uppercase_csv(self, tmp_path: Path) -> None:
        """Should also find .CSV files (uppercase)."""
        (tmp_path / "DATA.CSV").write_text("a,b,c\n1,2,3\n")

        with patch("sleep_scoring_web.services.file_watcher.settings") as mock_settings:
            mock_settings.data_dir = str(tmp_path)
            with patch(
                "sleep_scoring_web.services.file_watcher._ingest_file",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_ingest:
                result = await scan_existing_files()

        assert result == 1
        assert mock_ingest.call_count == 1


# ---------------------------------------------------------------------------
# _ingest_file (mocked dependencies)
# ---------------------------------------------------------------------------


class TestIngestFile:
    """Tests for the _ingest_file helper."""

    @pytest.mark.asyncio
    async def test_skips_duplicate_file(self, tmp_path: Path) -> None:
        """Should skip files already in the database."""
        from sleep_scoring_web.services.file_watcher import _ingest_file

        csv_file = tmp_path / "existing.csv"
        csv_file.write_text("a,b\n1,2\n")

        with patch(
            "sleep_scoring_web.services.file_watcher._check_file_exists_in_db",
            new_callable=AsyncMock,
            return_value=True,
        ):
            result = await _ingest_file(csv_file)

        assert result is False
        assert _watcher_status.total_skipped == 1

    @pytest.mark.asyncio
    async def test_removes_from_pending(self, tmp_path: Path) -> None:
        """Should remove filename from pending list."""
        from sleep_scoring_web.services.file_watcher import _ingest_file

        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n")
        _watcher_status.pending_files.append("test.csv")

        with patch(
            "sleep_scoring_web.services.file_watcher._check_file_exists_in_db",
            new_callable=AsyncMock,
            return_value=True,
        ):
            await _ingest_file(csv_file)

        assert "test.csv" not in _watcher_status.pending_files

    @pytest.mark.asyncio
    async def test_handles_ingestion_failure(self, tmp_path: Path) -> None:
        """Should track failed ingestion and store error."""
        from sleep_scoring_web.services.file_watcher import _ingest_file

        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("a,b\n1,2\n")

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock(return_value=mock_session)

        with (
            patch(
                "sleep_scoring_web.services.file_watcher._check_file_exists_in_db",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "sleep_scoring_web.db.session.async_session_maker",
                mock_session_maker,
            ),
            patch(
                "sleep_scoring_web.api.files.import_file_from_disk_async",
                new_callable=AsyncMock,
                side_effect=ValueError("Parse error"),
            ),
        ):
            result = await _ingest_file(csv_file)

        assert result is False
        assert _watcher_status.total_failed == 1
        assert len(_watcher_status.errors) == 1
        assert "bad.csv" in _watcher_status.errors[0]

    @pytest.mark.asyncio
    async def test_errors_capped_at_10(self, tmp_path: Path) -> None:
        """Should keep only the last 10 errors."""
        from sleep_scoring_web.services.file_watcher import _ingest_file

        # Pre-fill errors
        _watcher_status.errors = [f"old_error_{i}" for i in range(10)]

        csv_file = tmp_path / "fail.csv"
        csv_file.write_text("a,b\n1,2\n")

        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        mock_session_maker = MagicMock(return_value=mock_session)

        with (
            patch(
                "sleep_scoring_web.services.file_watcher._check_file_exists_in_db",
                new_callable=AsyncMock,
                return_value=False,
            ),
            patch(
                "sleep_scoring_web.db.session.async_session_maker",
                mock_session_maker,
            ),
            patch(
                "sleep_scoring_web.api.files.import_file_from_disk_async",
                new_callable=AsyncMock,
                side_effect=ValueError("New error"),
            ),
        ):
            await _ingest_file(csv_file)

        assert len(_watcher_status.errors) == 10
        assert "New error" in _watcher_status.errors[-1]


# ---------------------------------------------------------------------------
# _queue_file
# ---------------------------------------------------------------------------


class TestQueueFile:
    """Tests for CSVFileHandler._queue_file."""

    @pytest.mark.asyncio
    async def test_queue_file_adds_to_queue_and_pending(self) -> None:
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[Path] = asyncio.Queue()
        handler = CSVFileHandler(queue, loop)

        test_path = Path("/data/test.csv")
        await handler._queue_file(test_path)

        assert not queue.empty()
        queued = await queue.get()
        assert queued == test_path
        assert "test.csv" in _watcher_status.pending_files


# ---------------------------------------------------------------------------
# start/stop lifecycle (mocked)
# ---------------------------------------------------------------------------


class TestStartStopLifecycle:
    """Tests for start_file_watcher and stop_file_watcher lifecycle."""

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self) -> None:
        """stop_file_watcher should handle being called when not started."""
        from sleep_scoring_web.services.file_watcher import stop_file_watcher

        # Should not raise
        await stop_file_watcher()
        assert _watcher_status.is_running is False
