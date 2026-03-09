"""
File management connectors.

Connects file list, file table, and file selection UI to the Redux store.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import FileInfo
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class FileManagementConnector:
    """
    Smart Container for FileManagementWidget.
    Bridges Redux state to the presentational widget.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window

        # We find the widget in the hierarchy
        self.widget = getattr(main_window.data_settings_tab, "file_management_widget", None)
        if not self.widget:
            logger.warning("FILE MGMT CONNECTOR: Presentational widget not found")
            return

        # 1. Subscribe to Store changes
        self._unsubscribe = store.subscribe(self._on_state_change)

        # 2. Connect Widget signals to Actions
        self.widget.refreshRequested.connect(self._on_refresh_requested)
        self.widget.deleteRequested.connect(self._on_delete_requested)

        # Initial data injection
        self.widget.set_files(list(store.state.available_files))

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to available_files changes in Store."""
        if old_state.available_files != new_state.available_files:
            logger.info("FILE MGMT CONNECTOR: available_files changed in Store, updating widget")
            self.widget.set_files(list(new_state.available_files))

    def _on_refresh_requested(self) -> None:
        """Dispatch Refresh action to Store."""
        # Note: The actual service call is handled by the Effect Handler (e.g. NavManager)
        # or we could call it here if we want the Connector to handle the 'Effect'.
        # Industry standard: Dispatches an action that triggers a middleware/effect.
        from sleep_scoring_app.ui.store import Actions

        self.store.dispatch(Actions.refresh_files_requested())

    def _on_delete_requested(self, filenames: list[str]) -> None:
        """Dispatch Delete action to Store."""
        from sleep_scoring_app.ui.store import Actions

        self.store.dispatch(Actions.delete_files_requested(filenames))

    def disconnect(self) -> None:
        """Cleanup."""
        self._unsubscribe()
        try:
            self.widget.refreshRequested.disconnect(self._on_refresh_requested)
            self.widget.deleteRequested.disconnect(self._on_delete_requested)
        except (TypeError, RuntimeError, AttributeError):
            pass


class FileListConnector:
    """
    Connects the file list in the UI to the Redux store.
    SOLE Authority for file selector table UI state.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_table(store.state.available_files)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to file list changes."""
        if old_state.available_files != new_state.available_files:
            logger.info(f"FILE LIST CONNECTOR: Files changed, updating table. Count: {len(new_state.available_files)}")
            self._update_table(new_state.available_files)

    def _update_table(self, files: tuple[FileInfo, ...]) -> None:
        """Update file selector table widget."""
        selector = self.main_window.file_selector
        if not selector:
            return

        selector.populate_files(list(files))

        # Trigger indicator update (which also happens reactively via FileTableConnector)
        # Protocol guarantees data_service exists on MainWindowProtocol
        if self.main_window.data_service:
            self._update_indicators(files)

    def _update_indicators(self, files: tuple[FileInfo, ...]) -> None:
        """Update file completion indicators in the table."""
        # For now we delegate the complex count calculation to the service
        # but the connector triggers it based on state changes.
        pass

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class FileTableConnector:
    """Connects the file table indicators to the store."""

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to state changes that affect file table."""
        # Update when markers are saved (completion indicator may change)
        if old_state.last_saved_file != new_state.last_saved_file:
            self._update_file_indicators()

    def _update_file_indicators(self) -> None:
        """Update file table completion indicators."""
        # Protocol guarantees data_service exists
        if self.main_window.data_service:
            # Use QTimer to avoid dispatch-in-dispatch error
            def refresh_files():
                # Service is headless - provide callback to dispatch to store
                from sleep_scoring_app.ui.store import Actions

                def on_files_loaded(files):
                    self.main_window.store.dispatch(Actions.files_loaded(files))

                self.main_window.data_service.load_available_files(load_completion_counts=True, on_files_loaded=on_files_loaded)

            QTimer.singleShot(0, refresh_files)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class FileSelectionLabelConnector:
    """
    Updates the file selection label based on available_files and database_mode.

    ARCHITECTURE: Replaces UIStateCoordinator.update_folder_info_label()
    by reacting to Redux state changes instead of direct widget manipulation.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Initial update
        self._update_label(store.state)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to available_files or database_mode changes."""
        changed = old_state.available_files != new_state.available_files or old_state.database_mode != new_state.database_mode

        if changed:
            self._update_label(new_state)

    def _update_label(self, state: UIState) -> None:
        """Update the file selection label."""
        tab = self.main_window.analysis_tab
        if not tab:
            return

        label = getattr(tab, "file_selection_label", None)
        if not label:
            return

        file_count = len(state.available_files)

        if state.database_mode:
            label.setText(f"File Selection ({file_count} files from database)")
        else:
            label.setText(f"File Selection ({file_count} files)")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()
