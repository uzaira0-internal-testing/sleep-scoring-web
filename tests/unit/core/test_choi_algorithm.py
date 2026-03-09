"""
Tests for Choi (2011) Nonwear Detection Algorithm.

Tests the algorithm constants, helper functions, main detection functions,
and the ChoiAlgorithm class.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms.nonwear.choi import (
    MIN_PERIOD_LENGTH,
    SPIKE_TOLERANCE,
    WINDOW_SIZE,
    ChoiAlgorithm,
    _merge_adjacent_periods,
    choi_detect_nonwear,
)
from sleep_scoring_app.core.algorithms.types import ActivityColumn
from sleep_scoring_app.core.constants import AlgorithmOutputColumn, NonwearAlgorithm, NonwearDataSource
from sleep_scoring_app.core.dataclasses import NonwearPeriod


class TestChoiConstants:
    """Tests for algorithm constants."""

    def test_min_period_length(self) -> None:
        """MIN_PERIOD_LENGTH is 90 minutes per paper."""
        assert MIN_PERIOD_LENGTH == 90

    def test_spike_tolerance(self) -> None:
        """SPIKE_TOLERANCE is 2 minutes per paper."""
        assert SPIKE_TOLERANCE == 2

    def test_window_size(self) -> None:
        """WINDOW_SIZE is 30 minutes per paper."""
        assert WINDOW_SIZE == 30


class TestMergeAdjacentPeriods:
    """Tests for _merge_adjacent_periods helper function."""

    def test_empty_list(self) -> None:
        """Returns empty list for empty input."""
        result = _merge_adjacent_periods([])
        assert result == []

    def test_single_period(self) -> None:
        """Returns single period unchanged."""
        period = NonwearPeriod(
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 12, 0),
            participant_id="P001",
            source=NonwearDataSource.CHOI_ALGORITHM,
        )
        result = _merge_adjacent_periods([period])

        assert len(result) == 1
        assert result[0].start_time == period.start_time
        assert result[0].end_time == period.end_time

    def test_merges_adjacent_periods(self) -> None:
        """Merges periods within 60 seconds of each other."""
        period1 = NonwearPeriod(
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 11, 0),
            participant_id="P001",
            source=NonwearDataSource.CHOI_ALGORITHM,
            start_index=0,
            end_index=59,
        )
        period2 = NonwearPeriod(
            start_time=datetime(2024, 1, 1, 11, 0, 30),  # 30 seconds after first ends
            end_time=datetime(2024, 1, 1, 12, 0),
            participant_id="P001",
            source=NonwearDataSource.CHOI_ALGORITHM,
            start_index=60,
            end_index=119,
        )

        result = _merge_adjacent_periods([period1, period2])

        assert len(result) == 1
        assert result[0].start_time == period1.start_time
        assert result[0].end_time == period2.end_time

    def test_does_not_merge_separate_periods(self) -> None:
        """Does not merge periods more than 60 seconds apart."""
        period1 = NonwearPeriod(
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 11, 0),
            participant_id="P001",
            source=NonwearDataSource.CHOI_ALGORITHM,
        )
        period2 = NonwearPeriod(
            start_time=datetime(2024, 1, 1, 13, 0),  # 2 hours after first ends
            end_time=datetime(2024, 1, 1, 14, 0),
            participant_id="P001",
            source=NonwearDataSource.CHOI_ALGORITHM,
        )

        result = _merge_adjacent_periods([period1, period2])

        assert len(result) == 2

    def test_sorts_by_start_time(self) -> None:
        """Sorts periods by start time before merging."""
        period2 = NonwearPeriod(
            start_time=datetime(2024, 1, 1, 13, 0),
            end_time=datetime(2024, 1, 1, 14, 0),
            participant_id="P001",
            source=NonwearDataSource.CHOI_ALGORITHM,
        )
        period1 = NonwearPeriod(
            start_time=datetime(2024, 1, 1, 10, 0),
            end_time=datetime(2024, 1, 1, 11, 0),
            participant_id="P001",
            source=NonwearDataSource.CHOI_ALGORITHM,
        )

        # Pass in reverse order
        result = _merge_adjacent_periods([period2, period1])

        assert len(result) == 2
        assert result[0].start_time < result[1].start_time


class TestDetectInputValidation:
    """Tests for ChoiAlgorithm.detect input validation."""

    def test_none_activity_data_raises(self) -> None:
        """Raises ValueError for None activity data."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="None"):
            algo.detect(None, [])

    def test_none_timestamps_raises(self) -> None:
        """Raises ValueError for None timestamps."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="None"):
            algo.detect([1, 2, 3], None)

    def test_mismatched_lengths_raises(self) -> None:
        """Raises ValueError for mismatched lengths."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="length"):
            algo.detect([1, 2, 3], [datetime.now()])

    def test_empty_data_returns_empty(self) -> None:
        """Returns empty list for empty data."""
        algo = ChoiAlgorithm()
        result = algo.detect([], [])
        assert result == []

    def test_nan_values_raises(self) -> None:
        """Raises ValueError for NaN values."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="NaN"):
            algo.detect([1.0, np.nan, 2.0], [datetime.now()] * 3)

    def test_infinite_values_raises(self) -> None:
        """Raises ValueError for infinite values."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="infinite"):
            algo.detect([1.0, np.inf, 2.0], [datetime.now()] * 3)

    def test_negative_values_raises(self) -> None:
        """Raises ValueError for negative values."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="negative"):
            algo.detect([1.0, -5.0, 2.0], [datetime.now()] * 3)

    def test_detects_long_zero_period(self) -> None:
        """Detects nonwear period of 90+ minutes of zeros."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [0.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 1
        assert result[0].start_time == timestamps[0]
        assert result[0].end_time == timestamps[-1]
        assert result[0].source == NonwearDataSource.CHOI_ALGORITHM

    def test_ignores_short_zero_period(self) -> None:
        """Ignores zero period shorter than 90 minutes."""
        algo = ChoiAlgorithm()
        n_epochs = 60
        activity_data = [0.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 0

    def test_all_nonzero_returns_empty(self) -> None:
        """Returns empty list when all values are nonzero."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [100.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 0

    def test_allows_small_spikes(self) -> None:
        """Allows small spikes within nonwear period (SPIKE_TOLERANCE)."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [0.0] * n_epochs
        activity_data[30] = 10.0  # Spike at minute 30
        activity_data[60] = 10.0  # Spike at minute 60
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        # Should still detect as single nonwear period (within spike tolerance)
        assert len(result) >= 1


class TestChoiDetectNonwear:
    """Tests for choi_detect_nonwear DataFrame function."""

    def test_none_dataframe_raises(self) -> None:
        """Raises ValueError for None DataFrame."""
        with pytest.raises(ValueError, match="None or empty"):
            choi_detect_nonwear(None)

    def test_empty_dataframe_raises(self) -> None:
        """Raises ValueError for empty DataFrame."""
        df = pd.DataFrame()
        with pytest.raises(ValueError, match="None or empty"):
            choi_detect_nonwear(df)

    def test_missing_activity_column_raises(self) -> None:
        """Raises ValueError if activity column missing."""
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime(["2024-01-01 10:00:00"]),
                "other_column": [100],
            }
        )
        with pytest.raises(ValueError, match="Vector Magnitude"):
            choi_detect_nonwear(df, activity_column=ActivityColumn.VECTOR_MAGNITUDE)

    def test_returns_dataframe_with_nonwear_column(self) -> None:
        """Returns DataFrame with nonwear score column."""
        # Create 120 minutes of zeros
        n_epochs = 120
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime([f"2024-01-01 {10 + i // 60:02d}:{i % 60:02d}:00" for i in range(n_epochs)]),
                "Vector Magnitude": [0.0] * n_epochs,
            }
        )

        result = choi_detect_nonwear(df)

        assert AlgorithmOutputColumn.NONWEAR_SCORE in result.columns
        assert len(result) == n_epochs

    def test_preserves_original_columns(self) -> None:
        """Preserves all original columns."""
        n_epochs = 120
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime([f"2024-01-01 {10 + i // 60:02d}:{i % 60:02d}:00" for i in range(n_epochs)]),
                "Vector Magnitude": [0.0] * n_epochs,
                "extra_column": list(range(n_epochs)),
            }
        )

        result = choi_detect_nonwear(df)

        assert "extra_column" in result.columns
        assert "Vector Magnitude" in result.columns

    def test_nonwear_mask_values_are_0_or_1(self) -> None:
        """Nonwear mask contains only 0 or 1 values."""
        n_epochs = 120
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime([f"2024-01-01 {10 + i // 60:02d}:{i % 60:02d}:00" for i in range(n_epochs)]),
                "Vector Magnitude": [0.0] * n_epochs,
            }
        )

        result = choi_detect_nonwear(df)

        unique_values = result[AlgorithmOutputColumn.NONWEAR_SCORE].unique()
        assert set(unique_values).issubset({0, 1})

    def test_uses_specified_activity_column(self) -> None:
        """Uses specified activity column."""
        n_epochs = 120
        df = pd.DataFrame(
            {
                "datetime": pd.to_datetime([f"2024-01-01 {10 + i // 60:02d}:{i % 60:02d}:00" for i in range(n_epochs)]),
                "axis_y": [0.0] * n_epochs,  # Must match ActivityColumn.AXIS_Y.value
            }
        )

        result = choi_detect_nonwear(df, activity_column=ActivityColumn.AXIS_Y)

        assert AlgorithmOutputColumn.NONWEAR_SCORE in result.columns


class TestChoiAlgorithmProperties:
    """Tests for ChoiAlgorithm properties."""

    def test_name(self) -> None:
        """Algorithm has correct name."""
        algo = ChoiAlgorithm()
        assert algo.name == "Choi (2011)"

    def test_identifier(self) -> None:
        """Algorithm has correct identifier."""
        algo = ChoiAlgorithm()
        assert algo.identifier == NonwearAlgorithm.CHOI_2011

    def test_default_parameters(self) -> None:
        """Default parameters match published values."""
        algo = ChoiAlgorithm()
        params = algo.get_parameters()

        assert params["min_period_length"] == 90
        assert params["spike_tolerance"] == 2
        assert params["small_window_length"] == 30
        assert params["use_vector_magnitude"] is True

    def test_custom_parameters(self) -> None:
        """Can set custom parameters in constructor."""
        algo = ChoiAlgorithm(
            min_period_length=60,
            spike_tolerance=3,
            small_window_length=20,
            use_vector_magnitude=False,
        )
        params = algo.get_parameters()

        assert params["min_period_length"] == 60
        assert params["spike_tolerance"] == 3
        assert params["small_window_length"] == 20
        assert params["use_vector_magnitude"] is False


class TestChoiAlgorithmDetect:
    """Tests for ChoiAlgorithm.detect method."""

    def test_detect_returns_list_of_periods(self) -> None:
        """detect returns list of NonwearPeriod objects."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [0.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(isinstance(p, NonwearPeriod) for p in result)

    def test_detect_empty_data(self) -> None:
        """detect returns empty list for empty data."""
        algo = ChoiAlgorithm()
        result = algo.detect([], [])
        assert result == []

    def test_detect_uses_timestamps(self) -> None:
        """detect uses provided timestamps for period boundaries."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [0.0] * n_epochs
        start_time = datetime(2024, 6, 15, 14, 30)  # Specific start time
        timestamps = [start_time + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 1
        assert result[0].start_time == start_time


class TestChoiAlgorithmDetectMask:
    """Tests for ChoiAlgorithm.detect_mask method."""

    def test_detect_mask_returns_list(self) -> None:
        """detect_mask returns list of integers."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [0.0] * n_epochs

        result = algo.detect_mask(activity_data)

        assert isinstance(result, list)
        assert len(result) == n_epochs

    def test_detect_mask_values_0_or_1(self) -> None:
        """detect_mask returns only 0 or 1 values."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [0.0] * n_epochs

        result = algo.detect_mask(activity_data)

        assert set(result).issubset({0, 1})

    def test_detect_mask_empty_data(self) -> None:
        """detect_mask returns empty list for empty data."""
        algo = ChoiAlgorithm()
        result = algo.detect_mask([])
        assert result == []

    def test_detect_mask_none_raises(self) -> None:
        """detect_mask raises for None input."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="None"):
            algo.detect_mask(None)

    def test_detect_mask_marks_nonwear(self) -> None:
        """detect_mask marks nonwear periods with 1."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [0.0] * n_epochs

        result = algo.detect_mask(activity_data)

        # All zeros should be marked as nonwear
        assert sum(result) >= 90  # At least MIN_PERIOD_LENGTH marked


class TestChoiAlgorithmSetParameters:
    """Tests for ChoiAlgorithm.set_parameters method."""

    def test_set_valid_parameters(self) -> None:
        """Can set valid parameters."""
        algo = ChoiAlgorithm()
        algo.set_parameters(min_period_length=60)

        assert algo.get_parameters()["min_period_length"] == 60

    def test_set_multiple_parameters(self) -> None:
        """Can set multiple parameters at once."""
        algo = ChoiAlgorithm()
        algo.set_parameters(
            min_period_length=60,
            spike_tolerance=1,
        )

        params = algo.get_parameters()
        assert params["min_period_length"] == 60
        assert params["spike_tolerance"] == 1

    def test_set_invalid_parameter_name_raises(self) -> None:
        """Raises ValueError for invalid parameter name."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="Invalid parameter"):
            algo.set_parameters(invalid_param=10)

    def test_set_negative_min_period_raises(self) -> None:
        """Raises ValueError for negative min_period_length."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="positive integer"):
            algo.set_parameters(min_period_length=-1)

    def test_set_negative_spike_tolerance_raises(self) -> None:
        """Raises ValueError for negative spike_tolerance."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="non-negative integer"):
            algo.set_parameters(spike_tolerance=-1)

    def test_set_negative_window_length_raises(self) -> None:
        """Raises ValueError for negative small_window_length."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="positive integer"):
            algo.set_parameters(small_window_length=-1)

    def test_set_non_bool_use_vector_magnitude_raises(self) -> None:
        """Raises ValueError for non-boolean use_vector_magnitude."""
        algo = ChoiAlgorithm()
        with pytest.raises(ValueError, match="boolean"):
            algo.set_parameters(use_vector_magnitude="yes")  # type: ignore[arg-type]


class TestChoiEdgeCases:
    """Tests for edge cases in Choi algorithm."""

    def test_exactly_90_minute_period(self) -> None:
        """Detects period of exactly 90 minutes."""
        algo = ChoiAlgorithm()
        n_epochs = 90
        activity_data = [0.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 1

    def test_89_minute_period_ignored(self) -> None:
        """Ignores period of 89 minutes (less than minimum)."""
        algo = ChoiAlgorithm()
        n_epochs = 89
        activity_data = [0.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 0

    def test_multiple_nonwear_periods(self) -> None:
        """Detects multiple separate nonwear periods."""
        algo = ChoiAlgorithm()
        activity_data = [0.0] * 100 + [100.0] * 30 + [0.0] * 100
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(len(activity_data))]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 2

    def test_very_large_dataset(self) -> None:
        """Handles large dataset (24 hours of data)."""
        algo = ChoiAlgorithm()
        n_epochs = 24 * 60  # 24 hours
        activity_data = [0.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 1
        assert result[0].duration_minutes == n_epochs

    def test_alternating_zeros_and_activity(self) -> None:
        """Handles alternating zeros and activity (no nonwear detected)."""
        algo = ChoiAlgorithm()
        n_epochs = 200
        activity_data = [0.0 if i % 2 == 0 else 100.0 for i in range(n_epochs)]
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 0

    def test_numpy_array_input(self) -> None:
        """Accepts numpy array as input."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = np.zeros(n_epochs)
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 1

    def test_custom_parameters_affect_detection(self) -> None:
        """Custom parameters actually change detection behavior (not just stored)."""
        # Create a 60-minute zero period: below default 90 min, above custom 50 min
        n_epochs = 60
        activity_data = [0.0] * n_epochs
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        # Default params (min_period_length=90): should NOT detect
        algo_default = ChoiAlgorithm()
        result_default = algo_default.detect(activity_data, timestamps)
        assert len(result_default) == 0, "Default 90-min threshold should skip 60-min period"

        # Custom params (min_period_length=50): SHOULD detect
        algo_custom = ChoiAlgorithm(min_period_length=50)
        result_custom = algo_custom.detect(activity_data, timestamps)
        assert len(result_custom) == 1, "Custom 50-min threshold should detect 60-min period"

    def test_period_has_correct_indices(self) -> None:
        """Detected period has correct start and end indices."""
        algo = ChoiAlgorithm()
        n_epochs = 120
        activity_data = [100.0] * 20 + [0.0] * 100
        timestamps = [datetime(2024, 1, 1) + timedelta(minutes=i) for i in range(n_epochs)]

        result = algo.detect(activity_data, timestamps)

        assert len(result) == 1
        assert result[0].start_index == 20
        assert result[0].end_index == 119
