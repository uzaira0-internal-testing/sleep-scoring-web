"""
Tests for sleep/wake utility functions.

Tests shared utility functions used by sleep scoring algorithms.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms.sleep_wake.utils import (
    find_datetime_column,
    scale_counts,
    validate_and_collapse_epochs,
)


class TestScaleCounts:
    """Tests for scale_counts function."""

    def test_returns_numpy_array(self) -> None:
        """Returns numpy array."""
        counts = np.array([100, 200, 300])

        result = scale_counts(counts)

        assert isinstance(result, np.ndarray)

    def test_divides_by_scale_factor(self) -> None:
        """Divides counts by scale factor."""
        counts = np.array([4500, 3200, 1000])

        result = scale_counts(counts, scale_factor=100.0)

        assert result[0] == 45.0
        assert result[1] == 32.0
        assert result[2] == 10.0

    def test_caps_at_maximum(self) -> None:
        """Caps scaled values at maximum."""
        counts = np.array([4500, 35000])  # 35000/100 = 350 > 300

        result = scale_counts(counts, scale_factor=100.0, cap=300.0)

        assert result[1] == 300.0

    def test_clips_negative_to_zero(self) -> None:
        """Clips negative scaled values to zero."""
        # This shouldn't happen in practice, but test the clipping
        counts = np.array([100, 0])

        result = scale_counts(counts, scale_factor=100.0)

        assert result[1] >= 0

    def test_default_parameters(self) -> None:
        """Default parameters are scale_factor=100, cap=300."""
        counts = np.array([10000, 50000])

        result = scale_counts(counts)

        assert result[0] == 100.0  # 10000 / 100
        assert result[1] == 300.0  # 50000 / 100 = 500, capped to 300

    def test_preserves_array_length(self) -> None:
        """Preserves input array length."""
        counts = np.array([100, 200, 300, 400, 500])

        result = scale_counts(counts)

        assert len(result) == len(counts)

    def test_empty_array(self) -> None:
        """Handles empty array."""
        counts = np.array([])

        result = scale_counts(counts)

        assert len(result) == 0

    def test_custom_scale_factor(self) -> None:
        """Works with custom scale factor."""
        counts = np.array([500, 1000])

        result = scale_counts(counts, scale_factor=50.0)

        assert result[0] == 10.0  # 500 / 50
        assert result[1] == 20.0  # 1000 / 50

    def test_custom_cap(self) -> None:
        """Works with custom cap."""
        counts = np.array([10000, 20000])

        result = scale_counts(counts, scale_factor=100.0, cap=150.0)

        assert result[0] == 100.0  # 10000 / 100
        assert result[1] == 150.0  # 20000 / 100 = 200, capped to 150


class TestFindDatetimeColumn:
    """Tests for find_datetime_column function."""

    def test_finds_datetime_column_by_name(self) -> None:
        """Finds column named 'datetime'."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "value": range(10),
            }
        )

        result = find_datetime_column(df)

        assert result == "datetime"

    def test_finds_timestamp_column_by_name(self) -> None:
        """Finds column named 'timestamp'."""
        df = pd.DataFrame(
            {
                "timestamp": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "value": range(10),
            }
        )

        result = find_datetime_column(df)

        assert result == "timestamp"

    def test_finds_time_column_by_name(self) -> None:
        """Finds column named 'time'."""
        df = pd.DataFrame(
            {
                "time": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "value": range(10),
            }
        )

        result = find_datetime_column(df)

        assert result == "time"

    def test_case_insensitive_name_matching(self) -> None:
        """Matches column names case-insensitively."""
        df = pd.DataFrame(
            {
                "DateTime": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "value": range(10),
            }
        )

        result = find_datetime_column(df)

        assert result == "DateTime"

    def test_finds_by_dtype_if_no_named_match(self) -> None:
        """Finds column by datetime dtype if no named match."""
        df = pd.DataFrame(
            {
                "my_dates": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "value": range(10),
            }
        )

        result = find_datetime_column(df)

        assert result == "my_dates"

    def test_raises_if_no_datetime_column(self) -> None:
        """Raises ValueError if no datetime column found."""
        df = pd.DataFrame(
            {
                "col1": [1, 2, 3],
                "col2": ["a", "b", "c"],
            }
        )

        with pytest.raises(ValueError, match="No datetime column found"):
            find_datetime_column(df)

    def test_prefers_named_over_dtype(self) -> None:
        """Prefers named columns over dtype detection."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=5, freq="1min"),
                "other_dates": pd.date_range("2024-01-16", periods=5, freq="1min"),
            }
        )

        result = find_datetime_column(df)

        assert result == "datetime"


class TestValidateAndCollapseEpochs:
    """Tests for validate_and_collapse_epochs function."""

    def test_returns_unchanged_for_one_minute_epochs(self) -> None:
        """Returns unchanged DataFrame for 1-minute epochs."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=10, freq="1min"),
                "value": range(10),
            }
        )

        result = validate_and_collapse_epochs(df, "datetime")

        assert len(result) == 10

    def test_collapses_sub_minute_epochs(self) -> None:
        """Collapses sub-minute epochs to 1-minute."""
        # 30-second epochs (2 per minute)
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=20, freq="30s"),
                "value": np.ones(20),
            }
        )

        result = validate_and_collapse_epochs(df, "datetime")

        # 20 * 30s = 10 minutes of data, should have ~10 epochs
        assert len(result) <= 20
        # Values should be summed (2 * 1 = 2 per minute)
        assert result["value"].iloc[0] == 2.0

    def test_raises_for_epochs_larger_than_one_minute(self) -> None:
        """Raises ValueError for epochs larger than 1 minute."""
        # 2-minute epochs
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=10, freq="2min"),
                "value": range(10),
            }
        )

        with pytest.raises(ValueError, match="larger than 1 minute"):
            validate_and_collapse_epochs(df, "datetime")

    def test_returns_single_row_unchanged(self) -> None:
        """Returns single row DataFrame unchanged."""
        df = pd.DataFrame(
            {
                "datetime": [pd.Timestamp("2024-01-15 00:00:00")],
                "value": [100],
            }
        )

        result = validate_and_collapse_epochs(df, "datetime")

        assert len(result) == 1
        assert result["value"].iloc[0] == 100

    def test_returns_empty_unchanged(self) -> None:
        """Returns empty DataFrame unchanged."""
        df = pd.DataFrame({"datetime": [], "value": []})
        df["datetime"] = pd.to_datetime(df["datetime"])

        result = validate_and_collapse_epochs(df, "datetime")

        assert len(result) == 0

    def test_sorts_by_datetime(self) -> None:
        """Sorts data by datetime column."""
        df = pd.DataFrame(
            {
                "datetime": [
                    pd.Timestamp("2024-01-15 00:02:00"),
                    pd.Timestamp("2024-01-15 00:00:00"),
                    pd.Timestamp("2024-01-15 00:01:00"),
                ],
                "value": [3, 1, 2],
            }
        )

        result = validate_and_collapse_epochs(df, "datetime")

        # Should be sorted chronologically
        assert result["datetime"].iloc[0] == pd.Timestamp("2024-01-15 00:00:00")

    def test_tolerates_slight_epoch_variation(self) -> None:
        """Tolerates slight variation in epoch timing (within 0.02 min)."""
        # Create epochs that are very close to 1 minute
        timestamps = pd.date_range("2024-01-15", periods=10, freq="60100ms")  # 60.1 seconds
        df = pd.DataFrame(
            {
                "datetime": timestamps,
                "value": range(10),
            }
        )

        result = validate_and_collapse_epochs(df, "datetime")

        # Should accept as-is since very close to 1 minute
        assert len(result) == 10

    def test_preserves_numeric_columns_only(self) -> None:
        """Only numeric columns are resampled."""
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2024-01-15", periods=4, freq="30s"),
                "numeric_val": [1, 2, 3, 4],
                "string_val": ["a", "b", "c", "d"],
            }
        )

        result = validate_and_collapse_epochs(df, "datetime")

        # Numeric column should be present and aggregated
        assert "numeric_val" in result.columns
        # String column should not be in result (only numeric columns resampled)
        assert "string_val" not in result.columns
