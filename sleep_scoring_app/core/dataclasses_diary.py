#!/usr/bin/env python3
"""Diary-related dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import DatabaseColumn

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class DiaryColumnMapping:
    """Diary column mapping result."""

    participant_id_column_name: str | None = None
    sleep_onset_time_column_name: str | None = None
    sleep_offset_time_column_name: str | None = None
    napped_column_name: str | None = None
    nap_onset_time_column_name: str | None = None
    nap_offset_time_column_name: str | None = None
    nonwear_occurred_column_name: str | None = None
    nonwear_reason_column_names: str | None = None
    nonwear_start_time_column_names: str | None = None
    nonwear_end_time_column_names: str | None = None
    in_bed_time_column_name: str | None = None
    out_of_bed_time_column_name: str | None = None
    date_of_last_night_column_name: str | None = None
    sleep_onset_date_column_name: str | None = None
    sleep_offset_date_column_name: str | None = None
    todays_date_column_name: str | None = None
    nap_onset_date_column_name: str | None = None
    nap_offset_date_column_name: str | None = None
    nap_onset_time_column_names: str | None = None  # For multiple nap columns
    nap_offset_time_column_names: str | None = None  # For multiple nap columns
    diary_completed_for_current_day_column_name: str | None = None
    activity_columns: str | None = None
    expected_diary_entry_date_column_name: str | None = None
    diary_submission_date_column_name: str | None = None
    participant_timepoint_column_name: str | None = None
    participant_group_column_name: str | None = None
    auto_calculated_columns: dict[str, bool] = field(default_factory=dict)
    alternative_column_names: dict[str, list[str]] = field(default_factory=dict)

    def resolve_columns(self, available_columns: list[str]) -> None:
        """
        Resolve column names against actual columns in the data.

        For each field that has alternatives defined, check if the primary column
        exists in the data. If not, try each alternative until one is found.
        Updates the primary column name in-place.
        """
        import logging

        logger = logging.getLogger(__name__)

        # Map of config key → attribute name on this dataclass
        field_map = {
            "sleep_onset_time": "sleep_onset_time_column_name",
            "sleep_offset_time": "sleep_offset_time_column_name",
            "in_bed_time": "in_bed_time_column_name",
            "nap_onset_time": "nap_onset_time_column_name",
            "nap_offset_time": "nap_offset_time_column_name",
        }

        available_set = set(available_columns)

        for alt_key, attr_name in field_map.items():
            current_value = getattr(self, attr_name)
            if current_value and current_value in available_set:
                continue  # Primary column exists, no resolution needed

            alternatives = self.alternative_column_names.get(alt_key, [])
            for alt_name in alternatives:
                if alt_name in available_set:
                    logger.info(
                        "Resolved column '%s': '%s' -> '%s' (found in data)",
                        alt_key,
                        current_value,
                        alt_name,
                    )
                    setattr(self, attr_name, alt_name)
                    break
            else:
                if current_value and current_value not in available_set:
                    logger.warning(
                        "Column '%s' ('%s') not found in data and no alternatives matched. Available columns: %s",
                        alt_key,
                        current_value,
                        sorted(available_set),
                    )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiaryColumnMapping:
        """Create from dictionary data."""
        auto_calc = data.get("auto_calculated_columns", {})
        alt_names = data.get("alternative_column_names", {})

        return cls(
            participant_id_column_name=data.get("participant_id_column_name"),
            sleep_onset_time_column_name=data.get("sleep_onset_time_column_name"),
            sleep_offset_time_column_name=data.get("sleep_offset_time_column_name"),
            napped_column_name=data.get("napped_column_name"),
            nap_onset_time_column_name=data.get("nap_onset_time_column_name"),
            nap_offset_time_column_name=data.get("nap_offset_time_column_name"),
            nonwear_occurred_column_name=data.get("nonwear_occurred_column_name"),
            nonwear_reason_column_names=data.get("nonwear_reason_column_names"),
            nonwear_start_time_column_names=data.get("nonwear_start_time_column_names"),
            nonwear_end_time_column_names=data.get("nonwear_end_time_column_names"),
            in_bed_time_column_name=data.get("in_bed_time_column_name"),
            out_of_bed_time_column_name=data.get("out_of_bed_time_column_name"),
            date_of_last_night_column_name=data.get("date_of_last_night_column_name"),
            sleep_onset_date_column_name=data.get("sleep_onset_date_column_name"),
            sleep_offset_date_column_name=data.get("sleep_offset_date_column_name"),
            todays_date_column_name=data.get("todays_date_column_name"),
            nap_onset_date_column_name=data.get("nap_onset_date_column_name"),
            nap_offset_date_column_name=data.get("nap_offset_date_column_name"),
            nap_onset_time_column_names=data.get("nap_onset_time_column_names"),
            nap_offset_time_column_names=data.get("nap_offset_time_column_names"),
            diary_completed_for_current_day_column_name=data.get("diary_completed_for_current_day_column_name"),
            activity_columns=data.get("activity_columns"),
            expected_diary_entry_date_column_name=data.get("expected_diary_entry_date_column_name"),
            diary_submission_date_column_name=data.get("diary_submission_date_column_name"),
            participant_timepoint_column_name=data.get("participant_timepoint_column_name"),
            participant_group_column_name=data.get("participant_group_column_name"),
            auto_calculated_columns=auto_calc,
            alternative_column_names=alt_names,
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "participant_id_column_name": self.participant_id_column_name,
            "sleep_onset_time_column_name": self.sleep_onset_time_column_name,
            "sleep_offset_time_column_name": self.sleep_offset_time_column_name,
            "napped_column_name": self.napped_column_name,
            "nap_onset_time_column_name": self.nap_onset_time_column_name,
            "nap_offset_time_column_name": self.nap_offset_time_column_name,
            "nonwear_occurred_column_name": self.nonwear_occurred_column_name,
            "nonwear_reason_column_names": self.nonwear_reason_column_names,
            "nonwear_start_time_column_names": self.nonwear_start_time_column_names,
            "nonwear_end_time_column_names": self.nonwear_end_time_column_names,
            "in_bed_time_column_name": self.in_bed_time_column_name,
            "out_of_bed_time_column_name": self.out_of_bed_time_column_name,
            "date_of_last_night_column_name": self.date_of_last_night_column_name,
            "sleep_onset_date_column_name": self.sleep_onset_date_column_name,
            "sleep_offset_date_column_name": self.sleep_offset_date_column_name,
            "todays_date_column_name": self.todays_date_column_name,
            "nap_onset_date_column_name": self.nap_onset_date_column_name,
            "nap_offset_date_column_name": self.nap_offset_date_column_name,
            "nap_onset_time_column_names": self.nap_onset_time_column_names,
            "nap_offset_time_column_names": self.nap_offset_time_column_names,
            "diary_completed_for_current_day_column_name": self.diary_completed_for_current_day_column_name,
            "activity_columns": self.activity_columns,
            "expected_diary_entry_date_column_name": self.expected_diary_entry_date_column_name,
            "diary_submission_date_column_name": self.diary_submission_date_column_name,
            "participant_timepoint_column_name": self.participant_timepoint_column_name,
            "participant_group_column_name": self.participant_group_column_name,
            "auto_calculated_columns": self.auto_calculated_columns,
            "alternative_column_names": self.alternative_column_names,
        }


@dataclass
class DiaryFileInfo:
    """Information about a diary file to be processed."""

    file_path: Path
    file_type: str  # csv, xlsx, xls
    sheet_names: list[str] = field(default_factory=list)
    participant_info: Any = None  # ParticipantInfo | None
    column_mapping: DiaryColumnMapping | None = None
    import_status: str = "pending"
    error_message: str = ""
    total_records: int = 0

    @classmethod
    def from_path(cls, file_path: Path) -> DiaryFileInfo:
        """Create from file path."""
        file_extension = file_path.suffix.lower()

        if file_extension == ".csv":
            file_type = "csv"
            sheet_names = []
        elif file_extension in [".xlsx", ".xls"]:
            file_type = "excel"
            # Sheet names will be populated during processing
            sheet_names = []
        else:
            msg = f"Unsupported file format: {file_extension}"
            raise ValueError(msg)

        return cls(
            file_path=file_path,
            file_type=file_type,
            sheet_names=sheet_names,
        )


@dataclass
class DiaryEntry:
    """Single diary entry record."""

    participant_id: str
    diary_date: str
    filename: str
    # Core sleep timing
    bedtime: str | None = None
    wake_time: str | None = None
    sleep_onset_time: str | None = None
    sleep_offset_time: str | None = None
    in_bed_time: str | None = None

    # Sleep quality and metrics
    sleep_quality: int | None = None

    # Nap information
    nap_occurred: int | None = None  # Number of naps (0-3)
    nap_onset_time: str | None = None
    nap_offset_time: str | None = None
    # Second nap
    nap_onset_time_2: str | None = None
    nap_offset_time_2: str | None = None
    # Third nap
    nap_onset_time_3: str | None = None
    nap_offset_time_3: str | None = None

    # Nonwear information
    nonwear_occurred: bool | None = None
    nonwear_reason: str | None = None
    nonwear_start_time: str | None = None
    nonwear_end_time: str | None = None
    # Additional nonwear periods
    nonwear_reason_2: str | None = None
    nonwear_start_time_2: str | None = None
    nonwear_end_time_2: str | None = None
    nonwear_reason_3: str | None = None
    nonwear_start_time_3: str | None = None
    nonwear_end_time_3: str | None = None

    # Additional metadata
    diary_notes: str | None = None
    night_number: int | None = None

    # Import metadata
    import_date: str = field(default_factory=lambda: datetime.now().isoformat())
    original_column_mapping: str | None = None  # JSON string of original mapping

    @property
    def participant_key(self) -> str:
        """
        Generate composite PARTICIPANT_KEY from participant_id.

        Raises ValueError if participant_id cannot be extracted - this indicates
        a configuration issue where diary participant IDs don't match the
        configured patterns in Study Settings.
        """
        from sleep_scoring_app.utils.participant_extractor import extract_participant_info

        info = extract_participant_info(self.participant_id)

        if info.numerical_id == "UNKNOWN":
            msg = (
                f"Cannot generate participant_key: diary participant_id '{self.participant_id}' "
                f"does not match any configured patterns. "
                f"Check Study Settings -> Participant ID Patterns."
            )
            raise ValueError(msg)

        return info.participant_key

    def to_database_dict(self) -> dict[str, Any]:
        """Convert to database storage format (only columns that exist in diary_data table)."""
        return {
            DatabaseColumn.PARTICIPANT_KEY: self.participant_key,  # Add composite key
            DatabaseColumn.PARTICIPANT_ID: self.participant_id,
            DatabaseColumn.DIARY_DATE: self.diary_date,
            DatabaseColumn.FILENAME: self.filename,
            DatabaseColumn.BEDTIME: self.bedtime,
            DatabaseColumn.WAKE_TIME: self.wake_time,
            DatabaseColumn.SLEEP_ONSET_TIME: self.sleep_onset_time,
            DatabaseColumn.SLEEP_OFFSET_TIME: self.sleep_offset_time,
            DatabaseColumn.IN_BED_TIME: self.in_bed_time,
            DatabaseColumn.SLEEP_QUALITY: self.sleep_quality,
            DatabaseColumn.NAP_OCCURRED: self.nap_occurred,
            DatabaseColumn.NAP_ONSET_TIME: self.nap_onset_time,
            DatabaseColumn.NAP_OFFSET_TIME: self.nap_offset_time,
            DatabaseColumn.NAP_ONSET_TIME_2: self.nap_onset_time_2,
            DatabaseColumn.NAP_OFFSET_TIME_2: self.nap_offset_time_2,
            DatabaseColumn.NAP_ONSET_TIME_3: self.nap_onset_time_3,
            DatabaseColumn.NAP_OFFSET_TIME_3: self.nap_offset_time_3,
            DatabaseColumn.NONWEAR_OCCURRED: self.nonwear_occurred,
            DatabaseColumn.NONWEAR_REASON: self.nonwear_reason,
            DatabaseColumn.NONWEAR_START_TIME: self.nonwear_start_time,
            DatabaseColumn.NONWEAR_END_TIME: self.nonwear_end_time,
            DatabaseColumn.NONWEAR_REASON_2: self.nonwear_reason_2,
            DatabaseColumn.NONWEAR_START_TIME_2: self.nonwear_start_time_2,
            DatabaseColumn.NONWEAR_END_TIME_2: self.nonwear_end_time_2,
            DatabaseColumn.NONWEAR_REASON_3: self.nonwear_reason_3,
            DatabaseColumn.NONWEAR_START_TIME_3: self.nonwear_start_time_3,
            DatabaseColumn.NONWEAR_END_TIME_3: self.nonwear_end_time_3,
            DatabaseColumn.DIARY_NOTES: self.diary_notes,
            DatabaseColumn.NIGHT_NUMBER: self.night_number,
            # NOTE: import_date and original_column_mapping belong in other tables:
            # - import_date goes to diary_file_registry
            # - original_column_mapping goes to diary_raw_data
            # The diary_data table uses created_at/updated_at instead
        }

    @classmethod
    def from_database_dict(cls, data: dict[str, Any]) -> DiaryEntry:
        """Create from database data."""
        return cls(
            participant_id=data[DatabaseColumn.PARTICIPANT_ID],
            diary_date=data[DatabaseColumn.DIARY_DATE],
            filename=data[DatabaseColumn.FILENAME],
            bedtime=data.get(DatabaseColumn.BEDTIME),
            wake_time=data.get(DatabaseColumn.WAKE_TIME),
            sleep_onset_time=data.get(DatabaseColumn.SLEEP_ONSET_TIME),
            sleep_offset_time=data.get(DatabaseColumn.SLEEP_OFFSET_TIME),
            in_bed_time=data.get(DatabaseColumn.IN_BED_TIME),
            sleep_quality=data.get(DatabaseColumn.SLEEP_QUALITY),
            nap_occurred=data.get(DatabaseColumn.NAP_OCCURRED),
            nap_onset_time=data.get(DatabaseColumn.NAP_ONSET_TIME),
            nap_offset_time=data.get(DatabaseColumn.NAP_OFFSET_TIME),
            nap_onset_time_2=data.get(DatabaseColumn.NAP_ONSET_TIME_2),
            nap_offset_time_2=data.get(DatabaseColumn.NAP_OFFSET_TIME_2),
            nap_onset_time_3=data.get(DatabaseColumn.NAP_ONSET_TIME_3),
            nap_offset_time_3=data.get(DatabaseColumn.NAP_OFFSET_TIME_3),
            nonwear_occurred=data.get(DatabaseColumn.NONWEAR_OCCURRED),
            nonwear_reason=data.get(DatabaseColumn.NONWEAR_REASON),
            nonwear_start_time=data.get(DatabaseColumn.NONWEAR_START_TIME),
            nonwear_end_time=data.get(DatabaseColumn.NONWEAR_END_TIME),
            nonwear_reason_2=data.get(DatabaseColumn.NONWEAR_REASON_2),
            nonwear_start_time_2=data.get(DatabaseColumn.NONWEAR_START_TIME_2),
            nonwear_end_time_2=data.get(DatabaseColumn.NONWEAR_END_TIME_2),
            nonwear_reason_3=data.get(DatabaseColumn.NONWEAR_REASON_3),
            nonwear_start_time_3=data.get(DatabaseColumn.NONWEAR_START_TIME_3),
            nonwear_end_time_3=data.get(DatabaseColumn.NONWEAR_END_TIME_3),
            diary_notes=data.get(DatabaseColumn.DIARY_NOTES),
            night_number=data.get(DatabaseColumn.NIGHT_NUMBER),
            import_date=data.get(DatabaseColumn.IMPORT_DATE, datetime.now().isoformat()),
            original_column_mapping=data.get(DatabaseColumn.ORIGINAL_COLUMN_MAPPING),
        )


@dataclass
class DiaryImportResult:
    """Result of diary import operation."""

    total_files_processed: int = 0
    total_entries_imported: int = 0
    successful_files: list[str] = field(default_factory=list)
    failed_files: list[tuple[str, str]] = field(default_factory=list)  # (filename, error)
    mapping_results: dict[str, DiaryColumnMapping] = field(default_factory=dict)
    participants_found: set[str] = field(default_factory=set)
    import_duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_files_processed == 0:
            return 0.0
        return (len(self.successful_files) / self.total_files_processed) * 100


__all__ = [
    "DiaryColumnMapping",
    "DiaryEntry",
    "DiaryFileInfo",
    "DiaryImportResult",
]
