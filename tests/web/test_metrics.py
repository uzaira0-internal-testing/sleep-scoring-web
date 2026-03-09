"""
Tests for the Tudor-Locke sleep metrics calculator.

Tests verify the TudorLockeSleepMetricsCalculator produces correct metrics
matching the actigraph.sleepr R package implementation.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sleep_scoring_web.schemas.enums import MarkerLimits
from sleep_scoring_web.services.metrics import TudorLockeSleepMetricsCalculator


class TestTudorLockeSleepMetricsCalculator:
    """Tests for the metrics calculator."""

    @pytest.fixture
    def calculator(self) -> TudorLockeSleepMetricsCalculator:
        """Create a calculator instance."""
        return TudorLockeSleepMetricsCalculator()

    @pytest.fixture
    def simple_sleep_data(self) -> dict:
        """
        Create simple test data with known metrics.

        60 epochs (1 hour), all sleep, zero activity.
        Expected metrics:
        - TST = 60 minutes
        - TIB = 60 minutes
        - WASO = 0
        - Sleep Efficiency = 100%
        - Awakenings = 0
        """
        base_time = datetime(2024, 1, 1, 22, 0, 0)
        return {
            "sleep_scores": [1] * 60,  # All sleep
            "activity_counts": [0.0] * 60,  # No activity
            "timestamps": [base_time + timedelta(minutes=i) for i in range(60)],
            "onset_idx": 0,
            "offset_idx": 59,
        }

    @pytest.fixture
    def mixed_sleep_data(self) -> dict:
        """
        Create test data with mixed sleep/wake.

        100 epochs total:
        - First 10 epochs: wake
        - Middle 70 epochs: sleep
        - Last 20 epochs: wake

        Expected:
        - TST = 70 minutes
        - TIB = 100 minutes
        - SOL = 10 minutes (leading wake before first sleep)
        - WASO = 20 minutes (trailing wake after last sleep)
        - Sleep Efficiency = 70%
        - Awakenings = 1 (only wake bouts after first sleep epoch count)
        """
        base_time = datetime(2024, 1, 1, 22, 0, 0)
        sleep_scores = [0] * 10 + [1] * 70 + [0] * 20
        activity_counts = [50.0] * 10 + [5.0] * 70 + [100.0] * 20
        timestamps = [base_time + timedelta(minutes=i) for i in range(100)]

        return {
            "sleep_scores": sleep_scores,
            "activity_counts": activity_counts,
            "timestamps": timestamps,
            "onset_idx": 0,
            "offset_idx": 99,
        }

    @pytest.fixture
    def fragmented_sleep_data(self) -> dict:
        """
        Create test data with fragmented sleep.

        Pattern: Sleep, Wake, Sleep, Wake, Sleep (alternating)
        10 single-epoch sleep bouts
        """
        base_time = datetime(2024, 1, 1, 22, 0, 0)
        # Alternating pattern: 1 sleep, 1 wake repeated
        sleep_scores = [1, 0] * 10  # 20 epochs total, 10 sleep
        activity_counts = [10.0 if i % 2 == 0 else 50.0 for i in range(20)]
        timestamps = [base_time + timedelta(minutes=i) for i in range(20)]

        return {
            "sleep_scores": sleep_scores,
            "activity_counts": activity_counts,
            "timestamps": timestamps,
            "onset_idx": 0,
            "offset_idx": 19,
        }

    def test_calculate_metrics_all_sleep(self, calculator: TudorLockeSleepMetricsCalculator, simple_sleep_data: dict):
        """Test metrics calculation with all sleep epochs."""
        metrics = calculator.calculate_metrics(**simple_sleep_data)

        # Duration metrics
        assert metrics["total_sleep_time_minutes"] == 60.0
        assert metrics["time_in_bed_minutes"] == 60.0
        assert metrics["waso_minutes"] == 0.0
        assert metrics["sleep_onset_latency_minutes"] == 0.0

        # Quality indices
        assert metrics["sleep_efficiency"] == 100.0
        assert metrics["number_of_awakenings"] == 0
        assert metrics["average_awakening_length_minutes"] == 0.0

        # Activity metrics
        assert metrics["total_activity"] == 0
        assert metrics["nonzero_epochs"] == 0
        assert metrics["movement_index"] == 0.0

        # Fragmentation (all one bout)
        assert metrics["fragmentation_index"] == 0.0

    def test_calculate_metrics_mixed_sleep(self, calculator: TudorLockeSleepMetricsCalculator, mixed_sleep_data: dict):
        """Test metrics calculation with mixed sleep/wake."""
        metrics = calculator.calculate_metrics(**mixed_sleep_data)

        # Duration metrics
        assert metrics["total_sleep_time_minutes"] == 70.0
        assert metrics["time_in_bed_minutes"] == 100.0
        assert metrics["sleep_onset_latency_minutes"] == 10.0  # 10 leading wake epochs
        assert metrics["waso_minutes"] == 20.0  # 20 trailing wake epochs (SOL excluded)

        # Quality indices
        assert metrics["sleep_efficiency"] == 70.0
        assert metrics["number_of_awakenings"] == 1  # Only trailing wake bout (SOL excluded)

        # Activity metrics
        assert metrics["total_activity"] > 0
        assert metrics["nonzero_epochs"] == 100  # All have some activity

    def test_calculate_metrics_fragmented_sleep(self, calculator: TudorLockeSleepMetricsCalculator, fragmented_sleep_data: dict):
        """Test fragmentation index calculation with highly fragmented sleep."""
        metrics = calculator.calculate_metrics(**fragmented_sleep_data)

        # With alternating single-epoch sleep bouts, fragmentation should be 100%
        # All 10 sleep bouts are 1-minute bouts
        assert metrics["fragmentation_index"] == 100.0
        assert metrics["sleep_fragmentation_index"] > 100.0  # movement + fragmentation

    def test_period_boundaries(self, calculator: TudorLockeSleepMetricsCalculator, simple_sleep_data: dict):
        """Test that period boundaries are correctly identified."""
        metrics = calculator.calculate_metrics(**simple_sleep_data)

        assert metrics["in_bed_time"] == simple_sleep_data["timestamps"][0]
        assert metrics["out_bed_time"] == simple_sleep_data["timestamps"][-1]
        # With all sleep, onset and offset should match first/last
        assert metrics["sleep_onset"] == simple_sleep_data["timestamps"][0]
        assert metrics["sleep_offset"] == simple_sleep_data["timestamps"][-1]

    def test_sleep_onset_offset_detection(self, calculator: TudorLockeSleepMetricsCalculator, mixed_sleep_data: dict):
        """Test detection of first and last sleep epochs."""
        metrics = calculator.calculate_metrics(**mixed_sleep_data)

        # First sleep at index 10, last sleep at index 79
        expected_onset = mixed_sleep_data["timestamps"][10]
        expected_offset = mixed_sleep_data["timestamps"][79]

        assert metrics["sleep_onset"] == expected_onset
        assert metrics["sleep_offset"] == expected_offset

    def test_uses_epoch_duration_constant(self, calculator: TudorLockeSleepMetricsCalculator, simple_sleep_data: dict):
        """Test that default epoch duration uses the constant."""
        # Default should use MarkerLimits.EPOCH_DURATION_SECONDS (60)
        assert MarkerLimits.EPOCH_DURATION_SECONDS == 60
        metrics = calculator.calculate_metrics(**simple_sleep_data)
        # 60 epochs * 1 minute = 60 minutes
        assert metrics["time_in_bed_minutes"] == 60.0

    def test_custom_epoch_duration(self, calculator: TudorLockeSleepMetricsCalculator, simple_sleep_data: dict):
        """Test metrics with custom epoch duration (30 seconds)."""
        metrics = calculator.calculate_metrics(**simple_sleep_data, epoch_seconds=30)

        # 60 epochs * 0.5 minutes = 30 minutes
        assert metrics["time_in_bed_minutes"] == 30.0
        assert metrics["total_sleep_time_minutes"] == 30.0

    def test_movement_index_calculation(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test movement index calculation."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        # 10 epochs, 5 with activity > 0
        sleep_scores = [1] * 10
        activity_counts = [0.0, 10.0, 0.0, 20.0, 0.0, 30.0, 0.0, 40.0, 0.0, 50.0]
        timestamps = [base_time + timedelta(minutes=i) for i in range(10)]

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=timestamps,
        )

        assert metrics["nonzero_epochs"] == 5
        assert metrics["movement_index"] == 50.0  # 5/10 * 100

    def test_awakening_count(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test awakening count with multiple wake bouts."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        # Pattern: S S W W S S W S S S
        # Wake bouts: epochs 2-3 (first bout), epoch 6 (second bout)
        sleep_scores = [1, 1, 0, 0, 1, 1, 0, 1, 1, 1]
        activity_counts = [0.0] * 10
        timestamps = [base_time + timedelta(minutes=i) for i in range(10)]

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=timestamps,
        )

        # 2 distinct wake bouts
        assert metrics["number_of_awakenings"] == 2

    def test_average_awakening_length(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test average awakening length calculation."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        # 10 epochs: 5 sleep, 5 wake in 2 bouts (2 + 3)
        # Pattern: S S W W S S S W W W
        sleep_scores = [1, 1, 0, 0, 1, 1, 1, 0, 0, 0]
        activity_counts = [0.0] * 10
        timestamps = [base_time + timedelta(minutes=i) for i in range(10)]

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=timestamps,
        )

        # WASO = 5 minutes (5 wake epochs)
        # 2 awakenings
        # Average = 5/2 = 2.5 minutes
        assert metrics["waso_minutes"] == 5.0
        assert metrics["number_of_awakenings"] == 2
        assert metrics["average_awakening_length_minutes"] == 2.5


class TestTudorLockeValidation:
    """Test input validation for the metrics calculator."""

    @pytest.fixture
    def calculator(self) -> TudorLockeSleepMetricsCalculator:
        """Create a calculator instance."""
        return TudorLockeSleepMetricsCalculator()

    def test_empty_sleep_scores_raises(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test that empty sleep scores raises ValueError."""
        with pytest.raises(ValueError, match="sleep_scores cannot be empty"):
            calculator.calculate_metrics(
                sleep_scores=[],
                activity_counts=[],
                onset_idx=0,
                offset_idx=0,
                timestamps=[],
            )

    def test_mismatched_lengths_raises(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test that mismatched array lengths raises ValueError."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        with pytest.raises(ValueError, match="must have same length"):
            calculator.calculate_metrics(
                sleep_scores=[1, 1, 1],
                activity_counts=[0.0, 0.0],  # Different length
                onset_idx=0,
                offset_idx=2,
                timestamps=[base_time + timedelta(minutes=i) for i in range(3)],
            )

    def test_invalid_onset_idx_raises(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test that invalid onset index raises ValueError."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        with pytest.raises(ValueError, match=r"onset_idx.*out of range"):
            calculator.calculate_metrics(
                sleep_scores=[1, 1, 1],
                activity_counts=[0.0, 0.0, 0.0],
                onset_idx=-1,  # Invalid
                offset_idx=2,
                timestamps=[base_time + timedelta(minutes=i) for i in range(3)],
            )

    def test_onset_greater_than_offset_raises(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test that onset >= offset raises ValueError."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        with pytest.raises(ValueError, match=r"onset_idx.*must be less than offset_idx"):
            calculator.calculate_metrics(
                sleep_scores=[1, 1, 1],
                activity_counts=[0.0, 0.0, 0.0],
                onset_idx=2,
                offset_idx=1,  # onset > offset
                timestamps=[base_time + timedelta(minutes=i) for i in range(3)],
            )


class TestSleepOnsetLatencyBugFix:
    """Tests for the SOL falsy-zero bug fix (first_sleep_idx=0 was treated as falsy)."""

    def test_sol_is_zero_when_first_epoch_is_sleep(self):
        """Bug #2: first_sleep_idx=0 was treated as falsy, giving SOL=0 always."""
        calculator = TudorLockeSleepMetricsCalculator()
        sleep_scores = [1, 1, 1, 1, 1]
        activity_counts = [0.0, 0.0, 0.0, 0.0, 0.0]
        timestamps = [
            datetime(2024, 1, 1, 22, 0),
            datetime(2024, 1, 1, 22, 1),
            datetime(2024, 1, 1, 22, 2),
            datetime(2024, 1, 1, 22, 3),
            datetime(2024, 1, 1, 22, 4),
        ]
        result = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            timestamps=timestamps,
            onset_idx=0,
            offset_idx=4,
        )
        assert result["sleep_onset_latency_minutes"] == 0.0

    def test_sol_nonzero_when_wake_before_sleep(self):
        """SOL should equal minutes of wake before first sleep epoch."""
        calculator = TudorLockeSleepMetricsCalculator()
        sleep_scores = [0, 0, 1, 1, 1]
        activity_counts = [100.0, 50.0, 0.0, 0.0, 0.0]
        timestamps = [
            datetime(2024, 1, 1, 22, 0),
            datetime(2024, 1, 1, 22, 1),
            datetime(2024, 1, 1, 22, 2),
            datetime(2024, 1, 1, 22, 3),
            datetime(2024, 1, 1, 22, 4),
        ]
        result = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            timestamps=timestamps,
            onset_idx=0,
            offset_idx=4,
        )
        assert result["sleep_onset_latency_minutes"] == 2.0


class TestTudorLockeEdgeCases:
    """Test edge cases for the metrics calculator."""

    @pytest.fixture
    def calculator(self) -> TudorLockeSleepMetricsCalculator:
        """Create a calculator instance."""
        return TudorLockeSleepMetricsCalculator()

    def test_all_wake_epochs(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test metrics with all wake epochs (edge case)."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        metrics = calculator.calculate_metrics(
            sleep_scores=[0, 0, 0, 0, 0],
            activity_counts=[100.0] * 5,
            onset_idx=0,
            offset_idx=4,
            timestamps=[base_time + timedelta(minutes=i) for i in range(5)],
        )

        assert metrics["total_sleep_time_minutes"] == 0.0
        assert metrics["waso_minutes"] == 5.0
        assert metrics["sleep_efficiency"] == 0.0
        # sleep_onset/offset should fall back to first/last timestamp
        assert metrics["sleep_onset"] == base_time
        assert metrics["sleep_offset"] == base_time + timedelta(minutes=4)

    def test_single_epoch_period(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test with minimum valid period (2 epochs since onset < offset)."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        metrics = calculator.calculate_metrics(
            sleep_scores=[1, 1],
            activity_counts=[0.0, 0.0],
            onset_idx=0,
            offset_idx=1,
            timestamps=[base_time, base_time + timedelta(minutes=1)],
        )

        assert metrics["time_in_bed_minutes"] == 2.0
        assert metrics["total_sleep_time_minutes"] == 2.0

    def test_partial_period_within_data(self, calculator: TudorLockeSleepMetricsCalculator):
        """Test calculating metrics for a subset of the total data."""
        base_time = datetime(2024, 1, 1, 22, 0, 0)

        # 100 epochs total, but only use indices 20-50
        full_sleep = [1] * 100
        full_activity = [float(i) for i in range(100)]
        full_timestamps = [base_time + timedelta(minutes=i) for i in range(100)]

        metrics = calculator.calculate_metrics(
            sleep_scores=full_sleep,
            activity_counts=full_activity,
            onset_idx=20,
            offset_idx=50,
            timestamps=full_timestamps,
        )

        # Period is 31 epochs (index 20 to 50 inclusive)
        assert metrics["time_in_bed_minutes"] == 31.0
        assert metrics["in_bed_time"] == full_timestamps[20]
        assert metrics["out_bed_time"] == full_timestamps[50]
