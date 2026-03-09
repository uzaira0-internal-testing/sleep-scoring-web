#!/usr/bin/env python3
"""
File Navigation Manager for Sleep Scoring Application.

Manages file and date navigation, dropdown population, and selection handling.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMessageBox

from sleep_scoring_app.ui.store import Actions

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import (
        AppStateInterface,
        MainWindowProtocol,
        NavigationInterface,
        ServiceContainer,
    )
    from sleep_scoring_app.ui.store import UIStore

logger = logging.getLogger(__name__)


class FileNavigationManager:
    """
    Manages date navigation for the main window.

    NOTE: File selection is handled by UIControlsConnector -> MainWindow.on_file_selected_from_table().
    Navigation button state is handled by NavigationConnector.

    Remaining responsibilities:
    - Handle date selection changes (dropdown)
    - Navigate between dates (prev/next)
    - Check for unsaved markers before navigation
    """

    def __init__(
        self, store: UIStore, navigation: NavigationInterface, app_state: AppStateInterface, services: ServiceContainer, parent: MainWindowProtocol
    ) -> None:
        """
        Initialize the file navigation manager.

        Args:
            store: The UI store
            navigation: Navigation interface
            app_state: App state coordination interface
            services: Service container
            parent: Main window (still needed for some Qt-level access for now)

        """
        self.store = store
        self.navigation = navigation
        self.app_state = app_state
        self.services = services
        self.main_window = parent
        self.parent = parent

        logger.info("FileNavigationManager initialized with decoupled interfaces")

    def on_date_dropdown_changed(self, index: int) -> None:
        """Handle date dropdown selection change via Redux store."""
        if not self.navigation.available_dates or index < 0:
            return

        if index < len(self.navigation.available_dates) and index != self.navigation.current_date_index:
            # Check for unsaved markers
            if self._check_unsaved_markers():
                return

            logger.info(f"NAV MANAGER: Dispatching DATE_SELECTED ({index})")
            self.store.dispatch(Actions.date_selected(index))

    def prev_date(self) -> None:
        """Navigate to previous date via Redux store."""
        if self._check_unsaved_markers():
            return

        if self.navigation.current_date_index is not None and self.navigation.current_date_index > 0:
            logger.info("NAV MANAGER: Dispatching DATE_NAVIGATED (-1)")
            self.store.dispatch(Actions.date_navigated(-1))

    def next_date(self) -> None:
        """Navigate to next date via Redux store."""
        if self._check_unsaved_markers():
            return

        if self.navigation.current_date_index is not None and self.navigation.current_date_index < len(self.navigation.available_dates) - 1:
            logger.info("NAV MANAGER: Dispatching DATE_NAVIGATED (1)")
            self.store.dispatch(Actions.date_navigated(1))

    def _check_unsaved_markers(self) -> bool:
        """
        Check for unsaved markers before navigation.

        Uses Redux store as the source of truth.
        """
        logger.info("=== _check_unsaved_markers (file_navigation) START ===")

        # Use the Redux store selectors
        from sleep_scoring_app.ui.store import Selectors

        has_dirty = Selectors.is_any_markers_dirty(self.parent.store.state)
        logger.info(f"Redux store is_any_markers_dirty = {has_dirty}")

        if has_dirty:
            logger.info("Prompting user about unsaved markers")
            reply = QMessageBox.question(
                self.parent,  # type: ignore[arg-type]
                "Unsaved Markers",
                "You have unsaved markers. Continue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            result = reply == QMessageBox.StandardButton.No
            logger.info(f"User chose to cancel: {result}")
            return result

        logger.info("=== _check_unsaved_markers (file_navigation) END - No unsaved markers ===")
        return False
