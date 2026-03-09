"""
Navigation connectors.

Connects date navigation (dropdown, prev/next buttons, view mode) to the Redux store.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette

from sleep_scoring_app.core.constants import UIColors

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class DateDropdownConnector:
    """
    Connects the date dropdown population and color to the store.
    SOLE Authority for date dropdown UI state.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._rebuild_dropdown(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to state changes that affect dropdown."""
        # 1. Full re-build if dates changed
        if old_state.available_dates != new_state.available_dates:
            logger.info(f"DATE DROPDOWN CONNECTOR: Dates changed in STORE. New count: {len(new_state.available_dates)}")
            self._rebuild_dropdown(new_state)
            return

        # 2. Sync selection if index changed (without triggering re-dispatch)
        if old_state.current_date_index != new_state.current_date_index:
            logger.info(f"DATE DROPDOWN CONNECTOR: Index changed in STORE: {new_state.current_date_index}")
            self._sync_selection(new_state.current_date_index)

        # 3. Update colors if markers were saved, no-sleep changed, or selection changed
        should_update_colors = (
            old_state.last_markers_save_time != new_state.last_markers_save_time
            or old_state.is_no_sleep_marked != new_state.is_no_sleep_marked
            or old_state.current_date_index != new_state.current_date_index
        )
        if should_update_colors:
            logger.info(
                f"DATE DROPDOWN CONNECTOR: Updating colors. "
                f"save_time_changed={old_state.last_markers_save_time != new_state.last_markers_save_time}, "
                f"no_sleep_changed={old_state.is_no_sleep_marked != new_state.is_no_sleep_marked}"
            )
            self._update_visuals(new_state)

    def _rebuild_dropdown(self, state: UIState) -> None:
        """Build the dropdown items from state."""
        dropdown = self.main_window.date_dropdown
        # QComboBox.__bool__() returns False when empty (0 items), so use `is None`
        if dropdown is None:
            return

        # Block signals to prevent "dispatch in progress" recursion
        dropdown.blockSignals(True)
        try:
            dropdown.clear()
            dates = state.available_dates
            logger.info(f"DATE DROPDOWN CONNECTOR: State has {len(dates)} dates")

            if not dates:
                logger.info("DATE DROPDOWN CONNECTOR: No dates in state, disabling dropdown")
                dropdown.addItem("No dates available")
                # Center the "No dates available" item as well
                dropdown.setItemData(0, Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole)
                dropdown.setEnabled(False)
                return

            logger.info(f"DATE DROPDOWN CONNECTOR: Populating {len(dates)} dates into dropdown")
            for i, d_str in enumerate(dates):
                dropdown.addItem(d_str)
                logger.debug(f"DATE DROPDOWN CONNECTOR: Added date {i}: {d_str}")

            dropdown.setEnabled(True)
            logger.info(f"DATE DROPDOWN CONNECTOR: Dropdown now has {dropdown.count()} items, enabled={dropdown.isEnabled()}")

            # Set selection from state
            if 0 <= state.current_date_index < len(dates):
                dropdown.setCurrentIndex(state.current_date_index)
                logger.info(f"DATE DROPDOWN CONNECTOR: Set index to {state.current_date_index}")
            elif dates:
                dropdown.setCurrentIndex(0)
                logger.info("DATE DROPDOWN CONNECTOR: Defaulted to index 0")

            self._update_visuals(state)
            logger.info(f"DATE DROPDOWN CONNECTOR: _rebuild_dropdown COMPLETE. Final count: {dropdown.count()}")
        finally:
            dropdown.blockSignals(False)

    def _sync_selection(self, index: int) -> None:
        """Sync widget selection with state index."""
        dropdown = self.main_window.date_dropdown
        if dropdown and 0 <= index < dropdown.count():
            dropdown.blockSignals(True)
            dropdown.setCurrentIndex(index)
            dropdown.blockSignals(False)

    def _update_visuals(self, state: UIState) -> None:
        """
        Update dropdown colors based on marker status in DB.

        IMPORTANT: Do NOT use setStyleSheet here - it would destroy the original
        styling defined in analysis_tab.py. Use setItemData for dropdown items
        and QPalette for the line edit color.
        """
        dropdown = self.main_window.date_dropdown
        # Use `is None` check - QComboBox.__bool__() returns False when empty!
        if dropdown is None:
            return
        if dropdown.count() == 0 or not state.current_file:
            return

        filename = Path(state.current_file).name

        try:
            metrics_list = self.main_window.db_manager.load_sleep_metrics(filename=filename)
            status_map = {}
            for m in metrics_list:
                is_no_sleep = m.onset_time == "NO_SLEEP"
                has_markers = m.daily_sleep_markers and m.daily_sleep_markers.get_marker_count() > 0
                status_map[m.analysis_date] = "no_sleep" if is_no_sleep else "markers" if has_markers else "none"

            # Default text color for items without markers (black)
            default_color = QColor("#000000")

            dropdown.blockSignals(True)
            for i in range(dropdown.count()):
                date_str = dropdown.itemText(i)
                status = status_map.get(date_str, "none")

                if status == "no_sleep":
                    dropdown.setItemData(i, QColor(UIColors.DATE_NO_SLEEP), Qt.ItemDataRole.ForegroundRole)
                elif status == "markers":
                    dropdown.setItemData(i, QColor(UIColors.DATE_WITH_MARKERS), Qt.ItemDataRole.ForegroundRole)
                else:
                    # Reset to explicit black color (None doesn't work properly on Windows)
                    dropdown.setItemData(i, default_color, Qt.ItemDataRole.ForegroundRole)

                # Center-align each dropdown list item (CSS text-align doesn't work for QListView)
                dropdown.setItemData(i, Qt.AlignmentFlag.AlignCenter, Qt.ItemDataRole.TextAlignmentRole)

            # Update line edit color for current selection (preserves original stylesheet)
            line_edit = dropdown.lineEdit()
            if line_edit:
                current_index = dropdown.currentIndex()
                if 0 <= current_index < dropdown.count():
                    current_color = dropdown.itemData(current_index, Qt.ItemDataRole.ForegroundRole)
                    if isinstance(current_color, QColor) and current_color.name() != default_color.name():
                        # Set line edit text color via palette (doesn't destroy stylesheet)
                        palette = line_edit.palette()
                        palette.setColor(QPalette.ColorRole.Text, current_color)
                        line_edit.setPalette(palette)
                    else:
                        # Reset to default black
                        palette = line_edit.palette()
                        palette.setColor(QPalette.ColorRole.Text, default_color)
                        line_edit.setPalette(palette)
                    # Force immediate repaint to show color change
                    line_edit.update()

        except Exception as e:
            logger.debug(f"CONNECTOR: Error updating visuals: {e}")
        finally:
            dropdown.blockSignals(False)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class NavigationConnector:
    """Connects date navigation changes to the UI loading logic."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._last_date_str: str | None = None
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_navigation(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to date index or available dates changes."""
        # Calculate current date string
        current_date_str = None
        if 0 <= new_state.current_date_index < len(new_state.available_dates):
            current_date_str = new_state.available_dates[new_state.current_date_index]

        # Only trigger heavy reload if the ACTUAL date changed or file changed
        file_changed = old_state.current_file != new_state.current_file
        date_changed = current_date_str != self._last_date_str

        logger.debug(
            f"NAVIGATION CONNECTOR CHECK: current_date_str={current_date_str}, _last_date_str={self._last_date_str}, file_changed={file_changed}, date_changed={date_changed}"
        )

        if file_changed or date_changed:
            logger.info(f"NAVIGATION CONNECTOR: Triggering update. File changed: {file_changed}, Date changed: {date_changed}")
            self._last_date_str = current_date_str
            self._update_navigation(new_state)

    def _update_navigation(self, state: UIState) -> None:
        """
        Update UI buttons and dropdowns for new date index.

        ARCHITECTURE: This connector ONLY updates UI state (buttons, dropdowns).
        Data loading is handled by ActivityDataConnector -> Store -> PlotDataConnector.
        """
        logger.info(f"NAVIGATION CONNECTOR: Updating for index {state.current_date_index} of {len(state.available_dates)} dates")

        # Sync UI components - Protocol guarantees these exist on AnalysisTabProtocol
        tab = self.main_window.analysis_tab
        if tab:
            # Update buttons (Protocol-guaranteed attributes)
            has_prev = state.current_date_index > 0
            has_next = state.current_date_index < len(state.available_dates) - 1
            tab.prev_date_btn.setEnabled(has_prev)
            tab.next_date_btn.setEnabled(has_next)

            # Update date dropdown (Protocol-guaranteed attribute)
            tab.date_dropdown.blockSignals(True)
            tab.date_dropdown.setCurrentIndex(state.current_date_index)
            tab.date_dropdown.blockSignals(False)

            # Update weekday label
            if 0 <= state.current_date_index < len(state.available_dates):
                from datetime import date

                date_str = state.available_dates[state.current_date_index]
                current_date = date.fromisoformat(date_str)
                weekday_str = current_date.strftime("%A")
                tab.weekday_label.setText(f"Day: {weekday_str}")

        # NOTE: Marker clearing is MarkersConnector's responsibility (reacts to date changes).
        # NOTE: DO NOT call load_current_date() here!
            # ActivityDataConnector subscribes to date changes and loads data -> dispatches to store
            # PlotDataConnector subscribes to store data changes -> updates plot
            # This eliminates the duplicate data loading path that caused alignment bugs

            # Update activity source dropdown enabled state
            if tab:
                tab.update_activity_source_dropdown()

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class NavigationGuardConnector:
    """
    Guards date navigation by checking for unsaved markers before allowing navigation.

    This connector intercepts navigation signals from AnalysisTab and:
    1. Calls main_window._check_unsaved_markers_before_navigation()
    2. Only dispatches to the store if the check passes (user confirms or no unsaved markers)
    3. If user cancels, reverts the dropdown visual selection back to current state

    Architecture: AnalysisTab (signals) -> NavigationGuardConnector -> Store dispatch
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window

        # Connect to navigation signals from AnalysisTab
        tab = main_window.analysis_tab
        if tab:
            tab.prevDateRequested.connect(self._on_prev_date_requested)
            tab.nextDateRequested.connect(self._on_next_date_requested)
            tab.dateSelectRequested.connect(self._on_date_select_requested)
            logger.info("NAVIGATION GUARD CONNECTOR: Connected to AnalysisTab navigation signals")

    def _on_prev_date_requested(self) -> None:
        """Handle previous date button click with unsaved marker check."""
        logger.info("NAVIGATION GUARD CONNECTOR: prev_date_requested signal received")
        if not self.main_window._check_unsaved_markers_before_navigation():
            logger.info("NAVIGATION GUARD CONNECTOR: User canceled prev navigation")
            return

        # Check bounds and dispatch
        current_index = self.store.state.current_date_index
        if current_index > 0:
            from sleep_scoring_app.ui.store import Actions

            logger.info("NAVIGATION GUARD CONNECTOR: Dispatching date_navigated(-1)")
            self.store.dispatch(Actions.date_navigated(-1))

    def _on_next_date_requested(self) -> None:
        """Handle next date button click with unsaved marker check."""
        logger.info("NAVIGATION GUARD CONNECTOR: next_date_requested signal received")
        if not self.main_window._check_unsaved_markers_before_navigation():
            logger.info("NAVIGATION GUARD CONNECTOR: User canceled next navigation")
            return

        # Check bounds and dispatch
        current_index = self.store.state.current_date_index
        num_dates = len(self.store.state.available_dates)
        if current_index < num_dates - 1:
            from sleep_scoring_app.ui.store import Actions

            logger.info("NAVIGATION GUARD CONNECTOR: Dispatching date_navigated(1)")
            self.store.dispatch(Actions.date_navigated(1))

    def _on_date_select_requested(self, index: int) -> None:
        """Handle date dropdown selection with unsaved marker check."""
        logger.info(f"NAVIGATION GUARD CONNECTOR: date_select_requested signal received with index={index}")
        if not self.main_window._check_unsaved_markers_before_navigation():
            logger.info("NAVIGATION GUARD CONNECTOR: User canceled date selection")
            # Revert dropdown visual to current state
            self._revert_dropdown_selection()
            return

        from sleep_scoring_app.ui.store import Actions

        logger.info(f"NAVIGATION GUARD CONNECTOR: Dispatching date_selected({index})")
        self.store.dispatch_async(Actions.date_selected(index))

        # Save to session
        if self.main_window.session_service:
            self.main_window.session_service.save_current_date_index(index)

    def _revert_dropdown_selection(self) -> None:
        """Revert dropdown to show current state index when user cancels navigation."""
        tab = self.main_window.analysis_tab
        if tab and tab.date_dropdown:
            current_index = self.store.state.current_date_index
            tab.date_dropdown.blockSignals(True)
            tab.date_dropdown.setCurrentIndex(current_index)
            tab.date_dropdown.blockSignals(False)
            logger.info(f"NAVIGATION GUARD CONNECTOR: Reverted dropdown to index {current_index}")

    def disconnect(self) -> None:
        """Cleanup signal connections."""
        tab = self.main_window.analysis_tab
        if tab:
            try:
                tab.prevDateRequested.disconnect(self._on_prev_date_requested)
                tab.nextDateRequested.disconnect(self._on_next_date_requested)
                tab.dateSelectRequested.disconnect(self._on_date_select_requested)
            except (TypeError, RuntimeError):
                pass  # Already disconnected


class ViewModeConnector:
    """Connects the view mode (24h/48h) radio buttons to the store."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_ui(store.state.view_mode_hours)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to view mode changes."""
        if old_state.view_mode_hours != new_state.view_mode_hours:
            logger.info(f"VIEW MODE CONNECTOR: Triggering update. Hours: {new_state.view_mode_hours}")
            self._update_ui(new_state.view_mode_hours)

    def _update_ui(self, hours: int) -> None:
        """Update radio buttons and plot widget view."""
        from datetime import date

        tab = self.main_window.analysis_tab
        if not tab:
            return

        # Update radio buttons (Protocol-guaranteed attributes)
        tab.view_24h_btn.blockSignals(True)
        tab.view_48h_btn.blockSignals(True)

        tab.view_24h_btn.setChecked(hours == 24)
        tab.view_48h_btn.setChecked(hours == 48)

        tab.view_24h_btn.blockSignals(False)
        tab.view_48h_btn.blockSignals(False)

        # Update plot widget view range (data is already loaded by ActivityDataConnector)
        pw = self.main_window.plot_widget
        if pw and pw.timestamps:
            pw.current_view_hours = hours

            # Recalculate view bounds based on new mode
            state = self.store.state
            current_date = None
            if 0 <= state.current_date_index < len(state.available_dates):
                current_date = date.fromisoformat(state.available_dates[state.current_date_index])

            if current_date:
                # Update view range on plot (this also recalculates bounds)
                pw.update_view_range_only(hours, current_date)

            logger.info(f"VIEW MODE CONNECTOR: Updated view hours to {hours}h and recalculated bounds")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class ConsensusCheckboxConnector:
    """
    Connects the consensus review checkbox to the store and database.

    This connector:
    1. Listens to checkbox toggle signals from AnalysisTab
    2. Dispatches to store and persists to database
    3. Updates checkbox state when date changes (loads from DB)
    4. Reacts to store state changes to keep checkbox in sync
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Connect to checkbox signal from AnalysisTab
        tab = main_window.analysis_tab
        if tab:
            tab.consensusFlagToggled.connect(self._on_checkbox_toggled)
            logger.info("CONSENSUS CHECKBOX CONNECTOR: Connected to AnalysisTab consensusFlagToggled signal")

        # Initial update
        self._sync_checkbox_from_store(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to state changes that affect the consensus checkbox."""
        # Update checkbox when needs_consensus changes in store
        if old_state.needs_consensus != new_state.needs_consensus:
            logger.info(f"CONSENSUS CHECKBOX CONNECTOR: needs_consensus changed to {new_state.needs_consensus}")
            self._sync_checkbox_from_store(new_state)

        # Load from DB when date changes
        date_changed = old_state.current_date_index != new_state.current_date_index or old_state.current_file != new_state.current_file
        if date_changed and new_state.current_file and new_state.current_date_index >= 0:
            logger.info("CONSENSUS CHECKBOX CONNECTOR: Date changed, loading consensus flag from DB")
            self._load_consensus_from_db(new_state)

        # Enable/disable checkbox based on data availability
        has_data = bool(new_state.available_dates and new_state.current_date_index >= 0)
        tab = self.main_window.analysis_tab
        if tab and tab.needs_consensus_checkbox:
            if tab.needs_consensus_checkbox.isEnabled() != has_data:
                tab.needs_consensus_checkbox.setEnabled(has_data)
                logger.debug(f"CONSENSUS CHECKBOX CONNECTOR: Checkbox enabled={has_data}")

    def _sync_checkbox_from_store(self, state: UIState) -> None:
        """Sync checkbox widget state with store state."""
        tab = self.main_window.analysis_tab
        if not tab or not tab.needs_consensus_checkbox:
            return

        # Block signals to prevent re-dispatch
        tab.needs_consensus_checkbox.blockSignals(True)
        tab.needs_consensus_checkbox.setChecked(state.needs_consensus)
        tab.needs_consensus_checkbox.blockSignals(False)

    def _on_checkbox_toggled(self, checked: bool) -> None:
        """Handle checkbox toggle - dispatch to store and persist to DB."""
        from sleep_scoring_app.ui.store import Actions

        logger.info(f"CONSENSUS CHECKBOX CONNECTOR: Checkbox toggled to {checked}")

        # Dispatch to store
        self.store.dispatch(Actions.consensus_flag_toggled(checked))

        # Persist to database
        self._persist_consensus_to_db(checked)

    def _load_consensus_from_db(self, state: UIState) -> None:
        """Load consensus flag from database for current file/date."""
        try:
            if not state.current_file or state.current_date_index < 0:
                return

            filename = Path(state.current_file).name
            if state.current_date_index >= len(state.available_dates):
                return

            date_str = state.available_dates[state.current_date_index]

            # Load from database via db_manager
            db_manager = self.main_window.db_manager
            if not db_manager:
                logger.warning("CONSENSUS CHECKBOX CONNECTOR: No db_manager available")
                return

            metrics_list = db_manager.load_sleep_metrics(filename=filename, analysis_date=date_str)
            if metrics_list:
                # Get consensus flag from first matching record
                needs_consensus = metrics_list[0].needs_consensus
                logger.info(f"CONSENSUS CHECKBOX CONNECTOR: Loaded needs_consensus={needs_consensus} for {filename}/{date_str}")

                # Dispatch to store to update state
                from sleep_scoring_app.ui.store import Actions

                self.store.dispatch_safe(Actions.consensus_flag_loaded(needs_consensus))
            else:
                # No metrics record exists yet - default to False
                logger.debug(f"CONSENSUS CHECKBOX CONNECTOR: No metrics found for {filename}/{date_str}, defaulting to False")
                from sleep_scoring_app.ui.store import Actions

                self.store.dispatch_safe(Actions.consensus_flag_loaded(False))

        except Exception as e:
            logger.exception(f"CONSENSUS CHECKBOX CONNECTOR: Error loading consensus flag: {e}")

    def _persist_consensus_to_db(self, needs_consensus: bool) -> None:
        """Persist consensus flag to database for current file/date."""
        try:
            state = self.store.state
            if not state.current_file or state.current_date_index < 0:
                logger.warning("CONSENSUS CHECKBOX CONNECTOR: No file/date selected, cannot persist")
                return

            filename = Path(state.current_file).name
            if state.current_date_index >= len(state.available_dates):
                return

            date_str = state.available_dates[state.current_date_index]

            # Update database via db_manager
            db_manager = self.main_window.db_manager
            if not db_manager:
                logger.warning("CONSENSUS CHECKBOX CONNECTOR: No db_manager available")
                return

            # Use the repository to update the consensus flag
            db_manager.update_consensus_flag(filename=filename, analysis_date=date_str, needs_consensus=needs_consensus)
            logger.info(f"CONSENSUS CHECKBOX CONNECTOR: Persisted needs_consensus={needs_consensus} for {filename}/{date_str}")

        except Exception as e:
            logger.exception(f"CONSENSUS CHECKBOX CONNECTOR: Error persisting consensus flag: {e}")

    def disconnect(self) -> None:
        """Cleanup subscription and signal connections."""
        self._unsubscribe()
        tab = self.main_window.analysis_tab
        if tab:
            try:
                tab.consensusFlagToggled.disconnect(self._on_checkbox_toggled)
            except (TypeError, RuntimeError):
                pass  # Already disconnected
