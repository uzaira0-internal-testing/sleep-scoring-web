"""
Feature Extractors for Automated Marker Placement.

Extracts features from epoch data, diary entries, and cross-day patterns.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sleep_scoring_app.core.algorithms.marker_placement.features import (
    ActivitySpike,
    CrossDayFeatures,
    DiaryDay,
    EpochFeatures,
    SleepRun,
)

if TYPE_CHECKING:
    from datetime import datetime

logger = logging.getLogger(__name__)


class EpochFeatureExtractor:
    """Extracts per-epoch features from activity data."""

    def __init__(
        self,
        timestamps: list[datetime],
        activity_counts: list[float],
        sleep_scores: list[int],
        choi_nonwear: list[bool] | None = None,
        diary: DiaryDay | None = None,
    ) -> None:
        """
        Initialize with epoch data.

        Args:
            timestamps: List of epoch timestamps
            activity_counts: List of activity count values
            sleep_scores: List of sleep classifications (0=wake, 1=sleep)
            choi_nonwear: Optional list of Choi nonwear flags per epoch
            diary: Optional diary data for the day

        """
        self.timestamps = timestamps
        self.activity_counts = activity_counts
        self.sleep_scores = sleep_scores
        self.choi_nonwear = choi_nonwear or [False] * len(timestamps)
        self.diary = diary

    def extract(self) -> list[EpochFeatures]:
        """Extract features for all epochs."""
        features = []

        for i, ts in enumerate(self.timestamps):
            is_diary_sleep = self._is_in_diary_sleep_window(ts)
            is_diary_nap = self._is_in_diary_nap_window(ts)

            features.append(
                EpochFeatures(
                    timestamp=ts,
                    sleep_score=self.sleep_scores[i],
                    activity_counts=self.activity_counts[i],
                    is_choi_nonwear=self.choi_nonwear[i],
                    is_diary_sleep_window=is_diary_sleep,
                    is_diary_nap_window=is_diary_nap,
                )
            )

        return features

    def _is_in_diary_sleep_window(self, ts: datetime) -> bool:
        """Check if timestamp is within diary-reported sleep window."""
        if not self.diary or not self.diary.sleep_onset or not self.diary.wake_time:
            return False
        return self.diary.sleep_onset <= ts <= self.diary.wake_time

    def _is_in_diary_nap_window(self, ts: datetime) -> bool:
        """Check if timestamp is within any diary-reported nap window."""
        if not self.diary:
            return False
        return any(nap.start_time <= ts <= nap.end_time for nap in self.diary.nap_periods)


class RunLengthEncoder:
    """Encodes consecutive sleep/wake epochs into runs."""

    def __init__(
        self,
        epoch_features: list[EpochFeatures],
        epoch_length_seconds: int = 60,
    ) -> None:
        """
        Initialize with epoch features.

        Args:
            epoch_features: List of extracted epoch features
            epoch_length_seconds: Length of each epoch in seconds

        """
        self.epochs = epoch_features
        self.epoch_length = epoch_length_seconds

    def encode(self) -> list[SleepRun]:
        """Encode epochs into sleep/wake runs."""
        if not self.epochs:
            return []

        runs: list[SleepRun] = []
        run_start = 0
        current_is_sleep = self.epochs[0].sleep_score == 1

        for i in range(1, len(self.epochs)):
            is_sleep = self.epochs[i].sleep_score == 1

            if is_sleep != current_is_sleep:
                # End current run
                runs.append(self._create_run(run_start, i - 1, current_is_sleep))
                run_start = i
                current_is_sleep = is_sleep

        # Don't forget the last run
        runs.append(self._create_run(run_start, len(self.epochs) - 1, current_is_sleep))

        return runs

    def _create_run(self, start_idx: int, end_idx: int, is_sleep: bool) -> SleepRun:
        """Create a SleepRun from index range."""
        epoch_count = end_idx - start_idx + 1
        duration_minutes = (epoch_count * self.epoch_length) / 60.0

        # Calculate activity stats for the run
        activities = [self.epochs[i].activity_counts for i in range(start_idx, end_idx + 1)]
        mean_activity = sum(activities) / len(activities) if activities else 0.0
        max_activity = max(activities) if activities else 0.0

        return SleepRun(
            start_idx=start_idx,
            end_idx=end_idx,
            start_time=self.epochs[start_idx].timestamp,
            end_time=self.epochs[end_idx].timestamp,
            is_sleep=is_sleep,
            epoch_count=epoch_count,
            duration_minutes=duration_minutes,
            mean_activity=mean_activity,
            max_activity=max_activity,
        )

    def get_consecutive_sleep_at(self, idx: int) -> int:
        """Get count of consecutive sleep epochs starting at index."""
        if idx >= len(self.epochs) or self.epochs[idx].sleep_score != 1:
            return 0

        count = 0
        for i in range(idx, len(self.epochs)):
            if self.epochs[i].sleep_score == 1:
                count += 1
            else:
                break
        return count

    def get_consecutive_sleep_ending_at(self, idx: int) -> int:
        """Get count of consecutive sleep epochs ending at index."""
        if idx < 0 or idx >= len(self.epochs) or self.epochs[idx].sleep_score != 1:
            return 0

        count = 0
        for i in range(idx, -1, -1):
            if self.epochs[i].sleep_score == 1:
                count += 1
            else:
                break
        return count


class SpikeDetector:
    """Detects activity spikes (anomalously high activity)."""

    def __init__(
        self,
        epoch_features: list[EpochFeatures],
        baseline_percentile: float = 0.5,  # median
        spike_threshold_std: float = 2.0,  # 2 standard deviations
    ) -> None:
        """
        Initialize spike detector.

        Args:
            epoch_features: List of extracted epoch features
            baseline_percentile: Percentile to use as baseline (0.5 = median)
            spike_threshold_std: Number of std deviations above baseline to be a spike

        """
        self.epochs = epoch_features
        self.baseline_percentile = baseline_percentile
        self.spike_threshold_std = spike_threshold_std

        # Calculate baseline stats from sleep epochs only
        sleep_activities = [e.activity_counts for e in epoch_features if e.sleep_score == 1]
        if sleep_activities:
            sorted_acts = sorted(sleep_activities)
            percentile_idx = int(len(sorted_acts) * baseline_percentile)
            self.baseline = sorted_acts[percentile_idx]

            # Calculate std deviation
            mean = sum(sleep_activities) / len(sleep_activities)
            variance = sum((x - mean) ** 2 for x in sleep_activities) / len(sleep_activities)
            self.std_dev = variance**0.5
        else:
            self.baseline = 0.0
            self.std_dev = 1.0

        self.spike_threshold = self.baseline + (self.spike_threshold_std * self.std_dev)

    def detect(self, min_duration_epochs: int = 1) -> list[ActivitySpike]:
        """
        Detect activity spikes.

        Args:
            min_duration_epochs: Minimum epochs for a spike to be significant

        Returns:
            List of detected spikes

        """
        spikes: list[ActivitySpike] = []
        in_spike = False
        spike_start = 0

        for i, epoch in enumerate(self.epochs):
            is_above_threshold = epoch.activity_counts > self.spike_threshold

            if is_above_threshold and not in_spike:
                # Start of spike
                in_spike = True
                spike_start = i
            elif not is_above_threshold and in_spike:
                # End of spike
                in_spike = False
                spike = self._create_spike(spike_start, i - 1)
                if spike.duration_epochs >= min_duration_epochs:
                    spikes.append(spike)

        # Handle spike at end
        if in_spike:
            spike = self._create_spike(spike_start, len(self.epochs) - 1)
            if spike.duration_epochs >= min_duration_epochs:
                spikes.append(spike)

        return spikes

    def _create_spike(self, start_idx: int, end_idx: int) -> ActivitySpike:
        """Create an ActivitySpike from index range."""
        activities = [self.epochs[i].activity_counts for i in range(start_idx, end_idx + 1)]
        peak = max(activities)
        z_score = (peak - self.baseline) / self.std_dev if self.std_dev > 0 else 0.0

        return ActivitySpike(
            start_idx=start_idx,
            end_idx=end_idx,
            start_time=self.epochs[start_idx].timestamp,
            end_time=self.epochs[end_idx].timestamp,
            peak_activity=peak,
            z_score=z_score,
            duration_epochs=end_idx - start_idx + 1,
        )

    def has_spike_near(self, idx: int, window_epochs: int = 5) -> bool:
        """Check if there's a spike within window_epochs of index."""
        spikes = self.detect()
        return any(spike.start_idx - window_epochs <= idx <= spike.end_idx + window_epochs for spike in spikes)

    def get_spike_near(self, idx: int, window_epochs: int = 5) -> ActivitySpike | None:
        """Get spike near index if one exists."""
        spikes = self.detect()
        for spike in spikes:
            if spike.start_idx - window_epochs <= idx <= spike.end_idx + window_epochs:
                return spike
        return None


class CrossDayAggregator:
    """Aggregates features across multiple days for a participant."""

    def __init__(self, diary_days: list[DiaryDay]) -> None:
        """
        Initialize with diary data from multiple days.

        Args:
            diary_days: List of DiaryDay objects for the participant

        """
        self.diary_days = diary_days

    def aggregate(self) -> CrossDayFeatures:
        """Aggregate cross-day features."""
        all_nap_times: list[datetime] = []
        all_nonwear_times: list[datetime] = []
        nonwear_histogram: dict[int, int] = {}

        for day in self.diary_days:
            # Collect nap times
            for nap in day.nap_periods:
                all_nap_times.append(nap.start_time)

            # Collect nonwear times
            for nw in day.nonwear_periods:
                all_nonwear_times.append(nw.start_time)
                hour = nw.start_time.hour
                nonwear_histogram[hour] = nonwear_histogram.get(hour, 0) + 1

        # Calculate nap time variance
        nap_time_variance = self._calculate_time_variance(all_nap_times)

        # Find typical nap windows
        typical_nap_windows = self._find_typical_windows(all_nap_times)

        return CrossDayFeatures(
            typical_nap_windows=typical_nap_windows,
            nap_time_variance_minutes=nap_time_variance,
            nonwear_time_histogram=nonwear_histogram,
            all_nap_times=all_nap_times,
            all_nonwear_times=all_nonwear_times,
        )

    def _calculate_time_variance(self, times: list[datetime]) -> float:
        """Calculate variance of times in minutes."""
        if len(times) < 2:
            return 0.0

        # Convert to minutes from midnight
        minutes = [(t.hour * 60 + t.minute) for t in times]
        mean = sum(minutes) / len(minutes)
        variance = sum((m - mean) ** 2 for m in minutes) / len(minutes)
        return variance**0.5  # Return std dev

    def _find_typical_windows(
        self,
        times: list[datetime],
        window_size_hours: int = 2,
    ) -> list[tuple]:
        """Find typical time windows from a list of times."""
        if not times:
            return []

        # Group by hour
        hour_counts: dict[int, int] = {}
        for t in times:
            hour = t.hour
            hour_counts[hour] = hour_counts.get(hour, 0) + 1

        # Find peaks (hours with multiple occurrences)
        windows = []
        for hour, count in hour_counts.items():
            if count >= 2:  # At least 2 occurrences
                from datetime import time

                start = time(hour=max(0, hour - 1))
                end = time(hour=min(23, hour + 1), minute=59)
                windows.append((start, end))

        return windows
