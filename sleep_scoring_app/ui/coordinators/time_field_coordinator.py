#!/usr/bin/env python3
"""
Time Field Coordinator
Manages time field validation and focus handling.
"""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QEvent, QObject, QTimer, pyqtSlot
from PyQt6.QtWidgets import QLineEdit

if TYPE_CHECKING:
    from sleep_scoring_app.ui.store import UIStore

logger = logging.getLogger(__name__)

# Delay before triggering update after focus-out event (milliseconds).
# This allows the field value to be fully committed before notifying listeners.
# Too short causes race conditions; too long feels sluggish to users.
FOCUS_OUT_UPDATE_DELAY_MS = 50


class TimeFieldFocusHandler(QObject):
    """Handle focus events for time fields."""

    def __init__(self, parent_coordinator: "TimeFieldCoordinator", field_name: str, parent=None) -> None:
        super().__init__(parent)
        self.parent_coordinator = parent_coordinator
        self.field_name = field_name
        self.initial_value = ""

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:  # type: ignore[override]
        """Filter events for time field focus tracking."""
        if event is None:
            return False
        if event.type() == QEvent.Type.FocusIn:
            # Store initial value when focus gained
            if isinstance(obj, QLineEdit):
                self.initial_value = obj.text()
        elif event.type() == QEvent.Type.FocusOut:
            # Check if value changed when focus lost
            if isinstance(obj, QLineEdit) and obj.text() != self.initial_value:
                # Trigger update via callback
                QTimer.singleShot(FOCUS_OUT_UPDATE_DELAY_MS, self.parent_coordinator.trigger_update)
        return False  # Don't consume the event


class TimeFieldCoordinator(QObject):
    """Manages time field validation and focus handling."""

    def __init__(
        self,
        store: "UIStore",
        onset_time_input: QLineEdit,
        offset_time_input: QLineEdit,
        total_duration_label,
        update_callback: Callable[..., Any],
    ) -> None:
        """
        Initialize the time field coordinator.

        Args:
            store: The UI store
            onset_time_input: The onset time input field
            offset_time_input: The offset time input field
            total_duration_label: Label showing total duration
            update_callback: Callback to trigger when fields change

        """
        super().__init__()
        self.store = store
        self.onset_time_input = onset_time_input
        self.offset_time_input = offset_time_input
        self.total_duration_label = total_duration_label
        self.update_callback = update_callback

        # Connect signals
        self.onset_time_input.returnPressed.connect(self.on_time_field_return_pressed)
        self.onset_time_input.textChanged.connect(self.on_time_input_changed)
        self.offset_time_input.returnPressed.connect(self.on_time_field_return_pressed)
        self.offset_time_input.textChanged.connect(self.on_time_input_changed)

        # Set up focus handling
        self.setup_time_field_focus_handling()

    def trigger_update(self) -> None:
        """Trigger the update callback."""
        if self.update_callback:
            self.update_callback()

    @pyqtSlot()
    def on_time_field_return_pressed(self) -> None:
        """Handle Return key press in time fields - immediate update."""
        self.trigger_update()

    @pyqtSlot()
    def on_time_input_changed(self) -> None:
        """Update total duration label when time input fields change."""
        from datetime import datetime, timedelta

        # Get text from both fields
        onset_text = self.onset_time_input.text().strip()
        offset_text = self.offset_time_input.text().strip()

        # Only calculate if both fields have valid time format (HH:MM)
        if not onset_text or not offset_text:
            self.total_duration_label.setText("")
            return

        try:
            # Parse times
            onset_time = datetime.strptime(onset_text, "%H:%M")
            offset_time = datetime.strptime(offset_text, "%H:%M")

            # Calculate duration (handle overnight sleep)
            if offset_time <= onset_time:
                # Overnight: add 24 hours to offset time
                offset_time += timedelta(days=1)

            duration = offset_time - onset_time
            duration_hours = duration.total_seconds() / 3600

            # Update label
            self.total_duration_label.setText(f"Total Duration: {duration_hours:.1f} hours")

        except ValueError:
            # Invalid time format - clear the label
            self.total_duration_label.setText("")

    def setup_time_field_focus_handling(self) -> None:
        """Set up focus handling for time fields to prevent update loops."""
        # Install event filters for more granular control
        self.onset_filter = TimeFieldFocusHandler(self, "onset", parent=self.onset_time_input)
        self.onset_time_input.installEventFilter(self.onset_filter)

        self.offset_filter = TimeFieldFocusHandler(self, "offset", parent=self.offset_time_input)
        self.offset_time_input.installEventFilter(self.offset_filter)
