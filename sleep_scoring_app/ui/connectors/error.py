"""
Error notification connector.

Displays error messages from the Redux store in the status bar.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class ErrorNotificationConnector:
    """
    Connects error state to the status bar for user feedback.

    When an error_occurred action is dispatched, this connector shows
    the error message in the status bar for 5 seconds.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._last_error_time: float = 0.0
        self._unsubscribe = store.subscribe(self._on_state_change)

        logger.info("ERROR NOTIFICATION CONNECTOR: Initialized")

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to error state changes by showing messages in status bar."""
        # Check if a new error occurred (different timestamp means new error)
        if new_state.last_error_message and new_state.last_error_time != self._last_error_time:
            self._last_error_time = new_state.last_error_time
            self._show_error(new_state.last_error_message)

    def _show_error(self, message: str) -> None:
        """Display error message in the status bar."""
        logger.warning(f"ERROR NOTIFICATION CONNECTOR: Showing error to user: {message}")

        # Use the existing update_status_bar method on MainWindow
        # Protocol guarantees this method exists
        self.main_window.update_status_bar(f"Error: {message}")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()
