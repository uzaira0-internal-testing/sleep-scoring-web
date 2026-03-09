"""
Unit tests for Tudor-Locke sleep quality metrics calculation.

Tests the SleepPeriodMetrics dataclass and TudorLockeSleepMetricsCalculator
to ensure accurate calculation of all sleep quality metrics.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sleep_scoring_app.core.algorithms import (
    SleepPeriodMetrics,
    TudorLockeSleepMetricsCalculator,
)


class TestTudorLockeSleepMetricsCalculator:
    """Test suite for TudorLockeSleepMetricsCalculator."""

    @pytest.fixture
    def calculator(self) -> TudorLockeSleepMetricsCalculator:
        """Create calculator instance."""
        return TudorLockeSleepMetricsCalculator()

    @pytest.fixture
    def base_timestamps(self) -> list[datetime]:
        """Create base timestamp list (60 epochs = 1 hour)."""
        base = datetime(2024, 1, 1, 22, 0, 0)  # 10 PM
        return [base + timedelta(minutes=i) for i in range(60)]

    def test_perfect_sleep_no_awakenings(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test metrics for perfect sleep with no awakenings."""
        # 60 minutes of continuous sleep
        sleep_scores = [1] * 60
        activity_counts = [0.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Verify duration metrics
        assert metrics.time_in_bed == 60.0
        assert metrics.total_sleep_time == 60.0
        assert metrics.sleep_onset_latency == 0.0
        assert metrics.wake_after_sleep_onset == 0.0

        # Verify awakening metrics
        assert metrics.num_awakenings == 0
        assert metrics.avg_awakening_length == 0.0

        # Verify quality indices
        assert metrics.sleep_efficiency == 100.0
        assert metrics.movement_index == 0.0
        assert metrics.fragmentation_index == 0.0
        assert metrics.sleep_fragmentation_index == 0.0

        # Verify activity metrics
        assert metrics.total_activity_counts == 0.0
        assert metrics.nonzero_epochs == 0

    def test_sleep_with_single_awakening(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test metrics with a single awakening in the middle."""
        # 30 sleep + 10 wake + 20 sleep = 60 minutes total
        sleep_scores = [1] * 30 + [0] * 10 + [1] * 20
        activity_counts = [0.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Verify duration metrics
        assert metrics.time_in_bed == 60.0
        assert metrics.total_sleep_time == 50.0  # 30 + 20
        assert metrics.wake_after_sleep_onset == 10.0  # 60 - 50 - 0

        # Verify awakening metrics
        assert metrics.num_awakenings == 1
        assert metrics.avg_awakening_length == 10.0

        # Verify quality indices
        assert metrics.sleep_efficiency == pytest.approx(83.33, rel=0.01)  # 50/60 * 100

    def test_sleep_with_multiple_awakenings(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test metrics with multiple awakenings."""
        # Pattern: 20S + 5W + 10S + 5W + 20S = 60 minutes
        sleep_scores = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 5 + [1] * 20
        activity_counts = [0.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Verify awakening metrics
        assert metrics.num_awakenings == 2
        assert metrics.wake_after_sleep_onset == 10.0  # 5 + 5
        assert metrics.avg_awakening_length == 5.0  # 10 / 2

        # Verify total sleep time
        assert metrics.total_sleep_time == 50.0  # 20 + 10 + 20

    def test_movement_index_with_activity(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test movement index calculation with activity."""
        sleep_scores = [1] * 60
        # 30 epochs with activity, 30 without
        activity_counts = [100.0] * 30 + [0.0] * 30
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Verify activity metrics
        assert metrics.nonzero_epochs == 30
        assert metrics.total_activity_counts == 3000.0  # 100 * 30
        assert metrics.movement_index == 50.0  # 30/60 * 100

    def test_fragmentation_index_single_minute_bouts(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test fragmentation index with multiple 1-minute sleep bouts."""
        # Pattern: alternating 1 sleep, 1 wake for 60 minutes
        sleep_scores = [1, 0] * 30
        activity_counts = [0.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Should have 30 sleep bouts, all 1 minute long
        assert metrics.num_awakenings == 30  # 30 wake periods
        assert metrics.fragmentation_index == 100.0  # 30/30 * 100 (all bouts are 1-minute)

    def test_fragmentation_index_mixed_bouts(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test fragmentation index with mixed bout lengths."""
        # Pattern: 1S + 1W + 5S + 1W + 10S + 1W + 1S + 1W (remaining fill with sleep)
        sleep_scores = [1] + [0] + [1] * 5 + [0] + [1] * 10 + [0] + [1] + [0] + [1] * 39
        activity_counts = [0.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Sleep bouts: 1, 5, 10, 1, 39 = 5 total bouts
        # 1-minute bouts: 2 (first and fourth)
        # Fragmentation index = 2/5 * 100 = 40%
        assert metrics.fragmentation_index == 40.0

    def test_sleep_fragmentation_index(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test that sleep fragmentation index is sum of movement and fragmentation."""
        sleep_scores = [1] * 60
        activity_counts = [100.0] * 20 + [0.0] * 40  # 20 epochs with activity
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Movement index = 20/60 * 100 = 33.33%
        # Fragmentation index = 0% (single sleep bout)
        # Sleep fragmentation = 33.33 + 0 = 33.33
        assert metrics.movement_index == pytest.approx(33.33, rel=0.01)
        assert metrics.fragmentation_index == 0.0
        assert metrics.sleep_fragmentation_index == pytest.approx(33.33, rel=0.01)

    def test_sleep_onset_offset_detection(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test detection of first and last sleep epochs."""
        # Pattern: 5W + 30S + 10W + 10S + 5W
        sleep_scores = [0] * 5 + [1] * 30 + [0] * 10 + [1] * 10 + [0] * 5
        activity_counts = [0.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Sleep onset should be at index 5 (first sleep epoch)
        # Sleep offset should be at index 54 (last sleep epoch)
        assert metrics.sleep_onset == base_timestamps[5]
        assert metrics.sleep_offset == base_timestamps[54]

    def test_period_boundaries(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test that period boundaries match onset and offset indices."""
        sleep_scores = [1] * 60
        activity_counts = [0.0] * 60
        onset_idx = 10
        offset_idx = 49

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        assert metrics.in_bed_time == base_timestamps[10]
        assert metrics.out_bed_time == base_timestamps[49]
        assert metrics.time_in_bed == 40.0  # indices 10-49 inclusive

    def test_partial_sleep_period(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test metrics calculated on a subset of the data."""
        # Full data is 60 minutes, but we only analyze minutes 20-40
        sleep_scores = [1] * 60
        activity_counts = [50.0] * 60
        onset_idx = 20
        offset_idx = 39

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        assert metrics.time_in_bed == 20.0  # 20 minutes
        assert metrics.total_sleep_time == 20.0
        assert metrics.sleep_efficiency == 100.0
        assert metrics.total_activity_counts == 1000.0  # 50 * 20

    def test_mathematical_consistency(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test that metrics are mathematically consistent."""
        # Pattern: 40S + 10W + 10S = 60 minutes
        sleep_scores = [1] * 40 + [0] * 10 + [1] * 10
        activity_counts = [0.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # TST + WASO + latency should equal TIB
        assert metrics.total_sleep_time + metrics.wake_after_sleep_onset + metrics.sleep_onset_latency == metrics.time_in_bed

        # Sleep efficiency should match TST/TIB * 100
        expected_efficiency = metrics.total_sleep_time / metrics.time_in_bed * 100
        assert metrics.sleep_efficiency == pytest.approx(expected_efficiency)

    def test_no_sleep_epochs(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test handling of period with no sleep epochs."""
        # All wake
        sleep_scores = [0] * 60
        activity_counts = [100.0] * 60
        onset_idx = 0
        offset_idx = 59

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=base_timestamps,
        )

        # Should handle gracefully
        assert metrics.total_sleep_time == 0.0
        assert metrics.sleep_efficiency == 0.0
        assert metrics.num_awakenings == 1  # One continuous wake bout
        assert metrics.fragmentation_index == 0.0  # No sleep bouts

    def test_validation_empty_sleep_scores(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test validation rejects empty sleep scores."""
        with pytest.raises(ValueError, match="sleep_scores cannot be empty"):
            calculator.calculate_metrics(
                sleep_scores=[],
                activity_counts=[],
                onset_idx=0,
                offset_idx=0,
                timestamps=[],
            )

    def test_validation_mismatched_lengths(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test validation rejects mismatched array lengths."""
        sleep_scores = [1] * 60
        activity_counts = [0.0] * 50  # Wrong length

        with pytest.raises(ValueError, match="must have same length"):
            calculator.calculate_metrics(
                sleep_scores=sleep_scores,
                activity_counts=activity_counts,
                onset_idx=0,
                offset_idx=59,
                timestamps=base_timestamps,
            )

    def test_validation_invalid_onset_index(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test validation rejects invalid onset index."""
        sleep_scores = [1] * 60
        activity_counts = [0.0] * 60

        with pytest.raises(ValueError, match=r"onset_idx.*out of range"):
            calculator.calculate_metrics(
                sleep_scores=sleep_scores,
                activity_counts=activity_counts,
                onset_idx=-1,
                offset_idx=59,
                timestamps=base_timestamps,
            )

    def test_validation_invalid_offset_index(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test validation rejects invalid offset index."""
        sleep_scores = [1] * 60
        activity_counts = [0.0] * 60

        with pytest.raises(ValueError, match=r"offset_idx.*out of range"):
            calculator.calculate_metrics(
                sleep_scores=sleep_scores,
                activity_counts=activity_counts,
                onset_idx=0,
                offset_idx=100,
                timestamps=base_timestamps,
            )

    def test_validation_onset_after_offset(self, calculator: TudorLockeSleepMetricsCalculator, base_timestamps: list[datetime]) -> None:
        """Test validation rejects onset index >= offset index."""
        sleep_scores = [1] * 60
        activity_counts = [0.0] * 60

        with pytest.raises(ValueError, match=r"onset_idx.*must be less than offset_idx"):
            calculator.calculate_metrics(
                sleep_scores=sleep_scores,
                activity_counts=activity_counts,
                onset_idx=50,
                offset_idx=10,
                timestamps=base_timestamps,
            )

    def test_edge_case_single_epoch_period(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Test handling of minimum period length (onset == offset - 1)."""
        sleep_scores = [1] * 10
        activity_counts = [100.0] * 10
        timestamps = [datetime(2024, 1, 1, 22, 0, 0) + timedelta(minutes=i) for i in range(10)]
        onset_idx = 0
        offset_idx = 1  # Just 2 epochs

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=timestamps,
        )

        assert metrics.time_in_bed == 2.0
        assert metrics.total_sleep_time == 2.0

    def test_realistic_sleep_scenario(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Test with realistic sleep data mimicking actual actigraphy."""
        # 8 hours of sleep (480 minutes) with typical fragmentation
        base = datetime(2024, 1, 1, 22, 0, 0)
        timestamps = [base + timedelta(minutes=i) for i in range(480)]

        # Realistic pattern:
        # 10 min wake (sleep onset latency in real data)
        # 120 min sleep
        # 5 min wake (brief awakening)
        # 200 min sleep
        # 10 min wake (another awakening)
        # 130 min sleep
        # 5 min wake at end
        sleep_scores = (
            [0] * 10  # Initial wake
            + [1] * 120  # First sleep block
            + [0] * 5  # Awakening 1
            + [1] * 200  # Second sleep block
            + [0] * 10  # Awakening 2
            + [1] * 130  # Third sleep block
            + [0] * 5  # Final wake
        )

        # Activity follows sleep/wake with some movement during sleep
        activity_counts = [50.0 if s == 0 else 5.0 for s in sleep_scores]
        # Add some zero-activity epochs during sleep
        for i in range(10, 130, 10):
            activity_counts[i] = 0.0

        onset_idx = 0
        offset_idx = 479

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=onset_idx,
            offset_idx=offset_idx,
            timestamps=timestamps,
        )

        # Verify key metrics
        assert metrics.time_in_bed == 480.0
        assert metrics.total_sleep_time == 450.0  # 120 + 200 + 130
        assert metrics.wake_after_sleep_onset == 30.0  # 10 + 5 + 10 + 5
        assert metrics.num_awakenings == 4
        assert metrics.avg_awakening_length == 7.5  # 30 / 4
        assert metrics.sleep_efficiency == pytest.approx(93.75)  # 450/480 * 100

        # Verify activity metrics
        assert metrics.total_activity_counts > 0
        assert metrics.nonzero_epochs > 0


class TestSleepPeriodMetricsDataclass:
    """Test suite for SleepPeriodMetrics dataclass."""

    def test_dataclass_immutable(self) -> None:
        """Test that SleepPeriodMetrics is frozen/immutable."""
        metrics = SleepPeriodMetrics(
            in_bed_time=datetime(2024, 1, 1, 22, 0, 0),
            out_bed_time=datetime(2024, 1, 2, 6, 0, 0),
            sleep_onset=datetime(2024, 1, 1, 22, 5, 0),
            sleep_offset=datetime(2024, 1, 2, 5, 55, 0),
            time_in_bed=480.0,
            total_sleep_time=450.0,
            sleep_onset_latency=0.0,
            wake_after_sleep_onset=30.0,
            num_awakenings=2,
            avg_awakening_length=15.0,
            sleep_efficiency=93.75,
            movement_index=25.0,
            fragmentation_index=10.0,
            sleep_fragmentation_index=35.0,
            total_activity_counts=5000.0,
            nonzero_epochs=120,
        )

        # Verify it's frozen
        with pytest.raises(AttributeError):
            metrics.total_sleep_time = 500.0  # type: ignore

    def test_dataclass_attributes(self) -> None:
        """Test that all expected attributes are present."""
        base = datetime(2024, 1, 1, 22, 0, 0)
        metrics = SleepPeriodMetrics(
            in_bed_time=base,
            out_bed_time=base + timedelta(hours=8),
            sleep_onset=base + timedelta(minutes=5),
            sleep_offset=base + timedelta(hours=7, minutes=55),
            time_in_bed=480.0,
            total_sleep_time=450.0,
            sleep_onset_latency=0.0,
            wake_after_sleep_onset=30.0,
            num_awakenings=2,
            avg_awakening_length=15.0,
            sleep_efficiency=93.75,
            movement_index=25.0,
            fragmentation_index=10.0,
            sleep_fragmentation_index=35.0,
            total_activity_counts=5000.0,
            nonzero_epochs=120,
        )

        # Verify all attributes
        assert metrics.in_bed_time == base
        assert metrics.out_bed_time == base + timedelta(hours=8)
        assert metrics.time_in_bed == 480.0
        assert metrics.total_sleep_time == 450.0
        assert metrics.sleep_onset_latency == 0.0
        assert metrics.wake_after_sleep_onset == 30.0
        assert metrics.num_awakenings == 2
        assert metrics.avg_awakening_length == 15.0
        assert metrics.sleep_efficiency == 93.75
        assert metrics.movement_index == 25.0
        assert metrics.fragmentation_index == 10.0
        assert metrics.sleep_fragmentation_index == 35.0
        assert metrics.total_activity_counts == 5000.0
        assert metrics.nonzero_epochs == 120
