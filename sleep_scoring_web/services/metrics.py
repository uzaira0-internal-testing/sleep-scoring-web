"""
Tudor-Locke sleep quality metrics calculation.

Ported from desktop app's core/algorithms/sleep_period/metrics.py.
This module provides comprehensive sleep quality metrics for detected sleep periods,
matching the actigraph.sleepr R package implementation.

Reference:
    Tudor-Locke C, et al. (2014). Fully automated waist-worn accelerometer algorithm
    for detecting children's sleep-period time. Applied Physiology, Nutrition, and
    Metabolism, 39(1):53-57.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sleep_scoring_web.schemas.enums import MarkerLimits

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class TudorLockeSleepMetricsCalculator:
    """
    Calculate Tudor-Locke sleep quality metrics from sleep/wake scores and activity data.

    This calculator implements the full Tudor-Locke metrics algorithm as defined in
    the actigraph.sleepr R package. It operates on already-classified sleep/wake data
    and activity counts to produce comprehensive sleep quality metrics.

    Example:
        ```python
        calculator = TudorLockeSleepMetricsCalculator()
        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_wake_classifications,
            activity_counts=activity_data,
            onset_idx=sleep_onset_index,
            offset_idx=sleep_offset_index,
            timestamps=epoch_timestamps
        )
        print(f"Sleep efficiency: {metrics['sleep_efficiency']:.1f}%")
        print(f"Total sleep time: {metrics['total_sleep_time_minutes']:.1f} minutes")
        ```

    Reference:
        https://github.com/dipetkov/actigraph.sleepr
        https://rdrr.io/github/dipetkov/actigraph.sleepr/man/apply_tudor_locke.html

    """

    def calculate_metrics(
        self,
        sleep_scores: list[int],
        activity_counts: list[float],
        onset_idx: int,
        offset_idx: int,
        timestamps: list[datetime],
        epoch_seconds: int = MarkerLimits.EPOCH_DURATION_SECONDS,
    ) -> dict:
        """
        Calculate comprehensive sleep quality metrics for a sleep period.

        Args:
            sleep_scores: List of sleep/wake classifications (1=sleep, 0=wake)
            activity_counts: List of activity count values
            onset_idx: Index of sleep onset
            offset_idx: Index of sleep offset
            timestamps: List of datetime objects corresponding to epochs
            epoch_seconds: Duration of each epoch in seconds. Defaults to 60.
                          Must match the actual data epoch duration for correct metrics.

        Returns:
            Dictionary containing all calculated metrics matching SleepMetrics schema

        Raises:
            ValueError: If inputs are invalid or inconsistent

        """
        # Validate inputs
        self._validate_inputs(sleep_scores, activity_counts, onset_idx, offset_idx, timestamps)

        # Validate epoch duration against actual data
        if len(timestamps) >= 2:
            actual_epoch_seconds = (timestamps[1] - timestamps[0]).total_seconds()
            if abs(actual_epoch_seconds - epoch_seconds) > 5:  # 5-second tolerance
                logger.warning(
                    "EPOCH DURATION MISMATCH: Expected %d seconds but data shows %.1f seconds. "
                    "Metrics (TST, WASO, etc.) may be incorrect. Using specified epoch_seconds=%d.",
                    epoch_seconds,
                    actual_epoch_seconds,
                    epoch_seconds,
                )

        # Extract sleep period data
        period_sleep_scores = sleep_scores[onset_idx : offset_idx + 1]
        period_activity = activity_counts[onset_idx : offset_idx + 1]
        period_timestamps = timestamps[onset_idx : offset_idx + 1]

        # Period boundaries
        in_bed_time = period_timestamps[0]
        out_bed_time = period_timestamps[-1]
        sleep_onset = self._find_first_sleep_epoch(period_sleep_scores, period_timestamps)
        sleep_offset = self._find_last_sleep_epoch(period_sleep_scores, period_timestamps)

        # Duration metrics - convert epoch count to minutes using epoch_seconds
        epoch_minutes = epoch_seconds / 60.0
        time_in_bed = len(period_sleep_scores) * epoch_minutes  # Minutes
        total_sleep_time = sum(period_sleep_scores) * epoch_minutes  # Minutes of sleep

        # SOL = wake epochs before the first sleep epoch within the period
        first_sleep_idx = next((i for i, s in enumerate(period_sleep_scores) if s == 1), None)
        sleep_onset_latency = (first_sleep_idx * epoch_minutes) if first_sleep_idx is not None else 0.0
        wake_after_sleep_onset = time_in_bed - total_sleep_time - sleep_onset_latency

        # Awakening metrics
        num_awakenings = self._count_awakenings(period_sleep_scores)
        avg_awakening_length = wake_after_sleep_onset / num_awakenings if num_awakenings > 0 else 0.0

        # Activity metrics
        total_activity_counts = sum(period_activity)
        nonzero_epochs = sum(1 for count in period_activity if count > 0)
        total_epochs = len(period_sleep_scores)

        # Quality indices
        sleep_efficiency = (total_sleep_time / time_in_bed * 100) if time_in_bed > 0 else 0.0
        # movement_index uses epoch count (not minutes) for percentage calculation
        movement_index = (nonzero_epochs / total_epochs * 100) if total_epochs > 0 else 0.0

        # Fragmentation index calculation
        fragmentation_index = self._calculate_fragmentation_index(period_sleep_scores)

        # Sleep fragmentation index (combined)
        sleep_fragmentation_index = movement_index + fragmentation_index

        return {
            # Period boundaries (datetime)
            "in_bed_time": in_bed_time,
            "out_bed_time": out_bed_time,
            "sleep_onset": sleep_onset,
            "sleep_offset": sleep_offset,
            # Duration metrics (minutes)
            "time_in_bed_minutes": time_in_bed,
            "total_sleep_time_minutes": total_sleep_time,
            "sleep_onset_latency_minutes": sleep_onset_latency,
            "waso_minutes": wake_after_sleep_onset,
            # Awakening metrics
            "number_of_awakenings": num_awakenings,
            "average_awakening_length_minutes": avg_awakening_length,
            # Quality indices (percentages)
            "sleep_efficiency": sleep_efficiency,
            "movement_index": movement_index,
            "fragmentation_index": fragmentation_index,
            "sleep_fragmentation_index": sleep_fragmentation_index,
            # Activity metrics
            "total_activity": int(total_activity_counts),
            "nonzero_epochs": nonzero_epochs,
        }

    def _validate_inputs(
        self,
        sleep_scores: list[int],
        activity_counts: list[float],
        onset_idx: int,
        offset_idx: int,
        timestamps: list[datetime],
    ) -> None:
        """Validate input parameters."""
        if not sleep_scores:
            msg = "sleep_scores cannot be empty"
            raise ValueError(msg)

        if len(sleep_scores) != len(activity_counts):
            msg = f"sleep_scores ({len(sleep_scores)}) and activity_counts ({len(activity_counts)}) must have same length"
            raise ValueError(msg)

        if len(sleep_scores) != len(timestamps):
            msg = f"sleep_scores ({len(sleep_scores)}) and timestamps ({len(timestamps)}) must have same length"
            raise ValueError(msg)

        if onset_idx < 0 or onset_idx >= len(sleep_scores):
            msg = f"onset_idx ({onset_idx}) out of range [0, {len(sleep_scores)})"
            raise ValueError(msg)

        if offset_idx < 0 or offset_idx >= len(sleep_scores):
            msg = f"offset_idx ({offset_idx}) out of range [0, {len(sleep_scores)})"
            raise ValueError(msg)

        if onset_idx >= offset_idx:
            msg = f"onset_idx ({onset_idx}) must be less than offset_idx ({offset_idx})"
            raise ValueError(msg)

    def _find_first_sleep_epoch(self, sleep_scores: list[int], timestamps: list[datetime]) -> datetime:
        """Find the first epoch scored as sleep."""
        for i, score in enumerate(sleep_scores):
            if score == 1:  # Sleep
                return timestamps[i]
        # If no sleep epochs found, return first timestamp
        return timestamps[0]

    def _find_last_sleep_epoch(self, sleep_scores: list[int], timestamps: list[datetime]) -> datetime:
        """Find the last epoch scored as sleep."""
        for i in range(len(sleep_scores) - 1, -1, -1):
            if sleep_scores[i] == 1:  # Sleep
                return timestamps[i]
        # If no sleep epochs found, return last timestamp
        return timestamps[-1]

    def _count_awakenings(self, sleep_scores: list[int]) -> int:
        """
        Count number of awakening episodes.

        An awakening is a contiguous block of wake (0) epochs within the sleep period.

        Args:
            sleep_scores: List of sleep/wake classifications within period

        Returns:
            Number of distinct awakening episodes

        """
        # Skip epochs before the first sleep epoch (those are SOL, not awakenings)
        first_sleep = next((i for i, s in enumerate(sleep_scores) if s == 1), None)
        if first_sleep is None:
            return 0

        awakenings = 0
        in_wake_bout = False

        for score in sleep_scores[first_sleep:]:
            if score == 0 and not in_wake_bout:  # Wake epoch, start of bout
                awakenings += 1
                in_wake_bout = True
            elif score == 1:  # Sleep epoch
                in_wake_bout = False

        return awakenings

    def _calculate_fragmentation_index(self, sleep_scores: list[int]) -> float:
        """
        Calculate fragmentation index.

        Formula (from actigraph.sleepr):
            fragmentation_index = 100 * dozings_1min / dozings

        Where:
            - dozings = total number of sleep bouts of any length
            - dozings_1min = number of 1-minute sleep bouts

        Args:
            sleep_scores: List of sleep/wake classifications within period

        Returns:
            Fragmentation index as percentage (0-100)

        """
        # Count sleep bouts
        sleep_bouts: list[int] = []
        current_bout_length = 0

        for score in sleep_scores:
            if score == 1:  # Sleep
                current_bout_length += 1
            elif current_bout_length > 0:  # End of sleep bout
                sleep_bouts.append(current_bout_length)
                current_bout_length = 0

        # Don't forget the last bout if it ends with sleep
        if current_bout_length > 0:
            sleep_bouts.append(current_bout_length)

        # Calculate fragmentation index
        if len(sleep_bouts) == 0:
            return 0.0

        one_minute_bouts = sum(1 for bout_length in sleep_bouts if bout_length == 1)
        total_bouts = len(sleep_bouts)

        return (one_minute_bouts / total_bouts * 100) if total_bouts > 0 else 0.0
