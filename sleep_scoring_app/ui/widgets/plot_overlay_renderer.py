#!/usr/bin/env python3
"""
Plot Overlay Renderer for Activity Plot Widget.

Manages all overlay rendering operations for the activity plot including:
- Nonwear period visualization (sensor and Choi algorithm)
- Choi algorithm overlay updates and caching
- Background region rendering
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import QTimer

from sleep_scoring_app.core.constants import ActivityDataPreference, NonwearAlgorithm, UIColors

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import NonwearPeriod
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


class PlotOverlayRenderer:
    """
    Manages overlay rendering for the activity plot widget.

    Responsibilities:
    - Render nonwear period overlays (sensor and Choi)
    - Manage Choi algorithm caching and updates
    - Create background region visualizations
    - Handle overlay color customization

    Data Access (ARCHITECTURE):
    - Reads data from parent ActivityPlotWidget (timestamps, axis_y_data, sadeh_results)
    - Visual Qt objects (regions, plot items) remain on parent widget
    - Widget-local state (nonwear_data, caches) remain on parent
    """

    def __init__(self, parent: ActivityPlotWidget) -> None:
        """Initialize the plot overlay renderer."""
        self.parent = parent
        self._choi_cache: dict[str, dict[str, Any]] = {}
        logger.info("PlotOverlayRenderer initialized")

    @property
    def _timestamps(self) -> list | None:
        """Get timestamps from parent widget."""
        return self.parent.timestamps

    @property
    def _sadeh_results(self) -> list | None:
        """Get Sadeh results from parent widget."""
        return self.parent.sadeh_results

    @property
    def _axis_y_data(self) -> list[float]:
        """Get axis Y data from parent widget."""
        return self.parent.axis_y_data

    @property
    def _current_filename(self) -> str | None:
        """Get current filename from parent widget."""
        return self.parent.current_filename

    def _get_choi_activity_column(self) -> ActivityDataPreference:
        """Get the Choi activity column from config."""
        try:
            result = self.parent.get_choi_activity_column()
            return ActivityDataPreference(result) if not isinstance(result, ActivityDataPreference) else result
        except Exception as e:
            logger.debug("Could not get choi_axis from config, using default: %s", e)
        return ActivityDataPreference.VECTOR_MAGNITUDE

    # ========== Nonwear Data Management ==========

    def set_nonwear_data(self, nonwear_data) -> None:
        """
        Set nonwear data using immutable NonwearData structure.

        Args:
            nonwear_data: NonwearData object with immutable sensor/choi data and masks

        """
        from sleep_scoring_app.core.nonwear_data import NonwearData

        if not isinstance(nonwear_data, NonwearData):
            logger.error("Expected NonwearData object, got %s", type(nonwear_data))
            return

        logger.info(
            "Setting nonwear data: %d sensor periods, %d choi periods",
            len(nonwear_data.sensor_periods),
            len(nonwear_data.choi_periods),
        )

        self.clear_nonwear_visualizations()
        self.parent.nonwear_data = nonwear_data

        logger.info(
            "Stored nonwear data: %d sensor minutes, %d choi minutes nonwear",
            sum(nonwear_data.sensor_mask),
            sum(nonwear_data.choi_mask),
        )

        logger.debug("Sensor periods: %s", [f"{p.start_time}-{p.end_time}" for p in nonwear_data.sensor_periods[:3]])
        logger.debug("Choi periods: %s", [f"{p.start_time}-{p.end_time}" for p in nonwear_data.choi_periods[:3]])

        logger.debug("About to plot nonwear periods")
        self.plot_nonwear_periods()
        logger.debug("Finished plotting nonwear periods")

    def clear_nonwear_visualizations(self) -> None:
        """Clear all nonwear period visualizations."""
        for region in self.parent.nonwear_regions:
            self.parent.plotItem.removeItem(region)
        self.parent.nonwear_regions = []

    # ========== Nonwear Period Plotting ==========

    def plot_nonwear_periods(self) -> None:
        """Plot nonwear periods using the same per-minute data as table/mouseover."""
        for region in self.parent.nonwear_regions:
            self.parent.plotItem.removeItem(region)
        self.parent.nonwear_regions.clear()

        logger.info("=== PLOT_NONWEAR_PERIODS CALLED ===")

        if not self._timestamps:
            logger.debug("No timestamps available for nonwear visualization")
            return

        if not self.parent.nonwear_data:
            logger.warning("No nonwear_data available - nonwear visualization not possible")
            return

        logger.info(
            "nonwear_data exists with %d sensor periods, %d choi periods",
            len(self.parent.nonwear_data.sensor_periods),
            len(self.parent.nonwear_data.choi_periods),
        )

        nonwear_sensor_per_minute = self.parent.get_nonwear_sensor_results_per_minute()
        choi_per_minute = self.parent.get_choi_results_per_minute()

        logger.info("Got per-minute data: %d sensor values, %d choi values", len(nonwear_sensor_per_minute), len(choi_per_minute))
        logger.info("Sensor nonwear minutes: %d, Choi nonwear minutes: %d", sum(nonwear_sensor_per_minute), sum(choi_per_minute))

        colors = self._get_nonwear_colors()

        self._plot_nonwear_periods(
            nonwear_sensor_per_minute,
            choi_per_minute,
            colors["sensor_brush"],
            colors["sensor_border"],
            colors["choi_brush"],
            colors["choi_border"],
            colors["overlap_brush"],
            colors["overlap_border"],
        )

        logger.debug("Finished plotting nonwear periods, created %d regions", len(self.parent.nonwear_regions))

    def _get_nonwear_colors(self) -> dict[str, tuple]:
        """Get nonwear colors from custom settings or defaults."""
        custom_nonwear_colors = getattr(self.parent, "custom_nonwear_colors", {})

        def parse_hex_color(key: str, default: str, alpha: int) -> tuple:
            if key in custom_nonwear_colors:
                hex_color = custom_nonwear_colors[key].lstrip("#")
                return (*tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4)), alpha)
            return tuple(map(int, default.split(",")))

        return {
            "sensor_brush": parse_hex_color("sensor_brush", UIColors.NONWEAR_SENSOR_BRUSH, 70),
            "sensor_border": parse_hex_color("sensor_border", UIColors.NONWEAR_SENSOR_BORDER, 150),
            "choi_brush": parse_hex_color("choi_brush", UIColors.CHOI_ALGORITHM_BRUSH, 70),
            "choi_border": parse_hex_color("choi_border", UIColors.CHOI_ALGORITHM_BORDER, 150),
            "overlap_brush": parse_hex_color("overlap_brush", UIColors.NONWEAR_OVERLAP_BRUSH, 100),
            "overlap_border": parse_hex_color("overlap_border", UIColors.NONWEAR_OVERLAP_BORDER, 180),
        }

    def _plot_nonwear_periods(
        self,
        sensor_mask,
        choi_mask,
        sensor_brush,
        sensor_border,
        choi_brush,
        choi_border,
        overlap_brush,
        overlap_border,
    ) -> None:
        """Plot nonwear periods using numpy operations."""
        n_timestamps = len(self._timestamps)
        if len(sensor_mask) < n_timestamps:
            sensor_mask = sensor_mask + [0] * (n_timestamps - len(sensor_mask))
        if len(choi_mask) < n_timestamps:
            choi_mask = choi_mask + [0] * (n_timestamps - len(choi_mask))

        sensor_array = np.array(sensor_mask[:n_timestamps], dtype=bool)
        choi_array = np.array(choi_mask[:n_timestamps], dtype=bool)

        overlap_array = sensor_array & choi_array
        sensor_only_array = sensor_array & ~choi_array
        choi_only_array = choi_array & ~sensor_array

        self._plot_contiguous_periods(overlap_array, overlap_brush, overlap_border, "overlap")
        self._plot_contiguous_periods(sensor_only_array, sensor_brush, sensor_border, "sensor")
        self._plot_contiguous_periods(choi_only_array, choi_brush, choi_border, "choi")

    def _plot_contiguous_periods(self, mask_array, brush, border, period_type: str) -> None:
        """Find and plot contiguous periods from a boolean mask array."""
        if not mask_array.any():
            return

        padded = np.pad(mask_array, (1, 1), mode="constant", constant_values=False)
        diff = np.diff(padded.astype(int))

        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0] - 1

        logger.debug("Found %d %s periods", len(starts), period_type)

        for start_idx, end_idx in zip(starts, ends, strict=False):
            if start_idx < len(self._timestamps) and end_idx < len(self._timestamps):
                self._create_period_region(start_idx, end_idx, brush, border)

    def _create_period_region(self, start_idx: int, end_idx: int, brush, border) -> None:
        """Create visualization region for a period."""
        if start_idx is not None and start_idx < len(self._timestamps) and end_idx < len(self._timestamps):
            start_ts = self._timestamps[start_idx].timestamp()
            end_ts = self._timestamps[end_idx].timestamp()

            logger.debug(
                "Creating visual region: indices %d-%d, timestamps %s-%s",
                start_idx,
                end_idx,
                self._timestamps[start_idx].strftime("%H:%M"),
                self._timestamps[end_idx].strftime("%H:%M"),
            )

            region = self.add_background_region(start_ts, end_ts, brush, border)
            self.parent.nonwear_regions.append(region)
        elif start_idx is not None:
            logger.warning(
                "Invalid period indices: start=%s, end=%s, timestamps_length=%d",
                start_idx,
                end_idx,
                len(self._timestamps) if self._timestamps else 0,
            )

    def add_background_region(
        self,
        start_time,
        end_time,
        color=(220, 53, 69, 40),
        border_color=(220, 53, 69, 120),
    ) -> pg.LinearRegionItem:
        """Add a background region (e.g., for nonwear periods)."""
        region = pg.LinearRegionItem(
            [start_time, end_time],
            brush=pg.mkBrush(*color),
            pen=pg.mkPen(*border_color[:3], width=1),
            movable=False,
        )
        region.setZValue(-10)
        self.parent.plotItem.addItem(region)
        return region

    # ========== Choi Overlay Updates ==========

    def update_choi_overlay_only(self, new_activity_data: list[float]) -> None:
        """Recalculate Choi algorithm with new data while preserving Sadeh algorithm state."""
        logger.debug("Updating Choi overlay with new activity data")

        if not new_activity_data or not self._timestamps:
            logger.warning("Cannot update Choi overlay: missing activity data or timestamps")
            return

        logger.debug("Updating Choi overlay with %d data points (preserving Sadeh state)", len(new_activity_data))

        if self.restore_choi_from_cache(new_activity_data):
            logger.debug("Successfully used cached Choi results")
            return

        try:
            from sleep_scoring_app.core.nonwear_data import ActivityDataView, NonwearData

            # Algorithm cache is widget-local (for perf), preserved across Choi updates
            preserved_algorithm_cache = getattr(self.parent, "_algorithm_cache", {}).copy()

            current_filename = self._current_filename or "unknown"
            new_activity_view = ActivityDataView.create(
                timestamps=list(self._timestamps),
                counts=new_activity_data,
                filename=current_filename,
            )

            raw_sensor_periods = []
            if self.parent.nonwear_data:
                raw_sensor_periods = list(self.parent.nonwear_data.sensor_periods)

            new_nonwear_data = NonwearData.create_for_activity_view(
                activity_view=new_activity_view,
                raw_sensor_periods=raw_sensor_periods,
                nonwear_service=None,
                choi_activity_column=self._get_choi_activity_column(),
            )

            self.clear_nonwear_visualizations()
            self.parent.nonwear_data = new_nonwear_data

            # Restore algorithm cache (sadeh_results in store, not affected)
            self.parent._algorithm_cache = preserved_algorithm_cache

            logger.debug("Plotting updated Choi overlay")
            self.plot_nonwear_periods()

            self._update_choi_cache_key(new_activity_data)

            logger.info("Successfully updated Choi overlay with new data (Sadeh state preserved)")

        except Exception as e:
            logger.exception("Error updating Choi overlay: %s", e)
            self.parent.error_occurred.emit(f"Failed to update nonwear overlay: {e}")
            if self.parent.nonwear_data:
                try:
                    self.plot_nonwear_periods()
                except Exception as restore_error:
                    logger.exception("Failed to restore previous nonwear visualization: %s", restore_error)

    def update_choi_overlay_async(self, new_activity_data: list[float]) -> None:
        """Asynchronously recalculate Choi algorithm with new data."""
        logger.debug("Starting async Choi overlay update")

        if not new_activity_data or not self._timestamps:
            logger.warning("Cannot update Choi overlay async: missing activity data or timestamps")
            return

        logger.debug("Starting async Choi overlay update with %d data points", len(new_activity_data))

        if self.restore_choi_from_cache(new_activity_data):
            logger.debug("Used cached Choi results for immediate update")
            return

        # CRITICAL: Capture ALL data at scheduling time, not execution time.
        # If user switches dates quickly, self._timestamps would change
        # between scheduling and execution, causing data mismatch.
        captured_timestamps = list(self._timestamps)
        captured_filename = self._current_filename or "unknown"
        captured_sensor_periods = []
        if self.parent.nonwear_data:
            captured_sensor_periods = list(self.parent.nonwear_data.sensor_periods)
        captured_choi_column = self._get_choi_activity_column()

        def compute_choi_async():
            try:
                from sleep_scoring_app.core.nonwear_data import ActivityDataView, NonwearData

                new_activity_view = ActivityDataView.create(
                    timestamps=captured_timestamps,
                    counts=new_activity_data,
                    filename=captured_filename,
                )

                return NonwearData.create_for_activity_view(
                    activity_view=new_activity_view,
                    raw_sensor_periods=captured_sensor_periods,
                    nonwear_service=None,
                    choi_activity_column=captured_choi_column,
                )
            except Exception as e:
                logger.exception("Error in async Choi computation: %s", e)
                return None

        def on_computation_complete(new_nonwear_data):
            if new_nonwear_data is None:
                logger.error("Async Choi computation failed")
                self.parent.error_occurred.emit("Async nonwear computation failed")
                return

            # Verify we're still on the same data before applying results
            # If user navigated away, discard stale results
            # Use fast comparison: check length and first/last timestamps only (O(1) not O(n))
            current_timestamps = self._timestamps  # From Redux store
            if current_timestamps:
                curr_len = len(current_timestamps)
                capt_len = len(captured_timestamps)
                if curr_len != capt_len or (
                    curr_len > 0 and (current_timestamps[0] != captured_timestamps[0] or current_timestamps[-1] != captured_timestamps[-1])
                ):
                    logger.info("Discarding stale Choi results - user navigated to different date")
                    return

            try:
                preserved_algorithm_cache = getattr(self.parent, "_algorithm_cache", {}).copy()

                self.clear_nonwear_visualizations()
                self.parent.nonwear_data = new_nonwear_data

                self.parent._algorithm_cache = preserved_algorithm_cache

                self.plot_nonwear_periods()
                self._update_choi_cache_key(new_activity_data)

                logger.info("Async Choi overlay update completed successfully")
            except Exception as e:
                logger.exception("Error applying async Choi results: %s", e)
                self.parent.error_occurred.emit(f"Failed to apply nonwear results: {e}")

        def delayed_computation():
            result = compute_choi_async()
            on_computation_complete(result)

        QTimer.singleShot(0, delayed_computation)
        logger.debug("Scheduled async Choi computation")

    # ========== Choi Cache Management ==========

    def _update_choi_cache_key(self, new_activity_data: list[float]) -> None:
        """Update cache key for Choi results while preserving Sadeh cache."""
        try:
            choi_data_hash = hashlib.md5(str(new_activity_data).encode()).hexdigest()[:8]
            choi_cache_key = f"choi_{len(new_activity_data)}_{choi_data_hash}"

            if self.parent.nonwear_data:
                if len(self._choi_cache) >= 3:
                    oldest_key = next(iter(self._choi_cache))
                    del self._choi_cache[oldest_key]

                self._choi_cache[choi_cache_key] = {
                    "choi_periods": list(self.parent.nonwear_data.choi_periods),
                    "choi_mask": list(self.parent.nonwear_data.choi_mask),
                }

                logger.debug("Cached Choi results with key: %s", choi_cache_key)
        except Exception as e:
            logger.exception("Error updating Choi cache key: %s", e)

    def restore_choi_from_cache(self, activity_data: list[float]) -> bool:
        """Attempt to restore Choi results from cache for quick switching."""
        try:
            choi_data_hash = hashlib.md5(str(activity_data).encode()).hexdigest()[:8]
            choi_cache_key = f"choi_{len(activity_data)}_{choi_data_hash}"

            if choi_cache_key in self._choi_cache:
                cached_data = self._choi_cache[choi_cache_key]

                preserved_algorithm_cache = getattr(self.parent, "_algorithm_cache", {}).copy()

                from sleep_scoring_app.core.nonwear_data import ActivityDataView, NonwearData

                current_filename = self._current_filename or "unknown"
                activity_view = ActivityDataView.create(
                    timestamps=list(self._timestamps),
                    counts=activity_data,
                    filename=current_filename,
                )

                raw_sensor_periods = []
                if self.parent.nonwear_data:
                    raw_sensor_periods = list(self.parent.nonwear_data.sensor_periods)

                new_nonwear_data = NonwearData(
                    sensor_periods=tuple(raw_sensor_periods),
                    choi_periods=tuple(cached_data["choi_periods"]),
                    sensor_mask=tuple(getattr(self.parent.nonwear_data, "sensor_mask", [])) if self.parent.nonwear_data else (),
                    choi_mask=tuple(cached_data["choi_mask"]),
                    activity_view=activity_view,
                )

                self.clear_nonwear_visualizations()
                self.parent.nonwear_data = new_nonwear_data

                self.parent._algorithm_cache = preserved_algorithm_cache

                self.plot_nonwear_periods()

                logger.debug("Successfully restored Choi results from cache: %s", choi_cache_key)
                return True
        except Exception as e:
            logger.exception("Error restoring Choi results from cache: %s", e)

        return False

    def clear_choi_cache(self) -> None:
        """Clear the Choi algorithm results cache."""
        self._choi_cache.clear()
        logger.debug("Cleared Choi algorithm cache")

    def get_choi_cache_info(self) -> dict[str, int]:
        """Get information about the current Choi cache state."""
        total_entries = sum(len(data.get("choi_periods", [])) for data in self._choi_cache.values())
        return {"cache_size": len(self._choi_cache), "total_entries": total_entries}

    def validate_choi_overlay_state(self) -> bool:
        """Validate the current Choi overlay state for consistency."""
        try:
            if not self.parent.nonwear_data:
                logger.debug("No nonwear data available for validation")
                return False

            if self._sadeh_results:
                if not isinstance(self._sadeh_results, list):
                    logger.error("Sadeh results corrupted: not a list")
                    return False
                logger.debug("Sadeh results validated: %d entries", len(self._sadeh_results))

            if not self.parent.nonwear_data.choi_mask or not self.parent.nonwear_data.choi_periods:
                logger.error("Choi overlay data incomplete")
                return False

            if self._timestamps:
                expected_length = len(self._timestamps)
                choi_mask_length = len(self.parent.nonwear_data.choi_mask)

                if choi_mask_length != expected_length:
                    logger.warning("Choi mask length mismatch: expected %d, got %d", expected_length, choi_mask_length)

            logger.debug("Choi overlay state validation passed")
            return True
        except Exception as e:
            logger.exception("Error validating Choi overlay state: %s", e)
            return False

    def convert_choi_results_to_periods(self) -> list[NonwearPeriod]:
        """Convert dynamically generated Choi results to NonwearPeriod format."""
        periods = []
        if not self._axis_y_data or not self._timestamps:
            return periods

        try:
            choi_algorithm = self.parent.create_nonwear_algorithm(NonwearAlgorithm.CHOI_2011)
            periods = choi_algorithm.detect(activity_data=self._axis_y_data, timestamps=self._timestamps)
        except Exception as e:
            logger.exception("Error converting Choi results to periods: %s", e)

        return periods
