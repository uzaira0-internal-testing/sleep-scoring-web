"""Shared utility functions for sleep_scoring_web."""

import calendar
from datetime import datetime


def naive_to_unix(dt: datetime) -> float:
    """
    Convert naive datetime to Unix timestamp WITHOUT timezone interpretation.

    Uses calendar.timegm which treats the datetime as UTC without conversion.
    This ensures that "12:00" in the database displays as "12:00" to the user,
    regardless of server or client timezone.
    """
    return float(calendar.timegm(dt.timetuple()))


def ensure_seconds(ts: float) -> float:
    """
    Normalize a timestamp to seconds.

    The frontend historically sent milliseconds; the v6 Dexie migration
    converted to seconds, but some clients/data may still send ms.
    Timestamps > 1e12 are assumed to be milliseconds.
    """
    if ts > 1e12:
        return ts / 1000
    return ts
