#!/usr/bin/env python3
"""
Domain-specific column registries for the sleep scoring application.

This module provides focused registry functions organized by domain:
- metadata_columns: Participant information, import status, data coverage
- sleep_columns: Sleep markers and sleep metrics
- marker_columns: Sleep period markers and marker types
- activity_columns: Activity metrics and algorithm results
- diary_columns: Sleep diary information (naps, nonwear periods)
"""

from __future__ import annotations

from .activity_columns import register_activity_columns
from .diary_columns import register_diary_columns
from .marker_columns import register_marker_columns
from .metadata_columns import register_metadata_columns
from .nonwear_columns import register_nonwear_columns
from .sleep_columns import register_sleep_columns

__all__ = [
    "register_activity_columns",
    "register_diary_columns",
    "register_marker_columns",
    "register_metadata_columns",
    "register_nonwear_columns",
    "register_sleep_columns",
]
