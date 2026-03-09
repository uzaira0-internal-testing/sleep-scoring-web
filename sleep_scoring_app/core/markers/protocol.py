"""
Marker protocols and base classes for dependency inversion.

This module defines Protocol types and base classes for marker handling,
enabling consistent behavior between sleep markers and nonwear markers
through proper dependency injection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, TypeVar, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

# Type variable for marker period types
T = TypeVar("T", bound="MarkerPeriod")


@runtime_checkable
class MarkerPeriod(Protocol):
    """
    Protocol defining the interface for a marker period.

    Both SleepPeriod and ManualNonwearPeriod implement this protocol,
    allowing them to be treated uniformly for persistence and UI operations.
    """

    marker_index: int

    @property
    def is_complete(self) -> bool:
        """Check if both start and end markers are set."""
        ...

    @property
    def start_timestamp(self) -> float | None:
        """Get the start timestamp (onset for sleep, start for nonwear)."""
        ...

    @property
    def end_timestamp(self) -> float | None:
        """Get the end timestamp (offset for sleep, end for nonwear)."""
        ...

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        ...

    @property
    def duration_minutes(self) -> float | None:
        """Calculate duration in minutes."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        ...


@runtime_checkable
class DailyMarkersProtocol(Protocol[T]):
    """
    Protocol defining the interface for daily marker containers.

    Both DailySleepMarkers and DailyNonwearMarkers implement this protocol,
    enabling consistent handling of marker collections.
    """

    def get_all_periods(self) -> list[T]:
        """Get all non-None periods."""
        ...

    def get_complete_periods(self) -> list[T]:
        """Get all complete periods (both start and end set)."""
        ...

    def count_periods(self) -> int:
        """Count number of defined periods."""
        ...

    def has_space_for_new_period(self) -> bool:
        """Check if we can add another period."""
        ...

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        ...


@runtime_checkable
class MarkerPersistence(Protocol):
    """
    Protocol for marker persistence operations.

    This protocol abstracts the save/load behavior for markers,
    allowing both sleep and nonwear markers to use the same
    persistence interface through dependency injection.
    """

    def save(
        self,
        filename: str,
        participant_id: str,
        date: datetime,
        markers: DailyMarkersProtocol,
        **kwargs: Any,
    ) -> bool:
        """
        Save markers to persistent storage.

        Args:
            filename: The source file name
            participant_id: Participant identifier
            date: The date for these markers
            markers: The daily markers container to save
            **kwargs: Additional arguments (e.g., sleep_metrics, algorithm_type)

        Returns:
            True if save succeeded, False otherwise

        """
        ...

    def load(
        self,
        filename: str,
        date: datetime,
    ) -> DailyMarkersProtocol | None:
        """
        Load markers from persistent storage.

        Args:
            filename: The source file name
            date: The date to load markers for

        Returns:
            The loaded markers container, or None if not found

        """
        ...

    def delete(
        self,
        filename: str,
        date: datetime,
    ) -> bool:
        """
        Delete markers from persistent storage.

        Args:
            filename: The source file name
            date: The date to delete markers for

        Returns:
            True if delete succeeded, False otherwise

        """
        ...


class MarkerChangeHandler(Protocol):
    """
    Protocol for handling marker change events.

    This enables the UI layer to be decoupled from the persistence layer.
    When markers change, the handler is invoked to perform any necessary
    operations (save, update UI, etc.).
    """

    def on_markers_changed(
        self,
        markers: DailyMarkersProtocol,
        filename: str,
        date: datetime,
    ) -> None:
        """
        Handle marker change event.

        Args:
            markers: The updated markers container
            filename: The source file name
            date: The date for these markers

        """
        ...


@runtime_checkable
class MetricsSaver(Protocol):
    """
    Protocol for saving sleep metrics.

    This protocol abstracts the export/save behavior needed by
    the marker persistence layer, avoiding direct service dependency.
    """

    def save_comprehensive_sleep_metrics(
        self,
        metrics_list: list[Any],
        algorithm_type: Any,
    ) -> bool:
        """
        Save comprehensive sleep metrics to persistent storage.

        Args:
            metrics_list: List of SleepMetrics to save
            algorithm_type: Algorithm type used for scoring

        Returns:
            True if save succeeded, False otherwise

        """
        ...


@dataclass
class MarkerPeriodBase(ABC):
    """
    Abstract base class for marker periods.

    Provides common implementation for duration calculations and
    serialization. Subclasses must define their specific timestamp fields.
    """

    marker_index: int = 1

    @property
    @abstractmethod
    def start_timestamp(self) -> float | None:
        """Get the start timestamp."""
        ...

    @property
    @abstractmethod
    def end_timestamp(self) -> float | None:
        """Get the end timestamp."""
        ...

    @property
    def is_complete(self) -> bool:
        """Check if both markers are set."""
        return self.start_timestamp is not None and self.end_timestamp is not None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        start = self.start_timestamp
        end = self.end_timestamp
        if start is not None and end is not None:
            return end - start
        return None

    @property
    def duration_minutes(self) -> float | None:
        """Calculate duration in minutes."""
        if self.duration_seconds is not None:
            return self.duration_seconds / 60
        return None

    @property
    def duration_hours(self) -> float | None:
        """Calculate duration in hours."""
        if self.duration_seconds is not None:
            return self.duration_seconds / 3600
        return None

    def to_list(self) -> list[float]:
        """Convert to list format for compatibility."""
        start = self.start_timestamp
        end = self.end_timestamp
        if start is not None and end is not None:
            return [start, end]
        return []

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        ...


@dataclass
class DailyMarkersBase[T: "MarkerPeriod"](ABC):
    """
    Abstract base class for daily marker containers.

    Provides common implementation for period management.
    Subclasses define the specific period slots and types.
    """

    @property
    @abstractmethod
    def _period_slots(self) -> list[T | None]:
        """Get list of all period slots."""
        ...

    @property
    @abstractmethod
    def max_periods(self) -> int:
        """Maximum number of periods allowed."""
        ...

    def get_all_periods(self) -> list[T]:
        """Get all non-None periods."""
        return [p for p in self._period_slots if p is not None]

    def get_complete_periods(self) -> list[T]:
        """Get all complete periods."""
        return [p for p in self.get_all_periods() if p.is_complete]

    def count_periods(self) -> int:
        """Count number of defined periods."""
        return len(self.get_all_periods())

    def has_space_for_new_period(self) -> bool:
        """Check if we can add another period."""
        return self.count_periods() < self.max_periods

    def get_next_available_slot(self) -> int | None:
        """Get the next available slot number, or None if full."""
        for i, period in enumerate(self._period_slots, start=1):
            if period is None:
                return i
        return None

    @abstractmethod
    def get_period_by_slot(self, slot: int) -> T | None:
        """Get period by slot number."""
        ...

    @abstractmethod
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        ...
