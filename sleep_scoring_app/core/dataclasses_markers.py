#!/usr/bin/env python3
"""Marker-related dataclasses for sleep and nonwear periods."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

from sleep_scoring_app.core.constants import (
    AlgorithmType,
    DatabaseColumn,
    ExportColumn,
    MarkerLimits,
    MarkerType,
    NonwearDataSource,
)

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import ParticipantInfo


def _first_non_none(data: dict[str, Any], *keys: str) -> Any:
    """Return first non-None value found for given keys, or None."""
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return None


@dataclass
class SleepPeriod:
    """Individual sleep period with extended marker support."""

    onset_timestamp: float | None = None
    offset_timestamp: float | None = None
    marker_index: int = 1
    marker_type: MarkerType = MarkerType.MAIN_SLEEP

    @property
    def is_complete(self) -> bool:
        """Check if both markers are set."""
        return self.onset_timestamp is not None and self.offset_timestamp is not None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.is_complete and self.offset_timestamp is not None and self.onset_timestamp is not None:
            return self.offset_timestamp - self.onset_timestamp
        return None

    @property
    def duration_minutes(self) -> float | None:
        """Calculate duration in minutes."""
        if self.duration_seconds is not None:
            return self.duration_seconds / 60
        return None

    @property
    def duration_hours(self) -> float | None:
        """Calculate duration in hours."""
        if self.duration_seconds is not None:
            return self.duration_seconds / 3600
        return None

    # Protocol-compliant aliases for MarkerPeriod interface
    @property
    def start_timestamp(self) -> float | None:
        """Alias for onset_timestamp (MarkerPeriod protocol compliance)."""
        return self.onset_timestamp

    @property
    def end_timestamp(self) -> float | None:
        """Alias for offset_timestamp (MarkerPeriod protocol compliance)."""
        return self.offset_timestamp

    def to_list(self) -> list[float]:
        """Convert to list format for compatibility."""
        if self.is_complete and self.onset_timestamp is not None and self.offset_timestamp is not None:
            return [self.onset_timestamp, self.offset_timestamp]
        return []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "onset_timestamp": self.onset_timestamp,
            "offset_timestamp": self.offset_timestamp,
            "marker_index": self.marker_index,
            "marker_type": self.marker_type.value if self.marker_type else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SleepPeriod:
        """Create from dictionary data."""
        from sleep_scoring_app.core.constants import MarkerType

        # Validate marker_type enum with fallback
        marker_type = MarkerType.MAIN_SLEEP
        if data.get("marker_type"):
            try:
                marker_type = MarkerType(data["marker_type"])
            except ValueError:
                pass  # Use default MAIN_SLEEP

        return cls(
            onset_timestamp=data.get("onset_timestamp"),
            offset_timestamp=data.get("offset_timestamp"),
            marker_index=data.get("marker_index", 1),
            marker_type=marker_type,
        )


@dataclass
class NonwearPeriod:
    """
    Represents a single nonwear or wear period.

    Used by both the Choi algorithm output and nonwear sensor data processing.
    """

    start_time: datetime
    end_time: datetime
    participant_id: str
    source: NonwearDataSource
    duration_minutes: int | None = None
    start_index: int | None = None
    end_index: int | None = None

    def __post_init__(self) -> None:
        """Ensure timestamps are datetime objects for consistent comparisons."""
        self.start_time = self._parse_datetime(self.start_time)
        self.end_time = self._parse_datetime(self.end_time)

    @staticmethod
    def _parse_datetime(timestamp: str | datetime) -> datetime:
        """Parse timestamp to datetime object."""
        if isinstance(timestamp, datetime):
            return timestamp
        return datetime.fromisoformat(str(timestamp))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            DatabaseColumn.START_TIME: self.start_time.isoformat() if isinstance(self.start_time, datetime) else str(self.start_time),
            DatabaseColumn.END_TIME: self.end_time.isoformat() if isinstance(self.end_time, datetime) else str(self.end_time),
            DatabaseColumn.PARTICIPANT_ID: self.participant_id,
            DatabaseColumn.PERIOD_TYPE: self.source,
            DatabaseColumn.DURATION_MINUTES: self.duration_minutes,
            DatabaseColumn.START_INDEX: self.start_index,
            DatabaseColumn.END_INDEX: self.end_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NonwearPeriod:
        """Create from dictionary data."""
        start_time = data.get(DatabaseColumn.START_TIME) or data.get("start_time")
        end_time = data.get(DatabaseColumn.END_TIME) or data.get("end_time")
        if start_time is None or end_time is None:
            msg = "NonwearPeriod requires both start_time and end_time"
            raise ValueError(msg)
        return cls(
            start_time=start_time,
            end_time=end_time,
            participant_id=_first_non_none(data, DatabaseColumn.PARTICIPANT_ID, "participant_id") or "",
            source=NonwearDataSource(_first_non_none(data, DatabaseColumn.PERIOD_TYPE, "source") or NonwearDataSource.MANUAL_NWT),
            duration_minutes=_first_non_none(data, DatabaseColumn.DURATION_MINUTES, "duration_minutes"),
            start_index=_first_non_none(data, DatabaseColumn.START_INDEX, "start_index"),
            end_index=_first_non_none(data, DatabaseColumn.END_INDEX, "end_index"),
        )


@dataclass
class DailySleepMarkers:
    """Daily sleep markers with automatic main sleep/nap classification."""

    period_1: SleepPeriod | None = None
    period_2: SleepPeriod | None = None
    period_3: SleepPeriod | None = None
    period_4: SleepPeriod | None = None

    def get_all_periods(self) -> list[SleepPeriod]:
        """Get all non-None sleep periods."""
        return [p for p in [self.period_1, self.period_2, self.period_3, self.period_4] if p is not None]

    def get_complete_periods(self) -> list[SleepPeriod]:
        """Get all complete sleep periods."""
        return [p for p in self.get_all_periods() if p.is_complete]

    def get_main_sleep(self) -> SleepPeriod | None:
        """
        Get the longest sleep period (main sleep).

        Tie-breaking: When multiple periods have identical duration,
        the one with the earliest onset_timestamp wins.
        """
        complete_periods = self.get_complete_periods()
        if not complete_periods:
            return None
        # Primary sort: longest duration (descending via negation in min)
        # Secondary sort: earliest onset (ascending, so negate to use with max)
        # Using tuple comparison: (duration, -onset) where higher is "better"
        return max(
            complete_periods,
            key=lambda p: (p.duration_seconds or 0, -(p.onset_timestamp or float("inf"))),
        )

    def get_naps(self) -> list[SleepPeriod]:
        """Get all non-main sleep periods (naps)."""
        main_sleep = self.get_main_sleep()
        if main_sleep is None:
            return []
        return [p for p in self.get_complete_periods() if p is not main_sleep]

    def update_classifications(self) -> None:
        """Update marker type classifications based on duration."""
        main_sleep = self.get_main_sleep()
        for period in self.get_complete_periods():
            period.marker_type = MarkerType.MAIN_SLEEP if period is main_sleep else MarkerType.NAP

    def check_duration_tie(self) -> bool:
        """Check if there are periods with identical durations."""
        complete_periods = self.get_complete_periods()
        if len(complete_periods) < 2:
            return False
        durations = [p.duration_seconds for p in complete_periods]
        return len(durations) != len(set(durations))

    def count_periods(self) -> int:
        """Count number of defined periods."""
        return len(self.get_all_periods())

    def get_marker_count(self) -> int:
        """Return the total number of complete sleep periods (main sleep + naps)."""
        return len(self.get_complete_periods())

    def has_space_for_new_period(self) -> bool:
        """Check if we can add another period."""
        return self.count_periods() < MarkerLimits.MAX_SLEEP_PERIODS_PER_DAY

    def get_period_by_slot(self, slot: int) -> SleepPeriod | None:
        """Get period by slot number (1, 2, 3, or 4)."""
        if slot == 1:
            return self.period_1
        if slot == 2:
            return self.period_2
        if slot == 3:
            return self.period_3
        if slot == 4:
            return self.period_4
        return None

    def set_period_by_slot(self, slot: int, period: SleepPeriod | None) -> None:
        """Set period by slot number (1, 2, 3, or 4)."""
        if slot == 1:
            self.period_1 = period
        elif slot == 2:
            self.period_2 = period
        elif slot == 3:
            self.period_3 = period
        elif slot == 4:
            self.period_4 = period

    def remove_period_by_slot(self, slot: int) -> None:
        """Remove a period by slot number."""
        self.set_period_by_slot(slot, None)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "period_1": self.period_1.to_dict() if self.period_1 else None,
            "period_2": self.period_2.to_dict() if self.period_2 else None,
            "period_3": self.period_3.to_dict() if self.period_3 else None,
            "period_4": self.period_4.to_dict() if self.period_4 else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailySleepMarkers:
        """Create from dictionary data."""
        return cls(
            period_1=SleepPeriod.from_dict(data["period_1"]) if data.get("period_1") else None,
            period_2=SleepPeriod.from_dict(data["period_2"]) if data.get("period_2") else None,
            period_3=SleepPeriod.from_dict(data["period_3"]) if data.get("period_3") else None,
            period_4=SleepPeriod.from_dict(data["period_4"]) if data.get("period_4") else None,
        )


@dataclass
class ManualNonwearPeriod:
    """
    Individual manual nonwear period with timestamps.

    Similar to SleepPeriod but for user-placed nonwear markers.
    Uses dashed lines to distinguish from algorithmic nonwear.
    """

    start_timestamp: float | None = None
    end_timestamp: float | None = None
    marker_index: int = 1

    @property
    def is_complete(self) -> bool:
        """Check if both markers are set."""
        return self.start_timestamp is not None and self.end_timestamp is not None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.is_complete and self.start_timestamp is not None and self.end_timestamp is not None:
            return self.end_timestamp - self.start_timestamp
        return None

    @property
    def duration_minutes(self) -> float | None:
        """Calculate duration in minutes."""
        if self.duration_seconds is not None:
            return self.duration_seconds / 60
        return None

    def to_list(self) -> list[float]:
        """Convert to list format for compatibility."""
        if self.is_complete and self.start_timestamp is not None and self.end_timestamp is not None:
            return [self.start_timestamp, self.end_timestamp]
        return []

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "start_timestamp": self.start_timestamp,
            "end_timestamp": self.end_timestamp,
            "marker_index": self.marker_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ManualNonwearPeriod:
        """Create from dictionary data."""
        return cls(
            start_timestamp=data.get("start_timestamp"),
            end_timestamp=data.get("end_timestamp"),
            marker_index=data.get("marker_index", 1),
        )


@dataclass
class DailyNonwearMarkers:
    """
    Daily manual nonwear markers container with 10 period slots.

    Follows the same fixed-slot pattern as DailySleepMarkers for consistency.
    Supports up to 10 user-placed nonwear periods per sleep_date.
    """

    period_1: ManualNonwearPeriod | None = None
    period_2: ManualNonwearPeriod | None = None
    period_3: ManualNonwearPeriod | None = None
    period_4: ManualNonwearPeriod | None = None
    period_5: ManualNonwearPeriod | None = None
    period_6: ManualNonwearPeriod | None = None
    period_7: ManualNonwearPeriod | None = None
    period_8: ManualNonwearPeriod | None = None
    period_9: ManualNonwearPeriod | None = None
    period_10: ManualNonwearPeriod | None = None

    def get_all_periods(self) -> list[ManualNonwearPeriod]:
        """Get all non-None nonwear periods."""
        periods = [
            self.period_1,
            self.period_2,
            self.period_3,
            self.period_4,
            self.period_5,
            self.period_6,
            self.period_7,
            self.period_8,
            self.period_9,
            self.period_10,
        ]
        return [p for p in periods if p is not None]

    def get_complete_periods(self) -> list[ManualNonwearPeriod]:
        """Get all complete nonwear periods (both start and end set)."""
        return [p for p in self.get_all_periods() if p.is_complete]

    def count_periods(self) -> int:
        """Count number of defined periods."""
        return len(self.get_all_periods())

    def get_marker_count(self) -> int:
        """Return the total number of complete nonwear periods."""
        return len(self.get_complete_periods())

    def __len__(self) -> int:
        """Return the total number of periods (for len() support)."""
        return self.count_periods()

    def has_space_for_new_period(self) -> bool:
        """Check if we can add another period."""
        return self.count_periods() < MarkerLimits.MAX_NONWEAR_PERIODS_PER_DAY

    def get_next_available_slot(self) -> int | None:
        """Get the next available slot number (1-10), or None if full."""
        for i in range(1, 11):
            if self.get_period_by_slot(i) is None:
                return i
        return None

    def get_period_by_slot(self, slot: int) -> ManualNonwearPeriod | None:
        """Get period by slot number (1-10)."""
        slot_map = {
            1: self.period_1,
            2: self.period_2,
            3: self.period_3,
            4: self.period_4,
            5: self.period_5,
            6: self.period_6,
            7: self.period_7,
            8: self.period_8,
            9: self.period_9,
            10: self.period_10,
        }
        return slot_map.get(slot)

    def set_period_by_slot(self, slot: int, period: ManualNonwearPeriod | None) -> None:
        """Set period by slot number (1-10)."""
        if slot == 1:
            self.period_1 = period
        elif slot == 2:
            self.period_2 = period
        elif slot == 3:
            self.period_3 = period
        elif slot == 4:
            self.period_4 = period
        elif slot == 5:
            self.period_5 = period
        elif slot == 6:
            self.period_6 = period
        elif slot == 7:
            self.period_7 = period
        elif slot == 8:
            self.period_8 = period
        elif slot == 9:
            self.period_9 = period
        elif slot == 10:
            self.period_10 = period

    def remove_period_by_slot(self, slot: int) -> None:
        """Remove a period by slot number."""
        self.set_period_by_slot(slot, None)

    def check_overlap(self, new_start: float, new_end: float, exclude_slot: int | None = None) -> bool:
        """
        Check if a new period would overlap with existing periods.

        Args:
            new_start: Start timestamp of new period
            new_end: End timestamp of new period
            exclude_slot: Slot to exclude from check (for editing existing period)

        Returns:
            True if overlap detected, False otherwise

        """
        for i in range(1, 11):
            if exclude_slot is not None and i == exclude_slot:
                continue
            period = self.get_period_by_slot(i)
            if period and period.is_complete and period.start_timestamp is not None and period.end_timestamp is not None:
                # Check for overlap: not (new_end <= existing_start or new_start >= existing_end)
                if not (new_end <= period.start_timestamp or new_start >= period.end_timestamp):
                    return True
        return False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "period_1": self.period_1.to_dict() if self.period_1 else None,
            "period_2": self.period_2.to_dict() if self.period_2 else None,
            "period_3": self.period_3.to_dict() if self.period_3 else None,
            "period_4": self.period_4.to_dict() if self.period_4 else None,
            "period_5": self.period_5.to_dict() if self.period_5 else None,
            "period_6": self.period_6.to_dict() if self.period_6 else None,
            "period_7": self.period_7.to_dict() if self.period_7 else None,
            "period_8": self.period_8.to_dict() if self.period_8 else None,
            "period_9": self.period_9.to_dict() if self.period_9 else None,
            "period_10": self.period_10.to_dict() if self.period_10 else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyNonwearMarkers:
        """Create from dictionary data."""
        return cls(
            period_1=ManualNonwearPeriod.from_dict(data["period_1"]) if data.get("period_1") else None,
            period_2=ManualNonwearPeriod.from_dict(data["period_2"]) if data.get("period_2") else None,
            period_3=ManualNonwearPeriod.from_dict(data["period_3"]) if data.get("period_3") else None,
            period_4=ManualNonwearPeriod.from_dict(data["period_4"]) if data.get("period_4") else None,
            period_5=ManualNonwearPeriod.from_dict(data["period_5"]) if data.get("period_5") else None,
            period_6=ManualNonwearPeriod.from_dict(data["period_6"]) if data.get("period_6") else None,
            period_7=ManualNonwearPeriod.from_dict(data["period_7"]) if data.get("period_7") else None,
            period_8=ManualNonwearPeriod.from_dict(data["period_8"]) if data.get("period_8") else None,
            period_9=ManualNonwearPeriod.from_dict(data["period_9"]) if data.get("period_9") else None,
            period_10=ManualNonwearPeriod.from_dict(data["period_10"]) if data.get("period_10") else None,
        )


@dataclass
class SleepMetrics:
    """
    Complete sleep metrics for a single analysis date.

    Contains all calculated sleep quality metrics, algorithm outputs,
    and participant/file metadata. Used for database storage and export.

    The top-level fields (onset_time, total_sleep_time, etc.) represent
    the main sleep period's metrics. Per-period metrics (for multi-period
    days with naps) are stored in ``_dynamic_fields`` using keys of the
    form ``period_{marker_index}_metrics``, populated by
    ``store_period_metrics()`` and loaded from the database by
    ``_load_period_metrics_for_sleep_metrics()``.
    """

    # Use string annotation to avoid circular import
    participant: ParticipantInfo
    filename: str
    analysis_date: str
    algorithm_type: AlgorithmType = AlgorithmType.SADEH_1994_ACTILIFE
    daily_sleep_markers: DailySleepMarkers = field(default_factory=DailySleepMarkers)

    # Time strings for display
    onset_time: str = ""
    offset_time: str = ""

    # Core sleep metrics
    total_sleep_time: int | None = None
    sleep_efficiency: float | None = None
    total_minutes_in_bed: int | None = None
    waso: int | None = None
    awakenings: int | None = None
    average_awakening_length: float | None = None

    # Activity metrics
    total_activity: int | None = None
    movement_index: float | None = None
    fragmentation_index: float | None = None
    sleep_fragmentation_index: float | None = None

    # Algorithm values at markers
    sleep_algorithm_onset: int | None = None
    sleep_algorithm_offset: int | None = None

    # Nonwear overlap
    overlapping_nonwear_minutes_algorithm: int | None = None
    overlapping_nonwear_minutes_sensor: int | None = None

    # Additional algorithm metadata (for batch scoring)
    sleep_algorithm_name: str | None = None
    sleep_period_detector_id: str | None = None

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    # Consensus review flag
    needs_consensus: bool = False  # Flag for dates needing consensus review

    # Dynamic fields for period-level metrics (populated by repository)
    _dynamic_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for database storage."""
        return {
            "participant": self.participant.numerical_id if self.participant else None,
            "participant_group": self.participant.group_str if self.participant else None,
            "participant_timepoint": self.participant.timepoint_str if self.participant else None,
            "filename": self.filename,
            "analysis_date": self.analysis_date,
            "algorithm_type": self.algorithm_type.value if self.algorithm_type else None,
            "daily_sleep_markers": self.daily_sleep_markers.to_dict() if self.daily_sleep_markers else None,
            "onset_time": self.onset_time,
            "offset_time": self.offset_time,
            "total_sleep_time": self.total_sleep_time,
            "sleep_efficiency": self.sleep_efficiency,
            "total_minutes_in_bed": self.total_minutes_in_bed,
            "waso": self.waso,
            "awakenings": self.awakenings,
            "average_awakening_length": self.average_awakening_length,
            "total_activity": self.total_activity,
            "movement_index": self.movement_index,
            "fragmentation_index": self.fragmentation_index,
            "sleep_fragmentation_index": self.sleep_fragmentation_index,
            "sleep_algorithm_onset": self.sleep_algorithm_onset,
            "sleep_algorithm_offset": self.sleep_algorithm_offset,
            "overlapping_nonwear_minutes_algorithm": self.overlapping_nonwear_minutes_algorithm,
            "overlapping_nonwear_minutes_sensor": self.overlapping_nonwear_minutes_sensor,
            "sleep_algorithm_name": self.sleep_algorithm_name,
            "sleep_period_detector_id": self.sleep_period_detector_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "needs_consensus": self.needs_consensus,
            **self._dynamic_fields,
        }

    def to_export_dict(self) -> dict[str, Any]:
        """Convert to dictionary for CSV/JSON export with display-friendly keys."""
        # Build full participant ID from components using spaces (matching extract_participant_info format)
        full_participant_id = None
        if self.participant:
            parts = [self.participant.numerical_id]
            if self.participant.timepoint_str:
                parts.append(self.participant.timepoint_str)
            if self.participant.group_str:
                parts.append(self.participant.group_str)
            full_participant_id = " ".join(filter(None, parts))

        return {
            ExportColumn.FULL_PARTICIPANT_ID: full_participant_id,
            ExportColumn.NUMERICAL_PARTICIPANT_ID: self.participant.numerical_id if self.participant else None,
            ExportColumn.PARTICIPANT_GROUP: self.participant.group_str if self.participant else None,
            ExportColumn.PARTICIPANT_TIMEPOINT: self.participant.timepoint_str if self.participant else None,
            "filename": self.filename,
            ExportColumn.SLEEP_DATE: self.analysis_date,
            ExportColumn.ONSET_DATE: self.analysis_date,
            ExportColumn.SLEEP_ALGORITHM: self.algorithm_type.value if self.algorithm_type else None,
            ExportColumn.ONSET_OFFSET_RULE: self.sleep_period_detector_id,
            ExportColumn.ONSET_TIME: self.onset_time,
            ExportColumn.OFFSET_TIME: self.offset_time,
            ExportColumn.TOTAL_SLEEP_TIME: self.total_sleep_time,
            ExportColumn.EFFICIENCY: self.sleep_efficiency,
            ExportColumn.TOTAL_MINUTES_IN_BED: self.total_minutes_in_bed,
            ExportColumn.WASO: self.waso,
            ExportColumn.NUMBER_OF_AWAKENINGS: self.awakenings,
            ExportColumn.AVERAGE_AWAKENING_LENGTH: self.average_awakening_length,
            ExportColumn.TOTAL_COUNTS: self.total_activity,
            ExportColumn.MOVEMENT_INDEX: self.movement_index,
            ExportColumn.FRAGMENTATION_INDEX: self.fragmentation_index,
            ExportColumn.SLEEP_FRAGMENTATION_INDEX: self.sleep_fragmentation_index,
            ExportColumn.SLEEP_ALGORITHM_ONSET: self.sleep_algorithm_onset,
            ExportColumn.SLEEP_ALGORITHM_OFFSET: self.sleep_algorithm_offset,
            ExportColumn.OVERLAPPING_NONWEAR_MINUTES_ALGORITHM: self.overlapping_nonwear_minutes_algorithm,
            ExportColumn.OVERLAPPING_NONWEAR_MINUTES_SENSOR: self.overlapping_nonwear_minutes_sensor,
            ExportColumn.NEEDS_CONSENSUS: self.needs_consensus,
            ExportColumn.SAVED_AT: self.updated_at,
            **self._dynamic_fields,
        }

    def to_export_dict_list(self) -> list[dict[str, Any]]:
        """Convert to list of export dictionaries, one per complete sleep period."""
        complete_periods = self.daily_sleep_markers.get_complete_periods()

        if not complete_periods:
            # Return single row with empty period data if no complete periods
            return [self.to_export_dict()]

        # One row per complete period
        rows = []
        for period in complete_periods:
            row = self.to_export_dict()
            row[ExportColumn.MARKER_INDEX] = period.marker_index
            row[ExportColumn.MARKER_TYPE] = period.marker_type.value if period.marker_type else None

            # Override onset/offset with period-specific values
            if period.onset_timestamp is not None:
                onset_dt = datetime.fromtimestamp(period.onset_timestamp)
                row[ExportColumn.ONSET_TIME] = onset_dt.strftime("%H:%M")
                row[ExportColumn.ONSET_DATE] = onset_dt.strftime("%Y-%m-%d")

            if period.offset_timestamp is not None:
                offset_dt = datetime.fromtimestamp(period.offset_timestamp)
                row[ExportColumn.OFFSET_TIME] = offset_dt.strftime("%H:%M")
                row[ExportColumn.OFFSET_DATE] = offset_dt.strftime("%Y-%m-%d")

            # Get period-specific metrics using marker_index as key
            # CRITICAL: Must match the key used in store_period_metrics() and
            # _load_period_metrics_for_sleep_metrics() to ensure consistency
            period_key = f"period_{period.marker_index}_metrics"
            if period_key in self._dynamic_fields:
                row.update(self._dynamic_fields[period_key])

            rows.append(row)

        return rows

    def set_dynamic_field(self, key: str, value: Any) -> None:
        """Set a dynamic field value."""
        self._dynamic_fields[key] = value

    def get_dynamic_field(self, key: str, default: Any = None) -> Any:
        """Get a dynamic field value."""
        return self._dynamic_fields.get(key, default)

    def store_period_metrics(self, period: SleepPeriod, metrics_dict: dict[str, Any]) -> None:
        """
        Store metrics for a specific sleep period.

        Uses marker_index as the storage key to ensure consistency with:
        - to_export_dict_list() which retrieves using marker_index
        - _load_period_metrics_for_sleep_metrics() which loads from DB using marker_index

        Args:
            period: The SleepPeriod to store metrics for
            metrics_dict: Dictionary of metric values to store

        """
        # Use marker_index directly as the storage key for consistency
        # This matches how DB loading and export retrieval work
        if period.marker_index is not None:
            period_key = f"period_{period.marker_index}_metrics"
            self._dynamic_fields[period_key] = metrics_dict
            logger.debug(
                "Stored metrics for period %d (onset=%s, offset=%s)",
                period.marker_index,
                period.onset_timestamp,
                period.offset_timestamp,
            )
        else:
            # Log warning if marker_index is missing - this shouldn't happen
            # but helps debug if periods aren't set up correctly
            logger.warning(
                "Cannot store metrics: period has no marker_index (onset=%s, offset=%s)",
                period.onset_timestamp,
                period.offset_timestamp,
            )


__all__ = [
    "DailyNonwearMarkers",
    "DailySleepMarkers",
    "ManualNonwearPeriod",
    "NonwearPeriod",
    "SleepMetrics",
    "SleepPeriod",
]
