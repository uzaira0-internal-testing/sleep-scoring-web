"""
Sleep period detection protocol for dependency injection.

This protocol defines the interface that all sleep period detection rule implementations
must follow. Enables swappable rules without changing core application logic.

Critical distinction:
- Sleep scoring algorithms (Sadeh, Cole-Kripke) classify each epoch as sleep/wake
- Sleep period detectors find sleep period boundaries (onset/offset) within classified data
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime


@runtime_checkable
class SleepPeriodDetector(Protocol):
    """
    Protocol for sleep period detection rules.

    All rule implementations (ConsecutiveMinutesRule, TudorLockeRule, etc.) must
    implement this interface.

    The detector operates on already-classified sleep/wake data to identify the precise
    boundaries (onset and offset) of sleep periods.
    """

    @property
    def name(self) -> str:
        """
        Rule name for display and identification.

        Returns:
            Human-readable rule name (e.g., "Consecutive 3/5 Minutes", "Tudor-Locke (2014)")

        """
        ...

    @property
    def identifier(self) -> str:
        """
        Unique rule identifier for storage and configuration.

        Returns:
            Snake_case identifier (e.g., "consecutive_3_5", "tudor_locke_2014")

        """
        ...

    @property
    def description(self) -> str:
        """
        Brief description of the rule logic.

        Returns:
            User-friendly description for tooltips/documentation

        """
        ...

    def apply_rules(
        self,
        sleep_scores: list[int],
        sleep_start_marker: datetime,
        sleep_end_marker: datetime,
        timestamps: list[datetime],
    ) -> tuple[int | None, int | None]:
        """
        Apply detection rules to find sleep period boundaries.

        Args:
            sleep_scores: List of sleep/wake classifications (1=sleep, 0=wake)
            sleep_start_marker: User-provided approximate sleep start time
            sleep_end_marker: User-provided approximate sleep end time
            timestamps: List of timestamps corresponding to sleep_scores

        Returns:
            Tuple of (onset_index, offset_index), or (None, None) if not found

        Raises:
            ValueError: If input data is invalid or inconsistent

        """
        ...

    def get_parameters(self) -> dict[str, Any]:
        """
        Get current rule parameters.

        Returns:
            Dictionary of parameter names and values

        """
        ...

    def set_parameters(self, **kwargs: Any) -> None:
        """
        Update rule parameters.

        Args:
            **kwargs: Parameter name-value pairs

        Raises:
            ValueError: If parameter name is invalid or value is out of range

        """
        ...

    def get_marker_labels(self, onset_time: str, offset_time: str) -> tuple[str, str]:
        """
        Get UI marker label text for this rule.

        Args:
            onset_time: Onset time in HH:MM format
            offset_time: Offset time in HH:MM format

        Returns:
            Tuple of (onset_label, offset_label) for display in UI

        """
        ...
