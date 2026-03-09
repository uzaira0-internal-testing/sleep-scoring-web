"""
Tests for Sadeh (1994) sleep scoring algorithm.

Tests the core sleep/wake classification algorithm used for accelerometer data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms.sleep_wake.sadeh import (
    ACTIVITY_CAP,
    COEFFICIENT_A,
    COEFFICIENT_B,
    COEFFICIENT_C,
    COEFFICIENT_D,
    COEFFICIENT_E,
    NATS_MAX,
    NATS_MIN,
    WINDOW_SIZE,
    SadehAlgorithm,
    sadeh_score,
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


class TestSadehConstants:
    """Tests for Sadeh algorithm constants."""

    def test_window_size(self) -> None:
        """Window size is 11 minutes."""
        assert WINDOW_SIZE == 11

    def test_activity_cap(self) -> None:
        """Activity cap is 300."""
        assert ACTIVITY_CAP == 300

    def test_nats_range(self) -> None:
        """NATS range is 50-100."""
        assert NATS_MIN == 50
        assert NATS_MAX == 100

    def test_coefficients(self) -> None:
        """Coefficients match published values."""
        assert COEFFICIENT_A == 7.601
        assert COEFFICIENT_B == 0.065
        assert COEFFICIENT_C == 1.08
        assert COEFFICIENT_D == 0.056
        assert COEFFICIENT_E == 0.703


class TestSadehScore:
    """Tests for sadeh_score DataFrame function."""

    def test_returns_dataframe(self, sample_dataframe: pd.DataFrame) -> None:
        """Returns DataFrame with score column."""
        result = sadeh_score(sample_dataframe)

        assert isinstance(result, pd.DataFrame)
        assert "Sleep Score" in result.columns

    def test_preserves_original_columns(self, sample_dataframe: pd.DataFrame) -> None:
        """Preserves original DataFrame columns."""
        result = sadeh_score(sample_dataframe)

        assert "datetime" in result.columns
        assert "Axis1" in result.columns

    def test_raises_for_empty_dataframe(self) -> None:
        """Raises ValueError for empty DataFrame."""
        with pytest.raises(ValueError, match="empty"):
            sadeh_score(pd.DataFrame())

    def test_raises_for_none(self) -> None:
        """Raises ValueError for None input."""
        with pytest.raises(ValueError, match="None"):
            sadeh_score(None)

    def test_raises_for_missing_axis1(self) -> None:
        """Raises ValueError when Axis1 column missing."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "other_column": [1] * 10,
            }
        )

        with pytest.raises(ValueError, match="Axis1"):
            sadeh_score(df)

    def test_finds_datetime_column(self) -> None:
        """Finds datetime column automatically."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "Axis1": [50] * 10,
            }
        )

        result = sadeh_score(df)

        assert "Sleep Score" in result.columns

    def test_raises_for_nan_values(self) -> None:
        """Raises ValueError for NaN values in Axis1."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=3, freq="1min"),
                "Axis1": [1.0, np.nan, 2.0],
            }
        )

        with pytest.raises(ValueError, match="NaN"):
            sadeh_score(df)

    def test_raises_for_negative_values(self) -> None:
        """Raises ValueError for negative values in Axis1."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=3, freq="1min"),
                "Axis1": [1.0, -5.0, 2.0],
            }
        )

        with pytest.raises(ValueError, match="negative"):
            sadeh_score(df)

    def test_low_activity_scores_sleep(self) -> None:
        """All-zero activity scores as sleep (PS = 7.601 > -4.0 threshold)."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=20, freq="1min"),
                "Axis1": [0] * 20,
            }
        )

        result = sadeh_score(df)
        scores = result["Sleep Score"].tolist()

        assert scores == [1] * 20, f"Expected all 1s for zero activity, got {scores}"

    def test_high_activity_scores_wake(self) -> None:
        """High activity (500, capped to 300) scores as wake (PS = -15.91 < -4.0)."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=20, freq="1min"),
                "Axis1": [500] * 20,
            }
        )

        result = sadeh_score(df)
        scores = result["Sleep Score"].tolist()

        assert scores == [0] * 20, f"Expected all 0s for high activity, got {scores}"

    def test_moderate_activity_threshold_boundary(self) -> None:
        """Activity of 50 (in NATS range) heavily penalized, scores as wake."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=25, freq="1min"),
                "Axis1": [50] * 25,
            }
        )

        result = sadeh_score(df)
        scores = result["Sleep Score"].tolist()

        wake_count = scores.count(0)
        assert wake_count >= 20, f"Expected at least 20 wake epochs, got {wake_count}"

    def test_mixed_pattern_known_output(self) -> None:
        """Transition from zeros to high activity produces sleep→wake pattern.

        With forward-looking SD window (per Sadeh paper), epoch 2's 6-epoch
        window [i..i+5] spans the 0→300 transition, producing high SD that
        pushes PS below threshold. So the transition from sleep→wake happens
        earlier than it would with a backward-looking window.
        """
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=12, freq="1min"),
                "Axis1": [0] * 6 + [300] * 6,
            }
        )

        result = sadeh_score(df)
        scores = result["Sleep Score"].tolist()

        # First 2 epochs: SD window is entirely in zero region → sleep
        assert scores[:2] == [1, 1], f"First 2 should be sleep, got {scores[:2]}"
        assert scores[-3:] == [0, 0, 0], f"Last 3 should be wake, got {scores[-3:]}"

    def test_original_threshold_vs_actilife_threshold(self) -> None:
        """ActiLife (-4.0) and original (0.0) thresholds produce different results for borderline PS."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=25, freq="1min"),
                "Axis1": [100] * 25,
            }
        )

        result_actilife = sadeh_score(df, threshold=-4.0)
        result_original = sadeh_score(df, threshold=0.0)

        actilife_sleep = result_actilife["Sleep Score"].tolist().count(1)
        original_wake = result_original["Sleep Score"].tolist().count(0)

        assert actilife_sleep >= 20, f"ActiLife should give mostly sleep, got {actilife_sleep}"
        assert original_wake >= 20, f"Original should give mostly wake, got {original_wake}"

    def test_count_scaling_option(self) -> None:
        """Count scaling can be enabled and produces valid results."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=15, freq="1min"),
                "Axis1": [45, 32, 0, 12, 5, 100, 200, 50, 10, 0, 0, 0, 5, 10, 15],
            }
        )

        result_normal = sadeh_score(df)
        result_scaled = sadeh_score(df, enable_count_scaling=True)

        assert len(result_normal) == len(result_scaled)


class TestSadehAlgorithmInit:
    """Tests for SadehAlgorithm initialization."""

    def test_default_threshold_is_actilife(self) -> None:
        """Default threshold is -4.0 (ActiLife)."""
        algorithm = SadehAlgorithm()

        assert algorithm._threshold == -4.0

    def test_custom_threshold(self) -> None:
        """Can set custom threshold."""
        algorithm = SadehAlgorithm(threshold=0.0)

        assert algorithm._threshold == 0.0

    def test_count_scaling_disabled_by_default(self) -> None:
        """Count scaling disabled by default."""
        algorithm = SadehAlgorithm()

        assert algorithm._enable_count_scaling is False


class TestSadehAlgorithmProperties:
    """Tests for SadehAlgorithm properties."""

    def test_name_actilife_variant(self) -> None:
        """Name includes ActiLife for default threshold."""
        algorithm = SadehAlgorithm()

        assert "ActiLife" in algorithm.name

    def test_name_original_variant(self) -> None:
        """Name includes Original for threshold=0.0."""
        algorithm = SadehAlgorithm(threshold=0.0, variant_name="original")

        assert "Original" in algorithm.name

    def test_name_count_scaled_variant(self) -> None:
        """Name includes Count-Scaled when enabled."""
        algorithm = SadehAlgorithm(enable_count_scaling=True)

        assert "Count-Scaled" in algorithm.name

    def test_identifier_actilife(self) -> None:
        """Identifier is correct for ActiLife variant."""
        algorithm = SadehAlgorithm()

        assert algorithm.identifier == AlgorithmType.SADEH_1994_ACTILIFE

    def test_identifier_original(self) -> None:
        """Identifier is correct for original variant."""
        algorithm = SadehAlgorithm(threshold=0.0, variant_name="original")

        assert algorithm.identifier == AlgorithmType.SADEH_1994_ORIGINAL

    def test_requires_axis_y(self) -> None:
        """Requires axis_y (vertical axis)."""
        algorithm = SadehAlgorithm()

        assert algorithm.requires_axis == "axis_y"

    def test_data_requirement_epoch(self) -> None:
        """Data requirement is EPOCH_DATA."""
        algorithm = SadehAlgorithm()

        assert algorithm.data_requirement == AlgorithmDataRequirement.EPOCH_DATA


class TestSadehAlgorithmScore:
    """Tests for SadehAlgorithm scoring methods."""

    def test_score_dataframe(self, sample_dataframe: pd.DataFrame) -> None:
        """score() method works with DataFrame."""
        algorithm = SadehAlgorithm()

        result = algorithm.score(sample_dataframe)

        assert "Sleep Score" in result.columns


class TestSadehAlgorithmParameters:
    """Tests for SadehAlgorithm parameter methods."""

    def test_get_parameters(self) -> None:
        """get_parameters() returns parameter dict."""
        algorithm = SadehAlgorithm()

        params = algorithm.get_parameters()

        assert "threshold" in params
        assert "window_size" in params
        assert params["window_size"] == WINDOW_SIZE

    def test_set_parameters_threshold(self) -> None:
        """set_parameters() can update threshold."""
        algorithm = SadehAlgorithm()

        algorithm.set_parameters(threshold=0.0)

        assert algorithm._threshold == 0.0

    def test_set_parameters_warns_on_invalid(self) -> None:
        """set_parameters() warns on invalid parameters."""
        algorithm = SadehAlgorithm()

        # Should log warning but not raise
        algorithm.set_parameters(invalid_param=123)

        # Original parameters unchanged
        assert algorithm._threshold == -4.0
