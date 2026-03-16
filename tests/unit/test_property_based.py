"""
Property-based tests for non-algorithm modules using Hypothesis.

Covers: marker placement, complexity scoring, metrics calculation,
file identity parsing, and export CSV generation.

Each property tests an actual invariant of the system, not just
"doesn't crash" — e.g. markers never overlap, TST <= time in bed,
complexity is deterministic, etc.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import HealthCheck, assume, given, settings, strategies as st

from sleep_scoring_web.services.complexity import (
    _boundary_clarity_penalty,
    _count_activity_spikes,
    _count_sleep_runs,
    _count_transitions,
    _linear_penalty,
    _total_sleep_period_hours,
    compute_pre_complexity,
)
from sleep_scoring_web.services.export_service import (
    DEFAULT_COLUMNS,
    EXPORT_COLUMNS,
    ExportService,
)
from sleep_scoring_web.services.file_identity import (
    build_file_identity,
    filename_stem,
    infer_participant_id_and_timepoint_from_filename,
    is_excluded_activity_filename,
    normalize_filename,
    normalize_participant_id,
    normalize_timepoint,
)
from sleep_scoring_web.services.marker_placement import (
    DiaryDay,
    DiaryPeriod,
    EpochData,
    PlacementConfig,
    place_main_sleep,
    place_naps,
    place_without_diary,
)
from sleep_scoring_web.services.metrics import TudorLockeSleepMetricsCalculator

# =============================================================================
# Shared strategies
# =============================================================================

# Activity counts: non-negative integers in the realistic actigraphy range.
activity_int = st.integers(min_value=0, max_value=5000)
activity_float = st.floats(min_value=0.0, max_value=5000.0, allow_nan=False, allow_infinity=False)

# Sleep scores: binary 0/1.
sleep_score = st.integers(min_value=0, max_value=1)

# Lists of sleep scores of useful sizes.
sleep_scores_list = st.lists(sleep_score, min_size=1, max_size=500)
sleep_scores_nonempty = st.lists(sleep_score, min_size=2, max_size=500)


def _make_epochs(
    sleep_scores: list[int],
    activities: list[float] | None = None,
    base_time: datetime | None = None,
    epoch_seconds: int = 60,
) -> list[EpochData]:
    """Helper to build EpochData list from sleep scores."""
    base = base_time or datetime(2024, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
    if activities is None:
        activities = [0.0] * len(sleep_scores)
    return [
        EpochData(
            index=i,
            timestamp=base + timedelta(seconds=i * epoch_seconds),
            sleep_score=s,
            activity=activities[i] if i < len(activities) else 0.0,
            is_choi_nonwear=False,
        )
        for i, s in enumerate(sleep_scores)
    ]


def _make_timestamps(n: int, base_ts: float = 1_700_000_000.0, step: float = 60.0) -> list[float]:
    """Generate a list of n evenly-spaced Unix timestamps."""
    return [base_ts + i * step for i in range(n)]


def _make_datetime_timestamps(n: int, base: datetime | None = None, step_seconds: int = 60) -> list[datetime]:
    """Generate a list of n datetime timestamps."""
    b = base or datetime(2024, 1, 1, 22, 0, 0, tzinfo=timezone.utc)
    return [b + timedelta(seconds=i * step_seconds) for i in range(n)]


# =============================================================================
# Marker Placement Properties
# =============================================================================


class TestMarkerPlacementProperties:
    """Property-based tests for marker placement invariants."""

    @given(scores=st.lists(sleep_score, min_size=10, max_size=300))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_place_without_diary_onset_before_offset(self, scores: list[int]) -> None:
        """place_without_diary must return onset <= offset, if it returns a result."""
        epochs = _make_epochs(scores)
        config = PlacementConfig()
        result = place_without_diary(epochs, config)
        if result is not None:
            onset_idx, offset_idx = result
            assert onset_idx < offset_idx, (
                f"onset_idx ({onset_idx}) must be strictly less than offset_idx ({offset_idx})"
            )

    @given(scores=st.lists(sleep_score, min_size=10, max_size=300))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_place_without_diary_within_bounds(self, scores: list[int]) -> None:
        """Marker indices must be within the epoch array bounds."""
        epochs = _make_epochs(scores)
        config = PlacementConfig()
        result = place_without_diary(epochs, config)
        if result is not None:
            onset_idx, offset_idx = result
            assert 0 <= onset_idx < len(scores)
            assert 0 <= offset_idx < len(scores)

    @given(scores=st.lists(sleep_score, min_size=10, max_size=300))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_place_without_diary_onset_is_valid_3_consecutive(self, scores: list[int]) -> None:
        """Onset must be at the start of 3+ consecutive sleep epochs."""
        epochs = _make_epochs(scores)
        config = PlacementConfig()
        result = place_without_diary(epochs, config)
        if result is not None:
            onset_idx, _ = result
            # Check that epochs[onset_idx] starts a run of >= 3 consecutive sleep
            run_len = 0
            i = onset_idx
            while i < len(scores) and scores[i] == 1:
                run_len += 1
                i += 1
            assert run_len >= 3, (
                f"Onset at index {onset_idx} starts a run of only {run_len} sleep epochs, need >= 3"
            )

    @given(scores=st.lists(sleep_score, min_size=10, max_size=300))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_place_without_diary_offset_ends_valid_5min_run(self, scores: list[int]) -> None:
        """Offset must be at the end of a run with 5+ consecutive minutes of sleep (5 epochs at 60s)."""
        epochs = _make_epochs(scores)
        config = PlacementConfig()
        result = place_without_diary(epochs, config)
        if result is not None:
            _, offset_idx = result
            # Walk backwards from offset_idx to count consecutive sleep
            run_len = 0
            i = offset_idx
            while i >= 0 and scores[i] == 1:
                run_len += 1
                i -= 1
            min_epochs = max(1, config.offset_min_consecutive_minutes * 60 // config.epoch_length_seconds)
            assert run_len >= min_epochs, (
                f"Offset at index {offset_idx} ends a run of only {run_len} sleep epochs, need >= {min_epochs}"
            )

    @given(scores=st.lists(sleep_score, min_size=10, max_size=300))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_total_marker_time_does_not_exceed_recording(self, scores: list[int]) -> None:
        """Total time in the marker should not exceed total recording time."""
        epochs = _make_epochs(scores)
        config = PlacementConfig()
        result = place_without_diary(epochs, config)
        if result is not None:
            onset_idx, offset_idx = result
            marker_epochs = offset_idx - onset_idx + 1
            assert marker_epochs <= len(scores), (
                f"Marker spans {marker_epochs} epochs but recording only has {len(scores)}"
            )

    def test_empty_activity_produces_no_markers(self) -> None:
        """An empty epoch array should produce no markers."""
        epochs: list[EpochData] = []
        config = PlacementConfig()
        result = place_without_diary(epochs, config)
        assert result is None

    @given(scores=st.lists(st.just(0), min_size=5, max_size=100))
    @settings(max_examples=50, deadline=None)
    def test_all_wake_produces_no_markers(self, scores: list[int]) -> None:
        """All-wake input should produce no markers."""
        epochs = _make_epochs(scores)
        config = PlacementConfig()
        result = place_without_diary(epochs, config)
        assert result is None, "All-wake input should not produce any markers"

    @given(
        scores=st.lists(sleep_score, min_size=20, max_size=200),
        onset_hour=st.integers(min_value=21, max_value=23),
        wake_hour=st.integers(min_value=5, max_value=8),
    )
    @settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_place_main_sleep_onset_before_offset(
        self, scores: list[int], onset_hour: int, wake_hour: int
    ) -> None:
        """place_main_sleep must return onset < offset when it returns a result."""
        base = datetime(2024, 1, 1, 21, 0, 0, tzinfo=timezone.utc)
        epochs = _make_epochs(scores, base_time=base)
        diary = DiaryDay(
            in_bed_time=base + timedelta(hours=onset_hour - 21),
            sleep_onset=base + timedelta(hours=onset_hour - 21, minutes=15),
            wake_time=base + timedelta(hours=wake_hour - 21 + 24),
            out_bed_time=base + timedelta(hours=wake_hour - 21 + 24, minutes=15),
        )
        config = PlacementConfig()
        result = place_main_sleep(epochs, diary, config)
        if result is not None:
            onset_idx, offset_idx = result
            assert onset_idx < offset_idx

    @given(scores=st.lists(sleep_score, min_size=20, max_size=200))
    @settings(max_examples=80, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_place_naps_no_overlap(self, scores: list[int]) -> None:
        """Nap markers should not overlap each other."""
        base = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
        epochs = _make_epochs(scores, base_time=base)
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(
                    start_time=base + timedelta(hours=1),
                    end_time=base + timedelta(hours=2),
                ),
            ],
        )
        config = PlacementConfig()
        naps = place_naps(epochs, diary, None, None, config)
        # Check no overlap between any pair
        for i in range(len(naps)):
            onset_i, offset_i = naps[i]
            assert onset_i < offset_i, f"Nap {i}: onset >= offset"
            for j in range(i + 1, len(naps)):
                onset_j, offset_j = naps[j]
                # No overlap: one must end before the other starts
                assert offset_i < onset_j or offset_j < onset_i, (
                    f"Naps {i} and {j} overlap: ({onset_i},{offset_i}) vs ({onset_j},{offset_j})"
                )


# =============================================================================
# Complexity Scoring Properties
# =============================================================================


class TestComplexityProperties:
    """Property-based tests for the complexity scoring module."""

    @given(
        value=st.floats(min_value=-100.0, max_value=100.0, allow_nan=False, allow_infinity=False),
        low=st.floats(min_value=0.0, max_value=50.0, allow_nan=False, allow_infinity=False),
        high=st.floats(min_value=50.1, max_value=100.0, allow_nan=False, allow_infinity=False),
        max_penalty=st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200, deadline=None)
    def test_linear_penalty_in_range(
        self, value: float, low: float, high: float, max_penalty: float
    ) -> None:
        """_linear_penalty output is always between 0 and max_penalty."""
        result = _linear_penalty(value, low, high, max_penalty)
        assert 0.0 <= result <= max_penalty + 1e-10, (
            f"linear_penalty({value}, {low}, {high}, {max_penalty}) = {result}, out of range"
        )

    @given(scores=st.lists(sleep_score, min_size=2, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_count_transitions_non_negative(self, scores: list[int]) -> None:
        """Transition count is always non-negative."""
        count = _count_transitions(scores, 0, len(scores))
        assert count >= 0

    @given(scores=st.lists(sleep_score, min_size=2, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_count_transitions_max_bound(self, scores: list[int]) -> None:
        """Transition count is at most len(scores) - 1."""
        count = _count_transitions(scores, 0, len(scores))
        assert count <= len(scores) - 1

    @given(scores=st.lists(sleep_score, min_size=1, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_count_sleep_runs_non_negative(self, scores: list[int]) -> None:
        """Sleep run count is always non-negative."""
        runs = _count_sleep_runs(scores, 0, len(scores))
        assert runs >= 0

    @given(
        activities=st.lists(activity_float, min_size=1, max_size=200),
        threshold=st.floats(min_value=1.0, max_value=1000.0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, deadline=None)
    def test_count_activity_spikes_non_negative(self, activities: list[float], threshold: float) -> None:
        """Activity spike count is always non-negative."""
        spikes = _count_activity_spikes(activities, 0, len(activities), threshold)
        assert spikes >= 0

    @given(scores=st.lists(sleep_score, min_size=1, max_size=200))
    @settings(max_examples=100, deadline=None)
    def test_count_activity_spikes_zero_activity(self, scores: list[int]) -> None:
        """All-zero activity should produce zero spikes."""
        activities = [0.0] * len(scores)
        spikes = _count_activity_spikes(activities, 0, len(activities), threshold=50.0)
        assert spikes == 0

    @given(scores=st.lists(sleep_score, min_size=5, max_size=200))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_complexity_deterministic(self, scores: list[int]) -> None:
        """Same input always produces the same complexity score."""
        n = len(scores)
        timestamps = _make_timestamps(n)
        activities = [0.0] * n
        choi = [0] * n

        result1 = compute_pre_complexity(
            timestamps, activities, scores, choi,
            "22:00", "07:00", 0, "2024-01-01",
        )
        result2 = compute_pre_complexity(
            timestamps, activities, scores, choi,
            "22:00", "07:00", 0, "2024-01-01",
        )
        assert result1[0] == result2[0], "Complexity must be deterministic"

    @given(scores=st.lists(sleep_score, min_size=5, max_size=200))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_complexity_score_in_valid_range(self, scores: list[int]) -> None:
        """Complexity score must be -1 (infinite) or in [0, 100]."""
        n = len(scores)
        timestamps = _make_timestamps(n)
        activities = [0.0] * n
        choi = [0] * n

        score, _ = compute_pre_complexity(
            timestamps, activities, scores, choi,
            "22:00", "07:00", 0, "2024-01-01",
        )
        assert score == -1 or (0 <= score <= 100), f"Score {score} out of valid range"

    def test_complexity_all_zero_activity_deterministic(self) -> None:
        """All-zero activity with diary produces a deterministic score."""
        n = 100
        scores = [1] * n
        timestamps = _make_timestamps(n, base_ts=1_700_000_000.0)
        activities = [0.0] * n
        choi = [0] * n

        s1, f1 = compute_pre_complexity(
            timestamps, activities, scores, choi,
            "22:00", "07:00", 0, "2024-01-01",
        )
        s2, f2 = compute_pre_complexity(
            timestamps, activities, scores, choi,
            "22:00", "07:00", 0, "2024-01-01",
        )
        assert s1 == s2
        assert f1 == f2

    @given(scores=st.lists(sleep_score, min_size=5, max_size=200))
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_complexity_no_diary_returns_minus_one(self, scores: list[int]) -> None:
        """Missing diary (None onset or wake) should return -1."""
        n = len(scores)
        timestamps = _make_timestamps(n)
        activities = [0.0] * n
        choi = [0] * n

        score, _ = compute_pre_complexity(
            timestamps, activities, scores, choi,
            None, None, 0, "2024-01-01",
        )
        assert score == -1, "No diary should produce -1 (infinite complexity)"

    @given(scores=st.lists(sleep_score, min_size=5, max_size=200))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_complexity_partial_diary_returns_minus_one(self, scores: list[int]) -> None:
        """Partial diary (only onset or only wake) should return -1."""
        n = len(scores)
        timestamps = _make_timestamps(n)
        activities = [0.0] * n
        choi = [0] * n

        score1, _ = compute_pre_complexity(
            timestamps, activities, scores, choi,
            "22:00", None, 0, "2024-01-01",
        )
        score2, _ = compute_pre_complexity(
            timestamps, activities, scores, choi,
            None, "07:00", 0, "2024-01-01",
        )
        assert score1 == -1
        assert score2 == -1

    def test_complexity_empty_data_returns_zero(self) -> None:
        """Empty timestamps/scores should return 0."""
        score, features = compute_pre_complexity(
            [], [], [], [], "22:00", "07:00", 0, "2024-01-01",
        )
        assert score == 0
        assert "error" in features

    @given(scores=st.lists(sleep_score, min_size=10, max_size=200))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_boundary_clarity_penalty_in_range(self, scores: list[int]) -> None:
        """Boundary clarity penalty is between -10 and 0."""
        activities = [0.0] * len(scores)
        penalty = _boundary_clarity_penalty(activities, scores, 0, len(scores))
        assert -10.0 <= penalty <= 0.0, f"Penalty {penalty} out of range [-10, 0]"

    @given(n=st.integers(min_value=10, max_value=200))
    @settings(max_examples=50, deadline=None)
    def test_total_sleep_period_hours_non_negative(self, n: int) -> None:
        """Total sleep period hours is always non-negative."""
        scores = [1] * n
        timestamps = _make_timestamps(n)
        hours = _total_sleep_period_hours(scores, timestamps, 0, n)
        assert hours >= 0.0


# =============================================================================
# Metrics Properties
# =============================================================================


class TestMetricsProperties:
    """Property-based tests for Tudor-Locke sleep metrics."""

    @given(
        data=st.data(),
        n=st.integers(min_value=10, max_value=300),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_tst_leq_time_in_bed(self, data: st.DataObject, n: int) -> None:
        """Total Sleep Time must be <= Time in Bed."""
        scores = data.draw(st.lists(sleep_score, min_size=n, max_size=n))
        activities = data.draw(
            st.lists(activity_float, min_size=n, max_size=n)
        )
        timestamps = _make_datetime_timestamps(n)
        onset = data.draw(st.integers(min_value=0, max_value=n - 3))
        offset = data.draw(st.integers(min_value=onset + 2, max_value=n - 1))

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, onset, offset, timestamps)

        assert metrics["total_sleep_time_minutes"] <= metrics["time_in_bed_minutes"] + 0.01, (
            f"TST ({metrics['total_sleep_time_minutes']}) > TIB ({metrics['time_in_bed_minutes']})"
        )

    @given(
        data=st.data(),
        n=st.integers(min_value=10, max_value=300),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_sleep_efficiency_in_range(self, data: st.DataObject, n: int) -> None:
        """Sleep efficiency must be between 0% and 100%."""
        scores = data.draw(st.lists(sleep_score, min_size=n, max_size=n))
        activities = data.draw(st.lists(activity_float, min_size=n, max_size=n))
        timestamps = _make_datetime_timestamps(n)
        onset = data.draw(st.integers(min_value=0, max_value=n - 3))
        offset = data.draw(st.integers(min_value=onset + 2, max_value=n - 1))

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, onset, offset, timestamps)

        assert 0.0 <= metrics["sleep_efficiency"] <= 100.0 + 0.01, (
            f"Sleep efficiency {metrics['sleep_efficiency']}% out of range"
        )

    @given(
        data=st.data(),
        n=st.integers(min_value=10, max_value=300),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_waso_non_negative(self, data: st.DataObject, n: int) -> None:
        """WASO must be >= 0."""
        scores = data.draw(st.lists(sleep_score, min_size=n, max_size=n))
        activities = data.draw(st.lists(activity_float, min_size=n, max_size=n))
        timestamps = _make_datetime_timestamps(n)
        onset = data.draw(st.integers(min_value=0, max_value=n - 3))
        offset = data.draw(st.integers(min_value=onset + 2, max_value=n - 1))

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, onset, offset, timestamps)

        assert metrics["waso_minutes"] >= -0.01, f"WASO is negative: {metrics['waso_minutes']}"

    @given(
        data=st.data(),
        n=st.integers(min_value=10, max_value=300),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_sol_non_negative(self, data: st.DataObject, n: int) -> None:
        """Sleep onset latency must be >= 0."""
        scores = data.draw(st.lists(sleep_score, min_size=n, max_size=n))
        activities = data.draw(st.lists(activity_float, min_size=n, max_size=n))
        timestamps = _make_datetime_timestamps(n)
        onset = data.draw(st.integers(min_value=0, max_value=n - 3))
        offset = data.draw(st.integers(min_value=onset + 2, max_value=n - 1))

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, onset, offset, timestamps)

        assert metrics["sleep_onset_latency_minutes"] >= 0.0, (
            f"SOL is negative: {metrics['sleep_onset_latency_minutes']}"
        )

    @given(
        data=st.data(),
        n=st.integers(min_value=10, max_value=300),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_num_awakenings_non_negative(self, data: st.DataObject, n: int) -> None:
        """Number of awakenings must be >= 0."""
        scores = data.draw(st.lists(sleep_score, min_size=n, max_size=n))
        activities = data.draw(st.lists(activity_float, min_size=n, max_size=n))
        timestamps = _make_datetime_timestamps(n)
        onset = data.draw(st.integers(min_value=0, max_value=n - 3))
        offset = data.draw(st.integers(min_value=onset + 2, max_value=n - 1))

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, onset, offset, timestamps)

        assert metrics["number_of_awakenings"] >= 0

    @given(
        data=st.data(),
        n=st.integers(min_value=10, max_value=300),
    )
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_tst_plus_waso_plus_sol_leq_tib(self, data: st.DataObject, n: int) -> None:
        """TST + WASO + SOL must be <= Time in Bed (they partition it)."""
        scores = data.draw(st.lists(sleep_score, min_size=n, max_size=n))
        activities = data.draw(st.lists(activity_float, min_size=n, max_size=n))
        timestamps = _make_datetime_timestamps(n)
        onset = data.draw(st.integers(min_value=0, max_value=n - 3))
        offset = data.draw(st.integers(min_value=onset + 2, max_value=n - 1))

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, onset, offset, timestamps)

        total = (
            metrics["total_sleep_time_minutes"]
            + metrics["waso_minutes"]
            + metrics["sleep_onset_latency_minutes"]
        )
        tib = metrics["time_in_bed_minutes"]
        assert total <= tib + 0.01, (
            f"TST({metrics['total_sleep_time_minutes']}) + WASO({metrics['waso_minutes']}) "
            f"+ SOL({metrics['sleep_onset_latency_minutes']}) = {total} > TIB({tib})"
        )

    @given(
        data=st.data(),
        n=st.integers(min_value=10, max_value=300),
    )
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_fragmentation_index_in_range(self, data: st.DataObject, n: int) -> None:
        """Fragmentation index must be between 0 and 100."""
        scores = data.draw(st.lists(sleep_score, min_size=n, max_size=n))
        activities = data.draw(st.lists(activity_float, min_size=n, max_size=n))
        timestamps = _make_datetime_timestamps(n)
        onset = data.draw(st.integers(min_value=0, max_value=n - 3))
        offset = data.draw(st.integers(min_value=onset + 2, max_value=n - 1))

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, onset, offset, timestamps)

        assert 0.0 <= metrics["fragmentation_index"] <= 100.0
        assert 0.0 <= metrics["movement_index"] <= 100.0

    def test_all_sleep_tst_equals_tib(self) -> None:
        """When all scores are sleep, TST should equal TIB."""
        n = 20
        scores = [1] * n
        activities = [0.0] * n
        timestamps = _make_datetime_timestamps(n)

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, 0, n - 1, timestamps)

        assert abs(metrics["total_sleep_time_minutes"] - metrics["time_in_bed_minutes"]) < 0.01
        assert metrics["waso_minutes"] < 0.01
        assert metrics["sleep_onset_latency_minutes"] < 0.01
        assert abs(metrics["sleep_efficiency"] - 100.0) < 0.01

    def test_all_wake_tst_is_zero(self) -> None:
        """When all scores are wake, TST should be 0."""
        n = 20
        scores = [0] * n
        activities = [100.0] * n
        timestamps = _make_datetime_timestamps(n)

        calc = TudorLockeSleepMetricsCalculator()
        metrics = calc.calculate_metrics(scores, activities, 0, n - 1, timestamps)

        assert metrics["total_sleep_time_minutes"] < 0.01
        assert abs(metrics["sleep_efficiency"]) < 0.01


# =============================================================================
# File Identity Properties
# =============================================================================


class TestFileIdentityProperties:
    """Property-based tests for file identity parsing."""

    @given(filename=st.text(min_size=0, max_size=200))
    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_infer_always_returns_tuple(self, filename: str) -> None:
        """infer_participant_id_and_timepoint_from_filename always returns a tuple of (str|None, str|None)."""
        result = infer_participant_id_and_timepoint_from_filename(filename)
        assert isinstance(result, tuple)
        assert len(result) == 2
        pid, tp = result
        assert pid is None or isinstance(pid, str)
        assert tp is None or isinstance(tp, str)

    @given(filename=st.text(min_size=0, max_size=200))
    @settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_random_strings_dont_crash_parser(self, filename: str) -> None:
        """Random strings must not crash any file identity function."""
        # None of these should raise
        infer_participant_id_and_timepoint_from_filename(filename)
        normalize_filename(filename)
        filename_stem(filename)
        normalize_participant_id(filename)
        normalize_timepoint(filename)
        is_excluded_activity_filename(filename)

    @pytest.mark.parametrize(
        "filename, expected_pid, expected_tp",
        [
            ("1000 T1 G1 (2024-01-01)60sec.csv", "1000", "T1"),
            ("P1-1036-A-T2 (2023-07-18)60sec.csv", "P1-1036-A", "T2"),
            ("DEMO-001.csv", "DEMO-001", None),
            ("", None, None),
            ("   ", None, None),
        ],
    )
    def test_known_patterns_extract_correctly(
        self, filename: str, expected_pid: str | None, expected_tp: str | None
    ) -> None:
        """Known filename patterns should extract the expected pid and timepoint."""
        pid, tp = infer_participant_id_and_timepoint_from_filename(filename)
        assert pid == expected_pid, f"For '{filename}': expected pid={expected_pid}, got {pid}"
        assert tp == expected_tp, f"For '{filename}': expected tp={expected_tp}, got {tp}"

    @given(filename=st.from_regex(r"[a-z]{3,10}\.(txt|dat|bin)", fullmatch=True))
    @settings(max_examples=100, deadline=None)
    def test_no_timepoint_pattern_returns_none_tp(self, filename: str) -> None:
        """Filenames without a Tn pattern should return None for timepoint."""
        _, tp = infer_participant_id_and_timepoint_from_filename(filename)
        assert tp is None, f"'{filename}' unexpectedly matched timepoint: {tp}"

    @given(value=st.text(min_size=0, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_normalize_participant_id_returns_none_or_string(self, value: str) -> None:
        """normalize_participant_id returns None or a lowercase string."""
        result = normalize_participant_id(value)
        if result is not None:
            assert isinstance(result, str)
            assert result == result.lower()

    @given(value=st.text(min_size=0, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_normalize_timepoint_returns_none_or_string(self, value: str) -> None:
        """normalize_timepoint returns None or a string."""
        result = normalize_timepoint(value)
        if result is not None:
            assert isinstance(result, str)

    @pytest.mark.parametrize(
        "pid_input, expected",
        [
            ("1001", "1001"),
            ("1001.0", "1001"),
            ("  HELLO  ", "hello"),
            ("nan", None),
            ("none", None),
            ("", None),
            (None, None),
        ],
    )
    def test_normalize_participant_id_known_values(
        self, pid_input: Any, expected: str | None
    ) -> None:
        """Known participant ID patterns normalize correctly."""
        assert normalize_participant_id(pid_input) == expected

    @pytest.mark.parametrize(
        "tp_input, expected",
        [
            ("T1", "t1"),
            ("t1", "t1"),
            ("T 1", "t1"),
            ("T12", "t12"),
            ("nan", None),
            (None, None),
        ],
    )
    def test_normalize_timepoint_known_values(self, tp_input: Any, expected: str | None) -> None:
        """Known timepoint patterns normalize correctly."""
        assert normalize_timepoint(tp_input) == expected

    @given(filename=st.text(min_size=1, max_size=100))
    @settings(max_examples=100, deadline=None)
    def test_is_excluded_returns_bool(self, filename: str) -> None:
        """is_excluded_activity_filename always returns a bool."""
        result = is_excluded_activity_filename(filename)
        assert isinstance(result, bool)

    @pytest.mark.parametrize("filename", ["data_IGNORE_v2.csv", "file_issue_01.csv", "ISSUE.csv"])
    def test_excluded_filenames_detected(self, filename: str) -> None:
        """Filenames containing IGNORE or ISSUE should be excluded."""
        assert is_excluded_activity_filename(filename) is True

    @pytest.mark.parametrize("filename", ["normal_data.csv", "participant_001.csv"])
    def test_normal_filenames_not_excluded(self, filename: str) -> None:
        """Normal filenames should not be excluded."""
        assert is_excluded_activity_filename(filename) is False


# =============================================================================
# Export CSV Properties
# =============================================================================


class TestExportCsvProperties:
    """Property-based tests for the CSV export generation logic.

    Tests the static/pure parts of ExportService (column definitions,
    CSV generation, sanitization) without needing a database.
    """

    def test_export_csv_always_has_header(self) -> None:
        """Generated CSV with include_header=True always has a header row."""
        rows = [
            {"Filename": "test.csv", "File ID": 1, "Study Date": "2024-01-01"},
        ]
        # Use the _generate_csv method directly — it's a bound method but
        # we can call it on an instance with a mock db.
        service = ExportService.__new__(ExportService)
        csv_output = service._generate_csv(rows, ["Filename", "File ID", "Study Date"], include_header=True)
        lines = csv_output.strip().split("\n")
        assert len(lines) >= 2, "CSV should have at least header + 1 data row"
        header = lines[0]
        assert "Filename" in header

    def test_export_csv_row_count_matches_input(self) -> None:
        """Number of data rows in CSV matches the number of input dicts."""
        n_rows = 5
        rows = [
            {"Filename": f"file_{i}.csv", "File ID": i, "Study Date": "2024-01-01"}
            for i in range(n_rows)
        ]
        service = ExportService.__new__(ExportService)
        csv_output = service._generate_csv(rows, ["Filename", "File ID", "Study Date"], include_header=True)
        reader = csv.reader(io.StringIO(csv_output))
        all_lines = list(reader)
        # First line is header, rest are data
        assert len(all_lines) == n_rows + 1, f"Expected {n_rows + 1} lines (header + data), got {len(all_lines)}"

    @given(n_rows=st.integers(min_value=0, max_value=50))
    @settings(max_examples=50, deadline=None)
    def test_export_csv_row_count_property(self, n_rows: int) -> None:
        """For any number of input rows, CSV data rows match."""
        rows = [
            {"Filename": f"f_{i}.csv", "File ID": i, "Study Date": "2024-01-01"}
            for i in range(n_rows)
        ]
        service = ExportService.__new__(ExportService)
        csv_output = service._generate_csv(
            rows, ["Filename", "File ID", "Study Date"], include_header=True
        )
        reader = csv.reader(io.StringIO(csv_output))
        all_lines = list(reader)
        # Header + n_rows data rows
        expected = n_rows + 1  # +1 for header
        assert len(all_lines) == expected

    def test_all_requested_columns_appear_in_header(self) -> None:
        """All requested columns must appear in the CSV header."""
        columns = ["Filename", "Study Date", "Sleep Efficiency (%)", "WASO (min)"]
        rows = [
            {"Filename": "test.csv", "Study Date": "2024-01-01", "Sleep Efficiency (%)": "85.5", "WASO (min)": "30"},
        ]
        service = ExportService.__new__(ExportService)
        csv_output = service._generate_csv(rows, columns, include_header=True)
        reader = csv.reader(io.StringIO(csv_output))
        header = next(reader)
        for col in columns:
            assert col in header, f"Column '{col}' missing from header: {header}"

    def test_no_header_mode(self) -> None:
        """With include_header=False, CSV should have no header row."""
        rows = [{"Filename": "test.csv", "File ID": 1}]
        service = ExportService.__new__(ExportService)
        csv_output = service._generate_csv(rows, ["Filename", "File ID"], include_header=False)
        reader = csv.reader(io.StringIO(csv_output))
        all_lines = list(reader)
        assert len(all_lines) == 1, "No-header mode should have exactly 1 data row"
        # The row should NOT contain column names as data
        assert all_lines[0][0] != "Filename"

    def test_metadata_mode_has_comment_lines(self) -> None:
        """With include_metadata=True, CSV should start with # comment lines."""
        rows = [{"Filename": "test.csv"}]
        service = ExportService.__new__(ExportService)
        csv_output = service._generate_csv(rows, ["Filename"], include_header=True, include_metadata=True)
        lines = csv_output.split("\n")
        comment_lines = [l for l in lines if l.startswith("#")]
        assert len(comment_lines) >= 1, "Metadata mode should include comment lines"

    @pytest.mark.parametrize(
        "value, expected_sanitized",
        [
            ("=cmd()", "'=cmd()"),
            ("+cmd()", "'+cmd()"),
            ("@cmd()", "'@cmd()"),
            ("normal text", "normal text"),
            ("", ""),
            (42, 42),
        ],
    )
    def test_csv_injection_sanitization(self, value: Any, expected_sanitized: Any) -> None:
        """CSV values starting with =, +, @, etc. should be sanitized."""
        result = ExportService._sanitize_csv_value(value)
        assert result == expected_sanitized

    def test_default_columns_nonempty(self) -> None:
        """Default columns list must not be empty."""
        assert len(DEFAULT_COLUMNS) > 0

    def test_all_export_columns_have_names(self) -> None:
        """Every export column definition must have a non-empty name."""
        for col in EXPORT_COLUMNS:
            assert col.name, f"Column with empty name found: {col}"
            assert col.category, f"Column '{col.name}' has empty category"

    @given(
        columns=st.lists(
            st.sampled_from([c.name for c in EXPORT_COLUMNS]),
            min_size=1,
            max_size=10,
            unique=True,
        )
    )
    @settings(max_examples=50, deadline=None)
    def test_generate_csv_with_random_column_subset(self, columns: list[str]) -> None:
        """CSV generation works with any valid subset of columns."""
        rows = [
            {c: f"val_{i}" for c in columns}
            for i in range(3)
        ]
        service = ExportService.__new__(ExportService)
        csv_output = service._generate_csv(rows, columns, include_header=True)
        reader = csv.reader(io.StringIO(csv_output))
        header = next(reader)
        assert header == columns
        data_rows = list(reader)
        assert len(data_rows) == 3

    def test_format_number_properties(self) -> None:
        """_format_number handles None, int, and float correctly."""
        assert ExportService._format_number(None) == ""
        assert ExportService._format_number(42) == "42"
        assert ExportService._format_number(3.14159) == "3.14"
        assert ExportService._format_number(3.14159, precision=4) == "3.1416"
