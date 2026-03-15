"""
Cross-implementation parity tests: Python vs Rust/WASM sleep scoring algorithms.

The project implements sleep scoring algorithms in BOTH Python and Rust/WASM.
They MUST produce identical results for the same inputs.

Since we cannot call WASM from Python tests, this module:
1. Defines canonical test vectors (specific inputs + expected outputs).
2. Verifies the Python implementation matches those expected outputs.
3. Documents the test vectors so the Rust tests can use the same inputs.

Rust/WASM function mapping
--------------------------
| Python                                          | Rust (WASM export)                        |
|-------------------------------------------------|-------------------------------------------|
| SadehAlgorithm.score(activity)                  | sadeh::score(activity, threshold)         |
|   via sadeh_score(df, threshold)                |   WASM: scoreSadeh(Float64Array, f64)     |
| ColeKripkeAlgorithm.score(activity)             | cole_kripke::score(activity, use_scaling) |
|   via score_activity_cole_kripke(list, scaling) |   WASM: scoreColeKripke(Float64Array,bool)|

Rust tests using the same golden vectors live in:
  packages/sleep-scoring-wasm/crates/algorithms/src/sadeh.rs      (mod tests)
  packages/sleep-scoring-wasm/crates/algorithms/src/cole_kripke.rs (mod tests)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms.sleep_wake.sadeh import sadeh_score
from sleep_scoring_app.core.algorithms.sleep_wake.cole_kripke import (
    score_activity_cole_kripke,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sadeh_df(activity: list[float]) -> pd.DataFrame:
    """Build a minimal DataFrame that sadeh_score expects."""
    n = len(activity)
    return pd.DataFrame({
        "datetime": pd.date_range("2000-01-01", periods=n, freq="min"),
        "Axis1": np.array(activity, dtype=np.float64),
    })


def _run_sadeh(activity: list[float], threshold: float = -4.0) -> list[int]:
    """Run Python Sadeh and return list of scores."""
    df = _make_sadeh_df(activity)
    result_df = sadeh_score(df, threshold=threshold)
    return result_df["Sleep Score"].tolist()


def _run_cole_kripke(
    activity: list[float],
    use_actilife_scaling: bool = True,
) -> list[int]:
    """Run Python Cole-Kripke and return list of scores."""
    return score_activity_cole_kripke(
        activity, use_actilife_scaling=use_actilife_scaling,
    )


# ---------------------------------------------------------------------------
# CANONICAL TEST VECTORS — shared with Rust tests
# ---------------------------------------------------------------------------

# Vector 1: All zeros => all sleep
VECTOR_ALL_ZEROS = [0.0] * 20

# Vector 2: All high activity (300) => all wake (for Sadeh ActiLife)
VECTOR_ALL_HIGH = [300.0] * 20

# Vector 3: Values above 300 should be capped (same result as 300)
VECTOR_ABOVE_CAP = [500.0] * 20

# Vector 4: Alternating low/high pattern
VECTOR_ALTERNATING = [0.0, 200.0] * 10  # length 20

# Vector 5: Moderate activity that is borderline
VECTOR_MODERATE = [50.0] * 20

# Vector 6: Single epoch
VECTOR_SINGLE = [0.0]

# Vector 7: Short sequence (< window size)
VECTOR_SHORT = [0.0, 10.0, 20.0, 30.0, 40.0]

# Vector 8: Realistic sleep/wake transition pattern
VECTOR_TRANSITION = (
    [0.0] * 10  # sleep
    + [200.0] * 10  # wake
    + [0.0] * 10  # sleep again
)


# ===========================================================================
# Sadeh Algorithm Tests
# ===========================================================================


class TestSadehParity:
    """Sadeh algorithm parity tests with canonical vectors."""

    def test_empty_input(self) -> None:
        """Empty input => empty output (matches Rust: test_empty_input).

        Note: The core sadeh_score() raises ValueError on empty DataFrames,
        but the web wrapper SadehAlgorithm.score() handles empty lists
        gracefully, matching the Rust behavior.
        """
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm

        algo = SadehAlgorithm(variant="actilife")
        assert algo.score([]) == []

    def test_all_zeros_is_sleep(self) -> None:
        """All zeros => all sleep.

        Matches Rust test_all_zeros_is_sleep:
          PS = 7.601 - 0 - 0 - 0 - 0.703*ln(1) = 7.601 > -4 => sleep(1)
        """
        result = _run_sadeh(VECTOR_ALL_ZEROS, threshold=-4.0)
        assert len(result) == 20
        assert all(s == 1 for s in result), f"Expected all sleep, got {result}"

    def test_all_high_activity_is_wake(self) -> None:
        """All 300 => all wake.

        Matches Rust test_high_activity_is_wake:
          AVG=300, NATS=0, SD=0, LG=ln(301)~5.707
          PS = 7.601 - 0.065*300 - 0 - 0 - 0.703*5.707 ~ -15.91 < -4.0 => wake(0)
        """
        result = _run_sadeh(VECTOR_ALL_HIGH, threshold=-4.0)
        assert len(result) == 20
        assert all(s == 0 for s in result), f"Expected all wake, got {result}"

    def test_activity_capped_at_300(self) -> None:
        """Values > 300 treated as 300.

        Matches Rust test_activity_capped_at_300.
        """
        result_above = _run_sadeh(VECTOR_ABOVE_CAP, threshold=-4.0)
        result_at300 = _run_sadeh(VECTOR_ALL_HIGH, threshold=-4.0)
        assert result_above == result_at300, "Capping mismatch"

    def test_output_length_matches_input(self) -> None:
        """Output length always equals input length."""
        for vec in [VECTOR_ALL_ZEROS, VECTOR_SHORT, VECTOR_TRANSITION]:
            result = _run_sadeh(vec)
            assert len(result) == len(vec)

    def test_output_values_binary(self) -> None:
        """All output values are 0 or 1."""
        result = _run_sadeh(VECTOR_TRANSITION)
        assert all(v in (0, 1) for v in result)

    def test_single_epoch(self) -> None:
        """Single epoch should produce single result."""
        result = _run_sadeh(VECTOR_SINGLE)
        assert len(result) == 1
        # Single zero: PS = 7.601 - 0 - 0 - 0 - 0.703*ln(1) = 7.601 > -4 => sleep
        assert result[0] == 1

    def test_original_threshold(self) -> None:
        """Original paper threshold (0.0) is stricter than ActiLife (-4.0).

        With threshold=0.0, some epochs that are sleep at -4.0 become wake.
        For all-zeros: PS = 7.601 > 0.0 => still sleep.
        """
        result_orig = _run_sadeh(VECTOR_ALL_ZEROS, threshold=0.0)
        assert all(s == 1 for s in result_orig), "All zeros should be sleep even at threshold=0"

    def test_moderate_activity_nats_range(self) -> None:
        """Activity of 50 is in NATS range [50, 100).

        All 50s, window size 11 for fully-surrounded epochs:
          AVG=50, NATS=11, SD=0, LG=ln(51)~3.932
          PS = 7.601 - 0.065*50 - 1.08*11 - 0.056*0 - 0.703*3.932
             = 7.601 - 3.25 - 11.88 - 0 - 2.764 ~ -10.29 < -4 => wake

        Near boundaries (last epochs), zero-padding reduces NATS and AVG,
        which can push PS above the threshold. We verify the interior epochs
        are all wake.
        """
        result = _run_sadeh(VECTOR_MODERATE, threshold=-4.0)
        # Interior epochs (indices 5..14 fully surrounded by 50s) must be wake
        interior = result[5:15]
        assert all(s == 0 for s in interior), (
            f"Expected interior epochs to be wake for NATS-range activity, got {interior}"
        )

    def test_alternating_pattern(self) -> None:
        """Alternating 0/200 produces consistent-length output."""
        result = _run_sadeh(VECTOR_ALTERNATING)
        assert len(result) == 20
        assert all(v in (0, 1) for v in result)

    def test_sadeh_formula_manual_calculation(self) -> None:
        """Verify one epoch's PS against manual calculation.

        Use a carefully constructed 20-epoch input where epoch index 10
        (middle) has a known surrounding window.
        """
        # All 100s => capped at 100 (< 300)
        activity = [100.0] * 20
        df = _make_sadeh_df(activity)
        result_df = sadeh_score(df, threshold=-4.0)
        scores = result_df["Sleep Score"].tolist()

        # For middle epochs (fully windowed):
        # AVG = 100, NATS = 0 (100 is NOT in [50,100)), LG = ln(101) ~ 4.615
        # SD of 6 identical values = 0
        # PS = 7.601 - 0.065*100 - 1.08*0 - 0.056*0 - 0.703*4.615
        #    = 7.601 - 6.5 - 0 - 0 - 3.244 = -2.143
        # -2.143 > -4.0 => sleep(1)
        # Check a middle epoch
        assert scores[10] == 1, f"Expected sleep for epoch 10, PS ~ -2.14, got {scores[10]}"


# ===========================================================================
# Cole-Kripke Algorithm Tests
# ===========================================================================


class TestColeKripkeParity:
    """Cole-Kripke algorithm parity tests with canonical vectors."""

    def test_empty_input(self) -> None:
        """Empty input => empty output (matches Rust: test_empty_input)."""
        result = _run_cole_kripke([])
        assert result == []

    def test_all_zeros_is_sleep(self) -> None:
        """All zeros => all sleep.

        Matches Rust test_all_zeros_is_sleep:
          SI = 0.001 * sum(coeffs * 0) = 0 < 1.0 => sleep(1)
        """
        result = _run_cole_kripke(VECTOR_ALL_ZEROS, use_actilife_scaling=True)
        assert len(result) == 20
        assert all(s == 1 for s in result)

    def test_high_activity_is_wake_with_scaling(self) -> None:
        """High activity with ActiLife scaling => wake.

        Matches Rust test_high_activity_is_wake:
          50000/100 = 500, capped to 300
          SI = 0.001 * (106+54+58+76+230+74+67)*300 = 0.001 * 665 * 300 = 199.5 > 1.0 => wake
        """
        activity = [50000.0] * 20
        result = _run_cole_kripke(activity, use_actilife_scaling=True)
        assert all(s == 0 for s in result), f"Expected all wake, got {result}"

    def test_low_activity_with_scaling_is_sleep(self) -> None:
        """Low activity (100) with ActiLife scaling => sleep.

        Matches Rust test_actilife_scaling:
          100/100 = 1.0
          SI = 0.001 * 665 * 1 = 0.665 < 1.0 => sleep(1)
        """
        activity = [100.0] * 20
        result = _run_cole_kripke(activity, use_actilife_scaling=True)
        assert all(s == 1 for s in result), f"Expected all sleep, got {result}"

    def test_no_scaling_activity_100_is_wake(self) -> None:
        """Activity 100 without scaling => wake.

        Matches Rust test_no_scaling:
          SI = 0.001 * 665 * 100 = 66.5 > 1.0 => wake(0)
        """
        activity = [100.0] * 20
        result = _run_cole_kripke(activity, use_actilife_scaling=False)
        assert all(s == 0 for s in result), f"Expected all wake, got {result}"

    def test_output_length_matches_input(self) -> None:
        """Output length always equals input length."""
        for vec in [VECTOR_ALL_ZEROS, VECTOR_SHORT, VECTOR_TRANSITION]:
            result = _run_cole_kripke(vec)
            assert len(result) == len(vec)

    def test_output_values_binary(self) -> None:
        """All output values are 0 or 1."""
        result = _run_cole_kripke(VECTOR_TRANSITION)
        assert all(v in (0, 1) for v in result)

    def test_single_epoch(self) -> None:
        """Single zero epoch => sleep."""
        result = _run_cole_kripke([0.0])
        assert len(result) == 1
        assert result[0] == 1

    def test_alternating_pattern(self) -> None:
        """Alternating pattern produces valid output."""
        result = _run_cole_kripke(VECTOR_ALTERNATING)
        assert len(result) == 20
        assert all(v in (0, 1) for v in result)

    def test_cole_kripke_formula_manual_calculation(self) -> None:
        """Verify one epoch's SI against manual calculation.

        With ActiLife scaling, activity = [200]*20:
          Scaled: 200/100 = 2.0 (no cap needed)
          For middle epoch (full window): SI = 0.001 * (106+54+58+76+230+74+67)*2 = 0.001*665*2 = 1.33
          1.33 >= 1.0 => wake(0)
        """
        activity = [200.0] * 20
        result = _run_cole_kripke(activity, use_actilife_scaling=True)
        # Middle epochs should be wake
        assert result[10] == 0, f"Expected wake at epoch 10, got {result[10]}"


# ===========================================================================
# Cross-algorithm consistency tests
# ===========================================================================


class TestCrossAlgorithm:
    """Tests verifying consistent behavior across algorithms."""

    def test_both_agree_on_all_zeros(self) -> None:
        """Both algorithms should classify all-zeros as sleep."""
        sadeh = _run_sadeh(VECTOR_ALL_ZEROS)
        ck = _run_cole_kripke(VECTOR_ALL_ZEROS)
        assert all(s == 1 for s in sadeh)
        assert all(s == 1 for s in ck)

    def test_both_agree_on_extreme_wake(self) -> None:
        """Both algorithms should classify extreme activity as wake."""
        extreme = [50000.0] * 20
        # Sadeh caps at 300
        sadeh = _run_sadeh([300.0] * 20)
        # Cole-Kripke with ActiLife scaling: 50000/100=500 capped to 300
        ck = _run_cole_kripke(extreme, use_actilife_scaling=True)
        assert all(s == 0 for s in sadeh)
        assert all(s == 0 for s in ck)

    def test_same_output_length(self) -> None:
        """Both algorithms always produce same-length output."""
        for vec in [VECTOR_ALL_ZEROS, VECTOR_SHORT, VECTOR_TRANSITION]:
            sadeh = _run_sadeh(vec)
            ck = _run_cole_kripke(vec)
            assert len(sadeh) == len(vec)
            assert len(ck) == len(vec)


# ===========================================================================
# Web wrapper tests
# ===========================================================================


class TestWebWrappers:
    """Tests for the web app's thin algorithm wrappers."""

    def test_sadeh_web_wrapper_actilife(self) -> None:
        """Web SadehAlgorithm with actilife variant matches core."""
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm

        algo = SadehAlgorithm(variant="actilife")
        result = algo.score(VECTOR_ALL_ZEROS)
        assert all(s == 1 for s in result)

    def test_sadeh_web_wrapper_original(self) -> None:
        """Web SadehAlgorithm with original variant matches core."""
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm

        algo = SadehAlgorithm(variant="original")
        result = algo.score(VECTOR_ALL_ZEROS)
        assert all(s == 1 for s in result)

    def test_cole_kripke_web_wrapper_actilife(self) -> None:
        """Web ColeKripkeAlgorithm with actilife variant matches core."""
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant="actilife")
        result = algo.score(VECTOR_ALL_ZEROS)
        assert all(s == 1 for s in result)

    def test_cole_kripke_web_wrapper_original(self) -> None:
        """Web ColeKripkeAlgorithm with original variant matches core."""
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant="original")
        result = algo.score(VECTOR_ALL_ZEROS)
        assert all(s == 1 for s in result)

    def test_factory_creates_all_variants(self) -> None:
        """Algorithm factory creates all four algorithm variants."""
        from sleep_scoring_web.services.algorithms.factory import create_algorithm

        for algo_type in [
            "sadeh_1994_actilife",
            "sadeh_1994_original",
            "cole_kripke_1992_actilife",
            "cole_kripke_1992_original",
        ]:
            algo = create_algorithm(algo_type)
            result = algo.score(VECTOR_ALL_ZEROS)
            assert len(result) == 20
            assert all(s == 1 for s in result), f"{algo_type} failed on all-zeros"


# ===========================================================================
# Choi Nonwear Parity Tests
# ===========================================================================


# Choi canonical test vectors — shared with Rust tests in choi.rs
CHOI_VECTOR_EMPTY: list[float] = []
CHOI_VECTOR_ALL_ACTIVE = [100.0] * 200
CHOI_VECTOR_LONG_ZERO_PERIOD = [100.0] * 10 + [0.0] * 100 + [100.0] * 10
CHOI_VECTOR_SHORT_ZERO = [100.0] * 10 + [0.0] * 80 + [100.0] * 10


def _run_choi(counts: list[float]) -> list[int]:
    """Run Python Choi nonwear detection and return mask."""
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm

    algo = ChoiAlgorithm()
    return algo.detect_mask(counts)


class TestChoiParity:
    """Choi nonwear algorithm parity tests with canonical vectors.

    Rust counterparts live in:
      packages/sleep-scoring-wasm/crates/algorithms/src/choi.rs (mod tests)

    Intentional differences documented:
    - None known. Both implementations follow the same Choi 2011 algorithm
      with min_period=90, spike_tolerance=2, window_size=30.
    """

    def test_empty_input(self) -> None:
        """Empty input => empty output (matches Rust: test_empty_input)."""
        result = _run_choi(CHOI_VECTOR_EMPTY)
        assert result == []

    def test_all_active_no_nonwear(self) -> None:
        """All active => all wear (matches Rust: test_all_active_no_nonwear).

        No zero-count periods, so nothing is detected as nonwear.
        """
        result = _run_choi(CHOI_VECTOR_ALL_ACTIVE)
        assert len(result) == 200
        assert all(v == 0 for v in result), "All active should be all wear"

    def test_long_zero_period_detected(self) -> None:
        """100-minute zero period => nonwear (matches Rust: test_long_zero_period).

        100 consecutive zeros >= 90-min threshold => nonwear mask = 1.
        """
        result = _run_choi(CHOI_VECTOR_LONG_ZERO_PERIOD)
        assert len(result) == 120

        # First 10 epochs: active => wear (0)
        assert all(v == 0 for v in result[:10]), "Active prefix should be wear"
        # Middle 100 epochs: zeros => nonwear (1)
        assert all(v == 1 for v in result[10:110]), "Long zero period should be nonwear"
        # Last 10 epochs: active => wear (0)
        assert all(v == 0 for v in result[110:]), "Active suffix should be wear"

    def test_short_zero_period_not_detected(self) -> None:
        """80-minute zero period < 90-min threshold => wear (matches Rust: test_short_zero_period_not_nonwear)."""
        result = _run_choi(CHOI_VECTOR_SHORT_ZERO)
        assert len(result) == 100
        assert all(v == 0 for v in result), "Short zero period should be all wear"

    def test_output_length_matches_input(self) -> None:
        """Output mask length always equals input length."""
        for vec in [CHOI_VECTOR_ALL_ACTIVE, CHOI_VECTOR_LONG_ZERO_PERIOD, CHOI_VECTOR_SHORT_ZERO]:
            result = _run_choi(vec)
            assert len(result) == len(vec)

    def test_output_values_binary(self) -> None:
        """All output values are 0 or 1."""
        result = _run_choi(CHOI_VECTOR_LONG_ZERO_PERIOD)
        assert all(v in (0, 1) for v in result)

    def test_exactly_90_minutes_detected(self) -> None:
        """Exactly 90 zeros should be detected as nonwear (boundary case).

        Choi min_period_length = 90, so 90 consecutive zeros should qualify.
        """
        counts = [100.0] * 5 + [0.0] * 90 + [100.0] * 5
        result = _run_choi(counts)
        # The 90-zero block should be marked nonwear
        assert all(v == 1 for v in result[5:95]), "Exactly 90 zeros should be nonwear"

    def test_89_minutes_not_detected(self) -> None:
        """89 zeros < 90-min threshold => wear."""
        counts = [100.0] * 5 + [0.0] * 89 + [100.0] * 5
        result = _run_choi(counts)
        assert all(v == 0 for v in result), "89 zeros should be all wear"

    def test_spike_within_tolerance(self) -> None:
        """A small spike (1-2 non-zero epochs) within a long zero period
        should NOT break the nonwear detection.

        Choi allows up to spike_tolerance=2 non-zero epochs within the
        spike window of 30 minutes.
        """
        # 50 zeros, 1 spike, 50 zeros = 101 total (>= 90 consecutive zeros around spike)
        counts = [0.0] * 50 + [5.0] + [0.0] * 50
        result = _run_choi(counts)
        # The entire period should be detected as nonwear (spike tolerated)
        nonwear_count = sum(1 for v in result if v == 1)
        # At minimum, the 50+50 zero regions should be nonwear
        assert nonwear_count >= 90, (
            f"Expected >= 90 nonwear epochs with spike tolerance, got {nonwear_count}"
        )

    def test_multiple_nonwear_periods(self) -> None:
        """Two separate long zero periods should be detected independently."""
        counts = [100.0] * 5 + [0.0] * 95 + [100.0] * 10 + [0.0] * 95 + [100.0] * 5
        result = _run_choi(counts)
        # First nonwear block
        assert all(v == 1 for v in result[5:100]), "First nonwear block"
        # Gap (active)
        assert all(v == 0 for v in result[100:110]), "Active gap"
        # Second nonwear block
        assert all(v == 1 for v in result[110:205]), "Second nonwear block"
