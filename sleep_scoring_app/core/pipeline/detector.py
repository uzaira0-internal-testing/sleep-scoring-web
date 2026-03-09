"""
Data source type detection for pipeline routing.

This module automatically detects whether a file contains:
- Raw high-frequency tri-axial accelerometer data
- Pre-aggregated 60-second epoch count data

Detection is based on file format and column structure.

Example Usage:
    >>> from sleep_scoring_app.core.pipeline import DataSourceDetector
    >>>
    >>> detector = DataSourceDetector()
    >>>
    >>> # Detect from file path
    >>> source_type = detector.detect_from_file("data.gt3x")
    >>> print(source_type)  # DataSourceType.GT3X_RAW
    >>>
    >>> # Detect from loaded DataFrame
    >>> import pandas as pd
    >>> df = pd.read_csv("data.csv")
    >>> source_type = detector.detect_from_dataframe(df)

References:
    - CLAUDE.md: Protocol-first design
    - types.py: DataSourceType enum

"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    import pandas as pd

from .exceptions import DataDetectionError
from .types import DataSourceType

logger = logging.getLogger(__name__)


class DataSourceDetector:
    """
    Detector for identifying data source types.

    This class implements automatic detection logic to distinguish between
    raw accelerometer data and pre-epoched count data.

    Detection Rules:
        1. GT3X files -> Always GT3X_RAW (binary format contains raw data)
        2. CSV with AXIS_X, AXIS_Y, AXIS_Z -> CSV_RAW (raw tri-axial data)
        3. CSV with Axis1/Activity + ~60s intervals -> CSV_EPOCH (epoch counts)

    Example:
        >>> detector = DataSourceDetector()
        >>> source_type = detector.detect_from_file("data.gt3x")
        >>> if source_type.is_raw():
        ...     print("Raw data detected")

    """

    # Column patterns for detection
    RAW_CSV_COLUMNS: ClassVar[set[str]] = {"AXIS_X", "AXIS_Y", "AXIS_Z"}
    EPOCH_CSV_COLUMNS: ClassVar[set[str]] = {"Axis1"}  # Can also be "Activity"
    TIMESTAMP_COLUMNS: ClassVar[set[str]] = {
        "timestamp",
        "datetime",
        "Timestamp",
        "Date Time",
        "Date",
        "date",
        "Time",
        "time",
    }

    # Threshold for epoch detection (seconds)
    # If median interval is ~60s (+/-10s tolerance), consider it epoch data
    EPOCH_INTERVAL_MIN = 50
    EPOCH_INTERVAL_MAX = 70

    def detect_from_file(self, file_path: str | Path) -> DataSourceType:
        """
        Detect data source type from file path.

        This method uses file extension and (for CSV) column inspection
        to determine the data source type.

        Args:
            file_path: Path to data file

        Returns:
            DataSourceType enum value

        Raises:
            DataDetectionError: If data type cannot be determined
            FileNotFoundError: If file does not exist

        Example:
            >>> detector = DataSourceDetector()
            >>> source_type = detector.detect_from_file("raw_data.gt3x")
            >>> print(source_type)  # DataSourceType.GT3X_RAW

        """
        file_path = Path(file_path)

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        # Check file extension
        extension = file_path.suffix.lower()

        # GT3X files are always raw data
        if extension == ".gt3x":
            logger.debug(f"Detected GT3X file: {file_path.name}")
            return DataSourceType.GT3X_RAW

        # CSV files require content inspection
        if extension == ".csv":
            return self._detect_csv_type(file_path)

        # Unknown file type
        raise DataDetectionError(
            file_path=str(file_path),
            reason=f"Unsupported file extension: {extension}. Supported: .gt3x, .csv",
        )

    def detect_from_dataframe(self, df: pd.DataFrame) -> DataSourceType:
        """
        Detect data source type from loaded DataFrame.

        This method inspects column names and data intervals to determine
        whether the DataFrame contains raw or epoch data.

        Args:
            df: DataFrame to inspect

        Returns:
            DataSourceType enum value

        Raises:
            DataDetectionError: If data type cannot be determined

        Example:
            >>> import pandas as pd
            >>> df = pd.read_csv("data.csv")
            >>> detector = DataSourceDetector()
            >>> source_type = detector.detect_from_dataframe(df)

        """
        if df is None or len(df) == 0:
            raise DataDetectionError(
                file_path="<dataframe>",
                reason="DataFrame is None or empty",
            )

        # Get column names
        columns = set(df.columns)

        # Check for raw tri-axial data columns
        if self._has_raw_columns(columns):
            logger.debug("Detected raw tri-axial data (AXIS_X, AXIS_Y, AXIS_Z columns)")
            return DataSourceType.CSV_RAW

        # Check for epoch count column
        if self._has_epoch_columns(columns):
            # Verify interval is ~60 seconds
            if self._has_epoch_intervals(df):
                logger.debug("Detected epoch count data (Axis1 column with 60s intervals)")
                return DataSourceType.CSV_EPOCH
            # Has Axis1 but not 60s intervals - might be raw counts
            logger.warning("Found Axis1 column but intervals are not ~60s. This may be raw epoch data at different resolution.")
            return DataSourceType.CSV_EPOCH  # Still treat as epoch data

        # Cannot determine type
        available_columns = ", ".join(sorted(columns)[:10])
        raise DataDetectionError(
            file_path="<dataframe>",
            reason=(
                f"Cannot determine data type from columns. "
                f"Expected either (AXIS_X, AXIS_Y, AXIS_Z) for raw data "
                f"or (Axis1/Activity) for epoch data. "
                f"Found columns: {available_columns}"
            ),
        )

    def _detect_csv_type(self, file_path: Path) -> DataSourceType:
        """
        Detect CSV data type by loading and inspecting columns.

        Args:
            file_path: Path to CSV file

        Returns:
            DataSourceType enum value

        Raises:
            DataDetectionError: If CSV type cannot be determined

        """
        try:
            import pandas as pd

            # First, detect how many header rows to skip (ActiGraph files have 10)
            skip_rows = self._detect_skip_rows(file_path)
            logger.debug(f"Detected {skip_rows} header rows to skip in {file_path.name}")

            # Read first few rows to inspect columns
            # Use skipinitialspace to handle CSVs with spaces after commas
            df_sample = pd.read_csv(file_path, skiprows=skip_rows, nrows=100, skipinitialspace=True)
            # Also strip any remaining whitespace from column names (handles trailing spaces)
            df_sample.columns = df_sample.columns.str.strip()

            return self.detect_from_dataframe(df_sample)

        except Exception as e:
            raise DataDetectionError(
                file_path=str(file_path),
                reason=f"Failed to read CSV file: {e}",
            ) from e

    def _detect_skip_rows(self, file_path: Path) -> int:
        """
        Detect number of header rows to skip before the column header.

        Algorithm:
        1. Read first 20 lines
        2. Find the first line that looks like a CSV column header
           (multiple comma-separated non-numeric strings)

        Args:
            file_path: Path to CSV file

        Returns:
            Number of rows to skip (0 if no headers detected)

        """
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= 20:
                        break
                    lines.append(line.strip())

            # Look for first line that looks like a column header
            for i, line in enumerate(lines):
                # Split by comma
                parts = [p.strip() for p in line.split(",")]

                # Check if this looks like a header row:
                # - Has at least 3 columns
                # - Most values are non-numeric strings (column names)
                if len(parts) >= 3:
                    non_numeric_count = 0
                    for part in parts:
                        # Skip empty parts
                        if not part:
                            continue
                        # Check if it's non-numeric (a column name)
                        try:
                            float(part.replace(",", ""))
                        except ValueError:
                            non_numeric_count += 1

                    # If most columns are non-numeric, this is likely the header
                    if non_numeric_count >= 3:
                        logger.debug(f"Found column header at line {i}: {line[:60]}...")
                        return i

            # No header found - assume no rows to skip
            return 0

        except Exception as e:
            logger.warning(f"Error detecting skip rows: {e}")
            return 0  # Default to no skip

    def _has_raw_columns(self, columns: set[str]) -> bool:
        """
        Check if DataFrame has raw tri-axial data columns.

        Args:
            columns: Set of column names

        Returns:
            True if AXIS_X, AXIS_Y, AXIS_Z columns are present

        """
        return self.RAW_CSV_COLUMNS.issubset(columns)

    def _has_epoch_columns(self, columns: set[str]) -> bool:
        """
        Check if DataFrame has epoch count column.

        Args:
            columns: Set of column names

        Returns:
            True if Axis1 or Activity column is present

        """
        columns_lower = {col.lower() for col in columns}
        return any(epoch_col.lower() in columns_lower for epoch_col in ["Axis1", "Activity", "axis1", "activity"])

    def _has_epoch_intervals(self, df: pd.DataFrame) -> bool:
        """
        Check if DataFrame has ~60 second intervals between timestamps.

        Args:
            df: DataFrame to inspect

        Returns:
            True if median interval is approximately 60 seconds

        """
        try:
            timestamps = self._get_timestamps_from_df(df)

            if timestamps is None or len(timestamps) < 2:
                logger.warning("No timestamp column found, cannot verify epoch intervals")
                return True  # Assume epoch data if no timestamp column

            # Calculate intervals
            intervals = timestamps.diff().dt.total_seconds()

            # Get median interval (ignore first NaN)
            median_interval = intervals.median()

            logger.debug(f"Median timestamp interval: {median_interval}s")

            # Check if ~60 seconds (+/-10s tolerance)
            return self.EPOCH_INTERVAL_MIN <= median_interval <= self.EPOCH_INTERVAL_MAX

        except Exception as e:
            logger.warning(f"Failed to check timestamp intervals: {e}")
            return True  # Assume epoch data if interval check fails

    def _get_timestamps_from_df(self, df: pd.DataFrame) -> pd.Series | None:
        """
        Extract timestamps from DataFrame, handling both combined and separate Date/Time columns.

        Args:
            df: DataFrame to inspect

        Returns:
            pandas Series of datetime values, or None if no timestamps found

        """
        import pandas as pd

        columns = set(df.columns)
        columns_lower = {col.lower(): col for col in columns}

        # Check for combined datetime columns first
        for col in df.columns:
            if col.lower() in {"timestamp", "datetime", "date time"}:
                try:
                    return pd.to_datetime(df[col])
                except Exception:
                    continue

        # Check for separate Date and Time columns (ActiGraph format)
        date_col = columns_lower.get("date")
        time_col = columns_lower.get("time")

        if date_col and time_col:
            try:
                # Combine Date and Time columns
                combined = df[date_col].astype(str) + " " + df[time_col].astype(str)
                return pd.to_datetime(combined)
            except Exception:
                pass

        # Fallback to first timestamp column found
        timestamp_col = self._find_timestamp_column(df)
        if timestamp_col:
            try:
                return pd.to_datetime(df[timestamp_col])
            except Exception:
                pass

        return None

    def _find_timestamp_column(self, df: pd.DataFrame) -> str | None:
        """
        Find timestamp/datetime column in DataFrame.

        Args:
            df: DataFrame to inspect

        Returns:
            Column name if found, None otherwise

        """
        # Check for common timestamp column names
        for col in df.columns:
            if col in self.TIMESTAMP_COLUMNS:
                return col

            # Case-insensitive check
            if col.lower() in {tc.lower() for tc in self.TIMESTAMP_COLUMNS}:
                return col

        return None
