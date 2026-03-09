"""
Tests for DataManager service.

Tests the facade that delegates to DataLoadingService, MetricsCalculationService, and DataQueryService.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import ActivityDataPreference
from sleep_scoring_app.core.exceptions import DataLoadingError
from sleep_scoring_app.services.data_service import DataManager


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock DatabaseManager."""
    return MagicMock()


@pytest.fixture
def data_manager(mock_db_manager: MagicMock) -> DataManager:
    """Create a DataManager with mocked dependencies."""
    with (
        patch("sleep_scoring_app.services.data_service.DataLoadingService") as mock_loading,
        patch("sleep_scoring_app.services.data_service.MetricsCalculationService") as mock_metrics,
        patch("sleep_scoring_app.services.data_service.DataQueryService") as mock_query,
    ):
        manager = DataManager(mock_db_manager)
        manager._loading_service = mock_loading.return_value
        manager._metrics_service = mock_metrics.return_value
        manager._query_service = mock_query.return_value
        return manager


class TestDataManagerInit:
    """Tests for DataManager initialization."""

    def test_creates_with_provided_db_manager(self, mock_db_manager: MagicMock) -> None:
        """Uses provided database manager."""
        with (
            patch("sleep_scoring_app.services.data_service.DataLoadingService"),
            patch("sleep_scoring_app.services.data_service.MetricsCalculationService"),
            patch("sleep_scoring_app.services.data_service.DataQueryService"),
        ):
            manager = DataManager(mock_db_manager)

        assert manager.db_manager is mock_db_manager

    def test_creates_default_db_manager_when_none_provided(self) -> None:
        """Creates default DatabaseManager when none provided."""
        with (
            patch("sleep_scoring_app.services.data_service.DataLoadingService"),
            patch("sleep_scoring_app.services.data_service.MetricsCalculationService"),
            patch("sleep_scoring_app.services.data_service.DataQueryService"),
            patch("sleep_scoring_app.services.data_service.DatabaseManager") as mock_db_class,
        ):
            manager = DataManager(None)

        assert manager.db_manager is mock_db_class.return_value

    def test_default_activity_preferences(self, data_manager: DataManager) -> None:
        """Initializes with default activity column preferences."""
        # Reinitialize to check defaults
        with (
            patch("sleep_scoring_app.services.data_service.DataLoadingService"),
            patch("sleep_scoring_app.services.data_service.MetricsCalculationService"),
            patch("sleep_scoring_app.services.data_service.DataQueryService"),
        ):
            manager = DataManager(MagicMock())

        assert manager.preferred_activity_column == ActivityDataPreference.AXIS_Y
        assert manager.choi_activity_column == ActivityDataPreference.AXIS_Y

    def test_use_database_enabled_by_default(self, data_manager: DataManager) -> None:
        """Database mode is enabled by default."""
        with (
            patch("sleep_scoring_app.services.data_service.DataLoadingService"),
            patch("sleep_scoring_app.services.data_service.MetricsCalculationService"),
            patch("sleep_scoring_app.services.data_service.DataQueryService"),
        ):
            manager = DataManager(MagicMock())

        assert manager.use_database is True

    def test_initializes_all_services(self, mock_db_manager: MagicMock) -> None:
        """Initializes all specialized services."""
        with (
            patch("sleep_scoring_app.services.data_service.DataLoadingService") as mock_loading,
            patch("sleep_scoring_app.services.data_service.MetricsCalculationService") as mock_metrics,
            patch("sleep_scoring_app.services.data_service.DataQueryService") as mock_query,
        ):
            manager = DataManager(mock_db_manager)

        mock_loading.assert_called_once()
        mock_metrics.assert_called_once()
        mock_query.assert_called_once()


class TestSetActivityColumnPreferences:
    """Tests for set_activity_column_preferences method."""

    def test_sets_preferred_activity_column(self, data_manager: DataManager) -> None:
        """Sets preferred activity column."""
        data_manager.set_activity_column_preferences(ActivityDataPreference.AXIS_X, ActivityDataPreference.AXIS_Z)

        assert data_manager.preferred_activity_column == ActivityDataPreference.AXIS_X

    def test_sets_choi_activity_column(self, data_manager: DataManager) -> None:
        """Sets Choi activity column."""
        data_manager.set_activity_column_preferences(ActivityDataPreference.AXIS_X, ActivityDataPreference.AXIS_Z)

        assert data_manager.choi_activity_column == ActivityDataPreference.AXIS_Z

    def test_sets_both_to_same_value(self, data_manager: DataManager) -> None:
        """Can set both to the same value."""
        data_manager.set_activity_column_preferences(
            ActivityDataPreference.VECTOR_MAGNITUDE,
            ActivityDataPreference.VECTOR_MAGNITUDE,
        )

        assert data_manager.preferred_activity_column == ActivityDataPreference.VECTOR_MAGNITUDE
        assert data_manager.choi_activity_column == ActivityDataPreference.VECTOR_MAGNITUDE


class TestSetDataFolder:
    """Tests for set_data_folder method."""

    def test_sets_valid_folder(self, data_manager: DataManager, tmp_path: Path) -> None:
        """Sets valid folder path."""
        data_manager.set_data_folder(tmp_path)

        assert data_manager.data_folder == tmp_path

    def test_updates_loading_service_folder(self, data_manager: DataManager, tmp_path: Path) -> None:
        """Updates loading service's data folder."""
        data_manager.set_data_folder(tmp_path)

        assert data_manager._loading_service.data_folder == tmp_path

    def test_raises_for_nonexistent_folder(self, data_manager: DataManager) -> None:
        """Raises error for nonexistent folder."""
        with pytest.raises(DataLoadingError):
            data_manager.set_data_folder(Path("/nonexistent/folder"))

    def test_raises_for_file_path(self, data_manager: DataManager, tmp_path: Path) -> None:
        """Raises error when given file path instead of directory."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")

        with pytest.raises(DataLoadingError):
            data_manager.set_data_folder(test_file)


class TestFindDataFiles:
    """Tests for find_data_files method."""

    def test_delegates_to_loading_service(self, data_manager: DataManager) -> None:
        """Delegates to loading service."""
        mock_files = [MagicMock(), MagicMock()]
        data_manager._loading_service.find_data_files.return_value = mock_files

        result = data_manager.find_data_files()

        assert result is mock_files
        data_manager._loading_service.find_data_files.assert_called_once()


class TestLoadSelectedFile:
    """Tests for load_selected_file method."""

    def test_delegates_to_loading_service(self, data_manager: DataManager) -> None:
        """Delegates to loading service."""
        file_info = MagicMock()
        mock_dates = [date(2024, 1, 15), date(2024, 1, 16)]
        data_manager._loading_service.load_selected_file.return_value = mock_dates

        result = data_manager.load_selected_file(file_info, skip_rows=5)

        assert result is mock_dates
        data_manager._loading_service.load_selected_file.assert_called_once_with(file_info, 5)


class TestLoadRealData:
    """Tests for load_real_data method."""

    def test_delegates_to_loading_service(self, data_manager: DataManager) -> None:
        """Delegates to loading service."""
        target_date = datetime(2024, 1, 15, 12, 0, 0)
        mock_result = ([datetime.now()], [100.0])
        data_manager._loading_service.load_real_data.return_value = mock_result

        result = data_manager.load_real_data(target_date, 24, "test.csv", ActivityDataPreference.AXIS_X)

        assert result is mock_result
        data_manager._loading_service.load_real_data.assert_called_once_with(target_date, 24, "test.csv", ActivityDataPreference.AXIS_X)

    def test_uses_preferred_column_when_not_specified(self, data_manager: DataManager) -> None:
        """Uses preferred activity column when not specified."""
        data_manager.preferred_activity_column = ActivityDataPreference.AXIS_Z
        target_date = datetime(2024, 1, 15, 12, 0, 0)

        data_manager.load_real_data(target_date, 24, "test.csv", None)

        data_manager._loading_service.load_real_data.assert_called_once_with(target_date, 24, "test.csv", ActivityDataPreference.AXIS_Z)


class TestLoadActivityDataOnly:
    """Tests for load_activity_data_only method."""

    def test_delegates_to_loading_service(self, data_manager: DataManager) -> None:
        """Delegates to loading service."""
        target_date = datetime(2024, 1, 15)
        mock_result = ([datetime.now()], [100.0])
        data_manager._loading_service.load_activity_data_only.return_value = mock_result

        result = data_manager.load_activity_data_only("test.csv", target_date, ActivityDataPreference.AXIS_Y, 48)

        assert result is mock_result
        data_manager._loading_service.load_activity_data_only.assert_called_once_with("test.csv", target_date, ActivityDataPreference.AXIS_Y, 48)


class TestLoadAxisYDataForSadeh:
    """Tests for load_axis_y_data_for_sadeh method."""

    def test_delegates_to_loading_service(self, data_manager: DataManager) -> None:
        """Delegates to loading service."""
        target_date = datetime(2024, 1, 15)
        mock_result = ([datetime.now()], [100.0])
        data_manager._loading_service.load_axis_y_data_for_sadeh.return_value = mock_result

        result = data_manager.load_axis_y_data_for_sadeh("test.csv", target_date, 48)

        assert result is mock_result
        data_manager._loading_service.load_axis_y_data_for_sadeh.assert_called_once_with("test.csv", target_date, 48)


class TestLoadAxisYAligned:
    """Tests for load_axis_y_aligned method."""

    def test_delegates_to_loading_service(self, data_manager: DataManager) -> None:
        """Delegates to loading service."""
        target_date = datetime(2024, 1, 15)
        mock_result = MagicMock()
        data_manager._loading_service.load_axis_y_aligned.return_value = mock_result

        result = data_manager.load_axis_y_aligned("test.csv", target_date, 48)

        assert result is mock_result
        data_manager._loading_service.load_axis_y_aligned.assert_called_once_with("test.csv", target_date, 48)


class TestFilterTo24hView:
    """Tests for filter_to_24h_view method."""

    def test_delegates_to_query_service(self, data_manager: DataManager) -> None:
        """Delegates to query service."""
        timestamps = [datetime(2024, 1, 15, 12, 0)]
        activity = [100.0]
        target_date = date(2024, 1, 15)
        mock_result = ([datetime.now()], [50.0])
        data_manager._query_service.filter_to_24h_view.return_value = mock_result

        result = data_manager.filter_to_24h_view(timestamps, activity, target_date)

        assert result is mock_result
        data_manager._query_service.filter_to_24h_view.assert_called_once_with(timestamps, activity, target_date)


class TestExtractEnhancedParticipantInfo:
    """Tests for extract_enhanced_participant_info method."""

    def test_delegates_to_query_service(self, data_manager: DataManager) -> None:
        """Delegates to query service."""
        mock_info = MagicMock()
        data_manager._query_service.extract_enhanced_participant_info.return_value = mock_info

        result = data_manager.extract_enhanced_participant_info("path/to/file.csv")

        assert result is mock_info
        data_manager._query_service.extract_enhanced_participant_info.assert_called_once_with("path/to/file.csv")


class TestExtractGroupFromPath:
    """Tests for extract_group_from_path method."""

    def test_delegates_to_query_service(self, data_manager: DataManager) -> None:
        """Delegates to query service."""
        data_manager._query_service.extract_group_from_path.return_value = "G1"

        result = data_manager.extract_group_from_path("path/to/file.csv")

        assert result == "G1"
        data_manager._query_service.extract_group_from_path.assert_called_once_with("path/to/file.csv")


class TestCalculateSleepMetricsForPeriod:
    """Tests for calculate_sleep_metrics_for_period method."""

    def test_delegates_to_metrics_service(self, data_manager: DataManager) -> None:
        """Delegates to metrics service."""
        sleep_period = MagicMock()
        sadeh_results = [0, 0, 1, 1]
        choi_results = [0, 0, 0, 0]
        axis_y_data = [100.0, 200.0, 50.0, 30.0]
        x_data = [1.0, 2.0, 3.0, 4.0]
        mock_metrics = {"tst": 120}
        mock_participant = MagicMock()

        data_manager._query_service.extract_enhanced_participant_info.return_value = mock_participant
        data_manager._metrics_service.calculate_sleep_metrics_for_period.return_value = mock_metrics

        result = data_manager.calculate_sleep_metrics_for_period(
            sleep_period,
            sadeh_results,
            choi_results,
            axis_y_data,
            x_data,
            file_path="test.csv",
        )

        assert result is mock_metrics
        data_manager._metrics_service.calculate_sleep_metrics_for_period.assert_called_once()


class TestCalculateSleepMetricsForPeriodObject:
    """Tests for calculate_sleep_metrics_for_period_object method."""

    def test_delegates_to_metrics_service(self, data_manager: DataManager) -> None:
        """Delegates to metrics service."""
        sleep_period = MagicMock()
        mock_metrics_obj = MagicMock()
        mock_participant = MagicMock()

        data_manager._query_service.extract_enhanced_participant_info.return_value = mock_participant
        data_manager._metrics_service.calculate_sleep_metrics_for_period_object.return_value = mock_metrics_obj

        result = data_manager.calculate_sleep_metrics_for_period_object(sleep_period, [0], [0], [100.0], [1.0])

        assert result is mock_metrics_obj


class TestCalculateSleepMetricsForAllPeriods:
    """Tests for calculate_sleep_metrics_for_all_periods method."""

    def test_delegates_to_metrics_service(self, data_manager: DataManager) -> None:
        """Delegates to metrics service."""
        daily_markers = MagicMock()
        mock_metrics_list = [{"tst": 120}, {"tst": 180}]
        mock_participant = MagicMock()

        data_manager._query_service.extract_enhanced_participant_info.return_value = mock_participant
        data_manager._metrics_service.calculate_sleep_metrics_for_all_periods.return_value = mock_metrics_list

        result = data_manager.calculate_sleep_metrics_for_all_periods(daily_markers, [0], [0], [100.0], [1.0])

        assert result is mock_metrics_list


class TestGetDatabaseStatistics:
    """Tests for get_database_statistics method."""

    def test_delegates_to_query_service(self, data_manager: DataManager) -> None:
        """Delegates to query service."""
        mock_stats = {"files": 10, "rows": 1000}
        data_manager._query_service.get_database_statistics.return_value = mock_stats

        result = data_manager.get_database_statistics()

        assert result is mock_stats
        data_manager._query_service.get_database_statistics.assert_called_once()


class TestIsFileImported:
    """Tests for is_file_imported method."""

    def test_delegates_to_query_service(self, data_manager: DataManager) -> None:
        """Delegates to query service."""
        data_manager._query_service.is_file_imported.return_value = True

        result = data_manager.is_file_imported("test.csv")

        assert result is True
        data_manager._query_service.is_file_imported.assert_called_once_with("test.csv")


class TestGetParticipantInfoFromDatabase:
    """Tests for get_participant_info_from_database method."""

    def test_delegates_to_query_service(self, data_manager: DataManager) -> None:
        """Delegates to query service."""
        mock_info = {"participant_id": "1234"}
        data_manager._query_service.get_participant_info_from_database.return_value = mock_info

        result = data_manager.get_participant_info_from_database("test.csv")

        assert result is mock_info
        data_manager._query_service.get_participant_info_from_database.assert_called_once_with("test.csv")


class TestSetCurrentFileInfo:
    """Tests for set_current_file_info method."""

    def test_stores_file_info(self, data_manager: DataManager) -> None:
        """Stores file info."""
        file_info = {"filename": "test.csv", "path": "/data/test.csv"}

        data_manager.set_current_file_info(file_info)

        assert data_manager.current_file_info is file_info


class TestToggleDatabaseMode:
    """Tests for toggle_database_mode method."""

    def test_enables_database_mode(self, data_manager: DataManager) -> None:
        """Enables database mode."""
        data_manager.toggle_database_mode(True)

        assert data_manager.use_database is True
        assert data_manager._loading_service.use_database is True
        assert data_manager._query_service.use_database is True

    def test_disables_database_mode(self, data_manager: DataManager) -> None:
        """Disables database mode."""
        data_manager.toggle_database_mode(False)

        assert data_manager.use_database is False
        assert data_manager._loading_service.use_database is False
        assert data_manager._query_service.use_database is False


class TestClearCurrentData:
    """Tests for clear_current_data method."""

    def test_clears_loading_service_data(self, data_manager: DataManager) -> None:
        """Clears loading service data."""
        data_manager.clear_current_data()

        data_manager._loading_service.clear_current_data.assert_called_once()

    def test_clears_current_file_info(self, data_manager: DataManager) -> None:
        """Clears current file info."""
        data_manager.current_file_info = {"filename": "test.csv"}

        data_manager.clear_current_data()

        assert data_manager.current_file_info is None
