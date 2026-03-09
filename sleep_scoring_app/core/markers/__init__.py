"""
Marker protocols and base classes.

This module provides abstractions for marker handling through dependency inversion,
enabling consistent behavior between sleep markers and nonwear markers.
"""

from sleep_scoring_app.core.markers.persistence import (
    NonwearMarkerPersistence,
    SleepMarkerPersistence,
    UnifiedMarkerHandler,
)
from sleep_scoring_app.core.markers.protocol import (
    DailyMarkersBase,
    DailyMarkersProtocol,
    MarkerChangeHandler,
    MarkerPeriod,
    MarkerPeriodBase,
    MarkerPersistence,
)

__all__ = [
    # Protocols
    "DailyMarkersBase",
    "DailyMarkersProtocol",
    "MarkerChangeHandler",
    "MarkerPeriod",
    "MarkerPeriodBase",
    "MarkerPersistence",
    # Concrete implementations
    "NonwearMarkerPersistence",
    "SleepMarkerPersistence",
    "UnifiedMarkerHandler",
]
