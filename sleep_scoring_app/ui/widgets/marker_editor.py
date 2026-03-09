#!/usr/bin/env python3
"""
Simple FSM for marker editing modes.

This module provides a lightweight state machine for managing marker editing
interactions, handling transitions between IDLE, PLACING_ONSET, PLACING_OFFSET,
and DRAGGING states.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt

from sleep_scoring_app.core.constants import EditMode

if TYPE_CHECKING:
    from collections.abc import Callable

    from sleep_scoring_app.core.dataclasses_markers import SleepPeriod


class MarkerEditor:
    """
    Simple FSM for marker editing modes.

    Manages state transitions for marker placement and dragging operations.
    Uses a simple enum-based approach rather than full State pattern.
    """

    def __init__(self) -> None:
        self._mode = EditMode.IDLE
        self._drag_start: float | None = None
        self._dragging_marker: SleepPeriod | None = None

    @property
    def mode(self) -> EditMode:
        """Get current editing mode."""
        return self._mode

    def on_mouse_press(
        self,
        event,
        find_marker_fn: Callable[[object], SleepPeriod | None],
        needs_onset_fn: Callable[[], bool],
    ) -> None:
        """
        Handle mouse press based on current mode.

        Args:
            event: Mouse press event
            find_marker_fn: Function to find marker at event position
            needs_onset_fn: Function that returns True if we need to place onset

        """
        match self._mode:
            case EditMode.IDLE:
                marker = find_marker_fn(event.pos())
                if marker:
                    self._mode = EditMode.DRAGGING
                    self._drag_start = marker.onset_timestamp
                    self._dragging_marker = marker
                elif needs_onset_fn():
                    self._mode = EditMode.PLACING_ONSET

            case EditMode.PLACING_ONSET:
                # Place onset, transition to placing offset
                self._mode = EditMode.PLACING_OFFSET

            case EditMode.PLACING_OFFSET:
                # Place offset, return to idle
                self._mode = EditMode.IDLE

    def on_mouse_release(self) -> tuple[float | None, float | None]:
        """
        Handle mouse release. Returns (start_ts, end_ts) if drag completed.

        Returns:
            Tuple of (drag_start_timestamp, drag_end_timestamp) if dragging was active,
            otherwise (None, None)

        """
        if self._mode == EditMode.DRAGGING:
            result = (
                self._drag_start,
                self._dragging_marker.onset_timestamp if self._dragging_marker else None,
            )
            self._mode = EditMode.IDLE
            self._drag_start = None
            self._dragging_marker = None
            return result
        return (None, None)

    def on_key_press(self, key: int) -> bool:
        """
        Handle key press. Returns True if handled.

        Args:
            key: Qt key code

        Returns:
            True if the key was handled, False otherwise

        """
        if key == Qt.Key.Key_Escape:
            self._mode = EditMode.IDLE
            self._drag_start = None
            self._dragging_marker = None
            return True
        return False

    @property
    def cursor(self) -> Qt.CursorShape:
        """Get cursor for current mode."""
        return {
            EditMode.IDLE: Qt.CursorShape.ArrowCursor,
            EditMode.PLACING_ONSET: Qt.CursorShape.CrossCursor,
            EditMode.PLACING_OFFSET: Qt.CursorShape.CrossCursor,
            EditMode.DRAGGING: Qt.CursorShape.ClosedHandCursor,
        }[self._mode]

    @property
    def status_text(self) -> str:
        """Get status message for current mode."""
        return {
            EditMode.IDLE: "Click to place marker or drag existing",
            EditMode.PLACING_ONSET: "Click to place ONSET (Esc to cancel)",
            EditMode.PLACING_OFFSET: "Click to place OFFSET (Esc to cancel)",
            EditMode.DRAGGING: "Release to place marker",
        }[self._mode]
