"""
Tests for ImportProgressTracker and ImportProgress.

Tests progress tracking for file import operations.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.services.import_progress_tracker import (
    ImportProgress,
    ImportProgressTracker,
)


class TestImportProgressInit:
    """Tests for ImportProgress initialization."""

    def test_creates_with_defaults(self) -> None:
        """Creates with default values."""
        progress = ImportProgress()

        assert progress.total_files == 0
        assert progress.processed_files == 0
        assert progress.current_file == ""
        assert progress.errors == []
        assert progress.warnings == []

    def test_creates_with_total_files(self) -> None:
        """Creates with total files count."""
        progress = ImportProgress(total_files=10)

        assert progress.total_files == 10

    def test_creates_with_total_records(self) -> None:
        """Creates with total records count."""
        progress = ImportProgress(total_records=1000)

        assert progress.total_records == 1000


class TestFileProgressPercent:
    """Tests for file_progress_percent property."""

    def test_progress_zero_when_not_started(self) -> None:
        """Progress is 0% when not started."""
        progress = ImportProgress(total_files=10)

        assert progress.file_progress_percent == 0.0

    def test_progress_50_when_half_done(self) -> None:
        """Progress is 50% when half complete."""
        progress = ImportProgress(total_files=10)
        progress.processed_files = 5

        assert progress.file_progress_percent == 50.0

    def test_progress_100_when_complete(self) -> None:
        """Progress is 100% when complete."""
        progress = ImportProgress(total_files=10)
        progress.processed_files = 10

        assert progress.file_progress_percent == 100.0

    def test_progress_zero_when_no_files(self) -> None:
        """Progress is 0% when no files to process."""
        progress = ImportProgress(total_files=0)

        assert progress.file_progress_percent == 0.0


class TestRecordProgressPercent:
    """Tests for record_progress_percent property."""

    def test_progress_zero_when_not_started(self) -> None:
        """Progress is 0% when not started."""
        progress = ImportProgress(total_records=1000)

        assert progress.record_progress_percent == 0.0

    def test_progress_50_when_half_done(self) -> None:
        """Progress is 50% when half complete."""
        progress = ImportProgress(total_records=1000)
        progress.processed_records = 500

        assert progress.record_progress_percent == 50.0


class TestIsComplete:
    """Tests for is_complete property."""

    def test_is_complete_false_when_in_progress(self) -> None:
        """is_complete is False when in progress."""
        progress = ImportProgress(total_files=5)
        progress.processed_files = 3

        assert progress.is_complete is False

    def test_is_complete_true_when_done(self) -> None:
        """is_complete is True when all processed."""
        progress = ImportProgress(total_files=5)
        progress.processed_files = 5

        assert progress.is_complete is True

    def test_is_complete_true_when_no_files(self) -> None:
        """is_complete is True when no files to process."""
        progress = ImportProgress(total_files=0)

        # No files = nothing to do = complete
        assert progress.is_complete is True


class TestAddError:
    """Tests for add_error method."""

    def test_adds_error_to_list(self) -> None:
        """Adds error message to errors list."""
        progress = ImportProgress()

        progress.add_error("Test error message")

        assert len(progress.errors) == 1
        assert "Test error message" in progress.errors

    def test_multiple_errors(self) -> None:
        """Can add multiple errors."""
        progress = ImportProgress()

        progress.add_error("Error 1")
        progress.add_error("Error 2")

        assert len(progress.errors) == 2


class TestAddWarning:
    """Tests for add_warning method."""

    def test_adds_warning_to_list(self) -> None:
        """Adds warning message to warnings list."""
        progress = ImportProgress()

        progress.add_warning("Test warning")

        assert len(progress.warnings) == 1
        assert "Test warning" in progress.warnings


class TestGetSummary:
    """Tests for get_summary method."""

    def test_returns_summary_dict(self) -> None:
        """Returns summary dictionary with expected keys."""
        progress = ImportProgress(total_files=5)
        progress.processed_files = 3
        progress.imported_files.append("file1.csv")
        progress.add_error("Error 1")

        summary = progress.get_summary()

        assert summary["total_files"] == 5
        assert summary["processed_files"] == 3
        assert summary["imported_files_count"] == 1
        assert summary["error_count"] == 1


class TestImportProgressTrackerInit:
    """Tests for ImportProgressTracker initialization."""

    def test_creates_with_progress(self) -> None:
        """Creates with ImportProgress instance."""
        tracker = ImportProgressTracker(total_files=10)

        assert tracker.progress is not None
        assert tracker.progress.total_files == 10


class TestFileStarted:
    """Tests for file_started method."""

    def test_sets_current_file(self) -> None:
        """Sets current file on progress."""
        tracker = ImportProgressTracker(total_files=5)

        tracker.file_started("test.csv")

        assert tracker.progress.current_file == "test.csv"


class TestFileCompleted:
    """Tests for file_completed method."""

    def test_increments_processed_count(self) -> None:
        """Increments processed files count."""
        tracker = ImportProgressTracker(total_files=5)

        tracker.file_completed("test.csv", success=True)

        assert tracker.progress.processed_files == 1

    def test_adds_to_imported_on_success(self) -> None:
        """Adds filename to imported_files on success."""
        tracker = ImportProgressTracker(total_files=5)

        tracker.file_completed("test.csv", success=True)

        assert "test.csv" in tracker.progress.imported_files

    def test_no_imported_on_failure(self) -> None:
        """Doesn't add to imported_files on failure."""
        tracker = ImportProgressTracker(total_files=5)

        tracker.file_completed("test.csv", success=False)

        assert "test.csv" not in tracker.progress.imported_files


class TestFileSkipped:
    """Tests for file_skipped method."""

    def test_adds_to_skipped_files(self) -> None:
        """Adds to skipped_files list."""
        tracker = ImportProgressTracker(total_files=5)

        tracker.file_skipped("test.csv", "Already imported")

        assert len(tracker.progress.skipped_files) == 1


class TestTrackerAddError:
    """Tests for add_error method on tracker."""

    def test_delegates_to_progress(self) -> None:
        """Delegates to progress.add_error."""
        tracker = ImportProgressTracker(total_files=5)

        tracker.add_error("Test error")

        assert len(tracker.progress.errors) == 1


class TestTrackerAddWarning:
    """Tests for add_warning method on tracker."""

    def test_delegates_to_progress(self) -> None:
        """Delegates to progress.add_warning."""
        tracker = ImportProgressTracker(total_files=5)

        tracker.add_warning("Test warning")

        assert len(tracker.progress.warnings) == 1


class TestUpdateRecordProgress:
    """Tests for update_record_progress method."""

    def test_increments_record_count(self) -> None:
        """Increments processed records count."""
        tracker = ImportProgressTracker(total_files=1, total_records=100)

        tracker.update_record_progress(50)

        assert tracker.progress.processed_records == 50


class TestGetProgress:
    """Tests for get_progress method."""

    def test_returns_progress_object(self) -> None:
        """Returns the progress object."""
        tracker = ImportProgressTracker(total_files=5)

        result = tracker.get_progress()

        assert result is tracker.progress
