"""
Persistence connectors.

Connects configuration persistence and window geometry to the Redux store.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class ConfigPersistenceConnector:
    """
    Syncs store state to the application configuration file.

    This connector listens for changes to study settings in the Redux store
    and persists them to the config file via config_manager.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._unsubscribe = store.subscribe(self._on_state_change)

        logger.info("ConfigPersistenceConnector initialized")

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """Persist study settings changes to config file."""
        if not self.main_window.config_manager:
            return

        # Fields that should be persisted to config
        fields_to_persist = [
            "study_unknown_value",
            "study_valid_groups",
            "study_valid_timepoints",
            "study_default_group",
            "study_default_timepoint",
            "study_participant_id_patterns",
            "study_timepoint_pattern",
            "study_group_pattern",
            "data_paradigm",
            "sleep_algorithm_id",
            "onset_offset_rule_id",
            "night_start_hour",
            "night_end_hour",
            "nonwear_algorithm_id",
            "choi_axis",
        ]

        # Check if any of these changed
        changes = {}
        for field in fields_to_persist:
            old_val = getattr(old_state, field)
            new_val = getattr(new_state, field)
            if old_val != new_val:
                # Convert tuples back to lists for config compatibility if needed
                if isinstance(new_val, tuple):
                    new_val = list(new_val)
                changes[field] = new_val

        if changes:
            logger.info(f"CONFIG PERSISTENCE: Persisting {len(changes)} changes to config")
            # Update config manager
            self.main_window.config_manager.update_study_settings(**changes)

            # Schedule save if autosave is enabled
            if self.main_window.autosave_coordinator:
                self.main_window.autosave_coordinator.schedule_config_save()

        # Auto-save toggle uses a dedicated config method (not a study setting)
        if old_state.auto_save_enabled != new_state.auto_save_enabled:
            self.main_window.config_manager.update_auto_save_markers(new_state.auto_save_enabled)

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()


class _GeometryFilter:
    """Lightweight event filter that triggers geometry dispatch on resize/move."""

    def __init__(self, callback: callable) -> None:
        self._callback = callback

    def eventFilter(self, obj: object, event: object) -> bool:
        from PyQt6.QtCore import QEvent

        if event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self._callback()
        return False


class WindowGeometryConnector:
    """
    Tracks window geometry changes and dispatches them to the store.

    Uses Qt event filter on Resize/Move events with debouncing instead of polling.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        from PyQt6.QtCore import QEvent, QObject

        self.store = store
        self.main_window = main_window
        self._last_geometry: tuple[int, int, int, int] | None = None
        self._last_maximized: bool = False

        # Debounce timer for geometry dispatches (avoids spamming during drag)
        self._debounce_timer = QTimer()
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(100)
        self._debounce_timer.timeout.connect(self._dispatch_geometry)

        # QObject-based event filter wrapper
        class _QEventFilter(QObject):
            def __init__(self, geo_filter: _GeometryFilter) -> None:
                super().__init__()
                self._geo_filter = geo_filter

            def eventFilter(self, obj: QObject, event: QEvent) -> bool:
                return self._geo_filter.eventFilter(obj, event)

        self._filter_impl = _GeometryFilter(self._on_geometry_event)
        self._filter = _QEventFilter(self._filter_impl)
        self.main_window.installEventFilter(self._filter)

        logger.info("WindowGeometryConnector initialized (event-driven)")

    def _on_geometry_event(self) -> None:
        """Handle resize/move events by restarting debounce timer."""
        self._debounce_timer.start()

    def _dispatch_geometry(self) -> None:
        """Dispatch geometry changes after debounce period."""
        from sleep_scoring_app.ui.store import Actions

        if not self.main_window.isVisible():
            return

        # Check maximized state
        maximized = self.main_window.isMaximized()
        if maximized != self._last_maximized:
            self._last_maximized = maximized
            self.store.dispatch(Actions.window_maximized_changed(maximized))

        # Check geometry (only if not maximized - maximized geometry is not meaningful)
        if not maximized:
            geometry = self.main_window.geometry()
            current = (geometry.x(), geometry.y(), geometry.width(), geometry.height())

            if current != self._last_geometry:
                self._last_geometry = current
                self.store.dispatch(Actions.window_geometry_changed(*current))

    def disconnect(self) -> None:
        """Cleanup event filter and timer."""
        self._debounce_timer.stop()
        self.main_window.removeEventFilter(self._filter)
