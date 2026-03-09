"""
Sleep Period Placement Rules.

Implements the automated rules for placing sleep and nap markers.

See CLAUDE.md "Automated Marker Placement Rules" section for the complete
rule documentation. This module implements those rules.

Base Algorithm Requirements:
- Onset: First epoch of 3+ consecutive sleep epochs
- Offset: Ends with 5+ consecutive minutes of sleep
- Diary tolerance: 15 minutes for choosing between multiple candidates
- Nonwear: No Choi + diary nonwear overlap during the period

Key Rules (see CLAUDE.md for full details):
1. Activity in middle of sleep - include if continuous sleep after within diary period
2. Small periods near onset - consider duration/height/magnitude of wake
3. Extended sleep before diary - extend to typical nap period if applicable
4. Nap timing variation - mark >=10 sleep epoch periods as naps
5. Choi-only nonwear with spike - can sometimes be ignored
6. Equidistant candidates - choose one with fewer issues (spikes, nonwear)
7. Cross-day nonwear patterns - apply to other days if signs visible
8. Sleep onset before in-bed time - use in-bed time instead
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sleep_scoring_app.core.algorithms.marker_placement.extractors import (
    CrossDayAggregator,
    EpochFeatureExtractor,
    RunLengthEncoder,
    SpikeDetector,
)
from sleep_scoring_app.core.algorithms.marker_placement.features import (
    ActivitySpike,
    CrossDayFeatures,
    DiaryDay,
    EpochFeatures,
    NapCandidate,
    SleepPeriodCandidate,
    SleepRun,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RuleConfig:
    """
    Configuration for sleep period placement rules.

    Attributes:
        onset_min_consecutive_sleep: Min consecutive sleep epochs for onset (Rule 1)
        offset_min_consecutive_minutes: Min consecutive sleep minutes for offset (Rule 2)
        diary_tolerance_minutes: Tolerance for diary matching (Rule 3)
        nap_min_consecutive_epochs: Min epochs for a nap (Rule 4)
        nap_diary_overlap_tolerance_minutes: Tolerance for "exact" diary overlap
        epoch_length_seconds: Length of each epoch
        spike_threshold_std: Std deviations above baseline for spike detection

    """

    onset_min_consecutive_sleep: int = 3
    offset_min_consecutive_minutes: int = 5
    diary_tolerance_minutes: int = 15
    nap_min_consecutive_epochs: int = 10
    nap_diary_overlap_tolerance_minutes: int = 5
    epoch_length_seconds: int = 60
    spike_threshold_std: float = 2.0


class SleepPeriodCandidateFinder:
    """Finds candidate sleep periods from epoch data."""

    def __init__(
        self,
        epoch_features: list[EpochFeatures],
        runs: list[SleepRun],
        spike_detector: SpikeDetector,
        diary: DiaryDay | None = None,
        cross_day_features: CrossDayFeatures | None = None,
        config: RuleConfig | None = None,
    ) -> None:
        """
        Initialize candidate finder.

        Args:
            epoch_features: Extracted epoch features
            runs: Encoded sleep/wake runs
            spike_detector: Spike detector instance
            diary: Optional diary data for the day
            cross_day_features: Optional cross-day patterns
            config: Rule configuration

        """
        self.epochs = epoch_features
        self.runs = runs
        self.spike_detector = spike_detector
        self.diary = diary
        self.cross_day = cross_day_features
        self.config = config or RuleConfig()

        # Pre-compute for efficiency
        self._run_encoder = RunLengthEncoder(epoch_features, self.config.epoch_length_seconds)

    def find_main_sleep_candidates(self) -> list[SleepPeriodCandidate]:
        """
        Find all candidate main sleep periods.

        Returns candidates that:
        - Start with >= onset_min_consecutive_sleep epochs
        - End with >= offset_min_consecutive_minutes of sleep
        - Don't have overlapping Choi nonwear AND diary nonwear
        """
        candidates: list[SleepPeriodCandidate] = []

        # Find all sleep runs that could be onset points
        sleep_runs = [r for r in self.runs if r.is_sleep]

        for onset_run in sleep_runs:
            # Check onset requirement
            if onset_run.epoch_count < self.config.onset_min_consecutive_sleep:
                continue

            # Find possible offset points (sleep runs after this onset)
            for offset_run in sleep_runs:
                if offset_run.start_idx <= onset_run.start_idx:
                    continue

                # Check offset requirement (min consecutive minutes)
                offset_min_epochs = (self.config.offset_min_consecutive_minutes * 60) // self.config.epoch_length_seconds
                if offset_run.epoch_count < offset_min_epochs:
                    continue

                # Create candidate
                candidate = self._create_candidate(
                    onset_idx=onset_run.start_idx,
                    offset_idx=offset_run.end_idx,
                    onset_run=onset_run,
                    offset_run=offset_run,
                )

                # Filter out candidates with both Choi AND diary nonwear
                if self._has_nonwear_overlap(candidate):
                    continue

                candidates.append(candidate)

        return candidates

    def find_nap_candidates(self) -> list[NapCandidate]:
        """
        Find all candidate nap periods.

        Returns candidates that:
        - Have >= nap_min_consecutive_epochs sleep epochs
        - Have diary confirmation (same day or cross-day pattern)
        """
        candidates: list[NapCandidate] = []

        sleep_runs = [r for r in self.runs if r.is_sleep and r.epoch_count >= self.config.nap_min_consecutive_epochs]

        for run in sleep_runs:
            # Check if this could be a nap
            has_diary_nap = self._overlaps_diary_nap(run)
            has_cross_day_pattern = self._has_cross_day_nap_pattern(run)

            # Nap requires diary confirmation
            if not has_diary_nap and not has_cross_day_pattern:
                continue

            # Check if it overlaps diary exactly
            overlaps_exactly = self._overlaps_diary_nap_exactly(run)

            candidate = NapCandidate(
                onset_idx=run.start_idx,
                offset_idx=run.end_idx,
                onset_time=run.start_time,
                offset_time=run.end_time,
                onset_consecutive_sleep=run.epoch_count,
                offset_consecutive_sleep=run.epoch_count,
                duration_minutes=run.duration_minutes,
                has_diary_nap_confirmation=has_diary_nap,
                has_cross_day_nap_pattern=has_cross_day_pattern,
                overlaps_diary_nap_exactly=overlaps_exactly,
                contains_choi_nonwear=self._contains_choi_nonwear(run.start_idx, run.end_idx),
            )

            candidates.append(candidate)

        return candidates

    def _create_candidate(
        self,
        onset_idx: int,
        offset_idx: int,
        onset_run: SleepRun,
        offset_run: SleepRun,
    ) -> SleepPeriodCandidate:
        """Create a SleepPeriodCandidate with all features computed."""
        onset_time = self.epochs[onset_idx].timestamp
        offset_time = self.epochs[offset_idx].timestamp
        duration = (offset_time - onset_time).total_seconds() / 60.0

        # Distance to diary
        dist_onset = None
        dist_offset = None
        if self.diary:
            if self.diary.sleep_onset:
                dist_onset = abs((onset_time - self.diary.sleep_onset).total_seconds()) / 60.0
            if self.diary.wake_time:
                dist_offset = abs((offset_time - self.diary.wake_time).total_seconds()) / 60.0

        # Spike detection
        has_spike_onset = self.spike_detector.has_spike_near(onset_idx, window_epochs=5)
        has_spike_offset = self.spike_detector.has_spike_near(offset_idx, window_epochs=5)
        spike_before_onset = self.spike_detector.get_spike_near(onset_idx - 5, window_epochs=5)

        return SleepPeriodCandidate(
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            onset_time=onset_time,
            offset_time=offset_time,
            onset_consecutive_sleep=onset_run.epoch_count,
            offset_consecutive_sleep=offset_run.epoch_count,
            duration_minutes=duration,
            contains_choi_nonwear=self._contains_choi_nonwear(onset_idx, offset_idx),
            contains_diary_nonwear=self._overlaps_diary_nonwear(onset_time, offset_time),
            distance_to_diary_onset_minutes=dist_onset,
            distance_to_diary_offset_minutes=dist_offset,
            has_spike_at_onset=has_spike_onset,
            has_spike_at_offset=has_spike_offset,
            spike_before_onset=spike_before_onset,
            nonwear_near_onset=self._has_nonwear_near(onset_idx),
            nonwear_near_offset=self._has_nonwear_near(offset_idx),
        )

    def _has_nonwear_overlap(self, candidate: SleepPeriodCandidate) -> bool:
        """Check if candidate has BOTH Choi AND diary nonwear overlap."""
        return candidate.contains_choi_nonwear and candidate.contains_diary_nonwear

    def _contains_choi_nonwear(self, start_idx: int, end_idx: int) -> bool:
        """Check if range contains any Choi-detected nonwear."""
        return any(self.epochs[i].is_choi_nonwear for i in range(start_idx, end_idx + 1))

    def _overlaps_diary_nonwear(self, start: datetime, end: datetime) -> bool:
        """Check if period overlaps any diary nonwear."""
        if not self.diary:
            return False
        return any(start <= nw.end_time and end >= nw.start_time for nw in self.diary.nonwear_periods)

    def _has_nonwear_near(self, idx: int, window: int = 5) -> bool:
        """Check if there's nonwear within window of index."""
        start = max(0, idx - window)
        end = min(len(self.epochs) - 1, idx + window)
        return any(self.epochs[i].is_choi_nonwear for i in range(start, end + 1))

    def _overlaps_diary_nap(self, run: SleepRun) -> bool:
        """Check if run overlaps a diary-reported nap."""
        if not self.diary:
            return False
        return any(run.start_time <= nap.end_time and run.end_time >= nap.start_time for nap in self.diary.nap_periods)

    def _overlaps_diary_nap_exactly(self, run: SleepRun) -> bool:
        """Check if run overlaps diary nap within tolerance."""
        if not self.diary:
            return False
        tolerance = timedelta(minutes=self.config.nap_diary_overlap_tolerance_minutes)
        return any(abs(run.start_time - nap.start_time) <= tolerance for nap in self.diary.nap_periods)

    def _has_cross_day_nap_pattern(self, run: SleepRun) -> bool:
        """Check if similar nap time exists on other days."""
        if not self.cross_day:
            return False
        return self.cross_day.has_nap_at_similar_time(run.start_time)


class MainSleepPeriodRule:
    """
    Selects the best main sleep period candidate.

    Selection criteria:
    1. Prefer candidates within diary tolerance (15 min)
    2. If multiple within tolerance, prefer lowest issue_score
    3. If equidistant from diary, prefer fewer issues (Rule 6)
    4. If only one candidate, tolerance not required
    5. Prefer longer duration if all else equal
    """

    def __init__(self, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()

    def select(
        self,
        candidates: list[SleepPeriodCandidate],
        cross_day: CrossDayFeatures | None = None,
    ) -> SleepPeriodCandidate | None:
        """
        Select the best candidate.

        Args:
            candidates: List of candidates to choose from
            cross_day: Optional cross-day features for Rule 6/7

        Returns:
            Best candidate or None if no valid candidates

        """
        if not candidates:
            return None

        # If only one candidate, return it (Rule 5: tolerance not required)
        if len(candidates) == 1:
            return candidates[0]

        # Separate candidates by diary tolerance
        within_tolerance = [c for c in candidates if c.is_within_diary_tolerance]
        outside_tolerance = [c for c in candidates if not c.is_within_diary_tolerance]

        # Prefer candidates within tolerance
        pool = within_tolerance if within_tolerance else outside_tolerance

        # Score and sort candidates
        scored = []
        for c in pool:
            score = self._compute_score(c, cross_day)
            scored.append((score, c))

        # Sort by score (lower is better), then duration (higher is better)
        scored.sort(key=lambda x: (x[0], -x[1].duration_minutes))

        return scored[0][1] if scored else None

    def _compute_score(
        self,
        candidate: SleepPeriodCandidate,
        cross_day: CrossDayFeatures | None,
    ) -> float:
        """Compute a selection score (lower is better)."""
        score = 0.0

        # Base issue score
        score += candidate.issue_score * 10

        # Distance to diary (prefer closer)
        if candidate.distance_to_diary_onset_minutes is not None:
            score += candidate.distance_to_diary_onset_minutes
        if candidate.distance_to_diary_offset_minutes is not None:
            score += candidate.distance_to_diary_offset_minutes

        # Rule 7: Penalize if nonwear at similar time on other days
        if cross_day:
            if cross_day.has_nonwear_at_similar_time(candidate.onset_time):
                score += 20
            if cross_day.has_nonwear_at_similar_time(candidate.offset_time):
                score += 20

        return score


class NapPeriodRule:
    """
    Selects valid nap periods.

    Selection criteria:
    1. Must have diary confirmation (same day or cross-day pattern)
    2. If overlaps diary exactly, nonwear can be ignored
    3. Prefer longer continuous sleep periods (>=10 epochs)
    4. If diary shows nap timing variation, be more lenient with marking
    """

    def __init__(self, config: RuleConfig | None = None) -> None:
        self.config = config or RuleConfig()

    def select_all(
        self,
        candidates: list[NapCandidate],
        cross_day: CrossDayFeatures | None = None,
    ) -> list[NapCandidate]:
        """
        Select all valid nap candidates.

        Args:
            candidates: List of nap candidates
            cross_day: Optional cross-day features

        Returns:
            List of valid naps

        """
        valid_naps = []

        # Check if diary shows variable nap timing (Rule 4)
        high_nap_variance = (
            cross_day is not None and cross_day.nap_time_variance_minutes > 60  # >1 hour variance
        )

        for candidate in candidates:
            # Must have diary confirmation
            if not candidate.is_valid_nap():
                continue

            # If nonwear, check if we can ignore it
            if candidate.contains_choi_nonwear:
                if candidate.can_ignore_nonwear:
                    # Rule: exact diary overlap allows ignoring nonwear
                    pass
                elif not high_nap_variance:
                    # Skip if nonwear and diary doesn't show high variance
                    continue

            valid_naps.append(candidate)

        # Sort by duration (longer first)
        valid_naps.sort(key=lambda c: -c.duration_minutes)

        return valid_naps


class AutomatedMarkerPlacer:
    """
    Main entry point for automated marker placement.

    Combines all rules and feature extractors to place markers.
    """

    def __init__(
        self,
        timestamps: list[datetime],
        activity_counts: list[float],
        sleep_scores: list[int],
        choi_nonwear: list[bool] | None = None,
        diary: DiaryDay | None = None,
        all_diary_days: list[DiaryDay] | None = None,
        config: RuleConfig | None = None,
    ) -> None:
        """
        Initialize marker placer.

        Args:
            timestamps: Epoch timestamps
            activity_counts: Activity count values
            sleep_scores: Sleep classifications (0=wake, 1=sleep)
            choi_nonwear: Optional Choi nonwear flags
            diary: Diary data for current day
            all_diary_days: All diary days for cross-day patterns
            config: Rule configuration

        """
        self.config = config or RuleConfig()

        # Extract features
        self.epoch_extractor = EpochFeatureExtractor(timestamps, activity_counts, sleep_scores, choi_nonwear, diary)
        self.epochs = self.epoch_extractor.extract()

        # Encode runs
        self.run_encoder = RunLengthEncoder(self.epochs, self.config.epoch_length_seconds)
        self.runs = self.run_encoder.encode()

        # Detect spikes
        self.spike_detector = SpikeDetector(self.epochs, spike_threshold_std=self.config.spike_threshold_std)

        # Cross-day features
        self.cross_day = None
        if all_diary_days:
            aggregator = CrossDayAggregator(all_diary_days)
            self.cross_day = aggregator.aggregate()

        # Initialize candidate finder
        self.candidate_finder = SleepPeriodCandidateFinder(self.epochs, self.runs, self.spike_detector, diary, self.cross_day, self.config)

    def place_main_sleep(self) -> SleepPeriodCandidate | None:
        """Find and select the best main sleep period."""
        candidates = self.candidate_finder.find_main_sleep_candidates()
        logger.info(f"Found {len(candidates)} main sleep candidates")

        rule = MainSleepPeriodRule(self.config)
        selected = rule.select(candidates, self.cross_day)

        if selected:
            logger.info(
                f"Selected main sleep: {selected.onset_time} - {selected.offset_time} "
                f"(duration={selected.duration_minutes:.1f}min, issues={selected.issue_score})"
            )

        return selected

    def place_naps(self) -> list[NapCandidate]:
        """Find and select all valid nap periods."""
        candidates = self.candidate_finder.find_nap_candidates()
        logger.info(f"Found {len(candidates)} nap candidates")

        rule = NapPeriodRule(self.config)
        selected = rule.select_all(candidates, self.cross_day)

        for nap in selected:
            logger.info(
                f"Selected nap: {nap.onset_time} - {nap.offset_time} "
                f"(duration={nap.duration_minutes:.1f}min, diary_confirmed={nap.has_diary_nap_confirmation})"
            )

        return selected

    def get_all_spikes(self) -> list[ActivitySpike]:
        """Get all detected activity spikes."""
        return self.spike_detector.detect()

    def get_feature_summary(self) -> dict:
        """Get a summary of extracted features for debugging."""
        return {
            "total_epochs": len(self.epochs),
            "sleep_epochs": sum(1 for e in self.epochs if e.sleep_score == 1),
            "wake_epochs": sum(1 for e in self.epochs if e.sleep_score == 0),
            "nonwear_epochs": sum(1 for e in self.epochs if e.is_choi_nonwear),
            "sleep_runs": len([r for r in self.runs if r.is_sleep]),
            "wake_runs": len([r for r in self.runs if not r.is_sleep]),
            "spikes_detected": len(self.spike_detector.detect()),
            "spike_threshold": self.spike_detector.spike_threshold,
            "cross_day_nap_times": len(self.cross_day.all_nap_times) if self.cross_day else 0,
            "cross_day_nonwear_times": len(self.cross_day.all_nonwear_times) if self.cross_day else 0,
        }
