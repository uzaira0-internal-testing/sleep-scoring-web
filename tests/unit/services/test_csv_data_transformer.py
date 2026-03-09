#!/usr/bin/env python3
"""
Comprehensive tests for CSVDataTransformer.
Tests column identification, data transformation, and timestamp processing.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import ActivityDataPreference, DatabaseColumn
from sleep_scoring_app.services.csv_data_transformer import ColumnMapping, CSVDataTransformer


class TestColumnMapping:
    """Tests for ColumnMapping dataclass."""

    def test_empty_mapping_is_invalid(self) -> None:
        """Empty mapping should be invalid."""
        mapping = ColumnMapping()
        assert not mapping.is_valid

    def test_date_only_is_invalid(self) -> None:
        """Mapping with only date column is invalid (needs activity too)."""
        mapping = ColumnMapping(date_col="Date")
        assert not mapping.is_valid

    def test_activity_only_is_invalid(self) -> None:
        """Mapping with only activity column is invalid (needs date too)."""
        mapping = ColumnMapping(activity_col="Activity")
        assert not mapping.is_valid

    def test_date_and_activity_is_valid(self) -> None:
        """Mapping with date and activity is valid."""
        mapping = ColumnMapping(date_col="Date", activity_col="Activity")
        assert mapping.is_valid

    def test_combined_datetime_is_valid(self) -> None:
        """Combined datetime with activity is valid."""
        mapping = ColumnMapping(date_col="DateTime", activity_col="Activity", datetime_combined=True)
        assert mapping.is_valid

    def test_extra_cols_default_empty(self) -> None:
        """Extra columns should default to empty dict."""
        mapping = ColumnMapping()
        assert mapping.extra_cols == {}

    def test_extra_cols_preserved(self) -> None:
        """Extra columns should be preserved."""
        extra = {DatabaseColumn.AXIS_Y: "Axis1", DatabaseColumn.AXIS_X: "Axis2"}
        mapping = ColumnMapping(extra_cols=extra)
        assert mapping.extra_cols == extra


class TestCSVDataTransformer:
    """Tests for CSVDataTransformer class."""

    @pytest.fixture
    def transformer(self) -> CSVDataTransformer:
        """Create a transformer instance."""
        return CSVDataTransformer()

    @pytest.fixture
    def sample_csv(self, tmp_path: Path) -> Path:
        """Create a sample CSV file for testing."""
        csv_path = tmp_path / "sample.csv"
        csv_path.write_text(
            "Date,Time,Activity,Axis1,Axis2,Axis3,Vector Magnitude\n"
            "2024-01-01,12:00:00,100,50,30,20,60.8\n"
            "2024-01-01,12:01:00,150,75,45,30,91.2\n"
            "2024-01-01,12:02:00,200,100,60,40,121.7\n"
        )
        return csv_path

    @pytest.fixture
    def combined_datetime_csv(self, tmp_path: Path) -> Path:
        """Create CSV with combined datetime column."""
        csv_path = tmp_path / "combined.csv"
        csv_path.write_text("DateTime,Activity,Axis1\n2024-01-01 12:00:00,100,50\n2024-01-01 12:01:00,150,75\n")
        return csv_path

    @pytest.fixture
    def timestamp_csv(self, tmp_path: Path) -> Path:
        """Create CSV with timestamp column."""
        csv_path = tmp_path / "timestamp.csv"
        csv_path.write_text("Timestamp,Activity\n2024-01-01 12:00:00,100\n2024-01-01 12:01:00,150\n")
        return csv_path


class TestLoadCSV(TestCSVDataTransformer):
    """Tests for load_csv method."""

    def test_load_valid_csv(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should successfully load a valid CSV."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        assert df is not None
        assert len(df) == 3
        assert "Date" in df.columns
        assert "Activity" in df.columns

    def test_load_with_skip_rows(self, tmp_path: Path, transformer: CSVDataTransformer) -> None:
        """Should skip header rows correctly."""
        csv_path = tmp_path / "with_header.csv"
        csv_path.write_text("ActiGraph File\nSerial: ABC123\nDate,Activity\n2024-01-01,100\n")
        df = transformer.load_csv(csv_path, skip_rows=2)
        assert df is not None
        assert len(df) == 1
        assert "Date" in df.columns

    def test_load_empty_csv(self, tmp_path: Path, transformer: CSVDataTransformer) -> None:
        """Should return None for empty CSV."""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("")
        df = transformer.load_csv(csv_path, skip_rows=0)
        assert df is None

    def test_load_nonexistent_file(self, transformer: CSVDataTransformer) -> None:
        """Should return None for nonexistent file."""
        df = transformer.load_csv(Path("/nonexistent/file.csv"), skip_rows=0)
        assert df is None

    def test_load_file_too_large(self, tmp_path: Path) -> None:
        """Should return None for file exceeding size limit."""
        transformer = CSVDataTransformer(max_file_size=100)  # 100 bytes limit
        csv_path = tmp_path / "large.csv"
        csv_path.write_text("a" * 200)  # 200 bytes
        df = transformer.load_csv(csv_path, skip_rows=0)
        assert df is None


class TestIdentifyColumns(TestCSVDataTransformer):
    """Tests for identify_columns method."""

    def test_identify_standard_columns(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should identify standard date, time, activity columns."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        mapping = transformer.identify_columns(df)

        assert mapping.date_col == "Date"
        assert mapping.time_col == "Time"
        assert mapping.activity_col == "Vector Magnitude"  # Prioritizes VM
        assert not mapping.datetime_combined

    def test_identify_combined_datetime(self, transformer: CSVDataTransformer, combined_datetime_csv: Path) -> None:
        """Should identify combined datetime column."""
        df = transformer.load_csv(combined_datetime_csv, skip_rows=0)
        mapping = transformer.identify_columns(df)

        assert mapping.date_col == "DateTime"
        assert mapping.time_col is None
        assert mapping.datetime_combined

    def test_identify_timestamp_column(self, transformer: CSVDataTransformer, timestamp_csv: Path) -> None:
        """Should identify timestamp column as combined datetime."""
        df = transformer.load_csv(timestamp_csv, skip_rows=0)
        mapping = transformer.identify_columns(df)

        assert mapping.date_col == "Timestamp"
        assert mapping.datetime_combined

    def test_identify_axis_columns(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should identify axis columns in extra_cols."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        mapping = transformer.identify_columns(df)

        assert DatabaseColumn.AXIS_Y in mapping.extra_cols
        assert DatabaseColumn.VECTOR_MAGNITUDE in mapping.extra_cols

    def test_custom_column_mapping(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should use custom column mapping when provided."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        custom = {
            "date": "Date",
            "time": "Time",
            "activity": "Activity",
        }
        mapping = transformer.identify_columns(df, custom_columns=custom)

        assert mapping.date_col == "Date"
        assert mapping.time_col == "Time"
        assert mapping.activity_col == "Activity"

    def test_custom_combined_datetime(self, transformer: CSVDataTransformer, combined_datetime_csv: Path) -> None:
        """Should handle custom combined datetime mapping."""
        df = transformer.load_csv(combined_datetime_csv, skip_rows=0)
        custom = {
            "date": "DateTime",
            "activity": "Activity",
            "datetime_combined": True,
        }
        mapping = transformer.identify_columns(df, custom_columns=custom)

        assert mapping.date_col == "DateTime"
        assert mapping.time_col is None
        assert mapping.datetime_combined

    def test_custom_axis_columns(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should use custom axis column mappings."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        custom = {
            "date": "Date",
            "activity": "Activity",
            ActivityDataPreference.AXIS_Y: "Axis1",
            ActivityDataPreference.AXIS_X: "Axis2",
        }
        mapping = transformer.identify_columns(df, custom_columns=custom)

        assert mapping.extra_cols.get(DatabaseColumn.AXIS_Y) == "Axis1"
        assert mapping.extra_cols.get(DatabaseColumn.AXIS_X) == "Axis2"

    def test_invalid_custom_column_falls_back(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should handle invalid custom column names gracefully."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        custom = {
            "date": "NonexistentColumn",
            "activity": "Activity",
        }
        mapping = transformer.identify_columns(df, custom_columns=custom)

        assert mapping.date_col is None  # Invalid column not used


class TestFindExtraColumns(TestCSVDataTransformer):
    """Tests for _find_extra_columns method."""

    def test_find_axis1_as_y(self, transformer: CSVDataTransformer) -> None:
        """Should map Axis1 to AXIS_Y."""
        columns = ["Date", "Axis1", "Axis2", "Axis3"]
        extra = transformer._find_extra_columns(columns)
        assert extra.get(DatabaseColumn.AXIS_Y) == "Axis1"

    def test_find_axis_x_y_z(self, transformer: CSVDataTransformer) -> None:
        """Should map axis_x, axis_y, axis_z correctly."""
        columns = ["Date", "axis_x", "axis_y", "axis_z"]
        extra = transformer._find_extra_columns(columns)
        assert extra.get(DatabaseColumn.AXIS_Y) == "axis_y"
        assert extra.get(DatabaseColumn.AXIS_X) == "axis_x"
        assert extra.get(DatabaseColumn.AXIS_Z) == "axis_z"

    def test_find_vector_magnitude(self, transformer: CSVDataTransformer) -> None:
        """Should find vector magnitude column."""
        columns = ["Date", "Activity", "Vector Magnitude"]
        extra = transformer._find_extra_columns(columns)
        assert extra.get(DatabaseColumn.VECTOR_MAGNITUDE) == "Vector Magnitude"

    def test_find_vm_abbreviation(self, transformer: CSVDataTransformer) -> None:
        """Should find VM abbreviation."""
        columns = ["Date", "Activity", "VM"]
        extra = transformer._find_extra_columns(columns)
        assert extra.get(DatabaseColumn.VECTOR_MAGNITUDE) == "VM"


class TestProcessTimestamps(TestCSVDataTransformer):
    """Tests for process_timestamps method."""

    def test_process_separate_date_time(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should combine separate date and time columns."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        timestamps, epoch_seconds = transformer.process_timestamps(df, "Date", "Time")

        assert timestamps is not None
        assert len(timestamps) == 3
        assert "2024-01-01T12:00:00" in timestamps[0]
        assert epoch_seconds == 60  # Sample data has 1-minute intervals

    def test_process_combined_datetime(self, transformer: CSVDataTransformer, combined_datetime_csv: Path) -> None:
        """Should process combined datetime column."""
        df = transformer.load_csv(combined_datetime_csv, skip_rows=0)
        timestamps, _epoch_seconds = transformer.process_timestamps(df, "DateTime", None)

        assert timestamps is not None
        assert len(timestamps) == 2

    def test_process_missing_date_column(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should return None if date column doesn't exist."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        timestamps, epoch_seconds = transformer.process_timestamps(df, "NonexistentDate", "Time")
        assert timestamps is None
        assert epoch_seconds is None

    def test_process_missing_time_column(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should return None if time column doesn't exist."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        timestamps, epoch_seconds = transformer.process_timestamps(df, "Date", "NonexistentTime")
        assert timestamps is None
        assert epoch_seconds is None

    def test_process_various_date_formats(self, tmp_path: Path, transformer: CSVDataTransformer) -> None:
        """Should handle various date formats."""
        csv_path = tmp_path / "dates.csv"
        csv_path.write_text("Date,Activity\n01/15/2024,100\n01/16/2024,150\n")
        df = transformer.load_csv(csv_path, skip_rows=0)
        timestamps, _epoch_seconds = transformer.process_timestamps(df, "Date", None)

        assert timestamps is not None
        assert len(timestamps) == 2


class TestTransformActivityData(TestCSVDataTransformer):
    """Tests for transform_activity_data method."""

    def test_transform_valid_data(self, transformer: CSVDataTransformer, sample_csv: Path) -> None:
        """Should transform activity data to float list."""
        df = transformer.load_csv(sample_csv, skip_rows=0)
        activities = transformer.transform_activity_data(df, "Activity")

        assert len(activities) == 3
        assert activities == [100.0, 150.0, 200.0]

    def test_transform_with_nan(self, tmp_path: Path, transformer: CSVDataTransformer) -> None:
        """Should replace NaN with 0."""
        csv_path = tmp_path / "nan.csv"
        csv_path.write_text("Date,Activity\n2024-01-01,100\n2024-01-02,\n2024-01-03,200\n")
        df = transformer.load_csv(csv_path, skip_rows=0)
        activities = transformer.transform_activity_data(df, "Activity")

        assert activities == [100.0, 0.0, 200.0]

    def test_transform_string_numbers(self, tmp_path: Path, transformer: CSVDataTransformer) -> None:
        """Should convert string numbers to float."""
        csv_path = tmp_path / "strings.csv"
        csv_path.write_text("Date,Activity\n2024-01-01,100.5\n2024-01-02,200.7\n")
        df = transformer.load_csv(csv_path, skip_rows=0)
        activities = transformer.transform_activity_data(df, "Activity")

        assert activities == [100.5, 200.7]


class TestAutoDetectColumns(TestCSVDataTransformer):
    """Tests for _auto_detect_columns method."""

    def test_detect_datum_as_date(self, transformer: CSVDataTransformer) -> None:
        """Should detect 'Datum' as date column (Dutch)."""
        columns = ["Datum", "Tijd", "Activiteit"]
        mapping = transformer._auto_detect_columns(columns)
        assert mapping.date_col == "Datum"

    def test_detect_tijd_as_time(self, transformer: CSVDataTransformer) -> None:
        """Should detect 'Tijd' as time column (Dutch)."""
        columns = ["Datum", "Tijd", "Activiteit"]
        mapping = transformer._auto_detect_columns(columns)
        assert mapping.time_col == "Tijd"

    def test_prioritize_vector_magnitude(self, transformer: CSVDataTransformer) -> None:
        """Should prioritize vector magnitude over generic activity."""
        columns = ["Date", "Time", "Activity", "Vector Magnitude"]
        mapping = transformer._auto_detect_columns(columns)
        assert mapping.activity_col == "Vector Magnitude"

    def test_fallback_to_activity_count(self, transformer: CSVDataTransformer) -> None:
        """Should fall back to activity/count columns."""
        columns = ["Date", "Time", "Activity Count"]
        mapping = transformer._auto_detect_columns(columns)
        assert mapping.activity_col == "Activity Count"

    def test_case_insensitive_detection(self, transformer: CSVDataTransformer) -> None:
        """Should detect columns case-insensitively."""
        columns = ["DATE", "TIME", "ACTIVITY"]
        mapping = transformer._auto_detect_columns(columns)
        assert mapping.date_col == "DATE"
        assert mapping.time_col == "TIME"


class TestEdgeCases(TestCSVDataTransformer):
    """Tests for edge cases and error handling."""

    def test_whitespace_in_column_names(self, tmp_path: Path, transformer: CSVDataTransformer) -> None:
        """Should handle whitespace in column names."""
        csv_path = tmp_path / "whitespace.csv"
        csv_path.write_text(" Date , Time , Activity \n2024-01-01,12:00:00,100\n")
        df = transformer.load_csv(csv_path, skip_rows=0)
        mapping = transformer.identify_columns(df)

        # Should still find columns despite whitespace
        assert mapping.date_col is not None

    def test_empty_dataframe(self, transformer: CSVDataTransformer) -> None:
        """Should handle empty DataFrame."""
        df = pd.DataFrame()
        mapping = transformer.identify_columns(df)
        assert not mapping.is_valid

    def test_single_column_csv(self, tmp_path: Path, transformer: CSVDataTransformer) -> None:
        """Should handle single column CSV."""
        csv_path = tmp_path / "single.csv"
        csv_path.write_text("Value\n100\n200\n")
        df = transformer.load_csv(csv_path, skip_rows=0)
        mapping = transformer.identify_columns(df)

        assert not mapping.is_valid  # Can't identify required columns
