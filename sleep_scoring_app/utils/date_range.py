#!/usr/bin/env python3
"""
Centralized date range calculation utilities.

This module provides THE SINGLE SOURCE OF TRUTH for date range calculations
used throughout the application. All code that needs to calculate date ranges
for data loading, display, or filtering should use these functions.

The application uses two view modes:
- 24-hour view: noon to noon (12:00 PM current day to 12:00 PM next day)
- 48-hour view: midnight to midnight+48h (00:00 current day to 00:00 two days later)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class DateRange:
    """Immutable date range with start and end timestamps."""

    start: datetime
    end: datetime

    @property
    def start_timestamp(self) -> float:
        """Get start as Unix timestamp."""
        return self.start.timestamp()

    @property
    def end_timestamp(self) -> float:
        """Get end as Unix timestamp."""
        return self.end.timestamp()

    @property
    def duration_hours(self) -> float:
        """Get duration in hours."""
        return (self.end - self.start).total_seconds() / 3600


def get_24h_range(target_date: date | datetime) -> DateRange:
    """
    Get the 24-hour noon-to-noon range for a given date.

    The 24-hour view runs from noon (12:00) on the target date
    to noon (12:00) on the next day.

    Args:
        target_date: The date to get the range for

    Returns:
        DateRange with start at noon and end at noon next day

    Example:
        >>> from datetime import date
        >>> range = get_24h_range(date(2024, 1, 15))
        >>> range.start
        datetime.datetime(2024, 1, 15, 12, 0)
        >>> range.end
        datetime.datetime(2024, 1, 16, 12, 0)

    """
    if isinstance(target_date, datetime):
        base = target_date.replace(hour=12, minute=0, second=0, microsecond=0)
    else:
        base = datetime.combine(target_date, datetime.min.time()).replace(hour=12)

    return DateRange(start=base, end=base + timedelta(hours=24))


def get_48h_range(target_date: date | datetime) -> DateRange:
    """
    Get the 48-hour midnight-to-midnight range for a given date.

    The 48-hour view runs from midnight (00:00) on the target date
    to midnight (00:00) two days later.

    Args:
        target_date: The date to get the range for

    Returns:
        DateRange with start at midnight and end at midnight+48h

    Example:
        >>> from datetime import date
        >>> range = get_48h_range(date(2024, 1, 15))
        >>> range.start
        datetime.datetime(2024, 1, 15, 0, 0)
        >>> range.end
        datetime.datetime(2024, 1, 17, 0, 0)

    """
    if isinstance(target_date, datetime):
        base = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        base = datetime.combine(target_date, datetime.min.time())

    return DateRange(start=base, end=base + timedelta(hours=48))


def get_range_for_view_mode(target_date: date | datetime, hours: int) -> DateRange:
    """
    Get the date range for a given view mode.

    Args:
        target_date: The date to get the range for
        hours: View mode hours (24 or 48)

    Returns:
        DateRange for the specified view mode

    Raises:
        ValueError: If hours is not 24 or 48

    """
    if hours == 24:
        return get_24h_range(target_date)
    if hours == 48:
        return get_48h_range(target_date)
    msg = f"Invalid view mode hours: {hours}. Must be 24 or 48."
    raise ValueError(msg)


def filter_data_to_range(
    timestamps: list[datetime] | list[float],
    data: list[float],
    date_range: DateRange,
) -> tuple[list[datetime], list[float]]:
    """
    Filter data to a specific date range.

    Args:
        timestamps: List of timestamps (datetime or Unix float)
        data: Corresponding data values
        date_range: The range to filter to

    Returns:
        Tuple of (filtered_timestamps, filtered_data)

    """
    if not timestamps or not data:
        return [], []

    start_ts = date_range.start_timestamp
    end_ts = date_range.end_timestamp

    filtered_timestamps = []
    filtered_data = []

    for ts, value in zip(timestamps, data, strict=False):
        if isinstance(ts, datetime):
            ts_float = ts.timestamp()
        else:
            ts_float = ts

        if start_ts <= ts_float < end_ts:
            if isinstance(ts, datetime):
                filtered_timestamps.append(ts)
            else:
                filtered_timestamps.append(datetime.fromtimestamp(ts))
            filtered_data.append(value)

    return filtered_timestamps, filtered_data


__all__ = [
    "DateRange",
    "filter_data_to_range",
    "get_24h_range",
    "get_48h_range",
    "get_range_for_view_mode",
]
