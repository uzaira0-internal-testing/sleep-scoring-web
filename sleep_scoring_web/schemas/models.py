"""
Pydantic models for the Sleep Scoring Web API.

Ported from desktop app's dataclasses with Pydantic v2 features.
These models are the single source of truth for API request/response shapes.
"""

from __future__ import annotations

from datetime import date, datetime  # noqa: TC003 — Pydantic needs these at runtime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from sleep_scoring_web.utils import ensure_seconds

from .enums import (
    AlgorithmType,
    FileStatus,
    MarkerType,
    VerificationStatus,
)

# Semantic type alias — all timestamp fields across the API are Unix seconds.
UnixSeconds = Annotated[float, Field(description="Unix timestamp in seconds")]

# Upper bound: year 2100 in Unix seconds
_MAX_UNIX_SECONDS = 4_102_444_800


def _normalize_timestamp(v: float | None) -> float | None:
    """Normalize and validate a Unix timestamp, auto-converting ms → s."""
    if v is None:
        return None
    v = ensure_seconds(v)
    if v < 0 or v > _MAX_UNIX_SECONDS:
        msg = f"Timestamp {v} out of valid range (0 to year 2100)"
        raise ValueError(msg)
    return v


# =============================================================================
# Sleep Period & Marker Models
# =============================================================================


class SleepPeriod(BaseModel):
    """
    Individual sleep period with onset/offset timestamps.

    Ported from desktop's dataclasses_markers.SleepPeriod.
    """

    model_config = ConfigDict(frozen=True)

    onset_timestamp: UnixSeconds | None = None
    offset_timestamp: UnixSeconds | None = None
    marker_index: int = 1
    marker_type: MarkerType = MarkerType.MAIN_SLEEP

    @field_validator("onset_timestamp", "offset_timestamp")
    @classmethod
    def _validate_timestamp(cls, v: float | None) -> float | None:
        return _normalize_timestamp(v)

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

    start_timestamp: UnixSeconds | None = None
    end_timestamp: UnixSeconds | None = None
    marker_index: int = 1

    @field_validator("start_timestamp", "end_timestamp")
    @classmethod
    def _validate_timestamp(cls, v: float | None) -> float | None:
        return _normalize_timestamp(v)

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

    timestamps: list[UnixSeconds] = Field(default_factory=list, description="Unix timestamps in seconds")
    axis_x: list[float] = Field(default_factory=list)
    axis_y: list[float] = Field(default_factory=list)
    axis_z: list[float] = Field(default_factory=list)
    vector_magnitude: list[float] = Field(default_factory=list)

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

    start_timestamp: UnixSeconds
    end_timestamp: UnixSeconds


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
    view_start: UnixSeconds | None = None
    view_end: UnixSeconds | None = None


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


# =============================================================================
# Marker Table Models (moved from api/markers_tables.py)
# =============================================================================


class OnsetOffsetDataPoint(BaseModel):
    """Single data point for onset/offset tables."""

    timestamp: UnixSeconds
    datetime_str: str
    axis_y: float
    vector_magnitude: float
    algorithm_result: int | None = None  # 0=wake, 1=sleep
    choi_result: int | None = None  # 0=wear, 1=nonwear
    is_nonwear: bool = False  # Manual nonwear marker overlap


class OnsetOffsetColumnar(BaseModel):
    """Columnar format for onset/offset table data."""

    timestamps: list[UnixSeconds] = Field(default_factory=list)
    axis_y: list[float] = Field(default_factory=list)
    vector_magnitude: list[float] = Field(default_factory=list)
    algorithm_result: list[int | None] = Field(default_factory=list)
    choi_result: list[int | None] = Field(default_factory=list)
    is_nonwear: list[bool] = Field(default_factory=list)


class OnsetOffsetTableResponse(BaseModel):
    """Response with data points around a marker for tables."""

    onset_data: list[OnsetOffsetDataPoint] = Field(default_factory=list)
    offset_data: list[OnsetOffsetDataPoint] = Field(default_factory=list)
    period_index: int


class OnsetOffsetColumnarResponse(BaseModel):
    """Columnar response with data around a marker."""

    onset_data: OnsetOffsetColumnar = Field(default_factory=OnsetOffsetColumnar)
    offset_data: OnsetOffsetColumnar = Field(default_factory=OnsetOffsetColumnar)
    period_index: int


class FullTableDataPoint(BaseModel):
    """Single data point for full 48h table."""

    timestamp: UnixSeconds
    datetime_str: str
    axis_y: float
    vector_magnitude: float
    algorithm_result: int | None = None
    choi_result: int | None = None
    is_nonwear: bool = False


class FullTableColumnar(BaseModel):
    """Columnar format for full table data."""

    timestamps: list[UnixSeconds] = Field(default_factory=list)
    axis_y: list[float] = Field(default_factory=list)
    vector_magnitude: list[float] = Field(default_factory=list)
    algorithm_result: list[int | None] = Field(default_factory=list)
    choi_result: list[int | None] = Field(default_factory=list)
    is_nonwear: list[bool] = Field(default_factory=list)
    total_rows: int = 0
    start_time: str | None = None
    end_time: str | None = None


class FullTableResponse(BaseModel):
    """Response with full 48h of data for popout table."""

    data: list[FullTableDataPoint] = Field(default_factory=list)
    total_rows: int = 0
    start_time: str | None = None
    end_time: str | None = None


# =============================================================================
# Date Status Models
# =============================================================================


class DateStatus(BaseModel):
    """Date annotation status with complexity scores."""

    date: str
    has_markers: bool
    is_no_sleep: bool
    needs_consensus: bool  # manually flagged by user
    auto_flagged: bool = False  # system-detected: 2+ human scorers disagree
    has_auto_score: bool
    complexity_pre: float | None = None
    complexity_post: float | None = None


# =============================================================================
# API Response Models (typed replacements for raw dict returns)
# =============================================================================


class FileListResponse(BaseModel):
    """Response for listing files."""

    items: list[FileInfo]
    total: int


class AuthMeResponse(BaseModel):
    """Response for GET /files/auth/me."""

    username: str
    is_admin: bool


class FileAssignmentResponse(BaseModel):
    """Single file assignment entry."""

    id: int
    file_id: int
    filename: str
    username: str
    assigned_by: str
    assigned_at: str | None = None


class CreateAssignmentsResponse(BaseModel):
    """Response for POST /files/assignments."""

    created: int
    total_requested: int


class DeleteResponse(BaseModel):
    """Generic response for delete operations returning a count."""

    deleted: int


class AssignmentProgressFile(BaseModel):
    """Per-file progress within an assignment progress entry."""

    file_id: int
    filename: str
    total_dates: int
    scored_dates: int
    assigned_at: str | None = None


class AssignmentProgressResponse(BaseModel):
    """Per-user assignment progress."""

    username: str
    files: list[AssignmentProgressFile]
    total_files: int
    total_dates: int
    scored_dates: int


class UnassignedFileResponse(BaseModel):
    """A file with no assignments."""

    id: int
    filename: str
    participant_id: str | None = None
    status: str


class PurgeExcludedResponse(BaseModel):
    """Response for POST /files/purge-excluded."""

    deleted_count: int
    deleted_filenames: list[str]


class BackfillResponse(BaseModel):
    """Response for POST /files/backfill-participant-ids."""

    updated: int
    total_files: int


class ComputeComplexityResponse(BaseModel):
    """Response for POST /files/{file_id}/compute-complexity."""

    message: str
    date_count: int


class NightComplexityResponse(BaseModel):
    """Response for GET /files/{file_id}/{date}/complexity."""

    complexity_pre: int | None = None
    complexity_post: int | None = None
    features: dict[str, float | str | None]
    computed_at: str | None = None


class DeleteAllFilesResponse(BaseModel):
    """Response for DELETE /files."""

    message: str
    deleted_count: int


class ScanStartResponse(BaseModel):
    """Response for POST /files/scan."""

    message: str
    started: bool
    total_files: int
    status_url: str | None = None


class ScanStatusResponse(BaseModel):
    """Response for GET /files/scan/status."""

    is_running: bool
    total_files: int
    processed: int
    imported: int
    skipped: int
    failed: int
    current_file: str
    progress_percent: float
    imported_files: list[str]
    error: str | None = None


class WatcherStatusResponse(BaseModel):
    """Response for GET /files/watcher/status."""

    is_running: bool
    watched_directory: str
    total_ingested: int
    total_skipped: int
    total_failed: int
    pending_files: list[str]
    last_scan_time: str | None = None
    recent_errors: list[str]


class MarkerDeleteResponse(BaseModel):
    """Response for DELETE /markers/{file_id}/{date}/{period_index}."""

    deleted: bool
    period_index: int


class AutoScoreResultResponse(BaseModel):
    """Response for GET /markers/{file_id}/{date}/auto-score-result."""

    sleep_markers: list[dict[str, Any]]
    nonwear_markers: list[dict[str, Any]]
    algorithm_used: str | None = None
    notes: str | None = None


class PipelineDiscoveryResponse(BaseModel):
    """Response for GET /markers/pipeline/discover."""

    roles: dict[str, list[str]]
    param_schemas: dict[str, dict[str, Any]]


# NOTE: Consensus ballot models live in api/consensus.py (CandidateVoteSummary,
# ConsensusBallotResponse) and are already exposed in the OpenAPI schema via
# response_model annotations on the ballot endpoints.
