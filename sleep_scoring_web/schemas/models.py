"""
Pydantic models for the Sleep Scoring Web API.

Ported from desktop app's dataclasses with Pydantic v2 features.
These models are the single source of truth for API request/response shapes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    AlgorithmType,
    FileStatus,
    MarkerType,
    NonwearDataSource,
    VerificationStatus,
)

# =============================================================================
# Sleep Period & Marker Models
# =============================================================================


class SleepPeriod(BaseModel):
    """
    Individual sleep period with onset/offset timestamps.

    Ported from desktop's dataclasses_markers.SleepPeriod.
    """

    model_config = ConfigDict(frozen=True)

    onset_timestamp: float | None = None
    offset_timestamp: float | None = None
    marker_index: int = 1
    marker_type: MarkerType = MarkerType.MAIN_SLEEP

    @field_validator("onset_timestamp", "offset_timestamp")
    @classmethod
    def _validate_timestamp(cls, v: float | None) -> float | None:
        if v is not None and (v < 0 or v > 4_102_444_800):
            msg = f"Timestamp {v} out of valid range (0 to year 2100)"
            raise ValueError(msg)
        return v

    @property
    def is_complete(self) -> bool:
        """Check if both markers are set."""
        return self.onset_timestamp is not None and self.offset_timestamp is not None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.is_complete and self.offset_timestamp and self.onset_timestamp:
            return self.offset_timestamp - self.onset_timestamp
        return None

    @property
    def duration_minutes(self) -> float | None:
        """Calculate duration in minutes."""
        if self.duration_seconds is not None:
            return self.duration_seconds / 60
        return None


class ManualNonwearPeriod(BaseModel):
    """
    Individual manual nonwear period with timestamps.

    Ported from desktop's dataclasses_markers.ManualNonwearPeriod.
    """

    model_config = ConfigDict(frozen=True)

    start_timestamp: float | None = None
    end_timestamp: float | None = None
    marker_index: int = 1
    source: NonwearDataSource = NonwearDataSource.MANUAL

    @field_validator("start_timestamp", "end_timestamp")
    @classmethod
    def _validate_timestamp(cls, v: float | None) -> float | None:
        if v is not None and (v < 0 or v > 4_102_444_800):
            msg = f"Timestamp {v} out of valid range (0 to year 2100)"
            raise ValueError(msg)
        return v

    @property
    def is_complete(self) -> bool:
        """Check if both markers are set."""
        return self.start_timestamp is not None and self.end_timestamp is not None

    @property
    def duration_seconds(self) -> float | None:
        """Calculate duration in seconds."""
        if self.is_complete and self.start_timestamp and self.end_timestamp:
            return self.end_timestamp - self.start_timestamp
        return None


# =============================================================================
# Sleep Metrics
# =============================================================================


class SleepMetrics(BaseModel):
    """
    Complete sleep quality metrics for a single sleep period.

    Implements Tudor-Locke metrics algorithm as defined in the
    actigraph.sleepr R package.

    Reference:
        Tudor-Locke C, et al. (2014). Fully automated waist-worn accelerometer algorithm
        for detecting children's sleep-period time. Applied Physiology, Nutrition, and
        Metabolism, 39(1):53-57.
    """

    model_config = ConfigDict(frozen=True)

    # Period boundaries (datetime as ISO strings for JSON serialization)
    in_bed_time: datetime | None = None
    out_bed_time: datetime | None = None
    sleep_onset: datetime | None = None
    sleep_offset: datetime | None = None

    # Duration metrics (minutes)
    time_in_bed_minutes: float | None = None
    total_sleep_time_minutes: float | None = None
    sleep_onset_latency_minutes: float | None = None
    waso_minutes: float | None = None

    # Awakening metrics
    number_of_awakenings: int | None = None
    average_awakening_length_minutes: float | None = None

    # Quality indices (percentages 0-100)
    sleep_efficiency: float | None = None
    movement_index: float | None = None
    fragmentation_index: float | None = None
    sleep_fragmentation_index: float | None = None

    # Activity metrics
    total_activity: int | None = None
    nonzero_epochs: int | None = None


# =============================================================================
# Activity Data Models (Columnar Format)
# =============================================================================


class ActivityDataColumnar(BaseModel):
    """
    Columnar format for efficient JSON transfer.

    This format reduces JSON overhead by using arrays instead of
    repeated object keys for each data point.
    """

    timestamps: list[float] = Field(default_factory=list, description="Unix timestamps")
    axis_x: list[int] = Field(default_factory=list)
    axis_y: list[int] = Field(default_factory=list)
    axis_z: list[int] = Field(default_factory=list)
    vector_magnitude: list[int] = Field(default_factory=list)

    @property
    def count(self) -> int:
        """Get number of data points."""
        return len(self.timestamps)

    @field_validator("axis_x", "axis_y", "axis_z", "vector_magnitude", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list:
        """Ensure value is a list."""
        if v is None:
            return []
        return list(v)


class SensorNonwearPeriod(BaseModel):
    """A single sensor-detected nonwear period (read-only overlay, not user-editable)."""

    start_timestamp: float  # Unix timestamp in seconds
    end_timestamp: float  # Unix timestamp in seconds


class ActivityDataResponse(BaseModel):
    """Response for activity data endpoint."""

    data: ActivityDataColumnar
    available_dates: list[str] = Field(default_factory=list)
    current_date_index: int = 0
    algorithm_results: list[int] | None = None  # Sleep scoring results (1=sleep, 0=wake)
    nonwear_results: list[int] | None = None  # Choi nonwear detection (1=nonwear, 0=wear)
    sensor_nonwear_periods: list[SensorNonwearPeriod] = Field(default_factory=list)  # Uploaded sensor nonwear
    file_id: int
    analysis_date: str
    # Expected view range (for setting axis bounds even if data is missing)
    view_start: float | None = None  # Unix timestamp for view start
    view_end: float | None = None  # Unix timestamp for view end


# =============================================================================
# File Models
# =============================================================================


class FileInfo(BaseModel):
    """File metadata for listing."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    original_path: str | None = None
    file_type: str = "csv"
    participant_id: str | None = None
    status: FileStatus = FileStatus.PENDING
    row_count: int | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    uploaded_by: str | None = None
    uploaded_at: datetime | None = None


class FileUploadResponse(BaseModel):
    """Response after file upload."""

    file_id: int
    filename: str
    status: FileStatus
    row_count: int | None = None
    message: str = "File uploaded successfully"


class ProcessingStatusResponse(BaseModel):
    """Response for background file processing progress."""

    file_id: int
    status: FileStatus
    phase: str | None = None  # "decompressing" / "reading_csv" / "converting_counts" / "inserting_db"
    percent: float = 0.0
    rows_processed: int = 0
    total_rows_estimate: int | None = None
    error: str | None = None
    started_at: datetime | None = None


# =============================================================================
# Marker Request/Response Models
# =============================================================================


class MarkerUpdateRequest(BaseModel):
    """Request to update markers for a file/date."""

    sleep_markers: list[SleepPeriod] | None = None
    nonwear_markers: list[ManualNonwearPeriod] | None = None
    algorithm_used: AlgorithmType | None = None
    detection_rule: str | None = None
    notes: str | None = None
    is_no_sleep: bool = False  # Mark this date as having no sleep
    needs_consensus: bool = False  # Flag this date for consensus review


class MarkerResponse(BaseModel):
    """Response with marker data."""

    sleep_markers: list[SleepPeriod] = Field(default_factory=list)
    nonwear_markers: list[ManualNonwearPeriod] = Field(default_factory=list)
    verification_status: VerificationStatus = VerificationStatus.DRAFT
    algorithm_used: AlgorithmType | None = None
    last_modified_by: str | None = None
    last_modified_at: datetime | None = None


# =============================================================================
# Consensus Models (for multi-user verification)
# =============================================================================


class ConsensusStatusResponse(BaseModel):
    """Consensus status for a file/date."""

    file_id: int
    analysis_date: date
    annotation_count: int = 0
    has_consensus: bool = False
    verification_tier: str = "none"  # none, single_verified, agreed, disputed
    disagreement_summary: list[dict[str, Any]] | None = None


class ResolveDisputeRequest(BaseModel):
    """Request to resolve a disputed annotation."""

    final_sleep_markers: list[SleepPeriod]
    final_nonwear_markers: list[ManualNonwearPeriod] = Field(default_factory=list)
    resolution_notes: str | None = None


# =============================================================================
# Export Models
# =============================================================================


class ExportColumnCategory(BaseModel):
    """Category of export columns (e.g., Participant Info, Sleep Metrics)."""

    name: str = Field(description="Category display name")
    columns: list[str] = Field(default_factory=list, description="Column names in this category")


class ExportColumnInfo(BaseModel):
    """Information about an available export column."""

    name: str = Field(description="Column name as it appears in CSV")
    category: str = Field(description="Category for grouping in UI")
    description: str | None = Field(default=None, description="Human-readable description")
    data_type: str = Field(default="string", description="Data type: string, number, datetime")
    is_default: bool = Field(default=True, description="Whether included in default export")


class ExportColumnsResponse(BaseModel):
    """Response listing all available export columns."""

    columns: list[ExportColumnInfo] = Field(default_factory=list)
    categories: list[ExportColumnCategory] = Field(default_factory=list)


class ExportRequest(BaseModel):
    """Request to generate a CSV export."""

    file_ids: list[int] = Field(description="File IDs to include in export")
    date_range: tuple[date, date] | None = Field(default=None, description="Optional date range filter")
    columns: list[str] | None = Field(default=None, description="Columns to include (None = all)")
    include_header: bool = Field(default=True, description="Include CSV header row")
    include_metadata: bool = Field(default=False, description="Include metadata comments at top")


class ExportResponse(BaseModel):
    """Response after generating an export."""

    success: bool
    filename: str | None = None
    row_count: int = 0
    file_count: int = 0
    message: str = ""
    warnings: list[str] = Field(default_factory=list)
