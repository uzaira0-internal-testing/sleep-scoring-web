"""
Tests for DiaryImportProgress.

Tests progress tracking for diary import operations.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.services.diary.progress import DiaryImportProgress


class TestDiaryImportProgressInit:
    """Tests for DiaryImportProgress initialization."""

    def test_creates_with_defaults(self) -> None:
        """Creates with default values."""
        progress = DiaryImportProgress()

        assert progress.total_files == 0
        assert progress.total_sheets == 0
        assert progress.processed_files == 0
        assert progress.processed_sheets == 0
        assert progress.current_file == ""
        assert progress.current_sheet == ""
        assert progress.current_operation == ""
        assert progress.entries_imported == 0

    def test_creates_with_custom_values(self) -> None:
        """Creates with custom values."""
        progress = DiaryImportProgress(total_files=5, total_sheets=10)

        assert progress.total_files == 5
        assert progress.total_sheets == 10


class TestFileProgressPercent:
    """Tests for file_progress_percent property."""

    def test_returns_zero_for_no_files(self) -> None:
        """Returns 0 when no files to process."""
        progress = DiaryImportProgress(total_files=0)

        assert progress.file_progress_percent == 0.0

    def test_returns_50_for_half_done(self) -> None:
        """Returns 50% when half complete."""
        progress = DiaryImportProgress(total_files=4)
        progress.processed_files = 2

        assert progress.file_progress_percent == 50.0

    def test_returns_100_for_complete(self) -> None:
        """Returns 100% when complete."""
        progress = DiaryImportProgress(total_files=4)
        progress.processed_files = 4

        assert progress.file_progress_percent == 100.0


class TestSheetProgressPercent:
    """Tests for sheet_progress_percent property."""

    def test_returns_zero_for_no_sheets(self) -> None:
        """Returns 0 when no sheets to process."""
        progress = DiaryImportProgress(total_sheets=0)

        assert progress.sheet_progress_percent == 0.0

    def test_returns_25_for_quarter_done(self) -> None:
        """Returns 25% when quarter complete."""
        progress = DiaryImportProgress(total_sheets=8)
        progress.processed_sheets = 2

        assert progress.sheet_progress_percent == 25.0

    def test_returns_100_for_complete(self) -> None:
        """Returns 100% when complete."""
        progress = DiaryImportProgress(total_sheets=8)
        progress.processed_sheets = 8

        assert progress.sheet_progress_percent == 100.0


class TestGetStatusText:
    """Tests for get_status_text method."""

    def test_shows_loading_status(self) -> None:
        """Shows loading status."""
        progress = DiaryImportProgress()
        progress.current_operation = "loading"
        progress.current_file = "diary.xlsx"
        progress.current_sheet = "Sheet1"

        result = progress.get_status_text()

        assert "Loading" in result
        assert "diary.xlsx" in result
        assert "Sheet1" in result

    def test_shows_importing_status(self) -> None:
        """Shows importing status."""
        progress = DiaryImportProgress()
        progress.current_operation = "importing"
        progress.current_file = "diary.xlsx"
        progress.current_sheet = "Sheet1"

        result = progress.get_status_text()

        assert "Importing" in result

    def test_shows_processing_status(self) -> None:
        """Shows processing status."""
        progress = DiaryImportProgress()
        progress.current_operation = "processing"
        progress.current_file = "diary.xlsx"

        result = progress.get_status_text()

        assert "Processing" in result
        assert "diary.xlsx" in result

    def test_shows_default_status(self) -> None:
        """Shows default status for unknown operation."""
        progress = DiaryImportProgress(total_files=5)
        progress.processed_files = 2
        progress.current_operation = ""

        result = progress.get_status_text()

        assert "Processing file" in result
        assert "3" in result  # processed + 1
        assert "5" in result


class TestStateUpdates:
    """Tests for state update operations."""

    def test_can_update_processed_files(self) -> None:
        """Can update processed files count."""
        progress = DiaryImportProgress(total_files=5)

        progress.processed_files = 3

        assert progress.processed_files == 3

    def test_can_update_current_file(self) -> None:
        """Can update current file."""
        progress = DiaryImportProgress()

        progress.current_file = "new_file.xlsx"

        assert progress.current_file == "new_file.xlsx"

    def test_can_update_entries_imported(self) -> None:
        """Can update entries imported."""
        progress = DiaryImportProgress()

        progress.entries_imported = 150

        assert progress.entries_imported == 150
