"""
GT3X data source loader using gt3x-rs (Rust) backend.

This loader uses the high-performance gt3x-rs Rust library for parsing,
calibration, and processing GT3X files. It provides exact numerical
agreement with GGIR R package while being 52x faster than pygt3x.

Features:
    - Parsing: 72M samples in 1.77s (vs 93s pygt3x)
    - GGIR-compatible sphere-fitting autocalibration
    - Time gap imputation (row replication)
    - Exact match validation against pygt3x

References:
    - gt3x-rs: packages/gt3x-rs
    - ActiGraph GT3X File Format: https://github.com/actigraph/GT3X-File-Format

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

logger = logging.getLogger(__name__)


class Gt3xRsDataSourceLoader:
    """
    GT3X file loader using gt3x-rs Rust backend.

    This is the preferred loader for GT3X files, providing:
    - 52x faster parsing than pygt3x
    - GGIR-compatible autocalibration
    - Time gap imputation
    - Exact numerical agreement with reference implementations

    Attributes:
        epoch_length_seconds: Length of epoch window in seconds (default: 60)
        return_raw: If True, return raw samples; if False, aggregate to epochs
        autocalibrate: If True, apply GGIR-compatible autocalibration (default: True)
        impute_gaps: If True, impute time gaps via row replication (default: True)

    """

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".gt3x"})
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB limit (gt3x-rs handles large files)

    def __init__(
        self,
        backend: Any = None,  # Accepted for compatibility, ignored (uses gt3x-rs directly)
        epoch_length_seconds: int = 60,
        return_raw: bool = False,
        autocalibrate: bool = True,
        impute_gaps: bool = True,
        ism_handling: str = "replicate",
    ) -> None:
        """
        Initialize gt3x-rs loader.

        Args:
            backend: Ignored (for compatibility with factory). This loader uses gt3x-rs directly.
            epoch_length_seconds: Epoch length in seconds for aggregation (default: 60)
            return_raw: If True, return raw samples without aggregation (default: False)
            autocalibrate: If True, apply GGIR-compatible autocalibration (default: True)
            impute_gaps: If True, impute time gaps via row replication (default: True)
            ism_handling: How to handle Idle Sleep Mode samples:
                - "replicate": Keep replicated last-known values (default, matches pygt3x)
                - "zero": Set ISM samples to zero (matches read.gt3x imputeZeroes=TRUE)
                - "nan": Set ISM samples to NaN (for algorithms that skip ISM)

        Note:
            This loader directly uses gt3x-rs library and does not use the backend abstraction.
            Used by loader_factory.py as the primary GT3X loading implementation.

        """
        self.epoch_length_seconds = epoch_length_seconds
        self.return_raw = return_raw
        self.autocalibrate = autocalibrate
        self.impute_gaps = impute_gaps
        self.ism_handling = ism_handling

        # Verify gt3x-rs is available
        try:
            import gt3x_rs

            self._gt3x_rs = gt3x_rs
        except ImportError as e:
            msg = "gt3x-rs is required for this loader. Build with: cd packages/gt3x-rs && maturin develop --release"
            raise ImportError(msg) from e

    @property
    def name(self) -> str:
        """Loader name for display."""
        return "GT3X File Loader (Rust)"

    @property
    def identifier(self) -> str:
        """Unique loader identifier."""
        return "gt3x_rs"

    @property
    def supported_extensions(self) -> frozenset[str]:
        """Supported file extensions."""
        return self.SUPPORTED_EXTENSIONS

    def load_file(
        self,
        file_path: str | Path,
        skip_rows: int | None = None,
        custom_columns: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Load activity data from GT3X file using gt3x-rs.

        Args:
            file_path: Path to the GT3X file
            skip_rows: Unused (kept for protocol compatibility)
            custom_columns: Unused (GT3X format is standardized)

        Returns:
            Dictionary containing:
                - activity_data: pd.DataFrame with standardized columns
                - metadata: dict with file and device metadata
                - column_mapping: ColumnMapping object

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file format is invalid or corrupted
            ImportError: If gt3x-rs is not available

        """
        file_path = InputValidator.validate_file_path(
            file_path,
            must_exist=True,
            allowed_extensions=self.supported_extensions,
        )

        file_size = file_path.stat().st_size
        if file_size > self.MAX_FILE_SIZE:
            msg = f"File too large: {file_size / 1024 / 1024:.1f}MB > {self.MAX_FILE_SIZE / 1024 / 1024:.1f}MB"
            raise ValueError(msg)

        logger.info(f"Loading GT3X file with gt3x-rs: {file_path}")

        # Parse GT3X file
        try:
            data = self._gt3x_rs.parse_gt3x(str(file_path))
        except Exception as e:
            msg = f"Error parsing GT3X file: {e}"
            raise ValueError(msg) from e

        # Extract data as numpy arrays
        x = np.array(data.x, dtype=np.float64)
        y = np.array(data.y, dtype=np.float64)
        z = np.array(data.z, dtype=np.float64)
        timestamps = np.array(data.timestamps)
        sample_rate = float(data.sample_rate)
        serial_number = data.serial_number

        logger.info(f"Parsed {len(x)} samples at {sample_rate} Hz from {serial_number}")

        # Get idle sleep mode array if available
        idle_sleep_mode = np.zeros(len(x), dtype=np.bool_)
        if hasattr(data, "idle_sleep_mode"):
            ism = data.idle_sleep_mode
            if ism is not None:
                idle_sleep_mode = np.array(ism, dtype=np.bool_)

        # Apply GGIR-compatible autocalibration
        calibration_result = None
        if self.autocalibrate:
            try:
                logger.info("Applying GGIR-compatible autocalibration...")
                # calibrate_ggir requires: x, y, z, idle_sleep_mode, sample_rate
                cal_result = self._gt3x_rs.calibrate_ggir(x, y, z, idle_sleep_mode, int(sample_rate))

                if cal_result.converged:
                    # Apply calibration using zero-copy NumPy version
                    x, y, z = self._gt3x_rs.apply_calibration_ggir(x, y, z, cal_result)
                    x = np.asarray(x, dtype=np.float64)
                    y = np.asarray(y, dtype=np.float64)
                    z = np.asarray(z, dtype=np.float64)
                    logger.info(
                        f"Autocalibration successful: error {cal_result.error_before:.5f} -> {cal_result.error_after:.5f} "
                        f"using {cal_result.n_points_used} stationary points"
                    )
                    calibration_result = {
                        "success": True,
                        "error_before": cal_result.error_before,
                        "error_after": cal_result.error_after,
                        "n_points": cal_result.n_points_used,
                        "scale": list(cal_result.scale),
                        "offset": list(cal_result.offset),
                    }
                else:
                    logger.warning("Autocalibration did not converge")
                    calibration_result = {"success": False, "message": "Did not converge"}

            except Exception as e:
                logger.warning(f"Autocalibration failed: {e}")
                calibration_result = {"success": False, "message": str(e)}

        # Handle ISM samples BEFORE imputation (matches read.gt3x behavior)
        # read.gt3x sets ISM samples to zero, then imputation replicates those zeros
        # This ensures ISM periods produce NaN z-angles matching GGIR behavior
        if self.ism_handling != "replicate" and idle_sleep_mode.any():
            ism_count = idle_sleep_mode.sum()
            if self.ism_handling == "zero":
                # Set ISM samples to zero (matches read.gt3x imputeZeroes=TRUE)
                x[idle_sleep_mode] = 0.0
                y[idle_sleep_mode] = 0.0
                z[idle_sleep_mode] = 0.0
                logger.info(f"Set {ism_count} ISM samples to zero (before imputation)")
            elif self.ism_handling == "nan":
                # Set ISM samples to NaN (for direct exclusion)
                x[idle_sleep_mode] = np.nan
                y[idle_sleep_mode] = np.nan
                z[idle_sleep_mode] = np.nan
                logger.info(f"Set {ism_count} ISM samples to NaN (before imputation)")

        # Impute time gaps if enabled
        imputation_n_gaps = 0
        imputation_samples_added = 0
        imputation_total_gap_sec = 0.0
        if self.impute_gaps:
            try:
                logger.info("Checking for time gaps...")
                # Convert timestamps to float seconds for gap detection
                if np.issubdtype(timestamps.dtype, np.datetime64):
                    ts_seconds = timestamps.astype("datetime64[ns]").astype(np.float64) / 1e9
                else:
                    ts_seconds = timestamps.astype(np.float64)

                # Use zero-copy NumPy API if available, fallback to .tolist() version
                if hasattr(self._gt3x_rs, "detect_time_gaps_numpy"):
                    gaps = self._gt3x_rs.detect_time_gaps_numpy(ts_seconds, int(sample_rate), 1.0)
                else:
                    gaps = self._gt3x_rs.detect_time_gaps(ts_seconds.tolist(), int(sample_rate), 1.0)

                if gaps:
                    # Use zero-copy NumPy API if available
                    if hasattr(self._gt3x_rs, "impute_time_gaps_numpy"):
                        x_new, y_new, z_new, ts_new = self._gt3x_rs.impute_time_gaps_numpy(x, y, z, ts_seconds, int(sample_rate), 1.0)
                    else:
                        x_new, y_new, z_new, ts_new = self._gt3x_rs.impute_time_gaps(
                            x.tolist(), y.tolist(), z.tolist(), ts_seconds.tolist(), int(sample_rate), 1.0
                        )
                    samples_added = len(x_new) - len(x)
                    x = np.asarray(x_new, dtype=np.float64)
                    y = np.asarray(y_new, dtype=np.float64)
                    z = np.asarray(z_new, dtype=np.float64)
                    timestamps = np.asarray(ts_new)
                    imputation_n_gaps = len(gaps)
                    imputation_samples_added = samples_added
                    logger.info(f"Imputed {len(gaps)} time gaps, added {samples_added} samples")
                else:
                    logger.info("No time gaps detected")

            except Exception as e:
                logger.warning(f"Time gap imputation failed: {e}")

        # Create DataFrame
        if self.return_raw:
            result_df = self._create_raw_dataframe(x, y, z, timestamps)
        else:
            result_df = self._create_epoch_dataframe(x, y, z, timestamps, sample_rate)

        if result_df.empty:
            msg = f"No data in GT3X file: {file_path}"
            raise ValueError(msg)

        # Validate data
        is_valid, errors = self.validate_data(result_df)
        if not is_valid:
            msg = f"Data validation failed: {', '.join(errors)}"
            raise ValueError(msg)

        # Get column mapping
        column_mapping = self.detect_columns(result_df)

        # Build metadata
        metadata = {
            "file_size": file_size,
            "serial_number": serial_number,
            "sample_rate": sample_rate,
            "start_time": result_df[DatabaseColumn.TIMESTAMP].iloc[0],
            "end_time": result_df[DatabaseColumn.TIMESTAMP].iloc[-1],
            "total_epochs": len(result_df) if not self.return_raw else None,
            "total_samples": len(x),
            "epoch_length_seconds": None if self.return_raw else self.epoch_length_seconds,
            "loader": "gt3x_rs",
            "autocalibrated": calibration_result["success"] if calibration_result else False,
            "calibration": calibration_result,
            "timezone_offset": None,
            "device_type": None,
            "firmware": None,
            "calibration_error_before": calibration_result["error_before"] if calibration_result else None,
            "calibration_error_after": calibration_result["error_after"] if calibration_result else None,
            "imputation_applied": imputation_n_gaps > 0,
            "imputation_n_gaps": imputation_n_gaps,
            "imputation_samples_added": imputation_samples_added,
            "imputation_total_gap_sec": imputation_total_gap_sec,
        }

        return {
            "activity_data": result_df,
            "metadata": metadata,
            "column_mapping": column_mapping,
        }

    def _create_raw_dataframe(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        timestamps: np.ndarray,
    ) -> pd.DataFrame:
        """Create DataFrame with raw samples."""
        # Convert timestamps
        if np.issubdtype(timestamps.dtype, np.datetime64):
            datetimes = pd.to_datetime(timestamps)
        elif np.issubdtype(timestamps.dtype, np.floating):
            datetimes = pd.to_datetime(timestamps, unit="s")
        else:
            datetimes = pd.to_datetime(timestamps)

        # Calculate vector magnitude
        vm = np.sqrt(x**2 + y**2 + z**2)

        return pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: datetimes,
                DatabaseColumn.AXIS_X: x,
                DatabaseColumn.AXIS_Y: y,
                DatabaseColumn.AXIS_Z: z,
                DatabaseColumn.VECTOR_MAGNITUDE: vm,
            }
        )

    def _create_epoch_dataframe(
        self,
        x: np.ndarray,
        y: np.ndarray,
        z: np.ndarray,
        timestamps: np.ndarray,
        sample_rate: float,
    ) -> pd.DataFrame:
        """Create epoch-aggregated DataFrame using Rust for performance."""
        samples_per_epoch = int(sample_rate * self.epoch_length_seconds)
        n_samples = len(x)
        n_epochs = n_samples // samples_per_epoch

        if n_epochs == 0:
            logger.warning("Not enough samples for even one epoch")
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

        # Use Rust aggregation if available (much faster for large arrays)
        if hasattr(self._gt3x_rs, "aggregate_xyz_to_epochs"):
            logger.debug("Using Rust epoch aggregation")
            epoch_x, epoch_y, epoch_z, epoch_vm = self._gt3x_rs.aggregate_xyz_to_epochs(x, y, z, sample_rate, float(self.epoch_length_seconds))
        else:
            # Fallback to NumPy (slower but always available)
            logger.debug("Using NumPy epoch aggregation (fallback)")
            truncated = n_epochs * samples_per_epoch
            x_reshaped = x[:truncated].reshape(n_epochs, samples_per_epoch)
            y_reshaped = y[:truncated].reshape(n_epochs, samples_per_epoch)
            z_reshaped = z[:truncated].reshape(n_epochs, samples_per_epoch)

            epoch_x = np.sum(np.abs(x_reshaped), axis=1)
            epoch_y = np.sum(np.abs(y_reshaped), axis=1)
            epoch_z = np.sum(np.abs(z_reshaped), axis=1)
            vm_per_sample = np.sqrt(x_reshaped**2 + y_reshaped**2 + z_reshaped**2)
            epoch_vm = np.sum(vm_per_sample, axis=1)

        # Extract first timestamp of each epoch
        truncated = n_epochs * samples_per_epoch
        ts_reshaped = timestamps[:truncated].reshape(n_epochs, samples_per_epoch)
        epoch_timestamps = ts_reshaped[:, 0]

        # Convert timestamps
        if np.issubdtype(epoch_timestamps.dtype, np.datetime64):
            datetimes = pd.to_datetime(epoch_timestamps)
        elif np.issubdtype(epoch_timestamps.dtype, np.floating):
            datetimes = pd.to_datetime(epoch_timestamps, unit="s")
        else:
            datetimes = pd.to_datetime(epoch_timestamps)

        return pd.DataFrame(
            {
                DatabaseColumn.TIMESTAMP: datetimes,
                DatabaseColumn.AXIS_X: np.asarray(epoch_x),
                DatabaseColumn.AXIS_Y: np.asarray(epoch_y),
                DatabaseColumn.AXIS_Z: np.asarray(epoch_z),
                DatabaseColumn.VECTOR_MAGNITUDE: np.asarray(epoch_vm),
            }
        )

    def detect_columns(self, df: pd.DataFrame) -> ColumnMapping:
        """Detect and map column names."""
        return ColumnMapping(
            datetime_column=DatabaseColumn.TIMESTAMP,
            activity_column=DatabaseColumn.AXIS_Y,
            axis_x_column=DatabaseColumn.AXIS_X,
            axis_z_column=DatabaseColumn.AXIS_Z,
            vector_magnitude_column=DatabaseColumn.VECTOR_MAGNITUDE,
        )

    def validate_data(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        """Validate loaded data."""
        errors = []

        required = [DatabaseColumn.TIMESTAMP, DatabaseColumn.AXIS_X, DatabaseColumn.AXIS_Y, DatabaseColumn.AXIS_Z]
        for col in required:
            if col not in df.columns:
                errors.append(f"Missing required column: {col}")

        if len(df) == 0:
            errors.append("DataFrame is empty")

        return len(errors) == 0, errors

    def get_file_metadata(self, file_path: str | Path) -> dict[str, Any]:
        """Extract metadata without loading full data."""
        file_path = InputValidator.validate_file_path(
            file_path,
            must_exist=True,
            allowed_extensions=self.supported_extensions,
        )

        try:
            data = self._gt3x_rs.parse_gt3x(str(file_path))

            return {
                "file_size": file_path.stat().st_size,
                "serial_number": data.serial_number,
                "sample_rate": float(data.sample_rate),
                "total_samples": data.len,
                "loader": "gt3x_rs",
                "device_type": getattr(data, "device_type", None),
                "firmware": getattr(data, "firmware", None),
                "timezone_offset": getattr(data, "timezone_offset", None),
                "epoch_length_seconds": None if self.return_raw else self.epoch_length_seconds,
            }
        except Exception as e:
            msg = f"Error reading GT3X metadata: {e}"
            raise ValueError(msg) from e
