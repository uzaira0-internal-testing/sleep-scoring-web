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
