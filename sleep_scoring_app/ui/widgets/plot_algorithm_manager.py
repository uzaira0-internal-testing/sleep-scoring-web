#!/usr/bin/env python3
"""
Plot Algorithm Manager - Handles sleep scoring algorithms and rule application.

Extracted from ActivityPlotWidget to reduce god class size.
Manages Sadeh algorithm execution, sleep onset/offset rule application,
and algorithm result caching.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pandas as pd
import pyqtgraph as pg

from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    AlgorithmOutputColumn,
    ArrowColorKey,
    DatabaseColumn,
    DefaultColumn,
    NonwearAlgorithm,
    UIColors,
)

if TYPE_CHECKING:
    from sleep_scoring_app.core.algorithms.sleep_period.protocol import SleepPeriodDetector
    from sleep_scoring_app.core.algorithms.sleep_wake.protocol import SleepScoringAlgorithm
    from sleep_scoring_app.core.dataclasses import SleepPeriod
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


class PlotAlgorithmManager:
    """Manages sleep scoring algorithms and rule application for ActivityPlotWidget."""

    def __init__(self, parent: ActivityPlotWidget) -> None:
        """
        Initialize the algorithm manager with parent reference.

        Args:
            parent: The ActivityPlotWidget that owns this manager

        """
        self.parent = parent
        self._algorithm_cache: dict[str, dict[str, Any]] = {}
        self._sleep_pattern_cache: dict[tuple, tuple] = {}
        self._sleep_scoring_algorithm: SleepScoringAlgorithm | None = None
        self._sleep_period_detector: SleepPeriodDetector | None = None

    # ========== Property Accessors ==========

    @property
    def timestamps(self) -> list[datetime] | None:
        """Access parent's timestamps."""
        return self.parent.timestamps

    @property
    def x_data(self) -> list[float] | None:
        """Access parent's x_data."""
        return self.parent.x_data

    @property
    def activity_data(self) -> list[float] | None:
        """Access parent's activity_data."""
        return getattr(self.parent, "activity_data", None)

    @property
    def sadeh_results(self) -> list[int] | None:
        """Access parent's sadeh_results."""
        return getattr(self.parent, "sadeh_results", None)

    def _get_choi_activity_column(self) -> str:
        """
        Get the Choi activity column from config.

        Returns:
            Activity column name: 'vector_magnitude' (default), 'axis_y', 'axis_x', or 'axis_z'

        """
        try:
            return self.parent.get_choi_activity_column()
        except Exception as e:
            logger.debug("Exception getting Choi activity column: %s", e)
            return ActivityDataPreference.VECTOR_MAGNITUDE

    def get_sleep_scoring_algorithm(self) -> SleepScoringAlgorithm:
        """
        Get the current sleep scoring algorithm instance.

        Creates the algorithm from the factory if not already cached.
        Uses configuration to determine which algorithm and parameters to use.

        Returns:
            SleepScoringAlgorithm instance (default: SadehAlgorithm)

        """
        if self._sleep_scoring_algorithm is None:
            # Get config from main window
            config = self.parent.get_algorithm_config()

            # Get algorithm ID from config or use default
            algorithm_id = self.parent.get_default_sleep_algorithm_id()
            if config and config.sleep_algorithm_id:
                algorithm_id = config.sleep_algorithm_id

            algo = self.parent.create_sleep_algorithm(algorithm_id, config)
            if algo is None:
                msg = f"Failed to create sleep algorithm with id: {algorithm_id}"
                raise RuntimeError(msg)
            self._sleep_scoring_algorithm = algo
            logger.debug("Created sleep scoring algorithm: %s (id: %s)", algo.name, algorithm_id)

        # _sleep_scoring_algorithm is set above, cannot be None here
        assert self._sleep_scoring_algorithm is not None
        return self._sleep_scoring_algorithm

    def set_sleep_scoring_algorithm(self, algorithm: SleepScoringAlgorithm) -> None:
        """
        Set the sleep scoring algorithm instance.

        Clears caches when algorithm changes to ensure fresh results.

        Args:
            algorithm: SleepScoringAlgorithm instance to use

        """
        self._sleep_scoring_algorithm = algorithm
        # Clear caches when algorithm changes
        self._algorithm_cache.clear()
        self._sleep_pattern_cache.clear()
        logger.info("Sleep scoring algorithm changed to: %s", algorithm.name)

    def get_sleep_period_detector(self) -> SleepPeriodDetector:
        """
        Get the current sleep period detector instance.

        Creates the detector from the factory if not already cached.
        Uses configuration to determine which detector and parameters to use.

        Returns:
            SleepPeriodDetector instance (default: Consecutive 3S/5S)

        """
        if self._sleep_period_detector is None:
            # Get config from main window
            config = self.parent.get_algorithm_config()

            # Get detector ID from config or use default
            detector_id = self.parent.get_default_sleep_period_detector_id()
            if config and config.onset_offset_rule_id:
                detector_id = config.onset_offset_rule_id

            detector = self.parent.create_sleep_period_detector(detector_id)
            if detector is None:
                msg = f"Failed to create sleep period detector with id: {detector_id}"
                raise RuntimeError(msg)
            self._sleep_period_detector = detector
            logger.debug("Created sleep period detector: %s (id: %s)", detector.name, detector_id)

        # _sleep_period_detector is set above, cannot be None here
        assert self._sleep_period_detector is not None
        return self._sleep_period_detector

    def set_sleep_period_detector(self, detector: SleepPeriodDetector) -> None:
        """
        Set the sleep period detector instance.

        Clears caches when detector changes to ensure fresh results.

        Args:
            detector: SleepPeriodDetector instance to use

        """
        self._sleep_period_detector = detector
        # Clear caches when detector changes
        self._sleep_pattern_cache.clear()
        logger.info("Sleep period detector changed to: %s", detector.name)

    @sadeh_results.setter
    def sadeh_results(self, value: list[int] | None) -> None:
        """Set parent's sadeh_results."""
        self.parent.sadeh_results = value

    @property
    def main_48h_timestamps(self) -> list[datetime] | None:
        """Access parent's main 48hr timestamps."""
        return self.parent.main_48h_timestamps

    @property
    def main_48h_activity(self) -> list[float] | None:
        """Access parent's main 48hr activity data."""
        return self.parent.main_48h_activity

    @property
    def main_48h_sadeh_results(self) -> list[int] | None:
        """Access parent's main 48hr Sadeh results."""
        return self.parent.main_48h_sadeh_results

    @main_48h_sadeh_results.setter
    def main_48h_sadeh_results(self, value: list[int] | None) -> None:
        """Set parent's main 48hr Sadeh results."""
        self.parent.main_48h_sadeh_results = value

    @property
    def main_48h_axis_y_data(self) -> list[float] | None:
        """Access parent's main 48hr axis_y data."""
        return self.parent.main_48h_axis_y_data

    @main_48h_axis_y_data.setter
    def main_48h_axis_y_data(self, value: list[float] | None) -> None:
        """Set parent's main 48hr axis_y data."""
        self.parent.main_48h_axis_y_data = value

    @property
    def data_max_y(self) -> float:
        """Access parent's data_max_y."""
        return self.parent.data_max_y

    @property
    def plotItem(self) -> pg.PlotItem | None:
        """Access parent's plotItem."""
        return self.parent.plotItem

    # ========== Algorithm Execution Methods ==========

    def plot_algorithms(self) -> None:
        """Run and plot algorithms with performance optimization and caching."""
        if not self.activity_data:
            logger.debug("No activity data available for algorithm plotting")
            return

        # Always use 48hr main data for algorithms if available
        main_ts = self.main_48h_timestamps
        main_act = self.main_48h_activity
        if main_ts is not None and main_act is not None and hasattr(main_ts, "__len__"):
            algorithm_timestamps = main_ts
            algorithm_activity = main_act
            logger.debug("Using 48hr main data for algorithms: %d points", len(main_ts))
        else:
            algorithm_timestamps = self.timestamps
            algorithm_activity = self.activity_data
            logger.debug("Using current view data for algorithms: %d points", len(algorithm_timestamps) if algorithm_timestamps else 0)

        # Create cache key based on main data hash for efficient caching
        column_type = getattr(self.parent, "activity_column_type", "unknown")
        data_type = "vm" if column_type == DatabaseColumn.VECTOR_MAGNITUDE else "axis_y" if column_type else "unknown"
        data_hash = hashlib.md5(repr(algorithm_activity).encode()).hexdigest()[:16]

        # Include timestamp hash for proper cache invalidation
        timestamp_hash = ""
        sadeh_axis_y_hash = ""

        if self.parent.main_48h_axis_y_timestamps:
            timestamp_str = repr([ts.isoformat() if hasattr(ts, "isoformat") else str(ts) for ts in self.parent.main_48h_axis_y_timestamps[:10]])
            sadeh_axis_y_hash = hashlib.md5(timestamp_str.encode()).hexdigest()[:8]

        if data_type == "axis_y":
            timestamp_hash = sadeh_axis_y_hash
        elif algorithm_timestamps:
            timestamp_str = repr([ts.isoformat() if hasattr(ts, "isoformat") else str(ts) for ts in algorithm_timestamps[:10]])
            timestamp_hash = hashlib.md5(timestamp_str.encode()).hexdigest()[:8]

        # Include algorithm parameters in cache key so changing settings invalidates cache
        algorithm = self.get_sleep_scoring_algorithm()
        algorithm_id = algorithm.identifier
        choi_activity_col = self._get_choi_activity_column()
        cache_key = f"48h_{column_type}_{data_type}_{len(algorithm_activity)}_{data_hash}_{timestamp_hash}_sadeh_{sadeh_axis_y_hash}_algo{algorithm_id}_choi{choi_activity_col}"

        # Check if results are already cached
        if cache_key in self._algorithm_cache:
            cached_results = self._algorithm_cache[cache_key]
            cached_sadeh = cached_results["sadeh"]
            cached_timestamps = cached_results.get("timestamps")

            # CRITICAL: Restore BOTH sadeh results AND timestamps from cache together
            # This guarantees they are aligned (they were saved together from the same load)
            if cached_timestamps is not None and len(cached_timestamps) == len(cached_sadeh):
                self.main_48h_sadeh_results = cached_sadeh
                # CRITICAL: Set BOTH timestamp stores to ensure consistency
                self.parent.main_48h_axis_y_timestamps = cached_timestamps
                self.parent.main_48h_sadeh_timestamps = cached_timestamps  # For apply_sleep_scoring_rules
                self.main_48h_axis_y_data = cached_results.get("axis_y_data")
                logger.debug(
                    "Using cached 48hr algorithm results: %d sadeh, %d timestamps",
                    len(cached_sadeh),
                    len(cached_timestamps),
                )
                self._extract_view_subset_from_main_results()
                return
            # Cache is incomplete or corrupted - invalidate and reload
            logger.warning(
                "Cache incomplete (timestamps=%s, sadeh=%s) - invalidating",
                len(cached_timestamps) if cached_timestamps else None,
                len(cached_sadeh),
            )
            del self._algorithm_cache[cache_key]

        logger.debug("Running algorithms on 48hr main data")

        # Get axis_y data specifically for Sadeh algorithm
        # CRITICAL: Always use _get_axis_y_data_for_sadeh() which validates alignment
        # between cached data and timestamps. Do NOT bypass with direct cache access.
        axis_y_timestamps = self.parent.main_48h_axis_y_timestamps
        if (
            self.main_48h_axis_y_data is not None
            and len(self.main_48h_axis_y_data) > 0
            and axis_y_timestamps is not None
            and len(axis_y_timestamps) == len(self.main_48h_axis_y_data)
        ):
            axis_y_data = self.main_48h_axis_y_data
            logger.debug("AXIS_Y CACHE HIT: Using cached axis_y data with %d points (timestamps: %d)", len(axis_y_data), len(axis_y_timestamps))
        else:
            # Cache invalid or missing - reload from unified loader
            logger.debug(
                "AXIS_Y CACHE MISS: data=%s, timestamps=%s - reloading",
                len(self.main_48h_axis_y_data) if self.main_48h_axis_y_data else None,
                len(axis_y_timestamps) if axis_y_timestamps else None,
            )
            axis_y_data = self.parent._get_axis_y_data_for_sadeh()
            self.main_48h_axis_y_data = axis_y_data
            logger.debug("AXIS_Y CACHE MISS: Loaded fresh axis_y data with %d points for Sadeh", len(axis_y_data) if axis_y_data else 0)

        # Run Choi algorithm (nonwear detection) with configured activity column using DI pattern
        choi_activity_column = self._get_choi_activity_column()
        logger.debug("Running Choi algorithm with activity_column: %s", choi_activity_column)
        choi_algorithm = self.parent.create_nonwear_algorithm(NonwearAlgorithm.CHOI_2011)
        choi_periods = choi_algorithm.detect(
            activity_data=algorithm_activity,
            timestamps=algorithm_timestamps if algorithm_timestamps else [],
            activity_column=choi_activity_column,
        )
        logger.debug("Choi algorithm returned %d periods", len(choi_periods))
        logger.debug("Choi algorithm completed - plotting handled by NonwearData system")

        # Validate Sadeh input data
        if axis_y_data:
            logger.debug("Sadeh algorithm using axis_y_data with %d points", len(axis_y_data))
        else:
            logger.error("Sadeh algorithm cannot run: axis_y_data is None or empty")

        # Run Sadeh algorithm with axis_y timestamps
        if self.parent.main_48h_axis_y_timestamps:
            if len(self.parent.main_48h_axis_y_timestamps) == len(axis_y_data):
                sadeh_timestamps = self.parent.main_48h_axis_y_timestamps
                logger.debug("Using axis_y-specific timestamps (%d points)", len(sadeh_timestamps))
            else:
                logger.error(
                    "Timestamp count mismatch: axis_y_timestamps=%d, axis_y_data=%d - cannot run Sadeh",
                    len(self.parent.main_48h_axis_y_timestamps),
                    len(axis_y_data),
                )
                self.main_48h_sadeh_results = []
                self.parent.main_48h_sadeh_timestamps = []  # Clear alongside results
                self._extract_view_subset_from_main_results()
                return
        else:
            logger.error("No axis_y timestamps available - cannot run Sadeh algorithm")
            self.main_48h_sadeh_results = []
            self.parent.main_48h_sadeh_timestamps = []  # Clear alongside results
            self._extract_view_subset_from_main_results()
            return

        # Use DI pattern to get sleep scoring algorithm
        algorithm = self.get_sleep_scoring_algorithm()
        logger.debug("Running sleep scoring algorithm: %s", algorithm.name)
        scoring_df = pd.DataFrame({"datetime": list(sadeh_timestamps), DefaultColumn.AXIS_Y: list(axis_y_data)})
        scored_df = algorithm.score(scoring_df)
        self.main_48h_sadeh_results = scored_df[AlgorithmOutputColumn.SLEEP_SCORE].tolist()
        # CRITICAL: Store sadeh timestamps WITH sadeh results - they must stay together
        self.parent.main_48h_sadeh_timestamps = list(sadeh_timestamps)
        logger.debug("Sleep scoring algorithm returned %d results", len(self.main_48h_sadeh_results) if self.main_48h_sadeh_results else 0)

        self._extract_view_subset_from_main_results()

        # Cache results WITH timestamps and axis_y_data (limit to 5)
        # CRITICAL: Store all three together so they stay aligned on cache restore
        if len(self._algorithm_cache) >= 5:
            oldest_key = next(iter(self._algorithm_cache))
            del self._algorithm_cache[oldest_key]

        self._algorithm_cache[cache_key] = {
            "sadeh": self.main_48h_sadeh_results,
            "timestamps": list(sadeh_timestamps),  # Store timestamps with results
            "axis_y_data": list(axis_y_data),  # Store axis_y_data with results
        }

    def _extract_view_subset_from_main_results(self) -> None:
        """Extract the current view subset from main 48hr algorithm results."""
        import numpy as np

        # DATA ALIGNMENT FIX: Use main_48h_sadeh_timestamps (stored WITH results)
        # instead of main_48h_axis_y_timestamps (which can differ in length)
        main_sadeh_timestamps = getattr(self.parent, "main_48h_sadeh_timestamps", None)

        if self.main_48h_sadeh_results is None or main_sadeh_timestamps is None:
            logger.debug("No main 48hr Sadeh results or sadeh timestamps to extract subset from")
            self.sadeh_results = []
            return

        # Validate alignment before proceeding
        if len(main_sadeh_timestamps) != len(self.main_48h_sadeh_results):
            logger.error(
                "DATA ALIGNMENT BUG: sadeh_timestamps=%d != sadeh_results=%d",
                len(main_sadeh_timestamps),
                len(self.main_48h_sadeh_results),
            )
            self.sadeh_results = []
            return

        # If we're in 48hr view, use full results
        if self.parent.current_view_hours == 48:
            self.sadeh_results = self.main_48h_sadeh_results
            return

        # For 24hr view, extract noon-to-noon subset
        if not self.timestamps:
            self.sadeh_results = []
            return

        # Use sadeh timestamps (guaranteed to match sadeh results)
        main_axis_y_timestamps = main_sadeh_timestamps

        # Performance optimization: Convert to unix timestamps for faster matching
        try:
            main_ts_array = np.array([ts.timestamp() if hasattr(ts, "timestamp") else ts for ts in main_axis_y_timestamps])
            current_ts_array = np.array([ts.timestamp() if hasattr(ts, "timestamp") else ts for ts in self.timestamps])

            # Map indices using searchsorted (assuming main_ts_array is sorted)
            indices = np.searchsorted(main_ts_array, current_ts_array)

            # Bound and verify matches (1 second tolerance)
            indices = np.clip(indices, 0, len(main_ts_array) - 1)

            # Check for actual closeness
            diffs = np.abs(main_ts_array[indices] - current_ts_array)
            valid_mask = diffs <= 1.0  # 1 second tolerance

            results_array = np.array(self.main_48h_sadeh_results)

            # Fill results
            mapped_results = results_array[indices]
            # Zero out (Wake) anything that didn't match within tolerance
            mapped_results[~valid_mask] = 0

            self.sadeh_results = mapped_results.tolist()

            missing_count = np.sum(~valid_mask)
            if missing_count > 0:
                logger.warning(f"SADEH ALIGNMENT: {missing_count}/{len(current_ts_array)} timestamps had no close match in main dataset")

        except Exception as e:
            logger.exception(f"Error during Sadeh alignment: {e}")
            self.sadeh_results = [0] * len(self.timestamps)

        # Verify alignment
        if len(self.sadeh_results) != len(self.timestamps):
            logger.error("Sadeh subset length mismatch: timestamps=%d, results=%d", len(self.timestamps), len(self.sadeh_results))

    def plot_choi_results(self, nonwear_periods: list[dict[str, Any]]) -> None:
        """Plot Choi nonwear periods as purple background regions (optimized)."""
        if not nonwear_periods or self.timestamps is None:
            return

        plot_item = self.plotItem
        if plot_item is None:
            return

        choi_brush = tuple(map(int, UIColors.CHOI_ALGORITHM_BRUSH.split(",")))
        choi_border = tuple(map(int, UIColors.CHOI_ALGORITHM_BORDER.split(",")))

        for period in nonwear_periods:
            start_time = self.timestamps[period["start_index"]].timestamp()
            end_time = self.timestamps[period["end_index"]].timestamp()

            region = pg.LinearRegionItem(
                [start_time, end_time],
                brush=pg.mkBrush(*choi_brush),
                pen=pg.mkPen(*choi_border, width=1),
                movable=False,
            )
            region.setZValue(-10)
            plot_item.addItem(region)

    # ========== Sleep Scoring Rule Methods ==========

    def apply_sleep_scoring_rules(self, main_sleep_period: SleepPeriod) -> None:
        """Apply onset/offset detection rules to selected marker set using injected rule."""
        selected_period = self.parent.get_selected_marker_period()
        if not selected_period or not selected_period.is_complete:
            logger.debug("apply_sleep_scoring_rules: No selected period")
            return

        # Use MAIN 48hr data for detection, not view subset
        # This ensures we find the correct onset/offset even if they fall outside current view
        main_sadeh = self.main_48h_sadeh_results
        # CRITICAL: Use main_48h_sadeh_timestamps which is set TOGETHER with sadeh_results
        # This guarantees they are aligned, unlike main_48h_axis_y_timestamps which can change
        main_timestamps = getattr(self.parent, "main_48h_sadeh_timestamps", None)

        if not main_sadeh or len(main_sadeh) == 0:
            logger.debug("apply_sleep_scoring_rules: main_48h_sadeh_results is empty")
            return

        if not main_timestamps or len(main_timestamps) != len(main_sadeh):
            # This should NEVER happen now that we store sadeh_timestamps with sadeh_results.
            # If it does, there's a bug in the algorithm manager.
            logger.error(
                "CRITICAL DATA ALIGNMENT BUG: timestamp/sadeh mismatch detected! "
                "timestamps=%s, sadeh=%s. "
                "main_48h_sadeh_timestamps should always match main_48h_sadeh_results.",
                len(main_timestamps) if main_timestamps else 0,
                len(main_sadeh),
            )
            return

        self.clear_sleep_onset_offset_markers()

        # Get sleep period detector instance
        detector = self.get_sleep_period_detector()

        # Convert period timestamps to datetime objects
        onset_ts = selected_period.onset_timestamp
        offset_ts = selected_period.offset_timestamp
        if onset_ts is None or offset_ts is None:
            logger.debug("apply_sleep_scoring_rules: Missing timestamps despite is_complete")
            return
        sleep_start_time = datetime.fromtimestamp(onset_ts)
        sleep_end_time = datetime.fromtimestamp(offset_ts)

        # Apply detector using MAIN 48hr data (timestamps match sadeh_results)
        onset_idx, offset_idx = detector.apply_rules(
            sleep_scores=main_sadeh,
            sleep_start_marker=sleep_start_time,
            sleep_end_marker=sleep_end_time,
            timestamps=main_timestamps,
        )

        # Create visual markers using main timestamps (they're datetime objects)
        if onset_idx is not None and onset_idx < len(main_timestamps):
            onset_ts = main_timestamps[onset_idx]
            # Convert datetime to Unix timestamp for plotting
            onset_unix = onset_ts.timestamp() if hasattr(onset_ts, "timestamp") else onset_ts
            self.create_sleep_onset_marker(onset_unix, detector)

        if offset_idx is not None and offset_idx < len(main_timestamps):
            offset_ts = main_timestamps[offset_idx]
            # Convert datetime to Unix timestamp for plotting
            offset_unix = offset_ts.timestamp() if hasattr(offset_ts, "timestamp") else offset_ts
            self.create_sleep_offset_marker(offset_unix, detector)

    def create_sleep_onset_marker(self, timestamp: float, detector: SleepPeriodDetector | None = None) -> None:
        """Create sleep onset marker with arrow and axis label."""
        custom_arrow_colors = getattr(self.parent, "custom_arrow_colors", {})
        onset_arrow_color = custom_arrow_colors.get(ArrowColorKey.ONSET, "#0066CC")

        arrow = pg.ArrowItem(
            pos=(timestamp, self.data_max_y * 0.88),
            angle=-90,
            headLen=15,
            headWidth=12,
            tailLen=25,
            tailWidth=3,
            pen=pg.mkPen(color=onset_arrow_color, width=2),
            brush=pg.mkBrush(color=onset_arrow_color),
        )
        arrow.setZValue(10)
        arrow.setVisible(True)

        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")

        # Get label from detector protocol if available
        if detector is not None:
            onset_label, _ = detector.get_marker_labels(time_str, "")
        else:
            onset_label = f"Sleep Onset at {time_str}\n3-minute rule applied"

        onset_text = pg.TextItem(
            text=onset_label,
            color=onset_arrow_color,
            anchor=(0.5, 1.0),
        )
        onset_text.setFont(pg.QtGui.QFont("Arial", 10, pg.QtGui.QFont.Weight.Bold))
        onset_text.setPos(timestamp, self.data_max_y * 0.85)
        onset_text.setZValue(10)
        onset_text.setVisible(True)

        plot_item = self.plotItem
        if plot_item is not None:
            plot_item.addItem(arrow)
            plot_item.addItem(onset_text)

        self.parent.sleep_rule_markers.extend([arrow, onset_text])

    def create_sleep_offset_marker(self, timestamp: float, detector: SleepPeriodDetector | None = None) -> None:
        """Create sleep offset marker with arrow and axis label."""
        custom_arrow_colors = getattr(self.parent, "custom_arrow_colors", {})
        offset_arrow_color = custom_arrow_colors.get(ArrowColorKey.OFFSET, "#FFA500")

        arrow = pg.ArrowItem(
            pos=(timestamp, self.data_max_y * 0.88),
            angle=-90,
            headLen=15,
            headWidth=12,
            tailLen=25,
            tailWidth=3,
            pen=pg.mkPen(color=offset_arrow_color, width=2),
            brush=pg.mkBrush(color=offset_arrow_color),
        )
        arrow.setZValue(10)
        arrow.setVisible(True)

        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")

        # Get label from detector protocol if available
        if detector is not None:
            _, offset_label = detector.get_marker_labels("", time_str)
        else:
            offset_label = f"Sleep Offset at {time_str}\n5-minute rule applied"

        offset_text = pg.TextItem(
            text=offset_label,
            color=offset_arrow_color,
            anchor=(0.5, 1.0),
        )
        offset_text.setFont(pg.QtGui.QFont("Arial", 10, pg.QtGui.QFont.Weight.Bold))
        offset_text.setPos(timestamp, self.data_max_y * 0.85)
        offset_text.setZValue(10)
        offset_text.setVisible(True)

        plot_item = self.plotItem
        if plot_item is not None:
            plot_item.addItem(arrow)
            plot_item.addItem(offset_text)

        self.parent.sleep_rule_markers.extend([arrow, offset_text])

    def clear_sleep_onset_offset_markers(self) -> None:
        """Clear sleep onset/offset markers from 3/5 rule."""
        plot_item = self.plotItem
        for marker in self.parent.sleep_rule_markers:
            if plot_item is not None:
                plot_item.removeItem(marker)
        self.parent.sleep_rule_markers.clear()

    # ========== Cache Management ==========

    def clear_algorithm_cache(self) -> None:
        """Clear the algorithm results cache."""
        self._algorithm_cache.clear()
        self._sleep_pattern_cache.clear()

    def get_algorithm_cache_info(self) -> dict[str, int]:
        """Get information about the current algorithm cache state."""
        return {
            "algorithm_cache_size": len(self._algorithm_cache),
            "sleep_pattern_cache_size": len(self._sleep_pattern_cache),
        }
