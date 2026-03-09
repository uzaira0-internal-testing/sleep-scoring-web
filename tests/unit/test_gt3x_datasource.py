"""
Unit tests for GT3XDataSourceLoader.

Tests the GT3X binary data source loader implementation.
Mock GT3X files include proper log.bin files compatible with both pygt3x and gt3x-rs backends.
"""

from __future__ import annotations

import struct
import zipfile
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.constants import DatabaseColumn
from sleep_scoring_app.core.dataclasses import ColumnMapping
from sleep_scoring_app.io.sources.gt3x_loader import GT3XDataSourceLoader
from sleep_scoring_app.io.sources.loader_protocol import DataSourceLoader


@pytest.fixture
def gt3x_loader() -> GT3XDataSourceLoader:
    """Create GT3X loader instance for testing."""
    return GT3XDataSourceLoader()


@pytest.fixture
def gt3x_loader_raw() -> GT3XDataSourceLoader:
    """Create GT3X loader configured to return raw samples."""
    return GT3XDataSourceLoader(return_raw=True)


def _create_log_bin(n_samples: int, sample_rate: int = 30) -> bytes:
    """Create a valid log.bin file with ACTIVITY2 records for gt3x-rs.

    GT3X log.bin format:
    - 1 byte separator (0x1E)
    - 1 byte record type (0x1A for ACTIVITY2)
    - 4 bytes timestamp (u32 little-endian, seconds since device epoch)
    - 2 bytes payload size (u16 little-endian)
    - payload bytes (for ACTIVITY2: 6 bytes per sample as 3 x int16 LE)
    - 1 byte checksum (bitwise NOT of XOR of all header and payload bytes)

    gt3x-rs checksum validation: (!xor_result) == checksum
    So checksum = ~(xor of all bytes) & 0xFF
    """
    RECORD_SEPARATOR = 0x1E
    RECORD_ACTIVITY2 = 0x1A

    log_data = b""

    # Create activity records - each record contains samples for 1 second
    samples_per_record = sample_rate
    n_records = (n_samples + samples_per_record - 1) // samples_per_record

    for record_idx in range(n_records):
        timestamp = record_idx  # Seconds since start

        # Generate samples for this record
        record_samples = min(samples_per_record, n_samples - record_idx * samples_per_record)

        # ACTIVITY2 format: 6 bytes per sample (3 x int16 little-endian, XYZ order)
        payload = b""
        sample_idx = record_idx * samples_per_record
        for s in range(record_samples):
            i = sample_idx + s
            # Create varying acceleration values (raw ADC values)
            # Scale is 341.0, so 341 raw = 1g
            x_raw = int(100 * np.sin(i / 10)) + 100
            y_raw = int(341 + 50 * np.cos(i / 10))  # ~1g vertical
            z_raw = int(50 * np.sin(i / 15))

            # Clamp to int16 range
            x_raw = max(-32768, min(32767, x_raw))
            y_raw = max(-32768, min(32767, y_raw))
            z_raw = max(-32768, min(32767, z_raw))

            # Pack as 16-bit little-endian (XYZ order for ACTIVITY2)
            payload += struct.pack("<hhh", x_raw, y_raw, z_raw)

        payload_size = len(payload)

        # Build header: separator, type, timestamp (u32 LE), payload_size (u16 LE)
        header = struct.pack("<BBIH", RECORD_SEPARATOR, RECORD_ACTIVITY2, timestamp, payload_size)

        # Calculate checksum: XOR all header and payload bytes, then bitwise NOT
        # gt3x-rs expects: (!xor_result) == checksum
        xor_result = 0
        for b in header:
            xor_result ^= b
        for b in payload:
            xor_result ^= b
        checksum = (~xor_result) & 0xFF  # Bitwise NOT, masked to 8 bits

        log_data += header + payload + struct.pack("B", checksum)

    return log_data


@pytest.fixture
def mock_gt3x_file(tmp_path):
    """Create a mock GT3X file with realistic structure compatible with gt3x-rs."""
    gt3x_path = tmp_path / "test.gt3x"

    # Create info.txt content (gt3x-rs expects .NET ticks for dates)
    # .NET ticks for 2024-01-15 08:00:00 UTC
    start_ticks = 638412384000000000
    stop_ticks = 638412420000000000

    info_content = f"""Serial Number: TEST123
Device Type: wGT3X-BT
Firmware: 2.5.0
Sample Rate: 30
Start Date: {start_ticks}
Stop Date: {stop_ticks}
TimeZone: 00:00:00
Acceleration Scale: 341.0
"""

    # Create log.bin with ACTIVITY2 records (required by gt3x-rs)
    n_samples = 180  # 6 seconds at 30 Hz
    log_bin = _create_log_bin(n_samples, sample_rate=30)

    # Create ZIP archive with log.bin
    with zipfile.ZipFile(gt3x_path, "w") as zf:
        zf.writestr("info.txt", info_content)
        zf.writestr("log.bin", log_bin)

    return gt3x_path


@pytest.fixture
def mock_gt3x_file_large_epoch(tmp_path):
    """Create GT3X file with enough data for full epoch aggregation compatible with gt3x-rs."""
    gt3x_path = tmp_path / "test_large.gt3x"

    # Create info.txt (gt3x-rs expects .NET ticks for dates)
    # .NET ticks for 2024-01-15 08:00:00 UTC
    start_ticks = 638412384000000000

    info_content = f"""Serial Number: TEST456
Device Type: wGT3X-BT
Sample Rate: 30
Start Date: {start_ticks}
Stop Date: 0
TimeZone: 00:00:00
Acceleration Scale: 341.0
"""

    # Create log.bin with ACTIVITY2 records (required by gt3x-rs)
    # Create 3 minutes of data (3 * 60 * 30 = 5400 samples)
    n_samples = 5400
    log_bin = _create_log_bin(n_samples, sample_rate=30)

    with zipfile.ZipFile(gt3x_path, "w") as zf:
        zf.writestr("info.txt", info_content)
        zf.writestr("log.bin", log_bin)

    return gt3x_path


class TestGT3XLoaderProperties:
    """Tests for GT3X loader properties."""

    def test_gt3x_loader_name(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test GT3X loader has correct name."""
        assert gt3x_loader.name == "GT3X File Loader"

    def test_gt3x_loader_identifier(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test GT3X loader has correct identifier."""
        assert gt3x_loader.identifier == "gt3x"

    def test_gt3x_loader_supported_extensions(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test GT3X loader supports .gt3x extension."""
        extensions = gt3x_loader.supported_extensions
        assert ".gt3x" in extensions
        assert len(extensions) == 1

    def test_gt3x_loader_protocol_compliance(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test GT3X loader implements DataSourceLoader protocol."""
        assert isinstance(gt3x_loader, DataSourceLoader)

    def test_gt3x_loader_default_epoch_length(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test GT3X loader has default 60-second epoch length."""
        assert gt3x_loader.epoch_length_seconds == 60

    def test_gt3x_loader_custom_epoch_length(self) -> None:
        """Test GT3X loader can be initialized with custom epoch length."""
        loader = GT3XDataSourceLoader(epoch_length_seconds=30)
        assert loader.epoch_length_seconds == 30

    def test_gt3x_loader_raw_mode(self, gt3x_loader_raw: GT3XDataSourceLoader) -> None:
        """Test GT3X loader can be configured for raw mode."""
        assert gt3x_loader_raw.return_raw is True


class TestGT3XLoaderColumnDetection:
    """Tests for column detection (GT3X has fixed columns)."""

    def test_detect_columns_fixed(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test GT3X loader returns fixed column mapping."""
        # Create dummy DataFrame (doesn't matter what columns it has)
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.date_range("2024-01-15", periods=3, freq="1min"),
                DatabaseColumn.AXIS_X: [1, 2, 3],
                DatabaseColumn.AXIS_Y: [1, 2, 3],
                DatabaseColumn.AXIS_Z: [1, 2, 3],
            }
        )

        mapping = gt3x_loader.detect_columns(df)

        assert isinstance(mapping, ColumnMapping)
        assert mapping.datetime_column == DatabaseColumn.TIMESTAMP
        assert mapping.activity_column == DatabaseColumn.AXIS_Y
        assert mapping.axis_x_column == DatabaseColumn.AXIS_X
        assert mapping.axis_z_column == DatabaseColumn.AXIS_Z
        assert mapping.vector_magnitude_column == DatabaseColumn.VECTOR_MAGNITUDE


class TestGT3XLoaderFileLoading:
    """Tests for GT3X file loading."""

    def test_load_mock_gt3x(self, gt3x_loader: GT3XDataSourceLoader, mock_gt3x_file_large_epoch) -> None:
        """Test loading a mock GT3X file."""
        result = gt3x_loader.load_file(mock_gt3x_file_large_epoch)

        assert "activity_data" in result
        assert "metadata" in result
        assert "column_mapping" in result

        df = result["activity_data"]
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.AXIS_X in df.columns
        assert DatabaseColumn.AXIS_Y in df.columns
        assert DatabaseColumn.AXIS_Z in df.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in df.columns

    def test_load_file_not_found(self, gt3x_loader: GT3XDataSourceLoader, tmp_path) -> None:
        """Test loading non-existent file raises error."""
        from sleep_scoring_app.core.exceptions import ValidationError

        nonexistent = tmp_path / "nonexistent.gt3x"

        with pytest.raises(ValidationError):
            gt3x_loader.load_file(nonexistent)

    def test_load_invalid_zip(self, gt3x_loader: GT3XDataSourceLoader, tmp_path) -> None:
        """Test loading invalid ZIP file raises error."""
        invalid_zip = tmp_path / "invalid.gt3x"
        invalid_zip.write_text("This is not a ZIP file")

        with pytest.raises(ValueError, match="Error reading GT3X file"):
            gt3x_loader.load_file(invalid_zip)

    def test_load_missing_info_txt(self, gt3x_loader: GT3XDataSourceLoader, tmp_path) -> None:
        """Test loading GT3X without info.txt raises error."""
        gt3x_path = tmp_path / "missing_info.gt3x"

        with zipfile.ZipFile(gt3x_path, "w") as zf:
            # Only include activity.bin and log.txt, no info.txt
            zf.writestr("activity.bin", b"\x00" * 100)
            zf.writestr("log.txt", "")

        with pytest.raises(ValueError, match="Error reading GT3X file"):
            gt3x_loader.load_file(gt3x_path)

    def test_load_missing_activity_bin(self, gt3x_loader: GT3XDataSourceLoader, tmp_path) -> None:
        """Test loading GT3X without activity.bin raises error."""
        gt3x_path = tmp_path / "missing_activity.gt3x"

        info_content = "Serial Number: TEST\nSample Rate: 30 Hz\nStart Date: 2024-01-15\nStart Time: 08:00:00"

        with zipfile.ZipFile(gt3x_path, "w") as zf:
            zf.writestr("info.txt", info_content)
            zf.writestr("log.txt", "")

        with pytest.raises(ValueError, match="Error reading GT3X file"):
            gt3x_loader.load_file(gt3x_path)

    def test_load_raw_mode(self, gt3x_loader_raw: GT3XDataSourceLoader, mock_gt3x_file) -> None:
        """Test loading GT3X in raw mode returns individual samples."""
        result = gt3x_loader_raw.load_file(mock_gt3x_file)
        df = result["activity_data"]

        # Should have raw samples (not aggregated into epochs)
        # pygt3x may add idle sleep mode samples, so just check we got samples
        assert len(df) > 0
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in df.columns

    def test_load_epoch_mode(self, mock_gt3x_file_large_epoch) -> None:
        """Test loading GT3X in epoch mode aggregates data."""
        # Create loader with 60-second epochs
        loader = GT3XDataSourceLoader(epoch_length_seconds=60, return_raw=False)

        result = loader.load_file(mock_gt3x_file_large_epoch)
        df = result["activity_data"]

        # File has data that gets aggregated into epochs
        # pygt3x may add samples, so just verify we got epochs
        assert len(df) >= 3
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in df.columns


class TestGT3XLoaderMetadataParsing:
    """Tests for metadata parsing via pygt3x."""

    def test_get_file_metadata(self, gt3x_loader: GT3XDataSourceLoader, mock_gt3x_file) -> None:
        """Test get_file_metadata extracts metadata without loading full data."""
        metadata = gt3x_loader.get_file_metadata(mock_gt3x_file)

        assert "file_size" in metadata
        assert "serial_number" in metadata
        assert "device_type" in metadata
        assert "sample_rate" in metadata
        assert "start_time" in metadata
        assert "epoch_length_seconds" in metadata

        assert metadata["epoch_length_seconds"] == 60


class TestGT3XLoaderDataFrameCreation:
    """Tests for DataFrame creation from raw samples."""

    def test_create_raw_dataframe(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test creating raw DataFrame from samples."""
        # Create 90 samples (3 seconds at 30 Hz)
        n_samples = 90
        raw_data = np.random.randn(n_samples, 3) * 0.5

        # Create timestamps as numpy array (datetime64 format)
        start_time = pd.Timestamp("2024-01-15 08:00:00")
        timestamps = pd.date_range(start=start_time, periods=n_samples, freq=pd.Timedelta(seconds=1 / 30)).to_numpy()
        sample_rate = 30.0

        df = gt3x_loader._create_raw_dataframe(raw_data, timestamps, sample_rate)

        assert len(df) == n_samples
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.AXIS_X in df.columns
        assert DatabaseColumn.AXIS_Y in df.columns
        assert DatabaseColumn.AXIS_Z in df.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in df.columns

        # Check that timestamps are correctly spaced (1/30 second intervals)
        time_diff = (df[DatabaseColumn.TIMESTAMP].iloc[1] - df[DatabaseColumn.TIMESTAMP].iloc[0]).total_seconds()
        assert time_diff == pytest.approx(1 / 30, abs=0.001)

    def test_create_epoch_dataframe(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test creating epoch-aggregated DataFrame."""
        # Create 1800 samples (60 seconds at 30 Hz)
        n_samples = 1800
        raw_data = np.ones((n_samples, 3))  # All 1g for simplicity

        # Create timestamps as numpy array
        start_time = pd.Timestamp("2024-01-15 08:00:00")
        timestamps = pd.date_range(start=start_time, periods=n_samples, freq=pd.Timedelta(seconds=1 / 30)).to_numpy()
        sample_rate = 30.0

        df = gt3x_loader._create_epoch_dataframe(raw_data, timestamps, sample_rate)

        # Should have 1 epoch (60 seconds)
        assert len(df) == 1
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.VECTOR_MAGNITUDE in df.columns

        # First timestamp should be close to start_time
        expected_time = pd.Timestamp("2024-01-15 08:00:00")
        actual_time = df[DatabaseColumn.TIMESTAMP].iloc[0]
        assert abs((actual_time - expected_time).total_seconds()) < 1

    def test_create_epoch_dataframe_multiple_epochs(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test creating DataFrame with multiple epochs."""
        # Create 3600 samples (120 seconds = 2 epochs at 30 Hz)
        n_samples = 3600
        raw_data = np.random.randn(n_samples, 3) * 0.5

        start_time = pd.Timestamp("2024-01-15 08:00:00")
        timestamps = pd.date_range(start=start_time, periods=n_samples, freq=pd.Timedelta(seconds=1 / 30)).to_numpy()
        sample_rate = 30.0

        df = gt3x_loader._create_epoch_dataframe(raw_data, timestamps, sample_rate)

        # Should have 2 complete epochs
        assert len(df) == 2

        # Check epoch spacing (60 seconds)
        time_diff = (df[DatabaseColumn.TIMESTAMP].iloc[1] - df[DatabaseColumn.TIMESTAMP].iloc[0]).total_seconds()
        assert time_diff == pytest.approx(60, abs=1)

    def test_create_epoch_dataframe_insufficient_data(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test epoch DataFrame with insufficient data for one epoch."""
        # Create only 100 samples (not enough for one 60-second epoch at 30 Hz)
        n_samples = 100
        raw_data = np.random.randn(n_samples, 3)

        start_time = pd.Timestamp("2024-01-15 08:00:00")
        timestamps = pd.date_range(start=start_time, periods=n_samples, freq=pd.Timedelta(seconds=1 / 30)).to_numpy()
        sample_rate = 30.0

        df = gt3x_loader._create_epoch_dataframe(raw_data, timestamps, sample_rate)

        # Should return empty DataFrame
        assert len(df) == 0


class TestGT3XLoaderDataValidation:
    """Tests for data validation."""

    def test_validate_data_valid(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test validation of valid GT3X data."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.date_range("2024-01-15 08:00:00", periods=3, freq="1min"),
                DatabaseColumn.AXIS_X: [80.0, 85.0, 82.0],
                DatabaseColumn.AXIS_Y: [100.0, 120.0, 110.0],
                DatabaseColumn.AXIS_Z: [90.0, 95.0, 92.0],
                DatabaseColumn.VECTOR_MAGNITUDE: [150.0, 160.0, 155.0],
            }
        )

        is_valid, errors = gt3x_loader.validate_data(df)
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_data_missing_columns(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test validation fails when required columns are missing."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: pd.date_range("2024-01-15 08:00:00", periods=3, freq="1min"),
                DatabaseColumn.AXIS_Y: [100.0, 120.0, 110.0],
            }
        )

        is_valid, errors = gt3x_loader.validate_data(df)
        assert is_valid is False
        assert any("axis_x" in err.lower() for err in errors)
        assert any("axis_z" in err.lower() for err in errors)

    def test_validate_data_empty(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test validation fails for empty DataFrame."""
        df = pd.DataFrame(columns=[DatabaseColumn.TIMESTAMP, DatabaseColumn.AXIS_X, DatabaseColumn.AXIS_Y, DatabaseColumn.AXIS_Z])

        is_valid, errors = gt3x_loader.validate_data(df)
        assert is_valid is False
        assert any("empty" in err.lower() for err in errors)

    def test_validate_data_wrong_types(self, gt3x_loader: GT3XDataSourceLoader) -> None:
        """Test validation fails with wrong data types."""
        df = pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: ["2024-01-15 08:00:00", "2024-01-15 08:01:00"],  # String instead of datetime
                DatabaseColumn.AXIS_X: [80.0, 85.0],
                DatabaseColumn.AXIS_Y: [100.0, 120.0],
                DatabaseColumn.AXIS_Z: [90.0, 95.0],
            }
        )

        is_valid, errors = gt3x_loader.validate_data(df)
        assert is_valid is False
        assert any("datetime" in err.lower() for err in errors)


class TestGT3XLoaderIntegration:
    """Integration tests for full GT3X loading workflow."""

    def test_full_load_workflow(self, gt3x_loader: GT3XDataSourceLoader, mock_gt3x_file_large_epoch) -> None:
        """Test complete loading workflow from file to validated DataFrame."""
        result = gt3x_loader.load_file(mock_gt3x_file_large_epoch)

        # Check result structure
        assert "activity_data" in result
        assert "metadata" in result
        assert "column_mapping" in result

        # Check DataFrame
        df = result["activity_data"]
        assert len(df) > 0
        assert DatabaseColumn.TIMESTAMP in df.columns
        assert DatabaseColumn.AXIS_Y in df.columns

        # Check metadata
        metadata = result["metadata"]
        assert metadata["serial_number"] == "TEST456"
        assert metadata["sample_rate"] == 30
        assert metadata["total_epochs"] >= 3  # pygt3x may add samples

        # Check column mapping
        mapping = result["column_mapping"]
        assert isinstance(mapping, ColumnMapping)

    def test_load_and_validate_metadata(self, gt3x_loader: GT3XDataSourceLoader, mock_gt3x_file_large_epoch) -> None:
        """Test that metadata is correctly populated during load."""
        result = gt3x_loader.load_file(mock_gt3x_file_large_epoch)
        metadata = result["metadata"]

        assert "file_size" in metadata
        assert "serial_number" in metadata
        assert "sample_rate" in metadata
        assert "start_time" in metadata
        assert "end_time" in metadata
        assert "epoch_length_seconds" in metadata

        # device_type may be None if not provided in info.txt
        assert metadata["epoch_length_seconds"] == 60

    def test_raw_vs_epoch_mode_comparison(self, mock_gt3x_file_large_epoch) -> None:
        """Test that raw and epoch modes produce different outputs."""
        loader_raw = GT3XDataSourceLoader(return_raw=True)
        loader_epoch = GT3XDataSourceLoader(return_raw=False, epoch_length_seconds=60)

        result_raw = loader_raw.load_file(mock_gt3x_file_large_epoch)
        result_epoch = loader_epoch.load_file(mock_gt3x_file_large_epoch)

        df_raw = result_raw["activity_data"]
        df_epoch = result_epoch["activity_data"]

        # Raw should have more rows (individual samples)
        assert len(df_raw) > len(df_epoch)

        # Epoch should have fewer rows (aggregated)
        # pygt3x may add samples, so just verify we got epochs
        assert len(df_epoch) >= 3

        # Both should have same columns
        assert set(df_raw.columns) == set(df_epoch.columns)
