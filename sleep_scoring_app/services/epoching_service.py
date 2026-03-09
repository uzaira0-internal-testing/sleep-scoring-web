"""
Epoching service for converting raw accelerometer data to epoch counts.

This service handles the conversion of raw high-frequency tri-axial
accelerometer data into fixed-length epoch counts for use with epoch-based
sleep scoring algorithms (Sadeh, Cole-Kripke).

Example Usage:
    >>> from sleep_scoring_app.services.epoching_service import EpochingService
    >>> import pandas as pd
    >>>
    >>> # Load raw data
    >>> raw_df = pd.read_csv("raw_data.csv")
    >>>
    >>> # Create service
    >>> service = EpochingService()
    >>>
    >>> # Create 60-second epochs
    >>> epoch_df = service.create_epochs(raw_df, epoch_seconds=60)
    >>> print(epoch_df.columns)  # ['datetime', 'Axis1']

References:
    - CLAUDE.md: Service layer patterns
    - core/backends/protocol.py: ComputeBackend for actual computation

"""

from __future__ import annotations

import logging
from typing import ClassVar

import numpy as np
import pandas as pd

from sleep_scoring_app.core.constants import DefaultColumn
from sleep_scoring_app.core.pipeline.exceptions import EpochingError

logger = logging.getLogger(__name__)


class EpochingService:
    """
    Service for creating epoch counts from raw accelerometer data.

    This service converts raw tri-axial accelerometer data (typically 30-100 Hz)
    into fixed-length epoch counts (typically 60 seconds) by:
    1. Calculating vector magnitude (VM) from X, Y, Z axes
    2. Resampling to epoch intervals
    3. Summing absolute values within each epoch

    The output format matches ActiGraph epoch CSV files (datetime, Axis1 columns).

    Example:
        >>> service = EpochingService()
        >>> epoch_df = service.create_epochs(raw_df, epoch_seconds=60)

    """

    # Required columns for raw data
    REQUIRED_RAW_COLUMNS: ClassVar[set[str]] = {"timestamp", "AXIS_X", "AXIS_Y", "AXIS_Z"}

    # Alternative timestamp column names
    TIMESTAMP_ALIASES: ClassVar[set[str]] = {"timestamp", "datetime", "Timestamp", "Date Time"}

    def create_epochs(
        self,
        raw_data: pd.DataFrame,
        epoch_seconds: int = 60,
        use_axis: str = "Y",
    ) -> pd.DataFrame:
        """
        Create epoch counts from raw tri-axial accelerometer data.

        This method converts raw data to epoch counts compatible with
        Sadeh and Cole-Kripke algorithms.

        Args:
            raw_data: DataFrame with columns:
                - timestamp (or datetime): Timestamp for each sample
                - AXIS_X: X-axis acceleration in g
                - AXIS_Y: Y-axis acceleration in g
                - AXIS_Z: Z-axis acceleration in g
            epoch_seconds: Length of each epoch in seconds (default: 60)
            use_axis: Which axis to use for epoch counts ("Y" for vertical axis,
                     "VM" for vector magnitude). Default: "Y" (matches ActiGraph)

        Returns:
            DataFrame with columns:
                - datetime: Start of each epoch
                - Axis1: Activity count for epoch (sum of absolute values)

        Raises:
            EpochingError: If raw data is invalid or epoching fails

        Example:
            >>> service = EpochingService()
            >>> raw_df = pd.read_csv("raw_data.csv")
            >>> epoch_df = service.create_epochs(raw_df, epoch_seconds=60)
            >>> print(len(epoch_df))  # Number of 60-second epochs

        """
        logger.debug(f"Creating {epoch_seconds}s epochs from raw data")

        # Validate input data
        self._validate_raw_data(raw_data)

        # Find timestamp column
        timestamp_col = self._find_timestamp_column(raw_data)

        if timestamp_col is None:
            raise EpochingError(
                reason="No timestamp column found in raw data",
                epoch_length=epoch_seconds,
            )

        # Ensure timestamp is datetime type
        try:
            raw_data = raw_data.copy()
            raw_data[timestamp_col] = pd.to_datetime(raw_data[timestamp_col])
        except Exception as e:
            raise EpochingError(
                reason=f"Failed to convert timestamp column to datetime: {e}",
                epoch_length=epoch_seconds,
            ) from e

        # Set timestamp as index for resampling
        raw_data = raw_data.set_index(timestamp_col)

        # Select which axis/metric to use
        if use_axis.upper() == "Y":
            activity_signal = raw_data["AXIS_Y"].abs()
            logger.debug("Using Y-axis (vertical) for epoch counts")
        elif use_axis.upper() == "VM":
            # Calculate vector magnitude
            activity_signal = np.sqrt(raw_data["AXIS_X"] ** 2 + raw_data["AXIS_Y"] ** 2 + raw_data["AXIS_Z"] ** 2)
            logger.debug("Using vector magnitude for epoch counts")
        else:
            raise EpochingError(
                reason=f"Invalid use_axis parameter: {use_axis}. Must be 'Y' or 'VM'",
                epoch_length=epoch_seconds,
            )

        # Resample to epochs and sum
        try:
            epoch_counts = activity_signal.resample(f"{epoch_seconds}s").sum()

            # Reset index
            epoch_df = epoch_counts.reset_index()
            epoch_df.columns = ["datetime", DefaultColumn.AXIS_Y]

            # Convert counts to integer
            epoch_df[DefaultColumn.AXIS_Y] = epoch_df[DefaultColumn.AXIS_Y].round().astype(int)

            logger.info(f"Created {len(epoch_df)} epochs from {len(raw_data)} raw samples (epoch_length={epoch_seconds}s)")

            return epoch_df

        except Exception as e:
            raise EpochingError(
                reason=f"Failed to resample data to epochs: {e}",
                epoch_length=epoch_seconds,
            ) from e

    def _validate_raw_data(self, raw_data: pd.DataFrame) -> None:
        """
        Validate that raw data has required columns.

        Args:
            raw_data: DataFrame to validate

        Raises:
            EpochingError: If validation fails

        """
        if raw_data is None or len(raw_data) == 0:
            raise EpochingError(reason="Raw data is None or empty")

        # Check for required columns (timestamp can have different names)
        has_timestamp = self._find_timestamp_column(raw_data) is not None

        if not has_timestamp:
            raise EpochingError(reason=f"Missing timestamp column. Expected one of: {', '.join(self.TIMESTAMP_ALIASES)}")

        if "AXIS_X" not in raw_data.columns:
            raise EpochingError(reason="Missing AXIS_X column in raw data")

        if "AXIS_Y" not in raw_data.columns:
            raise EpochingError(reason="Missing AXIS_Y column in raw data")

        if "AXIS_Z" not in raw_data.columns:
            raise EpochingError(reason="Missing AXIS_Z column in raw data")

        logger.debug("Raw data validation passed")

    def _find_timestamp_column(self, df: pd.DataFrame) -> str | None:
        """
        Find timestamp column in DataFrame.

        Args:
            df: DataFrame to search

        Returns:
            Column name if found, None otherwise

        """
        for col in df.columns:
            if col in self.TIMESTAMP_ALIASES:
                return col

            # Case-insensitive check
            if col.lower() in {ts.lower() for ts in self.TIMESTAMP_ALIASES}:
                return col

        return None

    def estimate_sample_rate(self, raw_data: pd.DataFrame) -> float:
        """
        Estimate sample rate from timestamp intervals.

        This is a utility method for determining the sampling frequency
        of raw data.

        Args:
            raw_data: DataFrame with timestamp column

        Returns:
            Estimated sample rate in Hz

        Raises:
            EpochingError: If sample rate cannot be estimated

        Example:
            >>> service = EpochingService()
            >>> sample_rate = service.estimate_sample_rate(raw_df)
            >>> print(f"Sample rate: {sample_rate} Hz")

        """
        timestamp_col = self._find_timestamp_column(raw_data)

        if timestamp_col is None:
            raise EpochingError(reason="Cannot estimate sample rate without timestamp column")

        try:
            timestamps = pd.to_datetime(raw_data[timestamp_col])

            # Calculate intervals
            intervals = timestamps.diff().dt.total_seconds()

            # Get median interval (ignore first NaN)
            median_interval = intervals.median()

            if median_interval <= 0 or np.isnan(median_interval):
                raise EpochingError(reason=f"Invalid timestamp intervals (median={median_interval}s)")

            # Sample rate is inverse of interval
            sample_rate = 1.0 / median_interval

            logger.debug(f"Estimated sample rate: {sample_rate:.2f} Hz")

            return sample_rate

        except Exception as e:
            raise EpochingError(reason=f"Failed to estimate sample rate: {e}") from e
