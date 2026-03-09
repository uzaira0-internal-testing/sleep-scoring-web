#!/usr/bin/env python3
"""
UI State Coordinator.

Manages UI state dispatching to Redux store.
This coordinator dispatches Redux actions for state changes.
Widget updates are handled by Connectors subscribing to store state changes.

ARCHITECTURE: Coordinators are ONLY for QThread/QTimer glue.
All widget manipulation is done by Connectors.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIStore

logger = logging.getLogger(__name__)


class UIStateCoordinator:
    """
    Coordinates UI state changes via Redux actions.

    Responsibilities:
    - Dispatch Redux actions for UI enable/disable state
    - Dispatch Redux actions for clearing UI state

    Note: All widget updates are handled by Connectors subscribing to store state.
    This class ONLY dispatches actions - it does NOT directly manipulate widgets.
    """

    def __init__(self, parent: MainWindowProtocol, store: UIStore) -> None:
        """
        Initialize the UI state coordinator.

        Args:
            parent: Reference to main window (for QWidget parent context only)
            store: Redux store for dispatching actions

        """
        self.parent = parent
        self.store = store
        logger.info("UIStateCoordinator initialized with Redux store")

    def set_ui_enabled(self, enabled: bool) -> None:
        """
        Enable or disable UI controls based on folder selection status.

        Dispatches action to Redux store - UIControlsConnector handles widget updates.
        """
        from sleep_scoring_app.ui.store import Actions

        # Dispatch action - UIControlsConnector will update widgets
        self.store.dispatch(Actions.ui_controls_enabled_changed(enabled))
        logger.info(f"Dispatched ui_controls_enabled_changed({enabled})")

    def clear_plot_and_ui_state(self) -> None:
        """
        Clear plot and UI state when switching filters.

        Dispatches an action; connectors handle the widget updates reactively.
        """
        from sleep_scoring_app.ui.store import Actions

        logger.debug("Dispatching clear_activity_data_requested action")
        self.store.dispatch(Actions.clear_activity_data_requested())
