#!/usr/bin/env python3
"""
Plot Data Manager for Activity Plot Widget.

Manages all data operations for the activity plot including:
- Loading and caching activity data
- Managing 48-hour and view-specific data
- Handling timestamps and data ranges
- Managing data swapping between axis_y and vector magnitude
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


class PlotDataManager:
    """
    Manages data operations for the activity plot widget.

    Responsibilities:
    - Load and cache activity data
    - Manage 48-hour main data and view subsets
    - Handle timestamp operations
    - Coordinate data swapping
    - Manage data ranges and boundaries
    """

    def __init__(self, parent: ActivityPlotWidget) -> None:
        """Initialize the plot data manager."""
        self.parent = parent
        logger.info("PlotDataManager initialized")

        # Data storage
        self.timestamps: list[datetime] = []
        self.activity_data: list[float] = []
        self.sadeh_results: list[int] = []

        # 48-hour main data cache
        self.main_48h_timestamps: list[datetime] | None = None
        self.main_48h_activity: list[float] | None = None
        self.main_48h_axis_y_data: list[float] | None = None
        self.main_48h_sadeh_results: list[int] | None = None

        # Data boundaries
        self.data_start_time: float = 0
        self.data_end_time: float = 0
        self.view_start_idx: int = 0
        self.view_end_idx: int = 0

        # Current view mode
        self.current_view_hours: int = 48
        self.is_data_swapped: bool = False

    def set_timestamps(self, timestamps: list[datetime]) -> None:
        """Set the timestamp data."""
        self.timestamps = timestamps
        self.parent.timestamps = timestamps  # Keep parent reference for compatibility
        if timestamps:
            self.data_start_time = timestamps[0].timestamp()
            self.data_end_time = timestamps[-1].timestamp()
            logger.debug(f"Set {len(timestamps)} timestamps, range: {timestamps[0]} to {timestamps[-1]}")

    def set_activity_data(self, activity_data: list[float]) -> None:
        """Set the activity data."""
        self.activity_data = activity_data
        self.parent.activity_data = activity_data  # Keep parent reference
        logger.debug(f"Set {len(activity_data)} activity data points")

    def set_48h_main_data(
        self, timestamps: list[datetime], activity: list[float], axis_y: list[float] | None = None, sadeh: list[int] | None = None
    ) -> None:
        """
        Set the 48-hour main data cache.

        Args:
            timestamps: 48-hour timestamp array
            activity: 48-hour activity data
            axis_y: 48-hour axis_y data (optional)
            sadeh: 48-hour Sadeh results (optional)

        """
        self.main_48h_timestamps = timestamps
        self.main_48h_activity = activity
        self.main_48h_axis_y_data = axis_y
        self.main_48h_sadeh_results = sadeh

        # Update parent references for compatibility
        self.parent.main_48h_timestamps = timestamps
        self.parent.main_48h_activity = activity
        self.parent.main_48h_axis_y_data = axis_y
        self.parent.main_48h_sadeh_results = sadeh

        logger.info(f"Cached 48h main data: {len(timestamps)} points")

    def get_view_indices(self, start_hour: int, duration_hours: int) -> tuple[int, int]:
        """
        Calculate view indices for a time range.

        Args:
            start_hour: Starting hour (0-47)
            duration_hours: Duration in hours

        Returns:
            Tuple of (start_index, end_index)

        """
        if not self.main_48h_timestamps:
            return 0, 0

        # Calculate indices based on 1-minute epochs
        start_idx = start_hour * 60
        end_idx = min(start_idx + (duration_hours * 60), len(self.main_48h_timestamps))

        return start_idx, end_idx

    def extract_view_subset(self, start_idx: int, end_idx: int, include_algorithms: bool = True) -> dict[str, Any]:
        """
        Extract a subset of data for the current view.

        Args:
            start_idx: Start index in main data
            end_idx: End index in main data
            include_algorithms: Whether to include algorithm results

        Returns:
            Dictionary containing view data

        """
        if not self.main_48h_timestamps:
            return {}

        view_data = {
            "timestamps": self.main_48h_timestamps[start_idx:end_idx],
            "activity": self.main_48h_activity[start_idx:end_idx] if self.main_48h_activity else [],
        }

        if include_algorithms and self.main_48h_sadeh_results:
            view_data["sadeh"] = self.main_48h_sadeh_results[start_idx:end_idx]

        self.view_start_idx = start_idx
        self.view_end_idx = end_idx

        return view_data

    def swap_activity_data_source(self, use_vector_magnitude: bool) -> bool:
        """
        Swap between axis_y and vector magnitude data.

        Args:
            use_vector_magnitude: True to use vector magnitude, False for axis_y

        Returns:
            True if swap was successful

        """
        if not self.main_48h_activity or not self.main_48h_axis_y_data:
            logger.warning("Cannot swap data - missing required data arrays")
            return False

        if use_vector_magnitude and not self.is_data_swapped:
            # Swap to vector magnitude
            self.main_48h_activity, self.main_48h_axis_y_data = self.main_48h_axis_y_data, self.main_48h_activity
            self.is_data_swapped = True
            logger.info("Swapped to vector magnitude data")
        elif not use_vector_magnitude and self.is_data_swapped:
            # Swap back to axis_y
            self.main_48h_activity, self.main_48h_axis_y_data = self.main_48h_axis_y_data, self.main_48h_activity
            self.is_data_swapped = False
            logger.info("Swapped to axis_y data")
        else:
            logger.debug("No swap needed - already using requested data source")

        return True

    def clear_all_data(self) -> None:
        """Clear all stored data."""
        self.timestamps = []
        self.activity_data = []
        self.sadeh_results = []
        self.main_48h_timestamps = None
        self.main_48h_activity = None
        self.main_48h_axis_y_data = None
        self.main_48h_sadeh_results = None
        self.main_48h_sadeh_timestamps = None  # CRITICAL: Clear alongside sadeh_results
        self.data_start_time = 0
        self.data_end_time = 0
        self.view_start_idx = 0
        self.view_end_idx = 0
        self.is_data_swapped = False

        # Clear parent references
        self.parent.timestamps = []
        self.parent.activity_data = []
        self.parent.main_48h_timestamps = None
        self.parent.main_48h_activity = None
        self.parent.main_48h_axis_y_data = None
        self.parent.main_48h_sadeh_results = None
        self.parent.main_48h_sadeh_timestamps = None  # CRITICAL: Clear alongside sadeh_results

        logger.info("Cleared all plot data")

    def get_current_view_hours(self) -> int:
        """Get the current view duration in hours."""
        return self.current_view_hours

    def set_current_view_hours(self, hours: int) -> None:
        """Set the current view duration in hours."""
        self.current_view_hours = hours
        logger.debug(f"Set view hours to {hours}")
