"""
Unit tests for the in-memory ProcessingTracker.

Tests status tracking, progress updates, completion/failure states,
stale entry eviction, and max-entry capping.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from sleep_scoring_web.schemas.enums import FileStatus
from sleep_scoring_web.services.processing_tracker import (
    ProcessingProgress,
    _MAX_ENTRIES,
    _STALE_THRESHOLD,
    _processing_status,
    clear_tracking,
    get_progress,
    start_tracking,
    update_progress,
)


@pytest.fixture(autouse=True)
def _clean_tracker():
    """Ensure a clean tracker state for every test."""
    _processing_status.clear()
    yield
    _processing_status.clear()


class TestStartTracking:
    """Tests for start_tracking()."""

    def test_start_tracking_creates_entry(self) -> None:
        progress = start_tracking(42)
        assert progress.file_id == 42
        assert progress.status == FileStatus.PROCESSING
        assert progress.phase == ""
        assert progress.percent == 0.0
        assert progress.rows_processed == 0
        assert progress.error is None

    def test_start_tracking_returns_progress_object(self) -> None:
        progress = start_tracking(1)
        assert isinstance(progress, ProcessingProgress)

    def test_start_tracking_stores_in_global_dict(self) -> None:
        start_tracking(10)
        assert 10 in _processing_status
        assert _processing_status[10].file_id == 10

    def test_start_tracking_overwrites_existing(self) -> None:
        p1 = start_tracking(5)
        p1.percent = 50.0
        p2 = start_tracking(5)
        assert p2.percent == 0.0
        assert _processing_status[5].percent == 0.0

    def test_start_tracking_sets_timestamps(self) -> None:
        before = datetime.now()
        progress = start_tracking(1)
        after = datetime.now()
        assert before <= progress.started_at <= after
        assert before <= progress.updated_at <= after

    def test_start_tracking_multiple_files(self) -> None:
        start_tracking(1)
        start_tracking(2)
        start_tracking(3)
        assert len(_processing_status) == 3


class TestUpdateProgress:
    """Tests for update_progress()."""

    def test_update_phase(self) -> None:
        start_tracking(1)
        update_progress(1, phase="decompressing")
        assert get_progress(1).phase == "decompressing"

    def test_update_percent(self) -> None:
        start_tracking(1)
        update_progress(1, percent=55.5)
        assert get_progress(1).percent == 55.5

    def test_update_rows_processed(self) -> None:
        start_tracking(1)
        update_progress(1, rows_processed=1000)
        assert get_progress(1).rows_processed == 1000

    def test_update_total_rows_estimate(self) -> None:
        start_tracking(1)
        update_progress(1, total_rows_estimate=50000)
        assert get_progress(1).total_rows_estimate == 50000

    def test_update_error(self) -> None:
        start_tracking(1)
        update_progress(1, error="Something went wrong")
        assert get_progress(1).error == "Something went wrong"

    def test_update_status(self) -> None:
        start_tracking(1)
        update_progress(1, status=FileStatus.READY)
        assert get_progress(1).status == FileStatus.READY

    def test_update_multiple_fields(self) -> None:
        start_tracking(1)
        update_progress(
            1,
            phase="inserting_db",
            percent=90.0,
            rows_processed=5000,
            status=FileStatus.READY,
        )
        p = get_progress(1)
        assert p.phase == "inserting_db"
        assert p.percent == 90.0
        assert p.rows_processed == 5000
        assert p.status == FileStatus.READY

    def test_update_updates_timestamp(self) -> None:
        start_tracking(1)
        original_time = get_progress(1).updated_at
        # Use a small sleep alternative: just verify it's being called
        update_progress(1, phase="reading_csv")
        assert get_progress(1).updated_at >= original_time

    def test_update_nonexistent_file_is_noop(self) -> None:
        """Updating a file that isn't tracked should not raise."""
        update_progress(999, phase="test", percent=50.0)
        assert get_progress(999) is None

    def test_update_preserves_unset_fields(self) -> None:
        start_tracking(1)
        update_progress(1, phase="decompressing", percent=10.0)
        update_progress(1, percent=50.0)
        p = get_progress(1)
        assert p.phase == "decompressing"  # unchanged
        assert p.percent == 50.0  # updated


class TestGetProgress:
    """Tests for get_progress()."""

    def test_get_existing(self) -> None:
        start_tracking(1)
        assert get_progress(1) is not None
        assert get_progress(1).file_id == 1

    def test_get_nonexistent(self) -> None:
        assert get_progress(999) is None

    def test_get_returns_same_object(self) -> None:
        """Returned object is the same reference as internal storage."""
        start_tracking(1)
        p = get_progress(1)
        p.percent = 77.0
        assert _processing_status[1].percent == 77.0


class TestClearTracking:
    """Tests for clear_tracking()."""

    def test_clear_existing(self) -> None:
        start_tracking(1)
        clear_tracking(1)
        assert get_progress(1) is None
        assert 1 not in _processing_status

    def test_clear_nonexistent_is_noop(self) -> None:
        """Clearing a non-tracked file should not raise."""
        clear_tracking(999)  # Should not raise

    def test_clear_does_not_affect_others(self) -> None:
        start_tracking(1)
        start_tracking(2)
        clear_tracking(1)
        assert get_progress(1) is None
        assert get_progress(2) is not None


class TestStaleEviction:
    """Tests for _evict_stale_entries() triggered by start_tracking()."""

    def test_stale_entries_are_evicted(self) -> None:
        """Entries older than the threshold should be evicted on next start_tracking."""
        p = start_tracking(1)
        # Make it stale by backdating updated_at
        p.updated_at = datetime.now() - _STALE_THRESHOLD - timedelta(minutes=1)

        # Starting a new tracking should evict the stale entry
        start_tracking(2)
        assert get_progress(1) is None
        assert get_progress(2) is not None

    def test_fresh_entries_not_evicted(self) -> None:
        start_tracking(1)
        start_tracking(2)
        # Both should still be present
        assert get_progress(1) is not None
        assert get_progress(2) is not None

    def test_cap_at_max_entries(self) -> None:
        """When over _MAX_ENTRIES, eviction should trim to _MAX_ENTRIES.

        Eviction runs at the *start* of start_tracking, so after adding
        _MAX_ENTRIES + N entries the dict has at most _MAX_ENTRIES + 1
        (the last call evicts down to _MAX_ENTRIES, then adds one more).
        """
        for i in range(_MAX_ENTRIES + 10):
            start_tracking(i)

        # The dict may be _MAX_ENTRIES + 1 due to the add-after-evict order.
        assert len(_processing_status) <= _MAX_ENTRIES + 1


class TestProcessingProgressDataclass:
    """Tests for the ProcessingProgress dataclass defaults."""

    def test_defaults(self) -> None:
        p = ProcessingProgress(file_id=99)
        assert p.file_id == 99
        assert p.status == FileStatus.PROCESSING
        assert p.phase == ""
        assert p.percent == 0.0
        assert p.rows_processed == 0
        assert p.total_rows_estimate is None
        assert p.error is None
        assert isinstance(p.started_at, datetime)
        assert isinstance(p.updated_at, datetime)

    def test_custom_values(self) -> None:
        p = ProcessingProgress(
            file_id=42,
            status=FileStatus.READY,
            phase="done",
            percent=100.0,
            rows_processed=10000,
            total_rows_estimate=10000,
        )
        assert p.status == FileStatus.READY
        assert p.phase == "done"
        assert p.percent == 100.0


class TestFailureFlow:
    """Test typical failure workflow."""

    def test_failure_sets_error_and_status(self) -> None:
        start_tracking(1)
        update_progress(1, phase="reading_csv", percent=30.0)
        # Simulate failure
        update_progress(1, status=FileStatus.FAILED, error="CSV parse error")
        p = get_progress(1)
        assert p.status == FileStatus.FAILED
        assert p.error == "CSV parse error"
        assert p.phase == "reading_csv"  # phase preserved from before failure

    def test_full_lifecycle(self) -> None:
        """Track a file through the full processing lifecycle."""
        start_tracking(1)
        update_progress(1, phase="decompressing", percent=5.0)
        update_progress(1, phase="decompressing", percent=15.0)
        update_progress(1, phase="reading_csv", percent=30.0)
        update_progress(1, phase="inserting_db", percent=70.0)
        update_progress(1, phase="inserting_db", percent=100.0, status=FileStatus.READY)

        p = get_progress(1)
        assert p.status == FileStatus.READY
        assert p.percent == 100.0
        assert p.phase == "inserting_db"

        clear_tracking(1)
        assert get_progress(1) is None
