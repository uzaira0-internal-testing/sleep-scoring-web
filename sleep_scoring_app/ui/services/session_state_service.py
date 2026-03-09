#!/usr/bin/env python3
"""
Session state service using QSettings (platform-native storage).
This is the PRIMARY session recovery mechanism.

Also provides JSON backup for portability and recovery.
"""

from __future__ import annotations

import base64
import json
import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

if TYPE_CHECKING:
    from pathlib import Path

    from PyQt6.QtWidgets import QMainWindow


logger = logging.getLogger(__name__)


class SessionStateService:
    r"""
    Manages session state using QSettings (platform-native storage).

    Storage locations:
    - Windows: Registry under HKEY_CURRENT_USER\\Software\\SleepResearch\\SleepScoringApp
    - macOS: ~/Library/Preferences/com.sleepresearch.sleepscoringapp.plist
    - Linux: ~/.config/SleepResearch/SleepScoringApp.conf
    """

    # Session keys - use constants, not magic strings
    KEY_CURRENT_FILE = "session/current_file"
    KEY_DATE_INDEX = "session/current_date_index"
    KEY_VIEW_MODE = "session/view_mode_hours"
    KEY_CURRENT_TAB = "session/current_tab"
    KEY_WINDOW_GEOMETRY = "session/window_geometry"
    KEY_WINDOW_STATE = "session/window_state"

    # Splitter state keys
    KEY_SPLITTER_TOP_LEVEL = "layout/splitter_top_level"
    KEY_SPLITTER_MAIN = "layout/splitter_main"
    KEY_SPLITTER_PLOT_TABLES = "layout/splitter_plot_tables"

    def __init__(self) -> None:
        self._settings = QSettings("SleepResearch", "SleepScoringApp")
        logger.debug(
            "SessionStateService initialized, storage: %s",
            self._settings.fileName(),
        )

    # ==================== Navigation State ====================

    def save_current_file(self, filename: str | None) -> None:
        """Save currently selected file."""
        if filename:
            self._settings.setValue(self.KEY_CURRENT_FILE, filename)
        else:
            self._settings.remove(self.KEY_CURRENT_FILE)
        self._settings.sync()

    def get_current_file(self) -> str | None:
        """Get last selected file, or None if not set."""
        value = self._settings.value(self.KEY_CURRENT_FILE, None)
        return str(value) if value else None

    def save_current_date_index(self, index: int) -> None:
        """Save current date index."""
        self._settings.setValue(self.KEY_DATE_INDEX, index)
        self._settings.sync()

    def get_current_date_index(self) -> int:
        """Get last date index, defaults to 0."""
        value = self._settings.value(self.KEY_DATE_INDEX, 0)
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    # ==================== View State ====================

    def save_view_mode(self, hours: int) -> None:
        """Save current view mode (24/48 hours)."""
        self._settings.setValue(self.KEY_VIEW_MODE, hours)
        # Don't sync here - less critical

    def get_view_mode(self) -> int:
        """Get last view mode, defaults to 24."""
        value = self._settings.value(self.KEY_VIEW_MODE, 24)
        try:
            hours = int(value)  # type: ignore[arg-type]
            # Validate - only 24 or 48 are valid
            return hours if hours in (24, 48) else 24
        except (TypeError, ValueError):
            return 24

    def save_current_tab(self, tab_index: int) -> None:
        """Save current tab index."""
        self._settings.setValue(self.KEY_CURRENT_TAB, tab_index)
        # Don't sync here - less critical

    def get_current_tab(self) -> int:
        """Get last tab index, defaults to 0."""
        value = self._settings.value(self.KEY_CURRENT_TAB, 0)
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0

    # ==================== Window State ====================

    def save_window_geometry(self, window: QMainWindow) -> None:
        """Save window geometry and state."""
        self._settings.setValue(self.KEY_WINDOW_GEOMETRY, window.saveGeometry())
        self._settings.setValue(self.KEY_WINDOW_STATE, window.saveState())
        self._settings.sync()

    def restore_window_geometry(self, window: QMainWindow) -> bool:
        """
        Restore window geometry and state.

        Returns True if geometry was restored, False if using defaults.
        Validates that window is on-screen before restoring.
        """
        geometry = self._settings.value(self.KEY_WINDOW_GEOMETRY)
        state = self._settings.value(self.KEY_WINDOW_STATE)

        if geometry is None:
            logger.debug("No saved geometry, using defaults")
            return False

        # Restore geometry
        window.restoreGeometry(geometry)

        # Validate window is on a visible screen
        if not self._is_window_visible(window):
            logger.warning("Saved geometry is off-screen, resetting to default")
            window.setGeometry(100, 100, 1200, 800)
            return False

        # Restore window state (toolbars, docks, etc.)
        if state:
            window.restoreState(state)

        logger.debug("Restored window geometry")
        return True

    def _is_window_visible(self, window: QMainWindow) -> bool:
        """Check if window is visible on any screen."""
        app = QApplication.instance()
        if app is None or not isinstance(app, QApplication):
            return True  # Can't check, assume OK

        window_rect = window.geometry()
        screens = app.screens()

        return any(screen.availableGeometry().intersects(window_rect) for screen in screens)

    # ==================== Batch Operations ====================

    def save_all(
        self,
        current_file: str | None,
        date_index: int,
        view_mode: int,
        current_tab: int,
        window: QMainWindow,
    ) -> None:
        """Save all session state at once (for app close)."""
        if current_file:
            self._settings.setValue(self.KEY_CURRENT_FILE, current_file)
        self._settings.setValue(self.KEY_DATE_INDEX, date_index)
        self._settings.setValue(self.KEY_VIEW_MODE, view_mode)
        self._settings.setValue(self.KEY_CURRENT_TAB, current_tab)
        self._settings.setValue(self.KEY_WINDOW_GEOMETRY, window.saveGeometry())
        self._settings.setValue(self.KEY_WINDOW_STATE, window.saveState())
        self._settings.sync()
        self.backup_to_json()  # Also save to JSON backup
        logger.info("Saved all session state")

    def clear_session(self) -> None:
        """Clear all session state (for explicit reset)."""
        self._settings.remove("session")
        self._settings.sync()
        logger.info("Cleared session state")

    def clear_file_selection(self) -> None:
        """Clear just the file selection (when file no longer exists)."""
        self._settings.remove(self.KEY_CURRENT_FILE)
        self._settings.remove(self.KEY_DATE_INDEX)
        self._settings.sync()

    # ==================== Splitter State ====================

    def save_splitter_states(
        self,
        top_level_state: bytes | None,
        main_state: bytes | None,
        plot_tables_state: bytes | None,
    ) -> None:
        """Save splitter states for layout persistence."""
        if top_level_state:
            self._settings.setValue(self.KEY_SPLITTER_TOP_LEVEL, top_level_state)
        if main_state:
            self._settings.setValue(self.KEY_SPLITTER_MAIN, main_state)
        if plot_tables_state:
            self._settings.setValue(self.KEY_SPLITTER_PLOT_TABLES, plot_tables_state)
        self._settings.sync()
        self.backup_to_json()  # Also save to JSON backup
        logger.debug("Saved splitter states")

    def get_splitter_states(self) -> tuple[bytes | None, bytes | None, bytes | None]:
        """Get saved splitter states."""
        top_level = self._settings.value(self.KEY_SPLITTER_TOP_LEVEL)
        main = self._settings.value(self.KEY_SPLITTER_MAIN)
        plot_tables = self._settings.value(self.KEY_SPLITTER_PLOT_TABLES)

        return (
            bytes(top_level) if top_level else None,
            bytes(main) if main else None,
            bytes(plot_tables) if plot_tables else None,
        )

    # ==================== JSON Backup ====================

    def _get_backup_path(self) -> Path:
        """Get the path to the JSON backup file."""
        from sleep_scoring_app.utils.resource_resolver import get_settings_backup_path

        return get_settings_backup_path()

    def _collect_all_settings(self) -> dict[str, Any]:
        """Collect all QSettings keys and values into a dictionary."""
        from PyQt6.QtCore import QByteArray

        result: dict[str, Any] = {}

        def collect_group(prefix: str = "") -> None:
            """Recursively collect all keys from the current group."""
            for key in self._settings.childKeys():
                full_key = f"{prefix}{key}" if prefix else key

                try:
                    value = self._settings.value(key)

                    # Handle QByteArray explicitly
                    if isinstance(value, QByteArray):
                        result[full_key] = {"_type": "bytes", "_value": base64.b64encode(bytes(value)).decode("ascii")}
                    # Handle binary data (bytes/bytearray) by base64 encoding
                    elif isinstance(value, bytes | bytearray):
                        result[full_key] = {"_type": "bytes", "_value": base64.b64encode(value).decode("ascii")}
                    elif value is None:
                        result[full_key] = {"_type": "none", "_value": None}
                    else:
                        # Store primitive types directly
                        result[full_key] = value

                except TypeError:
                    # Some QVariant types can't be converted - skip them
                    logger.debug("Skipping key %s - cannot convert QVariant to Python", full_key)

            # Recurse into child groups
            for group in self._settings.childGroups():
                self._settings.beginGroup(group)
                collect_group(f"{prefix}{group}/")
                self._settings.endGroup()

        collect_group()
        return result

    def backup_to_json(self) -> Path | None:
        """
        Export all QSettings to a JSON backup file.

        Returns the path to the backup file, or None if backup failed.
        """
        try:
            from pathlib import Path as PathLib

            backup_path = self._get_backup_path()
            logger.info("Attempting to backup settings to: %s", backup_path)

            # Ensure parent directory exists
            PathLib(backup_path).parent.mkdir(parents=True, exist_ok=True)

            settings_data = self._collect_all_settings()
            logger.info("Collected %d settings keys", len(settings_data))

            # Add metadata
            from datetime import datetime

            backup_data = {
                "_metadata": {
                    "created_at": datetime.now().isoformat(),
                    "app": "SleepScoringApp",
                    "version": "1.0",
                },
                "settings": settings_data,
            }

            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2, default=str)

            logger.info("Successfully backed up settings to JSON: %s", backup_path)
            return PathLib(backup_path)

        except Exception:
            logger.exception("Failed to backup settings to JSON")
            return None

    def restore_from_json(self, backup_path: Path | None = None) -> bool:
        """
        Restore all settings from a JSON backup file.

        Args:
            backup_path: Path to backup file. If None, uses default location.

        Returns:
            True if restore succeeded, False otherwise.

        """
        try:
            if backup_path is None:
                backup_path = self._get_backup_path()

            if not backup_path.exists():
                logger.warning("No backup file found at: %s", backup_path)
                return False

            with open(backup_path, encoding="utf-8") as f:
                backup_data = json.load(f)

            settings_data = backup_data.get("settings", {})

            # Clear existing settings first
            self._settings.clear()

            # Restore all settings
            for key, value in settings_data.items():
                if isinstance(value, dict) and "_type" in value:
                    # Handle special types
                    if value["_type"] == "bytes":
                        decoded = base64.b64decode(value["_value"])
                        self._settings.setValue(key, decoded)
                    elif value["_type"] == "none":
                        # Skip None values
                        pass
                else:
                    self._settings.setValue(key, value)

            self._settings.sync()
            logger.info("Restored settings from JSON backup: %s", backup_path)
            return True

        except Exception:
            logger.exception("Failed to restore settings from JSON")
            return False

    def sync_with_json_backup(self) -> None:
        """Sync current QSettings to JSON backup (call after saves)."""
        self.backup_to_json()
