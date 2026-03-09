"""
GT3X data source loader implementation.

This module provides loading capabilities for ActiGraph GT3X binary format files.

GT3X File Format:
    - ZIP archive containing: activity.bin, lux.bin, info.txt, log.bin
    - activity.bin: Raw accelerometer data at 30-100Hz
    - info.txt: Device metadata (serial number, sample rate, start time)
    - Uses pygt3x library for parsing GT3X binary format
    - Data returned in g-units (calibrated)

Architecture:
    - Implements DataSourceLoader protocol
    - Handles GT3X binary format via pygt3x library
    - Extracts device metadata and settings
    - Converts binary data to DataFrame
    - Supports both raw (high-frequency) and epoch-aggregated output

Example Usage:
    >>> from sleep_scoring_app.io.sources.gt3x_loader import GT3XDataSourceLoader
    >>>
    >>> # Load as 60-second epochs
    >>> loader = GT3XDataSourceLoader(epoch_length_seconds=60)
    >>> result = loader.load_file("/path/to/data.gt3x")
    >>> activity_df = result["activity_data"]
    >>>
    >>> # Load raw high-frequency data
    >>> loader = GT3XDataSourceLoader(return_raw=True)
    >>> result = loader.load_file("/path/to/data.gt3x")
    >>> raw_df = result["activity_data"]

References:
    - pygt3x library: https://github.com/actigraph/pygt3x
    - ActiGraph GT3X binary format specification
    - ActiGraph device documentation

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd

from sleep_scoring_app.core.constants import DatabaseColumn
from sleep_scoring_app.core.dataclasses import ColumnMapping
from sleep_scoring_app.core.validation import InputValidator

if TYPE_CHECKING:
    from pathlib import Path

    from sleep_scoring_app.core.backends import ComputeBackend

logger = logging.getLogger(__name__)


class GT3XDataSourceLoader:
    """
    GT3X binary file data source loader.

    Loads activity data from ActiGraph GT3X binary files with full metadata extraction
    and device information. Implements DataSourceLoader protocol for DI compatibility.

    GT3X files are ZIP archives containing binary accelerometer data and device metadata.
    This loader uses the pygt3x library to parse the binary format and converts it to
    standardized DataFrames.

    Autocalibration:
        When autocalibrate=True (default), applies GGIR-compatible sphere calibration
        to correct for sensor drift. This finds stationary periods and optimizes
        scale/offset to ensure the accelerometer vector magnitude equals 1g at rest.

    Imputation:
        When impute_gaps=True (default), applies GGIR-compatible time gap imputation
        using row replication (np.repeat). This is CRITICAL for matching GGIR output.
        See: packages/accelerometer-nonwear and external/ggir/docs/nonwear-replication/

    Attributes:
        epoch_length_seconds: Length of epoch window in seconds (default: 60)
        return_raw: If True, return raw samples; if False, aggregate to epochs
        autocalibrate: If True, apply GGIR-compatible autocalibration (default: True)
        impute_gaps: If True, apply GGIR-compatible time gap imputation (default: True)

    """

    # GT3X format constants
    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".gt3x"})
    MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB limit

    def __init__(
        self,
        backend: ComputeBackend | None = None,
        epoch_length_seconds: int = 60,
        return_raw: bool = False,
        autocalibrate: bool = True,
        impute_gaps: bool = True,
    ) -> None:
        """
        Initialize GT3X loader.

        Args:
            backend: Compute backend to use (auto-selects if None)
            epoch_length_seconds: Epoch length in seconds for aggregation (default: 60)
            return_raw: If True, return raw samples without aggregation (default: False)
            autocalibrate: If True, apply GGIR-compatible autocalibration (default: True)
            impute_gaps: If True, apply GGIR-compatible time gap imputation (default: True)

        """
        # Auto-select backend if not provided
        if backend is None:
            from sleep_scoring_app.core.backends import BackendFactory

            backend = BackendFactory.create()

        self.backend = backend
        self.epoch_length_seconds = epoch_length_seconds
        self.return_raw = return_raw
        self.autocalibrate = autocalibrate
        self.impute_gaps = impute_gaps

    @property
    def name(self) -> str:
        """
        Loader name for display.

        Returns:
            Human-readable loader name

        """
        return "GT3X File Loader"

    @property
    def identifier(self) -> str:
        """
        Unique loader identifier.

        Returns:
            Snake_case identifier for configuration storage

        """
        return "gt3x"

    @property
    def supported_extensions(self) -> frozenset[str]:
        """
        Supported file extensions.

        Returns:
            Set of file extensions this loader can handle

        """
        return self.SUPPORTED_EXTENSIONS

    def load_file(
        self,
        file_path: str | Path,
        skip_rows: int | None = None,
        custom_columns: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Load activity data from GT3X file.

        Extracts accelerometer data from GT3X binary format using pygt3x library
        and converts to DataFrame. Can return either raw high-frequency samples
        or epoch-aggregated data.

        Args:
            file_path: Path to the GT3X file
            skip_rows: Unused for GT3X (kept for protocol compatibility)
            custom_columns: Unused for GT3X (format is standardized)

        Returns:
            Dictionary containing:
                - activity_data: pd.DataFrame with standardized columns
                - metadata: dict with file and device metadata
                - column_mapping: ColumnMapping object (GT3X has fixed mapping)

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file format is invalid or corrupted
            IOError: If file cannot be read
            ImportError: If pygt3x library is not installed

        """
        file_path = InputValidator.validate_file_path(
            file_path,
            must_exist=True,
            allowed_extensions=self.supported_extensions,
        )

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            msg = f"File too large: {file_size / 1024 / 1024:.1f}MB > {self.MAX_FILE_SIZE / 1024 / 1024:.1f}MB"
            raise ValueError(msg)

        # Parse GT3X file using backend
        try:
            raw_data = self.backend.parse_gt3x(str(file_path), include_sensors=False)

            # Extract data
            acc_data = np.column_stack([raw_data.x, raw_data.y, raw_data.z])
            timestamps = raw_data.timestamps
            sample_rate = raw_data.sample_rate

            # Extract metadata
            _metadata = raw_data.metadata or {}
            serial_number = _metadata.get("serial_number", "UNKNOWN")
            start_time = _metadata.get("start_time")
            timezone_offset = _metadata.get("timezone_offset")

        except Exception as e:
            msg = f"Error reading GT3X file with backend {self.backend.name}: {e}"
            raise ValueError(msg) from e

        # Apply GGIR-compatible autocalibration if enabled
        calibration_result = None
        if self.autocalibrate:
            try:
                logger.info("Applying GGIR-compatible autocalibration via backend...")
                calibration_result = self.backend.calibrate(acc_data[:, 0], acc_data[:, 1], acc_data[:, 2], sample_rate)

                if calibration_result.success:
                    x_cal, y_cal, z_cal = self.backend.apply_calibration(
                        acc_data[:, 0],
                        acc_data[:, 1],
                        acc_data[:, 2],
                        calibration_result.scale,
                        calibration_result.offset,
                    )
                    acc_data = np.column_stack([x_cal, y_cal, z_cal])
                    logger.info(
                        f"Autocalibration successful: error reduced from "
                        f"{calibration_result.error_before:.5f} to {calibration_result.error_after:.5f} "
                        f"using {calibration_result.n_points_used} stationary points"
                    )
                else:
                    logger.warning(f"Autocalibration skipped: {calibration_result.message}")

            except Exception as e:
                logger.warning(f"Autocalibration failed, using uncalibrated data: {e}")

        # Apply GGIR-compatible time gap imputation if enabled
        # CRITICAL: This uses row replication (np.repeat) to match GGIR g.imputeTimegaps
        # See: packages/accelerometer-nonwear and external/ggir/docs/nonwear-replication/
        imputation_result = None
        if self.impute_gaps:
            try:
                logger.info("Applying GGIR-compatible time gap imputation via backend...")
                imputation_result = self.backend.impute_gaps(
                    acc_data[:, 0],
                    acc_data[:, 1],
                    acc_data[:, 2],
                    timestamps,
                    sample_rate,
                )

                if imputation_result.n_gaps > 0:
                    acc_data = np.column_stack(
                        [
                            imputation_result.x,
                            imputation_result.y,
                            imputation_result.z,
                        ]
                    )
                    timestamps = imputation_result.timestamps
                    logger.info(
                        f"Imputation complete: filled {imputation_result.n_gaps} gaps, "
                        f"added {imputation_result.n_samples_added} samples "
                        f"({imputation_result.total_gap_sec:.1f}s total gap duration)"
                    )
                else:
                    logger.info("No time gaps detected, imputation not needed")

            except Exception as e:
                logger.warning(f"Time gap imputation failed: {e}")

        # Create DataFrame based on mode
        if self.return_raw:
            result_df = self._create_raw_dataframe(acc_data, timestamps, sample_rate)
        else:
            result_df = self._create_epoch_dataframe(acc_data, timestamps, sample_rate)

        if result_df.empty:
            msg = f"No data in GT3X file: {file_path}"
            raise ValueError(msg)

        # Validate data
        is_valid, errors = self.validate_data(result_df)
        if not is_valid:
            msg = f"Data validation failed: {', '.join(errors)}"
            raise ValueError(msg)

        # Get column mapping (GT3X has standardized format)
        column_mapping = self.detect_columns(result_df)

        # Build metadata dictionary
        metadata = {
            "loader": "gt3x",
            "file_size": file_size,
            "serial_number": serial_number,
            "device_type": start_time.get("device_type") if isinstance(start_time, dict) else None,
            "firmware": None,  # Available from backend metadata
            "sample_rate": sample_rate,
            "start_time": result_df[DatabaseColumn.TIMESTAMP].iloc[0],
            "end_time": result_df[DatabaseColumn.TIMESTAMP].iloc[-1],
            "timezone_offset": timezone_offset,
            "total_epochs": len(result_df) if not self.return_raw else None,
            "total_samples": len(acc_data),
            "epoch_length_seconds": None if self.return_raw else self.epoch_length_seconds,
            "autocalibrated": calibration_result.success if calibration_result else False,
            "calibration_error_before": calibration_result.error_before if calibration_result else None,
            "calibration_error_after": calibration_result.error_after if calibration_result else None,
            "imputation_applied": imputation_result is not None and imputation_result.n_gaps > 0,
            "imputation_n_gaps": imputation_result.n_gaps if imputation_result else 0,
            "imputation_samples_added": imputation_result.n_samples_added if imputation_result else 0,
            "imputation_total_gap_sec": imputation_result.total_gap_sec if imputation_result else 0.0,
        }

        return {
            "activity_data": result_df,
            "metadata": metadata,
            "column_mapping": column_mapping,
        }

    def _create_epoch_dataframe(self, raw_data: np.ndarray, timestamps: np.ndarray, sample_rate: float) -> pd.DataFrame:
        """
        Create epoch-aggregated DataFrame from raw samples.

        Aggregates high-frequency samples into epoch windows by summing absolute values.
        This matches the ActiGraph epoch aggregation method.

        Args:
            raw_data: NumPy array of shape (n_samples, 3) with X, Y, Z in g
            timestamps: NumPy array of timestamps (datetime64 or float)
            sample_rate: Sample rate in Hz

        Returns:
            DataFrame with columns: TIMESTAMP, AXIS_X, AXIS_Y, AXIS_Z, VECTOR_MAGNITUDE

        """
        # Calculate samples per epoch
        samples_per_epoch = int(sample_rate * self.epoch_length_seconds)

        # Calculate number of complete epochs
        n_samples = len(raw_data)
        n_epochs = n_samples // samples_per_epoch

        if n_epochs == 0:
            logger.warning("Not enough samples for even one epoch, returning empty DataFrame")
            return pd.DataFrame(
                columns=[
                    str(c)
                    for c in [
                        DatabaseColumn.TIMESTAMP,
                        DatabaseColumn.AXIS_X,
                        DatabaseColumn.AXIS_Y,
                        DatabaseColumn.AXIS_Z,
                        DatabaseColumn.VECTOR_MAGNITUDE,
                    ]
                ]
            )

        # Truncate to complete epochs
        truncated_samples = n_samples - (n_samples % samples_per_epoch)
        epoch_data = raw_data[:truncated_samples]
        epoch_timestamps = timestamps[:truncated_samples]

        # Reshape into epochs
        epoch_data = epoch_data.reshape(n_epochs, samples_per_epoch, 3)
        epoch_timestamps = epoch_timestamps.reshape(n_epochs, samples_per_epoch)

        # Sum absolute values for each axis
        # ActiGraph epochs represent total activity (sum of absolute accelerations)
        epoch_x = np.sum(np.abs(epoch_data[:, :, 0]), axis=1)
        epoch_y = np.sum(np.abs(epoch_data[:, :, 1]), axis=1)
        epoch_z = np.sum(np.abs(epoch_data[:, :, 2]), axis=1)

        # Calculate vector magnitude for each epoch
        # VM = sqrt(x^2 + y^2 + z^2) for each sample, then sum over epoch
        vm_per_sample = np.sqrt(np.sum(epoch_data**2, axis=2))
        epoch_vm = np.sum(vm_per_sample, axis=1)

        # Use first timestamp of each epoch
        epoch_start_timestamps = epoch_timestamps[:, 0]

        # Convert timestamps to datetime if needed
        if np.issubdtype(epoch_start_timestamps.dtype, np.datetime64):
            epoch_datetimes = pd.to_datetime(epoch_start_timestamps)
        else:
            # Assume Unix timestamps (float seconds)
            epoch_datetimes = pd.to_datetime(epoch_start_timestamps, unit="s")

        # Create DataFrame with enum keys (pandas handles StrEnum automatically)
        return pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: epoch_datetimes,
                DatabaseColumn.AXIS_X: epoch_x,
                DatabaseColumn.AXIS_Y: epoch_y,
                DatabaseColumn.AXIS_Z: epoch_z,
                DatabaseColumn.VECTOR_MAGNITUDE: epoch_vm,
            },
        )

    def _create_raw_dataframe(self, raw_data: np.ndarray, timestamps: np.ndarray, sample_rate: float) -> pd.DataFrame:
        """
        Create DataFrame with raw high-frequency samples.

        Args:
            raw_data: NumPy array of shape (n_samples, 3) with X, Y, Z in g
            timestamps: NumPy array of timestamps (datetime64 or float)
            sample_rate: Sample rate in Hz (unused but kept for signature consistency)

        Returns:
            DataFrame with columns: TIMESTAMP, AXIS_X, AXIS_Y, AXIS_Z, VECTOR_MAGNITUDE

        """
        # Convert timestamps to datetime if needed
        if np.issubdtype(timestamps.dtype, np.datetime64):
            datetimes = pd.to_datetime(timestamps)
        else:
            # Assume Unix timestamps (float seconds)
            datetimes = pd.to_datetime(timestamps, unit="s")

        # Calculate vector magnitude for each sample
        vm = np.sqrt(np.sum(raw_data**2, axis=1))

        # Create DataFrame with enum keys (pandas handles StrEnum automatically)
        return pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: datetimes,
                DatabaseColumn.AXIS_X: raw_data[:, 0],
                DatabaseColumn.AXIS_Y: raw_data[:, 1],
                DatabaseColumn.AXIS_Z: raw_data[:, 2],
                DatabaseColumn.VECTOR_MAGNITUDE: vm,
            },
        )

    def detect_columns(self, df: pd.DataFrame) -> ColumnMapping:
        """
        Detect and map column names.

        GT3X format produces standardized columns, so this always returns
        a fixed mapping.

        Args:
            df: DataFrame to analyze (unused - GT3X format is standardized)

        Returns:
            ColumnMapping with GT3X standard columns

        """
        return ColumnMapping(
            datetime_column=DatabaseColumn.TIMESTAMP,
            activity_column=DatabaseColumn.AXIS_Y,  # Y-axis is primary for sleep scoring
            axis_x_column=DatabaseColumn.AXIS_X,
            axis_z_column=DatabaseColumn.AXIS_Z,
            vector_magnitude_column=DatabaseColumn.VECTOR_MAGNITUDE,
        )

    def validate_data(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        """
        Validate loaded data structure and content.

        Args:
            df: DataFrame to validate

        Returns:
            Tuple of (is_valid, error_messages)

        """
        errors = []

        # Check required columns exist
        required_columns = [DatabaseColumn.TIMESTAMP, DatabaseColumn.AXIS_X, DatabaseColumn.AXIS_Y, DatabaseColumn.AXIS_Z]
        for col in required_columns:
            if col not in df.columns:
                errors.append(f"Missing required column: {col}")

        # Check for empty data
        if len(df) == 0:
            errors.append("DataFrame is empty")
            return False, errors

        # Validate data types
        if DatabaseColumn.TIMESTAMP in df.columns:
            try:
                if not pd.api.types.is_datetime64_any_dtype(df[DatabaseColumn.TIMESTAMP]):
                    errors.append(f"{DatabaseColumn.TIMESTAMP} must be datetime type")
            except Exception as e:
                errors.append(f"Error checking {DatabaseColumn.TIMESTAMP} type: {e}")

        # Validate numeric columns
        numeric_columns = [DatabaseColumn.AXIS_X, DatabaseColumn.AXIS_Y, DatabaseColumn.AXIS_Z, DatabaseColumn.VECTOR_MAGNITUDE]
        for col in numeric_columns:
            if col in df.columns:
                try:
                    if not pd.api.types.is_numeric_dtype(df[col]):
                        errors.append(f"{col} must be numeric type")
                except Exception as e:
                    errors.append(f"Error checking {col} type: {e}")

        # Check for reasonable acceleration values (should be in range -20g to +20g for raw)
        # For epoch data, values can be much higher due to summing
        for col in [DatabaseColumn.AXIS_X, DatabaseColumn.AXIS_Y, DatabaseColumn.AXIS_Z]:
            if col in df.columns:
                max_val = df[col].abs().max()
                if self.return_raw and max_val > 20:
                    logger.warning(f"{col} has suspiciously high raw values (max: {max_val:.1f}g)")
                elif not self.return_raw and max_val > 10000:
                    logger.warning(f"{col} has suspiciously high epoch values (max: {max_val:.1f})")

        return len(errors) == 0, errors

    def get_file_metadata(self, file_path: str | Path) -> dict[str, Any]:
        """
        Extract metadata from GT3X file without loading full data.

        Args:
            file_path: Path to the GT3X file

        Returns:
            Dictionary with metadata:
                - file_size: File size in bytes
                - device_type: Device model
                - serial_number: Device serial number
                - sample_rate: Sampling rate in Hz
                - firmware: Firmware version
                - start_time: Recording start datetime
                - timezone_offset: Timezone offset string
                - epoch_length_seconds: Configured epoch length (if using epochs)

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file is invalid or corrupted
            ImportError: If pygt3x library is not installed

        """
        file_path = InputValidator.validate_file_path(
            file_path,
            must_exist=True,
            allowed_extensions=self.supported_extensions,
        )

        file_size = file_path.stat().st_size

        # Extract metadata using backend
        try:
            backend_metadata = self.backend.parse_gt3x_metadata(str(file_path))

            metadata = {
                "loader": "gt3x",
                "file_size": file_size,
                "serial_number": backend_metadata.get("serial_number", "UNKNOWN"),
                "sample_rate": backend_metadata.get("sample_rate"),
                "start_time": backend_metadata.get("start_time"),
                "timezone_offset": backend_metadata.get("timezone_offset"),
                "device_type": backend_metadata.get("device_type"),
                "firmware": backend_metadata.get("firmware"),
                "epoch_length_seconds": None if self.return_raw else self.epoch_length_seconds,
            }
        except Exception as e:
            msg = f"Error reading GT3X metadata with backend {self.backend.name}: {e}"
            raise ValueError(msg) from e

        return metadata
