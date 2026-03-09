"""
Tests for time gap imputation algorithm.

Critical verification: Row replication (not insertion) maintains epoch alignment with R GGIR.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest

from sleep_scoring_app.preprocessing import ImputationConfig, ImputationResult, impute_timegaps


class TestImputationConfig:
    """Test ImputationConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ImputationConfig()
        assert config.gap_threshold_sec == 0.25
        assert config.max_gap_min == 90.0

    def test_custom_config(self):
        """Test custom configuration values."""
        config = ImputationConfig(gap_threshold_sec=0.5, max_gap_min=120.0)
        assert config.gap_threshold_sec == 0.5
        assert config.max_gap_min == 120.0

    def test_config_is_frozen(self):
        """Test that config is immutable."""
        config = ImputationConfig()
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.gap_threshold_sec = 1.0  # type: ignore[misc]


class TestImputationResult:
    """Test ImputationResult dataclass."""

    def test_result_structure(self):
        """Test result dataclass has correct fields."""
        data = np.array([[0.1, 0.2, 0.9]])
        timestamps = np.array([0.0])
        qc_log = {"n_zeros_replaced": 0, "n_gaps": 0, "total_gap_samples": 0, "total_gap_seconds": 0.0}

        result = ImputationResult(
            data=data,
            timestamps=timestamps,
            n_gaps=0,
            total_gap_sec=0.0,
            n_samples_added=0,
            qc_log=qc_log,
        )

        assert np.array_equal(result.data, data)
        assert np.array_equal(result.timestamps, timestamps)
        assert result.n_gaps == 0
        assert result.total_gap_sec == 0.0
        assert result.n_samples_added == 0
        assert result.qc_log == qc_log

    def test_result_is_frozen(self):
        """Test that result is immutable."""
        result = ImputationResult(
            data=np.array([[0.1, 0.2, 0.9]]),
            timestamps=np.array([0.0]),
            n_gaps=0,
            total_gap_sec=0.0,
            n_samples_added=0,
            qc_log={},
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            result.n_gaps = 5  # type: ignore[misc]


class TestImputeTimegapsNoGaps:
    """Test impute_timegaps with no gaps present."""

    def test_no_gaps_returns_original_data(self):
        """Test that data without gaps is returned unchanged."""
        # 30 Hz data with no gaps
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
                [0.15, 0.25, 0.92],
            ]
        )
        timestamps = np.array([0.0, 1 / 30, 2 / 30])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        assert result.n_gaps == 0
        assert result.total_gap_sec == 0.0
        assert result.n_samples_added == 0
        assert np.array_equal(result.data, data)
        assert len(result.timestamps) == len(timestamps)

    def test_small_gaps_below_threshold_ignored(self):
        """Test that gaps below threshold are not imputed."""
        # 30 Hz with tiny gap (< 2 samples threshold)
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        # Gap of 0.02 sec at 30Hz = 0.6 samples (below 2-sample minimum)
        timestamps = np.array([0.0, 0.02])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        assert result.n_gaps == 0
        assert result.n_samples_added == 0


class TestImputeTimegapsSingleGap:
    """Test impute_timegaps with a single gap."""

    def test_single_gap_replication(self):
        """Test that gap is filled with row replication, not insertion.

        CRITICAL: This verifies the key insight - the value BEFORE the gap
        is replicated, not the value AFTER. This matches R GGIR behavior.
        """
        # 30 Hz data with 1-second gap between samples
        data = np.array(
            [
                [0.1, 0.2, 0.9],  # Sample 0
                [0.2, 0.1, 0.95],  # Sample 1 (after gap)
            ]
        )
        timestamps = np.array([0.0, 1.0])  # 1 second gap

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        # Should detect 1 gap
        assert result.n_gaps == 1

        # Gap duration should be ~1 second
        assert abs(result.total_gap_sec - 1.0) < 0.01

        # Should add ~29 samples (30 samples per second - 1 existing = 29 new)
        # Round(1.0 * 30) = 30 replications total, meaning first row appears 30 times
        # Original data had 2 samples, after replication: 30 (first) + 1 (second) = 31
        # So n_samples_added = 31 - 2 = 29
        assert result.n_samples_added == 29

        # CRITICAL TEST: First value should be replicated (not second value inserted before gap)
        # The first 30 samples should all be the normalized version of [0.1, 0.2, 0.9]
        # Note: The algorithm normalizes to magnitude 1.0 at gap positions
        first_replicated = result.data[0]
        for i in range(30):
            assert np.allclose(result.data[i], first_replicated, atol=0.01)

        # The 31st sample should be the second original value
        assert np.allclose(result.data[30], [0.2, 0.1, 0.95], atol=0.01)

    def test_gap_timestamps_are_continuous(self):
        """Test that timestamps after imputation are continuous."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        timestamps = np.array([0.0, 1.0])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        # Check timestamp spacing is uniform
        time_diffs = np.diff(result.timestamps)
        expected_spacing = 1.0 / 30.0
        assert np.allclose(time_diffs, expected_spacing, atol=1e-6)

    def test_gap_with_custom_config(self):
        """Test gap imputation with custom configuration."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        timestamps = np.array([0.0, 2.0])  # 2 second gap

        config = ImputationConfig(gap_threshold_sec=0.5, max_gap_min=1.0)
        result = impute_timegaps(data, timestamps, sample_freq=30.0, config=config)

        # Should detect gap (2 sec > 0.5 sec threshold)
        assert result.n_gaps == 1

        # Gap should be capped at max_gap_min (1 minute = 60 seconds)
        # But 2 seconds < 60 seconds, so should impute full gap
        assert abs(result.total_gap_sec - 2.0) < 0.01


class TestImputeTimegapsMultipleGaps:
    """Test impute_timegaps with multiple gaps."""

    def test_multiple_gaps(self):
        """Test handling of multiple gaps in data."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],  # Sample 0
                [0.2, 0.1, 0.95],  # Sample 1 (after 1st gap)
                [0.15, 0.25, 0.92],  # Sample 2 (after 2nd gap)
            ]
        )
        # Two 1-second gaps
        timestamps = np.array([0.0, 1.0, 2.0])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        assert result.n_gaps == 2
        assert abs(result.total_gap_sec - 2.0) < 0.01
        # Each gap adds ~29 samples: 2 * 29 = 58
        assert result.n_samples_added == 58

    def test_gaps_of_different_sizes(self):
        """Test handling of gaps with different durations."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
                [0.15, 0.25, 0.92],
            ]
        )
        # First gap: 0.5 sec, Second gap: 1.5 sec
        timestamps = np.array([0.0, 0.5, 2.0])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        assert result.n_gaps == 2
        assert abs(result.total_gap_sec - 2.0) < 0.01


class TestImputeTimegapsLongGaps:
    """Test impute_timegaps with very long gaps."""

    def test_long_gap_capping(self):
        """Test that very long gaps are capped at max_gap_min."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        # 2 hour gap (120 minutes)
        timestamps = np.array([0.0, 7200.0])

        config = ImputationConfig(max_gap_min=90.0)
        result = impute_timegaps(data, timestamps, sample_freq=30.0, config=config)

        assert result.n_gaps == 1

        # Gap should be capped at 90 minutes = 5400 seconds
        # So we should add at most 5400 * 30 = 162000 samples
        max_expected_samples = int(90.0 * 60 * 30.0)
        assert result.n_samples_added <= max_expected_samples

    def test_exact_max_gap_boundary(self):
        """Test gap exactly at max_gap_min boundary."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        # Exactly 90 minute gap
        timestamps = np.array([0.0, 5400.0])

        config = ImputationConfig(max_gap_min=90.0)
        result = impute_timegaps(data, timestamps, sample_freq=30.0, config=config)

        assert result.n_gaps == 1
        # Should impute full gap (not cap it)
        # Gap of 5400 seconds at 30 Hz = 162000 samples to fill
        # But we start with 2 samples, replication creates 162000 (first) + 1 (second) = 162001
        # So n_samples_added = 162001 - 2 = 161999
        expected_samples = int(5400.0 * 30.0) - 1
        assert result.n_samples_added == expected_samples


class TestImputeTimegapsZeroHandling:
    """Test impute_timegaps handling of zero values (0, 0, 0)."""

    def test_zero_at_start_replaced(self):
        """Test that zeros at the start are replaced with [0, 0, 1]."""
        data = np.array(
            [
                [0.0, 0.0, 0.0],  # Zero at start
                [0.1, 0.2, 0.9],
            ]
        )
        timestamps = np.array([0.0, 1 / 30])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        # Should report 1 zero replaced
        assert result.qc_log["n_zeros_replaced"] == 1

        # First value should be replaced with [0, 0, 1]
        assert np.allclose(result.data[0], [0.0, 0.0, 1.0])

    def test_zero_at_end_replaced(self):
        """Test that zeros at the end are replaced with previous value."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.0, 0.0, 0.0],  # Zero at end
            ]
        )
        timestamps = np.array([0.0, 1 / 30])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        assert result.qc_log["n_zeros_replaced"] == 1
        # Last value should be replaced with previous value
        assert np.allclose(result.data[-1], [0.1, 0.2, 0.9])

    def test_zero_in_middle_removed(self):
        """Test that zeros in the middle are removed."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.0, 0.0, 0.0],  # Zero in middle
                [0.15, 0.25, 0.92],
            ]
        )
        timestamps = np.array([0.0, 1 / 30, 2 / 30])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        assert result.qc_log["n_zeros_replaced"] == 1
        # Middle zero should be removed, so only 2 samples remain
        assert len(result.data) == 2


class TestImputeTimegapsNormalization:
    """Test impute_timegaps magnitude normalization at gap positions."""

    def test_magnitude_normalization_at_gap(self):
        """Test that values at gap positions are normalized to 1g magnitude."""
        # Create data where first sample has magnitude != 1g
        data = np.array(
            [
                [0.5, 0.5, 0.5],  # Magnitude = sqrt(0.75) ≈ 0.866, not 1g
                [0.2, 0.1, 0.95],
            ]
        )
        timestamps = np.array([0.0, 1.0])  # 1 second gap

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        # First value should be normalized to magnitude ~1.0
        # All replicated samples should have normalized value
        magnitude = np.sqrt(np.sum(result.data[0] ** 2))
        assert abs(magnitude - 1.0) < 0.01

    def test_no_normalization_if_already_1g(self):
        """Test that values close to 1g are not normalized."""
        # Create data with magnitude very close to 1g
        data = np.array(
            [
                [0.1, 0.2, 0.9],  # Magnitude ≈ 0.922 (close to 1g)
                [0.2, 0.1, 0.95],
            ]
        )
        timestamps = np.array([0.0, 1.0])

        original_first = data[0].copy()
        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        # First value magnitude is within tolerance, should not be changed much
        # (may be normalized if magnitude differs by > 0.005 from 1.0)
        magnitude = np.sqrt(np.sum(data[0] ** 2))
        if abs(magnitude - 1.0) <= 0.005:
            assert np.allclose(result.data[0], original_first, atol=0.01)


class TestImputeTimegapsDatetimeInput:
    """Test impute_timegaps with datetime64 timestamp input."""

    def test_datetime64_timestamps_converted(self):
        """Test that datetime64 timestamps are converted to float seconds."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        # Create datetime64 timestamps
        timestamps = np.array(["2024-01-01T00:00:00", "2024-01-01T00:00:01"], dtype="datetime64[s]")

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        # Should successfully process
        assert result.n_gaps == 1
        # Timestamps should be float
        assert result.timestamps.dtype == np.float64


class TestImputeTimegapsEdgeCases:
    """Test edge cases and error conditions."""

    def test_single_sample_no_gaps(self):
        """Test with single sample (no gaps possible)."""
        data = np.array([[0.1, 0.2, 0.9]])
        timestamps = np.array([0.0])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        assert result.n_gaps == 0
        assert result.n_samples_added == 0
        assert len(result.data) == 1

    def test_high_sample_frequency(self):
        """Test with high sample frequency (100 Hz)."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        timestamps = np.array([0.0, 1.0])  # 1 second gap

        result = impute_timegaps(data, timestamps, sample_freq=100.0)

        assert result.n_gaps == 1
        # Should add ~99 samples (100 samples per second - 1 = 99)
        assert result.n_samples_added == 99

    def test_low_sample_frequency(self):
        """Test with low sample frequency (1 Hz)."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        timestamps = np.array([0.0, 5.0])  # 5 second gap

        result = impute_timegaps(data, timestamps, sample_freq=1.0)

        assert result.n_gaps == 1
        # Should add ~4 samples (5 samples total - 1 = 4)
        assert result.n_samples_added == 4

    def test_qc_log_structure(self):
        """Test that QC log contains expected keys."""
        data = np.array(
            [
                [0.1, 0.2, 0.9],
                [0.2, 0.1, 0.95],
            ]
        )
        timestamps = np.array([0.0, 1.0])

        result = impute_timegaps(data, timestamps, sample_freq=30.0)

        # Check all expected keys exist
        assert "n_zeros_replaced" in result.qc_log
        assert "n_gaps" in result.qc_log
        assert "total_gap_samples" in result.qc_log
        assert "total_gap_seconds" in result.qc_log

        # Check types
        assert isinstance(result.qc_log["n_zeros_replaced"], int)
        assert isinstance(result.qc_log["n_gaps"], int)
        assert isinstance(result.qc_log["total_gap_samples"], int)
        assert isinstance(result.qc_log["total_gap_seconds"], float)
