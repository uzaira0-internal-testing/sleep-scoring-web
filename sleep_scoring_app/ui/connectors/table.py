"""
Table connectors.

Connects side tables (marker data), pop-out windows, and diary table to the Redux store.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import MarkerCategory

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class SideTableConnector:
    """
    Connects the side tables in AnalysisTab to the Redux store marker state.

    Subscribes to store changes and updates tables when markers change.
    This is the SOLE source of table updates per CLAUDE.md Redux pattern:
    Widget -> Connector -> Store -> Connector -> UI

    Updates tables based on current marker_mode:
    - SLEEP mode: Shows data around selected sleep period onset/offset
    - NONWEAR mode: Shows data around selected nonwear marker start/end

    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._last_table_update_time: float = 0.0  # Throttling state - owned by connector
        self._unsubscribe = store.subscribe(self._on_state_change)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """
        React to marker, selection, or algorithm changes by updating side tables.

        Updates tables based on the CURRENT marker mode (SLEEP or NONWEAR).
        Each mode has symmetric logic: detect changes -> update tables with relevant data.

        Also updates when algorithm settings change since side tables display algorithm results.
        Clears tables when navigating to a date/file with no markers.
        """
        # Clear tables immediately on date or file change to prevent stale data
        date_or_file_changed = (
            old_state.current_date_index != new_state.current_date_index
            or old_state.current_file != new_state.current_file
        )
        if date_or_file_changed:
            self._clear_tables()

        current_mode = new_state.marker_mode

        # Detect algorithm/rule changes that affect table data
        algorithm_changed = (
            old_state.sleep_algorithm_id != new_state.sleep_algorithm_id
            or old_state.onset_offset_rule_id != new_state.onset_offset_rule_id
            or old_state.nonwear_algorithm_id != new_state.nonwear_algorithm_id
            or old_state.choi_axis != new_state.choi_axis
        )

        # === SLEEP MODE ===
        if current_mode == MarkerCategory.SLEEP:
            sleep_changed = (
                old_state.current_sleep_markers is not new_state.current_sleep_markers
                or old_state.last_marker_update_time != new_state.last_marker_update_time
            )
            sleep_selection_changed = old_state.selected_period_index != new_state.selected_period_index

            if (sleep_changed or sleep_selection_changed or algorithm_changed):
                if new_state.current_sleep_markers:
                    self._update_sleep_tables(new_state.current_sleep_markers)
                else:
                    self._clear_tables()

        # === NONWEAR MODE ===
        elif current_mode == MarkerCategory.NONWEAR:
            nonwear_changed = (
                old_state.current_nonwear_markers is not new_state.current_nonwear_markers
                or old_state.last_marker_update_time != new_state.last_marker_update_time
            )
            nonwear_selection_changed = old_state.selected_nonwear_index != new_state.selected_nonwear_index

            if (nonwear_changed or nonwear_selection_changed or algorithm_changed):
                if new_state.current_nonwear_markers is not None:
                    self._update_nonwear_tables(new_state.current_nonwear_markers, new_state.selected_nonwear_index)
                else:
                    self._clear_tables()

    def _clear_tables(self) -> None:
        """Clear both side tables (remove stale data)."""
        table_manager = self.main_window.table_manager
        if table_manager:
            table_manager.update_marker_tables([], [])

    def _update_sleep_tables(self, markers: Any) -> None:
        """Update side tables with data around selected sleep period onset/offset."""
        table_manager = self.main_window.table_manager
        if not table_manager:
            return

        pw = self.main_window.plot_widget
        if not pw:
            table_manager.update_marker_tables([], [])
            return

        # Get selected period from widget
        selected_period = pw.get_selected_marker_period()

        if selected_period and selected_period.is_complete:
            # Throttle updates (50ms)
            current_time = time.time()
            time_since_last_update = current_time - self._last_table_update_time
            if time_since_last_update > 0.05:
                # Get data around onset/offset timestamps using table_manager service
                onset_data = table_manager.get_marker_data_cached(selected_period.onset_timestamp, None)
                offset_data = table_manager.get_marker_data_cached(selected_period.offset_timestamp, None)

                if onset_data or offset_data:
                    table_manager.update_marker_tables(onset_data, offset_data)
                    self._last_table_update_time = current_time

                logger.debug(
                    "Updated tables for sleep marker: onset=%d rows, offset=%d rows",
                    len(onset_data) if onset_data else 0,
                    len(offset_data) if offset_data else 0,
                )
        else:
            # Fallback to first complete period
            complete_periods = markers.get_complete_periods()
            if complete_periods:
                first_period = complete_periods[0]
                current_time = time.time()
                time_since_last_update = current_time - self._last_table_update_time
                if time_since_last_update > 0.05:
                    onset_data = table_manager.get_marker_data_cached(first_period.onset_timestamp, None)
                    offset_data = table_manager.get_marker_data_cached(first_period.offset_timestamp, None)
                    if onset_data or offset_data:
                        table_manager.update_marker_tables(onset_data, offset_data)
                        self._last_table_update_time = current_time
            else:
                # No complete periods - clear tables
                table_manager.update_marker_tables([], [])

    def _update_nonwear_tables(self, markers: Any, selected_index: int) -> None:
        """
        Update side tables with data around selected nonwear marker start/end.

        Mirrors _update_sleep_tables - uses widget's get_selected_nonwear_period().
        """
        table_manager = self.main_window.table_manager
        if not table_manager:
            return

        pw = self.main_window.plot_widget
        if not pw:
            table_manager.update_marker_tables([], [])
            return

        # Use the SAME pattern as sleep: get selected period from widget
        selected_period = pw.get_selected_nonwear_period()

        if selected_period and selected_period.is_complete:
            # Throttle updates (same as sleep)
            current_time = time.time()
            time_since_last_update = current_time - self._last_table_update_time
            if time_since_last_update > 0.05:  # 50ms throttle
                # Get data around start/end timestamps (same as sleep onset/offset)
                start_data = table_manager.get_marker_data_cached(selected_period.start_timestamp, None)
                end_data = table_manager.get_marker_data_cached(selected_period.end_timestamp, None)

                if start_data or end_data:
                    table_manager.update_marker_tables(start_data, end_data)
                    self._last_table_update_time = current_time

                logger.debug(
                    "Updated tables for nonwear marker: start=%d rows, end=%d rows",
                    len(start_data) if start_data else 0,
                    len(end_data) if end_data else 0,
                )
        else:
            # No complete period selected - clear tables (same as sleep fallback)
            table_manager.update_marker_tables([], [])

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class PopOutConnector:
    """
    Connects the pop-out windows to the Redux store marker state.

    The SOLE authority for refreshing pop-out window data.
    Refreshes visible pop-out windows when markers change.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial refresh to ensure current state is shown if windows exist
        self._refresh_popouts()

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to any marker, selection, or algorithm changes by refreshing open pop-out windows."""
        # Refresh on: marker data change, dirty flag change, file/date selection change, or algorithm change
        markers_changed = (
            old_state.current_sleep_markers is not new_state.current_sleep_markers
            or old_state.current_nonwear_markers is not new_state.current_nonwear_markers
            or old_state.last_markers_save_time != new_state.last_markers_save_time
            or old_state.current_file != new_state.current_file
            or old_state.current_date_index != new_state.current_date_index
            or old_state.selected_period_index != new_state.selected_period_index
            or old_state.selected_nonwear_index != new_state.selected_nonwear_index
            or old_state.marker_mode != new_state.marker_mode
        )

        # Algorithm changes affect the sleep_score column in pop-out tables
        algorithm_changed = (
            old_state.sleep_algorithm_id != new_state.sleep_algorithm_id
            or old_state.nonwear_algorithm_id != new_state.nonwear_algorithm_id
            or old_state.choi_axis != new_state.choi_axis
        )

        if markers_changed or algorithm_changed:
            self._refresh_popouts()

    def _refresh_popouts(self) -> None:
        """Refresh visible pop-out windows via AnalysisTab."""
        # Protocol guarantees analysis_tab exists with these methods
        tab = self.main_window.analysis_tab
        if tab:
            # Delegate refreshing to the tab's methods which know how to fetch 48h data
            tab.refresh_onset_popout()
            tab.refresh_offset_popout()

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class DiaryTableConnector:
    """
    Connects the diary table to the Redux store state.

    Refreshes diary display when file selection changes.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_diary()

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to file changes by refreshing diary."""
        # Always log when state change is received
        logger.debug(f"DIARY CONNECTOR: _on_state_change called. old_file='{old_state.current_file}', new_file='{new_state.current_file}'")

        if old_state.current_file != new_state.current_file:
            logger.info(f"DIARY CONNECTOR: File changed from '{old_state.current_file}' to '{new_state.current_file}', updating diary")
            self._update_diary()
        elif old_state.current_file and old_state.current_file == new_state.current_file:
            # File unchanged - log for debugging
            logger.debug(f"DIARY CONNECTOR: File unchanged ({new_state.current_file}), skipping update")

    def _update_diary(self) -> None:
        """Refresh diary table via AnalysisTab."""
        # Protocol guarantees analysis_tab has update_diary_display method
        tab = self.main_window.analysis_tab
        logger.info(f"DIARY CONNECTOR: _update_diary called, analysis_tab exists: {tab is not None}")
        if tab:
            logger.info("DIARY CONNECTOR: Calling update_diary_display()")
            tab.update_diary_display()
        else:
            logger.warning("DIARY CONNECTOR: No analysis_tab available!")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()
