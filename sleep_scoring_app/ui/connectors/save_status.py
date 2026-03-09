"""
Save and status connectors.

Connects save button and status indicators (No Sleep button) to the Redux store.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sleep_scoring_app.core.constants import ButtonStyle, ButtonText

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class SaveButtonConnector:
    """Connects the save button to the Redux store marker state."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update with current state
        self._update_button_from_state(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to state changes that affect save button."""
        # Only update if dirty state or markers changed or autosave changed
        should_update = (
            old_state.sleep_markers_dirty != new_state.sleep_markers_dirty
            or old_state.nonwear_markers_dirty != new_state.nonwear_markers_dirty
            or old_state.current_sleep_markers is not new_state.current_sleep_markers
            or old_state.auto_save_enabled != new_state.auto_save_enabled
        )

        if should_update:
            logger.info(f"SAVE BUTTON CONNECTOR: Triggering update. Dirty: {new_state.sleep_markers_dirty}, AutoSave: {new_state.auto_save_enabled}")
            self._update_button_from_state(new_state)

    def _update_button_from_state(self, state: UIState) -> None:
        """Update save button appearance based on state."""
        # Protocol guarantees save_markers_btn exists
        btn = self.main_window.save_markers_btn
        if not btn:
            return

        # Visibility based on autosave setting from state
        btn.setVisible(not state.auto_save_enabled)

        # Determine state
        has_any_markers = state.current_sleep_markers is not None or state.current_nonwear_markers is not None
        is_dirty = state.sleep_markers_dirty or state.nonwear_markers_dirty

        if not has_any_markers:
            btn.setText(ButtonText.SAVE_MARKERS)
            btn.setStyleSheet(ButtonStyle.SAVE_MARKERS)
            btn.setEnabled(False)
        elif is_dirty:
            btn.setText(ButtonText.SAVE_MARKERS)
            btn.setStyleSheet(ButtonStyle.SAVE_MARKERS)
            btn.setEnabled(True)
        else:
            btn.setText(ButtonText.MARKERS_SAVED)
            btn.setStyleSheet(ButtonStyle.SAVE_MARKERS_SAVED)
            btn.setEnabled(True)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class StatusConnector:
    """Connects various status buttons (like No Sleep) to the store."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)
        logger.info("STATUS CONNECTOR: Initialized and subscribed to store")

        # Initial update
        self._update_ui(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to state changes."""
        # Log all relevant state changes for debugging
        logger.debug(
            f"STATUS CONNECTOR: State change detected. "
            f"is_no_sleep_marked: {old_state.is_no_sleep_marked} -> {new_state.is_no_sleep_marked}, "
            f"date_index: {old_state.current_date_index} -> {new_state.current_date_index}"
        )

        # Update if markers, file, date, or no_sleep flag changed
        should_update = (
            old_state.current_sleep_markers is not new_state.current_sleep_markers
            or old_state.current_file != new_state.current_file
            or old_state.current_date_index != new_state.current_date_index
            or old_state.is_no_sleep_marked != new_state.is_no_sleep_marked
        )
        if should_update:
            logger.info(f"STATUS CONNECTOR: Triggering UI update. is_no_sleep_marked={new_state.is_no_sleep_marked}")
            self._update_ui(new_state)

    def _update_ui(self, state: UIState) -> None:
        """Update 'No Sleep' button based on marker state."""
        tab = self.main_window.analysis_tab
        if not tab:
            logger.warning("STATUS CONNECTOR: analysis_tab is None, skipping update")
            return

        # Protocol guarantees no_sleep_btn exists on AnalysisTab
        btn = tab.no_sleep_btn

        # Priority: actual markers > no_sleep flag
        # If we have complete markers, show default state (user can still mark no sleep to clear them)
        if state.current_sleep_markers and state.current_sleep_markers.get_marker_count() >= 2:
            logger.info("STATUS CONNECTOR: Setting button to MARK_NO_SLEEP (has markers)")
            btn.setText(ButtonText.MARK_NO_SLEEP)
            btn.setStyleSheet(ButtonStyle.MARK_NO_SLEEP)
        # If this date is marked as "no sleep" (and no markers), show that state
        elif state.is_no_sleep_marked:
            logger.info("STATUS CONNECTOR: Setting button to NO_SLEEP_MARKED")
            btn.setText(ButtonText.NO_SLEEP_MARKED)
            btn.setStyleSheet(ButtonStyle.NO_SLEEP_MARKED)
        # Otherwise, show default state (ready to mark)
        else:
            logger.info("STATUS CONNECTOR: Setting button to MARK_NO_SLEEP (default)")
            btn.setText(ButtonText.MARK_NO_SLEEP)
            btn.setStyleSheet(ButtonStyle.MARK_NO_SLEEP)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()
        logger.info("STATUS CONNECTOR: Disconnected")
