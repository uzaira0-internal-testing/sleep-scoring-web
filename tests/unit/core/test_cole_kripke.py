"""
Tests for Cole-Kripke (1992) sleep scoring algorithm.

Tests the core sleep/wake classification algorithm used for accelerometer data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms.sleep_wake.cole_kripke import (
    ACTIVITY_CAP_ACTILIFE,
    ACTIVITY_SCALE_ACTILIFE,
    COEF_CURRENT,
    COEF_LAG1,
    COEF_LAG2,
    COEF_LAG3,
    COEF_LAG4,
    COEF_LEAD1,
    COEF_LEAD2,
    SCALING_FACTOR,
    THRESHOLD,
    WINDOW_SIZE,
    ColeKripkeAlgorithm,
    cole_kripke_score,
    score_activity_cole_kripke,
)
from sleep_scoring_app.core.constants import AlgorithmType
from sleep_scoring_app.core.pipeline.types import AlgorithmDataRequirement


@pytest.fixture
def sample_activity_data() -> list[float]:
    """Create sample activity data for testing."""
    return [45, 32, 0, 12, 5, 100, 200, 50, 10, 0, 0, 0, 5, 10, 15]


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """Create sample DataFrame with activity data."""
    timestamps = pd.date_range("2024-01-15 00:00:00", periods=60, freq="1min")
    activity = [50] * 20 + [0] * 20 + [100] * 20  # Wake, sleep, wake pattern
    return pd.DataFrame({"datetime": timestamps, "Axis1": activity})


class TestColeKripkeConstants:
    """Tests for Cole-Kripke algorithm constants."""

    def test_window_size(self) -> None:
        """Window size is 7 (4 lag + current + 2 lead)."""
        assert WINDOW_SIZE == 7

    def test_scaling_factor(self) -> None:
        """Scaling factor is 0.001."""
        assert SCALING_FACTOR == 0.001

    def test_threshold(self) -> None:
        """Threshold is 1.0."""
        assert THRESHOLD == 1.0

    def test_actilife_scale(self) -> None:
        """ActiLife scale factor is 100.0."""
        assert ACTIVITY_SCALE_ACTILIFE == 100.0

    def test_actilife_cap(self) -> None:
        """ActiLife activity cap is 300.0."""
        assert ACTIVITY_CAP_ACTILIFE == 300.0

    def test_coefficients(self) -> None:
        """Coefficients match published values."""
        assert COEF_LAG4 == 106
        assert COEF_LAG3 == 54
        assert COEF_LAG2 == 58
        assert COEF_LAG1 == 76
        assert COEF_CURRENT == 230
        assert COEF_LEAD1 == 74
        assert COEF_LEAD2 == 67


class TestScoreActivityColeKripke:
    """Tests for score_activity_cole_kripke function."""

    def test_returns_list(self, sample_activity_data: list[float]) -> None:
        """Returns list of integers."""
        result = score_activity_cole_kripke(sample_activity_data)

        assert isinstance(result, list)
        assert all(isinstance(x, int) for x in result)

    def test_returns_same_length(self, sample_activity_data: list[float]) -> None:
        """Returns same length as input."""
        result = score_activity_cole_kripke(sample_activity_data)

        assert len(result) == len(sample_activity_data)

    def test_returns_binary_values(self, sample_activity_data: list[float]) -> None:
        """Returns only 0 or 1 values."""
        result = score_activity_cole_kripke(sample_activity_data)

        assert all(x in (0, 1) for x in result)

    def test_empty_input_returns_empty(self) -> None:
        """Empty input returns empty list."""
        result = score_activity_cole_kripke([])

        assert result == []

    def test_raises_for_none(self) -> None:
        """Raises ValueError for None input."""
        with pytest.raises(ValueError, match="cannot be None"):
            score_activity_cole_kripke(None)

    def test_raises_for_nan(self) -> None:
        """Raises ValueError for NaN values."""
        with pytest.raises(ValueError, match="NaN"):
            score_activity_cole_kripke([1.0, np.nan, 2.0])

    def test_raises_for_infinity(self) -> None:
        """Raises ValueError for infinite values."""
        with pytest.raises(ValueError, match="infinite"):
            score_activity_cole_kripke([1.0, np.inf, 2.0])

    def test_raises_for_negative(self) -> None:
        """Raises ValueError for negative values."""
        with pytest.raises(ValueError, match="negative"):
            score_activity_cole_kripke([1.0, -5.0, 2.0])

    def test_low_activity_scores_sleep(self) -> None:
        """Low activity epochs score as sleep (1)."""
        low_activity = [0] * 20

        result = score_activity_cole_kripke(low_activity)

        # Most should be sleep (1)
        assert sum(result) > len(result) / 2

    def test_high_activity_scores_wake(self) -> None:
        """High activity epochs score as wake (0)."""
        high_activity = [500] * 20

        result = score_activity_cole_kripke(high_activity)

        # Most should be wake (0)
        assert sum(result) < len(result) / 2

    def test_actilife_scaling_default(self, sample_activity_data: list[float]) -> None:
        """ActiLife scaling is enabled by default."""
        result_default = score_activity_cole_kripke(sample_activity_data)
        result_actilife = score_activity_cole_kripke(sample_activity_data, use_actilife_scaling=True)

        assert result_default == result_actilife

    def test_original_variant(self, sample_activity_data: list[float]) -> None:
        """Original variant uses raw counts without scaling."""
        result_actilife = score_activity_cole_kripke(sample_activity_data, use_actilife_scaling=True)
        result_original = score_activity_cole_kripke(sample_activity_data, use_actilife_scaling=False)

        # Both should return valid results (may differ)
        assert len(result_actilife) == len(result_original)

    def test_count_scaling_option(self, sample_activity_data: list[float]) -> None:
        """Count scaling option can be enabled."""
        result_normal = score_activity_cole_kripke(sample_activity_data, enable_count_scaling=False)
        result_scaled = score_activity_cole_kripke(sample_activity_data, enable_count_scaling=True)

        assert len(result_normal) == len(result_scaled)

    def test_accepts_numpy_array(self) -> None:
        """Accepts numpy array input."""
        arr = np.array([50, 100, 0, 25, 10])

        result = score_activity_cole_kripke(arr)

        assert len(result) == 5


class TestColeKripkeScore:
    """Tests for cole_kripke_score DataFrame function."""

    def test_returns_dataframe(self, sample_dataframe: pd.DataFrame) -> None:
        """Returns DataFrame with score column."""
        result = cole_kripke_score(sample_dataframe)

        assert isinstance(result, pd.DataFrame)
        assert "Sleep Score" in result.columns

    def test_preserves_original_columns(self, sample_dataframe: pd.DataFrame) -> None:
        """Preserves original DataFrame columns."""
        result = cole_kripke_score(sample_dataframe)

        assert "datetime" in result.columns
        assert "Axis1" in result.columns

    def test_raises_for_empty_dataframe(self) -> None:
        """Raises ValueError for empty DataFrame."""
        with pytest.raises(ValueError, match="empty"):
            cole_kripke_score(pd.DataFrame())

    def test_raises_for_none(self) -> None:
        """Raises ValueError for None input."""
        with pytest.raises(ValueError, match="None"):
            cole_kripke_score(None)

    def test_raises_for_missing_axis1(self) -> None:
        """Raises ValueError when Axis1 column missing."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "other_column": [1] * 10,
            }
        )

        with pytest.raises(ValueError, match="Axis1"):
            cole_kripke_score(df)

    def test_finds_datetime_column(self) -> None:
        """Finds datetime column automatically."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "Axis1": [50] * 10,
            }
        )

        result = cole_kripke_score(df)

        assert "Sleep Score" in result.columns


class TestColeKripkeAlgorithmInit:
    """Tests for ColeKripkeAlgorithm initialization."""

    def test_default_variant_is_actilife(self) -> None:
        """Default variant is ActiLife."""
        algorithm = ColeKripkeAlgorithm()

        assert algorithm._variant_name == "actilife"

    def test_original_variant(self) -> None:
        """Can set original variant."""
        algorithm = ColeKripkeAlgorithm(variant_name="original")

        assert algorithm._variant_name == "original"

    def test_count_scaled_variant(self) -> None:
        """Can set count_scaled variant."""
        algorithm = ColeKripkeAlgorithm(variant_name="count_scaled")

        assert algorithm._enable_count_scaling is True


class TestColeKripkeAlgorithmProperties:
    """Tests for ColeKripkeAlgorithm properties."""

    def test_name_actilife_variant(self) -> None:
        """Name includes ActiLife for default variant."""
        algorithm = ColeKripkeAlgorithm(variant_name="actilife")

        assert "ActiLife" in algorithm.name

    def test_name_original_variant(self) -> None:
        """Name includes Original for original variant."""
        algorithm = ColeKripkeAlgorithm(variant_name="original")

        assert "Original" in algorithm.name

    def test_name_count_scaled_variant(self) -> None:
        """Name includes Count-Scaled for count_scaled variant."""
        algorithm = ColeKripkeAlgorithm(enable_count_scaling=True)

        assert "Count-Scaled" in algorithm.name

    def test_identifier_actilife(self) -> None:
        """Identifier is correct for ActiLife variant."""
        algorithm = ColeKripkeAlgorithm(variant_name="actilife")

        assert algorithm.identifier == AlgorithmType.COLE_KRIPKE_1992_ACTILIFE

    def test_identifier_original(self) -> None:
        """Identifier is correct for original variant."""
        algorithm = ColeKripkeAlgorithm(variant_name="original")

        assert algorithm.identifier == AlgorithmType.COLE_KRIPKE_1992_ORIGINAL

    def test_requires_axis_y(self) -> None:
        """Requires axis_y (vertical axis)."""
        algorithm = ColeKripkeAlgorithm()

        assert algorithm.requires_axis == "axis_y"

    def test_data_requirement_epoch(self) -> None:
        """Data requirement is EPOCH_DATA."""
        algorithm = ColeKripkeAlgorithm()

        assert algorithm.data_requirement == AlgorithmDataRequirement.EPOCH_DATA


class TestColeKripkeAlgorithmScore:
    """Tests for ColeKripkeAlgorithm scoring methods."""

    def test_score_dataframe(self, sample_dataframe: pd.DataFrame) -> None:
        """score() method works with DataFrame."""
        algorithm = ColeKripkeAlgorithm()

        result = algorithm.score(sample_dataframe)

        assert "Sleep Score" in result.columns

    def test_score_activity_function(self, sample_activity_data: list[float]) -> None:
        """score_activity_cole_kripke() module-level function works with list."""
        result = score_activity_cole_kripke(sample_activity_data)

        assert len(result) == len(sample_activity_data)


class TestColeKripkeAlgorithmParameters:
    """Tests for ColeKripkeAlgorithm parameter methods."""

    def test_get_parameters(self) -> None:
        """get_parameters() returns parameter dict."""
        algorithm = ColeKripkeAlgorithm()

        params = algorithm.get_parameters()

        assert "window_size" in params
        assert "threshold" in params
        assert "coef_current" in params
        assert params["window_size"] == WINDOW_SIZE

    def test_set_parameters_warns(self) -> None:
        """set_parameters() warns that no parameters are configurable."""
        algorithm = ColeKripkeAlgorithm()

        # Should log warning but not raise
        algorithm.set_parameters(threshold=0.5)

        # Parameters should be unchanged (Cole-Kripke has no configurable params)
        params = algorithm.get_parameters()
        assert params["threshold"] == THRESHOLD
