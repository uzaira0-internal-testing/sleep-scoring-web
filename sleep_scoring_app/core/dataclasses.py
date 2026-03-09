#!/usr/bin/env python3
"""
Type Definitions for Sleep Scoring Application.

Re-exports from focused domain modules for a single import point.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import (
    DeleteStatus,
    FileSourceType,
    MarkerType,  # pyright: ignore[reportUnusedImport]  # re-exported for consumers
    ParticipantGroup,
    ParticipantTimepoint,
)
from sleep_scoring_app.core.dataclasses_analysis import *  # noqa: F403
from sleep_scoring_app.core.dataclasses_config import *  # noqa: F403
from sleep_scoring_app.core.dataclasses_daily import *  # noqa: F403
from sleep_scoring_app.core.dataclasses_diary import *  # noqa: F403
from sleep_scoring_app.core.dataclasses_markers import *  # noqa: F403

if TYPE_CHECKING:
    from pathlib import Path

    import pandas as pd


@dataclass
class ParticipantInfo:
    """Participant information extracted from filename."""

    numerical_id: str = "Unknown"
    full_id: str = "Unknown T1 G1"
    group: ParticipantGroup = ParticipantGroup.GROUP_1
    timepoint: ParticipantTimepoint = ParticipantTimepoint.T1
    date: str = ""
    # Raw extracted strings (before enum conversion) for display purposes
    group_str: str = "G1"
    timepoint_str: str = "T1"

    @property
    def participant_key(self) -> str:
        """Generate composite PARTICIPANT_KEY from id, group, and timepoint."""
        return f"{self.numerical_id}_{self.group}_{self.timepoint}"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ParticipantInfo:
        """Create from dictionary data."""
        # Get group and timepoint values
        group_val = data.get("participant_group", ParticipantGroup.GROUP_1)
        timepoint_val = data.get("participant_timepoint", ParticipantTimepoint.T1)

        # Convert to enums if strings
        group_enum = ParticipantGroup(group_val) if isinstance(group_val, str) else group_val
        timepoint_enum = ParticipantTimepoint(timepoint_val) if isinstance(timepoint_val, str) else timepoint_val

        # Get string representations (use enum values if not provided)
        group_str = data.get("group_str") or str(group_enum.value if hasattr(group_enum, "value") else group_enum)
        timepoint_str = data.get("timepoint_str") or str(timepoint_enum.value if hasattr(timepoint_enum, "value") else timepoint_enum)

        return cls(
            numerical_id=data.get("numerical_participant_id", "Unknown"),
            full_id=data.get("full_participant_id", "Unknown T1 G1"),
            group=group_enum,
            timepoint=timepoint_enum,
            date=data.get("date", ""),
            group_str=group_str,
            timepoint_str=timepoint_str,
        )

    @classmethod
    def from_participant_key(cls, participant_key: str) -> ParticipantInfo:
        """Create from composite PARTICIPANT_KEY string."""
        parts = participant_key.split("_")
        if len(parts) != 3:
            msg = f"Invalid participant key format: {participant_key}"
            raise ValueError(msg)

        return cls(
            numerical_id=parts[0],
            group=ParticipantGroup(parts[1]),
            timepoint=ParticipantTimepoint(parts[2]),
        )


@dataclass(frozen=True)
class FileInfo:
    """
    Information about a data file available for analysis.

    Attributes:
        filename: The file name (e.g., "participant_001.csv")
        source: Where the data is loaded from (database or csv)
        source_path: Original filesystem path the file was imported from
        participant_id: Extracted participant ID
        participant_group: Extracted participant group
        total_records: Number of data records (epochs)
        import_date: When the file was imported (ISO format string)
        completed_count: Number of dates with completed scoring
        total_dates: Total number of dates available for scoring
        start_date: First date in the file (ISO format)
        end_date: Last date in the file (ISO format)
        has_metrics: Whether the file has associated sleep metrics in database

    """

    filename: str
    source: FileSourceType = FileSourceType.DATABASE
    source_path: Path | None = None
    participant_id: str = ""
    participant_group: str = ""
    total_records: int = 0
    import_date: str | None = None
    completed_count: int = 0
    total_dates: int = 0
    start_date: str | None = None
    end_date: str | None = None
    has_metrics: bool = False

    @property
    def display_name(self) -> str:
        """Human-readable name for UI display."""
        suffix = " (imported)" if self.source == FileSourceType.DATABASE else " (CSV)"
        return f"{self.filename}{suffix}"


@dataclass(frozen=True)
class DeleteResult:
    """Result of a single file deletion operation."""

    status: DeleteStatus
    filename: str
    records_deleted: int = 0
    metrics_deleted: int = 0
    error_message: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class BatchDeleteResult:
    """Result of a batch file deletion operation."""

    total_requested: int
    successful: int
    failed: int
    results: list[DeleteResult]


@dataclass(frozen=True)
class DataSourceConfig:
    """
    Data source configuration for dependency injection.

    Immutable configuration for data source loaders.
    Used to specify which data source to use and how to configure it.

    Attributes:
        source_type: Data source type identifier (e.g., "csv", "gt3x")
        file_path: Path to the data file
        skip_rows: Number of header rows to skip (CSV-specific)
        encoding: File encoding (CSV-specific)
        custom_columns: Custom column mappings (optional)

    """

    source_type: str = "csv"  # DataSourceType enum value
    file_path: str = ""
    skip_rows: int = 10
    encoding: str = "utf-8"
    custom_columns: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            "source_type": self.source_type,
            "file_path": self.file_path,
            "skip_rows": self.skip_rows,
            "encoding": self.encoding,
            "custom_columns": self.custom_columns,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DataSourceConfig:
        """Create from dictionary data."""
        return cls(
            source_type=data.get("source_type", "csv"),
            file_path=data.get("file_path", ""),
            skip_rows=data.get("skip_rows", 10),
            encoding=data.get("encoding", "utf-8"),
            custom_columns=data.get("custom_columns", {}),
        )


@dataclass(frozen=True)
class LoadedDataResult:
    """
    Result of data loading operation.

    Immutable container for loaded activity data and metadata.
    Returned by DataSourceLoader.load_file() implementations.

    Attributes:
        activity_data: DataFrame with datetime and activity columns
        metadata: File and device metadata
        column_mapping: Mapping of standard names to actual column names
        source_type: Data source type identifier
        file_path: Original file path

    """

    activity_data: pd.DataFrame
    metadata: dict[str, Any]
    column_mapping: dict[str, str]
    source_type: str
    file_path: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary (excluding DataFrame)."""
        return {
            "metadata": self.metadata,
            "column_mapping": self.column_mapping,
            "source_type": self.source_type,
            "file_path": self.file_path,
            "record_count": len(self.activity_data),
        }

    @property
    def has_data(self) -> bool:
        """Check if activity data is present and non-empty."""
        return self.activity_data is not None and not self.activity_data.empty

    @property
    def record_count(self) -> int:
        """Get number of records in activity data."""
        return len(self.activity_data) if self.has_data else 0
