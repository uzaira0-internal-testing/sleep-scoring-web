"""
SQLAlchemy ORM models for Sleep Scoring Web.

Database schema with tables for:
- Users (session-based auth with roles)
- Sessions (session storage for authentication)
- Files (uploaded activity data files)
- RawActivityData (epoch-level activity data)
- Markers (sleep and nonwear markers)
- UserAnnotations (for multi-user consensus)
- SleepMetrics (calculated metrics per period)
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - required at runtime for SQLAlchemy Mapped types
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
    func,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from sleep_scoring_web.schemas.enums import FileStatus, MarkerCategory, MarkerType, UserRole, VerificationStatus

if TYPE_CHECKING:
    from sqlalchemy.sql.elements import ColumnElement


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class User(Base):
    """User account for session-based authentication."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(SQLEnum(UserRole, native_enum=False), default=UserRole.ANNOTATOR, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Session(Base):
    """
    Session storage for cookie-based site-wide authentication.

    Used by SessionAuthMiddleware to store session tokens.
    """

    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class File(Base):
    """Uploaded activity data file."""

    __tablename__ = "files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    original_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_type: Mapped[str] = mapped_column(String(50), default="csv")
    participant_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(50), default=FileStatus.PENDING)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Honor-system username tracking
    uploaded_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    activity_data: Mapped[list[RawActivityData]] = relationship("RawActivityData", back_populates="file", cascade="all, delete-orphan")
    markers: Mapped[list[Marker]] = relationship("Marker", back_populates="file", cascade="all, delete-orphan")
    annotations: Mapped[list[UserAnnotation]] = relationship("UserAnnotation", back_populates="file", cascade="all, delete-orphan")
    sleep_metrics: Mapped[list[SleepMetric]] = relationship("SleepMetric", back_populates="file", cascade="all, delete-orphan")
    assignments: Mapped[list[FileAssignment]] = relationship("FileAssignment", back_populates="file", cascade="all, delete-orphan")


class RawActivityData(Base):
    """Raw activity data per epoch."""

    __tablename__ = "raw_activity_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    epoch_index: Mapped[int] = mapped_column(Integer, nullable=False)
    axis_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    axis_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    axis_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    vector_magnitude: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Relationships
    file: Mapped[File] = relationship("File", back_populates="activity_data")

    __table_args__ = (
        Index("ix_raw_activity_data_file_timestamp", "file_id", "timestamp"),
        Index("ix_raw_activity_data_file_epoch", "file_id", "epoch_index"),
    )


class Marker(Base):
    """Sleep or nonwear marker."""

    __tablename__ = "markers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    marker_category: Mapped[str] = mapped_column(String(50), nullable=False)  # sleep, nonwear
    marker_type: Mapped[str] = mapped_column(String(50), nullable=False)  # MAIN_SLEEP, NAP, etc.
    start_timestamp: Mapped[float] = mapped_column(Float, nullable=False)
    end_timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)
    period_index: Mapped[int] = mapped_column(Integer, default=1)

    # Honor-system username tracking
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    file: Mapped[File] = relationship("File", back_populates="markers")

    @classmethod
    def sensor_nonwear_filter(cls) -> ColumnElement[bool]:
        """Filter condition matching sensor nonwear markers."""
        return and_(
            cls.marker_category == MarkerCategory.NONWEAR,
            cls.marker_type == MarkerType.SENSOR_NONWEAR,
        )

    @classmethod
    def exclude_sensor_nonwear_filter(cls) -> ColumnElement[bool]:
        """Filter condition excluding sensor nonwear markers."""
        return cls.marker_type != MarkerType.SENSOR_NONWEAR

    __table_args__ = (
        Index("ix_markers_file_date", "file_id", "analysis_date"),
        UniqueConstraint("file_id", "analysis_date", "created_by", "marker_category", "period_index", name="uq_marker_file_date_user_cat_period"),
    )


class UserAnnotation(Base):
    """User annotation for consensus system."""

    __tablename__ = "user_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    # Honor-system username (for consensus tracking)
    username: Mapped[str] = mapped_column(String(100), nullable=False)

    # Marker data stored as JSON for flexibility
    sleep_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    nonwear_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    is_no_sleep: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    needs_consensus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    algorithm_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detection_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    time_spent_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default=VerificationStatus.DRAFT)  # draft, submitted

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    file: Mapped[File] = relationship("File", back_populates="annotations")

    __table_args__ = (Index("ix_user_annotations_file_date_user", "file_id", "analysis_date", "username", unique=True),)


class SleepMetric(Base):
    """
    Calculated Tudor-Locke sleep metrics per period.

    Reference:
        Tudor-Locke C, et al. (2014). Fully automated waist-worn accelerometer algorithm
        for detecting children's sleep-period time. Applied Physiology, Nutrition, and
        Metabolism, 39(1):53-57.
    """

    __tablename__ = "sleep_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    period_index: Mapped[int] = mapped_column(Integer, default=0)

    # Period boundaries (timestamps in seconds, datetimes for display)
    onset_timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)
    offset_timestamp: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_bed_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    out_bed_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sleep_onset: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sleep_offset: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Duration metrics (minutes)
    time_in_bed_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_sleep_time_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_onset_latency_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    waso_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Awakening metrics
    number_of_awakenings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    average_awakening_length_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Quality indices (percentages 0-100)
    sleep_efficiency: Mapped[float | None] = mapped_column(Float, nullable=True)
    movement_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    fragmentation_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_fragmentation_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Activity metrics
    total_activity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    nonzero_epochs: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Algorithm info
    algorithm_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    detection_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    scored_by: Mapped[str | None] = mapped_column(String(100), nullable=True)  # Honor-system username
    verification_status: Mapped[str] = mapped_column(String(50), default=VerificationStatus.DRAFT)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    file: Mapped[File] = relationship("File", back_populates="sleep_metrics")

    __table_args__ = (Index("ix_sleep_metrics_file_date_period_user", "file_id", "analysis_date", "period_index", "scored_by", unique=True),)


class ConsensusResult(Base):
    """Calculated consensus when 2+ annotations exist."""

    __tablename__ = "consensus_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    has_consensus: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    consensus_sleep_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    consensus_nonwear_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    disagreement_details_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    calculated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_consensus_results_file_date", "file_id", "analysis_date", unique=True),)


class ConsensusCandidate(Base):
    """Immutable candidate marker set for consensus voting."""

    __tablename__ = "consensus_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    # Creator identity (human scorer or pseudo-user like auto_score)
    source_username: Mapped[str] = mapped_column(String(100), nullable=False)

    # Canonical hash of marker payload for quick dedupe checks.
    candidate_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    sleep_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    nonwear_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    is_no_sleep: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    algorithm_used: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_consensus_candidates_file_date", "file_id", "analysis_date"),
        Index("ix_consensus_candidates_file_date_hash", "file_id", "analysis_date", "candidate_hash"),
        UniqueConstraint("file_id", "analysis_date", "source_username", name="uq_consensus_candidate_user"),
    )


class ConsensusVote(Base):
    """One active vote per (file, date, voter)."""

    __tablename__ = "consensus_votes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    voter_username: Mapped[str] = mapped_column(String(100), nullable=False)

    candidate_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("consensus_candidates.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_consensus_votes_file_date", "file_id", "analysis_date"),
        Index("ix_consensus_votes_file_date_user", "file_id", "analysis_date", "voter_username", unique=True),
    )


class ResolvedAnnotation(Base):
    """Admin-resolved final values for disputed annotations."""

    __tablename__ = "resolved_annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    final_sleep_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    final_nonwear_markers_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)

    # Honor-system username
    resolved_by: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_resolved_annotations_file_date", "file_id", "analysis_date", unique=True),)


class DiaryEntry(Base):
    """
    Sleep diary entry for a participant/date.

    Stores self-reported sleep times from a diary CSV for comparison
    with actigraphy-derived markers.
    """

    __tablename__ = "diary_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)

    # Self-reported times (stored as HH:MM strings or datetime)
    bed_time: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "22:30"
    wake_time: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "07:15"
    lights_out: Mapped[str | None] = mapped_column(String(10), nullable=True)
    got_up: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Optional quality metrics
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1-5 or 1-10 scale
    time_to_fall_asleep_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_awakenings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Nap periods (up to 3)
    nap_1_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nap_1_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nap_2_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nap_2_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nap_3_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nap_3_end: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Nonwear periods (up to 3, with reason)
    nonwear_1_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nonwear_1_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nonwear_1_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    nonwear_2_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nonwear_2_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nonwear_2_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    nonwear_3_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nonwear_3_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nonwear_3_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Honor-system username
    imported_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    file: Mapped[File] = relationship("File")

    __table_args__ = (Index("ix_diary_entries_file_date", "file_id", "analysis_date", unique=True),)


class NightComplexity(Base):
    """
    Night scoring difficulty metric (0-100, higher = easier).

    Pre-scoring: computed from raw activity + algorithm + diary + Choi nonwear.
    Post-scoring: refined after markers are placed, using actual metrics.
    """

    __tablename__ = "night_complexity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    complexity_pre: Mapped[int | None] = mapped_column(Integer, nullable=True)
    complexity_post: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    file: Mapped[File] = relationship("File")

    __table_args__ = (
        Index("ix_night_complexity_file_date", "file_id", "analysis_date", unique=True),
    )


class UserSettings(Base):
    """
    User-specific settings and preferences.

    Keyed by username (honor system).
    """

    __tablename__ = "user_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    # Study settings
    sleep_detection_rule: Mapped[str | None] = mapped_column(String(100), nullable=True)
    night_start_hour: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "21:00"
    night_end_hour: Mapped[str | None] = mapped_column(String(10), nullable=True)  # "09:00"

    # Data settings
    device_preset: Mapped[str | None] = mapped_column(String(50), nullable=True)
    epoch_length_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skip_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Display preferences
    preferred_display_column: Mapped[str | None] = mapped_column(String(50), nullable=True)
    view_mode_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 24 or 48
    default_algorithm: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # All other settings as JSON for flexibility
    extra_settings_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AuditLogEntry(Base):
    """
    Append-only audit log tracking every user action per file/date.

    Designed for ML training data and reproducibility: given the activity data
    and diary, replay exactly what the researcher did to produce the final markers.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    analysis_date: Mapped[datetime] = mapped_column(Date, nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)

    # Action classification
    action: Mapped[str] = mapped_column(String(50), nullable=False)

    # Client-side timestamp (when the user actually performed the action)
    client_timestamp: Mapped[float] = mapped_column(Float, nullable=False)

    # Server receipt timestamp
    server_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Session tracking (groups actions from one scoring session)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)

    # Ordering within a session (monotonically increasing)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)

    # Flexible JSON payload — action-specific data (before/after state, metadata)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # Relationships
    file: Mapped[File] = relationship("File")

    __table_args__ = (
        Index("ix_audit_log_file_date_user", "file_id", "analysis_date", "username"),
        UniqueConstraint("session_id", "sequence", name="uq_audit_session_sequence"),
    )


class FileAssignment(Base):
    """Admin-assigned file → user mapping for scoring workflow."""

    __tablename__ = "file_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(Integer, ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(100), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    file: Mapped[File] = relationship("File", back_populates="assignments")

    __table_args__ = (
        UniqueConstraint("file_id", "username", name="uq_file_assignment"),
        Index("ix_file_assignments_username", "username"),
    )
