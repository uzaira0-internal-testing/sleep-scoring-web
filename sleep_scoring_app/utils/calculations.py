"""
Canonical calculation utilities for sleep scoring metrics.

This module contains the single source of truth for common calculations used
throughout the application. All other modules should import from here rather
than duplicating logic.

Module ownership:
- Duration calculations: This module (for time-based durations)
- Sleep period durations: SleepPeriod.duration_minutes property (for period objects)
- Participant extraction: participant_extractor.py module
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime


def calculate_duration_minutes_from_timestamps(start_ts: float, end_ts: float) -> float:
    """
    Calculate duration in minutes from Unix timestamps.

    This is the canonical function for converting timestamp differences to minutes.

    Args:
        start_ts: Start timestamp (Unix epoch seconds)
        end_ts: End timestamp (Unix epoch seconds)

    Returns:
        Duration in minutes

    """
    return (end_ts - start_ts) / 60


def calculate_duration_minutes_from_datetimes(start_dt: datetime, end_dt: datetime) -> int:
    """
    Calculate duration in minutes from datetime objects.

    This is the canonical function for same-day duration calculations
    (e.g., nap periods, diary entries with HH:MM times).

    Args:
        start_dt: Start datetime
        end_dt: End datetime

    Returns:
        Duration in minutes (rounded to integer)

    """
    return int((end_dt - start_dt).total_seconds() / 60)


def calculate_total_minutes_in_bed_from_indices(onset_idx: int, offset_idx: int) -> int:
    """
    Calculate total minutes in bed from epoch indices.

    This is the canonical function for index-based TIB calculations.
    Uses exclusive end index (offset_idx - onset_idx) for ActiLife compatibility.

    Args:
        onset_idx: Sleep onset epoch index
        offset_idx: Sleep offset epoch index

    Returns:
        Total minutes in bed

    """
    return offset_idx - onset_idx


def calculate_overlapping_nonwear_minutes(
    nonwear_array: list[int] | None,
    onset_idx: int | None,
    offset_idx: int | None,
) -> int | None:
    """
    Calculate overlapping nonwear minutes during a sleep period.

    This is the canonical function for nonwear overlap calculations.
    Returns None when data is unavailable to distinguish from "calculated as 0".

    Args:
        nonwear_array: Binary array (0/1) indicating nonwear epochs
        onset_idx: Sleep onset epoch index
        offset_idx: Sleep offset epoch index

    Returns:
        Count of nonwear minutes (sum of 1s), or None if data unavailable

    """
    if not nonwear_array or onset_idx is None or offset_idx is None:
        return None if not nonwear_array else 0

    if offset_idx >= len(nonwear_array):
        return None

    return sum(nonwear_array[onset_idx : offset_idx + 1])
