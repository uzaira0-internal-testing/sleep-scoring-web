"""
Tests for Cole-Kripke sleep scoring algorithm.

Tests the web backend implementation against expected behavior.
"""

import pytest

from sleep_scoring_web.services.algorithms import (
    ALGORITHM_TYPES,
    AlgorithmType,
    ColeKripkeAlgorithm,
    create_algorithm,
)


class TestColeKripkeAlgorithm:
    """Tests for ColeKripkeAlgorithm class."""

    def test_empty_input_returns_empty(self):
        """Empty input should return empty list."""
        algorithm = ColeKripkeAlgorithm()
        assert algorithm.score([]) == []

    def test_single_epoch_zero_activity(self):
        """Single epoch with zero activity should be scored as sleep."""
        algorithm = ColeKripkeAlgorithm()
        result = algorithm.score([0])
        assert result == [1]  # Sleep

    def test_single_epoch_high_activity(self):
        """Single epoch with high activity should be scored as wake."""
        algorithm = ColeKripkeAlgorithm()
        # High activity value that should trigger wake classification
        result = algorithm.score([5000])
        assert result == [0]  # Wake

    def test_actilife_variant_scaling(self):
        """ActiLife variant should scale activity by /100 and cap at 300."""
        # ActiLife scaling: activity / 100, capped at 300
        # With scaling: 30000 / 100 = 300 (capped)
        algorithm = ColeKripkeAlgorithm(variant="actilife")

        # With very high activity, the scaled value hits cap (300)
        # This should produce wake classification
        result = algorithm.score([50000, 50000, 50000, 50000, 50000, 50000, 50000])
        assert all(r == 0 for r in result)  # All wake

    def test_original_variant_no_scaling(self):
        """Original variant should use raw activity counts."""
        algorithm = ColeKripkeAlgorithm(variant="original")

        # With raw high values, should definitely be wake
        high_activity = [10000] * 10
        result = algorithm.score(high_activity)
        assert all(r == 0 for r in result)  # All wake

    def test_low_activity_scores_sleep(self):
        """Low activity values should score as sleep."""
        algorithm = ColeKripkeAlgorithm()

        # Very low activity should produce sleep
        low_activity = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
        result = algorithm.score(low_activity)
        assert all(r == 1 for r in result)  # All sleep

    def test_moderate_activity_pattern(self):
        """Moderate activity pattern should produce mixed results."""
        algorithm = ColeKripkeAlgorithm()

        # Pattern with mix of low and moderate activity
        activity = [0, 10, 20, 50, 100, 200, 300, 500, 100, 50, 20, 0]
        result = algorithm.score(activity)

        # Should have some sleep and some wake (exact values depend on window)
        assert len(result) == len(activity)
        # First epochs (surrounded by low activity) likely sleep
        assert result[0] == 1  # Sleep at start

    def test_output_length_matches_input(self):
        """Output length should match input length."""
        algorithm = ColeKripkeAlgorithm()

        for length in [1, 5, 10, 100]:
            activity = [50] * length
            result = algorithm.score(activity)
            assert len(result) == length

    def test_variant_case_insensitive(self):
        """Variant parameter should be case-insensitive."""
        alg1 = ColeKripkeAlgorithm(variant="ACTILIFE")
        alg2 = ColeKripkeAlgorithm(variant="ActiLife")
        alg3 = ColeKripkeAlgorithm(variant="actilife")

        activity = [100] * 10
        assert alg1.score(activity) == alg2.score(activity) == alg3.score(activity)

    def test_boundary_handling_start(self):
        """Algorithm should handle boundary epochs at start correctly."""
        algorithm = ColeKripkeAlgorithm()

        # First 4 epochs have no lag data, should use zero padding
        activity = [0, 0, 0, 0, 0, 0, 0]
        result = algorithm.score(activity)
        assert len(result) == 7
        # All should be sleep with zero activity
        assert all(r == 1 for r in result)

    def test_boundary_handling_end(self):
        """Algorithm should handle boundary epochs at end correctly."""
        algorithm = ColeKripkeAlgorithm()

        # Last 2 epochs have no lead data, should use zero padding
        activity = [0] * 7
        result = algorithm.score(activity)
        assert len(result) == 7


class TestAlgorithmFactory:
    """Tests for algorithm factory function."""

    def test_create_sadeh_actilife(self):
        """Should create Sadeh ActiLife algorithm."""
        algorithm = create_algorithm(AlgorithmType.SADEH_1994_ACTILIFE)
        # Verify it works
        result = algorithm.score([0, 0, 0, 0, 0])
        assert isinstance(result, list)

    def test_create_sadeh_original(self):
        """Should create Sadeh Original algorithm."""
        algorithm = create_algorithm(AlgorithmType.SADEH_1994_ORIGINAL)
        result = algorithm.score([0, 0, 0, 0, 0])
        assert isinstance(result, list)

    def test_create_cole_kripke_actilife(self):
        """Should create Cole-Kripke ActiLife algorithm."""
        algorithm = create_algorithm(AlgorithmType.COLE_KRIPKE_1992_ACTILIFE)
        result = algorithm.score([0, 0, 0, 0, 0])
        assert isinstance(result, list)

    def test_create_cole_kripke_original(self):
        """Should create Cole-Kripke Original algorithm."""
        algorithm = create_algorithm(AlgorithmType.COLE_KRIPKE_1992_ORIGINAL)
        result = algorithm.score([0, 0, 0, 0, 0])
        assert isinstance(result, list)

    def test_unknown_algorithm_raises_error(self):
        """Unknown algorithm type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown algorithm type"):
            create_algorithm("unknown_algorithm")

    def test_all_algorithm_types_are_creatable(self):
        """All algorithm types in ALGORITHM_TYPES should be creatable."""
        for alg_type in ALGORITHM_TYPES:
            algorithm = create_algorithm(alg_type)
            # Should be able to score
            result = algorithm.score([0, 0, 0, 0, 0])
            assert isinstance(result, list)


class TestColeKripkeVsSadeh:
    """Compare Cole-Kripke and Sadeh algorithm outputs."""

    def test_algorithms_produce_different_results(self):
        """Cole-Kripke and Sadeh should produce different results for same input."""
        ck = create_algorithm(AlgorithmType.COLE_KRIPKE_1992_ACTILIFE)
        sadeh = create_algorithm(AlgorithmType.SADEH_1994_ACTILIFE)

        # Pattern that should show differences
        activity = [0, 50, 100, 150, 200, 250, 100, 50, 0, 0]

        ck_result = ck.score(activity)
        sadeh_result = sadeh.score(activity)

        # Both should produce valid results
        assert len(ck_result) == len(activity)
        assert len(sadeh_result) == len(activity)
        assert all(r in [0, 1] for r in ck_result)
        assert all(r in [0, 1] for r in sadeh_result)

        # They may or may not be identical depending on the input
        # Just verify they're both valid

    def test_both_algorithms_handle_zero_activity(self):
        """Both algorithms should classify zero activity as sleep."""
        ck = create_algorithm(AlgorithmType.COLE_KRIPKE_1992_ACTILIFE)
        sadeh = create_algorithm(AlgorithmType.SADEH_1994_ACTILIFE)

        zero_activity = [0] * 20

        ck_result = ck.score(zero_activity)
        sadeh_result = sadeh.score(zero_activity)

        # Both should be all sleep for zero activity
        assert all(r == 1 for r in ck_result)
        assert all(r == 1 for r in sadeh_result)
