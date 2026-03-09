"""
Integration tests for GT3X file loading.

Tests the complete GT3X loading pipeline with a real ActiGraph wGT3X-BT file.
This validates:
- Factory pattern correctly identifies GT3X files
- GT3X loader instantiation and configuration
- Real file parsing through pygt3x library
- Data structure compatibility with application expectations
- Metadata extraction and validation
- Both epoch and raw mode loading

Test File:
    Test_GT3X.gt3x
    Real ActiGraph wGT3X-BT device data (~32 days, ~47000 epochs at 60-second resolution)
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import DatabaseColumn
from sleep_scoring_app.io.sources.loader_factory import DataSourceFactory

if TYPE_CHECKING:
    from sleep_scoring_app.io.sources.loader_protocol import DataSourceLoader

# Path to real test file in repository root
GT3X_TEST_FILE = Path(__file__).parents[4] / "Test_GT3X.gt3x"


@pytest.fixture
def gt3x_file():
    """
    Fixture providing path to real GT3X test file.

    Skips test if file not found (file is large, may not be in all environments).
    """
    if not GT3X_TEST_FILE.exists():
        pytest.skip(f"Test file not found: {GT3X_TEST_FILE}")
    return GT3X_TEST_FILE


@pytest.fixture
def gt3x_loader() -> DataSourceLoader:
    """Create GT3X loader with default settings (60-second epochs). Uses gt3x-rs if available."""
    return DataSourceFactory.create("gt3x", epoch_length_seconds=60, return_raw=False)


@pytest.fixture
def gt3x_loader_raw() -> DataSourceLoader:
    """Create GT3X loader configured for raw high-frequency data. Uses gt3x-rs if available."""
    return DataSourceFactory.create("gt3x", return_raw=True)


class TestGT3XFactoryIntegration:
    """Test GT3X loader creation through factory pattern."""

    def test_factory_creates_gt3x_loader_by_id(self) -> None:
        """Test factory creates GT3X loader when requested by ID."""
        loader = DataSourceFactory.create("gt3x")

        assert loader is not None
        # May be DataSourceLoader or Gt3xRsDataSourceLoader depending on availability
        assert hasattr(loader, "load_file")
        assert loader.identifier in ("gt3x", "gt3x_rs")
        assert "GT3X" in loader.name

    def test_factory_detects_gt3x_extension(self) -> None:
        """Test factory auto-selects GT3X loader for .gt3x extension."""
        loader = DataSourceFactory.get_loader_for_extension(".gt3x")

        assert loader is not None
        # May be DataSourceLoader or Gt3xRsDataSourceLoader depending on availability
        assert hasattr(loader, "load_file")
        assert loader.identifier in ("gt3x", "gt3x_rs")

    def test_factory_detects_gt3x_from_file_path(self, gt3x_file: Path) -> None:
        """Test factory auto-selects GT3X loader from file path."""
        loader = DataSourceFactory.get_loader_for_file(gt3x_file)

        assert loader is not None
        # May be DataSourceLoader or Gt3xRsDataSourceLoader depending on availability
        assert hasattr(loader, "load_file")
        assert loader.identifier in ("gt3x", "gt3x_rs")

    def test_gt3x_in_supported_extensions(self) -> None:
        """Test .gt3x extension is in factory's supported extensions."""
        supported = DataSourceFactory.get_supported_extensions()

        assert ".gt3x" in supported


class TestGT3XRealFileLoading:
    """Test loading real GT3X file in epoch mode."""

    def test_load_real_file_epochs(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loading real GT3X file returns expected epoch count."""
        result = gt3x_loader.load_file(gt3x_file)

        assert "activity_data" in result
        assert "metadata" in result
        assert "column_mapping" in result

        df = result["activity_data"]

        # Test_GT3X.gt3x contains ~785 hours (32 days) of data at 30Hz
        # At 60-second epochs: 785 * 60 = ~47,100 epochs
        # Allow reasonable range for device start/stop
        assert len(df) > 1000, f"Expected many epochs, got {len(df)}"

    def test_load_real_file_has_correct_columns(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loaded data has expected column structure."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # Check required columns exist
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.AXIS_X in df.columns
        assert DatabaseColumn.AXIS_Y in df.columns
        assert DatabaseColumn.AXIS_Z in df.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in df.columns

    def test_load_real_file_correct_data_types(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loaded data has correct data types."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # TIMESTAMP must be datetime
        assert pd.api.types.is_datetime64_any_dtype(df[DatabaseColumn.TIMESTAMP])

        # Activity columns must be numeric (float)
        assert pd.api.types.is_numeric_dtype(df[DatabaseColumn.AXIS_X])
        assert pd.api.types.is_numeric_dtype(df[DatabaseColumn.AXIS_Y])
        assert pd.api.types.is_numeric_dtype(df[DatabaseColumn.AXIS_Z])
        assert pd.api.types.is_numeric_dtype(df[DatabaseColumn.VECTOR_MAGNITUDE])

    def test_load_real_file_no_nan_in_critical_columns(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loaded data has no NaN values in critical columns."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # No NaN in timestamp
        assert df[DatabaseColumn.TIMESTAMP].isna().sum() == 0

        # No NaN in activity columns
        assert df[DatabaseColumn.AXIS_X].isna().sum() == 0
        assert df[DatabaseColumn.AXIS_Y].isna().sum() == 0
        assert df[DatabaseColumn.AXIS_Z].isna().sum() == 0
        assert df[DatabaseColumn.VECTOR_MAGNITUDE].isna().sum() == 0

    def test_load_real_file_timestamps_sorted(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loaded data has sorted timestamps."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # Timestamps should be monotonically increasing
        timestamps = df[DatabaseColumn.TIMESTAMP]
        assert timestamps.is_monotonic_increasing, "Timestamps must be sorted"

    def test_load_real_file_epoch_spacing(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loaded data has correct epoch spacing (60 seconds)."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # Calculate time differences between consecutive epochs
        time_diffs = df[DatabaseColumn.TIMESTAMP].diff()[1:]  # Skip first NaT

        # Convert to seconds
        time_diffs_seconds = time_diffs.dt.total_seconds()

        # Most epochs should be 60 seconds apart
        # Allow some tolerance for device start/stop
        median_diff = time_diffs_seconds.median()
        assert 59 <= median_diff <= 61, f"Expected 60-second epochs, got median {median_diff}"

    def test_load_real_file_activity_values_reasonable(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loaded activity values are in reasonable range."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # For epoch data (sum of absolute accelerations), values should be positive
        assert (df[DatabaseColumn.AXIS_X] >= 0).all()
        assert (df[DatabaseColumn.AXIS_Y] >= 0).all()
        assert (df[DatabaseColumn.AXIS_Z] >= 0).all()
        assert (df[DatabaseColumn.VECTOR_MAGNITUDE] >= 0).all()

        # Check that we have non-zero values (device was recording activity)
        assert df[DatabaseColumn.AXIS_Y].max() > 0
        assert df[DatabaseColumn.VECTOR_MAGNITUDE].max() > 0


class TestGT3XRealFileRawMode:
    """Test loading real GT3X file in raw mode."""

    def test_load_real_file_raw_mode(self, gt3x_loader_raw: DataSourceLoader, gt3x_file: Path) -> None:
        """Test loading real GT3X file in raw mode returns millions of samples."""
        result = gt3x_loader_raw.load_file(gt3x_file)
        df = result["activity_data"]

        # File contains ~32 days at 30Hz = ~85 million samples
        # Allow wide range due to variable sample rates and device start/stop
        assert len(df) > 1000000, f"Expected millions of raw samples, got {len(df)}"

    def test_raw_mode_has_same_columns(self, gt3x_loader_raw: DataSourceLoader, gt3x_file: Path) -> None:
        """Test raw mode has same column structure as epoch mode."""
        result = gt3x_loader_raw.load_file(gt3x_file)
        df = result["activity_data"]

        # Same columns as epoch mode
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.AXIS_X in df.columns
        assert DatabaseColumn.AXIS_Y in df.columns
        assert DatabaseColumn.AXIS_Z in df.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in df.columns

    def test_raw_mode_different_value_range(self, gt3x_loader_raw: DataSourceLoader, gt3x_file: Path) -> None:
        """Test raw mode has different value range than epoch mode (individual g values)."""
        result = gt3x_loader_raw.load_file(gt3x_file)
        df = result["activity_data"]

        # Raw data should be in g-units (typically -20g to +20g)
        # Take absolute max across all axes
        max_x = df[DatabaseColumn.AXIS_X].abs().max()
        max_y = df[DatabaseColumn.AXIS_Y].abs().max()
        max_z = df[DatabaseColumn.AXIS_Z].abs().max()

        # Reasonable range for raw accelerometer data
        assert max_x < 20, f"X-axis raw values too high: {max_x}"
        assert max_y < 20, f"Y-axis raw values too high: {max_y}"
        assert max_z < 20, f"Z-axis raw values too high: {max_z}"


class TestGT3XMetadataExtraction:
    """Test metadata extraction from real GT3X file."""

    def test_metadata_contains_expected_fields(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test metadata dictionary contains expected fields."""
        result = gt3x_loader.load_file(gt3x_file)
        metadata = result["metadata"]

        # Required metadata fields
        assert "file_size" in metadata
        assert "serial_number" in metadata
        assert "sample_rate" in metadata
        assert "start_time" in metadata
        assert "end_time" in metadata
        assert "total_epochs" in metadata
        assert "total_samples" in metadata
        assert "epoch_length_seconds" in metadata

    def test_metadata_serial_number(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test metadata extracts correct serial number from filename."""
        result = gt3x_loader.load_file(gt3x_file)
        metadata = result["metadata"]

        # Serial number should be extracted from file
        assert metadata["serial_number"] is not None
        # Based on filename: TestUA_MOS2E22180349_2023-03-07___09-39-04.gt3x
        # Serial number is likely MOS2E22180349
        assert isinstance(metadata["serial_number"], str)
        assert len(metadata["serial_number"]) > 0

    def test_metadata_sample_rate(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test metadata extracts sample rate."""
        result = gt3x_loader.load_file(gt3x_file)
        metadata = result["metadata"]

        # Sample rate should be a positive number (typically 30, 60, or 100 Hz)
        assert metadata["sample_rate"] > 0
        assert metadata["sample_rate"] <= 100

    def test_metadata_timestamps(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test metadata contains valid start and end times."""
        result = gt3x_loader.load_file(gt3x_file)
        metadata = result["metadata"]

        # Start and end times should be datetime objects
        start_time = metadata["start_time"]
        end_time = metadata["end_time"]

        assert isinstance(start_time, pd.Timestamp | pd.DatetimeIndex)
        assert isinstance(end_time, pd.Timestamp | pd.DatetimeIndex)

        # End time should be after start time
        # Convert to Timestamp if needed for comparison
        if isinstance(start_time, pd.DatetimeIndex):
            start_time = start_time[0]
        if isinstance(end_time, pd.DatetimeIndex):
            end_time = end_time[0]

        assert end_time > start_time

    def test_metadata_epoch_count(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test metadata epoch count matches DataFrame length."""
        result = gt3x_loader.load_file(gt3x_file)
        metadata = result["metadata"]
        df = result["activity_data"]

        # Epoch count in metadata should match DataFrame length
        assert metadata["total_epochs"] == len(df)

    def test_metadata_epoch_length(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test metadata records epoch length setting."""
        result = gt3x_loader.load_file(gt3x_file)
        metadata = result["metadata"]

        # Should match loader configuration
        assert metadata["epoch_length_seconds"] == 60

    def test_get_file_metadata_without_loading(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test get_file_metadata extracts metadata without loading full data."""
        metadata = gt3x_loader.get_file_metadata(gt3x_file)

        # Should have basic fields (start_time requires parsing full data)
        assert "file_size" in metadata
        assert "serial_number" in metadata
        assert "sample_rate" in metadata
        assert "total_samples" in metadata

        # File size should be positive
        assert metadata["file_size"] > 0
        assert metadata["total_samples"] > 0


class TestGT3XDataValidation:
    """Test data validation during GT3X loading."""

    def test_validation_passes_for_real_file(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test validation passes for real GT3X file."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # Validate should pass without raising
        is_valid, errors = gt3x_loader.validate_data(df)

        assert is_valid is True
        assert len(errors) == 0

    def test_load_file_validates_automatically(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test load_file performs validation automatically (should not raise)."""
        # This should complete without raising ValueError
        result = gt3x_loader.load_file(gt3x_file)

        assert result is not None
        assert "activity_data" in result


class TestGT3XColumnMapping:
    """Test column mapping for GT3X files."""

    def test_column_mapping_structure(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test column mapping has correct structure."""
        result = gt3x_loader.load_file(gt3x_file)
        column_mapping = result["column_mapping"]

        # Column mapping should have standard fields
        assert column_mapping.datetime_column == DatabaseColumn.TIMESTAMP
        assert column_mapping.activity_column == DatabaseColumn.AXIS_Y
        assert column_mapping.axis_x_column == DatabaseColumn.AXIS_X
        assert column_mapping.axis_z_column == DatabaseColumn.AXIS_Z
        assert column_mapping.vector_magnitude_column == DatabaseColumn.VECTOR_MAGNITUDE

    def test_detect_columns_returns_fixed_mapping(self, gt3x_loader: DataSourceLoader, gt3x_file: Path) -> None:
        """Test detect_columns returns fixed mapping (GT3X format is standardized)."""
        result = gt3x_loader.load_file(gt3x_file)
        df = result["activity_data"]

        # Detect columns should return same mapping as in result
        mapping = gt3x_loader.detect_columns(df)

        assert mapping.datetime_column == DatabaseColumn.TIMESTAMP
        assert mapping.activity_column == DatabaseColumn.AXIS_Y


class TestGT3XEpochModeComparison:
    """Test different epoch lengths and modes."""

    def test_30_second_epochs(self, gt3x_file: Path) -> None:
        """Test loading with 30-second epochs."""
        loader = DataSourceFactory.create("gt3x", epoch_length_seconds=30, return_raw=False)
        result = loader.load_file(gt3x_file)
        df = result["activity_data"]

        # Should have approximately 2x epochs compared to 60-second
        # 32 days * 24 * 60 * 2 = ~92,000 epochs
        assert len(df) > 2000, f"Expected many 30-second epochs, got {len(df)}"

    def test_raw_vs_epoch_same_file(self, gt3x_file: Path) -> None:
        """Test raw mode has more rows than epoch mode for same file."""
        loader_epoch = DataSourceFactory.create("gt3x", epoch_length_seconds=60, return_raw=False)
        loader_raw = DataSourceFactory.create("gt3x", return_raw=True)

        result_epoch = loader_epoch.load_file(gt3x_file)
        result_raw = loader_raw.load_file(gt3x_file)

        df_epoch = result_epoch["activity_data"]
        df_raw = result_raw["activity_data"]

        # Raw should have many more rows (individual samples vs aggregated epochs)
        assert len(df_raw) > len(df_epoch) * 100


class TestGT3XFileNotFound:
    """Test error handling for missing files."""

    def test_load_nonexistent_file_raises(self, gt3x_loader: DataSourceLoader) -> None:
        """Test loading non-existent file raises ValidationError."""
        from sleep_scoring_app.core.exceptions import ValidationError

        nonexistent = Path("nonexistent_file.gt3x")

        with pytest.raises(ValidationError, match="FILE_NOT_FOUND"):
            gt3x_loader.load_file(nonexistent)

    def test_get_metadata_nonexistent_file_raises(self, gt3x_loader: DataSourceLoader) -> None:
        """Test getting metadata from non-existent file raises ValidationError."""
        from sleep_scoring_app.core.exceptions import ValidationError

        nonexistent = Path("nonexistent_file.gt3x")

        with pytest.raises(ValidationError, match="FILE_NOT_FOUND"):
            gt3x_loader.get_file_metadata(nonexistent)


class TestGT3XEndToEndWorkflow:
    """Test complete end-to-end GT3X loading workflow."""

    def test_complete_workflow(self, gt3x_file: Path) -> None:
        """Test complete workflow: factory -> loader -> load -> validate."""
        # Step 1: Get loader from factory
        loader = DataSourceFactory.get_loader_for_file(gt3x_file)
        assert loader.identifier in ("gt3x", "gt3x_rs")

        # Step 2: Load file
        result = loader.load_file(gt3x_file)
        assert "activity_data" in result

        # Step 3: Extract data
        df = result["activity_data"]
        metadata = result["metadata"]
        column_mapping = result["column_mapping"]

        # Step 4: Validate structure
        assert len(df) > 1000
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.AXIS_Y in df.columns

        # Step 5: Validate data
        is_valid, _errors = loader.validate_data(df)
        assert is_valid is True

        # Step 6: Check metadata
        assert metadata["total_epochs"] == len(df)

        # Step 7: Verify column mapping
        assert column_mapping.activity_column == DatabaseColumn.AXIS_Y

        # Workflow completed successfully
        assert True
