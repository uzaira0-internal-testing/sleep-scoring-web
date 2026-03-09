#!/usr/bin/env python3
"""
Immutable nonwear data structures for clean architecture.
Eliminates timezone conversion issues and provides single source of truth.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sleep_scoring_app.core.algorithms import NonwearAlgorithmFactory
from sleep_scoring_app.core.constants import ActivityDataPreference, NonwearAlgorithm, NonwearDataSource, NonwearSourceFilter

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sleep_scoring_app.core.dataclasses import NonwearPeriod

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ActivityDataView:
    """Immutable view of activity data with defined timeframe."""

    timestamps: tuple[datetime, ...]
    counts: tuple[float, ...]
    filename: str
    start_time: datetime
    end_time: datetime

    @classmethod
    def create(cls, timestamps: list[datetime], counts: list[float], filename: str) -> ActivityDataView:
        """Create ActivityDataView from lists, determining timeframe automatically."""
        if not timestamps or not counts:
            msg = "Activity data cannot be empty"
            raise ValueError(msg)

        if len(timestamps) != len(counts):
            msg = "Timestamps and counts must have same length"
            raise ValueError(msg)

        return cls(timestamps=tuple(timestamps), counts=tuple(counts), filename=filename, start_time=min(timestamps), end_time=max(timestamps))

    @property
    def timeframe_filter(self) -> Callable[[datetime, datetime], bool]:
        """Return function to test if a time period overlaps with this activity data."""
        return lambda start, end: (start <= self.end_time and end >= self.start_time)

    @property
    def duration_hours(self) -> float:
        """Duration of activity data in hours."""
        return (self.end_time - self.start_time).total_seconds() / 3600

    def __len__(self) -> int:
        return len(self.timestamps)


@dataclass(frozen=True)
class NonwearData:
    """Immutable nonwear data aligned with specific activity data."""

    sensor_periods: tuple[NonwearPeriod, ...]
    choi_periods: tuple[NonwearPeriod, ...]
    sensor_mask: tuple[int, ...]
    choi_mask: tuple[int, ...]
    activity_view: ActivityDataView

    @classmethod
    def create_for_activity_view(
        cls,
        activity_view: ActivityDataView,
        raw_sensor_periods: list[NonwearPeriod],
        nonwear_service=None,
        choi_activity_column: ActivityDataPreference = ActivityDataPreference.VECTOR_MAGNITUDE,
    ) -> NonwearData:
        """Create NonwearData from activity view and raw sensor periods."""
        logger.debug("Creating NonwearData for %s with %d raw sensor periods", activity_view.filename, len(raw_sensor_periods))
        logger.debug("Activity data timeframe: %s to %s (%d points)", activity_view.start_time, activity_view.end_time, len(activity_view))

        sensor_periods = []
        for i, period in enumerate(raw_sensor_periods):
            try:
                period_start = period.start_time
                period_end = period.end_time

                logger.debug("Processing sensor period %d: %s to %s", i, period_start, period_end)

                overlaps = activity_view.timeframe_filter(period_start, period_end)
                if not overlaps:
                    logger.debug("Period %d does not overlap with activity timeframe, skipping", i)
                    continue
                sensor_periods.append(period)

            except (ValueError, AttributeError) as e:
                logger.warning("Error parsing sensor period %d timestamps: %s", i, e)
                continue

        logger.debug("Processed %d sensor periods, kept %d after overlap filter", len(raw_sensor_periods), len(sensor_periods))

        choi_periods = cls._compute_choi_periods(activity_view, choi_activity_column)

        sensor_mask = cls._periods_to_mask(sensor_periods, activity_view)
        choi_mask = cls._periods_to_mask(choi_periods, activity_view)

        return cls(
            sensor_periods=tuple(sensor_periods),
            choi_periods=tuple(choi_periods),
            sensor_mask=sensor_mask,
            choi_mask=choi_mask,
            activity_view=activity_view,
        )

    @staticmethod
    def _compute_choi_periods(
        activity_view: ActivityDataView, activity_column: ActivityDataPreference = ActivityDataPreference.VECTOR_MAGNITUDE
    ) -> list[NonwearPeriod]:
        """Compute Choi nonwear periods from activity data."""
        if len(activity_view.counts) == 0:
            return []

        try:
            # Create Choi algorithm instance using factory
            choi_algorithm = NonwearAlgorithmFactory.create(NonwearAlgorithm.CHOI_2011)

            # Use the detect method to get NonwearPeriod objects directly
            periods = choi_algorithm.detect(
                activity_data=list(activity_view.counts), timestamps=list(activity_view.timestamps), activity_column=activity_column
            )

            logger.debug("Computed %d Choi nonwear periods from %d activity points", len(periods), len(activity_view.counts))
            return periods

        except Exception as e:
            logger.warning("Error computing Choi periods: %s", e)
            return []

    @staticmethod
    def _periods_to_mask(periods: list[NonwearPeriod], activity_view: ActivityDataView) -> tuple[int, ...]:
        """Convert nonwear periods to per-minute 0/1 mask."""
        mask = [0] * len(activity_view.timestamps)

        for period in periods:
            start_idx = period.start_index
            end_idx = period.end_index
            if start_idx is not None and end_idx is not None:
                for i in range(max(0, start_idx), min(len(mask), end_idx + 1)):
                    mask[i] = 1
                continue

            try:
                period_start = period.start_time
                period_end = period.end_time

                for i, timestamp in enumerate(activity_view.timestamps):
                    if period_start <= timestamp <= period_end:
                        mask[i] = 1
            except (ValueError, AttributeError) as e:
                logger.warning("Error parsing period timestamps for mask: %s", e)
                continue

        return tuple(mask)

    def get_combined_mask(self, prefer_sensor: bool = True) -> tuple[int, ...]:
        """Get combined nonwear mask with preference logic."""
        if prefer_sensor and self.sensor_periods:
            return self.sensor_mask
        return self.choi_mask

    def get_nonwear_count(self, source: NonwearSourceFilter = NonwearSourceFilter.COMBINED) -> int:
        """Get count of nonwear minutes."""
        if source == NonwearSourceFilter.SENSOR:
            return sum(self.sensor_mask)
        if source == NonwearSourceFilter.CHOI:
            return sum(self.choi_mask)
        return sum(self.get_combined_mask())

    def get_wear_percentage(self, source: NonwearSourceFilter = NonwearSourceFilter.COMBINED) -> float:
        """Get percentage of wear time."""
        if len(self.activity_view) == 0:
            return 0.0
        nonwear_count = self.get_nonwear_count(source)
        return ((len(self.activity_view) - nonwear_count) / len(self.activity_view)) * 100


class NonwearDataFactory:
    """Factory for creating and caching NonwearData objects."""

    def __init__(self, nonwear_service) -> None:
        self.nonwear_service = nonwear_service
        self._cache: dict[str, NonwearData] = {}
        self._lock = threading.Lock()

    def get_nonwear_data(self, activity_view: ActivityDataView) -> NonwearData:
        """Get NonwearData for activity view, using cache when possible."""
        cache_key = self._generate_cache_key(activity_view)

        with self._lock:
            if cache_key not in self._cache:
                logger.debug("Loading nonwear data for file: %s", activity_view.filename)

                raw_sensor_periods = self.nonwear_service.get_nonwear_periods_for_file(
                    filename=activity_view.filename,
                    source=NonwearDataSource.NONWEAR_SENSOR,
                )

                logger.debug("Loaded %d raw sensor periods from database for %s", len(raw_sensor_periods), activity_view.filename)

                self._cache[cache_key] = NonwearData.create_for_activity_view(activity_view, raw_sensor_periods, self.nonwear_service)

                logger.debug("Created and cached NonwearData for %s", cache_key)
            else:
                logger.debug("Using cached NonwearData for %s", cache_key)

            return self._cache[cache_key]

    def _generate_cache_key(self, activity_view: ActivityDataView) -> str:
        """Generate cache key for activity view."""
        return f"{activity_view.filename}_{activity_view.start_time.isoformat()}_{activity_view.end_time.isoformat()}_{len(activity_view)}"

    def clear_cache(self) -> None:
        """Clear all cached nonwear data."""
        with self._lock:
            self._cache.clear()
            logger.debug("Cleared NonwearData cache")

    def clear_cache_for_file(self, filename: str) -> None:
        """Clear cached data for specific file."""
        with self._lock:
            keys_to_remove = [key for key in self._cache if key.startswith(filename)]
            for key in keys_to_remove:
                del self._cache[key]
        logger.debug("Cleared NonwearData cache for file: %s", filename)
