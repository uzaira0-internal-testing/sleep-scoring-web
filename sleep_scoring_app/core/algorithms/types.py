"""
Algorithm type definitions.

This module defines common types and enums used across sleep scoring algorithms.
"""

from __future__ import annotations

from enum import StrEnum


class ActivityColumn(StrEnum):
    """
    Activity data column selection for algorithms.

    This enum specifies which accelerometer data column to use for algorithm processing.
    Different algorithms have different requirements:

    - Sadeh (1994): ALWAYS uses AXIS_Y (vertical axis, hardcoded in the algorithm)
    - Choi (2011): Can use either VECTOR_MAGNITUDE (recommended) or AXIS_Y

    The enum makes column selection explicit and type-safe, preventing errors from
    unclear boolean flags or string literals.

    Attributes:
        AXIS_Y: Y-axis accelerometer data (vertical axis) - Required for Sadeh
        VECTOR_MAGNITUDE: Vector magnitude combining all three axes (X, Y, Z)

    Example:
        >>> from sleep_scoring_app.core.algorithms import choi_detect_nonwear, ActivityColumn
        >>> result = choi_detect_nonwear(df, activity_column=ActivityColumn.VECTOR_MAGNITUDE)

    """

    AXIS_Y = "axis_y"
    VECTOR_MAGNITUDE = "Vector Magnitude"
