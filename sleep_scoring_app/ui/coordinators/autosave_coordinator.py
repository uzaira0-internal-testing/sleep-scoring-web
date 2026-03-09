#!/usr/bin/env python3
"""
Autosave Coordinator for Sleep Scoring Application.

Provides unified, debounced autosaving for all application state changes.
Replaces scattered QTimer autosave logic throughout the codebase.

The coordinator:
- Subscribes to Redux store for all state changes
- Detects what changed (sleep markers, nonwear markers, config, window state)
- Batches all pending changes into one debounced save operation
- Eliminates race conditions between different autosave timers
- Provides force_save() for application shutdown

Usage:
    # In MainWindow.__init__
    self.autosave_coordinator = AutosaveCoordinator(
        store=self.store,
        config_manager=self.config_manager,
        db_manager=self.db_manager,
    )

    # In MainWindow.closeEvent
    self.autosave_coordinator.force_save()
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from PyQt6.QtCore import QTimer

from sleep_scoring_app.core.dataclasses_markers import DailyNonwearMarkers, DailySleepMarkers
from sleep_scoring_app.data.database import DatabaseManager
from sleep_scoring_app.ui.store import UIState, UIStore
from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class PendingChangeType(StrEnum):
    """Types of changes that can be pending save."""

    SLEEP_MARKERS = "sleep_markers"
    NONWEAR_MARKERS = "nonwear_markers"
    CONFIG = "config"
    WINDOW_STATE = "window_state"


@dataclass(frozen=True)
class AutosaveConfig:
    """Configuration for autosave coordinator."""

    debounce_ms: int = 500  # 500ms debounce - fast enough to feel immediate on drop
    enabled: bool = True


class AutosaveCoordinator:
    """
    Unified autosave coordinator for all application state.

    Responsibilities:
    - Subscribe to Redux store for state changes
    - Detect what changed (markers, config, window state)
    - Debounce saves to avoid excessive I/O
    - Batch multiple changes into one save operation
    - Provide force_save() for immediate save on app close

    This eliminates race conditions between different autosave timers
    and provides a single source of truth for autosave behavior.
    """

    def __init__(
        self,
        store: UIStore,
        config_manager: ConfigManager,
        db_manager: DatabaseManager,
        save_sleep_markers_callback: Callable[[DailySleepMarkers], bool],
        save_nonwear_markers_callback: Callable[[DailyNonwearMarkers], bool],
        config: AutosaveConfig | None = None,
        on_autosave_failed: Callable[[str], None] | None = None,
        on_autosave_success: Callable[[], None] | None = None,
    ) -> None:
        """
        Initialize the autosave coordinator.

        Args:
            store: Redux store to subscribe to
            config_manager: Config manager for saving config changes
            db_manager: Database manager for saving markers
            save_sleep_markers_callback: Callback function from MainWindow to save sleep markers
            save_nonwear_markers_callback: Callback function from MainWindow to save nonwear markers
            config: Optional autosave configuration
            on_autosave_failed: Optional callback when autosave fails (receives error message)
            on_autosave_success: Optional callback when autosave succeeds

        """
        self.store = store
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.save_sleep_markers_callback = save_sleep_markers_callback
        self.save_nonwear_markers_callback = save_nonwear_markers_callback
        self.config = config or AutosaveConfig()
        self._on_autosave_failed = on_autosave_failed
        self._on_autosave_success = on_autosave_success

        # Track pending changes
        self._pending_changes: set[PendingChangeType] = set()

        # Capture the date at the time a save is requested (not when debounce fires)
        self._pending_save_file: str | None = None
        self._pending_save_date: str | None = None

        # MED-004 FIX: Track autosave status for UI feedback
        self._last_autosave_error: str | None = None
        self._autosave_failed: bool = False

        # Pause flag for modal dialogs
        self._paused: bool = False

        # Debounce timer
        self._save_timer = QTimer()
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._execute_save)

        # Subscribe to store
        self._unsubscribe = store.subscribe(self._on_state_change)

        # Track last known config hash for change detection
        self._last_config_hash: int | None = None

        # Reusable session state manager for JSON backups (avoid creating new instance each time)
        self._session_manager: Any = None

        logger.info("AutosaveCoordinator initialized with %dms debounce", self.config.debounce_ms)

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """
        Handle Redux store state changes.

        Detects what changed and schedules debounced save.

        Args:
            old_state: Previous state
            new_state: New state

        """
        if not self.config.enabled or self._paused:
            return

        # Detect when auto-save is RE-ENABLED while markers are already dirty
        # This handles: auto→manual (make changes)→auto scenario
        auto_save_just_enabled = not old_state.auto_save_enabled and new_state.auto_save_enabled
        if auto_save_just_enabled:
            if new_state.sleep_markers_dirty:
                self._pending_changes.add(PendingChangeType.SLEEP_MARKERS)
                logger.debug("Auto-save re-enabled with dirty sleep markers, scheduling save")
            if new_state.nonwear_markers_dirty:
                self._pending_changes.add(PendingChangeType.NONWEAR_MARKERS)
                logger.debug("Auto-save re-enabled with dirty nonwear markers, scheduling save")

        # Only autosave markers if auto_save_enabled in Redux state
        # (user can toggle via checkbox - respects their preference)
        if new_state.auto_save_enabled:
            # Detect sleep marker changes (dirty flag set)
            if not old_state.sleep_markers_dirty and new_state.sleep_markers_dirty:
                self._pending_changes.add(PendingChangeType.SLEEP_MARKERS)
                # Capture current file/date NOW (not when debounce fires)
                self._capture_pending_context(new_state)
                logger.debug("Sleep markers changed, scheduling autosave")

            # Detect nonwear marker changes (dirty flag set)
            if not old_state.nonwear_markers_dirty and new_state.nonwear_markers_dirty:
                self._pending_changes.add(PendingChangeType.NONWEAR_MARKERS)
                self._capture_pending_context(new_state)
                logger.debug("Nonwear markers changed, scheduling autosave")

        # Detect window geometry changes
        if (
            old_state.window_x != new_state.window_x
            or old_state.window_y != new_state.window_y
            or old_state.window_width != new_state.window_width
            or old_state.window_height != new_state.window_height
            or old_state.window_maximized != new_state.window_maximized
        ):
            self._pending_changes.add(PendingChangeType.WINDOW_STATE)
            logger.debug("Window state changed, scheduling autosave")

        # Detect config-related changes (view mode, database mode, etc.)
        if (
            old_state.view_mode_hours != new_state.view_mode_hours
            or old_state.database_mode != new_state.database_mode
            or old_state.current_file != new_state.current_file
        ):
            self._pending_changes.add(PendingChangeType.CONFIG)
            logger.debug("Config changed, scheduling autosave")

        # Schedule debounced save if we have pending changes
        if self._pending_changes:
            self._save_timer.stop()
            self._save_timer.start(self.config.debounce_ms)

    def _execute_save(self) -> None:
        """
        Execute batched save for all pending changes.

        This is called after the debounce timer expires.
        Saves BOTH sleep and nonwear markers together, then dispatches
        markers_saved() ONCE to clear both dirty flags.
        """
        if not self._pending_changes:
            return

        logger.debug("Executing autosave for: %s", self._pending_changes)

        # Get current state
        state = self.store.state

        try:
            # Track if marker saves were attempted/succeeded.
            marker_save_attempted = False
            marker_save_failed = False

            # Save sleep markers if dirty
            if PendingChangeType.SLEEP_MARKERS in self._pending_changes:
                if state.sleep_markers_dirty and state.current_sleep_markers is not None:
                    marker_save_attempted = True
                    if not self._save_sleep_markers(state):
                        marker_save_failed = True

            # Save nonwear markers if dirty
            if PendingChangeType.NONWEAR_MARKERS in self._pending_changes:
                if state.nonwear_markers_dirty and state.current_nonwear_markers is not None:
                    marker_save_attempted = True
                    if not self._save_nonwear_markers(state):
                        marker_save_failed = True

            # If any marker save failed, keep dirty flags and pending changes for retry.
            if marker_save_failed:
                error_msg = "Autosave failed: failed to persist one or more marker save operations"
                self._autosave_failed = True
                self._last_autosave_error = error_msg
                logger.error(error_msg)
                if self._on_autosave_failed:
                    self._on_autosave_failed(error_msg)
                return

            # Dispatch markers_saved ONCE after both saves complete
            if marker_save_attempted:
                from sleep_scoring_app.ui.store import Actions

                self.store.dispatch(Actions.markers_saved())
                logger.debug("Dispatched markers_saved action after autosave")

            # Save window state
            if PendingChangeType.WINDOW_STATE in self._pending_changes:
                self._save_window_state(state)

            # Save config
            if PendingChangeType.CONFIG in self._pending_changes:
                self._save_config(state)

            # Backup settings to JSON ONLY when config or window state changed (not markers)
            if PendingChangeType.CONFIG in self._pending_changes or PendingChangeType.WINDOW_STATE in self._pending_changes:
                self._backup_settings_to_json()

            # Clear pending changes
            self._pending_changes.clear()

            # MED-004 FIX: Track success and notify UI
            self._autosave_failed = False
            self._last_autosave_error = None
            if self._on_autosave_success:
                self._on_autosave_success()

            logger.info("Autosave completed successfully")

        except Exception as e:
            # MED-004 FIX: Track failure and notify UI
            error_msg = f"Autosave failed: {e}"
            self._autosave_failed = True
            self._last_autosave_error = error_msg
            logger.exception("Error during autosave")

            # Notify UI of failure so user knows their data may not be saved
            if self._on_autosave_failed:
                self._on_autosave_failed(error_msg)

            # Keep pending changes for retry
            # Timer will be restarted if state changes again

    def _capture_pending_context(self, state: UIState) -> None:
        """Capture file/date at the time a marker save is requested."""
        self._pending_save_file = state.current_file
        if 0 <= state.current_date_index < len(state.available_dates):
            self._pending_save_date = state.available_dates[state.current_date_index]
        else:
            self._pending_save_date = None

    def pause(self) -> None:
        """Pause autosave (e.g., during modal dialogs)."""
        self._paused = True
        self._save_timer.stop()
        logger.debug("Autosave paused")

    def resume(self) -> None:
        """Resume autosave and flush any pending changes."""
        self._paused = False
        if self._pending_changes:
            self._save_timer.start(self.config.debounce_ms)
        logger.debug("Autosave resumed")

    def _save_sleep_markers(self, state: UIState) -> bool:
        """Save sleep markers to database via MainWindow callback."""
        try:
            if state.current_sleep_markers:
                # Call the MainWindow callback to perform the complex save
                save_ok = self.save_sleep_markers_callback(state.current_sleep_markers)
                logger.debug("Triggered save_sleep_markers_callback for autosave.")
                return bool(save_ok)

            logger.debug("No current_sleep_markers to autosave.")
            return True

        except Exception:
            logger.exception("Error saving sleep markers via callback")
            return False

    def _save_nonwear_markers(self, state: UIState) -> bool:
        """Save nonwear markers to database via MainWindow callback."""
        try:
            if state.current_nonwear_markers is not None:
                # Use `is not None` (not truthiness) because DailyNonwearMarkers has
                # __len__ — an empty object is falsy but must still trigger a save
                # to DELETE stale records from the database.
                save_ok = self.save_nonwear_markers_callback(state.current_nonwear_markers)
                logger.debug("Triggered save_nonwear_markers_callback for autosave.")
                return bool(save_ok)

            logger.debug("No current_nonwear_markers to autosave.")
            return True

        except Exception:
            logger.exception("Error saving nonwear markers via callback")
            return False

    def _save_window_state(self, state: UIState) -> None:
        """Save window geometry to QSettings."""
        try:
            from PyQt6.QtCore import QSettings

            settings = QSettings("SleepResearch", "SleepScoringApp")

            if state.window_x is not None:
                settings.setValue("window_x", state.window_x)
            if state.window_y is not None:
                settings.setValue("window_y", state.window_y)
            if state.window_width is not None:
                settings.setValue("window_width", state.window_width)
            if state.window_height is not None:
                settings.setValue("window_height", state.window_height)

            settings.setValue("window_maximized", state.window_maximized)

            logger.debug("Saved window state to QSettings")

        except Exception:
            logger.exception("Error saving window state")

    def _save_config(self, state: UIState) -> None:
        """
        Save config changes to QSettings.

        This handles both Redux state config (view_mode, database_mode)
        and AppConfig changes (patterns, groups, timepoints) by delegating
        to config_manager.
        """
        try:
            from PyQt6.QtCore import QSettings

            settings = QSettings("SleepResearch", "SleepScoringApp")

            # Save Redux state config
            settings.setValue("view_mode_hours", state.view_mode_hours)
            settings.setValue("database_mode", state.database_mode)

            if state.current_file:
                settings.setValue("current_file", state.current_file)

            # Save full AppConfig via config_manager
            # This ensures ALL config fields are persisted (patterns, groups, etc.)
            if self.config_manager and self.config_manager.config:
                self.config_manager.save_config()

            logger.debug("Saved config to QSettings")

        except Exception:
            logger.exception("Error saving config")

    def _backup_settings_to_json(self) -> None:
        """Backup all QSettings to JSON file for portability."""
        try:
            logger.info("Starting settings backup to JSON")
            from sleep_scoring_app.ui.services import SessionStateService

            # Reuse session service instance (lazy initialization)
            if self._session_manager is None:
                self._session_manager = SessionStateService()
            result = self._session_manager.backup_to_json()
            if result:
                logger.info("Settings backup completed: %s", result)
            else:
                logger.warning("Settings backup returned None")

        except Exception:
            logger.exception("Error backing up settings to JSON")

    def schedule_config_save(self) -> None:
        """
        Schedule a debounced config save.

        Call this method whenever config changes occur (pattern edits, group/timepoint changes, etc.)
        This replaces individual timer-based autosaves with unified debouncing.
        """
        self._pending_changes.add(PendingChangeType.CONFIG)

        # Restart debounce timer
        self._save_timer.stop()
        self._save_timer.start(self.config.debounce_ms)

        logger.debug("Scheduled config save")

    def force_save(self) -> None:
        """
        Force immediate save of all pending changes.

        This should be called during application shutdown to ensure
        all changes are persisted before exit.
        """
        # Stop debounce timer
        self._save_timer.stop()

        # Execute save immediately
        if self._pending_changes:
            logger.info("Force saving pending changes: %s", self._pending_changes)
            self._execute_save()

    def cleanup(self) -> None:
        """Cleanup resources and unsubscribe from store."""
        # Stop timer
        self._save_timer.stop()

        # Unsubscribe from store
        if self._unsubscribe:
            self._unsubscribe()

        logger.info("AutosaveCoordinator cleaned up")

    # MED-004 FIX: Properties for UI to check autosave status

    @property
    def has_unsaved_changes(self) -> bool:
        """Check if there are pending changes that haven't been saved yet."""
        return bool(self._pending_changes)

    @property
    def autosave_failed(self) -> bool:
        """Check if the last autosave attempt failed."""
        return self._autosave_failed

    @property
    def last_autosave_error(self) -> str | None:
        """Get the error message from the last failed autosave, if any."""
        return self._last_autosave_error

    def get_pending_change_types(self) -> list[str]:
        """Get list of pending change types for UI display."""
        return [str(change_type) for change_type in self._pending_changes]
