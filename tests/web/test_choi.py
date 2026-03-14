"""
Tests for Choi nonwear detection algorithm.

Tests the web backend implementation against expected behavior.
"""

import pytest

from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm


class TestChoiAlgorithm:
    """Tests for ChoiAlgorithm class."""

    def test_empty_input_returns_empty_mask(self):
        """Empty input should return empty mask."""
        algorithm = ChoiAlgorithm()
        assert algorithm.detect_mask([]) == []

    def test_short_zero_period_not_detected(self):
        """Zero periods shorter than 90 minutes should not be detected as nonwear."""
        algorithm = ChoiAlgorithm()
        # 80 minutes of zeros - below threshold
        activity = [0] * 80 + [100] * 10
        mask = algorithm.detect_mask(activity)
        # Should not be marked as nonwear (too short)
        assert sum(mask) == 0

    def test_long_zero_period_detected(self):
        """Zero periods >= 90 minutes should be detected as nonwear."""
        algorithm = ChoiAlgorithm()
        # 100 minutes of zeros - above threshold
        activity = [100] * 10 + [0] * 100 + [100] * 10
        mask = algorithm.detect_mask(activity)
        # Should have 100 nonwear epochs
        assert sum(mask) == 100
        # Verify mask positions
        assert all(m == 0 for m in mask[:10])  # Wear at start
        assert all(m == 1 for m in mask[10:110])  # Nonwear in middle
        assert all(m == 0 for m in mask[110:])  # Wear at end

    def test_small_spikes_allowed(self):
        """Small spikes (<=2 minutes) within zero period should be allowed."""
        algorithm = ChoiAlgorithm()
        # 120 minutes mostly zeros with 1 spike in middle
        activity = [0] * 50 + [50] + [0] * 69  # 120 total
        mask = algorithm.detect_mask(activity)
        # Should still detect as nonwear (spike is within tolerance)
        assert sum(mask) >= 90

    def test_large_spikes_break_period(self):
        """Large spikes (>2 minutes in window) should break nonwear period."""
        algorithm = ChoiAlgorithm()
        # Start with zeros, then activity spikes, then zeros
        # Each section too short to be nonwear
        activity = [0] * 50 + [100] * 20 + [0] * 50
        mask = algorithm.detect_mask(activity)
        # Should not detect any nonwear (both zero sections too short)
        assert sum(mask) == 0

    def test_multiple_nonwear_periods(self):
        """Should detect multiple separate nonwear periods."""
        algorithm = ChoiAlgorithm()
        # Two separate 100-minute zero periods
        activity = [0] * 100 + [100] * 20 + [0] * 100
        mask = algorithm.detect_mask(activity)
        # Should detect both periods (200 total nonwear epochs)
        assert sum(mask) == 200

    def test_adjacent_periods_merged(self):
        """Adjacent nonwear periods should be merged."""
        algorithm = ChoiAlgorithm()
        # 200 minutes of zeros (should be one merged period)
        activity = [0] * 200
        periods = algorithm.detect(activity)
        # Should be exactly one period after merging
        assert len(periods) == 1
        assert periods[0].start_index == 0
        assert periods[0].end_index == 199

    def test_detect_returns_periods(self):
        """detect() should return list of NonwearPeriod objects."""
        algorithm = ChoiAlgorithm()
        activity = [0] * 100
        periods = algorithm.detect(activity)

        assert len(periods) == 1
        period = periods[0]
        assert period.start_index == 0
        assert period.end_index == 99
        assert period.duration_minutes == 100

    def test_mask_length_matches_input(self):
        """Output mask length should match input length."""
        algorithm = ChoiAlgorithm()

        for length in [1, 50, 100, 200]:
            activity = [0] * length
            mask = algorithm.detect_mask(activity)
            assert len(mask) == length

    def test_all_activity_no_nonwear(self):
        """High activity throughout should result in no nonwear detected."""
        algorithm = ChoiAlgorithm()
        activity = [100] * 200
        mask = algorithm.detect_mask(activity)
        assert sum(mask) == 0

    def test_min_period_exactly_90(self):
        """Period of exactly 90 minutes should be detected."""
        algorithm = ChoiAlgorithm()
        activity = [100] * 10 + [0] * 90 + [100] * 10
        mask = algorithm.detect_mask(activity)
        assert sum(mask) == 90

    def test_min_period_89_not_detected(self):
        """Period of 89 minutes should not be detected."""
        algorithm = ChoiAlgorithm()
        activity = [100] * 10 + [0] * 89 + [100] * 10
        mask = algorithm.detect_mask(activity)
        assert sum(mask) == 0


class TestChoiDefaults:
    """Tests for Choi algorithm default behavior matching paper parameters."""

    def test_min_period_90_minutes(self):
        """Default min period should be 90 minutes (Choi 2011)."""
        algorithm = ChoiAlgorithm()
        # 90 zeros detected, 89 not — validates 90-min threshold
        assert sum(algorithm.detect_mask([0] * 90 + [100] * 10)) == 90
        assert sum(algorithm.detect_mask([0] * 89 + [100] * 10)) == 0


class TestChoiEdgeCases:
    """Edge case tests for Choi algorithm."""

    def test_single_epoch_zero(self):
        """Single zero epoch should not be nonwear."""
        algorithm = ChoiAlgorithm()
        mask = algorithm.detect_mask([0])
        assert mask == [0]

    def test_single_epoch_activity(self):
        """Single activity epoch should not be nonwear."""
        algorithm = ChoiAlgorithm()
        mask = algorithm.detect_mask([100])
        assert mask == [0]

    def test_all_zeros(self):
        """All zeros should be all nonwear if long enough."""
        algorithm = ChoiAlgorithm()
        activity = [0] * 150
        mask = algorithm.detect_mask(activity)
        assert all(m == 1 for m in mask)

    def test_negative_values_raise_error(self):
        """Negative values should raise ValueError (Choi 2011 expects counts >= 0)."""
        algorithm = ChoiAlgorithm()
        activity = [-50] * 100 + [50] * 100
        with pytest.raises(ValueError, match="negative values"):
            algorithm.detect_mask(activity)

    def test_float_values(self):
        """Float values should work correctly."""
        algorithm = ChoiAlgorithm()
        activity = [0.0] * 100 + [50.5] * 10
        mask = algorithm.detect_mask(activity)
        assert sum(mask) == 100
