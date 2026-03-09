#!/usr/bin/env python3
"""
Comprehensive unit tests for FileService.

Tests file discovery, data loading, deletion, and configuration operations.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from sleep_scoring_app.core.constants import ActivityDataPreference, DeleteStatus
from sleep_scoring_app.core.dataclasses import BatchDeleteResult, DeleteResult, FileInfo
from sleep_scoring_app.services.file_service import FileService
from sleep_scoring_app.services.memory_service import BoundedCache


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create mock DatabaseManager."""
    mock = MagicMock()
    mock.get_available_files.return_value = []
    mock.get_file_date_ranges.return_value = []
    mock.load_sleep_metrics.return_value = []
    mock.delete_imported_file.return_value = True
    return mock


@pytest.fixture
def mock_data_manager() -> MagicMock:
    """Create mock DataManager."""
    mock = MagicMock()
    mock.find_data_files.return_value = []
    mock.load_real_data.return_value = ([], [])
    mock.preferred_activity_column = ActivityDataPreference.AXIS_Y
    mock._loading_service = MagicMock()
    mock._loading_service.load_unified_activity_data.return_value = None
    return mock


@pytest.fixture
def file_service(mock_db_manager: MagicMock) -> FileService:
    """Create FileService with mock dependencies."""
    with patch("sleep_scoring_app.services.file_service.DataManager") as MockDataManager:
        mock_data_manager = MagicMock()
        mock_data_manager.find_data_files.return_value = []
        mock_data_manager.preferred_activity_column = ActivityDataPreference.AXIS_Y
        mock_data_manager._loading_service = MagicMock()
        mock_data_manager._loading_service.load_unified_activity_data.return_value = None
        MockDataManager.return_value = mock_data_manager

        return FileService(mock_db_manager, max_files=1000)


@pytest.fixture
def sample_file_info() -> FileInfo:
    """Create sample FileInfo."""
    return FileInfo(
        filename="DEMO-1001.csv",
        source_path=Path("/data/DEMO-1001.csv"),
        total_dates=10,
        completed_count=5,
    )


@pytest.fixture
def sample_file_list(sample_file_info: FileInfo) -> list[FileInfo]:
    """Create list of sample files."""
    return [
        sample_file_info,
        FileInfo(
            filename="DEMO-1002.csv",
            source_path=Path("/data/DEMO-1002.csv"),
            total_dates=15,
            completed_count=10,
        ),
    ]


class TestFileServiceInit:
    """Tests for FileService initialization."""

    def test_creates_with_db_manager(self, mock_db_manager: MagicMock):
        """Creates with database manager."""
        with patch("sleep_scoring_app.services.file_service.DataManager"):
            service = FileService(mock_db_manager)
            assert service.db_manager is mock_db_manager

    def test_creates_with_custom_max_files(self, mock_db_manager: MagicMock):
        """Creates with custom max_files."""
        with patch("sleep_scoring_app.services.file_service.DataManager"):
            service = FileService(mock_db_manager, max_files=500)
            assert service._max_files == 500

    def test_initializes_caches(self, file_service: FileService):
        """Caches are initialized."""
        assert file_service.main_48h_data_cache is not None
        assert file_service.marker_status_cache is not None
        assert file_service._cached_date_ranges is not None

    def test_initializes_main_data_as_none(self, file_service: FileService):
        """Main data starts as None."""
        assert file_service.main_48h_data is None


class TestFindAvailableFiles:
    """Tests for find_available_files method."""

    def test_returns_files_from_data_manager(self, file_service: FileService, sample_file_list: list[FileInfo]):
        """Returns files from data manager."""
        file_service.data_manager.find_data_files.return_value = sample_file_list

        result = file_service.find_available_files()

        assert result == sample_file_list
        file_service.data_manager.find_data_files.assert_called_once()

    def test_returns_empty_list_on_error(self, file_service: FileService):
        """Returns empty list when error occurs."""
        file_service.data_manager.find_data_files.side_effect = Exception("Test error")

        result = file_service.find_available_files()

        assert result == []


class TestFindAvailableFilesWithCompletionCount:
    """Tests for find_available_files_with_completion_count method."""

    def test_adds_completion_counts(self, file_service: FileService, sample_file_info: FileInfo):
        """Completion counts are added to files."""
        file_service.data_manager.find_data_files.return_value = [sample_file_info]
        file_service.db_manager.load_sleep_metrics.return_value = []

        result = file_service.find_available_files_with_completion_count()

        assert len(result) == 1
        assert hasattr(result[0], "completed_count")


class TestLoadCurrentDateCore:
    """Tests for load_current_date_core method."""

    def test_returns_none_for_empty_dates(self, file_service: FileService):
        """Returns None when no available dates."""
        result = file_service.load_current_date_core(
            available_dates=[],
            current_date_index=0,
            current_date_48h_cache=BoundedCache(10, 10),
            selected_file="test.csv",
        )

        assert result is None

    def test_returns_none_for_invalid_index(self, file_service: FileService):
        """Returns None for out-of-bounds index."""
        dates = [date(2024, 1, 15)]

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=5,  # Out of bounds
            current_date_48h_cache=BoundedCache(10, 10),
            selected_file="test.csv",
        )

        assert result is None

    def test_returns_none_for_negative_index(self, file_service: FileService):
        """Returns None for negative index."""
        dates = [date(2024, 1, 15)]

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=-1,
            current_date_48h_cache=BoundedCache(10, 10),
            selected_file="test.csv",
        )

        assert result is None

    def test_uses_cache_when_available(self, file_service: FileService):
        """Returns cached data when available."""
        dates = [date(2024, 1, 15)]
        cache = BoundedCache(10, 10)
        cached_data = {
            "timestamps": [datetime(2024, 1, 15, 0, 0)],
            "axis_y": [100.0],
            "axis_x": [50.0],
            "axis_z": [25.0],
            "vector_magnitude": [120.0],
        }
        cache.put("2024-01-15", cached_data, 1)

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=0,
            current_date_48h_cache=cache,
            selected_file="test.csv",
        )

        assert result is not None
        assert result[0] == cached_data["timestamps"]
        assert result[1] == cached_data["axis_y"]

    def test_handles_unified_cache_data(self, file_service: FileService):
        """Handles unified data format in cache."""
        dates = [date(2024, 1, 15)]
        cache = BoundedCache(10, 10)
        unified_data = {
            "timestamps": [datetime(2024, 1, 15, 0, 0)],
            "axis_y": [100.0],
            "axis_x": [50.0],
            "axis_z": [25.0],
            "vector_magnitude": [120.0],
        }
        cache.put("2024-01-15", unified_data, 1)

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=0,
            current_date_48h_cache=cache,
            selected_file="test.csv",
        )

        # Should extract timestamps and preferred column
        assert result is not None
        assert result[0] == unified_data["timestamps"]

    def test_extracts_filename_from_path(self, file_service: FileService):
        """Extracts filename from full path."""
        dates = [date(2024, 1, 15)]
        cache = BoundedCache(10, 10)
        cached_data = {
            "timestamps": [datetime(2024, 1, 15)],
            "axis_y": [100.0],
            "axis_x": [50.0],
            "axis_z": [25.0],
            "vector_magnitude": [120.0],
        }
        cache.put("2024-01-15", cached_data, 1)

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=0,
            current_date_48h_cache=cache,
            selected_file="/path/to/test.csv",  # Full path
        )

        assert result is not None

    def test_stores_result_in_main_48h_data(self, file_service: FileService):
        """Stores result in main_48h_data."""
        dates = [date(2024, 1, 15)]
        cache = BoundedCache(10, 10)
        cached_data = {
            "timestamps": [datetime(2024, 1, 15)],
            "axis_y": [100.0],
            "axis_x": [50.0],
            "axis_z": [25.0],
            "vector_magnitude": [120.0],
        }
        cache.put("2024-01-15", cached_data, 1)

        file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=0,
            current_date_48h_cache=cache,
            selected_file="test.csv",
        )

        assert file_service.main_48h_data == (cached_data["timestamps"], cached_data["axis_y"])


class TestGetImportedFiles:
    """Tests for get_imported_files method."""

    def test_returns_files_from_db(self, file_service: FileService):
        """Returns files from database manager."""
        expected = [{"filename": "test.csv", "status": "imported"}]
        file_service.db_manager.get_available_files.return_value = expected

        result = file_service.get_imported_files()

        assert result == expected

    def test_returns_empty_on_error(self, file_service: FileService):
        """Returns empty list on error."""
        file_service.db_manager.get_available_files.side_effect = Exception("DB error")

        result = file_service.get_imported_files()

        assert result == []


class TestDeleteFile:
    """Tests for delete_file method."""

    def test_returns_success_on_deletion(self, file_service: FileService):
        """Returns success result on successful deletion."""
        file_service.db_manager.delete_imported_file.return_value = True

        result = file_service.delete_file("test.csv")

        assert result.status == DeleteStatus.SUCCESS
        assert result.filename == "test.csv"

    def test_returns_failed_on_failure(self, file_service: FileService):
        """Returns failed status when deletion fails."""
        file_service.db_manager.delete_imported_file.return_value = False

        result = file_service.delete_file("test.csv")

        assert result.status == DeleteStatus.FAILED

    def test_returns_error_on_exception(self, file_service: FileService):
        """Returns error status on exception."""
        file_service.db_manager.delete_imported_file.side_effect = Exception("DB error")

        result = file_service.delete_file("test.csv")

        assert result.status == DeleteStatus.ERROR
        assert result.error_message is not None


class TestDeleteFiles:
    """Tests for delete_files method."""

    def test_deletes_multiple_files(self, file_service: FileService):
        """Deletes all specified files."""
        file_service.db_manager.delete_imported_file.return_value = True

        result = file_service.delete_files(["file1.csv", "file2.csv", "file3.csv"])

        assert result.total_requested == 3
        assert result.successful == 3
        assert result.failed == 0

    def test_counts_failures(self, file_service: FileService):
        """Counts failed deletions correctly."""
        # First two succeed, third fails
        file_service.db_manager.delete_imported_file.side_effect = [True, True, False]

        result = file_service.delete_files(["file1.csv", "file2.csv", "file3.csv"])

        assert result.total_requested == 3
        assert result.successful == 2
        assert result.failed == 1

    def test_returns_individual_results(self, file_service: FileService):
        """Returns individual delete results."""
        file_service.db_manager.delete_imported_file.return_value = True

        result = file_service.delete_files(["file1.csv", "file2.csv"])

        assert len(result.results) == 2
        assert all(r.status == DeleteStatus.SUCCESS for r in result.results)


class TestGetFileCompletionCount:
    """Tests for get_file_completion_count method."""

    def test_returns_completion_count_from_files(self, file_service: FileService, sample_file_info: FileInfo):
        """Returns completion count from file list."""
        files = [sample_file_info]
        file_service.db_manager.load_sleep_metrics.return_value = []

        _completed, total = file_service.get_file_completion_count("DEMO-1001.csv", files)

        assert total == 10  # From sample_file_info

    def test_counts_unique_completed_dates(self, file_service: FileService, sample_file_info: FileInfo):
        """Counts unique dates with metrics."""
        from sleep_scoring_app.core.dataclasses import DailySleepMarkers, ParticipantInfo, SleepMetrics

        files = [sample_file_info]
        # Mock metrics with 3 unique dates
        mock_metrics = [
            MagicMock(analysis_date="2024-01-15"),
            MagicMock(analysis_date="2024-01-16"),
            MagicMock(analysis_date="2024-01-17"),
        ]
        file_service.db_manager.load_sleep_metrics.return_value = mock_metrics

        completed, _total = file_service.get_file_completion_count("DEMO-1001.csv", files)

        assert completed == 3

    def test_returns_zeros_on_error(self, file_service: FileService):
        """Returns (0, 0) on error."""
        file_service.db_manager.load_sleep_metrics.side_effect = Exception("DB error")

        completed, total = file_service.get_file_completion_count("test.csv")

        assert completed == 0
        assert total == 0


class TestSetDataFolder:
    """Tests for set_data_folder method."""

    def test_delegates_to_data_manager(self, file_service: FileService):
        """Delegates to data manager."""
        file_service.data_manager.set_data_folder.return_value = True

        result = file_service.set_data_folder("/new/folder")

        file_service.data_manager.set_data_folder.assert_called_once_with("/new/folder")
        assert result is True

    def test_accepts_path_object(self, file_service: FileService):
        """Accepts Path object."""
        file_service.data_manager.set_data_folder.return_value = True

        result = file_service.set_data_folder(Path("/new/folder"))

        assert result is True


class TestGetDataFolder:
    """Tests for get_data_folder method."""

    def test_returns_folder_from_data_manager(self, file_service: FileService):
        """Returns folder from data manager."""
        file_service.data_manager.data_folder = "/current/folder"

        result = file_service.get_data_folder()

        assert result == "/current/folder"

    def test_returns_none_when_not_set(self, file_service: FileService):
        """Returns None when no folder set."""
        file_service.data_manager.data_folder = None

        result = file_service.get_data_folder()

        assert result is None


class TestToggleDatabaseMode:
    """Tests for toggle_database_mode method."""

    def test_sets_use_database_true(self, file_service: FileService):
        """Sets database mode to True."""
        file_service.toggle_database_mode(True)

        assert file_service.data_manager.use_database is True

    def test_sets_use_database_false(self, file_service: FileService):
        """Sets database mode to False."""
        file_service.toggle_database_mode(False)

        assert file_service.data_manager.use_database is False


class TestGetDatabaseMode:
    """Tests for get_database_mode method."""

    def test_returns_current_mode(self, file_service: FileService):
        """Returns current database mode."""
        file_service.data_manager.use_database = True

        result = file_service.get_database_mode()

        assert result is True


class TestActivityColumnInLoadCurrentDateCore:
    """Tests for activity column handling in load_current_date_core."""

    def test_uses_axis_y_by_default(self, file_service: FileService):
        """Uses axis_y when preference is AXIS_Y."""
        dates = [date(2024, 1, 15)]
        cache = BoundedCache(10, 10)
        unified_data = {
            "timestamps": [datetime(2024, 1, 15, 0, 0)],
            "axis_y": [100.0],
            "axis_x": [50.0],
            "axis_z": [25.0],
            "vector_magnitude": [120.0],
        }
        cache.put("2024-01-15", unified_data, 1)
        file_service.data_manager.preferred_activity_column = ActivityDataPreference.AXIS_Y

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=0,
            current_date_48h_cache=cache,
            selected_file="test.csv",
        )

        assert result[1] == [100.0]  # axis_y value

    def test_uses_vector_magnitude_when_preferred(self, file_service: FileService):
        """Uses vector_magnitude when preference is VECTOR_MAGNITUDE."""
        dates = [date(2024, 1, 15)]
        cache = BoundedCache(10, 10)
        unified_data = {
            "timestamps": [datetime(2024, 1, 15, 0, 0)],
            "axis_y": [100.0],
            "axis_x": [50.0],
            "axis_z": [25.0],
            "vector_magnitude": [120.0],
        }
        cache.put("2024-01-15", unified_data, 1)
        file_service.data_manager.preferred_activity_column = ActivityDataPreference.VECTOR_MAGNITUDE

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=0,
            current_date_48h_cache=cache,
            selected_file="test.csv",
        )

        assert result[1] == [120.0]  # vector_magnitude value

    def test_uses_axis_x_when_preferred(self, file_service: FileService):
        """Uses axis_x when preference is AXIS_X."""
        dates = [date(2024, 1, 15)]
        cache = BoundedCache(10, 10)
        unified_data = {
            "timestamps": [datetime(2024, 1, 15, 0, 0)],
            "axis_y": [100.0],
            "axis_x": [50.0],
            "axis_z": [25.0],
            "vector_magnitude": [120.0],
        }
        cache.put("2024-01-15", unified_data, 1)
        file_service.data_manager.preferred_activity_column = ActivityDataPreference.AXIS_X

        result = file_service.load_current_date_core(
            available_dates=dates,
            current_date_index=0,
            current_date_48h_cache=cache,
            selected_file="test.csv",
        )

        assert result[1] == [50.0]  # axis_x value
