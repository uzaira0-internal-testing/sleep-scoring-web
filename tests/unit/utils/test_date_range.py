"""
Tests for date range utilities.

Tests centralized date range calculation functions.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from sleep_scoring_app.utils.date_range import (
    DateRange,
    filter_data_to_range,
    get_24h_range,
    get_48h_range,
    get_range_for_view_mode,
)


class TestDateRange:
    """Tests for DateRange dataclass."""

    def test_is_frozen(self) -> None:
        """DateRange is immutable (frozen)."""
        dr = DateRange(
            start=datetime(2024, 1, 15, 12, 0),
            end=datetime(2024, 1, 16, 12, 0),
        )

        with pytest.raises(AttributeError):
            dr.start = datetime(2024, 1, 14, 12, 0)  # type: ignore

    def test_start_timestamp_property(self) -> None:
        """start_timestamp returns Unix timestamp."""
        dr = DateRange(
            start=datetime(2024, 1, 15, 12, 0),
            end=datetime(2024, 1, 16, 12, 0),
        )

        ts = dr.start_timestamp

        assert isinstance(ts, float)
        assert ts == datetime(2024, 1, 15, 12, 0).timestamp()

    def test_end_timestamp_property(self) -> None:
        """end_timestamp returns Unix timestamp."""
        dr = DateRange(
            start=datetime(2024, 1, 15, 12, 0),
            end=datetime(2024, 1, 16, 12, 0),
        )

        ts = dr.end_timestamp

        assert isinstance(ts, float)
        assert ts == datetime(2024, 1, 16, 12, 0).timestamp()

    def test_duration_hours_property(self) -> None:
        """duration_hours returns duration in hours."""
        dr = DateRange(
            start=datetime(2024, 1, 15, 12, 0),
            end=datetime(2024, 1, 16, 12, 0),
        )

        assert dr.duration_hours == 24.0

    def test_duration_hours_48h(self) -> None:
        """duration_hours works for 48-hour range."""
        dr = DateRange(
            start=datetime(2024, 1, 15, 0, 0),
            end=datetime(2024, 1, 17, 0, 0),
        )

        assert dr.duration_hours == 48.0


class TestGet24hRange:
    """Tests for get_24h_range function."""

    def test_returns_date_range(self) -> None:
        """Returns DateRange object."""
        result = get_24h_range(date(2024, 1, 15))

        assert isinstance(result, DateRange)

    def test_starts_at_noon(self) -> None:
        """Range starts at noon (12:00)."""
        result = get_24h_range(date(2024, 1, 15))

        assert result.start.hour == 12
        assert result.start.minute == 0

    def test_ends_at_noon_next_day(self) -> None:
        """Range ends at noon next day."""
        result = get_24h_range(date(2024, 1, 15))

        assert result.end.hour == 12
        assert result.end.minute == 0
        assert result.end.day == 16

    def test_duration_is_24_hours(self) -> None:
        """Duration is exactly 24 hours."""
        result = get_24h_range(date(2024, 1, 15))

        assert result.duration_hours == 24.0

    def test_accepts_datetime_input(self) -> None:
        """Accepts datetime input."""
        dt = datetime(2024, 1, 15, 8, 30, 45)

        result = get_24h_range(dt)

        assert result.start.hour == 12
        assert result.start.minute == 0
        assert result.start.second == 0
        assert result.start.microsecond == 0

    def test_preserves_date_from_datetime(self) -> None:
        """Preserves date portion from datetime input."""
        dt = datetime(2024, 1, 15, 23, 59, 59)

        result = get_24h_range(dt)

        assert result.start.year == 2024
        assert result.start.month == 1
        assert result.start.day == 15


class TestGet48hRange:
    """Tests for get_48h_range function."""

    def test_returns_date_range(self) -> None:
        """Returns DateRange object."""
        result = get_48h_range(date(2024, 1, 15))

        assert isinstance(result, DateRange)

    def test_starts_at_midnight(self) -> None:
        """Range starts at midnight (00:00)."""
        result = get_48h_range(date(2024, 1, 15))

        assert result.start.hour == 0
        assert result.start.minute == 0

    def test_ends_at_midnight_two_days_later(self) -> None:
        """Range ends at midnight two days later."""
        result = get_48h_range(date(2024, 1, 15))

        assert result.end.hour == 0
        assert result.end.minute == 0
        assert result.end.day == 17  # Two days later

    def test_duration_is_48_hours(self) -> None:
        """Duration is exactly 48 hours."""
        result = get_48h_range(date(2024, 1, 15))

        assert result.duration_hours == 48.0

    def test_accepts_datetime_input(self) -> None:
        """Accepts datetime input."""
        dt = datetime(2024, 1, 15, 8, 30, 45)

        result = get_48h_range(dt)

        assert result.start.hour == 0
        assert result.start.minute == 0
        assert result.start.second == 0
        assert result.start.microsecond == 0

    def test_preserves_date_from_datetime(self) -> None:
        """Preserves date portion from datetime input."""
        dt = datetime(2024, 1, 15, 23, 59, 59)

        result = get_48h_range(dt)

        assert result.start.year == 2024
        assert result.start.month == 1
        assert result.start.day == 15


class TestGetRangeForViewMode:
    """Tests for get_range_for_view_mode function."""

    def test_returns_24h_range_for_hours_24(self) -> None:
        """Returns 24h noon-to-noon range for hours=24."""
        result = get_range_for_view_mode(date(2024, 1, 15), hours=24)

        assert result.start.hour == 12
        assert result.duration_hours == 24.0

    def test_returns_48h_range_for_hours_48(self) -> None:
        """Returns 48h midnight-to-midnight range for hours=48."""
        result = get_range_for_view_mode(date(2024, 1, 15), hours=48)

        assert result.start.hour == 0
        assert result.duration_hours == 48.0

    def test_raises_for_invalid_hours(self) -> None:
        """Raises ValueError for invalid hours value."""
        with pytest.raises(ValueError, match="Invalid view mode hours"):
            get_range_for_view_mode(date(2024, 1, 15), hours=12)

    def test_raises_for_zero_hours(self) -> None:
        """Raises ValueError for zero hours."""
        with pytest.raises(ValueError, match="Invalid view mode hours"):
            get_range_for_view_mode(date(2024, 1, 15), hours=0)

    def test_raises_for_negative_hours(self) -> None:
        """Raises ValueError for negative hours."""
        with pytest.raises(ValueError, match="Invalid view mode hours"):
            get_range_for_view_mode(date(2024, 1, 15), hours=-24)


class TestFilterDataToRange:
    """Tests for filter_data_to_range function."""

    def test_filters_datetime_timestamps(self) -> None:
        """Filters data using datetime timestamps."""
        date_range = get_24h_range(date(2024, 1, 15))

        timestamps = [
            datetime(2024, 1, 15, 11, 0),  # Before range
            datetime(2024, 1, 15, 13, 0),  # In range
            datetime(2024, 1, 15, 18, 0),  # In range
            datetime(2024, 1, 16, 13, 0),  # After range
        ]
        data = [1.0, 2.0, 3.0, 4.0]

        filtered_ts, filtered_data = filter_data_to_range(timestamps, data, date_range)

        assert len(filtered_ts) == 2
        assert len(filtered_data) == 2
        assert filtered_data == [2.0, 3.0]

    def test_filters_float_timestamps(self) -> None:
        """Filters data using float (Unix) timestamps."""
        date_range = get_24h_range(date(2024, 1, 15))

        timestamps = [
            datetime(2024, 1, 15, 11, 0).timestamp(),  # Before range
            datetime(2024, 1, 15, 13, 0).timestamp(),  # In range
            datetime(2024, 1, 15, 18, 0).timestamp(),  # In range
            datetime(2024, 1, 16, 13, 0).timestamp(),  # After range
        ]
        data = [1.0, 2.0, 3.0, 4.0]

        filtered_ts, filtered_data = filter_data_to_range(timestamps, data, date_range)

        assert len(filtered_ts) == 2
        assert len(filtered_data) == 2

    def test_converts_float_to_datetime(self) -> None:
        """Converts float timestamps to datetime in output."""
        date_range = get_24h_range(date(2024, 1, 15))

        timestamps = [datetime(2024, 1, 15, 14, 0).timestamp()]
        data = [1.0]

        filtered_ts, _ = filter_data_to_range(timestamps, data, date_range)

        assert isinstance(filtered_ts[0], datetime)

    def test_returns_empty_for_empty_input(self) -> None:
        """Returns empty lists for empty input."""
        date_range = get_24h_range(date(2024, 1, 15))

        filtered_ts, filtered_data = filter_data_to_range([], [], date_range)

        assert filtered_ts == []
        assert filtered_data == []

    def test_excludes_end_timestamp(self) -> None:
        """Excludes data at exactly the end timestamp (half-open interval)."""
        date_range = get_24h_range(date(2024, 1, 15))

        timestamps = [
            datetime(2024, 1, 16, 12, 0),  # Exactly at end
        ]
        data = [1.0]

        filtered_ts, _filtered_data = filter_data_to_range(timestamps, data, date_range)

        assert len(filtered_ts) == 0

    def test_includes_start_timestamp(self) -> None:
        """Includes data at exactly the start timestamp."""
        date_range = get_24h_range(date(2024, 1, 15))

        timestamps = [
            datetime(2024, 1, 15, 12, 0),  # Exactly at start
        ]
        data = [1.0]

        filtered_ts, filtered_data = filter_data_to_range(timestamps, data, date_range)

        assert len(filtered_ts) == 1
        assert filtered_data[0] == 1.0

    def test_handles_all_data_in_range(self) -> None:
        """Returns all data when all timestamps in range."""
        date_range = get_24h_range(date(2024, 1, 15))

        timestamps = [
            datetime(2024, 1, 15, 14, 0),
            datetime(2024, 1, 15, 18, 0),
            datetime(2024, 1, 16, 8, 0),
        ]
        data = [1.0, 2.0, 3.0]

        filtered_ts, filtered_data = filter_data_to_range(timestamps, data, date_range)

        assert len(filtered_ts) == 3
        assert filtered_data == [1.0, 2.0, 3.0]

    def test_handles_no_data_in_range(self) -> None:
        """Returns empty when no timestamps in range."""
        date_range = get_24h_range(date(2024, 1, 15))

        timestamps = [
            datetime(2024, 1, 14, 10, 0),  # Before range
            datetime(2024, 1, 17, 10, 0),  # After range
        ]
        data = [1.0, 2.0]

        filtered_ts, filtered_data = filter_data_to_range(timestamps, data, date_range)

        assert len(filtered_ts) == 0
        assert len(filtered_data) == 0
