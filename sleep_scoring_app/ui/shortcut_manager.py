#!/usr/bin/env python3
"""
Shortcut Manager for Sleep Scoring Application.

Centralizes keyboard shortcut handling for the main window.
Provides a clean interface for registering and managing shortcuts.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject
from PyQt6.QtGui import QKeySequence, QShortcut

if TYPE_CHECKING:
    from collections.abc import Callable

    from PyQt6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class ShortcutManager(QObject):
    """
    Manager for keyboard shortcuts.

    Provides centralized shortcut registration and management.
    Supports context-aware shortcuts that can be enabled/disabled.
    """

    def __init__(self, parent_widget: QWidget) -> None:
        """
        Initialize the shortcut manager.

        Args:
            parent_widget: The widget that owns the shortcuts (usually MainWindow)

        """
        super().__init__(parent_widget)
        self._parent_widget = parent_widget
        self._shortcuts: dict[str, QShortcut] = {}
        self._contexts: dict[str, bool] = {}

        logger.info("ShortcutManager initialized")

    def register_shortcut(
        self,
        name: str,
        key_sequence: str | QKeySequence,
        callback: Callable[[], None],
        context: str = "global",
        enabled: bool = True,
    ) -> QShortcut:
        """
        Register a new keyboard shortcut.

        Args:
            name: Unique name for the shortcut
            key_sequence: Key sequence string (e.g., "Ctrl+S") or QKeySequence
            callback: Function to call when shortcut is triggered
            context: Context name for enabling/disabling groups
            enabled: Whether shortcut is initially enabled

        Returns:
            The created QShortcut object

        """
        if isinstance(key_sequence, str):
            key_sequence = QKeySequence(key_sequence)

        shortcut = QShortcut(key_sequence, self._parent_widget)
        shortcut.activated.connect(callback)
        shortcut.setEnabled(enabled)

        self._shortcuts[name] = shortcut
        self._contexts.setdefault(context, True)

        logger.debug("Registered shortcut: %s -> %s", name, key_sequence.toString())
        return shortcut

    def unregister_shortcut(self, name: str) -> bool:
        """
        Unregister a shortcut by name.

        Args:
            name: The shortcut name to remove

        Returns:
            True if shortcut was found and removed

        """
        if name in self._shortcuts:
            shortcut = self._shortcuts.pop(name)
            shortcut.setEnabled(False)
            shortcut.deleteLater()
            logger.debug("Unregistered shortcut: %s", name)
            return True
        return False

    def enable_shortcut(self, name: str) -> bool:
        """
        Enable a specific shortcut.

        Args:
            name: The shortcut name

        Returns:
            True if shortcut was found

        """
        if name in self._shortcuts:
            self._shortcuts[name].setEnabled(True)
            return True
        return False

    def disable_shortcut(self, name: str) -> bool:
        """
        Disable a specific shortcut.

        Args:
            name: The shortcut name

        Returns:
            True if shortcut was found

        """
        if name in self._shortcuts:
            self._shortcuts[name].setEnabled(False)
            return True
        return False

    def enable_context(self, context: str) -> None:
        """
        Enable all shortcuts in a context.

        Args:
            context: The context name

        """
        self._contexts[context] = True
        # Note: Individual shortcuts would need context tracking
        # to implement full context-based enabling
        logger.debug("Enabled context: %s", context)

    def disable_context(self, context: str) -> None:
        """
        Disable all shortcuts in a context.

        Args:
            context: The context name

        """
        self._contexts[context] = False
        logger.debug("Disabled context: %s", context)

    def is_context_enabled(self, context: str) -> bool:
        """Check if a context is enabled."""
        return self._contexts.get(context, True)

    def get_shortcut(self, name: str) -> QShortcut | None:
        """Get a shortcut by name."""
        return self._shortcuts.get(name)

    def get_all_shortcuts(self) -> dict[str, QShortcut]:
        """Get all registered shortcuts."""
        return dict(self._shortcuts)

    def clear_all(self) -> None:
        """Remove all shortcuts."""
        for name in list(self._shortcuts.keys()):
            self.unregister_shortcut(name)
        self._contexts.clear()
        logger.debug("Cleared all shortcuts")

    def setup_default_shortcuts(self, callbacks: dict[str, Callable]) -> None:
        """
        Setup default application shortcuts.

        Args:
            callbacks: Dictionary mapping shortcut names to callbacks
                Expected keys:
                - save_markers
                - prev_date
                - next_date
                - clear_markers
                - toggle_view_mode

        """
        default_shortcuts = [
            ("save_markers", "Ctrl+S", "save_markers"),
            ("prev_date", "Left", "prev_date"),
            ("next_date", "Right", "next_date"),
            ("clear_markers", "Ctrl+Shift+C", "clear_markers"),
            ("toggle_48h", "Ctrl+4", "toggle_view_mode"),
        ]

        for name, key, callback_name in default_shortcuts:
            if callback_name in callbacks:
                self.register_shortcut(name, key, callbacks[callback_name])
            else:
                logger.debug("Callback not provided for shortcut: %s", name)
