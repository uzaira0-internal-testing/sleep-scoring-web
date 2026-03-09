#!/usr/bin/env python3
"""
Analysis-related dataclasses.

Provides immutable containers for aligned algorithm data to prevent
timestamp/data misalignment bugs.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sleep_scoring_app.core.constants import ActivityDataPreference

if TYPE_CHECKING:
    from datetime import datetime

    pass

logger = logging.getLogger(__name__)


__all__: list[str] = ["AlgorithmDataset", "AlignedActivityData"]


@dataclass(frozen=True)
class AlignedActivityData:
    """
    Immutable container for aligned timestamp and activity data.

    This ensures timestamps and activity values are ALWAYS paired together,
    making it impossible for them to get out of sync. The data is validated
    at construction time.

    Attributes:
        timestamps: List of datetime objects for each epoch
        activity_values: Activity counts for each epoch (same length as timestamps)
        column_type: Source column type (e.g., "axis_y", "vector_magnitude")

    Raises:
        ValueError: If timestamps and activity_values have different lengths

    """

    timestamps: tuple[datetime, ...]
    activity_values: tuple[float, ...]
    column_type: str = ActivityDataPreference.AXIS_Y

    def __post_init__(self) -> None:
        """Validate data alignment at construction time."""
        if len(self.timestamps) != len(self.activity_values):
            msg = (
                f"AlignedActivityData length mismatch: "
                f"timestamps={len(self.timestamps)}, "
                f"activity_values={len(self.activity_values)}. "
                f"Data must be loaded together from the same source."
            )
            logger.error(msg)
            raise ValueError(msg)

    def __len__(self) -> int:
        """Return number of data points."""
        return len(self.timestamps)

    @property
    def is_empty(self) -> bool:
        """Check if container has no data."""
        return len(self.timestamps) == 0

    @classmethod
    def from_lists(
        cls,
        timestamps: list[datetime],
        activity_values: list[float],
        column_type: str = ActivityDataPreference.AXIS_Y,
    ) -> AlignedActivityData:
        """
        Create from mutable lists, converting to immutable tuples.

        Args:
            timestamps: List of datetime objects
            activity_values: List of activity values
            column_type: Column type identifier

        Returns:
            Immutable AlignedActivityData instance

        Raises:
            ValueError: If lengths don't match

        """
        return cls(
            timestamps=tuple(timestamps),
            activity_values=tuple(activity_values),
            column_type=column_type,
        )

    @classmethod
    def empty(cls, column_type: str = ActivityDataPreference.AXIS_Y) -> AlignedActivityData:
        """Create an empty AlignedActivityData instance."""
        return cls(timestamps=(), activity_values=(), column_type=column_type)


@dataclass(frozen=True)
class AlgorithmDataset:
    """
    Immutable container for algorithm input/output data.

    Keeps timestamps and all related data (activity, algorithm results)
    together to prevent misalignment. Used primarily by sleep scoring algorithms.

    Attributes:
        axis_y_data: Aligned axis_y data (timestamps + activity values)
        sadeh_results: Sleep scoring results (same length as axis_y_data, or None)

    Raises:
        ValueError: If sadeh_results length doesn't match axis_y_data

    """

    axis_y_data: AlignedActivityData
    sadeh_results: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        """Validate algorithm results alignment."""
        if self.sadeh_results is not None and len(self.sadeh_results) != len(self.axis_y_data):
            msg = (
                f"AlgorithmDataset sadeh_results mismatch: "
                f"axis_y_data={len(self.axis_y_data)}, "
                f"sadeh_results={len(self.sadeh_results)}. "
                f"Algorithm results must match input data length."
            )
            logger.error(msg)
            raise ValueError(msg)

    @property
    def timestamps(self) -> tuple[datetime, ...]:
        """Get timestamps from underlying axis_y_data."""
        return self.axis_y_data.timestamps

    @property
    def activity_values(self) -> tuple[float, ...]:
        """Get activity values from underlying axis_y_data."""
        return self.axis_y_data.activity_values

    def __len__(self) -> int:
        """Return number of data points."""
        return len(self.axis_y_data)

    @property
    def is_empty(self) -> bool:
        """Check if dataset has no data."""
        return self.axis_y_data.is_empty

    def with_sadeh_results(self, results: list[int]) -> AlgorithmDataset:
        """
        Create new dataset with Sadeh results attached.

        Args:
            results: Sleep scoring results (must match data length)

        Returns:
            New AlgorithmDataset with results attached

        Raises:
            ValueError: If results length doesn't match

        """
        return AlgorithmDataset(
            axis_y_data=self.axis_y_data,
            sadeh_results=tuple(results),
        )

    @classmethod
    def from_aligned_data(cls, axis_y_data: AlignedActivityData) -> AlgorithmDataset:
        """Create from AlignedActivityData without algorithm results."""
        return cls(axis_y_data=axis_y_data, sadeh_results=None)

    @classmethod
    def empty(cls) -> AlgorithmDataset:
        """Create an empty AlgorithmDataset instance."""
        return cls(axis_y_data=AlignedActivityData.empty())
