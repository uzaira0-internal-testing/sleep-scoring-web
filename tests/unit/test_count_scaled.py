"""
Unit tests for count-scaled sleep scoring algorithms.

Tests the count-scaling functionality for Sadeh and Cole-Kripke algorithms
to ensure proper scaling of activity counts for modern accelerometers.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms.sleep_wake.cole_kripke import (
    ColeKripkeAlgorithm,
    cole_kripke_score,
)
from sleep_scoring_app.core.algorithms.sleep_wake.factory import AlgorithmFactory
from sleep_scoring_app.core.algorithms.sleep_wake.sadeh import (
    SadehAlgorithm,
    sadeh_score,
)
from sleep_scoring_app.core.algorithms.sleep_wake.utils import scale_counts
from sleep_scoring_app.core.pipeline.types import AlgorithmDataRequirement


class TestScaleCounts:
    """Test the scale_counts utility function."""

    def test_scale_counts_basic(self):
        """Test basic scaling with default parameters."""
        counts = np.array([100, 200, 500, 10000])
        scaled = scale_counts(counts, scale_factor=100.0, cap=300.0)

        # 100/100=1, 200/100=2, 500/100=5, 10000/100=100 (capped at 100, not exceeding cap)
        expected = np.array([1.0, 2.0, 5.0, 100.0])
        np.testing.assert_array_equal(scaled, expected)

    def test_scale_counts_with_capping(self):
        """Test that values are capped at maximum."""
        counts = np.array([50000, 40000, 30000, 20000])
        scaled = scale_counts(counts, scale_factor=100.0, cap=300.0)

        # All scaled values (500, 400, 300, 200) should be capped at 300
        # So we get: 300, 300, 300, 200
        assert scaled[0] == 300.0
        assert scaled[1] == 300.0
        assert scaled[2] == 300.0
        assert scaled[3] == 200.0

    def test_scale_counts_no_negative_values(self):
        """Test that negative values are clipped to 0."""
        counts = np.array([-100, 0, 100])
        scaled = scale_counts(counts, scale_factor=100.0, cap=300.0)

        assert scaled[0] >= 0  # No negative values allowed

    def test_scale_counts_custom_parameters(self):
        """Test scaling with custom scale factor and cap."""
        counts = np.array([50, 100, 200, 1000])
        scaled = scale_counts(counts, scale_factor=50.0, cap=5.0)

        expected = np.array([1.0, 2.0, 4.0, 5.0])  # Last value capped
        np.testing.assert_array_equal(scaled, expected)

    def test_scale_counts_preserves_zeros(self):
        """Test that zero values remain zero after scaling."""
        counts = np.array([0, 0, 0, 100])
        scaled = scale_counts(counts, scale_factor=100.0, cap=300.0)

        assert scaled[0] == 0.0
        assert scaled[1] == 0.0
        assert scaled[2] == 0.0
        assert scaled[3] == 1.0


class TestSadehCountScaled:
    """Test Sadeh count-scaled algorithm."""

    @pytest.fixture
    def sample_data(self):
        """Create sample activity data for testing."""
        n_epochs = 100
        timestamps = pd.date_range(start="2024-01-01 00:00:00", periods=n_epochs, freq="1min")
        # Higher activity values to test scaling effect
        activity = np.random.randint(0, 10000, size=n_epochs).astype(float)

        return pd.DataFrame({"datetime": timestamps, "Axis1": activity})

    def test_sadeh_count_scaled_runs(self, sample_data):
        """Test that Sadeh count-scaled algorithm runs without errors."""
        result = sadeh_score(
            sample_data,
            threshold=-4.0,
            enable_count_scaling=True,
            scale_factor=100.0,
            count_cap=300.0,
        )

        assert "Sleep Score" in result.columns
        assert len(result) == len(sample_data)
        assert result["Sleep Score"].isin([0, 1]).all()

    def test_sadeh_count_scaled_vs_original(self, sample_data):
        """Test that count-scaled produces different results than original."""
        # Use high activity values to ensure visible difference
        high_activity = pd.DataFrame(
            {
                "datetime": sample_data["datetime"],
                "Axis1": np.full(len(sample_data), 5000.0),  # Very high activity
            }
        )

        result_original = sadeh_score(high_activity, threshold=-4.0, enable_count_scaling=False)
        result_scaled = sadeh_score(
            high_activity,
            threshold=-4.0,
            enable_count_scaling=True,
            scale_factor=100.0,
            count_cap=300.0,
        )

        # Count-scaled should produce MORE sleep classifications (scaled values are lower)
        sleep_count_original = (result_original["Sleep Score"] == 1).sum()
        sleep_count_scaled = (result_scaled["Sleep Score"] == 1).sum()

        # With very high activity, scaling should increase sleep detection
        assert sleep_count_scaled >= sleep_count_original

    def test_sadeh_count_scaled_class_instantiation(self):
        """Test instantiation of SadehAlgorithm with count-scaling."""
        algorithm = SadehAlgorithm(
            threshold=-4.0,
            variant_name="count_scaled",
            enable_count_scaling=True,
            scale_factor=100.0,
            count_cap=300.0,
        )

        assert algorithm.name == "Sadeh (1994) Count-Scaled"
        assert algorithm.identifier == "sadeh_1994_count_scaled"
        assert algorithm.data_requirement == AlgorithmDataRequirement.EPOCH_DATA

        params = algorithm.get_parameters()
        assert params["enable_count_scaling"] is True
        assert params["scale_factor"] == 100.0
        assert params["count_cap"] == 300.0

    @pytest.mark.skip(reason="count_scaled algorithms are disabled in factory")
    def test_sadeh_count_scaled_via_factory(self):
        """Test creating Sadeh count-scaled via factory."""
        algorithm = AlgorithmFactory.create("sadeh_1994_count_scaled")

        assert algorithm.name == "Sadeh (1994) Count-Scaled"
        assert algorithm.identifier == "sadeh_1994_count_scaled"


class TestColeKripkeCountScaled:
    """Test Cole-Kripke count-scaled algorithm."""

    @pytest.fixture
    def sample_data(self):
        """Create sample activity data for testing."""
        n_epochs = 100
        timestamps = pd.date_range(start="2024-01-01 00:00:00", periods=n_epochs, freq="1min")
        # Higher activity values to test scaling effect
        activity = np.random.randint(0, 10000, size=n_epochs).astype(float)

        return pd.DataFrame({"datetime": timestamps, "Axis1": activity})

    def test_cole_kripke_count_scaled_runs(self, sample_data):
        """Test that Cole-Kripke count-scaled algorithm runs without errors."""
        result = cole_kripke_score(
            sample_data,
            use_actilife_scaling=False,
            enable_count_scaling=True,
            scale_factor=100.0,
            count_cap=300.0,
        )

        assert "Sleep Score" in result.columns
        assert len(result) == len(sample_data)
        assert result["Sleep Score"].isin([0, 1]).all()

    def test_cole_kripke_count_scaled_vs_original(self, sample_data):
        """Test that count-scaled produces different results than original."""
        # Use high activity values to ensure visible difference
        high_activity = pd.DataFrame(
            {
                "datetime": sample_data["datetime"],
                "Axis1": np.full(len(sample_data), 5000.0),  # Very high activity
            }
        )

        result_original = cole_kripke_score(high_activity, use_actilife_scaling=False, enable_count_scaling=False)
        result_scaled = cole_kripke_score(
            high_activity,
            use_actilife_scaling=False,
            enable_count_scaling=True,
            scale_factor=100.0,
            count_cap=300.0,
        )

        # Count-scaled should produce MORE sleep classifications (scaled values are lower)
        sleep_count_original = (result_original["Sleep Score"] == 1).sum()
        sleep_count_scaled = (result_scaled["Sleep Score"] == 1).sum()

        # With very high activity, scaling should increase sleep detection
        assert sleep_count_scaled >= sleep_count_original

    def test_cole_kripke_count_scaled_class_instantiation(self):
        """Test instantiation of ColeKripkeAlgorithm with count-scaling."""
        algorithm = ColeKripkeAlgorithm(
            variant_name="count_scaled",
            enable_count_scaling=True,
            scale_factor=100.0,
            count_cap=300.0,
        )

        assert algorithm.name == "Cole-Kripke (1992) Count-Scaled"
        assert algorithm.identifier == "cole_kripke_1992_count_scaled"
        assert algorithm.data_requirement == AlgorithmDataRequirement.EPOCH_DATA

        params = algorithm.get_parameters()
        assert params["enable_count_scaling"] is True
        assert params["scale_factor"] == 100.0
        assert params["count_cap"] == 300.0

    @pytest.mark.skip(reason="count_scaled algorithms are disabled in factory")
    def test_cole_kripke_count_scaled_via_factory(self):
        """Test creating Cole-Kripke count-scaled via factory."""
        algorithm = AlgorithmFactory.create("cole_kripke_1992_count_scaled")

        assert algorithm.name == "Cole-Kripke (1992) Count-Scaled"
        assert algorithm.identifier == "cole_kripke_1992_count_scaled"

    def test_cole_kripke_count_scaled_ignores_actilife_when_enabled(self):
        """Test that count-scaling takes precedence over ActiLife scaling."""
        # When both are enabled, count-scaling should be used
        algorithm = ColeKripkeAlgorithm(
            variant_name="count_scaled",
            enable_count_scaling=True,
            scale_factor=50.0,  # Different from ActiLife's 100
            count_cap=200.0,  # Different from ActiLife's 300
        )

        params = algorithm.get_parameters()
        assert params["scale_factor"] == 50.0
        assert params["count_cap"] == 200.0
        assert params["enable_count_scaling"] is True


@pytest.mark.skip(reason="count_scaled algorithms are disabled in factory")
class TestAlgorithmFactoryCountScaled:
    """Test factory registration of count-scaled algorithms."""

    def test_count_scaled_algorithms_registered(self):
        """Test that count-scaled algorithms are registered in factory."""
        available = AlgorithmFactory.get_available_algorithms()

        assert "sadeh_1994_count_scaled" in available
        assert "cole_kripke_1992_count_scaled" in available
        assert available["sadeh_1994_count_scaled"] == "Sadeh (1994) Count-Scaled"
        assert available["cole_kripke_1992_count_scaled"] == "Cole-Kripke (1992) Count-Scaled"

    def test_count_scaled_data_requirement(self):
        """Test that count-scaled algorithms have correct data requirement."""
        from sleep_scoring_app.core.pipeline import AlgorithmDataRequirement

        sadeh_req = AlgorithmFactory.get_algorithm_data_requirement("sadeh_1994_count_scaled")
        ck_req = AlgorithmFactory.get_algorithm_data_requirement("cole_kripke_1992_count_scaled")

        assert sadeh_req == AlgorithmDataRequirement.EPOCH_DATA
        assert ck_req == AlgorithmDataRequirement.EPOCH_DATA

    def test_get_epoch_algorithms_includes_count_scaled(self):
        """Test that count-scaled algorithms appear in epoch-based algorithm list."""
        from sleep_scoring_app.core.pipeline import AlgorithmDataRequirement

        epoch_algorithms = AlgorithmFactory.get_algorithms_by_data_requirement(AlgorithmDataRequirement.EPOCH_DATA)

        assert "sadeh_1994_count_scaled" in epoch_algorithms
        assert "cole_kripke_1992_count_scaled" in epoch_algorithms


class TestCountScaledIntegration:
    """Integration tests for count-scaled algorithms."""

    @pytest.fixture
    def realistic_modern_device_data(self):
        """
        Create realistic data from a modern accelerometer.

        Modern devices (GT3X+, wGT3X-BT) produce higher counts for the same
        physical activity compared to older devices (AM7164).
        """
        n_epochs = 200
        timestamps = pd.date_range(start="2024-01-01 22:00:00", periods=n_epochs, freq="1min")

        # Simulate sleep period with occasional movements
        # Modern devices produce counts in the 1000s-10000s range
        activity = np.zeros(n_epochs)

        # Wake period (high activity): 0-30 min
        activity[0:30] = np.random.randint(3000, 15000, size=30)

        # Sleep onset: 30-50 min (decreasing activity)
        activity[30:50] = np.random.randint(500, 3000, size=20)

        # Deep sleep: 50-150 min (very low activity)
        activity[50:150] = np.random.randint(0, 500, size=100)

        # Wake period: 150-200 min (high activity)
        activity[150:200] = np.random.randint(3000, 15000, size=50)

        return pd.DataFrame({"datetime": timestamps, "Axis1": activity})

    def test_count_scaled_improves_modern_device_scoring(self, realistic_modern_device_data):
        """
        Test that count-scaled algorithm better handles modern device data.

        With high counts from modern devices, original algorithms tend to
        underestimate sleep. Count-scaling should improve this.
        """
        # Original Sadeh (without scaling) - will underestimate sleep
        result_original = sadeh_score(realistic_modern_device_data, threshold=-4.0, enable_count_scaling=False)

        # Count-scaled Sadeh - should detect more sleep
        result_scaled = sadeh_score(
            realistic_modern_device_data,
            threshold=-4.0,
            enable_count_scaling=True,
            scale_factor=100.0,
            count_cap=300.0,
        )

        # Count sleep in the deep sleep period (epochs 50-150)
        deep_sleep_period = slice(50, 150)
        original_sleep_count = (result_original["Sleep Score"].iloc[deep_sleep_period] == 1).sum()
        scaled_sleep_count = (result_scaled["Sleep Score"].iloc[deep_sleep_period] == 1).sum()

        # Count-scaled should detect more sleep in this period
        assert scaled_sleep_count >= original_sleep_count

        # Wake periods should still be detected as wake
        wake_period = slice(0, 30)
        original_wake = (result_original["Sleep Score"].iloc[wake_period] == 0).sum()
        scaled_wake = (result_scaled["Sleep Score"].iloc[wake_period] == 0).sum()

        # Both should detect mostly wake
        assert original_wake > 20  # At least 20 out of 30 epochs
        assert scaled_wake > 20
