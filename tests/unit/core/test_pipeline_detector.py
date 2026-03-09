"""
Tests for DataSourceDetector in core/pipeline/detector.py.

Tests automatic detection of raw accelerometer vs epoch count data.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from sleep_scoring_app.core.pipeline.detector import DataSourceDetector
from sleep_scoring_app.core.pipeline.exceptions import DataDetectionError
from sleep_scoring_app.core.pipeline.types import DataSourceType


@pytest.fixture
def detector() -> DataSourceDetector:
    """Create a DataSourceDetector instance."""
    return DataSourceDetector()


@pytest.fixture
def raw_dataframe() -> pd.DataFrame:
    """Create a DataFrame with raw tri-axial data."""
    base_time = datetime(2024, 1, 15, 8, 0, 0)
    n_samples = 100
    return pd.DataFrame(
        {
            "timestamp": [
                base_time + timedelta(milliseconds=i * 33)  # ~30 Hz
                for i in range(n_samples)
            ],
            "AXIS_X": [0.5] * n_samples,
            "AXIS_Y": [0.2] * n_samples,
            "AXIS_Z": [-0.8] * n_samples,
        }
    )


@pytest.fixture
def epoch_dataframe() -> pd.DataFrame:
    """Create a DataFrame with 60-second epoch count data."""
    base_time = datetime(2024, 1, 15, 8, 0, 0)
    n_epochs = 10
    return pd.DataFrame(
        {
            "datetime": [base_time + timedelta(seconds=i * 60) for i in range(n_epochs)],
            "Axis1": [100, 200, 50, 30, 10, 5, 0, 15, 80, 150],
        }
    )


class TestDetectFromFile:
    """Tests for detect_from_file method."""

    def test_detects_gt3x_file(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Detects GT3X files as raw data."""
        gt3x_file = tmp_path / "data.gt3x"
        gt3x_file.write_bytes(b"fake gt3x content")

        result = detector.detect_from_file(gt3x_file)

        assert result == DataSourceType.GT3X_RAW

    def test_detects_csv_with_raw_columns(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Detects CSV with raw tri-axial columns."""
        csv_file = tmp_path / "raw_data.csv"
        csv_file.write_text("timestamp,AXIS_X,AXIS_Y,AXIS_Z\n2024-01-15 08:00:00,0.5,0.2,-0.8\n")

        result = detector.detect_from_file(csv_file)

        assert result == DataSourceType.CSV_RAW

    def test_detects_csv_with_epoch_columns(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Detects CSV with epoch count column."""
        csv_file = tmp_path / "epoch_data.csv"
        # Create proper 60-second interval data
        csv_file.write_text("datetime,Axis1\n2024-01-15 08:00:00,100\n2024-01-15 08:01:00,200\n2024-01-15 08:02:00,150\n")

        result = detector.detect_from_file(csv_file)

        assert result == DataSourceType.CSV_EPOCH

    def test_raises_for_nonexistent_file(self, detector: DataSourceDetector) -> None:
        """Raises FileNotFoundError for nonexistent file."""
        with pytest.raises(FileNotFoundError):
            detector.detect_from_file("/nonexistent/file.csv")

    def test_raises_for_unsupported_extension(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Raises DataDetectionError for unsupported file extension."""
        txt_file = tmp_path / "data.txt"
        txt_file.write_text("some content")

        with pytest.raises(DataDetectionError) as exc_info:
            detector.detect_from_file(txt_file)

        assert "Unsupported file extension" in str(exc_info.value)

    def test_handles_string_path(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Handles string paths."""
        gt3x_file = tmp_path / "data.gt3x"
        gt3x_file.write_bytes(b"fake content")

        result = detector.detect_from_file(str(gt3x_file))

        assert result == DataSourceType.GT3X_RAW


class TestDetectFromDataframe:
    """Tests for detect_from_dataframe method."""

    def test_detects_raw_dataframe(self, detector: DataSourceDetector, raw_dataframe: pd.DataFrame) -> None:
        """Detects DataFrame with raw tri-axial columns."""
        result = detector.detect_from_dataframe(raw_dataframe)

        assert result == DataSourceType.CSV_RAW

    def test_detects_epoch_dataframe(self, detector: DataSourceDetector, epoch_dataframe: pd.DataFrame) -> None:
        """Detects DataFrame with epoch count column."""
        result = detector.detect_from_dataframe(epoch_dataframe)

        assert result == DataSourceType.CSV_EPOCH

    def test_raises_for_none_dataframe(self, detector: DataSourceDetector) -> None:
        """Raises DataDetectionError for None DataFrame."""
        with pytest.raises(DataDetectionError) as exc_info:
            detector.detect_from_dataframe(None)

        assert "None or empty" in str(exc_info.value)

    def test_raises_for_empty_dataframe(self, detector: DataSourceDetector) -> None:
        """Raises DataDetectionError for empty DataFrame."""
        with pytest.raises(DataDetectionError) as exc_info:
            detector.detect_from_dataframe(pd.DataFrame())

        assert "None or empty" in str(exc_info.value)

    def test_raises_for_unrecognized_columns(self, detector: DataSourceDetector) -> None:
        """Raises DataDetectionError for unrecognized column structure."""
        df = pd.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})

        with pytest.raises(DataDetectionError) as exc_info:
            detector.detect_from_dataframe(df)

        assert "Cannot determine data type" in str(exc_info.value)

    def test_detects_activity_column(self, detector: DataSourceDetector) -> None:
        """Detects 'Activity' column as epoch data."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        df = pd.DataFrame(
            {
                "datetime": [base_time + timedelta(seconds=i * 60) for i in range(3)],
                "Activity": [100, 200, 150],
            }
        )

        result = detector.detect_from_dataframe(df)

        assert result == DataSourceType.CSV_EPOCH

    def test_prefers_raw_over_epoch_when_both_present(self, detector: DataSourceDetector) -> None:
        """Prefers raw detection when both raw and epoch columns present."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        df = pd.DataFrame(
            {
                "timestamp": [base_time + timedelta(seconds=i) for i in range(3)],
                "AXIS_X": [0.5, 0.6, 0.7],
                "AXIS_Y": [0.2, 0.3, 0.4],
                "AXIS_Z": [-0.8, -0.7, -0.6],
                "Axis1": [100, 200, 150],  # Also has epoch column
            }
        )

        result = detector.detect_from_dataframe(df)

        # Raw detection takes precedence
        assert result == DataSourceType.CSV_RAW


class TestHasRawColumns:
    """Tests for _has_raw_columns method."""

    def test_returns_true_for_all_axis_columns(self, detector: DataSourceDetector) -> None:
        """Returns True when all axis columns present."""
        columns = {"timestamp", "AXIS_X", "AXIS_Y", "AXIS_Z"}

        assert detector._has_raw_columns(columns) is True

    def test_returns_false_for_missing_axis(self, detector: DataSourceDetector) -> None:
        """Returns False when any axis column is missing."""
        columns = {"timestamp", "AXIS_X", "AXIS_Y"}  # Missing AXIS_Z

        assert detector._has_raw_columns(columns) is False

    def test_returns_false_for_no_axis_columns(self, detector: DataSourceDetector) -> None:
        """Returns False when no axis columns present."""
        columns = {"timestamp", "Axis1", "Activity"}

        assert detector._has_raw_columns(columns) is False


class TestHasEpochColumns:
    """Tests for _has_epoch_columns method."""

    def test_returns_true_for_axis1(self, detector: DataSourceDetector) -> None:
        """Returns True for Axis1 column."""
        columns = {"datetime", "Axis1"}

        assert detector._has_epoch_columns(columns) is True

    def test_returns_true_for_activity(self, detector: DataSourceDetector) -> None:
        """Returns True for Activity column."""
        columns = {"datetime", "Activity"}

        assert detector._has_epoch_columns(columns) is True

    def test_case_insensitive(self, detector: DataSourceDetector) -> None:
        """Handles case-insensitive column names."""
        columns = {"datetime", "AXIS1"}

        assert detector._has_epoch_columns(columns) is True

    def test_returns_false_without_epoch_column(self, detector: DataSourceDetector) -> None:
        """Returns False without epoch columns."""
        columns = {"datetime", "AXIS_X", "AXIS_Y", "AXIS_Z"}

        assert detector._has_epoch_columns(columns) is False


class TestHasEpochIntervals:
    """Tests for _has_epoch_intervals method."""

    def test_returns_true_for_60_second_intervals(self, detector: DataSourceDetector, epoch_dataframe: pd.DataFrame) -> None:
        """Returns True for ~60 second intervals."""
        result = detector._has_epoch_intervals(epoch_dataframe)

        assert result  # numpy bool compatible

    def test_returns_true_when_no_timestamp(self, detector: DataSourceDetector) -> None:
        """Returns True when no timestamp column (assumes epoch data)."""
        df = pd.DataFrame({"Axis1": [100, 200, 150]})

        result = detector._has_epoch_intervals(df)

        assert result is True

    def test_returns_false_for_high_frequency(self, detector: DataSourceDetector) -> None:
        """Returns False for high-frequency data (~30 Hz)."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        df = pd.DataFrame(
            {
                "timestamp": [base_time + timedelta(milliseconds=i * 33) for i in range(100)],
                "Axis1": list(range(100)),
            }
        )

        result = detector._has_epoch_intervals(df)

        assert not result  # numpy bool compatible


class TestFindTimestampColumn:
    """Tests for _find_timestamp_column method."""

    def test_finds_timestamp(self, detector: DataSourceDetector) -> None:
        """Finds 'timestamp' column."""
        df = pd.DataFrame({"timestamp": [1], "data": [2]})

        assert detector._find_timestamp_column(df) == "timestamp"

    def test_finds_datetime(self, detector: DataSourceDetector) -> None:
        """Finds 'datetime' column."""
        df = pd.DataFrame({"datetime": [1], "data": [2]})

        assert detector._find_timestamp_column(df) == "datetime"

    def test_finds_date_time(self, detector: DataSourceDetector) -> None:
        """Finds 'Date Time' column."""
        df = pd.DataFrame({"Date Time": [1], "data": [2]})

        assert detector._find_timestamp_column(df) == "Date Time"

    def test_case_insensitive(self, detector: DataSourceDetector) -> None:
        """Finds column case-insensitively."""
        df = pd.DataFrame({"TIMESTAMP": [1], "data": [2]})

        assert detector._find_timestamp_column(df) == "TIMESTAMP"

    def test_returns_none_for_no_match(self, detector: DataSourceDetector) -> None:
        """Returns None when no timestamp column found."""
        df = pd.DataFrame({"col1": [1], "col2": [2]})

        assert detector._find_timestamp_column(df) is None


class TestDetectSkipRows:
    """Tests for _detect_skip_rows method."""

    def test_detects_actigraph_header(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Detects ActiGraph 10-line header."""
        csv_file = tmp_path / "actigraph.csv"
        csv_file.write_text(
            "------------ Data File Created By ActiGraph ActiLife v6.13.3 Firmware v2.2.1 date format M/d/yyyy at 30 Hz  Filter Normal -----------\n"
            "Serial Number: TAS1D50150142\n"
            "Start Time 00:00:00\n"
            "Start Date 11/12/2014\n"
            "Epoch Period (hh:mm:ss) 00:01:00\n"
            "Download Time 10:19:57\n"
            "Download Date 11/13/2014\n"
            "Current Memory Address: 0\n"
            "Current Battery Voltage: 4.17     Mode = 1\n"
            "--------------------------------------------------\n"
            "Date,Time,Axis1,Axis2,Axis3,Steps,Lux,Inclinometer Off,Inclinometer Standing\n"
            "11/12/2014,00:00:00,0,0,0,0,0,1,0\n"
        )

        result = detector._detect_skip_rows(csv_file)

        assert result == 10

    def test_returns_zero_for_no_header(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Returns 0 for CSV without metadata header."""
        csv_file = tmp_path / "simple.csv"
        csv_file.write_text("datetime,Axis1\n2024-01-15 08:00:00,100\n2024-01-15 08:01:00,200\n")

        result = detector._detect_skip_rows(csv_file)

        assert result == 0

    def test_handles_empty_file(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Handles empty file gracefully."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        result = detector._detect_skip_rows(csv_file)

        assert result == 0


class TestGetTimestampsFromDf:
    """Tests for _get_timestamps_from_df method."""

    def test_extracts_combined_datetime(self, detector: DataSourceDetector) -> None:
        """Extracts timestamps from combined datetime column."""
        df = pd.DataFrame(
            {
                "datetime": ["2024-01-15 08:00:00", "2024-01-15 08:01:00"],
                "Axis1": [100, 200],
            }
        )

        result = detector._get_timestamps_from_df(df)

        assert result is not None
        assert len(result) == 2

    def test_extracts_separate_date_time(self, detector: DataSourceDetector) -> None:
        """Extracts timestamps from separate Date and Time columns."""
        df = pd.DataFrame(
            {
                "Date": ["01/15/2024", "01/15/2024"],
                "Time": ["08:00:00", "08:01:00"],
                "Axis1": [100, 200],
            }
        )

        result = detector._get_timestamps_from_df(df)

        assert result is not None
        assert len(result) == 2

    def test_returns_none_without_timestamp(self, detector: DataSourceDetector) -> None:
        """Returns None when no timestamp column found."""
        df = pd.DataFrame({"col1": [1, 2], "col2": [3, 4]})

        result = detector._get_timestamps_from_df(df)

        assert result is None


class TestDataSourceType:
    """Tests for DataSourceType enum methods."""

    def test_gt3x_raw_is_raw(self) -> None:
        """GT3X_RAW is classified as raw data."""
        assert DataSourceType.GT3X_RAW.is_raw() is True
        assert DataSourceType.GT3X_RAW.is_epoched() is False

    def test_csv_raw_is_raw(self) -> None:
        """CSV_RAW is classified as raw data."""
        assert DataSourceType.CSV_RAW.is_raw() is True
        assert DataSourceType.CSV_RAW.is_epoched() is False

    def test_csv_epoch_is_epoched(self) -> None:
        """CSV_EPOCH is classified as epoch data."""
        assert DataSourceType.CSV_EPOCH.is_raw() is False
        assert DataSourceType.CSV_EPOCH.is_epoched() is True


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_handles_csv_with_spaces_in_columns(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Handles CSV with spaces after commas."""
        csv_file = tmp_path / "spaced.csv"
        csv_file.write_text("timestamp, AXIS_X, AXIS_Y, AXIS_Z\n2024-01-15 08:00:00, 0.5, 0.2, -0.8\n")

        result = detector.detect_from_file(csv_file)

        assert result == DataSourceType.CSV_RAW

    def test_handles_csv_with_trailing_spaces(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Handles CSV with trailing spaces in column names."""
        csv_file = tmp_path / "trailing.csv"
        csv_file.write_text("timestamp ,AXIS_X ,AXIS_Y ,AXIS_Z \n2024-01-15 08:00:00,0.5,0.2,-0.8\n")

        result = detector.detect_from_file(csv_file)

        assert result == DataSourceType.CSV_RAW

    def test_handles_malformed_csv(self, detector: DataSourceDetector, tmp_path: Path) -> None:
        """Raises error for malformed CSV."""
        csv_file = tmp_path / "malformed.csv"
        csv_file.write_text("not,a,valid,csv\nwith,inconsistent,rows")

        with pytest.raises(DataDetectionError):
            detector.detect_from_file(csv_file)
