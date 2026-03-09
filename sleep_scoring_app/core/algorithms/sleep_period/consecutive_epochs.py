"""
Consecutive epochs sleep period detection - Unified implementation.

This module implements a configurable sleep period detector that finds onset
and offset times based on consecutive epochs of a specified state.

Supports both:
- Traditional 3/5 rule (consecutive SLEEP epochs for both onset and offset)
- Tudor-Locke style (consecutive SLEEP for onset, consecutive WAKE for offset)
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from .config import (
    AnchorPosition,
    ConsecutiveEpochsSleepPeriodDetectorConfig,
    EpochState,
)

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class ConsecutiveEpochsSleepPeriodDetector:
    """
    Configurable consecutive epochs sleep period detector.

    This class implements the SleepPeriodDetector protocol using a configurable
    approach that supports different parameter combinations for onset and offset
    detection.

    Parameters are configured via SleepPeriodDetectionConsecutiveEpochsConfig:
    - onset_n, onset_state, onset_anchor: How to detect sleep onset
    - offset_n, offset_state, offset_anchor: How to detect sleep offset
    - offset_preceding_epoch: Whether to return epoch before detected run

    Example usage:
        ```python
        from sleep_scoring_app.core.algorithms.sleep_period import (
            ConsecutiveEpochsSleepPeriodDetector,
            ConsecutiveEpochsSleepPeriodDetectorConfig,
            EpochState,
            AnchorPosition,
        )

        # Traditional 3/5 rule
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            onset_n=3, onset_state=EpochState.SLEEP, onset_anchor=AnchorPosition.START,
            offset_n=5, offset_state=EpochState.SLEEP, offset_anchor=AnchorPosition.END,
        )
        detector = ConsecutiveEpochsSleepPeriodDetector(config=config)
        onset_idx, offset_idx = detector.apply_rules(sleep_scores, start, end, timestamps)
        ```
    """

    def __init__(
        self,
        config: ConsecutiveEpochsSleepPeriodDetectorConfig | None = None,
        *,
        preset_name: str | None = None,
    ) -> None:
        """
        Initialize detector with configuration.

        Args:
            config: Detection configuration (uses defaults if None)
            preset_name: Optional name for display purposes (e.g., "Tudor-Locke (2014)")

        """
        self.config = config or ConsecutiveEpochsSleepPeriodDetectorConfig()
        self._preset_name = preset_name

    # === Protocol Properties ===

    @property
    def name(self) -> str:
        """Human-readable detector name."""
        if self._preset_name:
            return self._preset_name

        onset_state = "S" if self.config.onset_state == EpochState.SLEEP else "W"
        offset_state = "S" if self.config.offset_state == EpochState.SLEEP else "W"
        return f"Consecutive {self.config.onset_n}{onset_state}/{self.config.offset_n}{offset_state}"

    @property
    def identifier(self) -> str:
        """Unique identifier for storage."""
        onset_state = "s" if self.config.onset_state == EpochState.SLEEP else "w"
        offset_state = "s" if self.config.offset_state == EpochState.SLEEP else "w"
        return f"consecutive_onset{self.config.onset_n}{onset_state}_offset{self.config.offset_n}{offset_state}"

    @property
    def description(self) -> str:
        """Brief description of detection logic."""
        onset_state_name = "Sleep" if self.config.onset_state == EpochState.SLEEP else "Wake"
        offset_state_name = "Sleep" if self.config.offset_state == EpochState.SLEEP else "Wake"
        onset_anchor_name = "first" if self.config.onset_anchor == AnchorPosition.START else "last"
        offset_anchor_name = "first" if self.config.offset_anchor == AnchorPosition.START else "last"

        onset_desc = f"Onset: {onset_anchor_name.capitalize()} epoch of {self.config.onset_n} consecutive {onset_state_name} epochs"
        offset_desc = f"Offset: {offset_anchor_name.capitalize()} epoch of {self.config.offset_n} consecutive {offset_state_name} epochs"

        if self.config.offset_preceding_epoch:
            offset_desc += " (preceding epoch)"

        return f"{onset_desc}. {offset_desc}. Search extension: +/-{self.config.search_extension_minutes} minutes."

    # === Protocol Methods ===

    def get_parameters(self) -> dict[str, Any]:
        """Get current detection parameters."""
        return {
            "onset_n": self.config.onset_n,
            "onset_state": self.config.onset_state.value,
            "onset_anchor": self.config.onset_anchor.value,
            "offset_n": self.config.offset_n,
            "offset_state": self.config.offset_state.value,
            "offset_anchor": self.config.offset_anchor.value,
            "offset_preceding_epoch": self.config.offset_preceding_epoch,
            "search_extension_minutes": self.config.search_extension_minutes,
        }

    def set_parameters(self, **kwargs: Any) -> None:
        """
        Update detection parameters.

        Args:
            **kwargs: Parameter name-value pairs

        Raises:
            ValueError: If parameter name is invalid

        """
        valid_params = {
            "onset_n",
            "onset_state",
            "onset_anchor",
            "offset_n",
            "offset_state",
            "offset_anchor",
            "offset_preceding_epoch",
            "search_extension_minutes",
        }
        invalid_params = set(kwargs.keys()) - valid_params
        if invalid_params:
            msg = f"Invalid parameters: {invalid_params}. Valid: {valid_params}"
            raise ValueError(msg)

        # Convert string values to enums if needed
        if "onset_state" in kwargs and isinstance(kwargs["onset_state"], str):
            kwargs["onset_state"] = EpochState(kwargs["onset_state"])
        if "offset_state" in kwargs and isinstance(kwargs["offset_state"], str):
            kwargs["offset_state"] = EpochState(kwargs["offset_state"])
        if "onset_anchor" in kwargs and isinstance(kwargs["onset_anchor"], str):
            kwargs["onset_anchor"] = AnchorPosition(kwargs["onset_anchor"])
        if "offset_anchor" in kwargs and isinstance(kwargs["offset_anchor"], str):
            kwargs["offset_anchor"] = AnchorPosition(kwargs["offset_anchor"])

        self.config = replace(self.config, **kwargs)

    def get_marker_labels(self, onset_time: str, offset_time: str) -> tuple[str, str]:
        """
        Get UI marker label text.

        Args:
            onset_time: Onset time in HH:MM format
            offset_time: Offset time in HH:MM format

        Returns:
            Tuple of (onset_label, offset_label) for display in UI

        """
        onset_state = "S" if self.config.onset_state == EpochState.SLEEP else "W"
        offset_state = "S" if self.config.offset_state == EpochState.SLEEP else "W"

        onset_label = f"Sleep Onset at {onset_time}\n{self.config.onset_n} consecutive {onset_state} epochs"
        offset_label = f"Sleep Offset at {offset_time}\n{self.config.offset_n} consecutive {offset_state} epochs"

        return onset_label, offset_label

    # === Core Detection Logic ===

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

        """
        if not sleep_scores or len(sleep_scores) == 0:
            return None, None

        # Find corresponding indices for markers in the data
        start_idx = None
        end_idx = None

        for i, timestamp in enumerate(timestamps):
            if start_idx is None and timestamp >= sleep_start_marker:
                start_idx = i
            if timestamp <= sleep_end_marker:
                end_idx = i

        if start_idx is None or end_idx is None:
            return None, None

        # Find sleep onset
        sleep_onset_idx = self._find_onset(
            sleep_scores=sleep_scores,
            start_idx=start_idx,
            end_idx=end_idx,
        )

        # Find sleep offset
        sleep_offset_idx = None
        if sleep_onset_idx is not None:
            sleep_offset_idx = self._find_offset(
                sleep_scores=sleep_scores,
                start_idx=start_idx,
                end_idx=end_idx,
                onset_idx=sleep_onset_idx,
            )

        return sleep_onset_idx, sleep_offset_idx

    def _find_onset(
        self,
        sleep_scores: list[int],
        start_idx: int,
        end_idx: int,
    ) -> int | None:
        """
        Find sleep onset based on configured parameters.

        Args:
            sleep_scores: List of sleep/wake classifications
            start_idx: Starting index from sleep start marker
            end_idx: Ending index from sleep end marker

        Returns:
            Index of sleep onset, or None if not found

        """
        target_value = 1 if self.config.onset_state == EpochState.SLEEP else 0

        # Extend search by configured minutes
        extended_start = max(0, start_idx - self.config.search_extension_minutes)
        extended_end = min(len(sleep_scores) - 1, end_idx + self.config.search_extension_minutes)

        # Ensure we have room for consecutive epochs
        safe_end = min(extended_end, len(sleep_scores) - self.config.onset_n)

        # Find first occurrence of N consecutive target epochs
        for i in range(extended_start, safe_end + 1):
            if all(sleep_scores[i + offset] == target_value for offset in range(self.config.onset_n)):
                # Found a run - return based on anchor position
                if self.config.onset_anchor == AnchorPosition.START:
                    return i
                # END
                return i + self.config.onset_n - 1

        return None

    def _find_offset(
        self,
        sleep_scores: list[int],
        start_idx: int,
        end_idx: int,
        onset_idx: int,
    ) -> int | None:
        """
        Find sleep offset based on configured parameters.

        Args:
            sleep_scores: List of sleep/wake classifications
            start_idx: Starting index from sleep start marker
            end_idx: Ending index from sleep end marker
            onset_idx: Index of identified sleep onset

        Returns:
            Index of sleep offset, or None if not found

        """
        target_value = 1 if self.config.offset_state == EpochState.SLEEP else 0

        # Extend search by configured minutes
        extended_end = min(len(sleep_scores) - 1, end_idx + self.config.search_extension_minutes)

        # Ensure we have room for consecutive epochs
        safe_end = min(extended_end, len(sleep_scores) - self.config.offset_n)

        # Start searching after onset
        search_start = onset_idx + self.config.onset_n

        # Collect all valid runs
        offset_candidates = []

        for i in range(search_start, safe_end + 1):
            if all(sleep_scores[i + offset] == target_value for offset in range(self.config.offset_n)):
                # Found a run - calculate index based on anchor position
                if self.config.offset_anchor == AnchorPosition.START:
                    candidate_idx = i
                else:  # END
                    candidate_idx = i + self.config.offset_n - 1

                # Apply preceding epoch adjustment if configured
                if self.config.offset_preceding_epoch:
                    candidate_idx = i - 1
                    # Verify the preceding epoch is valid (should be opposite state)
                    if candidate_idx < onset_idx:
                        continue

                offset_candidates.append(candidate_idx)

        # Return the LAST valid offset (latest time)
        if offset_candidates:
            return max(offset_candidates)

        # Fallback: if no consecutive run found, find last sleep epoch in range
        if self.config.offset_state == EpochState.WAKE and self.config.offset_preceding_epoch:
            # Looking for wake but returning preceding sleep - find last sleep
            for i in range(extended_end, onset_idx, -1):
                if i < len(sleep_scores) and sleep_scores[i] == 1:
                    return i

        return None


def find_sleep_onset_offset(
    sleep_scores: list[int],
    sleep_start_marker: datetime,
    sleep_end_marker: datetime,
    timestamps: list[datetime],
    config: ConsecutiveEpochsSleepPeriodDetectorConfig | None = None,
) -> tuple[int | None, int | None]:
    """
    Convenience function to apply sleep onset/offset detection.

    Args:
        sleep_scores: List of sleep/wake classifications (1=sleep, 0=wake)
        sleep_start_marker: User-provided approximate sleep start time
        sleep_end_marker: User-provided approximate sleep end time
        timestamps: List of timestamps corresponding to sleep_scores
        config: Optional detection configuration

    Returns:
        Tuple of (onset_index, offset_index), or (None, None) if not found

    """
    detector = ConsecutiveEpochsSleepPeriodDetector(config=config)
    return detector.apply_rules(sleep_scores, sleep_start_marker, sleep_end_marker, timestamps)
