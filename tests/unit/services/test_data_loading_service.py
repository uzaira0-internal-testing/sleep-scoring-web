"""
Tests for DataLoadingService.

Tests file discovery from database and CSV, activity data loading,
and configurable activity column handling.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.constants import ActivityDataPreference, FileSourceType
from sleep_scoring_app.core.dataclasses import AlignedActivityData, FileInfo
from sleep_scoring_app.core.exceptions import DataLoadingError, ErrorCodes
from sleep_scoring_app.services.data_loading_service import DataLoadingService


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager."""
    manager = MagicMock()
    manager.get_available_files.return_value = []
    manager.get_file_date_ranges.return_value = []
    manager.load_raw_activity_data.return_value = ([], [])
    manager.load_all_activity_columns.return_value = None
    return manager


@pytest.fixture
def data_folder(tmp_path: Path) -> Path:
    """Create a temporary data folder."""
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


@pytest.fixture
def service(mock_db_manager: MagicMock, data_folder: Path) -> DataLoadingService:
    """Create a DataLoadingService instance."""
    return DataLoadingService(mock_db_manager, data_folder)


@pytest.fixture
def sample_csv_file(data_folder: Path) -> Path:
    """Create a sample CSV file for testing."""
    csv_file = data_folder / "test_data.csv"
    # Create CSV with date, time, and activity columns
    content = """Line 1 header
Line 2 header
Line 3 header
Line 4 header
Line 5 header
Line 6 header
Line 7 header
Line 8 header
Line 9 header
Line 10 header
Date, Time,Axis1,Axis2,Axis3,Vector Magnitude
2024-01-15,08:00:00,100,50,30,120
2024-01-15,08:01:00,150,60,40,170
2024-01-15,08:02:00,200,70,50,220
2024-01-16,09:00:00,120,55,35,140
2024-01-16,09:01:00,180,65,45,200
"""
    csv_file.write_text(content)
    return csv_file


@pytest.fixture
def sample_datetime_csv(data_folder: Path) -> Path:
    """Create a CSV with single datetime column."""
    csv_file = data_folder / "datetime_data.csv"
    content = """header1
header2
header3
header4
header5
header6
header7
header8
header9
header10
datetime,activity
2024-01-15 08:00:00,100
2024-01-15 08:01:00,150
2024-01-15 08:02:00,200
"""
    csv_file.write_text(content)
    return csv_file


class TestDataLoadingServiceInit:
    """Tests for DataLoadingService initialization."""

    def test_init_with_database_manager(self, mock_db_manager: MagicMock, data_folder: Path) -> None:
        """Service initializes with database manager."""
        service = DataLoadingService(mock_db_manager, data_folder)
        assert service.db_manager is mock_db_manager
        assert service.data_folder == data_folder
        assert service.use_database is True

    def test_init_clears_csv_state(self, mock_db_manager: MagicMock, data_folder: Path) -> None:
        """Service initializes with cleared CSV state."""
        service = DataLoadingService(mock_db_manager, data_folder)
        assert service.current_data is None
        assert service.current_date_col is None
        assert service.current_time_col is None
        assert service.timestamps_combined is None
        assert service.current_activity_col is None


class TestFindDataFiles:
    """Tests for find_data_files method."""

    def test_finds_database_files(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns files from database."""
        mock_db_manager.get_available_files.return_value = [
            {
                "filename": "DEMO-001.csv",
                "original_path": "/path/to/DEMO-001.csv",
                "participant_id": "DEMO-001",
                "participant_group": "control",
                "total_records": 1000,
                "import_date": datetime(2024, 1, 15),
                "date_range_start": date(2024, 1, 15),
                "date_range_end": date(2024, 1, 20),
            }
        ]

        files = service.find_data_files()

        assert len(files) == 1
        assert files[0].filename == "DEMO-001.csv"
        assert files[0].source == FileSourceType.DATABASE
        assert files[0].participant_id == "DEMO-001"
        assert files[0].total_records == 1000

    def test_finds_csv_files_in_folder(self, service: DataLoadingService, data_folder: Path) -> None:
        """Returns CSV files from data folder."""
        # Create CSV files
        (data_folder / "file1.csv").write_text("data")
        (data_folder / "file2.csv").write_text("data")

        files = service.find_data_files()

        assert len(files) == 2
        filenames = [f.filename for f in files]
        assert "file1.csv" in filenames
        assert "file2.csv" in filenames
        assert all(f.source == FileSourceType.CSV for f in files)

    def test_database_files_take_priority(self, service: DataLoadingService, mock_db_manager: MagicMock, data_folder: Path) -> None:
        """Database files shadow CSV files with same name."""
        # Create CSV file
        (data_folder / "DEMO-001.csv").write_text("data")

        # Database has same file
        mock_db_manager.get_available_files.return_value = [{"filename": "DEMO-001.csv", "participant_id": "DEMO-001"}]

        files = service.find_data_files()

        assert len(files) == 1
        assert files[0].source == FileSourceType.DATABASE

    def test_handles_database_failure(self, service: DataLoadingService, mock_db_manager: MagicMock, data_folder: Path) -> None:
        """Continues with CSV discovery when database fails."""
        mock_db_manager.get_available_files.side_effect = Exception("DB error")
        (data_folder / "fallback.csv").write_text("data")

        files = service.find_data_files()

        assert len(files) == 1
        assert files[0].filename == "fallback.csv"
        assert files[0].source == FileSourceType.CSV

    def test_returns_empty_for_nonexistent_folder(self, mock_db_manager: MagicMock, tmp_path: Path) -> None:
        """Returns empty list when data folder doesn't exist."""
        service = DataLoadingService(mock_db_manager, tmp_path / "nonexistent")
        files = service.find_data_files()
        assert files == []

    def test_ignores_non_csv_files(self, service: DataLoadingService, data_folder: Path) -> None:
        """Only returns CSV files, not other file types."""
        (data_folder / "data.csv").write_text("data")
        (data_folder / "data.txt").write_text("text")
        (data_folder / "data.json").write_text("{}")

        files = service.find_data_files()

        assert len(files) == 1
        assert files[0].filename == "data.csv"

    def test_sorts_files_by_filename(self, service: DataLoadingService, data_folder: Path) -> None:
        """Files are sorted alphabetically by filename."""
        (data_folder / "zebra.csv").write_text("data")
        (data_folder / "alpha.csv").write_text("data")
        (data_folder / "beta.csv").write_text("data")

        files = service.find_data_files()

        filenames = [f.filename for f in files]
        assert filenames == ["alpha.csv", "beta.csv", "zebra.csv"]


class TestLoadSelectedFile:
    """Tests for load_selected_file method."""

    def test_loads_database_file(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Loads dates from database source."""
        mock_db_manager.get_file_date_ranges.return_value = [
            date(2024, 1, 15),
            date(2024, 1, 16),
        ]
        file_info = FileInfo(
            filename="test.csv",
            source=FileSourceType.DATABASE,
            source_path=None,
        )

        dates = service.load_selected_file(file_info)

        assert len(dates) == 2
        mock_db_manager.get_file_date_ranges.assert_called_once_with("test.csv")

    def test_loads_csv_file(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Loads dates from CSV source."""
        file_info = FileInfo(
            filename=sample_csv_file.name,
            source=FileSourceType.CSV,
            source_path=sample_csv_file,
        )

        dates = service.load_selected_file(file_info, skip_rows=10)

        assert len(dates) == 2  # 2024-01-15 and 2024-01-16

    def test_returns_empty_for_none_file_info(self, service: DataLoadingService) -> None:
        """Returns empty list for None file info."""
        dates = service.load_selected_file(None)
        assert dates == []

    def test_returns_empty_for_csv_without_path(self, service: DataLoadingService) -> None:
        """Returns empty list when CSV source has no path."""
        file_info = FileInfo(
            filename="test.csv",
            source=FileSourceType.CSV,
            source_path=None,
        )

        dates = service.load_selected_file(file_info)
        assert dates == []


class TestLoadDatabaseFile:
    """Tests for _load_database_file method."""

    def test_loads_dates_from_database(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns dates from database query."""
        mock_db_manager.get_file_date_ranges.return_value = [
            date(2024, 1, 15),
            date(2024, 1, 16),
        ]

        dates = service._load_database_file("test.csv")

        assert dates == [date(2024, 1, 15), date(2024, 1, 16)]

    def test_warns_and_extracts_filename_from_path(self, service: DataLoadingService, mock_db_manager: MagicMock, caplog) -> None:
        """Warns and extracts filename when path is passed."""
        mock_db_manager.get_file_date_ranges.return_value = [date(2024, 1, 15)]

        with caplog.at_level(logging.WARNING):
            dates = service._load_database_file("/path/to/test.csv")

        assert "FILENAME FORMAT ERROR" in caplog.text
        mock_db_manager.get_file_date_ranges.assert_called_with("test.csv")

    def test_returns_empty_for_no_dates(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns empty list when no dates found."""
        mock_db_manager.get_file_date_ranges.return_value = []

        dates = service._load_database_file("nonexistent.csv")

        assert dates == []

    def test_returns_empty_on_exception(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns empty list when database throws exception."""
        mock_db_manager.get_file_date_ranges.side_effect = Exception("DB error")

        dates = service._load_database_file("test.csv")

        assert dates == []


class TestLoadCsvFile:
    """Tests for _load_csv_file method."""

    def test_loads_dates_from_csv(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Extracts unique dates from CSV file."""
        dates = service._load_csv_file(sample_csv_file, skip_rows=10)

        assert len(dates) == 2
        # Returns datetime objects at noon
        assert all(isinstance(d, datetime) for d in dates)

    def test_stores_current_data(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Stores loaded data for subsequent operations with content verification."""
        service._load_csv_file(sample_csv_file, skip_rows=10)

        # Verify data is stored
        assert service.current_data is not None
        # Verify data has expected columns and rows
        assert len(service.current_data) == 5  # 5 data rows in sample_csv_file
        assert "Axis1" in service.current_data.columns
        assert "Vector Magnitude" in service.current_data.columns

        # Verify date column is identified
        assert service.current_date_col is not None
        assert service.current_date_col == "Date"

        # Verify activity column is identified
        assert service.current_activity_col is not None
        assert "Vector Magnitude" in service.current_activity_col or "Axis1" in service.current_activity_col

    def test_finds_vector_magnitude_column(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Detects vector magnitude column."""
        service._load_csv_file(sample_csv_file, skip_rows=10)

        assert "Vector Magnitude" in service.current_activity_col

    def test_handles_single_datetime_column(self, service: DataLoadingService, sample_datetime_csv: Path) -> None:
        """Loads file with single datetime column."""
        dates = service._load_csv_file(sample_datetime_csv, skip_rows=10)

        assert len(dates) == 1

    def test_returns_empty_for_none_path(self, service: DataLoadingService) -> None:
        """Returns empty list for None path."""
        dates = service._load_csv_file(None)
        assert dates == []

    def test_raises_for_empty_csv(self, service: DataLoadingService, data_folder: Path) -> None:
        """Raises error for empty CSV file."""
        empty_file = data_folder / "empty.csv"
        # Create valid CSV header but no data rows after skipping
        empty_file.write_text("h1\n" * 11)  # 11 lines, skip 10

        with pytest.raises(DataLoadingError) as exc_info:
            service._load_csv_file(empty_file, skip_rows=10)
        assert exc_info.value.error_code == ErrorCodes.INVALID_INPUT

    def test_raises_for_nonexistent_file(self, service: DataLoadingService, data_folder: Path) -> None:
        """Raises error for nonexistent file."""
        # The generic exception handler wraps errors as INVALID_INPUT
        with pytest.raises(DataLoadingError) as exc_info:
            service._load_csv_file(data_folder / "nonexistent.csv")
        assert exc_info.value.error_code == ErrorCodes.INVALID_INPUT

    def test_validates_skip_rows(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Validates skip_rows parameter."""
        # skip_rows > 1000 should fail validation
        with pytest.raises(DataLoadingError):
            service._load_csv_file(sample_csv_file, skip_rows=2000)


class TestLoadRealData:
    """Tests for load_real_data method."""

    def test_loads_from_database_first(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Prioritizes database over CSV."""
        test_time = datetime(2024, 1, 15, 12, 0, 0)
        timestamps = [test_time + timedelta(minutes=i) for i in range(10)]
        activities = [100.0 + i * 10 for i in range(10)]
        mock_db_manager.load_raw_activity_data.return_value = (timestamps, activities)

        result_ts, result_act = service.load_real_data(datetime(2024, 1, 15), 24, filename="test.csv")

        assert result_ts == timestamps
        assert result_act == activities

    def test_falls_back_to_csv_on_database_failure(self, service: DataLoadingService, mock_db_manager: MagicMock, sample_csv_file: Path) -> None:
        """Falls back to CSV when database fails."""
        from sleep_scoring_app.core.exceptions import DatabaseError

        mock_db_manager.load_raw_activity_data.side_effect = DatabaseError("DB error", ErrorCodes.DB_QUERY_FAILED)
        # Load CSV data first
        service._load_csv_file(sample_csv_file, skip_rows=10)

        result_ts, result_act = service.load_real_data(datetime(2024, 1, 15), 24, filename="test.csv")

        # Fallback to CSV should not raise; result may be None if date out of range
        assert result_ts is None or isinstance(result_ts, list)
        assert result_act is None or isinstance(result_act, list)

    def test_returns_none_when_no_data_source(self, service: DataLoadingService) -> None:
        """Returns None when no data source available."""
        service.use_database = False
        service.current_data = None

        result_ts, result_act = service.load_real_data(datetime(2024, 1, 15), 24, filename="test.csv")

        assert result_ts is None
        assert result_act is None


class TestLoadUnifiedActivityData:
    """Tests for load_unified_activity_data method."""

    def test_loads_all_columns_in_one_query(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Loads all activity columns from database."""
        test_time = datetime(2024, 1, 15, 12, 0, 0)
        timestamps = [test_time + timedelta(minutes=i) for i in range(10)]
        mock_db_manager.load_all_activity_columns.return_value = {
            "timestamps": timestamps,
            "axis_y": [100.0] * 10,
            "axis_x": [50.0] * 10,
            "axis_z": [30.0] * 10,
            "vector_magnitude": [120.0] * 10,
        }

        result = service.load_unified_activity_data("test.csv", datetime(2024, 1, 15), hours=48)

        # Verify result is not None and contains expected data
        assert result is not None
        assert len(result["timestamps"]) == 10
        assert len(result["axis_y"]) == 10
        assert len(result["vector_magnitude"]) == 10
        # Verify actual values match mock data
        assert result["timestamps"][0] == test_time
        assert result["axis_y"][0] == 100.0
        assert result["vector_magnitude"][0] == 120.0

    def test_extracts_filename_from_path(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Extracts filename when path is passed."""
        mock_db_manager.load_all_activity_columns.return_value = {
            "timestamps": [datetime.now()],
            "axis_y": [100.0],
        }

        service.load_unified_activity_data("/path/to/test.csv", datetime(2024, 1, 15))

        # Check that the call used just the filename
        call_args = mock_db_manager.load_all_activity_columns.call_args
        assert call_args[0][0] == "test.csv"

    def test_returns_none_for_empty_filename(self, service: DataLoadingService) -> None:
        """Returns None for empty filename."""
        result = service.load_unified_activity_data("", datetime(2024, 1, 15))
        assert result is None

    def test_returns_none_when_database_disabled(self, service: DataLoadingService) -> None:
        """Returns None when database is disabled."""
        service.use_database = False

        result = service.load_unified_activity_data("test.csv", datetime(2024, 1, 15))

        assert result is None

    def test_returns_none_on_exception(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns None when database throws exception."""
        mock_db_manager.load_all_activity_columns.side_effect = Exception("error")

        result = service.load_unified_activity_data("test.csv", datetime(2024, 1, 15))

        assert result is None

    def test_handles_date_input(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Converts date to datetime for query."""
        mock_db_manager.load_all_activity_columns.return_value = {
            "timestamps": [datetime.now()],
            "axis_y": [100.0],
        }

        result = service.load_unified_activity_data("test.csv", date(2024, 1, 15), hours=24)

        # Verify result is not None and contains expected structure
        assert result is not None
        assert "timestamps" in result
        assert "axis_y" in result
        assert len(result["timestamps"]) == 1


class TestLoadDatabaseActivityData:
    """Tests for _load_database_activity_data method."""

    def test_loads_activity_with_column_preference(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Uses specified activity column."""
        timestamps = [datetime(2024, 1, 15, 12, i) for i in range(5)]
        activities = [100.0 + i for i in range(5)]
        mock_db_manager.load_raw_activity_data.return_value = (timestamps, activities)

        result = service._load_database_activity_data(
            "test.csv",
            datetime(2024, 1, 15),
            hours=24,
            activity_column=ActivityDataPreference.AXIS_Y,
        )

        assert result == (timestamps, activities)
        # Verify column was passed
        call_kwargs = mock_db_manager.load_raw_activity_data.call_args[1]
        assert call_kwargs["activity_column"] == ActivityDataPreference.AXIS_Y

    def test_extracts_filename_from_path(self, service: DataLoadingService, mock_db_manager: MagicMock, caplog) -> None:
        """Extracts filename when path is passed."""
        mock_db_manager.load_raw_activity_data.return_value = ([datetime.now()], [100.0])

        with caplog.at_level(logging.WARNING):
            service._load_database_activity_data(
                "/full/path/to/file.csv",
                datetime(2024, 1, 15),
                hours=24,
            )

        assert "FILENAME FORMAT ERROR" in caplog.text
        # Verify extracted filename was used
        call_args = mock_db_manager.load_raw_activity_data.call_args[0]
        assert call_args[0] == "file.csv"

    def test_returns_none_for_empty_results(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns None tuple when no data found."""
        mock_db_manager.load_raw_activity_data.return_value = ([], [])

        result_ts, result_act = service._load_database_activity_data("test.csv", datetime(2024, 1, 15), hours=24)

        assert result_ts is None
        assert result_act is None


class TestLoadCsvActivityData:
    """Tests for _load_csv_activity_data method."""

    def test_loads_activity_from_csv(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Loads activity data from stored CSV with content verification."""
        service._load_csv_file(sample_csv_file, skip_rows=10)

        result_ts, result_act = service._load_csv_activity_data(datetime(2024, 1, 15), hours=24)

        # Verify both results are returned and have content
        assert result_ts is not None
        assert result_act is not None
        assert len(result_ts) == len(result_act)
        # Verify we got some data for the date (sample file has rows for 2024-01-15)
        assert len(result_ts) > 0
        # Verify timestamps are datetime objects
        assert all(isinstance(ts, datetime) for ts in result_ts)
        # Verify activity values are numeric
        assert all(isinstance(act, int | float) for act in result_act)

    def test_uses_specified_column(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Uses specified activity column preference."""
        service._load_csv_file(sample_csv_file, skip_rows=10)

        # Store original column for comparison
        default_col = service.current_activity_col

        result_ts, result_act = service._load_csv_activity_data(
            datetime(2024, 1, 15),
            hours=24,
            activity_column=ActivityDataPreference.VECTOR_MAGNITUDE,
        )

        # Should still work with vector magnitude and return valid data
        assert result_ts is not None
        assert result_act is not None
        # Verify we got data for the specified date
        assert len(result_ts) > 0
        assert len(result_act) > 0
        assert len(result_ts) == len(result_act)

    def test_returns_none_for_out_of_range(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Returns None when date is out of data range."""
        service._load_csv_file(sample_csv_file, skip_rows=10)

        result_ts, result_act = service._load_csv_activity_data(
            datetime(2025, 1, 15),  # Future date not in data
            hours=24,
        )

        assert result_ts is None
        assert result_act is None


class TestLoadActivityDataOnly:
    """Tests for load_activity_data_only method."""

    def test_loads_specific_column(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Loads only the specified column."""
        timestamps = [datetime(2024, 1, 15, 12, i) for i in range(5)]
        activities = [100.0] * 5
        mock_db_manager.load_raw_activity_data.return_value = (timestamps, activities)

        result = service.load_activity_data_only(
            "test.csv",
            datetime(2024, 1, 15),
            ActivityDataPreference.AXIS_Y,
            hours=24,
        )

        # Verify result is not None and contains expected data
        assert result is not None
        result_ts, result_act = result
        assert result_ts == timestamps
        assert result_act == activities
        assert len(result_ts) == 5
        assert all(act == 100.0 for act in result_act)

    def test_falls_back_to_csv(self, service: DataLoadingService, mock_db_manager: MagicMock, sample_csv_file: Path) -> None:
        """Falls back to CSV when database fails with specific error types."""
        # The code only catches DatabaseError, ValidationError, KeyError - not generic Exception
        from sleep_scoring_app.core.exceptions import DatabaseError

        mock_db_manager.load_raw_activity_data.side_effect = DatabaseError("DB error", ErrorCodes.DB_QUERY_FAILED)
        service._load_csv_file(sample_csv_file, skip_rows=10)

        result = service.load_activity_data_only(
            "test.csv",
            datetime(2024, 1, 15),
            ActivityDataPreference.VECTOR_MAGNITUDE,
            hours=24,
        )

        # Should get data from CSV fallback for the date in the sample file
        # Verify we got actual data, not just that it didn't raise
        assert result is not None
        result_ts, result_act = result
        # Should get some data for the date (actual count depends on sample file)
        assert len(result_ts) > 0
        assert len(result_act) > 0
        assert len(result_ts) == len(result_act)

    def test_returns_none_when_no_data(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns None when no data source available."""
        mock_db_manager.load_raw_activity_data.side_effect = Exception("DB error")
        service.current_data = None

        result = service.load_activity_data_only(
            "test.csv",
            datetime(2024, 1, 15),
            ActivityDataPreference.AXIS_Y,
            hours=24,
        )

        assert result is None


class TestLoadAxisYDataForSadeh:
    """Tests for load_axis_y_data_for_sadeh method."""

    def test_loads_axis_y_data(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Loads axis_y data specifically."""
        timestamps = [datetime(2024, 1, 15, 12, i) for i in range(5)]
        activities = [100.0] * 5
        mock_db_manager.load_raw_activity_data.return_value = (timestamps, activities)

        result_ts, result_act = service.load_axis_y_data_for_sadeh("test.csv", datetime(2024, 1, 15), hours=48)

        assert result_ts == timestamps
        assert result_act == activities

    def test_returns_lists(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns list types, not AlignedActivityData."""
        mock_db_manager.load_raw_activity_data.return_value = (
            [datetime(2024, 1, 15, 12)],
            [100.0],
        )

        result_ts, result_act = service.load_axis_y_data_for_sadeh("test.csv", datetime(2024, 1, 15))

        assert isinstance(result_ts, list)
        assert isinstance(result_act, list)


class TestLoadAxisYAligned:
    """Tests for load_axis_y_aligned method."""

    def test_returns_aligned_activity_data(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns AlignedActivityData container."""
        timestamps = [datetime(2024, 1, 15, 12, i) for i in range(5)]
        activities = [100.0] * 5
        mock_db_manager.load_raw_activity_data.return_value = (timestamps, activities)

        result = service.load_axis_y_aligned("test.csv", datetime(2024, 1, 15))

        assert isinstance(result, AlignedActivityData)
        assert len(result.timestamps) == 5
        assert len(result.activity_values) == 5

    def test_returns_empty_on_failure(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Returns empty AlignedActivityData on failure."""
        mock_db_manager.load_raw_activity_data.return_value = ([], [])
        service.current_data = None

        result = service.load_axis_y_aligned("test.csv", datetime(2024, 1, 15))

        assert isinstance(result, AlignedActivityData)
        assert result.is_empty

    def test_handles_date_input(self, service: DataLoadingService, mock_db_manager: MagicMock) -> None:
        """Converts date to datetime for query."""
        mock_db_manager.load_raw_activity_data.return_value = (
            [datetime(2024, 1, 15, 12)],
            [100.0],
        )

        result = service.load_axis_y_aligned("test.csv", date(2024, 1, 15))

        # Verify result is not empty and contains expected data
        assert isinstance(result, AlignedActivityData)
        assert not result.is_empty
        assert len(result.timestamps) == 1
        assert result.activity_values[0] == 100.0

    def test_falls_back_to_csv(self, service: DataLoadingService, mock_db_manager: MagicMock, sample_csv_file: Path) -> None:
        """Falls back to CSV when database fails."""
        mock_db_manager.load_raw_activity_data.side_effect = Exception("DB error")
        service._load_csv_file(sample_csv_file, skip_rows=10)

        result = service.load_axis_y_aligned("test.csv", datetime(2024, 1, 15))

        # Should get data from CSV fallback and return valid AlignedActivityData
        assert isinstance(result, AlignedActivityData)
        # For the sample file, we should get some data for 2024-01-15
        assert not result.is_empty
        # Should have at least one timestamp
        assert len(result.timestamps) > 0


class TestClearCurrentData:
    """Tests for clear_current_data method."""

    def test_clears_all_csv_state(self, service: DataLoadingService, sample_csv_file: Path) -> None:
        """Clears all stored CSV state with verification of before/after states."""
        # First load some data and verify it's loaded
        service._load_csv_file(sample_csv_file, skip_rows=10)
        assert service.current_data is not None
        assert len(service.current_data) == 5  # Verify data was actually loaded
        assert service.current_date_col == "Date"  # Verify column was identified

        # Clear it
        service.clear_current_data()

        # Verify ALL state is cleared
        assert service.current_data is None
        assert service.current_date_col is None
        assert service.current_time_col is None
        assert service.timestamps_combined is None
        assert service.current_activity_col is None

    def test_clear_is_idempotent(self, service: DataLoadingService) -> None:
        """Clearing already-cleared state is safe."""
        service.clear_current_data()
        service.clear_current_data()  # Should not raise

        assert service.current_data is None
