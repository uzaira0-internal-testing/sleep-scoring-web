"""
Tests for calculation utilities.

Tests canonical calculation functions for durations and overlaps.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from sleep_scoring_app.utils.calculations import (
    calculate_duration_minutes_from_datetimes,
    calculate_duration_minutes_from_timestamps,
    calculate_overlapping_nonwear_minutes,
    calculate_total_minutes_in_bed_from_indices,
)


class TestCalculateDurationMinutesFromTimestamps:
    """Tests for calculate_duration_minutes_from_timestamps function."""

    def test_returns_float(self) -> None:
        """Returns float value."""
        start_ts = datetime(2024, 1, 15, 22, 0).timestamp()
        end_ts = datetime(2024, 1, 15, 22, 30).timestamp()

        result = calculate_duration_minutes_from_timestamps(start_ts, end_ts)

        assert isinstance(result, float)

    def test_calculates_30_minute_duration(self) -> None:
        """Calculates 30-minute duration correctly."""
        start_ts = datetime(2024, 1, 15, 22, 0).timestamp()
        end_ts = datetime(2024, 1, 15, 22, 30).timestamp()

        result = calculate_duration_minutes_from_timestamps(start_ts, end_ts)

        assert result == 30.0

    def test_calculates_overnight_duration(self) -> None:
        """Calculates overnight duration (crossing midnight)."""
        start_ts = datetime(2024, 1, 15, 23, 0).timestamp()
        end_ts = datetime(2024, 1, 16, 7, 0).timestamp()

        result = calculate_duration_minutes_from_timestamps(start_ts, end_ts)

        assert result == 8 * 60  # 8 hours

    def test_handles_fractional_minutes(self) -> None:
        """Handles fractional minutes."""
        start_ts = datetime(2024, 1, 15, 22, 0, 0).timestamp()
        end_ts = datetime(2024, 1, 15, 22, 0, 30).timestamp()  # 30 seconds

        result = calculate_duration_minutes_from_timestamps(start_ts, end_ts)

        assert result == 0.5

    def test_negative_duration(self) -> None:
        """Returns negative for reversed timestamps."""
        start_ts = datetime(2024, 1, 15, 23, 0).timestamp()
        end_ts = datetime(2024, 1, 15, 22, 0).timestamp()

        result = calculate_duration_minutes_from_timestamps(start_ts, end_ts)

        assert result == -60.0

    def test_zero_duration(self) -> None:
        """Returns zero for same timestamps."""
        ts = datetime(2024, 1, 15, 22, 0).timestamp()

        result = calculate_duration_minutes_from_timestamps(ts, ts)

        assert result == 0.0


class TestCalculateDurationMinutesFromDatetimes:
    """Tests for calculate_duration_minutes_from_datetimes function."""

    def test_returns_int(self) -> None:
        """Returns integer value."""
        start_dt = datetime(2024, 1, 15, 22, 0)
        end_dt = datetime(2024, 1, 15, 22, 30)

        result = calculate_duration_minutes_from_datetimes(start_dt, end_dt)

        assert isinstance(result, int)

    def test_calculates_30_minute_duration(self) -> None:
        """Calculates 30-minute duration correctly."""
        start_dt = datetime(2024, 1, 15, 22, 0)
        end_dt = datetime(2024, 1, 15, 22, 30)

        result = calculate_duration_minutes_from_datetimes(start_dt, end_dt)

        assert result == 30

    def test_calculates_overnight_duration(self) -> None:
        """Calculates overnight duration (crossing midnight)."""
        start_dt = datetime(2024, 1, 15, 23, 0)
        end_dt = datetime(2024, 1, 16, 7, 0)

        result = calculate_duration_minutes_from_datetimes(start_dt, end_dt)

        assert result == 8 * 60  # 8 hours

    def test_truncates_fractional_minutes(self) -> None:
        """Truncates fractional minutes (returns int)."""
        start_dt = datetime(2024, 1, 15, 22, 0, 0)
        end_dt = datetime(2024, 1, 15, 22, 0, 45)  # 45 seconds

        result = calculate_duration_minutes_from_datetimes(start_dt, end_dt)

        assert result == 0  # Truncated, not rounded

    def test_negative_duration(self) -> None:
        """Returns negative for reversed datetimes."""
        start_dt = datetime(2024, 1, 15, 23, 0)
        end_dt = datetime(2024, 1, 15, 22, 0)

        result = calculate_duration_minutes_from_datetimes(start_dt, end_dt)

        assert result == -60

    def test_zero_duration(self) -> None:
        """Returns zero for same datetimes."""
        dt = datetime(2024, 1, 15, 22, 0)

        result = calculate_duration_minutes_from_datetimes(dt, dt)

        assert result == 0


class TestCalculateTotalMinutesInBedFromIndices:
    """Tests for calculate_total_minutes_in_bed_from_indices function."""

    def test_returns_int(self) -> None:
        """Returns integer value."""
        result = calculate_total_minutes_in_bed_from_indices(100, 200)

        assert isinstance(result, int)

    def test_calculates_difference(self) -> None:
        """Calculates difference between indices."""
        result = calculate_total_minutes_in_bed_from_indices(100, 200)

        assert result == 100

    def test_uses_exclusive_end(self) -> None:
        """Uses exclusive end index (ActiLife compatibility)."""
        # If onset is at epoch 0 and offset is at epoch 10,
        # TIB = 10 - 0 = 10 minutes (not 11)
        result = calculate_total_minutes_in_bed_from_indices(0, 10)

        assert result == 10

    def test_zero_duration(self) -> None:
        """Returns zero for same indices."""
        result = calculate_total_minutes_in_bed_from_indices(100, 100)

        assert result == 0

    def test_typical_sleep_duration(self) -> None:
        """Calculates typical 8-hour sleep duration."""
        # 8 hours = 480 minutes
        onset = 1320  # 10 PM (1320 minutes from midnight)
        offset = 1800  # 6 AM next day (480 + 1320 = 1800, but actually offset would be 1320 + 480)

        result = calculate_total_minutes_in_bed_from_indices(onset, onset + 480)

        assert result == 480


class TestCalculateOverlappingNonwearMinutes:
    """Tests for calculate_overlapping_nonwear_minutes function."""

    def test_counts_nonwear_epochs_in_range(self) -> None:
        """Counts nonwear epochs (1s) within range."""
        # 10 epochs, some nonwear
        nonwear = [0, 0, 1, 1, 1, 0, 0, 0, 0, 0]  # 3 nonwear at indices 2-4
        onset = 2
        offset = 4

        result = calculate_overlapping_nonwear_minutes(nonwear, onset, offset)

        assert result == 3  # All 3 nonwear epochs are in sleep period

    def test_includes_onset_and_offset_indices(self) -> None:
        """Includes both onset and offset indices."""
        nonwear = [1, 1, 1, 1, 1]  # All nonwear
        onset = 1
        offset = 3

        result = calculate_overlapping_nonwear_minutes(nonwear, onset, offset)

        assert result == 3  # Indices 1, 2, 3

    def test_returns_none_for_none_nonwear_array(self) -> None:
        """Returns None when nonwear_array is None."""
        result = calculate_overlapping_nonwear_minutes(None, 0, 10)

        assert result is None

    def test_returns_none_for_empty_nonwear_array(self) -> None:
        """Returns None when nonwear_array is empty (treated same as None)."""
        result = calculate_overlapping_nonwear_minutes([], 0, 10)

        assert result is None

    def test_returns_zero_when_onset_is_none(self) -> None:
        """Returns 0 when onset_idx is None but array exists."""
        nonwear = [0, 1, 1, 0]

        result = calculate_overlapping_nonwear_minutes(nonwear, None, 3)

        # Array exists so returns 0 (not None) to distinguish from "no data"
        assert result == 0

    def test_returns_zero_when_offset_is_none(self) -> None:
        """Returns 0 when offset_idx is None but array exists."""
        nonwear = [0, 1, 1, 0]

        result = calculate_overlapping_nonwear_minutes(nonwear, 0, None)

        # Array exists so returns 0 (not None) to distinguish from "no data"
        assert result == 0

    def test_returns_none_when_offset_beyond_array(self) -> None:
        """Returns None when offset_idx is beyond array length."""
        nonwear = [0, 1, 1, 0]  # 4 elements, max valid index is 3

        result = calculate_overlapping_nonwear_minutes(nonwear, 0, 10)

        assert result is None

    def test_returns_zero_when_no_nonwear_in_range(self) -> None:
        """Returns 0 when no nonwear in range."""
        nonwear = [1, 1, 0, 0, 0, 0, 0, 0, 1, 1]  # Nonwear at edges only
        onset = 3
        offset = 6

        result = calculate_overlapping_nonwear_minutes(nonwear, onset, offset)

        assert result == 0

    def test_handles_all_wear(self) -> None:
        """Handles array with all wear (no nonwear)."""
        nonwear = [0, 0, 0, 0, 0]

        result = calculate_overlapping_nonwear_minutes(nonwear, 1, 3)

        assert result == 0

    def test_handles_all_nonwear(self) -> None:
        """Handles array with all nonwear."""
        nonwear = [1, 1, 1, 1, 1]

        result = calculate_overlapping_nonwear_minutes(nonwear, 0, 4)

        assert result == 5

    def test_handles_single_epoch_range(self) -> None:
        """Handles single epoch range (onset == offset)."""
        nonwear = [0, 1, 0, 0, 0]

        result = calculate_overlapping_nonwear_minutes(nonwear, 1, 1)

        assert result == 1  # Single epoch is nonwear
