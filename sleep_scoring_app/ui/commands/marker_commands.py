"""Marker-specific commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sleep_scoring_app.ui.commands.base import Command

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import DailySleepMarkers


@dataclass
class PlaceMarkerCommand(Command):
    """Command for placing a marker at a timestamp."""

    markers: DailySleepMarkers
    timestamp: float
    is_onset: bool
    period_index: int

    def execute(self) -> None:
        """Place the marker."""
        period = self.markers.get_period_by_slot(self.period_index)
        if period is None:
            return
        if self.is_onset:
            period.onset_timestamp = self.timestamp
        else:
            period.offset_timestamp = self.timestamp

    def undo(self) -> None:
        """Remove the marker."""
        period = self.markers.get_period_by_slot(self.period_index)
        if period is None:
            return
        if self.is_onset:
            period.onset_timestamp = None
        else:
            period.offset_timestamp = None

    @property
    def description(self) -> str:
        """Human-readable description."""
        marker_type = "onset" if self.is_onset else "offset"
        return f"Place {marker_type} marker"


@dataclass
class MoveMarkerCommand(Command):
    """Command for moving a marker (after drag completes)."""

    markers: DailySleepMarkers
    period_index: int
    is_onset: bool
    from_timestamp: float
    to_timestamp: float

    def execute(self) -> None:
        """Move marker to new position."""
        period = self.markers.get_period_by_slot(self.period_index)
        if period is None:
            return
        if self.is_onset:
            period.onset_timestamp = self.to_timestamp
        else:
            period.offset_timestamp = self.to_timestamp

    def undo(self) -> None:
        """Restore marker to original position."""
        period = self.markers.get_period_by_slot(self.period_index)
        if period is None:
            return
        if self.is_onset:
            period.onset_timestamp = self.from_timestamp
        else:
            period.offset_timestamp = self.from_timestamp

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Move marker"


@dataclass
class DeleteMarkerCommand(Command):
    """Command for deleting a marker."""

    markers: DailySleepMarkers
    period_index: int
    is_onset: bool
    deleted_timestamp: float

    def execute(self) -> None:
        """Delete the marker."""
        period = self.markers.get_period_by_slot(self.period_index)
        if period is None:
            return
        if self.is_onset:
            period.onset_timestamp = None
        else:
            period.offset_timestamp = None

    def undo(self) -> None:
        """Restore the deleted marker."""
        period = self.markers.get_period_by_slot(self.period_index)
        if period is None:
            return
        if self.is_onset:
            period.onset_timestamp = self.deleted_timestamp
        else:
            period.offset_timestamp = self.deleted_timestamp

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Delete marker"


@dataclass
class ClearAllMarkersCommand(Command):
    """Command for clearing all markers."""

    markers: DailySleepMarkers
    saved_state: dict[int, tuple[float | None, float | None]]

    def __init__(self, markers: DailySleepMarkers) -> None:
        """Initialize with markers and save current state."""
        self.markers = markers
        # Save current state of all periods
        self.saved_state = {}
        for i in range(1, 5):  # Periods 1-4
            period = markers.get_period_by_slot(i)
            if period is not None:
                self.saved_state[i] = (period.onset_timestamp, period.offset_timestamp)

    def execute(self) -> None:
        """Clear all markers."""
        for i in range(1, 5):
            period = self.markers.get_period_by_slot(i)
            if period is not None:
                period.onset_timestamp = None
                period.offset_timestamp = None

    def undo(self) -> None:
        """Restore all markers to saved state."""
        for i, (onset, offset) in self.saved_state.items():
            period = self.markers.get_period_by_slot(i)
            if period is not None:
                period.onset_timestamp = onset
                period.offset_timestamp = offset

    @property
    def description(self) -> str:
        """Human-readable description."""
        return "Clear all markers"
