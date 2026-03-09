"""
Tests for IO Data Source Loaders.

Tests CSVDataSourceLoader, DataSourceFactory, and column detection.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import DatabaseColumn
from sleep_scoring_app.core.dataclasses import ColumnMapping
from sleep_scoring_app.io.sources.csv_loader import CSVDataSourceLoader
from sleep_scoring_app.io.sources.loader_factory import DataSourceFactory


@pytest.fixture
def temp_csv_file() -> Path:
    """Create a temporary CSV file with valid activity data."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # Write 10 header rows (ActiGraph format)
        for i in range(10):
            f.write(f"Header row {i + 1}\n")

        # Write column headers
        f.write("Date,Time,Axis1,Axis2,Axis3,Vector Magnitude\n")

        # Write sample data
        f.write("2024-01-01,10:00:00,100,50,75,135\n")
        f.write("2024-01-01,10:01:00,200,60,80,220\n")
        f.write("2024-01-01,10:02:00,150,55,70,175\n")

    return Path(f.name)


@pytest.fixture
def temp_csv_combined_datetime() -> Path:
    """Create a CSV with combined datetime column."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        # No header rows
        f.write("Timestamp,Axis1\n")
        f.write("2024-01-01 10:00:00,100\n")
        f.write("2024-01-01 10:01:00,200\n")

    return Path(f.name)


@pytest.fixture
def csv_loader() -> CSVDataSourceLoader:
    """Create a CSV loader instance."""
    return CSVDataSourceLoader()


class TestCSVDataSourceLoaderProperties:
    """Tests for CSVDataSourceLoader properties."""

    def test_name(self, csv_loader: CSVDataSourceLoader) -> None:
        """Loader has correct name."""
        assert csv_loader.name == "CSV/XLSX File Loader"

    def test_identifier(self, csv_loader: CSVDataSourceLoader) -> None:
        """Loader has correct identifier."""
        assert csv_loader.identifier == "csv"

    def test_supported_extensions(self, csv_loader: CSVDataSourceLoader) -> None:
        """Loader supports expected extensions."""
        extensions = csv_loader.supported_extensions
        assert ".csv" in extensions
        assert ".xlsx" in extensions
        assert ".xls" in extensions

    def test_default_skip_rows(self) -> None:
        """Default skip_rows is 10 for ActiGraph."""
        loader = CSVDataSourceLoader()
        assert loader.skip_rows == 10

    def test_custom_skip_rows(self) -> None:
        """Can set custom skip_rows."""
        loader = CSVDataSourceLoader(skip_rows=5)
        assert loader.skip_rows == 5


class TestCSVDataSourceLoaderDetection:
    """Tests for column detection logic."""

    def test_detects_combined_datetime_column(self, csv_loader: CSVDataSourceLoader) -> None:
        """Detects combined datetime column."""
        df = pd.DataFrame({"Datetime": [], "Axis1": []})
        mapping = csv_loader.detect_columns(df)

        assert mapping.datetime_column == "Datetime"

    def test_detects_timestamp_column(self, csv_loader: CSVDataSourceLoader) -> None:
        """Detects timestamp column."""
        df = pd.DataFrame({"Timestamp": [], "Axis1": []})
        mapping = csv_loader.detect_columns(df)

        assert mapping.datetime_column == "Timestamp"

    def test_detects_separate_date_time_columns(self, csv_loader: CSVDataSourceLoader) -> None:
        """Detects separate date and time columns."""
        df = pd.DataFrame({"Date": [], "Time": [], "Axis1": []})
        mapping = csv_loader.detect_columns(df)

        assert mapping.date_column == "Date"
        assert mapping.time_column == "Time"

    def test_detects_vector_magnitude_column(self, csv_loader: CSVDataSourceLoader) -> None:
        """Detects vector magnitude column."""
        df = pd.DataFrame({"Datetime": [], "Vector Magnitude": []})
        mapping = csv_loader.detect_columns(df)

        assert mapping.activity_column == "Vector Magnitude"
        assert mapping.vector_magnitude_column == "Vector Magnitude"

    def test_detects_axis_columns(self, csv_loader: CSVDataSourceLoader) -> None:
        """Detects axis columns."""
        df = pd.DataFrame(
            {
                "Datetime": [],
                "Axis1": [],
                "Axis2": [],
                "Axis3": [],
            }
        )
        mapping = csv_loader.detect_columns(df)

        # Axis1 becomes activity column (Y-axis in ActiGraph)
        assert mapping.activity_column == "Axis1"
        assert mapping.axis_x_column == "Axis2"
        assert mapping.axis_z_column == "Axis3"

    def test_prioritizes_vector_magnitude_over_axis(self, csv_loader: CSVDataSourceLoader) -> None:
        """Prioritizes vector magnitude over individual axes."""
        df = pd.DataFrame(
            {
                "Datetime": [],
                "Axis1": [],
                "Vector Magnitude": [],
            }
        )
        mapping = csv_loader.detect_columns(df)

        assert mapping.activity_column == "Vector Magnitude"


class TestCSVDataSourceLoaderValidation:
    """Tests for column mapping validation."""

    def test_valid_mapping_with_datetime(self, csv_loader: CSVDataSourceLoader) -> None:
        """Valid mapping with datetime column."""
        mapping = ColumnMapping(
            datetime_column="Datetime",
            activity_column="Axis1",
        )
        is_valid, errors = csv_loader._validate_column_mapping(mapping)

        assert is_valid is True
        assert len(errors) == 0

    def test_valid_mapping_with_date(self, csv_loader: CSVDataSourceLoader) -> None:
        """Valid mapping with date column."""
        mapping = ColumnMapping(
            date_column="Date",
            activity_column="Axis1",
        )
        is_valid, errors = csv_loader._validate_column_mapping(mapping)

        assert is_valid is True
        assert len(errors) == 0

    def test_invalid_mapping_missing_timestamp(self, csv_loader: CSVDataSourceLoader) -> None:
        """Invalid mapping missing timestamp column."""
        mapping = ColumnMapping(activity_column="Axis1")
        is_valid, errors = csv_loader._validate_column_mapping(mapping)

        assert is_valid is False
        assert any("timestamp" in e.lower() for e in errors)

    def test_invalid_mapping_missing_activity(self, csv_loader: CSVDataSourceLoader) -> None:
        """Invalid mapping missing activity column."""
        mapping = ColumnMapping(datetime_column="Datetime")
        is_valid, errors = csv_loader._validate_column_mapping(mapping)

        assert is_valid is False
        assert any("activity" in e.lower() for e in errors)


class TestCSVDataSourceLoaderStandardization:
    """Tests for column standardization."""

    def test_standardizes_combined_datetime(self, csv_loader: CSVDataSourceLoader) -> None:
        """Standardizes combined datetime column."""
        df = pd.DataFrame(
            {
                "Datetime": ["2024-01-01 10:00:00", "2024-01-01 10:01:00"],
                "Axis1": [100, 200],
            }
        )
        mapping = ColumnMapping(datetime_column="Datetime", activity_column="Axis1")

        result = csv_loader._standardize_columns(df, mapping)

        assert DatabaseColumn.TIMESTAMP in result.columns
        assert DatabaseColumn.AXIS_Y in result.columns
        assert pd.api.types.is_datetime64_any_dtype(result[DatabaseColumn.TIMESTAMP])

    def test_standardizes_separate_date_time(self, csv_loader: CSVDataSourceLoader) -> None:
        """Standardizes separate date and time columns."""
        df = pd.DataFrame(
            {
                "Date": ["2024-01-01", "2024-01-01"],
                "Time": ["10:00:00", "10:01:00"],
                "Axis1": [100, 200],
            }
        )
        mapping = ColumnMapping(date_column="Date", time_column="Time", activity_column="Axis1")

        result = csv_loader._standardize_columns(df, mapping)

        assert DatabaseColumn.TIMESTAMP in result.columns
        assert pd.api.types.is_datetime64_any_dtype(result[DatabaseColumn.TIMESTAMP])

    def test_calculates_vector_magnitude_from_axes(self, csv_loader: CSVDataSourceLoader) -> None:
        """Calculates vector magnitude from X, Y, Z axes."""
        df = pd.DataFrame(
            {
                "Datetime": ["2024-01-01 10:00:00"],
                "Axis1": [100],  # Y
                "Axis2": [50],  # X
                "Axis3": [75],  # Z
            }
        )
        mapping = ColumnMapping(
            datetime_column="Datetime",
            activity_column="Axis1",
            axis_x_column="Axis2",
            axis_z_column="Axis3",
        )

        result = csv_loader._standardize_columns(df, mapping)

        assert DatabaseColumn.VECTOR_MAGNITUDE in result.columns
        # sqrt(100^2 + 50^2 + 75^2) ≈ 134.63
        expected_vm = (100**2 + 50**2 + 75**2) ** 0.5
        assert abs(result[DatabaseColumn.VECTOR_MAGNITUDE].iloc[0] - expected_vm) < 0.01


class TestCSVDataSourceLoaderDataValidation:
    """Tests for data validation."""

    def test_valid_data(self, csv_loader: CSVDataSourceLoader) -> None:
        """Validates correctly structured data."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.to_datetime(["2024-01-01 10:00:00"]),
                DatabaseColumn.AXIS_Y: [100.0],
            }
        )
        is_valid, errors = csv_loader.validate_data(df)

        assert is_valid is True
        assert len(errors) == 0

    def test_invalid_missing_timestamp(self, csv_loader: CSVDataSourceLoader) -> None:
        """Fails validation when timestamp missing."""
        df = pd.DataFrame({DatabaseColumn.AXIS_Y: [100.0]})
        is_valid, errors = csv_loader.validate_data(df)

        assert is_valid is False
        assert any(DatabaseColumn.TIMESTAMP in e for e in errors)

    def test_invalid_missing_axis_y(self, csv_loader: CSVDataSourceLoader) -> None:
        """Fails validation when AXIS_Y missing."""
        df = pd.DataFrame({DatabaseColumn.TIMESTAMP: pd.to_datetime(["2024-01-01 10:00:00"])})
        is_valid, errors = csv_loader.validate_data(df)

        assert is_valid is False
        assert any(DatabaseColumn.AXIS_Y in e for e in errors)

    def test_invalid_empty_dataframe(self, csv_loader: CSVDataSourceLoader) -> None:
        """Fails validation for empty DataFrame."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.to_datetime([]),
                DatabaseColumn.AXIS_Y: [],
            }
        )
        is_valid, errors = csv_loader.validate_data(df)

        assert is_valid is False
        assert any("empty" in e.lower() for e in errors)


class TestCSVDataSourceLoaderFileLoading:
    """Tests for file loading."""

    def test_load_valid_csv(self, csv_loader: CSVDataSourceLoader, temp_csv_file: Path) -> None:
        """Loads valid CSV file successfully."""
        result = csv_loader.load_file(temp_csv_file)

        assert "activity_data" in result
        assert "metadata" in result
        assert "column_mapping" in result
        assert len(result["activity_data"]) == 3

    def test_load_with_combined_datetime(self, csv_loader: CSVDataSourceLoader, temp_csv_combined_datetime: Path) -> None:
        """Loads CSV with combined datetime column."""
        result = csv_loader.load_file(temp_csv_combined_datetime, skip_rows=0)

        assert "activity_data" in result
        assert len(result["activity_data"]) == 2

    def test_load_nonexistent_file_raises(self, csv_loader: CSVDataSourceLoader) -> None:
        """Raises ValidationError for nonexistent file."""
        from sleep_scoring_app.core.exceptions import ValidationError

        with pytest.raises(ValidationError):
            csv_loader.load_file("/nonexistent/file.csv")

    def test_load_unsupported_extension_raises(self, csv_loader: CSVDataSourceLoader) -> None:
        """Raises ValidationError for unsupported extension."""
        from sleep_scoring_app.core.exceptions import ValidationError

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test")

        with pytest.raises(ValidationError):
            csv_loader.load_file(f.name)

    def test_load_extracts_metadata(self, csv_loader: CSVDataSourceLoader, temp_csv_file: Path) -> None:
        """Extracts metadata from loaded file."""
        result = csv_loader.load_file(temp_csv_file)
        metadata = result["metadata"]

        assert metadata["loader"] == "csv"
        assert metadata["total_epochs"] == 3
        assert "start_time" in metadata
        assert "end_time" in metadata

    def test_load_file_too_large_raises(self, csv_loader: CSVDataSourceLoader) -> None:
        """Raises ValueError for files exceeding size limit."""
        csv_loader.max_file_size = 10  # 10 bytes

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write("This is more than 10 bytes of content")

        with pytest.raises(ValueError, match="too large"):
            csv_loader.load_file(f.name)


class TestCSVDataSourceLoaderCustomMapping:
    """Tests for custom column mapping."""

    def test_custom_column_mapping(self, csv_loader: CSVDataSourceLoader) -> None:
        """Uses custom column mapping when provided."""
        df = pd.DataFrame(
            {
                "my_date": ["2024-01-01"],
                "my_time": ["10:00:00"],
                "my_activity": [100],
            }
        )
        custom_columns = {
            "date": "my_date",
            "time": "my_time",
            "activity": "my_activity",
        }

        mapping = csv_loader._create_custom_mapping(df, custom_columns)

        assert mapping.date_column == "my_date"
        assert mapping.time_column == "my_time"
        assert mapping.activity_column == "my_activity"


class TestDataSourceFactoryCreate:
    """Tests for DataSourceFactory.create method."""

    def test_create_csv_loader(self) -> None:
        """Creates CSV loader."""
        loader = DataSourceFactory.create("csv")

        assert loader.identifier == "csv"
        assert isinstance(loader, CSVDataSourceLoader)

    def test_create_unknown_loader_raises(self) -> None:
        """Raises ValueError for unknown loader ID."""
        with pytest.raises(ValueError, match="Unknown"):
            DataSourceFactory.create("unknown_loader")

    def test_create_with_kwargs(self) -> None:
        """Passes kwargs to loader constructor."""
        loader = DataSourceFactory.create("csv", skip_rows=5)

        assert loader.skip_rows == 5


class TestDataSourceFactoryRegistry:
    """Tests for DataSourceFactory registry."""

    def test_get_available_loaders(self) -> None:
        """Returns dictionary of available loaders."""
        loaders = DataSourceFactory.get_available_loaders()

        assert isinstance(loaders, dict)
        assert "csv" in loaders
        assert "gt3x" in loaders

    def test_is_registered(self) -> None:
        """Checks if loader is registered."""
        assert DataSourceFactory.is_registered("csv") is True
        assert DataSourceFactory.is_registered("nonexistent") is False

    def test_get_default_loader_id(self) -> None:
        """Returns default loader ID."""
        assert DataSourceFactory.get_default_loader_id() == "csv"

    def test_get_supported_extensions(self) -> None:
        """Returns all supported extensions."""
        extensions = DataSourceFactory.get_supported_extensions()

        assert ".csv" in extensions
        assert ".xlsx" in extensions
        assert ".xls" in extensions
        assert ".gt3x" in extensions


class TestDataSourceFactoryExtensionSelection:
    """Tests for extension-based loader selection."""

    def test_get_loader_for_csv_extension(self) -> None:
        """Selects CSV loader for .csv extension."""
        loader = DataSourceFactory.get_loader_for_extension(".csv")

        assert loader.identifier == "csv"

    def test_get_loader_for_xlsx_extension(self) -> None:
        """Selects CSV loader for .xlsx extension."""
        loader = DataSourceFactory.get_loader_for_extension(".xlsx")

        assert loader.identifier == "csv"

    def test_get_loader_for_gt3x_extension(self) -> None:
        """Selects GT3X loader for .gt3x extension."""
        loader = DataSourceFactory.get_loader_for_extension(".gt3x")

        # Could be gt3x or gt3x_rs depending on availability
        assert "gt3x" in loader.identifier

    def test_get_loader_normalizes_extension(self) -> None:
        """Normalizes extension (case, leading dot)."""
        loader1 = DataSourceFactory.get_loader_for_extension("csv")
        loader2 = DataSourceFactory.get_loader_for_extension(".CSV")

        assert loader1.identifier == loader2.identifier

    def test_get_loader_for_unknown_extension_raises(self) -> None:
        """Raises ValueError for unknown extension."""
        with pytest.raises(ValueError, match="No loader found"):
            DataSourceFactory.get_loader_for_extension(".unknown")

    def test_get_loader_for_file_path(self) -> None:
        """Selects loader based on file path."""
        loader = DataSourceFactory.get_loader_for_file("/data/activity.csv")

        assert loader.identifier == "csv"


class TestDataSourceFactoryRegistration:
    """Tests for dynamic loader registration."""

    def test_register_new_loader(self) -> None:
        """Registers new loader."""
        # Create a mock loader class
        mock_loader_class = MagicMock()
        mock_loader_class.SUPPORTED_EXTENSIONS = frozenset({".test"})

        # Register it
        DataSourceFactory.register("test_loader", mock_loader_class, "Test Loader")

        assert DataSourceFactory.is_registered("test_loader")

        # Clean up
        del DataSourceFactory._registry["test_loader"]

    def test_register_duplicate_raises(self) -> None:
        """Raises ValueError when registering duplicate ID."""
        mock_loader_class = MagicMock()

        with pytest.raises(ValueError, match="already registered"):
            DataSourceFactory.register("csv", mock_loader_class, "Duplicate")


class TestColumnMapping:
    """Tests for ColumnMapping dataclass."""

    def test_default_values(self) -> None:
        """Has None default values."""
        mapping = ColumnMapping()

        assert mapping.datetime_column is None
        assert mapping.date_column is None
        assert mapping.time_column is None
        assert mapping.activity_column is None
        assert mapping.axis_x_column is None
        assert mapping.axis_z_column is None
        assert mapping.vector_magnitude_column is None

    def test_with_values(self) -> None:
        """Can set values."""
        mapping = ColumnMapping(
            datetime_column="Datetime",
            activity_column="Axis1",
        )

        assert mapping.datetime_column == "Datetime"
        assert mapping.activity_column == "Axis1"


@pytest.fixture(autouse=True)
def cleanup_temp_files(temp_csv_file: Path, temp_csv_combined_datetime: Path):
    """Clean up temporary files after tests."""
    yield
    # Cleanup
    if temp_csv_file.exists():
        temp_csv_file.unlink()
    if temp_csv_combined_datetime.exists():
        temp_csv_combined_datetime.unlink()
