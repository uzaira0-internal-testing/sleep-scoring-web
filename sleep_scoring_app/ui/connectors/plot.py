"""
Plot connectors.

Connects plot widget interactions (clicks, arrows, data display) to the Redux store.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sleep_scoring_app.core.constants import ActivityDataPreference, DatabaseColumn, MarkerCategory

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class PlotArrowsConnector:
    """
    Connects the plot arrows refresh to Redux store marker state changes.

    Subscribes to state and refreshes arrows when save completes (dirty -> clean transition).
    NO POLLING - uses Redux subscription.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to state changes for arrow refresh."""
        # Refresh arrows when transitioning from dirty to clean (save completed)
        was_dirty = old_state.sleep_markers_dirty
        is_clean = not new_state.sleep_markers_dirty

        if was_dirty and is_clean:
            self._refresh_arrows()

    def _refresh_arrows(self) -> None:
        """Refresh sleep onset/offset arrows on plot."""
        # Protocol guarantees plot_widget exists
        plot_widget = self.main_window.plot_widget
        if not plot_widget:
            return
        selected_period = plot_widget.get_selected_marker_period()

        if selected_period and selected_period.is_complete:
            plot_widget.apply_sleep_scoring_rules(selected_period)
            logger.debug("Refreshed arrows after save")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class PlotClickConnector:
    """
    Handles plot click signals and decides action based on Redux state.

    Widget emits click signal; connector checks Redux marker_mode
    to decide whether to add a sleep or nonwear marker.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window

        # Connect to plot widget click signals
        pw = main_window.plot_widget
        if pw:
            pw.plot_left_clicked.connect(self._on_plot_left_clicked)
            pw.plot_right_clicked.connect(self._on_plot_right_clicked)
            logger.info("PLOT CLICK CONNECTOR: Connected to plot click signals")

    def _on_plot_left_clicked(self, timestamp: float) -> None:
        """Handle left-click on plot - add marker based on Redux marker_mode."""
        pw = self.main_window.plot_widget
        if not pw:
            return

        # Check Redux state for marker mode
        marker_mode = self.store.state.marker_mode
        logger.debug(f"PLOT CLICK CONNECTOR: Left click at {timestamp}, mode={marker_mode}")

        if marker_mode == MarkerCategory.SLEEP:
            # On no-sleep days, force nap creation instead of main sleep
            if self.store.state.is_no_sleep_marked:
                pw.add_sleep_marker(timestamp, force_nap=True)
            else:
                pw.add_sleep_marker(timestamp)
        elif marker_mode == MarkerCategory.NONWEAR:
            pw.add_nonwear_marker(timestamp)

    def _on_plot_right_clicked(self) -> None:
        """Handle right-click on plot - cancel incomplete marker based on Redux marker_mode."""
        pw = self.main_window.plot_widget
        if not pw:
            return

        # Check Redux state for marker mode
        marker_mode = self.store.state.marker_mode

        if marker_mode == MarkerCategory.SLEEP:
            if pw.current_marker_being_placed is not None:
                logger.debug("PLOT CLICK CONNECTOR: Cancelling incomplete sleep marker")
                pw.cancel_incomplete_marker()
        elif marker_mode == MarkerCategory.NONWEAR:
            if pw._current_nonwear_marker_being_placed is not None:
                logger.debug("PLOT CLICK CONNECTOR: Cancelling incomplete nonwear marker")
                pw.cancel_incomplete_nonwear_marker()

    def disconnect(self) -> None:
        """Cleanup signal connections."""
        pw = self.main_window.plot_widget
        if pw:
            try:
                pw.plot_left_clicked.disconnect(self._on_plot_left_clicked)
                pw.plot_right_clicked.disconnect(self._on_plot_right_clicked)
            except (TypeError, RuntimeError):
                pass  # Already disconnected


class PlotDataConnector:
    """
    Connects the PlotWidget to activity data in the Redux store.

    Subscribes to activity_timestamps changes in the store and updates
    PlotWidget with the data. Store is the single source of truth.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        logger.info("PLOT DATA CONNECTOR: Initialized")

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to activity data changes by updating plot widget."""
        # Check if activity data changed
        data_changed = old_state.activity_timestamps != new_state.activity_timestamps

        if data_changed:
            if new_state.activity_timestamps:
                logger.info(f"PLOT DATA CONNECTOR: Activity data changed. timestamps={len(new_state.activity_timestamps)}, updating plot")
                self._update_plot(new_state)
            else:
                # Data was cleared - clear the plot widget
                logger.info("PLOT DATA CONNECTOR: Activity data cleared, clearing plot")
                self._clear_plot()

        # Also clear if file becomes None (regardless of data change)
        if old_state.current_file and not new_state.current_file:
            logger.info("PLOT DATA CONNECTOR: File deselected, clearing plot")
            self._clear_plot()

    def _clear_plot(self) -> None:
        """Clear the plot widget when data is removed."""
        pw = self.main_window.plot_widget
        if not pw:
            return
        pw.clear_plot()
        pw.clear_sleep_markers()
        pw.clear_nonwear_markers()
        pw.clear_sleep_onset_offset_markers()
        logger.info("PLOT DATA CONNECTOR: Plot cleared")

    def _update_plot(self, state: UIState) -> None:
        """Update plot widget with data from store."""
        from datetime import date

        pw = self.main_window.plot_widget
        if not pw:
            logger.warning("PLOT DATA CONNECTOR: No plot widget available")
            return

        # Convert tuples back to lists for widget compatibility
        timestamps = list(state.activity_timestamps)
        axis_y = list(state.axis_y_data)
        vector_magnitude = list(state.vector_magnitude_data)

        if not timestamps:
            logger.warning("PLOT DATA CONNECTOR: No timestamps in state")
            return

        # Determine which column to display based on preference
        preferred = state.preferred_display_column
        if preferred == ActivityDataPreference.VECTOR_MAGNITUDE and vector_magnitude:
            display_data = vector_magnitude
            column_type = DatabaseColumn.VECTOR_MAGNITUDE
        else:  # axis_y (default)
            display_data = axis_y
            column_type = DatabaseColumn.AXIS_Y

        logger.info(f"PLOT DATA CONNECTOR: Updating plot with {len(timestamps)} points, display_column={preferred}, column_type={column_type}")

        # Get current date for display
        current_date = None
        if 0 <= state.current_date_index < len(state.available_dates):
            current_date = date.fromisoformat(state.available_dates[state.current_date_index])

        # Call the plot update method FIRST
        # (it will clear algorithm data, which is fine - we set axis_y after)
        pw.set_data_and_restrictions(
            timestamps=timestamps,
            activity_data=display_data,
            view_hours=state.view_mode_hours,  # Use actual view mode from store
            skip_nonwear_plotting=True,  # Skip algorithms for now - we'll set axis_y and trigger manually
            filename=state.current_file,
            activity_column_type=column_type,
            current_date=current_date,
        )

        # CRITICAL: Store axis_y data AFTER set_data_and_restrictions
        # (set_data_and_restrictions clears main_48h_axis_y_data, so we must set it after)
        pw.main_48h_axis_y_data = axis_y
        pw.main_48h_axis_y_timestamps = timestamps  # SAME timestamps - no alignment bug

        # Load nonwear data for plot (Choi algorithm, sensor data)
        # This was previously called by load_current_date() after updating plot
        self.main_window.load_nonwear_data_for_plot()

        # Now run algorithms with the axis_y data properly set
        pw.plot_algorithms()

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()
