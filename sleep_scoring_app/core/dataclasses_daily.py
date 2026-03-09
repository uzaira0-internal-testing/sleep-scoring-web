#!/usr/bin/env python3
"""
Daily data container structures for unified sleep and nonwear data management.

This module defines the proper data hierarchy:
Study → Participant → Date → (Sleep+Nonwear Markers) → Period → Metrics

Key Design Principles:
1. DailyData contains BOTH sleep_markers AND nonwear_markers
2. Nonwear is a first-class citizen, not an afterthought
3. Metrics are PER-PERIOD, NOT per-date (accessed via period.metrics)
4. DailyData provides single source of truth for all daily data

Export Design:
- export_sleep_rows() and export_nonwear_rows() return generic dicts with string keys
- The export service layer maps these to ExportColumn enums for CSV export
- This separation keeps dataclasses independent of export format details
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.dataclasses_markers import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    SleepPeriod,
)

if TYPE_CHECKING:
    from datetime import date


@dataclass
class DailyData:
    """
    Container for all markers and data for a single sleep_date.

    Holds BOTH sleep markers AND nonwear markers, establishing nonwear as a
    first-class citizen in the data structure.

    CRITICAL: Metrics are stored PER-PERIOD, NOT at the daily level.
    Access metrics via:
    - period.metrics (if stored on period object)
    - Calculate from period timestamps and activity data
    - Retrieve from SleepMetrics object (legacy pattern)

    Attributes:
        sleep_date: The sleep date (calendar date of the night)
        filename: Source filename for this date's data
        sleep_markers: Sleep period markers (onset/offset times)
        nonwear_markers: Nonwear period markers (manual NWT periods)
        is_validated: Whether markers have been validated
        validation_warnings: List of validation warning messages

    """

    sleep_date: date
    filename: str
    sleep_markers: DailySleepMarkers = field(default_factory=DailySleepMarkers)
    nonwear_markers: DailyNonwearMarkers = field(default_factory=DailyNonwearMarkers)
    is_validated: bool = False
    validation_warnings: list[str] = field(default_factory=list)

    def get_complete_sleep_periods(self) -> list[SleepPeriod]:
        """Get all complete sleep periods for this date."""
        return self.sleep_markers.get_complete_periods()

    def has_complete_sleep_period(self) -> bool:
        """Check if at least one complete sleep period exists."""
        return len(self.get_complete_sleep_periods()) > 0

    def has_nonwear_overlap(self) -> bool:
        """Check if any nonwear periods exist for this date."""
        return len(self.nonwear_markers.get_complete_periods()) > 0

    def get_main_sleep_period(self) -> SleepPeriod | None:
        """Get the main sleep period (longest duration)."""
        return self.sleep_markers.get_main_sleep()

    def get_nap_periods(self) -> list[SleepPeriod]:
        """Get all nap periods (non-main sleep)."""
        return self.sleep_markers.get_naps()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "sleep_date": self.sleep_date.isoformat(),
            "filename": self.filename,
            "sleep_markers": self.sleep_markers.to_dict(),
            "nonwear_markers": self.nonwear_markers.to_dict(),
            "is_validated": self.is_validated,
            "validation_warnings": self.validation_warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DailyData:
        """Create from dictionary data."""
        from datetime import date as date_type

        return cls(
            sleep_date=date_type.fromisoformat(data["sleep_date"]),
            filename=data.get("filename", ""),
            sleep_markers=DailySleepMarkers.from_dict(data.get("sleep_markers", {})),
            nonwear_markers=DailyNonwearMarkers.from_dict(data.get("nonwear_markers", {})),
            is_validated=data.get("is_validated", False),
            validation_warnings=data.get("validation_warnings", []),
        )


@dataclass
class ParticipantData:
    """
    Container for all daily data for a single participant.

    Holds multiple DailyData objects keyed by sleep_date, providing
    a complete view of all marker data for the participant.

    Attributes:
        participant_id: Numerical participant ID (e.g., "1234")
        full_id: Full participant ID (e.g., "1234 BO G1")
        group: Participant group (e.g., "G1")
        timepoint: Participant timepoint (e.g., "T1")
        daily_data: Dictionary of DailyData keyed by sleep_date

    """

    participant_id: str
    full_id: str
    group: str
    timepoint: str
    daily_data: dict[date, DailyData] = field(default_factory=dict)

    def get_dates_with_data(self) -> list[date]:
        """Get all dates with daily data, sorted chronologically."""
        return sorted(self.daily_data.keys())

    def get_dates_with_complete_sleep(self) -> list[date]:
        """Get dates that have at least one complete sleep period."""
        return [d for d, data in self.daily_data.items() if data.has_complete_sleep_period()]

    def get_dates_with_incomplete_sleep(self) -> list[date]:
        """Get dates that have no complete sleep periods."""
        return [d for d, data in self.daily_data.items() if not data.has_complete_sleep_period()]

    def get_dates_with_nonwear(self) -> list[date]:
        """Get dates that have nonwear periods."""
        return [d for d, data in self.daily_data.items() if data.has_nonwear_overlap()]

    def add_daily_data(self, sleep_date: date, daily_data: DailyData) -> None:
        """Add or update daily data for a specific date."""
        self.daily_data[sleep_date] = daily_data

    def get_daily_data(self, sleep_date: date) -> DailyData | None:
        """Get daily data for a specific date."""
        return self.daily_data.get(sleep_date)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "participant_id": self.participant_id,
            "full_id": self.full_id,
            "group": self.group,
            "timepoint": self.timepoint,
            "daily_data": {d.isoformat(): data.to_dict() for d, data in self.daily_data.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParticipantData:
        """Create from dictionary data."""
        from datetime import date as date_type

        daily_data = {date_type.fromisoformat(d): DailyData.from_dict(dd) for d, dd in data.get("daily_data", {}).items()}

        return cls(
            participant_id=data["participant_id"],
            full_id=data["full_id"],
            group=data["group"],
            timepoint=data["timepoint"],
            daily_data=daily_data,
        )


@dataclass
class StudyData:
    """
    Container for all participant data in a study.

    Provides study-level view with iteration helpers for exporting
    sleep and nonwear data separately.

    Attributes:
        study_name: Name of the study
        participants: Dictionary of ParticipantData keyed by participant_id

    """

    study_name: str
    participants: dict[str, ParticipantData] = field(default_factory=dict)

    def add_participant(self, participant_data: ParticipantData) -> None:
        """Add or update participant data."""
        self.participants[participant_data.participant_id] = participant_data

    def get_participant(self, participant_id: str) -> ParticipantData | None:
        """Get participant data by ID."""
        return self.participants.get(participant_id)

    def all_daily_data(self) -> list[tuple[str, date, DailyData]]:
        """
        Iterate over all daily data across all participants.

        Yields:
            Tuples of (participant_id, sleep_date, daily_data)

        """
        result = []
        for participant_id, participant_data in self.participants.items():
            for sleep_date, daily_data in participant_data.daily_data.items():
                result.append((participant_id, sleep_date, daily_data))
        return result

    def export_sleep_rows(self) -> list[dict[str, Any]]:
        """
        Generate export rows for sleep periods across all participants.

        Returns one row per complete sleep period with participant info,
        date, and period details.

        Returns:
            List of dictionaries ready for CSV export

        """
        rows = []
        for participant_id, sleep_date, daily_data in self.all_daily_data():
            participant_data = self.participants[participant_id]

            for period in daily_data.get_complete_sleep_periods():
                rows.append(
                    {
                        "participant_id": participant_id,
                        "full_id": participant_data.full_id,
                        "group": participant_data.group,
                        "timepoint": participant_data.timepoint,
                        "sleep_date": sleep_date.isoformat(),
                        "filename": daily_data.filename,
                        "marker_type": period.marker_type.value if period.marker_type else None,
                        "marker_index": period.marker_index,
                        "onset_timestamp": period.onset_timestamp,
                        "offset_timestamp": period.offset_timestamp,
                        "duration_minutes": period.duration_minutes,
                    }
                )

        return rows

    def export_nonwear_rows(self) -> list[dict[str, Any]]:
        """
        Generate export rows for nonwear periods across all participants.

        Returns one row per complete nonwear period with participant info,
        date, and period details.

        Returns:
            List of dictionaries ready for CSV export

        """
        rows = []
        for participant_id, sleep_date, daily_data in self.all_daily_data():
            participant_data = self.participants[participant_id]

            for period in daily_data.nonwear_markers.get_complete_periods():
                rows.append(
                    {
                        "participant_id": participant_id,
                        "full_id": participant_data.full_id,
                        "group": participant_data.group,
                        "timepoint": participant_data.timepoint,
                        "sleep_date": sleep_date.isoformat(),
                        "filename": daily_data.filename,
                        "marker_index": period.marker_index,
                        "start_timestamp": period.start_timestamp,
                        "end_timestamp": period.end_timestamp,
                        "duration_minutes": period.duration_minutes,
                    }
                )

        return rows

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage/serialization."""
        return {
            "study_name": self.study_name,
            "participants": {pid: p.to_dict() for pid, p in self.participants.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StudyData:
        """Create from dictionary data."""
        participants = {pid: ParticipantData.from_dict(p) for pid, p in data.get("participants", {}).items()}

        return cls(
            study_name=data["study_name"],
            participants=participants,
        )


__all__ = [
    "DailyData",
    "ParticipantData",
    "StudyData",
]
