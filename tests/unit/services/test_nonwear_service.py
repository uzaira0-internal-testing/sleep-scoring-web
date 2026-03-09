"""
Tests for NonwearDataService.

Tests nonwear period file discovery, loading, and alignment with activity data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import NonwearDataSource
from sleep_scoring_app.core.dataclasses import NonwearPeriod
from sleep_scoring_app.core.exceptions import DataLoadingError, ErrorCodes
from sleep_scoring_app.services.nonwear_service import NonwearDataService


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager."""
    manager = MagicMock()
    manager.db_path = Path(":memory:")
    manager._validate_table_name = MagicMock()
    manager._validate_column_name = MagicMock()
    return manager


@pytest.fixture
def service(mock_db_manager: MagicMock) -> NonwearDataService:
    """Create a NonwearDataService instance."""
    return NonwearDataService(mock_db_manager)


@pytest.fixture
def data_folder(tmp_path: Path) -> Path:
    """Create a temporary data folder."""
    folder = tmp_path / "data"
    folder.mkdir()
    return folder


@pytest.fixture
def nonwear_sensor_file(data_folder: Path) -> Path:
    """Create a sample nonwear sensor file."""
    csv_file = data_folder / "TEST-001_nonwear_periods.csv"
    content = """start,end,participant_id
2024-01-15 08:00:00,2024-01-15 09:00:00,001
2024-01-15 14:00:00,2024-01-15 15:30:00,001
"""
    csv_file.write_text(content)
    return csv_file


@pytest.fixture
def choi_algorithm_file(data_folder: Path) -> Path:
    """Create a sample Choi algorithm file."""
    csv_file = data_folder / "TEST-001_60sec_choi.csv"
    content = """start_time,end_time,duration_minutes,start_index,end_index
2024-01-15 10:00:00,2024-01-15 11:00:00,60,100,159
2024-01-15 20:00:00,2024-01-15 20:30:00,30,700,729
"""
    csv_file.write_text(content)
    return csv_file


class TestNonwearDataServiceInit:
    """Tests for NonwearDataService initialization."""

    def test_init_with_database_manager(self, mock_db_manager: MagicMock) -> None:
        """Service initializes with database manager."""
        service = NonwearDataService(mock_db_manager)
        assert service.db_manager is mock_db_manager
        assert service.data_base_path is None

    def test_init_without_database_manager(self) -> None:
        """Service creates default database manager if none provided."""
        with patch("sleep_scoring_app.services.nonwear_service.DatabaseManager") as mock_db:
            mock_db.return_value = MagicMock()
            service = NonwearDataService(None)
            mock_db.assert_called_once()


class TestFindNonwearSensorFiles:
    """Tests for find_nonwear_sensor_files method."""

    def test_finds_nonwear_files(self, service: NonwearDataService, data_folder: Path) -> None:
        """Finds files matching *_nonwear_periods.csv pattern."""
        (data_folder / "TEST-001_nonwear_periods.csv").write_text("data")
        (data_folder / "TEST-002_nonwear_periods.csv").write_text("data")

        files = service.find_nonwear_sensor_files(data_folder)

        assert len(files) == 2
        filenames = [f.name for f in files]
        assert "TEST-001_nonwear_periods.csv" in filenames
        assert "TEST-002_nonwear_periods.csv" in filenames

    def test_ignores_non_matching_files(self, service: NonwearDataService, data_folder: Path) -> None:
        """Ignores files not matching pattern."""
        (data_folder / "TEST-001_nonwear_periods.csv").write_text("data")
        (data_folder / "other_file.csv").write_text("data")

        files = service.find_nonwear_sensor_files(data_folder)

        assert len(files) == 1

    def test_returns_empty_for_nonexistent_folder(self, service: NonwearDataService, tmp_path: Path) -> None:
        """Returns empty list for nonexistent folder."""
        files = service.find_nonwear_sensor_files(tmp_path / "nonexistent")
        assert files == []

    def test_returns_empty_on_exception(self, service: NonwearDataService, tmp_path: Path) -> None:
        """Returns empty list on exception."""
        # Create a file instead of folder to cause error
        fake_folder = tmp_path / "not_a_folder"
        fake_folder.write_text("not a folder")

        files = service.find_nonwear_sensor_files(fake_folder)
        assert files == []


class TestFindChoiAlgorithmFiles:
    """Tests for find_choi_algorithm_files method."""

    def test_finds_choi_files(self, service: NonwearDataService, data_folder: Path) -> None:
        """Finds files matching *60sec_choi.csv pattern."""
        (data_folder / "TEST-001_60sec_choi.csv").write_text("data")
        (data_folder / "TEST-002_60sec_choi.csv").write_text("data")

        files = service.find_choi_algorithm_files(data_folder)

        assert len(files) == 2

    def test_ignores_non_matching_files(self, service: NonwearDataService, data_folder: Path) -> None:
        """Ignores files not matching pattern."""
        (data_folder / "TEST-001_60sec_choi.csv").write_text("data")
        (data_folder / "other_file.csv").write_text("data")

        files = service.find_choi_algorithm_files(data_folder)

        assert len(files) == 1

    def test_returns_empty_for_nonexistent_folder(self, service: NonwearDataService, tmp_path: Path) -> None:
        """Returns empty list for nonexistent folder."""
        files = service.find_choi_algorithm_files(tmp_path / "nonexistent")
        assert files == []


class TestExtractParticipantFromFilename:
    """Tests for extract_participant_from_filename method."""

    def test_extracts_participant_id(self, service: NonwearDataService, tmp_path: Path) -> None:
        """Extracts participant ID using centralized extractor."""
        test_file = tmp_path / "TEST-001.csv"
        test_file.write_text("data")

        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "001"
            mock_extract.return_value = mock_info

            result = service.extract_participant_from_filename(test_file)

        assert result == "001"


class TestLoadNonwearSensorPeriods:
    """Tests for load_nonwear_sensor_periods method."""

    def test_loads_periods_from_file(self, service: NonwearDataService, nonwear_sensor_file: Path) -> None:
        """Loads nonwear periods from CSV file."""
        with patch.object(service, "extract_participant_from_filename") as mock_extract:
            mock_extract.return_value = "001"

            periods = service.load_nonwear_sensor_periods(nonwear_sensor_file)

        assert len(periods) == 2
        assert all(isinstance(p, NonwearPeriod) for p in periods)
        assert all(p.source == NonwearDataSource.NONWEAR_SENSOR for p in periods)

    def test_returns_empty_for_empty_file(self, service: NonwearDataService, data_folder: Path) -> None:
        """Returns empty list for empty file."""
        empty_file = data_folder / "empty_nonwear_periods.csv"
        empty_file.write_text("start,end,participant_id\n")  # Just headers

        with patch.object(service, "extract_participant_from_filename") as mock_extract:
            mock_extract.return_value = "001"
            periods = service.load_nonwear_sensor_periods(empty_file)

        assert periods == []

    def test_raises_for_missing_columns(self, service: NonwearDataService, data_folder: Path) -> None:
        """Raises error when required columns are missing."""
        bad_file = data_folder / "bad_nonwear_periods.csv"
        bad_file.write_text("only_one_column\nvalue\n")

        # Error is wrapped in FILE_OPERATION_FAILED by outer exception handler
        with pytest.raises(DataLoadingError) as exc_info:
            service.load_nonwear_sensor_periods(bad_file)

        assert exc_info.value.error_code == ErrorCodes.FILE_OPERATION_FAILED

    def test_skips_invalid_rows(self, service: NonwearDataService, data_folder: Path) -> None:
        """Skips rows with invalid data."""
        mixed_file = data_folder / "mixed_nonwear_periods.csv"
        content = """start,end,participant_id
2024-01-15 08:00:00,2024-01-15 09:00:00,001
invalid,data,here
2024-01-15 14:00:00,2024-01-15 15:30:00,001
"""
        mixed_file.write_text(content)

        with patch.object(service, "extract_participant_from_filename") as mock_extract:
            mock_extract.return_value = "001"
            periods = service.load_nonwear_sensor_periods(mixed_file)

        # Should load 2 valid periods, skip 1 invalid row
        assert len(periods) == 2


class TestLoadChoiAlgorithmPeriods:
    """Tests for load_choi_algorithm_periods method."""

    def test_loads_periods_from_file(self, service: NonwearDataService, choi_algorithm_file: Path) -> None:
        """Loads Choi algorithm periods from CSV file."""
        with patch.object(service, "extract_participant_from_filename") as mock_extract:
            mock_extract.return_value = "001"

            periods = service.load_choi_algorithm_periods(choi_algorithm_file)

        assert len(periods) == 2
        assert all(isinstance(p, NonwearPeriod) for p in periods)
        assert all(p.source == NonwearDataSource.CHOI_ALGORITHM for p in periods)
        assert periods[0].duration_minutes == 60
        assert periods[0].start_index == 100
        assert periods[0].end_index == 159

    def test_returns_empty_for_empty_file(self, service: NonwearDataService, data_folder: Path) -> None:
        """Returns empty list for empty file."""
        empty_file = data_folder / "empty_choi.csv"
        empty_file.write_text("start_time,end_time,duration_minutes,start_index,end_index\n")

        with patch.object(service, "extract_participant_from_filename") as mock_extract:
            mock_extract.return_value = "001"
            periods = service.load_choi_algorithm_periods(empty_file)

        assert periods == []

    def test_raises_for_missing_columns(self, service: NonwearDataService, data_folder: Path) -> None:
        """Raises error when required columns are missing."""
        bad_file = data_folder / "bad_choi.csv"
        bad_file.write_text("start_time,end_time\n2024-01-15,2024-01-16\n")

        # Error is wrapped in FILE_OPERATION_FAILED by outer exception handler
        with pytest.raises(DataLoadingError) as exc_info:
            service.load_choi_algorithm_periods(bad_file)

        assert exc_info.value.error_code == ErrorCodes.FILE_OPERATION_FAILED


class TestGetNonwearPeriodsForFile:
    """Tests for get_nonwear_periods_for_file method."""

    def test_returns_periods_from_database(self, service: NonwearDataService, mock_db_manager: MagicMock) -> None:
        """Returns periods from database query via NonwearRepository."""
        expected_period = NonwearPeriod(
            start_time="2024-01-15 08:00:00",
            end_time="2024-01-15 09:00:00",
            participant_id="001",
            source=NonwearDataSource.NONWEAR_SENSOR,
            duration_minutes=60,
        )
        mock_db_manager.nonwear.get_periods_for_file.return_value = [expected_period]

        with patch.object(service, "_extract_participant_id_from_filename", return_value="001"):
            periods = service.get_nonwear_periods_for_file("TEST-001.csv", NonwearDataSource.NONWEAR_SENSOR)

        assert len(periods) == 1
        assert periods[0].participant_id == "001"
        mock_db_manager.nonwear.get_periods_for_file.assert_called_once_with(
            filename="TEST-001.csv",
            participant_id="001",
            source=NonwearDataSource.NONWEAR_SENSOR,
            start_time=None,
            end_time=None,
        )

    def test_returns_empty_on_exception(self, service: NonwearDataService, mock_db_manager: MagicMock) -> None:
        """Returns empty list on database exception."""
        mock_db_manager.nonwear.get_periods_for_file.side_effect = Exception("DB error")

        with patch.object(service, "_extract_participant_id_from_filename", return_value="001"):
            periods = service.get_nonwear_periods_for_file("TEST-001.csv", NonwearDataSource.NONWEAR_SENSOR)

        assert periods == []


class TestSaveNonwearPeriods:
    """Tests for save_nonwear_periods method."""

    def test_saves_sensor_periods(self, service: NonwearDataService, mock_db_manager: MagicMock) -> None:
        """Saves sensor periods to database via NonwearRepository."""
        periods = [
            NonwearPeriod(
                start_time="2024-01-15 08:00:00",
                end_time="2024-01-15 09:00:00",
                participant_id="001",
                source=NonwearDataSource.NONWEAR_SENSOR,
            )
        ]

        mock_db_manager.nonwear.save_periods.return_value = True
        result = service.save_nonwear_periods(periods, "TEST-001.csv")

        assert result is True
        mock_db_manager.nonwear.save_periods.assert_called_once_with(periods, "TEST-001.csv")

    def test_saves_choi_periods_with_indices(self, service: NonwearDataService, mock_db_manager: MagicMock) -> None:
        """Saves Choi periods with indices to database via NonwearRepository."""
        periods = [
            NonwearPeriod(
                start_time="2024-01-15 08:00:00",
                end_time="2024-01-15 09:00:00",
                participant_id="001",
                source=NonwearDataSource.CHOI_ALGORITHM,
                duration_minutes=60,
                start_index=100,
                end_index=159,
            )
        ]

        mock_db_manager.nonwear.save_periods.return_value = True
        result = service.save_nonwear_periods(periods, "TEST-001.csv")

        assert result is True

    def test_returns_false_on_exception(self, service: NonwearDataService, mock_db_manager: MagicMock) -> None:
        """Returns False on database exception."""
        periods = [
            NonwearPeriod(
                start_time="2024-01-15 08:00:00",
                end_time="2024-01-15 09:00:00",
                participant_id="001",
                source=NonwearDataSource.NONWEAR_SENSOR,
            )
        ]

        mock_db_manager.nonwear.save_periods.side_effect = Exception("DB error")
        result = service.save_nonwear_periods(periods, "TEST-001.csv")

        assert result is False


class TestAlignNonwearWithActivity:
    """Tests for align_nonwear_with_activity method."""

    def test_aligns_single_period(self, service: NonwearDataService) -> None:
        """Aligns a single nonwear period with activity timestamps."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        activity_timestamps = [base_time + timedelta(minutes=i) for i in range(10)]

        periods = [
            NonwearPeriod(
                start_time="2024-01-15 08:02:00",
                end_time="2024-01-15 08:05:00",
                participant_id="001",
                source=NonwearDataSource.NONWEAR_SENSOR,
            )
        ]

        status = service.align_nonwear_with_activity(periods, activity_timestamps)

        assert len(status) == 10
        # Minutes 2-5 should be marked as nonwear
        assert status[0] is False  # 08:00
        assert status[1] is False  # 08:01
        assert status[2] is True  # 08:02
        assert status[3] is True  # 08:03
        assert status[4] is True  # 08:04
        assert status[5] is True  # 08:05
        assert status[6] is False  # 08:06

    def test_aligns_multiple_periods(self, service: NonwearDataService) -> None:
        """Aligns multiple nonwear periods."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        activity_timestamps = [base_time + timedelta(minutes=i) for i in range(20)]

        periods = [
            NonwearPeriod(
                start_time="2024-01-15 08:02:00",
                end_time="2024-01-15 08:05:00",
                participant_id="001",
                source=NonwearDataSource.NONWEAR_SENSOR,
            ),
            NonwearPeriod(
                start_time="2024-01-15 08:15:00",
                end_time="2024-01-15 08:17:00",
                participant_id="001",
                source=NonwearDataSource.NONWEAR_SENSOR,
            ),
        ]

        status = service.align_nonwear_with_activity(periods, activity_timestamps)

        # Check both periods are marked
        assert status[2] is True  # First period
        assert status[15] is True  # Second period
        assert status[10] is False  # Gap between periods

    def test_returns_all_wear_for_empty_periods(self, service: NonwearDataService) -> None:
        """Returns all wear status when no nonwear periods."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        activity_timestamps = [base_time + timedelta(minutes=i) for i in range(10)]

        status = service.align_nonwear_with_activity([], activity_timestamps)

        assert len(status) == 10
        assert all(s is False for s in status)

    def test_handles_out_of_range_periods(self, service: NonwearDataService) -> None:
        """Handles periods that don't overlap with activity timestamps."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        activity_timestamps = [base_time + timedelta(minutes=i) for i in range(10)]

        # Period is before activity timestamps
        periods = [
            NonwearPeriod(
                start_time="2024-01-14 08:00:00",  # Day before
                end_time="2024-01-14 09:00:00",
                participant_id="001",
                source=NonwearDataSource.NONWEAR_SENSOR,
            ),
        ]

        status = service.align_nonwear_with_activity(periods, activity_timestamps)

        # No overlap, all should be wear
        assert len(status) == 10
        assert all(s is False for s in status)

    def test_returns_fallback_on_exception(self, service: NonwearDataService) -> None:
        """Returns all wear as fallback on exception."""
        # Pass invalid activity_timestamps to trigger exception
        with patch("pandas.to_datetime") as mock_parse:
            mock_parse.side_effect = Exception("Parse error")

            periods = [
                NonwearPeriod(
                    start_time="2024-01-15 08:00:00",
                    end_time="2024-01-15 09:00:00",
                    participant_id="001",
                    source=NonwearDataSource.NONWEAR_SENSOR,
                ),
            ]

            status = service.align_nonwear_with_activity(periods, [datetime(2024, 1, 15, 8, 0)])

        assert len(status) == 1
        assert status[0] is False  # Fallback to wear
