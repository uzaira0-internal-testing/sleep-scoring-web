#!/usr/bin/env python3
"""
Marker Table Manager for Sleep Scoring Application.

Manages marker table display, updates, click handlers, and data fetching for marker tables.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtGui import QColor

from sleep_scoring_app.core.constants import MarkerEndpoint, SleepMarkerEndpoint, TableDimensions
from sleep_scoring_app.ui.utils.table_helpers import update_marker_table, update_table_sleep_algorithm_header

if TYPE_CHECKING:
    from collections.abc import Callable

    from sleep_scoring_app.ui.protocols import (
        AppStateInterface,
        MainWindowProtocol,
        MarkerOperationsInterface,
        NavigationInterface,
        ServiceContainer,
    )
    from sleep_scoring_app.ui.store import UIStore

logger = logging.getLogger(__name__)


# TODO(refactor): pattern-violation Not a QWidget (coordinator class) with 12 direct service
# calls. Consider extracting service interactions into a dedicated connector.
class MarkerTableManager:
    """
    Manages marker table operations for the main window.

    Responsibilities:
    - Update onset/offset marker tables with data
    - Handle custom table colors
    - Update pop-out windows when visible
    - Manage table click handlers
    """

    def __init__(
        self,
        store: UIStore,
        navigation: NavigationInterface,
        marker_ops: MarkerOperationsInterface,
        app_state: AppStateInterface,
        services: ServiceContainer,
        parent: MainWindowProtocol,
        get_sleep_algorithm_name: Callable[[], str] | None = None,
    ) -> None:
        """
        Initialize the marker table manager.

        Args:
            store: The UI store
            marker_ops: Marker operations interface
            app_state: App state coordination interface
            services: Service container
            parent: Main window (still needed for some Qt-level access for now)

        """
        self.store = store
        self.navigation = navigation
        self.marker_ops = marker_ops
        self.app_state = app_state
        self.services = services
        self.main_window = parent
        self.parent = parent
        self._get_sleep_algorithm_name = get_sleep_algorithm_name

        self._cached_algorithm_name: str | None = None
        logger.info("MarkerTableManager initialized with decoupled interfaces")

    def get_current_sleep_algorithm_name(self) -> str:
        """
        Get the display name of the currently configured sleep/wake algorithm.

        Retrieves the algorithm name from the config via the AlgorithmService.

        Returns:
            Display name of the algorithm (e.g., "Sadeh", "Cole-Kripke")

        """
        try:
            if self._get_sleep_algorithm_name:
                name = self._get_sleep_algorithm_name()
                if name:
                    return name

            # Fall back to getting it from the plot widget via services
            if self.services.plot_widget and self.services.plot_widget.algorithm_manager:
                algorithm = self.services.plot_widget.algorithm_manager.get_sleep_scoring_algorithm()
                # SleepScoringAlgorithm Protocol guarantees name property exists
                if algorithm:
                    return algorithm.name

        except Exception as e:
            logger.warning("Failed to get sleep algorithm name: %s", e)

        return "Sadeh"

    def update_table_headers_for_algorithm(self, force: bool = False) -> None:
        """
        Update the table column headers to reflect the current sleep algorithm.

        Should be called when the algorithm is changed in study settings.

        Args:
            force: If True, bypass the cache check and always update headers.
                   Use this when you know the algorithm just changed.

        """
        algorithm_name = self.get_current_sleep_algorithm_name()

        # Only update if the algorithm name has changed (unless forced)
        if not force and algorithm_name == self._cached_algorithm_name:
            return

        self._cached_algorithm_name = algorithm_name
        logger.info("Updating table headers for algorithm: %s (force=%s)", algorithm_name, force)

        # Update onset table header via main window references
        if self.main_window.onset_table:
            update_table_sleep_algorithm_header(self.main_window.onset_table, algorithm_name)

        # Update offset table header
        if self.main_window.offset_table:
            update_table_sleep_algorithm_header(self.main_window.offset_table, algorithm_name)

    def update_marker_tables(self, onset_data: list, offset_data: list) -> None:
        """Update the data tables with surrounding marker information."""
        logger.debug(f"Updating marker tables: onset_data={len(onset_data)} rows, offset_data={len(offset_data)} rows")

        # Store the data for use by click handlers via main window reference
        self.main_window._onset_table_data = onset_data
        self.main_window._offset_table_data = offset_data

        # Get custom table colors if they exist via services interface
        pw = self.services.plot_widget
        custom_table_colors = getattr(pw, "custom_table_colors", None) if pw else None

        # Use custom colors if available, otherwise defaults
        if custom_table_colors and "onset_bg" in custom_table_colors:
            onset_bg = QColor(custom_table_colors["onset_bg"])
        else:
            onset_bg = QColor(TableDimensions.ONSET_MARKER_BACKGROUND)

        if custom_table_colors and "onset_fg" in custom_table_colors:
            onset_fg = QColor(custom_table_colors["onset_fg"])
        else:
            onset_fg = QColor(TableDimensions.ONSET_MARKER_FOREGROUND)

        if custom_table_colors and "offset_bg" in custom_table_colors:
            offset_bg = QColor(custom_table_colors["offset_bg"])
        else:
            offset_bg = QColor(TableDimensions.OFFSET_MARKER_BACKGROUND)

        if custom_table_colors and "offset_fg" in custom_table_colors:
            offset_fg = QColor(custom_table_colors["offset_fg"])
        else:
            offset_fg = QColor(TableDimensions.OFFSET_MARKER_FOREGROUND)

        # Update tables via main window references
        update_marker_table(self.main_window.onset_table, onset_data, onset_bg, onset_fg, custom_table_colors)
        update_marker_table(self.main_window.offset_table, offset_data, offset_bg, offset_fg, custom_table_colors)

        # Update pop-out windows if they exist and are visible
        self._update_popout_windows()

    def _update_popout_windows(self) -> None:
        """Update pop-out windows with full 48-hour data if visible."""
        # Guard: analysis_tab may not exist via services yet
        tab = getattr(self.main_window, "analysis_tab", None)
        if tab is None:
            return

        # PERFORMANCE: Skip pop-out updates during active drag
        pw = self.services.plot_widget
        if pw and getattr(pw, "_marker_drag_in_progress", False):
            return

        # Update onset pop-out window
        if tab.onset_popout_window:
            if tab.onset_popout_window.isVisible():
                self._update_onset_popout()

        # Update offset pop-out window
        if tab.offset_popout_window:
            if tab.offset_popout_window.isVisible():
                self._update_offset_popout()

    def _update_onset_popout(self) -> None:
        """Update onset/start pop-out window with full 48-hour data (works for both sleep and nonwear)."""
        from sleep_scoring_app.core.constants import MarkerCategory

        # Get the current onset/start marker timestamp for highlighting
        onset_timestamp = None
        pw = self.services.plot_widget
        if pw:
            active_category = pw.get_active_marker_category()
            if active_category == MarkerCategory.NONWEAR:
                selected_period = pw.get_selected_nonwear_period()
                if selected_period and selected_period.start_timestamp:
                    onset_timestamp = selected_period.start_timestamp
            else:
                selected_period = pw.get_selected_marker_period()
                if selected_period and selected_period.onset_timestamp:
                    onset_timestamp = selected_period.onset_timestamp

        # Reload full 2880 rows with updated marker position
        full_onset_data = self.get_full_48h_data_for_popout(marker_timestamp=onset_timestamp)
        tab = self.main_window.analysis_tab
        tab.onset_popout_window.update_table_data(full_onset_data)

        # Scroll to the marker position
        if onset_timestamp is not None:
            for row_idx, row_data in enumerate(full_onset_data):
                if row_data.get("is_marker", False):
                    tab.onset_popout_window.scroll_to_row(row_idx)
                    break

        logger.debug(f"Updated onset pop-out window with {len(full_onset_data)} rows (full 48h period)")

    def _update_offset_popout(self) -> None:
        """Update offset/end pop-out window with full 48-hour data (works for both sleep and nonwear)."""
        from sleep_scoring_app.core.constants import MarkerCategory

        # Get the current offset/end marker timestamp for highlighting
        offset_timestamp = None
        pw = self.services.plot_widget
        if pw:
            active_category = pw.get_active_marker_category()
            if active_category == MarkerCategory.NONWEAR:
                selected_period = pw.get_selected_nonwear_period()
                if selected_period and selected_period.end_timestamp:
                    offset_timestamp = selected_period.end_timestamp
            else:
                selected_period = pw.get_selected_marker_period()
                if selected_period and selected_period.offset_timestamp:
                    offset_timestamp = selected_period.offset_timestamp

        # Reload full 2880 rows with updated marker position
        full_offset_data = self.get_full_48h_data_for_popout(marker_timestamp=offset_timestamp)
        tab = self.main_window.analysis_tab
        tab.offset_popout_window.update_table_data(full_offset_data)

        # Scroll to the marker position
        if offset_timestamp is not None:
            for row_idx, row_data in enumerate(full_offset_data):
                if row_data.get("is_marker", False):
                    tab.offset_popout_window.scroll_to_row(row_idx)
                    break

        logger.debug(f"Updated offset pop-out window with {len(full_offset_data)} rows (full 48h period)")

    def move_marker_from_table_click(self, marker_type: str, row: int) -> None:
        """
        Move a marker based on table row click.

        This method checks the active marker category and moves either sleep or nonwear markers.

        Args:
            marker_type: "onset" or "offset" (mapped to "start"/"end" for nonwear)
            row: The row index that was clicked (in the visible table, not the full data)

        """
        from sleep_scoring_app.core.constants import MarkerCategory

        try:
            # Check if we have plot widget and it's ready
            pw = self.services.plot_widget
            if not pw:
                logger.warning("Plot widget not available for marker movement")
                return

            # Get the appropriate table container (stores data and visible offset)
            if marker_type == SleepMarkerEndpoint.ONSET:
                table_container = getattr(self.main_window, "onset_table", None)
            else:
                table_container = getattr(self.main_window, "offset_table", None)

            if not table_container:
                logger.warning(f"No table container available for {marker_type}")
                return

            # Get data and visible offset from the table container
            table_data = getattr(table_container, "_table_data", None)
            visible_start_idx = getattr(table_container, "_visible_start_idx", 0)

            if not table_data:
                logger.warning(f"No data available in {marker_type} table container")
                return

            # Calculate actual data index from table row + visible offset
            data_idx = visible_start_idx + row

            if data_idx >= len(table_data):
                logger.warning(f"Data index {data_idx} out of range for {marker_type} table (len={len(table_data)})")
                return

            # Get the row data using the corrected index
            row_data = table_data[data_idx]

            # Check if this is the marker row itself (no-op)
            if row_data.get("is_marker", False):
                logger.debug(f"Clicked on current {marker_type} marker row - no movement needed")
                return

            # Extract timestamp from the row
            if "timestamp" in row_data:
                # Direct timestamp available
                target_timestamp = row_data["timestamp"]
            elif "time" in row_data:
                # Need to parse time string and find corresponding timestamp
                time_str = row_data["time"]

                # Get current date and timestamps from plot
                if not pw.timestamps:
                    logger.warning("No timestamps available in plot widget")
                    return

                # Find matching timestamp by time string
                target_timestamp = self.main_window._find_timestamp_by_time_string(time_str)
                if target_timestamp is None:
                    logger.warning(f"Could not find timestamp for time {time_str}")
                    return
            else:
                logger.warning(f"No timestamp information in row data: {row_data}")
                return

            # Check active marker category to determine which type of marker to move
            active_category = pw.get_active_marker_category()

            if active_category == MarkerCategory.NONWEAR:
                # Move nonwear marker
                # Map onset/offset to start/end for nonwear markers
                nonwear_marker_type = MarkerEndpoint.START if marker_type == SleepMarkerEndpoint.ONSET else MarkerEndpoint.END

                selected_period = pw.marker_renderer.get_selected_nonwear_period()
                period_slot = selected_period.marker_index if selected_period else None

                if not selected_period:
                    logger.warning("No nonwear period selected to move marker for")
                    return

                logger.debug(f"Moving nonwear {nonwear_marker_type} marker for period {period_slot}")

                success = pw.move_nonwear_marker_to_timestamp(nonwear_marker_type, target_timestamp, period_slot)

                if success:
                    logger.info(f"Successfully moved nonwear {nonwear_marker_type} marker for period {period_slot} to row {row}")
                else:
                    logger.warning(f"Failed to move nonwear {nonwear_marker_type} marker for period {period_slot} to row {row}")

            else:
                # Move sleep marker (default behavior)
                selected_period = pw.get_selected_marker_period()
                period_slot = None

                if selected_period:
                    # Use the marker_index from the selected period
                    period_slot = selected_period.marker_index
                    logger.debug(f"Moving {marker_type} marker for period {period_slot} ({selected_period.marker_type.value})")

                # Move the marker to the target timestamp
                success = pw.move_marker_to_timestamp(marker_type, target_timestamp, period_slot)

                if success:
                    logger.info(f"Successfully moved {marker_type} marker for period {period_slot} to row {row}")
                    # Auto-save after successful movement
                    self.marker_ops.auto_save_current_markers()
                else:
                    logger.warning(f"Failed to move {marker_type} marker for period {period_slot} to row {row}")

        except Exception as e:
            logger.error(f"Error moving {marker_type} marker from table click: {e}", exc_info=True)

    def get_marker_data_cached(self, marker_timestamp: float, cached_idx: int | None = None) -> list[dict[str, Any]]:
        """Get marker surrounding data using cached index for better performance during drag operations."""
        surrounding_data = []

        # ALWAYS use full 48hr data for tables, not the filtered view data
        pw = self.services.plot_widget
        if not pw:
            return surrounding_data

        full_48h_timestamps = getattr(pw, "main_48h_timestamps", None)
        full_48h_activity = getattr(pw, "main_48h_activity", None)

        # Get axis_y data (unified loader handles caching automatically)
        full_48h_axis_y = None

        # Check if plot widget has cached axis_y data
        if pw.main_48h_axis_y_data:
            full_48h_axis_y = pw.main_48h_axis_y_data
            logger.info("TABLE: Using cached axis_y data: %d points", len(full_48h_axis_y))
        else:
            # Load axis_y data via unified loader via main window callback
            logger.info("TABLE: Loading fresh axis_y data via unified loader (cache was cleared or empty)")
            full_48h_axis_y = self.main_window._get_axis_y_data_for_sadeh()

        if not full_48h_axis_y:
            logger.error("TABLE: No axis_y data available!")

        # Try to load Vector Magnitude data
        full_48h_vm = self._load_vector_magnitude_data()

        # Log VM data availability
        logger.debug("Vector magnitude data length: %d", len(full_48h_vm) if full_48h_vm else 0)

        # If no 48hr data, fall back to current view data (for compatibility)
        if full_48h_timestamps is None or full_48h_activity is None:
            full_48h_timestamps = pw.timestamps
            full_48h_activity = pw.activity_data

        if not full_48h_timestamps:
            return surrounding_data

        # Find index in full 48hr data directly
        if cached_idx is not None and 0 <= cached_idx < len(full_48h_timestamps):
            marker_idx = cached_idx
        else:
            marker_idx = self.main_window._find_index_in_timestamps(full_48h_timestamps, marker_timestamp)
            if marker_idx is not None:
                self.main_window._marker_index_cache[marker_timestamp] = marker_idx

        if marker_idx is None:
            return surrounding_data

        # Log marker position
        target_dt = datetime.fromtimestamp(marker_timestamp)
        logger.debug("Marker at %s, index %d", target_dt.strftime("%Y-%m-%d %H:%M:%S"), marker_idx)

        # Get sleep/wake algorithm results - use full 48hr results
        sleep_score_results = getattr(pw, "main_48h_sadeh_results", getattr(pw, "sadeh_results", []))

        # If no sleep score results available, trigger algorithm calculation
        if not sleep_score_results:
            logger.debug("No sleep score results available, triggering algorithm calculation")
            try:
                pw.plot_algorithms()
                sleep_score_results = getattr(pw, "main_48h_sadeh_results", getattr(pw, "sadeh_results", []))
            except Exception as e:
                logger.exception("Failed to run algorithms for table: %s", e)

        # PlotWidgetProtocol guarantees these methods exist
        choi_results = pw.get_choi_results_per_minute()
        nonwear_sensor_results = pw.get_nonwear_sensor_results_per_minute()

        # Get elements around marker (±100 minutes = 200 rows max)
        elements_around_marker = 100
        start_idx = max(0, marker_idx - elements_around_marker)
        end_idx = min(len(full_48h_timestamps), marker_idx + elements_around_marker + 1)

        for i in range(start_idx, end_idx):
            if i < len(full_48h_timestamps):
                is_marker = i == marker_idx
                sleep_value = sleep_score_results[i] if i < len(sleep_score_results) else 0
                choi_value = choi_results[i] if i < len(choi_results) else 0
                nwt_value = nonwear_sensor_results[i] if i < len(nonwear_sensor_results) else 0

                axis_y_value = int(full_48h_axis_y[i]) if full_48h_axis_y and i < len(full_48h_axis_y) else 0
                vm_value = int(full_48h_vm[i]) if full_48h_vm and i < len(full_48h_vm) else 0

                surrounding_data.append(
                    {
                        "time": full_48h_timestamps[i].strftime("%H:%M"),
                        "timestamp": full_48h_timestamps[i].timestamp(),
                        "axis_y": axis_y_value,
                        "vm": vm_value,
                        "sleep_score": sleep_value,  # Generic key for any sleep/wake algorithm
                        "choi": choi_value,
                        "nwt_sensor": nwt_value,
                        "is_marker": is_marker,
                    }
                )

        return surrounding_data

    def get_full_48h_data_for_popout(self, marker_timestamp: float | None = None) -> list[dict[str, Any]]:
        """
        Get all 2880 rows of 48-hour data for pop-out tables (full day view).

        Args:
            marker_timestamp: Optional timestamp of the marker to highlight

        Returns:
            List of data dictionaries for all 2880 rows

        """
        full_data = []

        # ALWAYS use full 48hr data for tables
        pw = self.services.plot_widget
        if not pw:
            return full_data

        full_48h_timestamps = getattr(pw, "main_48h_timestamps", None)
        full_48h_activity = getattr(pw, "main_48h_activity", None)

        # Get axis_y data
        full_48h_axis_y = None
        if pw.main_48h_axis_y_data:
            full_48h_axis_y = pw.main_48h_axis_y_data
        else:
            full_48h_axis_y = self.main_window._get_axis_y_data_for_sadeh()

        if not full_48h_axis_y:
            logger.error("POPOUT: No axis_y data available!")

        # Load Vector Magnitude data
        full_48h_vm = self._load_vector_magnitude_data()

        # If no 48hr data, fall back to current view data
        if full_48h_timestamps is None or full_48h_activity is None:
            full_48h_timestamps = pw.timestamps
            full_48h_activity = pw.activity_data

        if not full_48h_timestamps:
            return full_data

        logger.debug("Loading %d rows for pop-out table", len(full_48h_timestamps))

        # Get sleep/wake algorithm result arrays
        sleep_score_results = getattr(pw, "main_48h_sadeh_results", getattr(pw, "sadeh_results", []))

        if not sleep_score_results:
            try:
                pw.plot_algorithms()
                sleep_score_results = getattr(pw, "main_48h_sadeh_results", getattr(pw, "sadeh_results", []))
            except Exception as e:
                logger.exception("Failed to run algorithms for popout table: %s", e)

        # PlotWidgetProtocol guarantees these methods exist
        choi_results = pw.get_choi_results_per_minute()
        nonwear_sensor_results = pw.get_nonwear_sensor_results_per_minute()

        # Get ALL rows
        for i in range(len(full_48h_timestamps)):
            sleep_value = sleep_score_results[i] if i < len(sleep_score_results) else 0
            choi_value = choi_results[i] if i < len(choi_results) else 0
            nwt_value = nonwear_sensor_results[i] if i < len(nonwear_sensor_results) else 0

            axis_y_value = int(full_48h_axis_y[i]) if full_48h_axis_y and i < len(full_48h_axis_y) else 0
            vm_value = int(full_48h_vm[i]) if full_48h_vm and i < len(full_48h_vm) else 0

            # Check if this row should be marked
            is_marker = False
            if marker_timestamp is not None:
                row_timestamp = full_48h_timestamps[i].timestamp()
                if abs(row_timestamp - marker_timestamp) < 30:
                    is_marker = True

            full_data.append(
                {
                    "time": full_48h_timestamps[i].strftime("%H:%M"),
                    "timestamp": full_48h_timestamps[i].timestamp(),
                    "axis_y": axis_y_value,
                    "vm": vm_value,
                    "sleep_score": sleep_value,  # Generic key for any sleep/wake algorithm
                    "choi": choi_value,
                    "nwt_sensor": nwt_value,
                    "is_marker": is_marker,
                }
            )

        return full_data

    def _load_vector_magnitude_data(self) -> list[float] | None:
        """Load vector magnitude data for table display."""
        # PERFORMANCE: Return cached VM data if available
        pw = self.services.plot_widget
        if pw and pw._cached_48h_vm_data is not None:
            return pw._cached_48h_vm_data

        full_48h_vm = None
        # Use services and navigation interfaces
        filename = self.navigation.selected_file
        if filename and not filename.endswith((".csv", ".gt3x")):
            filename = Path(filename).name

        current_date = (
            self.navigation.available_dates[self.navigation.current_date_index]
            if self.navigation.current_date_index is not None and self.navigation.available_dates
            else None
        )

        if filename and current_date:
            try:
                from sleep_scoring_app.core.constants import ActivityDataPreference, ViewHours

                # Handle both date and datetime objects
                if isinstance(current_date, date) and not isinstance(current_date, datetime):
                    start_time = datetime.combine(current_date, datetime.min.time())
                else:
                    start_time = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_time = start_time + timedelta(hours=48)

                if self.services.data_service.get_database_mode():
                    _, full_48h_vm = self.services.data_service.load_raw_activity_data(
                        filename, start_time, end_time, activity_column=ActivityDataPreference.VECTOR_MAGNITUDE
                    )
                else:
                    _, full_48h_vm = self.services.data_service.load_real_data(
                        current_date,
                        ViewHours.HOURS_48,
                        filename,
                        activity_column=ActivityDataPreference.VECTOR_MAGNITUDE,
                    )

                # Cache the result on the plot widget
                if full_48h_vm is not None and pw:
                    pw._cached_48h_vm_data = full_48h_vm

            except Exception as e:
                logger.exception("Failed to load vector magnitude data: %s", e)
                full_48h_vm = None

        return full_48h_vm
