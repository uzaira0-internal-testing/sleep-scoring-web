#!/usr/bin/env python3
"""
Seamless Source Switcher
Manages seamless activity data source transitions without losing plot state.
"""

import logging
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

if TYPE_CHECKING:
    from sleep_scoring_app.services.protocols import UnifiedDataProtocol
    from sleep_scoring_app.ui.store import UIStore
    from sleep_scoring_app.ui.utils.config import ConfigManager
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

from sleep_scoring_app.core.constants import ActivityDataPreference
from sleep_scoring_app.core.dataclasses import SleepPeriod
from sleep_scoring_app.utils.date_range import get_48h_range

logger = logging.getLogger(__name__)


class SeamlessSourceSwitcher:
    """Manages seamless activity data source switching."""

    def __init__(
        self,
        store: "UIStore",
        data_service: "UnifiedDataProtocol",
        config_manager: "ConfigManager",
        plot_widget: "ActivityPlotWidget",
        available_dates: list,  # Explicit dependency
        # Functional callbacks to avoid circular MainWindow dependency
        set_pref_callback: Callable[..., Any],
        auto_save_callback: Callable[..., Any],
        load_markers_callback: Callable[..., Any],
        get_tab_dropdown_fn: Callable[..., Any],
    ) -> None:
        """
        Initialize the seamless source switcher.

        Args:
            store: The UI store
            data_service: The unified data service
            config_manager: The config manager
            plot_widget: The activity plot widget
            available_dates: List of available dates
            set_pref_callback: Function to update activity prefs
            auto_save_callback: Function to auto-save markers
            load_markers_callback: Function to reload saved markers
            get_tab_dropdown_fn: Function to get the dropdown widget

        NOTE: load_date_callback REMOVED - dispatches to store instead,
        which triggers ActivityDataConnector to handle data loading.

        """
        self.store = store
        self.data_service = data_service
        self.config_manager = config_manager
        self.plot_widget = plot_widget
        self.available_dates = available_dates

        # Callbacks
        self.set_pref_callback = set_pref_callback
        self.auto_save_callback = auto_save_callback
        self.load_markers_callback = load_markers_callback
        self.get_tab_dropdown_fn = get_tab_dropdown_fn

    def switch_activity_source(self, index: int) -> None:
        """Handle activity data source dropdown change with seamless switching."""
        if index < 0:
            return

        start_time = time.perf_counter()
        selected_column: str | None = None

        try:
            # Get the dropdown via callback
            dropdown = self.get_tab_dropdown_fn()
            if not dropdown:
                return

            selected_column = dropdown.itemData(index)
            if not selected_column:
                return

            logger.info(f"Activity data source changing to: {selected_column} (seamless mode)")

            # Disable dropdown to prevent race conditions
            dropdown.setEnabled(False)

            # Change cursor to indicate processing (thread-safe)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

            try:
                # Step 1: Capture complete current state
                state_capture_start = time.perf_counter()
                current_state = self._capture_complete_plot_state()
                state_capture_time = time.perf_counter() - state_capture_start
                logger.debug(f"State capture took: {state_capture_time:.3f}s")

                # Step 2: Update activity data preferences
                # Choi column is controlled separately by Study Settings
                choi_column = self.config_manager.config.choi_axis if self.config_manager.config else ActivityDataPreference.AXIS_Y
                self.set_pref_callback(selected_column, choi_column)

                # Step 3: Load new activity data only (no full reload)
                data_load_start = time.perf_counter()
                success = self._load_activity_data_seamlessly(selected_column)
                data_load_time = time.perf_counter() - data_load_start
                logger.debug(f"Data loading took: {data_load_time:.3f}s")

                if not success:
                    logger.error("Failed to load activity data seamlessly, falling back to full reload")
                    self._fallback_to_full_reload(selected_column)
                    return

                # Step 4: Update Choi algorithm overlay with new data
                choi_update_start = time.perf_counter()
                self._update_choi_overlay_seamlessly()
                choi_update_time = time.perf_counter() - choi_update_start
                logger.debug(f"Choi overlay update took: {choi_update_time:.3f}s")

                # Step 5: Restore all captured state
                state_restore_start = time.perf_counter()
                self._restore_complete_plot_state(current_state)
                state_restore_time = time.perf_counter() - state_restore_start
                logger.debug(f"State restoration took: {state_restore_time:.3f}s")

                total_time = time.perf_counter() - start_time
                logger.info(f"Seamless activity source switch completed in {total_time:.3f}s")

            finally:
                # Always restore cursor and re-enable dropdown
                QApplication.restoreOverrideCursor()
                dropdown.setEnabled(True)

        except Exception as e:
            logger.exception(f"Error in seamless activity source change: {e}")
            # Fallback to original method on any error
            try:
                QApplication.restoreOverrideCursor()
                dropdown = self.get_tab_dropdown_fn()
                if dropdown:
                    dropdown.setEnabled(True)
                if selected_column:
                    self._fallback_to_full_reload(selected_column)
            except Exception as fallback_error:
                logger.exception(f"Fallback reload also failed: {fallback_error}")

    def _capture_complete_plot_state(self) -> dict:
        """Capture complete plot state including view range, zoom, sleep markers, and UI state."""
        state = {}

        try:
            # Capture view range (zoom and pan state)
            if hasattr(self.plot_widget, "vb") and self.plot_widget.vb:
                view_range = self.plot_widget.vb.viewRange()
                state["view_range"] = {"x_range": view_range[0], "y_range": view_range[1]}

            # Capture sleep markers state from Redux store (SINGLE SOURCE OF TRUTH)
            daily_markers = self.store.state.current_sleep_markers
            if daily_markers:
                state["daily_sleep_markers"] = {
                    "period_1": self._serialize_sleep_period(daily_markers.period_1),
                    "period_2": self._serialize_sleep_period(daily_markers.period_2),
                    "period_3": self._serialize_sleep_period(daily_markers.period_3),
                    "period_4": self._serialize_sleep_period(daily_markers.period_4),
                }

            # Capture current view mode
            if self.data_service:
                state["view_mode"] = getattr(self.data_service, "current_view_mode", None)

            # Capture UI states from store
            ui_state = {
                "view_mode_hours": self.store.state.view_mode_hours,
                "auto_save_enabled": self.store.state.auto_save_enabled,
            }
            state["ui_state"] = ui_state

            return state

        except Exception as e:
            logger.exception(f"Error capturing plot state: {e}")
            return {}

    def _load_activity_data_seamlessly(self, activity_column: ActivityDataPreference) -> bool:
        """Load new activity data without clearing existing state."""
        try:
            state = self.store.state

            # Get dates from Redux store state (single source of truth)
            # Store holds dates as ISO strings, convert to date objects
            if not state.available_dates:
                return False

            if state.current_date_index is None or state.current_date_index < 0:
                return False

            if state.current_date_index >= len(state.available_dates):
                return False

            from datetime import date as date_type

            date_str = state.available_dates[state.current_date_index]
            current_date = date_type.fromisoformat(date_str)
            current_view_mode = state.view_mode_hours
            filename = state.current_file

            # Calculate 48h time range using centralized utility
            date_range_48h = get_48h_range(current_date)

            # Load 48h main data
            timestamps_48h, activity_data_48h = self.data_service.load_raw_activity_data(
                filename, date_range_48h.start, date_range_48h.end, activity_column=activity_column
            )

            if not timestamps_48h or not activity_data_48h:
                return False

            # Always pass full 48h data to the plot.
            # View mode (24h/48h) must only affect viewport/range, not backing data.
            self.plot_widget.update_data_and_view_only(
                timestamps_48h,
                activity_data_48h,
                current_view_mode,
                current_date=current_date,
            )

            return True

        except Exception as e:
            logger.exception(f"Error in seamless data loading: {e}")
            return False

    def _update_choi_overlay_seamlessly(self) -> None:
        """
        Preserve Choi algorithm overlay during display source switch.

        When the user switches the DISPLAY activity source (e.g., from VM to Axis Y),
        the Choi nonwear detection should NOT recalculate because choi_axis hasn't changed.
        Choi uses its own configured axis (choi_axis), not the display axis.

        The Choi overlay only needs recalculation when choi_axis itself changes,
        which is handled by StudySettingsConnector._handle_side_effects().
        """
        # Choi overlay already computed with choi_axis data - preserve it
        logger.debug("Preserving existing Choi overlay during display source switch")

    def _restore_complete_plot_state(self, state: dict) -> None:
        """Restore complete plot state including view range, zoom, and sleep markers."""
        # PlotWidgetProtocol guarantees _update_sleep_scoring_rules exists
        self.plot_widget._update_sleep_scoring_rules()

        if not state:
            return

        try:
            # Restore view range
            if "view_range" in state and hasattr(self.plot_widget, "vb") and self.plot_widget.vb:
                view_range = state["view_range"]
                self.plot_widget.vb.setRange(xRange=view_range["x_range"], yRange=view_range["y_range"], padding=0)

            # Restore sleep markers
            if state.get("daily_sleep_markers"):
                daily_markers_data = state["daily_sleep_markers"]
                from sleep_scoring_app.core.dataclasses import DailySleepMarkers

                restored_markers = DailySleepMarkers(
                    period_1=self._deserialize_sleep_period(daily_markers_data.get("period_1")),
                    period_2=self._deserialize_sleep_period(daily_markers_data.get("period_2")),
                    period_3=self._deserialize_sleep_period(daily_markers_data.get("period_3")),
                    period_4=self._deserialize_sleep_period(daily_markers_data.get("period_4")),
                )
                self.plot_widget.load_daily_sleep_markers(restored_markers)
                # Sync restored markers back to Redux store
                from sleep_scoring_app.ui.store import Actions

                self.store.dispatch_safe(Actions.sleep_markers_changed(restored_markers))

        except Exception as e:
            logger.exception(f"Error restoring plot state: {e}")

    def _fallback_to_full_reload(self, selected_column: str) -> None:
        """
        Fallback to full reload method when seamless switching fails.

        ARCHITECTURE: Dispatches to store to trigger reload via ActivityDataConnector.
        Does NOT call load_current_date() directly - store is single source of truth.
        """
        try:
            self.auto_save_callback()
            # Dispatch config change action to trigger ActivityDataConnector reload
            # Using config_changed action since switching activity source is a config change
            from sleep_scoring_app.ui.store import Actions

            self.store.dispatch_safe(Actions.preferred_display_column_changed(selected_column))
            self.load_markers_callback()
        except Exception as e:
            logger.exception(f"Error in fallback reload: {e}")

    def _serialize_sleep_period(self, period) -> dict | None:
        """Serialize a sleep period for state capture."""
        if period is None:
            return None

        return {
            "onset_timestamp": period.onset_timestamp,
            "offset_timestamp": period.offset_timestamp,
            "marker_index": period.marker_index,
            "marker_type": period.marker_type.value if period.marker_type else None,
        }

    def _deserialize_sleep_period(self, period_data: dict | None) -> SleepPeriod | None:
        """Deserialize a sleep period for state restore."""
        if period_data is None:
            return None

        from sleep_scoring_app.core.constants import MarkerType
        from sleep_scoring_app.core.dataclasses import SleepPeriod

        marker_type = MarkerType.MAIN_SLEEP  # Default
        if period_data.get("marker_type"):
            try:
                marker_type = MarkerType(period_data["marker_type"])
            except ValueError:
                marker_type = MarkerType.MAIN_SLEEP

        return SleepPeriod(
            onset_timestamp=period_data.get("onset_timestamp"),
            offset_timestamp=period_data.get("offset_timestamp"),
            marker_index=period_data.get("marker_index", 1),
            marker_type=marker_type,
        )
