"""
Feature Extraction for Automated Marker Placement.

Defines dataclasses for features used by sleep/nap marker placement rules.
Features are extracted from epoch data, diary entries, and cross-day patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime, time


@dataclass(frozen=True)
class EpochFeatures:
    """
    Features for a single epoch.

    Attributes:
        timestamp: Epoch timestamp
        sleep_score: Sleep classification (0=wake, 1=sleep)
        activity_counts: Raw activity count value
        is_choi_nonwear: Whether Choi algorithm marked this as nonwear
        is_diary_sleep_window: Whether this falls within diary-reported sleep period
        is_diary_nap_window: Whether this falls within a diary-reported nap period

    """

    timestamp: datetime
    sleep_score: int  # 0=wake, 1=sleep
    activity_counts: float
    is_choi_nonwear: bool = False
    is_diary_sleep_window: bool = False
    is_diary_nap_window: bool = False


@dataclass(frozen=True)
class SleepRun:
    """
    A consecutive run of sleep or wake epochs.

    Attributes:
        start_idx: Index of first epoch in run
        end_idx: Index of last epoch in run (inclusive)
        start_time: Timestamp of first epoch
        end_time: Timestamp of last epoch
        is_sleep: True if sleep run, False if wake run
        epoch_count: Number of epochs in run
        duration_minutes: Duration of run in minutes
        mean_activity: Mean activity during run (useful for wake runs)
        max_activity: Max activity during run (spike detection)

    """

    start_idx: int
    end_idx: int
    start_time: datetime
    end_time: datetime
    is_sleep: bool
    epoch_count: int
    duration_minutes: float
    mean_activity: float = 0.0
    max_activity: float = 0.0


@dataclass(frozen=True)
class ActivitySpike:
    """
    An activity spike (anomalously high activity).

    Attributes:
        start_idx: Index of first epoch in spike
        end_idx: Index of last epoch in spike
        start_time: Timestamp of spike start
        end_time: Timestamp of spike end
        peak_activity: Maximum activity value in spike
        z_score: How many standard deviations above baseline
        duration_epochs: Number of epochs in spike

    """

    start_idx: int
    end_idx: int
    start_time: datetime
    end_time: datetime
    peak_activity: float
    z_score: float
    duration_epochs: int


@dataclass
class DiaryPeriod:
    """
    A time period from the sleep diary.

    Attributes:
        start_time: Period start time
        end_time: Period end time
        period_type: Type of period ('sleep', 'nap', 'nonwear')
        date: The date this period belongs to

    """

    start_time: datetime
    end_time: datetime
    period_type: str  # 'sleep', 'nap', 'nonwear'
    date: datetime


@dataclass
class DiaryDay:
    """
    Diary data for a single day.

    Attributes:
        date: The analysis date
        in_bed_time: Time got into bed
        out_bed_time: Time got out of bed
        sleep_onset: Reported sleep onset time
        wake_time: Reported wake time
        nap_periods: List of reported nap periods
        nonwear_periods: List of reported nonwear periods

    """

    date: datetime
    in_bed_time: datetime | None = None
    out_bed_time: datetime | None = None
    sleep_onset: datetime | None = None
    wake_time: datetime | None = None
    nap_periods: list[DiaryPeriod] = field(default_factory=list)
    nonwear_periods: list[DiaryPeriod] = field(default_factory=list)


@dataclass
class CrossDayFeatures:
    """
    Features aggregated across multiple days for a participant.

    Attributes:
        typical_nap_windows: Common nap time windows (start_hour, end_hour)
        nap_time_variance_minutes: Variance in nap timing (high = irregular naps)
        nonwear_time_histogram: Count of nonwear at each hour across days
        all_nap_times: List of all nap times across days (for pattern matching)
        all_nonwear_times: List of all nonwear times across days

    """

    typical_nap_windows: list[tuple[time, time]] = field(default_factory=list)
    nap_time_variance_minutes: float = 0.0
    nonwear_time_histogram: dict[int, int] = field(default_factory=dict)  # hour -> count
    all_nap_times: list[datetime] = field(default_factory=list)
    all_nonwear_times: list[datetime] = field(default_factory=list)

    def has_nonwear_at_similar_time(self, timestamp: datetime, tolerance_minutes: int = 30) -> bool:
        """Check if nonwear was reported at a similar time on other days."""
        target_time = timestamp.time()
        for nw_time in self.all_nonwear_times:
            if nw_time.date() == timestamp.date():
                continue  # Skip same day
            time_diff = abs((nw_time.hour * 60 + nw_time.minute) - (target_time.hour * 60 + target_time.minute))
            if time_diff <= tolerance_minutes:
                return True
        return False

    def has_nap_at_similar_time(self, timestamp: datetime, tolerance_minutes: int = 60) -> bool:
        """Check if naps were reported at a similar time on other days."""
        target_time = timestamp.time()
        for nap_time in self.all_nap_times:
            time_diff = abs((nap_time.hour * 60 + nap_time.minute) - (target_time.hour * 60 + target_time.minute))
            if time_diff <= tolerance_minutes:
                return True
        return False


@dataclass
class SleepPeriodCandidate:
    """
    A candidate sleep period with scoring features.

    Attributes:
        onset_idx: Index of sleep onset epoch
        offset_idx: Index of sleep offset epoch
        onset_time: Timestamp of sleep onset
        offset_time: Timestamp of sleep offset
        onset_consecutive_sleep: Number of consecutive sleep epochs at onset
        offset_consecutive_sleep: Number of consecutive sleep epochs at offset
        duration_minutes: Total duration of candidate period
        contains_choi_nonwear: Whether period contains Choi nonwear
        contains_diary_nonwear: Whether period overlaps diary nonwear
        distance_to_diary_onset_minutes: Distance from diary-reported onset
        distance_to_diary_offset_minutes: Distance from diary-reported offset
        has_spike_at_onset: Whether there's an activity spike near onset
        has_spike_at_offset: Whether there's an activity spike near offset
        spike_before_onset: Activity spike info before onset (if any)
        nonwear_near_onset: Whether nonwear detected near onset
        nonwear_near_offset: Whether nonwear detected near offset

    """

    onset_idx: int
    offset_idx: int
    onset_time: datetime
    offset_time: datetime

    # Consecutive epoch requirements
    onset_consecutive_sleep: int = 0
    offset_consecutive_sleep: int = 0

    # Duration
    duration_minutes: float = 0.0

    # Nonwear overlap
    contains_choi_nonwear: bool = False
    contains_diary_nonwear: bool = False

    # Distance to diary
    distance_to_diary_onset_minutes: float | None = None
    distance_to_diary_offset_minutes: float | None = None

    # Spike features
    has_spike_at_onset: bool = False
    has_spike_at_offset: bool = False
    spike_before_onset: ActivitySpike | None = None

    # Nonwear near boundaries
    nonwear_near_onset: bool = False
    nonwear_near_offset: bool = False

    @property
    def is_within_diary_tolerance(self) -> bool:
        """Check if candidate is within 15 minutes of diary times."""
        if self.distance_to_diary_onset_minutes is None:
            return True  # No diary to compare against
        return self.distance_to_diary_onset_minutes <= 15 and (self.distance_to_diary_offset_minutes or 0) <= 15

    @property
    def issue_score(self) -> int:
        """
        Compute a score of potential issues (lower is better).

        Used for choosing between equidistant candidates per Rule 6.
        """
        score = 0
        if self.has_spike_at_onset:
            score += 1
        if self.has_spike_at_offset:
            score += 1
        if self.contains_choi_nonwear:
            score += 2
        if self.nonwear_near_onset:
            score += 1
        if self.nonwear_near_offset:
            score += 1
        return score

    def meets_onset_requirement(self, min_consecutive: int = 3) -> bool:
        """Check if onset meets minimum consecutive sleep epochs."""
        return self.onset_consecutive_sleep >= min_consecutive

    def meets_offset_requirement(self, min_consecutive_minutes: int = 5, epoch_length_seconds: int = 60) -> bool:
        """Check if offset meets minimum consecutive sleep time."""
        epochs_needed = (min_consecutive_minutes * 60) // epoch_length_seconds
        return self.offset_consecutive_sleep >= epochs_needed


@dataclass
class NapCandidate(SleepPeriodCandidate):
    """
    A candidate nap period with additional nap-specific features.

    Attributes:
        has_diary_nap_confirmation: Diary explicitly mentions nap at this time
        has_cross_day_nap_pattern: Similar nap time found on other days
        overlaps_diary_nap_exactly: Within a few minutes of diary nap time

    """

    has_diary_nap_confirmation: bool = False
    has_cross_day_nap_pattern: bool = False
    overlaps_diary_nap_exactly: bool = False  # Within ~5 minutes

    @property
    def can_ignore_nonwear(self) -> bool:
        """Per user rules: if nap overlaps diary exactly, nonwear can be ignored."""
        return self.overlaps_diary_nap_exactly

    def is_valid_nap(self) -> bool:
        """Nap requires diary confirmation (same day or cross-day pattern)."""
        return self.has_diary_nap_confirmation or self.has_cross_day_nap_pattern
