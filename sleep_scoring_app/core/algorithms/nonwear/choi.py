"""
Choi (2011) nonwear detection algorithm - Framework-agnostic implementation.

This module implements the Choi algorithm for detecting periods when an accelerometer
is not being worn. The implementation uses FIXED validated parameters from the published
paper and provides a simple function-based API.

References:
    Choi, L., Liu, Z., Matthews, C. E., & Buchowski, M. S. (2011).
    Validation of accelerometer wear and nonwear time classification algorithm.
    Medicine and Science in Sports and Exercise, 43(2), 357-364.

Algorithm Details:
    - Identifies consecutive zero-count periods as potential nonwear
    - Allows small spikes (<=2 minutes) within larger zero periods
    - Validates minimum period length (default: 90 minutes)
    - Merges adjacent/overlapping periods
    - Can use single axis or vector magnitude (specified via ActivityColumn enum)

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from sleep_scoring_app.core.algorithms.sleep_wake.utils import find_datetime_column, validate_and_collapse_epochs
from sleep_scoring_app.core.algorithms.types import ActivityColumn
from sleep_scoring_app.core.constants import ActivityDataPreference, AlgorithmOutputColumn, NonwearAlgorithm, NonwearDataSource
from sleep_scoring_app.core.dataclasses import NonwearPeriod

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)

MIN_PERIOD_LENGTH: int = 90
SPIKE_TOLERANCE: int = 2
WINDOW_SIZE: int = 30


def _merge_adjacent_periods(periods: list[NonwearPeriod]) -> list[NonwearPeriod]:
    """
    Merge adjacent or overlapping nonwear periods.

    Args:
        periods: List of NonwearPeriod objects

    Returns:
        List of merged NonwearPeriod objects

    """
    if not periods:
        return periods

    periods.sort(key=lambda x: x.start_time)

    merged_periods: list[NonwearPeriod] = []
    current = periods[0]

    for next_period in periods[1:]:
        if (next_period.start_time - current.end_time).total_seconds() <= 60:
            # Calculate merged end_index (handle None values)
            merged_end_index = None
            if current.end_index is not None and next_period.end_index is not None:
                merged_end_index = max(current.end_index, next_period.end_index)
            elif current.end_index is not None:
                merged_end_index = current.end_index
            elif next_period.end_index is not None:
                merged_end_index = next_period.end_index

            # Calculate duration_minutes if indices are available
            duration_minutes = None
            if current.start_index is not None and merged_end_index is not None:
                duration_minutes = merged_end_index - current.start_index + 1

            current = NonwearPeriod(
                start_time=current.start_time,
                end_time=max(current.end_time, next_period.end_time),
                participant_id=current.participant_id,
                source=current.source,
                duration_minutes=duration_minutes,
                start_index=current.start_index,
                end_index=merged_end_index,
            )
        else:
            merged_periods.append(current)
            current = next_period

    merged_periods.append(current)

    return merged_periods


def choi_detect_nonwear(
    data: pd.DataFrame,
    activity_column: ActivityColumn = ActivityColumn.VECTOR_MAGNITUDE,
) -> pd.DataFrame:
    """
    Apply Choi (2011) nonwear detection algorithm.

    Uses FIXED validated parameters from the published paper:
    - Minimum period: 90 minutes
    - Spike tolerance: 2 minutes
    - Window size: 30 minutes

    The algorithm detects periods when the accelerometer is not being worn by
    identifying extended intervals of zero or near-zero activity. This is a
    validated research algorithm with parameters that should not be modified.

    Args:
        data: DataFrame with datetime and activity columns
        activity_column: Which activity column to use (VECTOR_MAGNITUDE recommended, or AXIS_Y)

    Returns:
        Original DataFrame with new 'Choi Nonwear' column appended (1=nonwear, 0=wear)

    Raises:
        ValueError: If epochs are larger than 1 minute or required columns missing

    Validation:
        - Finds datetime/date+time columns automatically
        - Verifies 1-minute epochs (+/-1 second tolerance)
        - Collapses to 1-minute if epochs < 1 minute
        - Raises error if epochs > 1 minute

    Example:
        >>> import pandas as pd
        >>> from sleep_scoring_app.core.algorithms import choi_detect_nonwear, ActivityColumn
        >>> data = pd.read_csv('activity.csv')
        >>> data.head()
           datetime             Axis1  Vector Magnitude
        0  2024-01-01 00:00:00  45     52.3
        1  2024-01-01 00:01:00  32     38.1
        2  2024-01-01 00:02:00  0      0.0
        >>> data = choi_detect_nonwear(data, ActivityColumn.VECTOR_MAGNITUDE)
        >>> data.head()
           datetime             Axis1  Vector Magnitude  Choi Nonwear
        0  2024-01-01 00:00:00  45     52.3              0
        1  2024-01-01 00:01:00  32     38.1              0
        2  2024-01-01 00:02:00  0      0.0               1

    """
    if data is None or len(data) == 0:
        msg = "DataFrame cannot be None or empty"
        raise ValueError(msg)

    datetime_col = find_datetime_column(data)

    data = validate_and_collapse_epochs(data, datetime_col)

    column_name = activity_column.value
    if column_name not in data.columns:
        msg = f"DataFrame must contain '{column_name}' column. Available columns: {data.columns.tolist()}"
        raise ValueError(msg)

    counts = data[column_name].to_numpy()
    timestamps = data[datetime_col].to_numpy()

    if len(counts) == 0:
        result_df = data.copy()
        result_df[AlgorithmOutputColumn.NONWEAR_SCORE] = []
        return result_df

    nonwear_periods: list[NonwearPeriod] = []
    i = 0

    while i < len(counts):
        if counts[i] > 0:
            i += 1
            continue

        start_idx = i
        end_idx = i

        nonwear_continuation = i

        while nonwear_continuation < len(counts):
            if counts[nonwear_continuation] == 0:
                end_idx = nonwear_continuation
                nonwear_continuation += 1
                continue

            window_start = max(0, nonwear_continuation - WINDOW_SIZE)
            window_end = min(len(counts), nonwear_continuation + WINDOW_SIZE)

            if window_end - window_start > 1000000:
                logger.warning(f"Window size too large: {window_end - window_start}, limiting to 1000000")
                window_end = window_start + 1000000

            nonzero_count = np.sum(counts[window_start:window_end] > 0)

            if nonzero_count > SPIKE_TOLERANCE:
                break

            nonwear_continuation += 1

        if end_idx - start_idx + 1 >= MIN_PERIOD_LENGTH:
            start_time = pd.to_datetime(timestamps[start_idx])
            end_time = pd.to_datetime(timestamps[end_idx])
            period = NonwearPeriod(
                start_time=start_time,
                end_time=end_time,
                participant_id="",
                source=NonwearDataSource.CHOI_ALGORITHM,
                duration_minutes=end_idx - start_idx + 1,
                start_index=start_idx,
                end_index=end_idx,
            )
            nonwear_periods.append(period)
            i = end_idx + 1
        else:
            i += 1

    merged_periods = _merge_adjacent_periods(nonwear_periods)

    nonwear_mask = np.zeros(len(data), dtype=int)
    for period in merged_periods:
        # Skip periods without valid indices
        if period.start_index is not None and period.end_index is not None:
            nonwear_mask[period.start_index : period.end_index + 1] = 1

    result_df = data.copy()
    result_df[AlgorithmOutputColumn.NONWEAR_SCORE] = nonwear_mask

    return result_df


class ChoiAlgorithm:
    """
    Choi (2011) nonwear detection algorithm implementation.

    Implements the NonwearDetectionAlgorithm protocol for dependency injection.
    Uses fixed validated parameters from the published research.

    Algorithm Parameters (configurable):
        min_period_length: Minimum consecutive minutes for nonwear period (default: 90)
        spike_tolerance: Maximum allowed consecutive non-zero minutes (default: 2)
        small_window_length: Window size to check around spikes (default: 30)
        use_vector_magnitude: Whether to use vector magnitude vs single axis (default: True)

    Note: While parameters are configurable, the defaults are validated values from
    the original paper and should not be changed without strong justification.
    """

    def __init__(
        self,
        min_period_length: int = 90,
        spike_tolerance: int = 2,
        small_window_length: int = 30,
        use_vector_magnitude: bool = True,
    ) -> None:
        """
        Initialize Choi algorithm with parameters.

        Args:
            min_period_length: Minimum consecutive minutes for nonwear period
            spike_tolerance: Maximum allowed consecutive non-zero minutes
            small_window_length: Window size to check around spikes
            use_vector_magnitude: Whether to use vector magnitude vs single axis

        """
        self._min_period_length = min_period_length
        self._spike_tolerance = spike_tolerance
        self._small_window_length = small_window_length
        self._use_vector_magnitude = use_vector_magnitude

        # Log warning if non-standard parameters are used
        if min_period_length != 90 or spike_tolerance != 2 or small_window_length != 30:
            logger.warning(
                "Choi algorithm initialized with non-standard parameters: "
                f"min_period={min_period_length}, spike_tolerance={spike_tolerance}, "
                f"window={small_window_length}. Standard validated values are 90, 2, 30."
            )

    @property
    def name(self) -> str:
        """Algorithm display name."""
        return "Choi (2011)"

    @property
    def identifier(self) -> str:
        """Algorithm unique identifier."""
        return NonwearAlgorithm.CHOI_2011

    def detect(
        self,
        activity_data: list[float] | np.ndarray,
        timestamps: list[datetime],
        activity_column: str = ActivityDataPreference.AXIS_Y,
    ) -> list[NonwearPeriod]:
        """
        Detect nonwear periods from activity data.

        Args:
            activity_data: List or array of activity count values
            timestamps: List of datetime objects corresponding to activity data
            activity_column: Name of activity column for reference (ignored - for API compatibility)

        Returns:
            List of NonwearPeriod objects representing detected nonwear periods

        Raises:
            ValueError: If input data is invalid or mismatched lengths

        """
        if activity_data is None or timestamps is None:
            msg = "activity_data and timestamps cannot be None"
            raise ValueError(msg)

        if len(activity_data) != len(timestamps):
            msg = f"activity_data length ({len(activity_data)}) must match timestamps length ({len(timestamps)})"
            raise ValueError(msg)

        if len(activity_data) == 0:
            return []

        counts = np.array(activity_data, dtype=np.float64)

        if np.any(np.isnan(counts)):
            msg = "activity_data contains NaN (Not a Number) values"
            raise ValueError(msg)

        if np.any(np.isinf(counts)):
            msg = "activity_data contains infinite values"
            raise ValueError(msg)

        if np.any(counts < 0):
            negative_indices = np.where(counts < 0)[0]
            msg = f"activity_data contains negative values at indices: {negative_indices[:10].tolist()}"
            raise ValueError(msg)

        logger.debug(f"Running Choi algorithm on {len(counts)} epochs")

        nonwear_periods: list[NonwearPeriod] = []
        i = 0

        while i < len(counts):
            if counts[i] > 0:
                i += 1
                continue

            start_idx = i
            end_idx = i

            nonwear_continuation = i

            while nonwear_continuation < len(counts):
                if counts[nonwear_continuation] == 0:
                    end_idx = nonwear_continuation
                    nonwear_continuation += 1
                    continue

                window_start = max(0, nonwear_continuation - self._small_window_length)
                window_end = min(len(counts), nonwear_continuation + self._small_window_length)

                if window_end - window_start > 1000000:
                    logger.warning(f"Window size too large: {window_end - window_start}, limiting to 1000000")
                    window_end = window_start + 1000000

                nonzero_count = np.sum(counts[window_start:window_end] > 0)

                if nonzero_count > self._spike_tolerance:
                    break

                nonwear_continuation += 1

            if end_idx - start_idx + 1 >= self._min_period_length:
                start_time = timestamps[start_idx]
                end_time = timestamps[end_idx]
                period = NonwearPeriod(
                    start_time=start_time,
                    end_time=end_time,
                    participant_id="",
                    source=NonwearDataSource.CHOI_ALGORITHM,
                    duration_minutes=end_idx - start_idx + 1,
                    start_index=start_idx,
                    end_index=end_idx,
                )
                nonwear_periods.append(period)
                i = end_idx + 1
            else:
                i += 1

        merged_periods = _merge_adjacent_periods(nonwear_periods)

        logger.debug(f"Choi algorithm completed successfully. Found {len(merged_periods)} nonwear periods")

        return merged_periods

    def detect_mask(self, activity_data: list[float] | np.ndarray) -> list[int]:
        """
        Generate per-epoch nonwear mask from activity data.

        Args:
            activity_data: List or array of activity count values

        Returns:
            List of 0/1 values where 0=wearing, 1=not wearing

        Raises:
            ValueError: If input data is invalid

        """
        if activity_data is None:
            msg = "activity_data cannot be None"
            raise ValueError(msg)

        if len(activity_data) == 0:
            return []

        # Create dummy timestamps for mask generation
        from datetime import datetime, timedelta

        timestamps = [datetime(2000, 1, 1) + timedelta(minutes=i) for i in range(len(activity_data))]

        # Get nonwear periods
        periods = self.detect(activity_data, timestamps)

        # Convert to mask
        mask = [0] * len(activity_data)
        for period in periods:
            if period.start_index is not None and period.end_index is not None:
                for i in range(period.start_index, min(period.end_index + 1, len(mask))):
                    mask[i] = 1

        return mask

    def get_parameters(self) -> dict[str, int | bool]:
        """
        Get current algorithm parameters.

        Returns:
            Dictionary of parameter names and values

        """
        return {
            "min_period_length": self._min_period_length,
            "spike_tolerance": self._spike_tolerance,
            "small_window_length": self._small_window_length,
            "use_vector_magnitude": self._use_vector_magnitude,
        }

    def set_parameters(self, **kwargs: int | bool) -> None:
        """
        Update algorithm parameters.

        Args:
            **kwargs: Parameter name-value pairs

        Raises:
            ValueError: If parameter name is invalid or value is out of range

        """
        valid_params = {
            "min_period_length",
            "spike_tolerance",
            "small_window_length",
            "use_vector_magnitude",
        }

        for key, value in kwargs.items():
            if key not in valid_params:
                msg = f"Invalid parameter: {key}. Valid parameters: {valid_params}"
                raise ValueError(msg)

            if key == "min_period_length":
                if not isinstance(value, int) or value < 1:
                    msg = f"min_period_length must be positive integer, got {value}"
                    raise ValueError(msg)
                self._min_period_length = value

            elif key == "spike_tolerance":
                if not isinstance(value, int) or value < 0:
                    msg = f"spike_tolerance must be non-negative integer, got {value}"
                    raise ValueError(msg)
                self._spike_tolerance = value

            elif key == "small_window_length":
                if not isinstance(value, int) or value < 1:
                    msg = f"small_window_length must be positive integer, got {value}"
                    raise ValueError(msg)
                self._small_window_length = value

            elif key == "use_vector_magnitude":
                if not isinstance(value, bool):
                    msg = f"use_vector_magnitude must be boolean, got {value}"
                    raise ValueError(msg)
                self._use_vector_magnitude = value

        # Log warning if non-standard parameters are set
        if self._min_period_length != 90 or self._spike_tolerance != 2 or self._small_window_length != 30:
            logger.warning(
                "Choi algorithm parameters changed to non-standard values: "
                f"min_period={self._min_period_length}, spike_tolerance={self._spike_tolerance}, "
                f"window={self._small_window_length}. Standard validated values are 90, 2, 30."
            )
