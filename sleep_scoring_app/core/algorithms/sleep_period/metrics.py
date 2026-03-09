"""
Tudor-Locke sleep quality metrics calculation.

This module provides comprehensive sleep quality metrics for detected sleep periods,
matching the actigraph.sleepr R package implementation.

Terminology Glossary:
    The codebase uses specific terms that have distinct meanings:

    Period Boundaries (in SleepPeriod dataclass):
        - onset_timestamp: Unix timestamp of the detected sleep period start
        - offset_timestamp: Unix timestamp of the detected sleep period end

    Tudor-Locke Metrics (in SleepPeriodMetrics):
        - in_bed_time: First minute of the sleep period (same as onset)
        - out_bed_time: Last minute of the sleep period (same as offset)
        - sleep_onset: First epoch actually scored as sleep within the period
        - sleep_offset: Last epoch actually scored as sleep within the period

    Algorithm Parameters (in onset/offset detection):
        - sleep_start_marker: User-provided or diary-derived approximate sleep start
        - sleep_end_marker: User-provided or diary-derived approximate sleep end
        These are HINTS for algorithms, not the detected boundaries.

    Note: "onset/offset" refers to detected/calculated boundaries.
          "sleep_start/sleep_end_marker" refers to user-provided reference points.

Reference:
    Tudor-Locke C, et al. (2014). Fully automated waist-worn accelerometer algorithm
    for detecting children's sleep-period time. Applied Physiology, Nutrition, and
    Metabolism, 39(1):53-57.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    pass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SleepPeriodMetrics:
    """
    Comprehensive sleep quality metrics for a detected sleep period.

    These metrics match the Tudor-Locke algorithm implementation from the
    actigraph.sleepr R package. All metrics are calculated from:
    1. Sleep/wake classifications (from Sadeh, Cole-Kripke, etc.)
    2. Activity count data
    3. Detected sleep period boundaries

    Attributes:
        # Period boundaries
        in_bed_time: First minute of bedtime (start of sleep period)
        out_bed_time: First minute of wake time (end of sleep period)
        sleep_onset: First epoch scored as sleep
        sleep_offset: Last epoch scored as sleep

        # Duration metrics (minutes)
        time_in_bed: Total minutes in bed (sleep period duration)
        total_sleep_time: Total minutes scored as sleep
        sleep_onset_latency: Time from bedtime to sleep onset (0 by Tudor-Locke definition)
        wake_after_sleep_onset: Wake time during sleep period (TIB - TST - latency)

        # Awakening metrics
        num_awakenings: Number of awakening episodes (wake bouts)
        avg_awakening_length: Average duration of awakenings in minutes

        # Quality indices (percentages)
        sleep_efficiency: Percentage of time asleep (TST / TIB * 100)
        movement_index: Proportion of epochs with activity > 0 (%)
        fragmentation_index: Proportion of 1-minute sleep bouts (%)
        sleep_fragmentation_index: Combined disruption measure (movement + fragmentation)

        # Activity metrics
        total_activity_counts: Sum of activity counts during sleep period
        nonzero_epochs: Number of epochs with activity > 0

    """

    # Period boundaries
    in_bed_time: datetime
    out_bed_time: datetime
    sleep_onset: datetime
    sleep_offset: datetime

    # Duration metrics (minutes)
    time_in_bed: float
    total_sleep_time: float
    sleep_onset_latency: float
    wake_after_sleep_onset: float

    # Awakening metrics
    num_awakenings: int
    avg_awakening_length: float

    # Quality indices (percentages)
    sleep_efficiency: float
    movement_index: float
    fragmentation_index: float
    sleep_fragmentation_index: float

    # Activity metrics
    total_activity_counts: float
    nonzero_epochs: int


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
        print(f"Sleep efficiency: {metrics.sleep_efficiency:.1f}%")
        print(f"Total sleep time: {metrics.total_sleep_time:.1f} minutes")
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
        epoch_seconds: int = 60,
    ) -> SleepPeriodMetrics:
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
            SleepPeriodMetrics containing all calculated metrics

        Raises:
            ValueError: If inputs are invalid or inconsistent

        """
        # Validate inputs
        self._validate_inputs(sleep_scores, activity_counts, onset_idx, offset_idx, timestamps)

        # Warn if specified epoch duration doesn't match actual data spacing
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

        epoch_minutes = epoch_seconds / 60.0
        time_in_bed = len(period_sleep_scores) * epoch_minutes  # Minutes
        total_sleep_time = sum(period_sleep_scores) * epoch_minutes  # Minutes of sleep
        sleep_onset_latency = 0.0  # By Tudor-Locke definition, always 0
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

        return SleepPeriodMetrics(
            in_bed_time=in_bed_time,
            out_bed_time=out_bed_time,
            sleep_onset=sleep_onset,
            sleep_offset=sleep_offset,
            time_in_bed=time_in_bed,
            total_sleep_time=total_sleep_time,
            sleep_onset_latency=sleep_onset_latency,
            wake_after_sleep_onset=wake_after_sleep_onset,
            num_awakenings=num_awakenings,
            avg_awakening_length=avg_awakening_length,
            sleep_efficiency=sleep_efficiency,
            movement_index=movement_index,
            fragmentation_index=fragmentation_index,
            sleep_fragmentation_index=sleep_fragmentation_index,
            total_activity_counts=total_activity_counts,
            nonzero_epochs=nonzero_epochs,
        )

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
        awakenings = 0
        in_wake_bout = False

        for score in sleep_scores:
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
