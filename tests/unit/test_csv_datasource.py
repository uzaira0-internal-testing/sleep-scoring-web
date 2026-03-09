"""
Unit tests for CSVDataSourceLoader.

Tests the CSV/XLSX data source loader implementation.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import DatabaseColumn
from sleep_scoring_app.core.dataclasses import ColumnMapping
from sleep_scoring_app.io.sources.csv_loader import CSVDataSourceLoader
from sleep_scoring_app.io.sources.loader_protocol import DataSourceLoader


@pytest.fixture
def csv_loader() -> CSVDataSourceLoader:
    """Create CSV loader instance for testing."""
    return CSVDataSourceLoader()


@pytest.fixture
def sample_csv_file(tmp_path):
    """Create a sample CSV file with ActiGraph format."""
    file_path = tmp_path / "test_activity.csv"

    # Write ActiGraph-style metadata header lines (10 lines to skip)
    metadata_lines = [
        "------------ Data File Created By ActiGraph GT3X+ ActiLife v6.13.3 Firmware v2.5.0 date format M/d/yyyy at 30 Hz  Filter Normal -----------",
        "Serial Number: TEST123",
        "Start Time 08:00:00",
        "Start Date 1/15/2024",
        "Epoch Period (hh:mm:ss) 00:01:00",
        "Download Time 08:30:00",
        "Download Date 1/16/2024",
        "Current Memory Address: 0",
        "Current Battery Voltage: 4.22     Mode = 12",
        "------",  # 10th line to skip
    ]

    # Column header line (will be read as header after skipping 10 rows)
    column_header = "DATE,TIME,Axis1,Axis2,Axis3,Vector Magnitude,Steps"

    # Write data rows
    data_rows = [
        "1/15/2024,08:00:00,100,80,90,150,0",
        "1/15/2024,08:01:00,120,85,95,160,5",
        "1/15/2024,08:02:00,110,82,92,155,3",
        "1/15/2024,08:03:00,5,3,4,8,0",
        "1/15/2024,08:04:00,8,5,6,10,0",
    ]

    with open(file_path, "w") as f:
        f.write("\n".join([*metadata_lines, column_header, *data_rows]))

    return file_path


@pytest.fixture
def sample_csv_alternative_names(tmp_path):
    """Create CSV file with alternative column names."""
    file_path = tmp_path / "alternative.csv"

    # Write header lines (skip rows)
    header_lines = ["Header Line 1"] * 10

    # Write data with alternative column names
    data_lines = [
        "timestamp,y-axis,x-axis,z-axis",
        "2024-01-15 08:00:00,100,80,90",
        "2024-01-15 08:01:00,120,85,95",
        "2024-01-15 08:02:00,110,82,92",
    ]

    with open(file_path, "w") as f:
        f.write("\n".join(header_lines + data_lines))

    return file_path


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """Create sample DataFrame for testing."""
    return pd.DataFrame(
        {
            "Date": ["1/15/2024", "1/15/2024", "1/15/2024"],
            "Time": ["08:00:00", "08:01:00", "08:02:00"],
            "Axis1": [100, 120, 110],
            "Axis2": [80, 85, 82],
            "Axis3": [90, 95, 92],
            "Vector Magnitude": [150, 160, 155],
        }
    )


class TestCSVLoaderProperties:
    """Tests for CSV loader properties."""

    def test_csv_loader_name(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test CSV loader has correct name."""
        assert csv_loader.name == "CSV/XLSX File Loader"

    def test_csv_loader_identifier(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test CSV loader has correct identifier."""
        assert csv_loader.identifier == "csv"

    def test_csv_loader_supported_extensions(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test CSV loader supports expected extensions."""
        extensions = csv_loader.supported_extensions
        assert ".csv" in extensions
        assert ".xlsx" in extensions
        assert ".xls" in extensions

    def test_csv_loader_protocol_compliance(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test CSV loader implements DataSourceLoader protocol."""
        assert isinstance(csv_loader, DataSourceLoader)


class TestCSVLoaderColumnDetection:
    """Tests for column detection logic."""

    def test_detect_columns_actigraph_format(self, csv_loader: CSVDataSourceLoader, sample_dataframe: pd.DataFrame) -> None:
        """Test detecting columns in ActiGraph format."""
        mapping = csv_loader.detect_columns(sample_dataframe)

        assert isinstance(mapping, ColumnMapping)
        assert mapping.date_column == "Date"
        assert mapping.time_column == "Time"
        assert mapping.activity_column == "Vector Magnitude"
        assert mapping.vector_magnitude_column == "Vector Magnitude"

    def test_detect_columns_combined_datetime(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test detecting combined datetime column."""
        df = pd.DataFrame(
            {
                "datetime": ["2024-01-15 08:00:00", "2024-01-15 08:01:00"],
                "Axis1": [100, 120],
            }
        )

        mapping = csv_loader.detect_columns(df)
        assert mapping.datetime_column == "datetime"
        assert mapping.date_column is None
        assert mapping.time_column is None

    def test_detect_columns_timestamp_column(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test detecting timestamp as datetime column."""
        df = pd.DataFrame(
            {
                "timestamp": ["2024-01-15 08:00:00", "2024-01-15 08:01:00"],
                "Axis1": [100, 120],
            }
        )

        mapping = csv_loader.detect_columns(df)
        assert mapping.datetime_column == "timestamp"

    def test_detect_columns_alternative_names(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test detecting columns with alternative names."""
        df = pd.DataFrame(
            {
                "timestamp": ["2024-01-15 08:00:00", "2024-01-15 08:01:00"],
                "y-axis": [100, 120],
                "x-axis": [80, 85],
                "z-axis": [90, 95],
            }
        )

        mapping = csv_loader.detect_columns(df)
        assert mapping.datetime_column == "timestamp"
        assert mapping.activity_column == "y-axis"
        assert mapping.axis_x_column == "x-axis"
        assert mapping.axis_z_column == "z-axis"

    def test_detect_columns_axis1_fallback(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test fallback to Axis1 when no vector magnitude."""
        df = pd.DataFrame(
            {
                "Date": ["1/15/2024"],
                "Time": ["08:00:00"],
                "Axis1": [100],
                "Axis2": [80],
            }
        )

        mapping = csv_loader.detect_columns(df)
        assert mapping.activity_column == "Axis1"

    def test_detect_columns_prioritizes_vector_magnitude(self, csv_loader: CSVDataSourceLoader, sample_dataframe: pd.DataFrame) -> None:
        """Test that vector magnitude is prioritized over individual axes."""
        mapping = csv_loader.detect_columns(sample_dataframe)
        # Should prefer Vector Magnitude over Axis1
        assert mapping.activity_column == "Vector Magnitude"


class TestCSVLoaderFileLoading:
    """Tests for file loading functionality."""

    def test_load_file_basic(self, csv_loader: CSVDataSourceLoader, sample_csv_file) -> None:
        """Test loading a basic CSV file."""
        result = csv_loader.load_file(sample_csv_file)

        assert "activity_data" in result
        assert "metadata" in result
        assert "column_mapping" in result

        df = result["activity_data"]
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.AXIS_Y in df.columns
        assert len(df) == 5

    def test_load_file_not_found(self, csv_loader: CSVDataSourceLoader, tmp_path) -> None:
        """Test loading non-existent file raises error."""
        from sleep_scoring_app.core.exceptions import ValidationError

        nonexistent = tmp_path / "nonexistent.csv"

        with pytest.raises(ValidationError):
            csv_loader.load_file(nonexistent)

    def test_load_file_custom_skip_rows(self, csv_loader: CSVDataSourceLoader, tmp_path) -> None:
        """Test loading with custom skip_rows parameter."""
        # Create file with 5 header lines
        file_path = tmp_path / "custom_skip.csv"
        lines = ["Header"] * 5 + ["Date,Time,Axis1", "1/15/2024,08:00:00,100"]

        with open(file_path, "w") as f:
            f.write("\n".join(lines))

        result = csv_loader.load_file(file_path, skip_rows=5)
        df = result["activity_data"]
        assert len(df) == 1

    def test_load_excel_file(self, csv_loader: CSVDataSourceLoader, tmp_path) -> None:
        """Test loading Excel file (.xlsx)."""
        file_path = tmp_path / "test.xlsx"

        # Create Excel file with header rows and data
        # Create all rows in one DataFrame
        header_rows = [["Header"] * 3] * 10
        data_header = [["DATE", "TIME", "Axis1"]]
        data_rows = [
            ["1/15/2024", "08:00:00", 100],
            ["1/15/2024", "08:01:00", 120],
        ]

        all_rows = header_rows + data_header + data_rows
        df_combined = pd.DataFrame(all_rows)

        # Write to Excel
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df_combined.to_excel(writer, index=False, header=False)

        result = csv_loader.load_file(file_path, skip_rows=10)
        df = result["activity_data"]
        assert len(df) == 2

    def test_load_file_empty_raises(self, csv_loader: CSVDataSourceLoader, tmp_path) -> None:
        """Test loading empty file raises error."""
        empty_file = tmp_path / "empty.csv"
        empty_file.write_text("")

        with pytest.raises(ValueError, match="Empty data file"):
            csv_loader.load_file(empty_file)


class TestCSVLoaderColumnStandardization:
    """Tests for column standardization."""

    def test_standardize_columns_renames(self, csv_loader: CSVDataSourceLoader, sample_dataframe: pd.DataFrame) -> None:
        """Test that columns are renamed to database schema."""
        mapping = csv_loader.detect_columns(sample_dataframe)
        standardized = csv_loader._standardize_columns(sample_dataframe, mapping)

        assert DatabaseColumn.TIMESTAMP in standardized.columns
        assert DatabaseColumn.AXIS_Y in standardized.columns
        assert DatabaseColumn.AXIS_X in standardized.columns
        assert DatabaseColumn.AXIS_Z in standardized.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in standardized.columns

    def test_standardize_columns_creates_datetime(self, csv_loader: CSVDataSourceLoader, sample_dataframe: pd.DataFrame) -> None:
        """Test that datetime is created from date and time columns."""
        mapping = csv_loader.detect_columns(sample_dataframe)
        standardized = csv_loader._standardize_columns(sample_dataframe, mapping)

        assert pd.api.types.is_datetime64_any_dtype(standardized[DatabaseColumn.TIMESTAMP])

    def test_standardize_columns_combined_datetime(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test standardization with combined datetime column."""
        df = pd.DataFrame(
            {
                "datetime": ["2024-01-15 08:00:00", "2024-01-15 08:01:00"],
                "Axis1": [100, 120],
            }
        )

        mapping = ColumnMapping(datetime_column="datetime", activity_column="Axis1")

        standardized = csv_loader._standardize_columns(df, mapping)
        assert DatabaseColumn.TIMESTAMP in standardized.columns
        assert pd.api.types.is_datetime64_any_dtype(standardized[DatabaseColumn.TIMESTAMP])

    def test_vector_magnitude_calculation(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test vector magnitude is calculated from X, Y, Z."""
        df = pd.DataFrame(
            {
                "datetime": ["2024-01-15 08:00:00"],
                "Axis1": [3],  # Y-axis
                "Axis2": [4],  # X-axis
                "Axis3": [0],  # Z-axis
            }
        )

        mapping = ColumnMapping(datetime_column="datetime", activity_column="Axis1", axis_x_column="Axis2", axis_z_column="Axis3")

        standardized = csv_loader._standardize_columns(df, mapping)

        # VM should be sqrt(3^2 + 4^2 + 0^2) = 5
        assert DatabaseColumn.VECTOR_MAGNITUDE in standardized.columns
        assert standardized[DatabaseColumn.VECTOR_MAGNITUDE].iloc[0] == pytest.approx(5.0)

    def test_vector_magnitude_from_existing_column(self, csv_loader: CSVDataSourceLoader, sample_dataframe: pd.DataFrame) -> None:
        """Test that existing vector magnitude column is used if available."""
        mapping = csv_loader.detect_columns(sample_dataframe)
        standardized = csv_loader._standardize_columns(sample_dataframe, mapping)

        # Should use the existing Vector Magnitude column values
        assert DatabaseColumn.VECTOR_MAGNITUDE in standardized.columns
        assert standardized[DatabaseColumn.VECTOR_MAGNITUDE].iloc[0] == 150


class TestCSVLoaderDataValidation:
    """Tests for data validation."""

    def test_validate_data_valid(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation of valid data."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.date_range("2024-01-15 08:00:00", periods=3, freq="1min"),
                DatabaseColumn.AXIS_Y: [100, 120, 110],
            }
        )

        is_valid, errors = csv_loader.validate_data(df)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_data_missing_timestamp(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation fails when timestamp column is missing."""
        df = pd.DataFrame({DatabaseColumn.AXIS_Y: [100, 120, 110]})

        is_valid, errors = csv_loader.validate_data(df)
        assert is_valid is False
        assert any("timestamp" in err.lower() for err in errors)

    def test_validate_data_missing_activity(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation fails when activity column is missing."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.date_range("2024-01-15 08:00:00", periods=3, freq="1min"),
            }
        )

        is_valid, errors = csv_loader.validate_data(df)
        assert is_valid is False
        assert any("axis_y" in err.lower() for err in errors)

    def test_validate_data_empty_dataframe(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation fails for empty DataFrame."""
        df = pd.DataFrame(columns=[DatabaseColumn.TIMESTAMP, DatabaseColumn.AXIS_Y])

        is_valid, errors = csv_loader.validate_data(df)
        assert is_valid is False
        assert any("empty" in err.lower() for err in errors)

    def test_validate_data_wrong_timestamp_type(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation fails when timestamp is not datetime."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: ["2024-01-15 08:00:00", "2024-01-15 08:01:00"],
                DatabaseColumn.AXIS_Y: [100, 120],
            }
        )

        is_valid, errors = csv_loader.validate_data(df)
        assert is_valid is False
        assert any("datetime" in err.lower() for err in errors)

    def test_validate_data_wrong_activity_type(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation fails when activity is not numeric."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.date_range("2024-01-15 08:00:00", periods=2, freq="1min"),
                DatabaseColumn.AXIS_Y: ["100", "120"],  # String instead of numeric
            }
        )

        is_valid, errors = csv_loader.validate_data(df)
        assert is_valid is False
        assert any("numeric" in err.lower() for err in errors)


class TestCSVLoaderMetadataExtraction:
    """Tests for metadata extraction."""

    def test_get_file_metadata(self, csv_loader: CSVDataSourceLoader, sample_csv_file) -> None:
        """Test extracting file metadata."""
        metadata = csv_loader.get_file_metadata(sample_csv_file)

        assert "file_size" in metadata
        assert "device_type" in metadata
        assert "epoch_length_seconds" in metadata
        assert metadata["device_type"] == "actigraph"
        assert metadata["epoch_length_seconds"] == 60

    def test_get_file_metadata_not_found(self, csv_loader: CSVDataSourceLoader, tmp_path) -> None:
        """Test metadata extraction for non-existent file raises error."""
        from sleep_scoring_app.core.exceptions import ValidationError

        nonexistent = tmp_path / "nonexistent.csv"

        with pytest.raises(ValidationError):
            csv_loader.get_file_metadata(nonexistent)

    def test_load_file_includes_metadata(self, csv_loader: CSVDataSourceLoader, sample_csv_file) -> None:
        """Test that load_file includes comprehensive metadata."""
        result = csv_loader.load_file(sample_csv_file)
        metadata = result["metadata"]

        assert "file_size" in metadata
        assert "device_type" in metadata
        assert "epoch_length_seconds" in metadata
        assert "total_epochs" in metadata
        assert "start_time" in metadata
        assert "end_time" in metadata
        assert metadata["total_epochs"] == 5


class TestCSVLoaderCustomColumnMapping:
    """Tests for custom column mapping."""

    def test_create_custom_mapping_datetime_combined(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test custom mapping with combined datetime column."""
        df = pd.DataFrame(
            {
                "timestamp": ["2024-01-15 08:00:00"],
                "activity": [100],
            }
        )

        custom_columns = {"datetime_combined": True, "date": "timestamp", "activity": "activity"}

        mapping = csv_loader._create_custom_mapping(df, custom_columns)
        assert mapping.datetime_column == "timestamp"
        assert mapping.activity_column == "activity"

    def test_create_custom_mapping_separate_datetime(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test custom mapping with separate date and time columns."""
        df = pd.DataFrame(
            {
                "date_col": ["2024-01-15"],
                "time_col": ["08:00:00"],
                "counts": [100],
            }
        )

        custom_columns = {"date": "date_col", "time": "time_col", "activity": "counts"}

        mapping = csv_loader._create_custom_mapping(df, custom_columns)
        assert mapping.date_column == "date_col"
        assert mapping.time_column == "time_col"
        assert mapping.activity_column == "counts"

    def test_create_custom_mapping_with_axes(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test custom mapping with axis columns."""
        df = pd.DataFrame(
            {
                "datetime": ["2024-01-15 08:00:00"],
                "y": [100],
                "x": [80],
                "z": [90],
                "vm": [150],
            }
        )

        custom_columns = {
            "datetime_combined": True,
            "date": "datetime",
            "axis_y": "y",
            "axis_x": "x",
            "axis_z": "z",
            "vector_magnitude": "vm",
        }

        mapping = csv_loader._create_custom_mapping(df, custom_columns)
        assert mapping.activity_column == "y"
        assert mapping.axis_x_column == "x"
        assert mapping.axis_z_column == "z"
        assert mapping.vector_magnitude_column == "vm"


class TestCSVLoaderColumnMappingValidation:
    """Tests for column mapping validation."""

    def test_validate_column_mapping_valid(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation of valid column mapping."""
        mapping = ColumnMapping(datetime_column="timestamp", activity_column="Axis1")

        is_valid, errors = csv_loader._validate_column_mapping(mapping)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_column_mapping_missing_timestamp(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation fails without timestamp column."""
        mapping = ColumnMapping(activity_column="Axis1")

        is_valid, errors = csv_loader._validate_column_mapping(mapping)
        assert is_valid is False
        assert any("timestamp" in err.lower() for err in errors)

    def test_validate_column_mapping_missing_activity(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation fails without activity column."""
        mapping = ColumnMapping(datetime_column="timestamp")

        is_valid, errors = csv_loader._validate_column_mapping(mapping)
        assert is_valid is False
        assert any("activity" in err.lower() for err in errors)

    def test_validate_column_mapping_date_only(self, csv_loader: CSVDataSourceLoader) -> None:
        """Test validation passes with date column only."""
        mapping = ColumnMapping(date_column="Date", activity_column="Axis1")

        is_valid, errors = csv_loader._validate_column_mapping(mapping)
        assert is_valid is True
        assert len(errors) == 0
