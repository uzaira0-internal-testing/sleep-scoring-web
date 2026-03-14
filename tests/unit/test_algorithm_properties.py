"""
Property-based tests for sleep scoring algorithms using Hypothesis.

Tests invariant properties that must hold for ANY valid input:
- Output values are always in the expected domain (0 or 1)
- Output length always matches input length
- Nonwear periods never overlap
- Factory produces valid algorithm instances for all registered types

These tests use Hypothesis to generate random activity count sequences
and verify that algorithmic invariants are preserved.
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, example, given, settings, strategies as st

from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm
from sleep_scoring_web.services.algorithms.factory import ALGORITHM_TYPES, create_algorithm
from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
from sleep_scoring_web.utils import ensure_seconds

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

# Activity counts are non-negative floats (accelerometer data).
# We avoid NaN/Inf since the algorithms explicitly reject them.
activity_count = st.floats(min_value=0.0, max_value=10_000.0, allow_nan=False, allow_infinity=False)

# Sadeh requires at least 11 epochs (uses +/-5 window around each epoch).
sadeh_counts = st.lists(activity_count, min_size=11, max_size=500)

# Cole-Kripke works with any non-empty input (7-epoch window, zero-padded).
cole_kripke_counts = st.lists(activity_count, min_size=1, max_size=500)

# Choi requires non-empty input; longer sequences needed to trigger 90-min
# nonwear detection, but the mask should be valid for any length.
choi_counts = st.lists(activity_count, min_size=1, max_size=500)


# ---------------------------------------------------------------------------
# Sadeh algorithm properties
# ---------------------------------------------------------------------------


class TestSadehProperties:
    """Property-based tests for the Sadeh 1994 sleep scoring algorithm."""

    @given(counts=sadeh_counts)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_output_is_binary(self, counts: list[float]) -> None:
        """Sadeh output must be 0 (wake) or 1 (sleep) for every epoch."""
        sadeh = SadehAlgorithm(variant="actilife")
        result = sadeh.score(counts)
        assert all(v in (0, 1) for v in result), f"Non-binary values found: {set(result) - {0, 1}}"

    @given(counts=sadeh_counts)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_output_length_equals_input_length(self, counts: list[float]) -> None:
        """Sadeh output length must equal input length."""
        sadeh = SadehAlgorithm(variant="actilife")
        result = sadeh.score(counts)
        assert len(result) == len(counts)

    @given(counts=sadeh_counts)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_original_variant_output_is_binary(self, counts: list[float]) -> None:
        """Sadeh original variant also produces only 0 or 1."""
        sadeh = SadehAlgorithm(variant="original")
        result = sadeh.score(counts)
        assert all(v in (0, 1) for v in result)
        assert len(result) == len(counts)


# ---------------------------------------------------------------------------
# Cole-Kripke algorithm properties
# ---------------------------------------------------------------------------


class TestColeKripkeProperties:
    """Property-based tests for the Cole-Kripke 1992 sleep scoring algorithm."""

    @given(counts=cole_kripke_counts)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_output_is_binary(self, counts: list[float]) -> None:
        """Cole-Kripke output must be 0 (wake) or 1 (sleep) for every epoch."""
        ck = ColeKripkeAlgorithm(variant="actilife")
        result = ck.score(counts)
        assert all(v in (0, 1) for v in result), f"Non-binary values found: {set(result) - {0, 1}}"

    @given(counts=cole_kripke_counts)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_output_length_equals_input_length(self, counts: list[float]) -> None:
        """Cole-Kripke output length must equal input length."""
        ck = ColeKripkeAlgorithm(variant="actilife")
        result = ck.score(counts)
        assert len(result) == len(counts)

    @given(counts=cole_kripke_counts)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_original_variant_output_is_binary(self, counts: list[float]) -> None:
        """Cole-Kripke original variant also produces only 0 or 1."""
        ck = ColeKripkeAlgorithm(variant="original")
        result = ck.score(counts)
        assert all(v in (0, 1) for v in result)
        assert len(result) == len(counts)


# ---------------------------------------------------------------------------
# Choi nonwear detection properties
# ---------------------------------------------------------------------------


class TestChoiProperties:
    """Property-based tests for the Choi 2011 nonwear detection algorithm."""

    @given(counts=choi_counts)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_detect_mask_is_binary(self, counts: list[float]) -> None:
        """Choi detect_mask output must be 0 (wear) or 1 (nonwear) for every epoch."""
        choi = ChoiAlgorithm()
        mask = choi.detect_mask(counts)
        assert all(v in (0, 1) for v in mask), f"Non-binary values found: {set(mask) - {0, 1}}"

    @given(counts=choi_counts)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_detect_mask_length_equals_input_length(self, counts: list[float]) -> None:
        """Choi detect_mask output length must equal input length."""
        choi = ChoiAlgorithm()
        mask = choi.detect_mask(counts)
        assert len(mask) == len(counts)

    @given(counts=choi_counts)
    @settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_detect_periods_never_overlap(self, counts: list[float]) -> None:
        """Nonwear periods from detect() must not overlap and must have start <= end."""
        choi = ChoiAlgorithm()
        periods = choi.detect(counts)

        for period in periods:
            assert period.start_index <= period.end_index, (
                f"Period has start > end: start={period.start_index}, end={period.end_index}"
            )
            assert period.start_index >= 0, f"Period start is negative: {period.start_index}"
            assert period.end_index < len(counts), (
                f"Period end ({period.end_index}) exceeds data length ({len(counts)})"
            )

        # Check no two periods overlap (they should be sorted and non-overlapping)
        for i in range(len(periods) - 1):
            current_end = periods[i].end_index
            next_start = periods[i + 1].start_index
            assert current_end < next_start, (
                f"Periods overlap: period[{i}].end={current_end} >= period[{i + 1}].start={next_start}"
            )

    @given(counts=choi_counts)
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_detect_mask_consistent_with_detect(self, counts: list[float]) -> None:
        """The mask from detect_mask must be consistent with the periods from detect."""
        choi = ChoiAlgorithm()
        mask = choi.detect_mask(counts)
        periods = choi.detect(counts)

        # Reconstruct mask from periods
        reconstructed = [0] * len(counts)
        for period in periods:
            for i in range(period.start_index, period.end_index + 1):
                reconstructed[i] = 1

        assert mask == reconstructed, "detect_mask and detect produce inconsistent results"


# ---------------------------------------------------------------------------
# All-zero input property (applies to all algorithms)
# ---------------------------------------------------------------------------


class TestAllZeroInput:
    """Test that all algorithms handle all-zero input gracefully."""

    @pytest.mark.parametrize("variant", ["actilife", "original"])
    def test_sadeh_all_zeros(self, variant: str) -> None:
        """Sadeh produces valid output for all-zero input."""
        sadeh = SadehAlgorithm(variant=variant)
        counts = [0.0] * 20
        result = sadeh.score(counts)
        assert len(result) == 20
        assert all(v in (0, 1) for v in result)

    @pytest.mark.parametrize("variant", ["actilife", "original"])
    def test_cole_kripke_all_zeros(self, variant: str) -> None:
        """Cole-Kripke produces valid output for all-zero input."""
        ck = ColeKripkeAlgorithm(variant=variant)
        counts = [0.0] * 20
        result = ck.score(counts)
        assert len(result) == 20
        assert all(v in (0, 1) for v in result)

    def test_choi_detect_mask_all_zeros(self) -> None:
        """Choi detect_mask produces valid output for all-zero input."""
        choi = ChoiAlgorithm()
        counts = [0.0] * 100
        mask = choi.detect_mask(counts)
        assert len(mask) == 100
        assert all(v in (0, 1) for v in mask)

    def test_choi_detect_all_zeros(self) -> None:
        """Choi detect produces valid nonwear periods for all-zero input."""
        choi = ChoiAlgorithm()
        counts = [0.0] * 100
        periods = choi.detect(counts)
        # All zeros for 100 epochs (100 min >= 90 min threshold) should produce
        # at least one nonwear period
        assert len(periods) >= 1
        for period in periods:
            assert period.start_index <= period.end_index


# ---------------------------------------------------------------------------
# Factory properties
# ---------------------------------------------------------------------------


class TestFactoryProperties:
    """Test that the algorithm factory produces valid algorithms for all types."""

    @pytest.mark.parametrize("algorithm_type", ALGORITHM_TYPES)
    def test_factory_creates_scoreable_algorithm(self, algorithm_type: str) -> None:
        """Every registered algorithm type can be created and scored."""
        algorithm = create_algorithm(algorithm_type)
        # Use 20 epochs (enough for both Sadeh's 11-min window and CK's 7-min)
        counts = [50.0] * 20
        result = algorithm.score(counts)
        assert len(result) == 20
        assert all(v in (0, 1) for v in result)

    @given(counts=st.lists(activity_count, min_size=11, max_size=200))
    @settings(max_examples=50, deadline=None, suppress_health_check=[HealthCheck.too_slow])
    def test_all_factory_algorithms_produce_valid_output(self, counts: list[float]) -> None:
        """All factory-created algorithms produce binary output matching input length."""
        for algorithm_type in ALGORITHM_TYPES:
            algorithm = create_algorithm(algorithm_type)
            result = algorithm.score(counts)
            assert len(result) == len(counts), (
                f"{algorithm_type}: output length {len(result)} != input length {len(counts)}"
            )
            assert all(v in (0, 1) for v in result), (
                f"{algorithm_type}: non-binary values found: {set(result) - {0, 1}}"
            )


# ---------------------------------------------------------------------------
# Timestamp normalization (ensure_seconds)
# ---------------------------------------------------------------------------


class TestTimestampNormalization:
    """Property-based tests for the ensure_seconds timestamp conversion."""

    @given(ts_seconds=st.floats(min_value=0.0, max_value=1e12, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_seconds_timestamps_pass_through(self, ts_seconds: float) -> None:
        """Timestamps <= 1e12 are treated as seconds and returned unchanged."""
        result = ensure_seconds(ts_seconds)
        assert result == ts_seconds

    @given(ts_ms=st.floats(min_value=1e12 + 1, max_value=1e16, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    @example(ts_ms=1_700_000_000_000.0)  # ~2023 in milliseconds
    @example(ts_ms=1_800_000_000_000.0)  # ~2027 in milliseconds
    def test_millisecond_timestamps_are_divided(self, ts_ms: float) -> None:
        """Timestamps > 1e12 are assumed to be milliseconds and divided by 1000."""
        result = ensure_seconds(ts_ms)
        assert result == ts_ms / 1000

    @given(ts_ms=st.floats(min_value=1e12 + 1, max_value=1e16, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_converted_result_is_in_seconds_range(self, ts_ms: float) -> None:
        """After conversion, the result should be <= 1e13 (reasonable seconds range)."""
        result = ensure_seconds(ts_ms)
        assert result <= ts_ms, "Converted timestamp should not exceed original"
        assert result == ts_ms / 1000

    def test_boundary_value_at_threshold(self) -> None:
        """Test the exact boundary at 1e12."""
        # Exactly 1e12 is treated as seconds (not milliseconds)
        assert ensure_seconds(1e12) == 1e12
        # Just above 1e12 is treated as milliseconds
        above = 1e12 + 1
        assert ensure_seconds(above) == above / 1000

    @given(ts=st.floats(min_value=0.0, max_value=1e16, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_idempotence_for_seconds_range(self, ts: float) -> None:
        """Applying ensure_seconds twice should be equivalent to applying it once,
        provided the first application brings the value into seconds range."""
        first = ensure_seconds(ts)
        second = ensure_seconds(first)
        # If the first application converted ms -> s, the result should now
        # be in seconds range and pass through unchanged on second call
        if first <= 1e12:
            assert second == first, "ensure_seconds should be idempotent for values in seconds range"
