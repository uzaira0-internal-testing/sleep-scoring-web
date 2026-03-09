"""
Tests for Tudor-Locke sleep quality metrics calculation.

Tests SleepPeriodMetrics dataclass and TudorLockeSleepMetricsCalculator.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sleep_scoring_app.core.algorithms.sleep_period.metrics import (
    SleepPeriodMetrics,
    TudorLockeSleepMetricsCalculator,
)


@pytest.fixture
def calculator() -> TudorLockeSleepMetricsCalculator:
    """Create a TudorLockeSleepMetricsCalculator instance."""
    return TudorLockeSleepMetricsCalculator()


@pytest.fixture
def sample_timestamps() -> list[datetime]:
    """Create sample 60-second epoch timestamps."""
    base_time = datetime(2024, 1, 15, 22, 0, 0)
    return [base_time + timedelta(minutes=i) for i in range(10)]


@pytest.fixture
def sample_sleep_scores() -> list[int]:
    """Create sample sleep/wake classifications (1=sleep, 0=wake)."""
    # Pattern: 0, 1, 1, 1, 0, 1, 1, 1, 1, 0
    #          wake, sleep, sleep, sleep, wake, sleep, sleep, sleep, sleep, wake
    return [0, 1, 1, 1, 0, 1, 1, 1, 1, 0]


@pytest.fixture
def sample_activity_counts() -> list[float]:
    """Create sample activity count values."""
    return [100.0, 10.0, 5.0, 0.0, 50.0, 8.0, 0.0, 0.0, 3.0, 80.0]


class TestSleepPeriodMetrics:
    """Tests for SleepPeriodMetrics dataclass."""

    def test_creates_frozen_dataclass(self) -> None:
        """Creates a frozen dataclass with all fields."""
        now = datetime.now()
        metrics = SleepPeriodMetrics(
            in_bed_time=now,
            out_bed_time=now + timedelta(hours=8),
            sleep_onset=now + timedelta(minutes=10),
            sleep_offset=now + timedelta(hours=7, minutes=50),
            time_in_bed=480.0,
            total_sleep_time=450.0,
            sleep_onset_latency=0.0,
            wake_after_sleep_onset=30.0,
            num_awakenings=3,
            avg_awakening_length=10.0,
            sleep_efficiency=93.75,
            movement_index=25.0,
            fragmentation_index=10.0,
            sleep_fragmentation_index=35.0,
            total_activity_counts=5000.0,
            nonzero_epochs=100,
        )

        assert metrics.time_in_bed == 480.0
        assert metrics.total_sleep_time == 450.0
        assert metrics.sleep_efficiency == 93.75

    def test_is_frozen(self) -> None:
        """Dataclass is frozen (immutable)."""
        now = datetime.now()
        metrics = SleepPeriodMetrics(
            in_bed_time=now,
            out_bed_time=now,
            sleep_onset=now,
            sleep_offset=now,
            time_in_bed=480.0,
            total_sleep_time=450.0,
            sleep_onset_latency=0.0,
            wake_after_sleep_onset=30.0,
            num_awakenings=3,
            avg_awakening_length=10.0,
            sleep_efficiency=93.75,
            movement_index=25.0,
            fragmentation_index=10.0,
            sleep_fragmentation_index=35.0,
            total_activity_counts=5000.0,
            nonzero_epochs=100,
        )

        with pytest.raises(AttributeError):
            metrics.time_in_bed = 500.0  # type: ignore


class TestCalculateMetrics:
    """Tests for calculate_metrics method."""

    def test_calculates_time_in_bed(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates time in bed correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        # 10 epochs * 1 minute = 10 minutes
        assert metrics.time_in_bed == 10.0

    def test_calculates_total_sleep_time(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates total sleep time correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        # 7 sleep epochs * 1 minute = 7 minutes
        assert metrics.total_sleep_time == 7.0

    def test_calculates_waso(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates wake after sleep onset correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        # WASO = TIB - TST - latency = 10 - 7 - 0 = 3
        assert metrics.wake_after_sleep_onset == 3.0

    def test_calculates_sleep_efficiency(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates sleep efficiency correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        # SE = TST / TIB * 100 = 7 / 10 * 100 = 70%
        assert metrics.sleep_efficiency == 70.0

    def test_calculates_num_awakenings(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates number of awakenings correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        # Pattern has 3 wake bouts: at index 0, 4, and 9
        assert metrics.num_awakenings == 3

    def test_calculates_total_activity_counts(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates total activity counts correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        expected = sum(sample_activity_counts)
        assert metrics.total_activity_counts == expected

    def test_calculates_nonzero_epochs(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates nonzero epochs correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        # Counts: 100, 10, 5, 0, 50, 8, 0, 0, 3, 80 -> 7 nonzero
        assert metrics.nonzero_epochs == 7

    def test_calculates_movement_index(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_timestamps: list[datetime],
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Calculates movement index correctly."""
        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=sample_timestamps,
            epoch_seconds=60,
        )

        # MI = nonzero_epochs / total_epochs * 100 = 7 / 10 * 100 = 70%
        assert metrics.movement_index == 70.0

    def test_handles_different_epoch_seconds(
        self,
        calculator: TudorLockeSleepMetricsCalculator,
        sample_sleep_scores: list[int],
        sample_activity_counts: list[float],
    ) -> None:
        """Handles 30-second epochs correctly."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps_30s = [base_time + timedelta(seconds=i * 30) for i in range(10)]

        metrics = calculator.calculate_metrics(
            sleep_scores=sample_sleep_scores,
            activity_counts=sample_activity_counts,
            onset_idx=0,
            offset_idx=9,
            timestamps=timestamps_30s,
            epoch_seconds=30,
        )

        # 10 epochs * 0.5 minutes = 5 minutes
        assert metrics.time_in_bed == 5.0


class TestValidateInputs:
    """Tests for _validate_inputs method."""

    def test_raises_for_empty_sleep_scores(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Raises error for empty sleep scores."""
        with pytest.raises(ValueError) as exc_info:
            calculator._validate_inputs([], [1.0, 2.0], 0, 1, [datetime.now()])

        assert "empty" in str(exc_info.value).lower()

    def test_raises_for_length_mismatch_scores_activity(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Raises error when sleep_scores and activity_counts have different lengths."""
        with pytest.raises(ValueError) as exc_info:
            calculator._validate_inputs(
                [0, 1, 1],
                [1.0, 2.0],  # Different length
                0,
                2,
                [datetime.now()] * 3,
            )

        assert "same length" in str(exc_info.value).lower()

    def test_raises_for_length_mismatch_scores_timestamps(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Raises error when sleep_scores and timestamps have different lengths."""
        with pytest.raises(ValueError) as exc_info:
            calculator._validate_inputs(
                [0, 1, 1],
                [1.0, 2.0, 3.0],
                0,
                2,
                [datetime.now()] * 2,  # Different length
            )

        assert "same length" in str(exc_info.value).lower()

    def test_raises_for_onset_out_of_range(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Raises error when onset_idx is out of range."""
        with pytest.raises(ValueError) as exc_info:
            calculator._validate_inputs(
                [0, 1, 1],
                [1.0, 2.0, 3.0],
                5,  # Out of range
                2,
                [datetime.now()] * 3,
            )

        assert "onset_idx" in str(exc_info.value).lower()

    def test_raises_for_offset_out_of_range(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Raises error when offset_idx is out of range."""
        with pytest.raises(ValueError) as exc_info:
            calculator._validate_inputs(
                [0, 1, 1],
                [1.0, 2.0, 3.0],
                0,
                5,  # Out of range
                [datetime.now()] * 3,
            )

        assert "offset_idx" in str(exc_info.value).lower()

    def test_raises_for_onset_greater_than_offset(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Raises error when onset_idx >= offset_idx."""
        with pytest.raises(ValueError) as exc_info:
            calculator._validate_inputs(
                [0, 1, 1],
                [1.0, 2.0, 3.0],
                2,  # Greater than offset
                1,
                [datetime.now()] * 3,
            )

        assert "less than" in str(exc_info.value).lower()


class TestFindFirstSleepEpoch:
    """Tests for _find_first_sleep_epoch method."""

    def test_finds_first_sleep(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Finds first epoch scored as sleep."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(5)]
        sleep_scores = [0, 0, 1, 1, 0]  # First sleep at index 2

        result = calculator._find_first_sleep_epoch(sleep_scores, timestamps)

        assert result == timestamps[2]

    def test_returns_first_if_no_sleep(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Returns first timestamp if no sleep epochs found."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(5)]
        sleep_scores = [0, 0, 0, 0, 0]  # All wake

        result = calculator._find_first_sleep_epoch(sleep_scores, timestamps)

        assert result == timestamps[0]


class TestFindLastSleepEpoch:
    """Tests for _find_last_sleep_epoch method."""

    def test_finds_last_sleep(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Finds last epoch scored as sleep."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(5)]
        sleep_scores = [0, 1, 1, 0, 0]  # Last sleep at index 2

        result = calculator._find_last_sleep_epoch(sleep_scores, timestamps)

        assert result == timestamps[2]

    def test_returns_last_if_no_sleep(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Returns last timestamp if no sleep epochs found."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(5)]
        sleep_scores = [0, 0, 0, 0, 0]  # All wake

        result = calculator._find_last_sleep_epoch(sleep_scores, timestamps)

        assert result == timestamps[-1]


class TestCountAwakenings:
    """Tests for _count_awakenings method."""

    def test_counts_single_awakening(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Counts single awakening bout."""
        sleep_scores = [1, 1, 0, 0, 1, 1]  # 1 awakening (indices 2-3)

        result = calculator._count_awakenings(sleep_scores)

        assert result == 1

    def test_counts_multiple_awakenings(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Counts multiple awakening bouts."""
        sleep_scores = [1, 0, 1, 0, 1, 0]  # 3 separate awakenings

        result = calculator._count_awakenings(sleep_scores)

        assert result == 3

    def test_counts_zero_if_all_sleep(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Returns 0 when all epochs are sleep."""
        sleep_scores = [1, 1, 1, 1, 1]

        result = calculator._count_awakenings(sleep_scores)

        assert result == 0

    def test_counts_one_if_all_wake(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Returns 1 when all epochs are wake (one continuous bout)."""
        sleep_scores = [0, 0, 0, 0, 0]

        result = calculator._count_awakenings(sleep_scores)

        assert result == 1


class TestCalculateFragmentationIndex:
    """Tests for _calculate_fragmentation_index method."""

    def test_calculates_fragmentation(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Calculates fragmentation index correctly."""
        # Pattern: [1, 0, 1, 0, 1, 1, 0, 1, 1, 1]
        # Sleep bouts: [1], [1], [1, 1], [1, 1, 1] -> lengths: 1, 1, 2, 3
        # 1-minute bouts: 2, total bouts: 4
        # FI = 2/4 * 100 = 50%
        sleep_scores = [1, 0, 1, 0, 1, 1, 0, 1, 1, 1]

        result = calculator._calculate_fragmentation_index(sleep_scores)

        assert result == 50.0

    def test_returns_zero_for_no_sleep_bouts(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Returns 0 when no sleep bouts."""
        sleep_scores = [0, 0, 0, 0, 0]

        result = calculator._calculate_fragmentation_index(sleep_scores)

        assert result == 0.0

    def test_returns_zero_for_no_one_minute_bouts(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Returns 0 when no 1-minute bouts."""
        # All bouts are > 1 minute
        sleep_scores = [1, 1, 0, 1, 1, 1, 0, 1, 1]

        result = calculator._calculate_fragmentation_index(sleep_scores)

        assert result == 0.0

    def test_returns_100_for_all_one_minute_bouts(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Returns 100 when all bouts are 1 minute."""
        # All bouts are exactly 1 epoch
        sleep_scores = [1, 0, 1, 0, 1, 0, 1]

        result = calculator._calculate_fragmentation_index(sleep_scores)

        assert result == 100.0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_handles_minimal_period(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Handles minimal 2-epoch period."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time, base_time + timedelta(minutes=1)]
        sleep_scores = [0, 1]
        activity_counts = [100.0, 10.0]

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=0,
            offset_idx=1,
            timestamps=timestamps,
            epoch_seconds=60,
        )

        assert metrics.time_in_bed == 2.0
        assert metrics.total_sleep_time == 1.0

    def test_handles_all_sleep(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Handles period with all epochs as sleep."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(5)]
        sleep_scores = [1, 1, 1, 1, 1]
        activity_counts = [0.0] * 5

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=0,
            offset_idx=4,
            timestamps=timestamps,
            epoch_seconds=60,
        )

        assert metrics.sleep_efficiency == 100.0
        assert metrics.num_awakenings == 0

    def test_handles_all_wake(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Handles period with all epochs as wake."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(5)]
        sleep_scores = [0, 0, 0, 0, 0]
        activity_counts = [100.0] * 5

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=0,
            offset_idx=4,
            timestamps=timestamps,
            epoch_seconds=60,
        )

        assert metrics.sleep_efficiency == 0.0
        assert metrics.total_sleep_time == 0.0
        assert metrics.wake_after_sleep_onset == 5.0

    def test_handles_zero_activity(self, calculator: TudorLockeSleepMetricsCalculator) -> None:
        """Handles period with all zero activity."""
        base_time = datetime(2024, 1, 15, 22, 0, 0)
        timestamps = [base_time + timedelta(minutes=i) for i in range(5)]
        sleep_scores = [1, 1, 1, 1, 1]
        activity_counts = [0.0, 0.0, 0.0, 0.0, 0.0]

        metrics = calculator.calculate_metrics(
            sleep_scores=sleep_scores,
            activity_counts=activity_counts,
            onset_idx=0,
            offset_idx=4,
            timestamps=timestamps,
            epoch_seconds=60,
        )

        assert metrics.total_activity_counts == 0.0
        assert metrics.nonzero_epochs == 0
        assert metrics.movement_index == 0.0
