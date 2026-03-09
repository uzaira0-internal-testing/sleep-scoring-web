"""
Tests for UnifiedDataService.

Tests the facade pattern that delegates to FileService, DiaryService, and CacheService.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import ActivityDataPreference, FileSourceType
from sleep_scoring_app.core.dataclasses import FileInfo
from sleep_scoring_app.services.unified_data_service import UnifiedDataService


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager."""
    manager = MagicMock()
    manager.get_available_activity_columns.return_value = []
    manager.load_raw_activity_data.return_value = ([], [])
    return manager


@pytest.fixture
def service(mock_db_manager: MagicMock) -> UnifiedDataService:
    """Create a UnifiedDataService instance with mocked dependencies."""
    with (
        patch("sleep_scoring_app.services.unified_data_service.FileService") as mock_fs,
        patch("sleep_scoring_app.services.unified_data_service.DiaryService") as mock_ds,
        patch("sleep_scoring_app.services.unified_data_service.CacheService") as mock_cs,
    ):
        # Configure mock services
        mock_file_service = MagicMock()
        mock_diary_service = MagicMock()
        mock_cache_service = MagicMock()

        mock_fs.return_value = mock_file_service
        mock_ds.return_value = mock_diary_service
        mock_cs.return_value = mock_cache_service

        # Create service
        svc = UnifiedDataService(mock_db_manager)

        # Store mocks for test access
        svc._file_service = mock_file_service
        svc._diary_service = mock_diary_service
        svc._cache_service = mock_cache_service

        return svc


@pytest.fixture
def sample_file_info() -> FileInfo:
    """Create sample FileInfo for testing."""
    return FileInfo(
        filename="TEST-001.csv",
        source=FileSourceType.DATABASE,
        source_path=None,
        participant_id="TEST-001",
    )


class TestUnifiedDataServiceInit:
    """Tests for UnifiedDataService initialization."""

    def test_init_with_database_manager(self, mock_db_manager: MagicMock) -> None:
        """Service initializes with database manager."""
        with (
            patch("sleep_scoring_app.services.unified_data_service.FileService"),
            patch("sleep_scoring_app.services.unified_data_service.DiaryService"),
            patch("sleep_scoring_app.services.unified_data_service.CacheService"),
        ):
            service = UnifiedDataService(mock_db_manager)
            assert service.db_manager is mock_db_manager

    def test_sets_singleton_instance(self, mock_db_manager: MagicMock) -> None:
        """Service sets singleton instance."""
        with (
            patch("sleep_scoring_app.services.unified_data_service.FileService"),
            patch("sleep_scoring_app.services.unified_data_service.DiaryService"),
            patch("sleep_scoring_app.services.unified_data_service.CacheService"),
        ):
            service = UnifiedDataService(mock_db_manager)
            assert UnifiedDataService.get_instance() is service

    def test_exposes_data_manager(self, service: UnifiedDataService) -> None:
        """Service exposes _data_manager from file service."""
        assert service._data_manager is service._file_service.data_manager


class TestLoadCurrentDate:
    """Tests for load_current_date method."""

    def test_returns_none_for_empty_dates(self, service: UnifiedDataService) -> None:
        """Returns None when no dates available."""
        result = service.load_current_date(
            current_date_48h_cache=MagicMock(),
            available_dates_iso=[],
            current_date_index=0,
            selected_file="test.csv",
        )
        assert result is None

    def test_returns_none_for_no_file(self, service: UnifiedDataService) -> None:
        """Returns None when no file selected."""
        result = service.load_current_date(
            current_date_48h_cache=MagicMock(),
            available_dates_iso=["2024-01-15"],
            current_date_index=0,
            selected_file="",
        )
        assert result is None

    def test_delegates_to_file_service(self, service: UnifiedDataService) -> None:
        """Delegates loading to file service."""
        mock_cache = MagicMock()
        service._file_service.load_current_date_core.return_value = (
            [datetime(2024, 1, 15, 12)],
            [100.0],
        )

        result = service.load_current_date(
            current_date_48h_cache=mock_cache,
            available_dates_iso=["2024-01-15", "2024-01-16"],
            current_date_index=0,
            selected_file="test.csv",
        )

        service._file_service.load_current_date_core.assert_called_once()
        assert result is not None


class TestLoadSelectedFile:
    """Tests for load_selected_file method."""

    def test_delegates_to_data_manager(self, service: UnifiedDataService, sample_file_info: FileInfo) -> None:
        """Delegates to data manager."""
        expected_dates = [date(2024, 1, 15), date(2024, 1, 16)]
        service._data_manager.load_selected_file.return_value = expected_dates

        result = service.load_selected_file(sample_file_info, skip_rows=10)

        service._data_manager.load_selected_file.assert_called_once_with(sample_file_info, 10)
        assert result == expected_dates


class TestFindAvailableFiles:
    """Tests for find_available_files methods."""

    def test_find_available_files(self, service: UnifiedDataService) -> None:
        """Delegates to file service."""
        expected = [FileInfo(filename="test.csv", source=FileSourceType.CSV)]
        service._file_service.find_available_files.return_value = expected

        result = service.find_available_files()

        service._file_service.find_available_files.assert_called_once()
        assert result == expected

    def test_find_available_files_with_completion_count(self, service: UnifiedDataService) -> None:
        """Delegates to file service for completion count variant."""
        expected = [FileInfo(filename="test.csv", source=FileSourceType.CSV)]
        service._file_service.find_available_files_with_completion_count.return_value = expected

        result = service.find_available_files_with_completion_count()

        service._file_service.find_available_files_with_completion_count.assert_called_once()
        assert result == expected


class TestDeleteFiles:
    """Tests for delete_files method."""

    def test_delegates_to_file_service(self, service: UnifiedDataService) -> None:
        """Delegates deletion to file service."""
        filenames = ["file1.csv", "file2.csv"]
        service._file_service.delete_files.return_value = {"deleted": 2}

        result = service.delete_files(filenames)

        service._file_service.delete_files.assert_called_once_with(filenames)
        assert result == {"deleted": 2}


class TestLoadAvailableFiles:
    """Tests for load_available_files method."""

    def test_loads_files_without_completion_counts(self, service: UnifiedDataService) -> None:
        """Loads files without completion counts by default."""
        expected = [FileInfo(filename="test.csv", source=FileSourceType.CSV)]
        service._file_service.find_available_files.return_value = expected

        result = service.load_available_files(load_completion_counts=False)

        service._file_service.find_available_files.assert_called_once()
        assert result == expected

    def test_loads_files_with_completion_counts(self, service: UnifiedDataService) -> None:
        """Loads files with completion counts when requested."""
        expected = [FileInfo(filename="test.csv", source=FileSourceType.CSV)]
        service._file_service.find_available_files_with_completion_count.return_value = expected

        result = service.load_available_files(load_completion_counts=True)

        service._file_service.find_available_files_with_completion_count.assert_called_once()
        assert result == expected

    def test_calls_callback_with_files(self, service: UnifiedDataService) -> None:
        """Calls callback with loaded files."""
        expected = [FileInfo(filename="test.csv", source=FileSourceType.CSV)]
        service._file_service.find_available_files.return_value = expected
        callback = MagicMock()

        result = service.load_available_files(on_files_loaded=callback)

        callback.assert_called_once_with(expected)
        assert result == expected

    def test_works_without_callback(self, service: UnifiedDataService) -> None:
        """Works when no callback provided."""
        expected = [FileInfo(filename="test.csv", source=FileSourceType.CSV)]
        service._file_service.find_available_files.return_value = expected

        result = service.load_available_files()

        assert result == expected


class TestDatabaseMode:
    """Tests for database mode methods."""

    def test_toggle_database_mode(self, service: UnifiedDataService) -> None:
        """Toggles mode on file service and clears caches."""
        service.toggle_database_mode(True)

        service._file_service.toggle_database_mode.assert_called_once_with(True)
        service._cache_service.clear_all_caches_on_mode_change.assert_called_once()

    def test_get_database_mode(self, service: UnifiedDataService) -> None:
        """Gets mode from file service."""
        service._file_service.get_database_mode.return_value = True

        result = service.get_database_mode()

        assert result is True


class TestCacheOperations:
    """Tests for cache operations."""

    def test_clear_file_cache(self, service: UnifiedDataService) -> None:
        """Clears cache via cache service."""
        service.clear_file_cache("test.csv")

        service._cache_service.clear_file_cache.assert_called_once_with("test.csv")

    def test_invalidate_marker_status_cache(self, service: UnifiedDataService) -> None:
        """Invalidates marker cache via cache service."""
        service.invalidate_marker_status_cache("test.csv")

        service._cache_service.invalidate_marker_status_cache.assert_called_once_with("test.csv")

    def test_clear_algorithm_caches(self, service: UnifiedDataService) -> None:
        """Clears algorithm caches via cache service."""
        service.clear_algorithm_caches()

        service._cache_service.clear_all_algorithm_caches.assert_called_once()


class TestDataFolder:
    """Tests for data folder operations."""

    def test_set_data_folder(self, service: UnifiedDataService) -> None:
        """Sets data folder via file service."""
        service._file_service.set_data_folder.return_value = True

        result = service.set_data_folder("/path/to/data")

        service._file_service.set_data_folder.assert_called_once_with("/path/to/data")
        assert result is True

    def test_get_data_folder(self, service: UnifiedDataService) -> None:
        """Gets data folder from file service."""
        service._file_service.get_data_folder.return_value = "/path/to/data"

        result = service.get_data_folder()

        assert result == "/path/to/data"


class TestActivityDataOperations:
    """Tests for activity data operations."""

    def test_get_activity_column_preferences(self, service: UnifiedDataService) -> None:
        """Gets preferences from data manager."""
        service._data_manager.preferred_activity_column = "vector_magnitude"
        service._data_manager.choi_activity_column = "axis_y"

        result = service.get_activity_column_preferences()

        assert result == ("vector_magnitude", "axis_y")

    def test_get_available_activity_columns(self, service: UnifiedDataService, mock_db_manager: MagicMock) -> None:
        """Gets available columns from database manager."""
        mock_db_manager.get_available_activity_columns.return_value = [
            "axis_y",
            "vector_magnitude",
        ]

        result = service.get_available_activity_columns("test.csv")

        mock_db_manager.get_available_activity_columns.assert_called_once_with("test.csv")
        assert "axis_y" in result

    def test_load_raw_activity_data(self, service: UnifiedDataService, mock_db_manager: MagicMock) -> None:
        """Loads raw data from database manager."""
        timestamps = [datetime(2024, 1, 15, 12)]
        activities = [100.0]
        mock_db_manager.load_raw_activity_data.return_value = (timestamps, activities)

        result = service.load_raw_activity_data(
            "test.csv",
            start_time=datetime(2024, 1, 15),
            end_time=datetime(2024, 1, 16),
            activity_column="axis_y",
        )

        assert result == (timestamps, activities)

    def test_load_activity_data_only(self, service: UnifiedDataService) -> None:
        """Loads specific column via data manager."""
        expected = ([datetime(2024, 1, 15, 12)], [100.0])
        service._data_manager.load_activity_data_only.return_value = expected

        result = service.load_activity_data_only(
            "test.csv",
            datetime(2024, 1, 15),
            ActivityDataPreference.AXIS_Y,
            hours=24,
        )

        service._data_manager.load_activity_data_only.assert_called_once_with(
            "test.csv",
            datetime(2024, 1, 15),
            ActivityDataPreference.AXIS_Y,
            24,
        )
        assert result == expected


class TestDiaryDataOperations:
    """Tests for diary data operations."""

    def test_check_current_participant_has_diary_data_no_file(self, service: UnifiedDataService) -> None:
        """Returns False when no file selected."""
        result = service.check_current_participant_has_diary_data("")
        assert result is False

    def test_check_current_participant_has_diary_data(self, service: UnifiedDataService) -> None:
        """Checks diary data via diary service."""
        service._diary_service.check_participant_has_diary_data.return_value = True

        with patch("sleep_scoring_app.services.unified_data_service.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "001"
            mock_info.full_id = "TEST-001"
            mock_extract.return_value = mock_info

            result = service.check_current_participant_has_diary_data("TEST-001.csv")

        assert result is True
        service._diary_service.check_participant_has_diary_data.assert_called_once_with("TEST-001")

    def test_check_current_participant_returns_false_for_unknown(self, service: UnifiedDataService) -> None:
        """Returns False when participant ID is unknown."""
        with patch("sleep_scoring_app.services.unified_data_service.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "UNKNOWN"
            mock_extract.return_value = mock_info

            result = service.check_current_participant_has_diary_data("invalid.csv")

        assert result is False

    def test_load_diary_data_for_current_file_no_file(self, service: UnifiedDataService) -> None:
        """Returns empty list when no file selected."""
        result = service.load_diary_data_for_current_file("")
        assert result == []

    def test_load_diary_data_for_current_file(self, service: UnifiedDataService) -> None:
        """Loads diary data via diary service."""
        expected_diary = [{"date": "2024-01-15", "bedtime": "22:00"}]
        service._diary_service.get_diary_data_for_participant.return_value = expected_diary

        with patch("sleep_scoring_app.services.unified_data_service.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "001"
            mock_info.full_id = "TEST-001"
            mock_extract.return_value = mock_info

            result = service.load_diary_data_for_current_file("TEST-001.csv")

        assert result == expected_diary

    def test_diary_service_property(self, service: UnifiedDataService) -> None:
        """Returns diary service instance."""
        result = service.diary_service
        assert result is service._diary_service


class TestSingletonPattern:
    """Tests for singleton pattern."""

    def test_get_instance_returns_last_created(self, mock_db_manager: MagicMock) -> None:
        """get_instance returns the last created service."""
        with (
            patch("sleep_scoring_app.services.unified_data_service.FileService"),
            patch("sleep_scoring_app.services.unified_data_service.DiaryService"),
            patch("sleep_scoring_app.services.unified_data_service.CacheService"),
        ):
            service1 = UnifiedDataService(mock_db_manager)
            service2 = UnifiedDataService(mock_db_manager)

            assert UnifiedDataService.get_instance() is service2
            assert UnifiedDataService.get_instance() is not service1
