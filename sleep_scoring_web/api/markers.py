"""
Marker API endpoints for sleep and nonwear marker management.

Provides CRUD operations for markers with optimistic update support.

Note: We intentionally avoid `from __future__ import annotations` here
because FastAPI's dependency injection needs actual types, not string
annotations. Using Annotated types requires runtime resolution.
"""

import calendar
import asyncio
import logging
from dataclasses import dataclass, field as dc_field
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, or_, select

from sleep_scoring_web.api.access import require_file_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import ConsensusCandidate, ConsensusVote, DiaryEntry, Marker, RawActivityData, SleepMetric, UserAnnotation
from sleep_scoring_web.schemas import ManualNonwearPeriod, MarkerResponse, MarkerUpdateRequest, SleepMetrics, SleepPeriod
from sleep_scoring_web.schemas.enums import AlgorithmType, MarkerCategory, MarkerLimits, MarkerType, VerificationStatus
from sleep_scoring_web.services.consensus import compute_candidate_hash
from sleep_scoring_web.services.consensus_realtime import broadcast_consensus_update
from sleep_scoring_web.services.file_identity import (
    build_file_identity,
    filename_stem,
    is_excluded_activity_filename,
    is_excluded_file_obj,
    normalize_filename,
    normalize_participant_id,
    normalize_timepoint,
)

router = APIRouter()


def naive_to_unix(dt: datetime) -> float:
    """Convert naive datetime to Unix timestamp without timezone interpretation."""
    return float(calendar.timegm(dt.timetuple()))


async def _upsert_consensus_candidate_snapshot(
    db: DbSession,
    *,
    file_id: int,
    analysis_date: date,
    source_username: str,
    sleep_markers_json: list[dict[str, Any]] | None,
    nonwear_markers_json: list[dict[str, Any]] | None,
    is_no_sleep: bool,
    algorithm_used: str | None,
    notes: str | None,
) -> None:
    """
    Persist consensus candidate for a user's current marker set.

    Each user has exactly one candidate per file/date (enforced by unique
    constraint on (file_id, analysis_date, source_username)).  When the
    user saves updated markers, their candidate is updated in place.
    """
    candidate_hash = compute_candidate_hash(
        sleep_markers=sleep_markers_json,
        nonwear_markers=nonwear_markers_json,
        is_no_sleep=is_no_sleep,
    )

    # Find this user's existing candidate for this file/date
    result = await db.execute(
        select(ConsensusCandidate).where(
            and_(
                ConsensusCandidate.file_id == file_id,
                ConsensusCandidate.analysis_date == analysis_date,
                ConsensusCandidate.source_username == source_username,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        if existing.candidate_hash == candidate_hash:
            return  # No change
        # Update in place — preserves the candidate ID so any votes stay linked
        existing.candidate_hash = candidate_hash
        existing.sleep_markers_json = sleep_markers_json
        existing.nonwear_markers_json = nonwear_markers_json
        existing.is_no_sleep = is_no_sleep
        existing.algorithm_used = algorithm_used
        existing.notes = notes
    else:
        db.add(
            ConsensusCandidate(
                file_id=file_id,
                analysis_date=analysis_date,
                source_username=source_username,
                candidate_hash=candidate_hash,
                sleep_markers_json=sleep_markers_json,
                nonwear_markers_json=nonwear_markers_json,
                is_no_sleep=is_no_sleep,
                algorithm_used=algorithm_used,
                notes=notes,
            )
        )


# =============================================================================
# Request/Response Models
# =============================================================================


class OnsetOffsetDataPoint(BaseModel):
    """Single data point for onset/offset tables."""

    timestamp: float
    datetime_str: str
    axis_y: int
    vector_magnitude: int
    algorithm_result: int | None = None  # 0=wake, 1=sleep
    choi_result: int | None = None  # 0=wear, 1=nonwear
    is_nonwear: bool = False  # Manual nonwear marker overlap


class OnsetOffsetTableResponse(BaseModel):
    """Response with data points around a marker for tables."""

    onset_data: list[OnsetOffsetDataPoint] = Field(default_factory=list)
    offset_data: list[OnsetOffsetDataPoint] = Field(default_factory=list)
    period_index: int


class MarkersWithMetricsResponse(BaseModel):
    """Response with markers and their calculated metrics."""

    sleep_markers: list[SleepPeriod] = Field(default_factory=list)
    nonwear_markers: list[ManualNonwearPeriod] = Field(default_factory=list)
    metrics: list[SleepMetrics] = Field(default_factory=list)
    algorithm_results: list[int] | None = None
    verification_status: VerificationStatus = VerificationStatus.DRAFT
    last_modified_at: datetime | None = None
    is_dirty: bool = False  # For optimistic update tracking
    is_no_sleep: bool = False  # True if this date is marked as having no sleep
    needs_consensus: bool = False  # True if flagged for consensus review
    notes: str | None = None  # Free-text annotation notes


class SaveStatusResponse(BaseModel):
    """Response after saving markers."""

    success: bool
    saved_at: datetime
    sleep_marker_count: int
    nonwear_marker_count: int
    message: str = "Markers saved successfully"


# =============================================================================
# Marker CRUD Endpoints
# =============================================================================


@router.get("/{file_id}/{analysis_date}")
async def get_markers(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    include_algorithm: Annotated[bool, Query(description="Include Sadeh algorithm results")] = True,
) -> MarkersWithMetricsResponse:
    """
    Get all markers for a specific file and date.

    Returns sleep markers, nonwear markers, and calculated metrics.
    Optionally includes algorithm results for overlay display.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()

    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Get markers for THIS user.
    # Exclude sensor nonwear (marker_type="sensor") — those are read-only overlay data
    # returned via the activity endpoint, not editable markers.
    # Fallback to legacy rows (created_by IS NULL) for backward compatibility.
    markers_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.analysis_date == analysis_date,
                Marker.created_by == username,
                Marker.marker_type != "sensor",
            )
        )
    )
    markers = markers_result.scalars().all()
    if not markers:
        legacy_markers_result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.analysis_date == analysis_date,
                    Marker.created_by.is_(None),
                    Marker.marker_type != "sensor",
                )
            )
        )
        markers = legacy_markers_result.scalars().all()
    sleep_markers: list[SleepPeriod] = []
    nonwear_markers: list[ManualNonwearPeriod] = []

    for marker in markers:
        if marker.marker_category == MarkerCategory.SLEEP:
            sleep_markers.append(
                SleepPeriod(
                    onset_timestamp=marker.start_timestamp,
                    offset_timestamp=marker.end_timestamp,
                    marker_index=marker.period_index,
                    marker_type=MarkerType(marker.marker_type) if marker.marker_type else MarkerType.MAIN_SLEEP,
                )
            )
        elif marker.marker_category == MarkerCategory.NONWEAR and marker.marker_type != "sensor":
            nonwear_markers.append(
                ManualNonwearPeriod(
                    start_timestamp=marker.start_timestamp,
                    end_timestamp=marker.end_timestamp,
                    marker_index=marker.period_index,
                )
            )

    activity_rows_cache: list[RawActivityData] | None = None
    sleep_scores_cache: list[int] | None = None

    async def _load_activity_rows() -> list[RawActivityData]:
        nonlocal activity_rows_cache
        if activity_rows_cache is not None:
            return activity_rows_cache
        start_time = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
        end_time = start_time + timedelta(hours=24)
        activity_result = await db.execute(
            select(RawActivityData)
            .where(
                and_(
                    RawActivityData.file_id == file_id,
                    RawActivityData.timestamp >= start_time,
                    RawActivityData.timestamp < end_time,
                )
            )
            .order_by(RawActivityData.timestamp)
        )
        activity_rows_cache = activity_result.scalars().all()
        return activity_rows_cache

    # Get metrics for THIS user.
    # Fallback to legacy rows (scored_by IS NULL) for backward compatibility.
    metrics_result = await db.execute(
        select(SleepMetric).where(
            and_(
                SleepMetric.file_id == file_id,
                SleepMetric.analysis_date == analysis_date,
                SleepMetric.scored_by == username,
            )
        )
    )
    db_metrics = metrics_result.scalars().all()
    if not db_metrics:
        legacy_metrics_result = await db.execute(
            select(SleepMetric).where(
                and_(
                    SleepMetric.file_id == file_id,
                    SleepMetric.analysis_date == analysis_date,
                    SleepMetric.scored_by.is_(None),
                )
            )
        )
        db_metrics = legacy_metrics_result.scalars().all()

    metrics: list[SleepMetrics] = []
    for m in db_metrics:
        metrics.append(
            SleepMetrics(
                # Period boundaries
                in_bed_time=m.in_bed_time,
                out_bed_time=m.out_bed_time,
                sleep_onset=m.sleep_onset,
                sleep_offset=m.sleep_offset,
                # Duration metrics
                time_in_bed_minutes=m.time_in_bed_minutes,
                total_sleep_time_minutes=m.total_sleep_time_minutes,
                sleep_onset_latency_minutes=m.sleep_onset_latency_minutes,
                waso_minutes=m.waso_minutes,
                # Awakening metrics
                number_of_awakenings=m.number_of_awakenings,
                average_awakening_length_minutes=m.average_awakening_length_minutes,
                # Quality indices
                sleep_efficiency=m.sleep_efficiency,
                movement_index=m.movement_index,
                fragmentation_index=m.fragmentation_index,
                sleep_fragmentation_index=m.sleep_fragmentation_index,
                # Activity metrics
                total_activity=m.total_activity,
                nonzero_epochs=m.nonzero_epochs,
            )
        )

    # If per-user metrics are missing (e.g., another scorer overwrote global rows),
    # compute metrics on-the-fly from THIS user's markers.
    if not metrics and sleep_markers:
        activity_rows = await _load_activity_rows()
        if activity_rows:
            from sleep_scoring_web.services.algorithms import create_algorithm
            from sleep_scoring_web.services.metrics import TudorLockeSleepMetricsCalculator

            # Look up the user's saved algorithm from their annotation
            _anno_result = await db.execute(
                select(UserAnnotation)
                .where(
                    and_(
                        UserAnnotation.file_id == file_id,
                        UserAnnotation.analysis_date == analysis_date,
                        UserAnnotation.username == username,
                    )
                )
            )
            _anno = _anno_result.scalar_one_or_none()
            algo_name = _anno.algorithm_used if _anno and _anno.algorithm_used else "sadeh_1994_actilife"

            axis_y_data = [row.axis_y or 0 for row in activity_rows]
            timestamps_float = [naive_to_unix(row.timestamp) for row in activity_rows]
            timestamps_dt = [row.timestamp for row in activity_rows]
            sleep_scores_cache = create_algorithm(algo_name).score(axis_y_data)
            calculator = TudorLockeSleepMetricsCalculator()

            for marker in sleep_markers:
                if marker.onset_timestamp is None or marker.offset_timestamp is None:
                    continue

                onset_idx = None
                offset_idx = None
                for i, ts in enumerate(timestamps_float):
                    if onset_idx is None and ts >= marker.onset_timestamp:
                        onset_idx = i
                    if ts <= marker.offset_timestamp:
                        offset_idx = i
                    elif ts > marker.offset_timestamp:
                        break

                if onset_idx is None or offset_idx is None:
                    continue

                try:
                    calc = calculator.calculate_metrics(
                        sleep_scores=sleep_scores_cache,
                        activity_counts=[float(x) for x in axis_y_data],
                        onset_idx=onset_idx,
                        offset_idx=offset_idx,
                        timestamps=timestamps_dt,
                    )
                    metrics.append(
                        SleepMetrics(
                            in_bed_time=calc["in_bed_time"],
                            out_bed_time=calc["out_bed_time"],
                            sleep_onset=calc["sleep_onset"],
                            sleep_offset=calc["sleep_offset"],
                            time_in_bed_minutes=calc["time_in_bed_minutes"],
                            total_sleep_time_minutes=calc["total_sleep_time_minutes"],
                            sleep_onset_latency_minutes=calc["sleep_onset_latency_minutes"],
                            waso_minutes=calc["waso_minutes"],
                            number_of_awakenings=calc["number_of_awakenings"],
                            average_awakening_length_minutes=calc["average_awakening_length_minutes"],
                            sleep_efficiency=calc["sleep_efficiency"],
                            movement_index=calc["movement_index"],
                            fragmentation_index=calc["fragmentation_index"],
                            sleep_fragmentation_index=calc["sleep_fragmentation_index"],
                            total_activity=calc["total_activity"],
                            nonzero_epochs=calc["nonzero_epochs"],
                        )
                    )
                except ValueError:
                    continue

    # Get algorithm results if requested
    algorithm_results: list[int] | None = None
    if include_algorithm and sleep_markers:
        if sleep_scores_cache is not None:
            algorithm_results = sleep_scores_cache
        else:
            activity_rows = await _load_activity_rows()
            if activity_rows:
                from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm

                axis_y_data = [row.axis_y or 0 for row in activity_rows]
                algorithm = SadehAlgorithm()
                algorithm_results = algorithm.score(axis_y_data)

    # Get last modified time
    last_modified = None
    if markers:
        last_modified = max(m.updated_at for m in markers)

    # Get is_no_sleep and needs_consensus from THIS user's annotation
    is_no_sleep = False
    needs_consensus = False
    annotation_result = await db.execute(
        select(UserAnnotation)
        .where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
                UserAnnotation.username == username,
            )
        )
    )
    annotation = annotation_result.scalar_one_or_none()
    annotation_notes: str | None = None
    if annotation:
        is_no_sleep = annotation.is_no_sleep
        needs_consensus = annotation.needs_consensus
        annotation_notes = annotation.notes

    return MarkersWithMetricsResponse(
        sleep_markers=sleep_markers,
        nonwear_markers=nonwear_markers,
        metrics=metrics,
        algorithm_results=algorithm_results,
        verification_status=VerificationStatus.DRAFT,
        last_modified_at=last_modified,
        is_dirty=False,
        is_no_sleep=is_no_sleep,
        needs_consensus=needs_consensus,
        notes=annotation_notes,
    )


@router.put("/{file_id}/{analysis_date}")
async def save_markers(
    file_id: int,
    analysis_date: date,
    request: MarkerUpdateRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    background_tasks: BackgroundTasks,
) -> SaveStatusResponse:
    """
    Save markers for a specific file and date.

    Replaces all existing markers for this file/date with the new ones.
    Triggers background calculation of sleep metrics.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()

    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Delete existing markers for THIS user/file/date.
    # Also clear legacy rows with no owner to allow clean migration.
    # IMPORTANT: Exclude marker_type="sensor" — those are uploaded nonwear sensor
    # data (read-only overlays) and must NOT be deleted when saving sleep/nonwear markers.
    await db.execute(
        delete(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.analysis_date == analysis_date,
                or_(Marker.created_by == username, Marker.created_by.is_(None)),
                Marker.marker_type != "sensor",
            )
        )
    )
    await db.flush()  # Ensure deletes are applied before inserting new rows

    # Insert new sleep markers
    sleep_count = 0
    if request.sleep_markers:
        for i, marker in enumerate(request.sleep_markers):
            if marker.onset_timestamp is not None:
                db_marker = Marker(
                    file_id=file_id,
                    analysis_date=analysis_date,
                    marker_category=MarkerCategory.SLEEP,
                    marker_type=marker.marker_type.value if marker.marker_type else MarkerType.MAIN_SLEEP.value,
                    start_timestamp=marker.onset_timestamp,
                    end_timestamp=marker.offset_timestamp,
                    period_index=marker.marker_index if marker.marker_index is not None else (i + 1),
                    created_by=username,
                )
                db.add(db_marker)
                sleep_count += 1

    # Insert new nonwear markers
    nonwear_count = 0
    if request.nonwear_markers:
        for i, marker in enumerate(request.nonwear_markers):
            if marker.start_timestamp is not None:
                db_marker = Marker(
                    file_id=file_id,
                    analysis_date=analysis_date,
                    marker_category=MarkerCategory.NONWEAR,
                    marker_type="manual",
                    start_timestamp=marker.start_timestamp,
                    end_timestamp=marker.end_timestamp,
                    period_index=marker.marker_index if marker.marker_index is not None else (i + 1),
                    created_by=username,
                )
                db.add(db_marker)
                nonwear_count += 1

    # Persist is_no_sleep and needs_consensus INLINE (not background) so the
    # GET endpoint sees them immediately.  Background tasks run AFTER the
    # response, so navigating away and back before the task completes would
    # return stale values — causing consensus flags to appear to not persist.
    existing_annotation = await db.execute(
        select(UserAnnotation)
        .where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
                UserAnnotation.username == username,
            )
        )
    )
    annotation = existing_annotation.scalar_one_or_none()

    sleep_json = [m.model_dump() for m in request.sleep_markers] if request.sleep_markers else None
    nonwear_json = [m.model_dump() for m in request.nonwear_markers] if request.nonwear_markers else None

    if annotation:
        annotation.sleep_markers_json = sleep_json
        annotation.nonwear_markers_json = nonwear_json
        annotation.is_no_sleep = request.is_no_sleep
        annotation.needs_consensus = request.needs_consensus
        annotation.algorithm_used = request.algorithm_used.value if request.algorithm_used else None
        annotation.detection_rule = request.detection_rule
        annotation.notes = request.notes
        annotation.status = "submitted"
    else:
        annotation = UserAnnotation(
            file_id=file_id,
            analysis_date=analysis_date,
            username=username,
            sleep_markers_json=sleep_json,
            nonwear_markers_json=nonwear_json,
            is_no_sleep=request.is_no_sleep,
            needs_consensus=request.needs_consensus,
            algorithm_used=request.algorithm_used.value if request.algorithm_used else None,
            detection_rule=request.detection_rule,
            notes=request.notes,
            status="submitted",
        )
        db.add(annotation)

    await _upsert_consensus_candidate_snapshot(
        db,
        file_id=file_id,
        analysis_date=analysis_date,
        source_username=username,
        sleep_markers_json=sleep_json,
        nonwear_markers_json=nonwear_json,
        is_no_sleep=request.is_no_sleep,
        algorithm_used=request.algorithm_used.value if request.algorithm_used else None,
        notes=request.notes,
    )

    await db.commit()
    await broadcast_consensus_update(
        file_id=file_id,
        analysis_date=analysis_date,
        event="candidate_updated",
        username=username,
    )

    # Recompute metrics/complexity in background on every save, including clears.
    # Without this, clearing markers leaves stale complexity_post from previous saves.
    background_tasks.add_task(
        _calculate_and_store_metrics,
        file_id=file_id,
        analysis_date=analysis_date,
        sleep_markers=request.sleep_markers or [],
        username=username,
        algorithm_type=request.algorithm_used.value if request.algorithm_used else None,
        detection_rule=request.detection_rule,
    )

    return SaveStatusResponse(
        success=True,
        saved_at=datetime.now(timezone.utc),
        sleep_marker_count=sleep_count,
        nonwear_marker_count=nonwear_count,
    )


@router.delete("/{file_id}/{analysis_date}/{period_index}")
async def delete_marker(
    file_id: int,
    analysis_date: date,
    period_index: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    marker_category: Annotated[MarkerCategory, Query()] = MarkerCategory.SLEEP,
) -> dict[str, Any]:
    """Delete a specific marker period."""
    await require_file_access(db, username, file_id)

    result = await db.execute(
        delete(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.analysis_date == analysis_date,
                Marker.period_index == period_index,
                Marker.marker_category == marker_category,
                or_(Marker.created_by == username, Marker.created_by.is_(None)),
            )
        )
    )
    await db.commit()

    if result.rowcount == 0:  # type: ignore[union-attr]
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marker not found")

    return {"deleted": True, "period_index": period_index}


# =============================================================================
# Adjacent Day Markers Endpoint
# =============================================================================


class AdjacentDayMarkersResponse(BaseModel):
    """Response with markers from previous and next days."""

    previous_day_markers: list[SleepPeriod] = Field(default_factory=list)
    next_day_markers: list[SleepPeriod] = Field(default_factory=list)
    previous_date: date | None = None
    next_date: date | None = None


@router.get("/{file_id}/{analysis_date}/adjacent")
async def get_adjacent_day_markers(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> AdjacentDayMarkersResponse:
    """
    Get sleep markers from previous and next days.

    Used to show continuity of sleep across day boundaries.
    """
    await require_file_access(db, username, file_id)

    from datetime import timedelta

    prev_date = analysis_date - timedelta(days=1)
    next_date = analysis_date + timedelta(days=1)

    # Get previous day markers for THIS user; fallback to legacy rows.
    prev_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.analysis_date == prev_date,
                Marker.marker_category == MarkerCategory.SLEEP,
                Marker.created_by == username,
            )
        )
    )
    prev_markers = prev_result.scalars().all()
    if not prev_markers:
        prev_legacy_result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.analysis_date == prev_date,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    Marker.created_by.is_(None),
                )
            )
        )
        prev_markers = prev_legacy_result.scalars().all()

    previous_day_markers = [
        SleepPeriod(
            onset_timestamp=m.start_timestamp,
            offset_timestamp=m.end_timestamp,
            marker_index=m.period_index,
            marker_type=MarkerType(m.marker_type) if m.marker_type else MarkerType.MAIN_SLEEP,
        )
        for m in prev_markers
    ]

    # Get next day markers for THIS user; fallback to legacy rows.
    next_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.analysis_date == next_date,
                Marker.marker_category == MarkerCategory.SLEEP,
                Marker.created_by == username,
            )
        )
    )
    next_markers = next_result.scalars().all()
    if not next_markers:
        next_legacy_result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.analysis_date == next_date,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    Marker.created_by.is_(None),
                )
            )
        )
        next_markers = next_legacy_result.scalars().all()

    next_day_markers = [
        SleepPeriod(
            onset_timestamp=m.start_timestamp,
            offset_timestamp=m.end_timestamp,
            marker_index=m.period_index,
            marker_type=MarkerType(m.marker_type) if m.marker_type else MarkerType.MAIN_SLEEP,
        )
        for m in next_markers
    ]

    return AdjacentDayMarkersResponse(
        previous_day_markers=previous_day_markers,
        next_day_markers=next_day_markers,
        previous_date=prev_date if prev_markers else None,
        next_date=next_date if next_markers else None,
    )


# =============================================================================
# Data Tables Endpoint (for onset/offset panels)
# =============================================================================


@router.get("/{file_id}/{analysis_date}/table/{period_index}")
async def get_onset_offset_data(
    file_id: int,
    analysis_date: date,
    period_index: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    window_minutes: Annotated[int, Query(ge=5, le=120)] = 100,
    onset_ts: Annotated[float | None, Query(description="Onset timestamp in seconds (use instead of DB lookup)")] = None,
    offset_ts: Annotated[float | None, Query(description="Offset timestamp in seconds (use instead of DB lookup)")] = None,
) -> OnsetOffsetTableResponse:
    """
    Get activity data around a marker for onset/offset tables.

    Returns data points within window_minutes of the onset and offset timestamps.
    Accepts optional onset_ts/offset_ts query params to use client-side timestamps
    instead of requiring a saved marker in the database.
    """
    await require_file_access(db, username, file_id)

    # Determine onset/offset timestamps - prefer query params, fall back to DB
    onset_timestamp: float | None = onset_ts
    offset_timestamp: float | None = offset_ts

    if onset_timestamp is None or offset_timestamp is None:
        # Fall back to THIS user's saved marker lookup.
        marker_result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.analysis_date == analysis_date,
                    Marker.period_index == period_index,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    Marker.created_by == username,
                )
            )
        )
        marker = marker_result.scalar_one_or_none()
        if marker is None:
            legacy_marker_result = await db.execute(
                select(Marker).where(
                    and_(
                        Marker.file_id == file_id,
                        Marker.analysis_date == analysis_date,
                        Marker.period_index == period_index,
                        Marker.marker_category == MarkerCategory.SLEEP,
                        Marker.created_by.is_(None),
                    )
                )
            )
            marker = legacy_marker_result.scalar_one_or_none()

        if not marker:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marker not found")

        onset_timestamp = marker.start_timestamp
        offset_timestamp = marker.end_timestamp

    if onset_timestamp is None or offset_timestamp is None:
        return OnsetOffsetTableResponse(onset_data=[], offset_data=[], period_index=period_index)

    # Get data around onset (use UTC to match stored timestamps)
    onset_dt = datetime.utcfromtimestamp(onset_timestamp)
    onset_start = onset_dt - timedelta(minutes=window_minutes)
    onset_end = onset_dt + timedelta(minutes=window_minutes)

    onset_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= onset_start,
                RawActivityData.timestamp <= onset_end,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    onset_rows = onset_result.scalars().all()

    # Get data around offset (use UTC to match stored timestamps)
    offset_dt = datetime.utcfromtimestamp(offset_timestamp)
    offset_start = offset_dt - timedelta(minutes=window_minutes)
    offset_end = offset_dt + timedelta(minutes=window_minutes)

    offset_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= offset_start,
                RawActivityData.timestamp <= offset_end,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    offset_rows = offset_result.scalars().all()

    # Get ALL sensor nonwear markers for this file that overlap the table's time range.
    # Don't filter by analysis_date — sensor nonwear spans real timestamps and the
    # table window can cross date boundaries.
    if not onset_rows and not offset_rows:
        # No activity data in either window — skip sensor nonwear query
        sensor_nw_markers = []
    else:
        table_min_ts = min(
            naive_to_unix(onset_rows[0].timestamp) if onset_rows else naive_to_unix(offset_rows[0].timestamp),
            naive_to_unix(offset_rows[0].timestamp) if offset_rows else naive_to_unix(onset_rows[0].timestamp),
        )
        table_max_ts = max(
            naive_to_unix(onset_rows[-1].timestamp) if onset_rows else naive_to_unix(offset_rows[-1].timestamp),
            naive_to_unix(offset_rows[-1].timestamp) if offset_rows else naive_to_unix(onset_rows[-1].timestamp),
        )
        sensor_nw_result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.marker_category == MarkerCategory.NONWEAR,
                    Marker.marker_type == "sensor",
                    Marker.start_timestamp <= table_max_ts,
                    Marker.end_timestamp >= table_min_ts,
                )
            )
        )
        sensor_nw_markers = list(sensor_nw_result.scalars().all())

    def is_in_nonwear(ts: float) -> bool:
        """Check if timestamp falls within any sensor nonwear period."""
        for nw in sensor_nw_markers:
            if nw.start_timestamp and nw.end_timestamp:
                if nw.start_timestamp <= ts <= nw.end_timestamp:
                    return True
        return False

    # Run algorithms on the data ranges
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column

    choi_column = await get_choi_column(db, username)

    def compute_algorithm_results(rows: list[RawActivityData]) -> tuple[list[int], list[int]]:
        """Compute Sadeh and Choi results for a set of rows."""
        if not rows:
            return [], []

        axis_y_data = [row.axis_y or 0 for row in rows]

        # Sadeh algorithm
        sadeh = SadehAlgorithm()
        sleep_results = sadeh.score(axis_y_data)

        # Choi nonwear detection using user's preferred column
        choi = ChoiAlgorithm()
        choi_input = extract_choi_input(rows, choi_column)
        choi_results = choi.detect_mask(choi_input)

        return sleep_results, choi_results

    onset_sleep, onset_choi = compute_algorithm_results(onset_rows)
    offset_sleep, offset_choi = compute_algorithm_results(offset_rows)

    # Convert to response format with all columns
    onset_data = [
        OnsetOffsetDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=onset_sleep[i] if i < len(onset_sleep) else None,
            choi_result=onset_choi[i] if i < len(onset_choi) else None,
            is_nonwear=is_in_nonwear(naive_to_unix(row.timestamp)),
        )
        for i, row in enumerate(onset_rows)
    ]

    offset_data = [
        OnsetOffsetDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=offset_sleep[i] if i < len(offset_sleep) else None,
            choi_result=offset_choi[i] if i < len(offset_choi) else None,
            is_nonwear=is_in_nonwear(naive_to_unix(row.timestamp)),
        )
        for i, row in enumerate(offset_rows)
    ]

    return OnsetOffsetTableResponse(
        onset_data=onset_data,
        offset_data=offset_data,
        period_index=period_index,
    )


class FullTableDataPoint(BaseModel):
    """Single data point for full 48h table."""

    timestamp: float
    datetime_str: str
    axis_y: int
    vector_magnitude: int
    algorithm_result: int | None = None
    choi_result: int | None = None
    is_nonwear: bool = False


class FullTableResponse(BaseModel):
    """Response with full 48h of data for popout table."""

    data: list[FullTableDataPoint] = Field(default_factory=list)
    total_rows: int = 0
    start_time: str | None = None
    end_time: str | None = None


@router.get("/{file_id}/{analysis_date}/table-full")
async def get_full_table_data(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> FullTableResponse:
    """
    Get full 48h of activity data for popout table display.

    Returns all epochs from noon of analysis_date to noon of next day.
    Includes algorithm results and nonwear detection.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()

    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Get 24h of data (noon to noon)
    start_time = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
    end_time = start_time + timedelta(hours=24)

    activity_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= start_time,
                RawActivityData.timestamp < end_time,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    rows = activity_result.scalars().all()

    if not rows:
        return FullTableResponse(data=[], total_rows=0)

    # Get sensor nonwear markers (from diary/CSV upload) for the "N" column.
    # Query by timestamp overlap with the table's data range (not analysis_date)
    # so sensor nonwear always shows regardless of which date it was stored under.
    table_min_ts = naive_to_unix(rows[0].timestamp)
    table_max_ts = naive_to_unix(rows[-1].timestamp)
    sensor_nw_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.marker_category == MarkerCategory.NONWEAR,
                Marker.marker_type == "sensor",
                Marker.start_timestamp <= table_max_ts,
                Marker.end_timestamp >= table_min_ts,
            )
        )
    )
    sensor_nw_markers = list(sensor_nw_result.scalars().all())

    def is_in_nonwear(ts: float) -> bool:
        """Check if timestamp falls within any sensor nonwear period."""
        for nw in sensor_nw_markers:
            if nw.start_timestamp and nw.end_timestamp:
                if nw.start_timestamp <= ts <= nw.end_timestamp:
                    return True
        return False

    # Run algorithms on full data
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column

    axis_y_data = [row.axis_y or 0 for row in rows]

    sadeh = SadehAlgorithm()
    sleep_results = sadeh.score(axis_y_data)

    choi_column = await get_choi_column(db, username)
    choi = ChoiAlgorithm()
    choi_results = choi.detect_mask(extract_choi_input(rows, choi_column))

    # Convert to response format
    data = [
        FullTableDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=sleep_results[i] if i < len(sleep_results) else None,
            choi_result=choi_results[i] if i < len(choi_results) else None,
            is_nonwear=is_in_nonwear(naive_to_unix(row.timestamp)),
        )
        for i, row in enumerate(rows)
    ]

    return FullTableResponse(
        data=data,
        total_rows=len(data),
        start_time=rows[0].timestamp.strftime("%Y-%m-%d %H:%M:%S") if rows else None,
        end_time=rows[-1].timestamp.strftime("%Y-%m-%d %H:%M:%S") if rows else None,
    )


# =============================================================================
# Nonwear Sensor Data Upload
# =============================================================================


class NonwearUploadResponse(BaseModel):
    """Response after uploading nonwear sensor CSV."""

    dates_imported: int
    markers_created: int
    dates_skipped: int
    errors: list[str] = Field(default_factory=list)
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_identifiers: list[str] = Field(default_factory=list)
    ambiguous_identifiers: list[str] = Field(default_factory=list)


@router.post("/nonwear/upload")
async def upload_nonwear_csv(
    file: Annotated[UploadFile, File(description="Nonwear CSV file")],
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> NonwearUploadResponse:
    """
    Upload nonwear sensor data CSV (study-wide).

    Matches rows to activity files by participant_id column.

    Expected CSV columns (case-insensitive):
    - participant_id: Participant identifier (matched to activity filenames)
    - date / startdate: Analysis date (YYYY-MM-DD or MM/DD/YYYY)
    - start_time / nonwear_start: Nonwear start time (HH:MM)
    - end_time / nonwear_end: Nonwear end time (HH:MM)

    For each date+file, existing nonwear markers are replaced.
    Multiple nonwear periods per date are supported (one row per period).
    """
    return await _process_nonwear_csv(file, db, username, file_id=None)


@router.post("/{file_id}/nonwear/upload")
async def upload_nonwear_csv_for_file(
    file_id: int,
    file: Annotated[UploadFile, File(description="Nonwear CSV file")],
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> NonwearUploadResponse:
    """
    Upload nonwear sensor data CSV for a specific activity file (legacy).

    Does not require participant_id — all rows go to the specified file.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file_obj = file_result.scalar_one_or_none()
    if not file_obj or is_excluded_file_obj(file_obj):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return await _process_nonwear_csv(file, db, username, file_id=file_id)


async def _process_nonwear_csv(
    file: UploadFile,
    db,
    username: str,
    file_id: int | None,
) -> NonwearUploadResponse:
    """Shared implementation for nonwear CSV processing."""
    from collections import defaultdict
    from io import StringIO

    import polars as pl

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            text = content.decode("cp1252")

    lines = text.splitlines()
    filtered_lines = [line for line in lines if not line.startswith("#")]
    text = "\n".join(filtered_lines)

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty after removing comment lines",
        )

    try:
        df = pl.read_csv(StringIO(text))
    except Exception as e:
        logger.exception("Failed to parse CSV: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {e}",
        ) from e

    df = df.rename({col: col.lower().strip().replace(" ", "_") for col in df.columns})

    date_col = None
    for col in ["date", "startdate", "analysis_date", "diary_date", "date_of_last_night"]:
        if col in df.columns:
            date_col = col
            break

    start_col = None
    for col in [
        "start_time",
        "start",
        "nonwear_start",
        "nonwear_start_time",
        "nw_start",
        "start_datetime",
        "nonwear_start_datetime",
    ]:
        if col in df.columns:
            start_col = col
            break
    end_col = None
    for col in [
        "end_time",
        "end",
        "nonwear_end",
        "nonwear_end_time",
        "nw_end",
        "end_datetime",
        "nonwear_end_datetime",
    ]:
        if col in df.columns:
            end_col = col
            break
    if start_col is None or end_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have start and end columns. Found columns: {list(df.columns)}",
        )

    if date_col is None and start_col:
        date_col = None

    pid_col = None
    nw_filename_col = None
    timepoint_col = None
    filename_pid: str | None = None
    all_files: list[FileModel] = []
    identities = []
    filename_to_files: dict[str, list[FileModel]] = {}
    stem_to_files: dict[str, list[FileModel]] = {}
    pid_to_identities: dict[str, list] = {}
    pid_tp_to_identities: dict[tuple[str, str], list] = {}
    unmatched_identifiers: set[str] = set()
    ambiguous_identifiers: set[str] = set()

    if file_id is None:
        for col in ["filename", "file", "file_name"]:
            if col in df.columns:
                nw_filename_col = col
                break

        if nw_filename_col is None:
            for col in ["participant_id", "participantid", "pid", "subject_id", "id"]:
                if col in df.columns:
                    pid_col = col
                    break
            for col in ["participant_timepoint", "timepoint", "tp"]:
                if col in df.columns:
                    timepoint_col = col
                    break
            if pid_col is None:
                filename_pid = filename_stem(file.filename)
                if not filename_pid:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="CSV must have participant_id or filename column, or upload filename must identify participant",
                    )

        files_result = await db.execute(select(FileModel))
        all_files = [f for f in files_result.scalars().all() if not is_excluded_file_obj(f)]
        identities = [build_file_identity(f) for f in all_files]
        for ident in identities:
            filename_to_files.setdefault(ident.normalized_filename, []).append(ident.file)
            stem_to_files.setdefault(ident.normalized_stem, []).append(ident.file)
            if ident.participant_id_norm:
                pid_to_identities.setdefault(ident.participant_id_norm, []).append(ident)
                if ident.timepoint_norm:
                    pid_tp_to_identities.setdefault(
                        (ident.participant_id_norm, ident.timepoint_norm), []
                    ).append(ident)
            if ident.short_pid_norm:
                pid_to_identities.setdefault(ident.short_pid_norm, []).append(ident)
                if ident.timepoint_norm:
                    pid_tp_to_identities.setdefault(
                        (ident.short_pid_norm, ident.timepoint_norm), []
                    ).append(ident)

    file_date_periods: dict[tuple[int, date], list[tuple[str, str]]] = defaultdict(list)
    dates_skipped = 0
    matched_rows = 0
    total_rows = int(df.height)
    errors: list[str] = []

    for row in df.iter_rows(named=True):
        matched_file_ids: list[int] = [file_id] if file_id is not None else []

        # Parse date early for date-range matching when multiple files share a PID
        start_raw = str(row[start_col]).strip()
        end_raw = str(row[end_col]).strip()
        row_date_for_match: date | None = None
        if date_col is not None:
            row_date_for_match = _parse_nonwear_date(str(row[date_col]).strip())
        elif start_raw and start_raw.lower() not in ("nan", "none"):
            row_date_for_match = _parse_nonwear_date(start_raw.split(" ")[0].split("T")[0])

        if not matched_file_ids:
            if nw_filename_col is not None:
                raw_fn = normalize_filename(row.get(nw_filename_col))
                if raw_fn is None:
                    dates_skipped += 1
                    continue
                candidates = filename_to_files.get(raw_fn, [])
                if not candidates:
                    raw_stem = filename_stem(raw_fn)
                    if raw_stem:
                        candidates = stem_to_files.get(raw_stem, [])
                    if not candidates and raw_stem:
                        fuzzy = [
                            ident.file for ident in identities
                            if raw_stem in ident.normalized_stem or ident.normalized_stem in raw_stem
                        ]
                        seen_ids: set[int] = set()
                        dedup: list[FileModel] = []
                        for f in fuzzy:
                            if f.id not in seen_ids:
                                seen_ids.add(f.id)
                                dedup.append(f)
                        candidates = dedup
                if len(candidates) == 1:
                    matched_file_ids = [candidates[0].id]
                elif len(candidates) > 1:
                    covering = _files_covering_date(candidates, row_date_for_match)
                    if covering:
                        matched_file_ids = [f.id for f in covering]
                    else:
                        ambiguous_identifiers.add(raw_fn)
                        dates_skipped += 1
                        continue
                else:
                    unmatched_identifiers.add(raw_fn)
                    dates_skipped += 1
                    continue
            else:
                pid_norm = normalize_participant_id(
                    row.get(pid_col) if pid_col is not None else filename_pid
                )
                if pid_norm is None:
                    dates_skipped += 1
                    continue

                tp_norm = normalize_timepoint(row.get(timepoint_col)) if timepoint_col else None
                candidates_ident = []

                if tp_norm:
                    candidates_ident = pid_tp_to_identities.get((pid_norm, tp_norm), [])
                    if not candidates_ident:
                        pid_pool = pid_to_identities.get(pid_norm, [])
                        if pid_pool:
                            candidates_ident = [
                                ident for ident in pid_pool
                                if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename
                            ]
                else:
                    candidates_ident = pid_to_identities.get(pid_norm, [])

                if not candidates_ident:
                    fuzzy_all = [
                        ident for ident in identities if pid_norm in ident.normalized_filename
                    ]
                    if tp_norm and len(fuzzy_all) > 1:
                        fuzzy_filtered = [
                            ident for ident in fuzzy_all
                            if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename
                        ]
                        candidates_ident = fuzzy_filtered if fuzzy_filtered else fuzzy_all
                    else:
                        candidates_ident = fuzzy_all

                seen_ids: set[int] = set()
                dedup_ident = []
                for ident in candidates_ident:
                    if ident.file.id not in seen_ids:
                        seen_ids.add(ident.file.id)
                        dedup_ident.append(ident)

                if len(dedup_ident) == 1:
                    matched_file_ids = [dedup_ident[0].file.id]
                elif len(dedup_ident) > 1:
                    covering = _files_covering_date(dedup_ident, row_date_for_match)
                    if covering:
                        matched_file_ids = [f.id for f in covering]
                    else:
                        label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                        ambiguous_identifiers.add(label)
                        dates_skipped += 1
                        continue
                else:
                    label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                    unmatched_identifiers.add(label)
                    dates_skipped += 1
                    continue

            matched_rows += 1
        if (
            not start_raw
            or not end_raw
            or start_raw.lower() in ("nan", "none")
            or end_raw.lower() in ("nan", "none")
        ):
            dates_skipped += 1
            continue

        if date_col is not None:
            date_str = str(row[date_col]).strip()
            analysis_date_val = _parse_nonwear_date(date_str)
        else:
            analysis_date_val = _parse_nonwear_date(start_raw.split(" ")[0].split("T")[0])

        if analysis_date_val is None:
            errors.append(f"Invalid date from row: {start_raw}")
            dates_skipped += 1
            continue

        start_time = _extract_time(start_raw)
        end_time = _extract_time(end_raw)
        if start_time is None or end_time is None:
            errors.append(f"Invalid time on {analysis_date_val}: {start_raw} - {end_raw}")
            dates_skipped += 1
            continue

        for fid in matched_file_ids:
            file_date_periods[(fid, analysis_date_val)].append((start_time, end_time))

    dates_imported = 0
    markers_created = 0

    # Delete ALL existing sensor nonwear for each affected file before inserting.
    # Per-date deletion is unreliable because analysis_date may not match between
    # old and new uploads (e.g., different CSV date formats or noon-vs-calendar day).
    deleted_file_ids: set[int] = set()
    for fid, _ in file_date_periods:
        if fid not in deleted_file_ids:
            await db.execute(
                delete(Marker).where(
                    and_(
                        Marker.file_id == fid,
                        Marker.marker_category == MarkerCategory.NONWEAR,
                        Marker.marker_type == "sensor",
                    )
                )
            )
            deleted_file_ids.add(fid)

    for (fid, analysis_date_val), periods in file_date_periods.items():
        for i, (start_time, end_time) in enumerate(periods):
            start_h, start_m = map(int, start_time.split(":"))
            end_h, end_m = map(int, end_time.split(":"))

            start_dt = datetime(
                analysis_date_val.year,
                analysis_date_val.month,
                analysis_date_val.day,
                start_h,
                start_m,
            )
            end_dt = datetime(
                analysis_date_val.year,
                analysis_date_val.month,
                analysis_date_val.day,
                end_h,
                end_m,
            )
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            start_ts = float(calendar.timegm(start_dt.timetuple()))
            end_ts = float(calendar.timegm(end_dt.timetuple()))

            db_marker = Marker(
                file_id=fid,
                analysis_date=analysis_date_val,
                marker_category=MarkerCategory.NONWEAR,
                marker_type="sensor",
                start_timestamp=start_ts,
                end_timestamp=end_ts,
                period_index=i + 1,
                created_by=username,
            )
            db.add(db_marker)
            markers_created += 1

        dates_imported += 1

    await db.commit()

    if unmatched_identifiers:
        errors.insert(0, f"No matching activity files for: {', '.join(sorted(unmatched_identifiers))}")
    if ambiguous_identifiers:
        errors.insert(0, f"Ambiguous file matches (use filename or timepoint): {', '.join(sorted(ambiguous_identifiers))}")

    return NonwearUploadResponse(
        dates_imported=dates_imported,
        markers_created=markers_created,
        dates_skipped=dates_skipped,
        errors=errors,
        total_rows=total_rows,
        matched_rows=matched_rows,
        unmatched_identifiers=sorted(unmatched_identifiers),
        ambiguous_identifiers=sorted(ambiguous_identifiers),
    )


def _extract_time(value: str) -> str | None:
    """
    Extract HH:MM time from a time or datetime string.

    Handles:
      - "10:30" → "10:30"
      - "2025-08-01 10:30:00" → "10:30"
      - "2025-08-01T10:30:00" → "10:30"
      - "10:30 AM" → "10:30"  (already HH:MM, AM/PM stripped)
    """
    v = value.strip()
    if not v or v.lower() in ("nan", "none", "null", ""):
        return None

    # If it contains a space or T, try to extract time portion from datetime
    time_part = v
    if "T" in v:
        time_part = v.split("T")[1].split("+")[0].split("Z")[0]
    elif " " in v:
        # Could be "2025-08-01 10:30:00" or "10:30 AM"
        parts = v.split(" ", 1)
        # If first part looks like a date (contains -), use second part as time
        if "-" in parts[0] or "/" in parts[0]:
            time_part = parts[1]
        # Otherwise keep full string (it may be "10:30 AM")

    # Strip AM/PM for now (we just need HH:MM)
    time_part = time_part.strip()
    is_pm = "PM" in time_part.upper()
    is_am = "AM" in time_part.upper()
    time_part = time_part.upper().replace("PM", "").replace("AM", "").strip()

    try:
        colon_parts = time_part.split(":")
        h = int(colon_parts[0])
        m = int(colon_parts[1]) if len(colon_parts) > 1 else 0

        if is_am or is_pm:
            if h == 12:
                h = 0 if is_am else 12
            elif is_pm:
                h += 12

        return f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        return None


def _files_covering_date(candidates: list, row_date: date | None) -> list:
    """Return all files whose start_time..end_time range contains row_date.

    Candidates may be FileModel objects or FileIdentity objects (uses ``.file``).
    """
    if row_date is None or not candidates:
        return []

    matched = []
    for c in candidates:
        f = getattr(c, "file", c)  # FileIdentity.file or raw FileModel
        st = getattr(f, "start_time", None)
        et = getattr(f, "end_time", None)
        if st is None or et is None:
            continue
        if st.date() <= row_date <= et.date():
            matched.append(f)

    return matched


def _parse_nonwear_date(date_str: str) -> date | None:
    """Parse a date string, trying multiple formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _parse_full_datetime(dt_str: str) -> datetime | None:
    """Parse a full datetime string (from web export Onset/Offset Datetime columns)."""
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


# =============================================================================
# Sleep Marker Import (Desktop + Web Export)
# =============================================================================


class SleepImportResponse(BaseModel):
    """Response after importing sleep marker CSV (desktop or web export)."""

    dates_imported: int
    markers_created: int
    no_sleep_dates: int
    dates_skipped: int
    errors: list[str] = Field(default_factory=list)
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_identifiers: list[str] = Field(default_factory=list)
    ambiguous_identifiers: list[str] = Field(default_factory=list)


@router.post("/sleep/upload")
async def upload_sleep_csv(
    file: Annotated[UploadFile, File(description="Desktop sleep marker CSV export")],
    background_tasks: BackgroundTasks,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> SleepImportResponse:
    """
    Upload a sleep marker export CSV (desktop or web app format).

    Supports both desktop export CSVs (with onset_time/offset_time) and
    web export CSVs (with Onset Datetime/Offset Datetime, Study Date, etc.).

    Matches rows to activity files by `filename` column, or by
    `participant_id` + `timepoint` columns when no filename is present.

    For each (file, date), existing sleep markers are replaced and metrics recalculated.

    Expected CSV columns (comment lines starting with # are stripped):
    - filename OR (numerical_participant_id + participant_timepoint)
    - sleep_date / study_date / date: Analysis date (YYYY-MM-DD)
    - onset_time + offset_time (HH:MM), OR onset_datetime + offset_datetime (full datetime)
    - marker_type (optional): MAIN_SLEEP / NAP (default: MAIN_SLEEP)
    - marker_index / period_index (optional): Period index (default: sequential)
    - is_no_sleep (optional): TRUE/FALSE — marks date as no-sleep
    - needs_consensus (optional): TRUE/FALSE — flags for consensus review
    - Rows with NO_SLEEP onset/offset are treated as no-sleep dates.
    """
    return await _process_sleep_csv(file, background_tasks, db, username)


async def _process_sleep_csv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db,
    username: str,
) -> SleepImportResponse:
    """Process a sleep marker CSV export (desktop or web format)."""
    from collections import defaultdict
    from io import StringIO

    import polars as pl

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            text = content.decode("cp1252")

    lines = text.splitlines()
    filtered_lines = [line for line in lines if not line.startswith("#")]
    text = "\n".join(filtered_lines)

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty after removing comment lines",
        )

    try:
        df = pl.read_csv(StringIO(text))
    except Exception as e:
        logger.exception("Failed to parse CSV: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {e}",
        ) from e

    df = df.rename({col: col.lower().strip().replace(" ", "_") for col in df.columns})

    # --- Detect columns (supports both desktop and web export formats) ---
    # After rename, web export "Study Date" → "study_date", "Period Index" → "period_index", etc.

    filename_col = None
    for col in ["filename", "file", "file_name"]:
        if col in df.columns:
            filename_col = col
            break

    pid_col = None
    timepoint_col = None
    filename_pid: str | None = None
    if filename_col is None:
        for col in ["numerical_participant_id", "participant_id", "participantid", "pid"]:
            if col in df.columns:
                pid_col = col
                break
        for col in ["participant_timepoint", "timepoint", "tp"]:
            if col in df.columns:
                timepoint_col = col
                break
        if pid_col is None:
            filename_pid = filename_stem(file.filename)
            if not filename_pid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV must have filename or participant_id columns, or upload filename must identify participant",
                )

    date_col = None
    for col in ["sleep_date", "study_date", "date", "analysis_date"]:
        if col in df.columns:
            date_col = col
            break
    if date_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have a date column (sleep_date, study_date, date, or analysis_date). Found: {list(df.columns)}",
        )

    # Full datetime columns (web export: "Onset Datetime", "Offset Datetime")
    onset_datetime_col = None
    for col in ["onset_datetime", "onset_date_time"]:
        if col in df.columns:
            onset_datetime_col = col
            break

    offset_datetime_col = None
    for col in ["offset_datetime", "offset_date_time"]:
        if col in df.columns:
            offset_datetime_col = col
            break

    onset_date_col = "onset_date" if "onset_date" in df.columns else None

    onset_time_col = None
    for col in ["onset_time", "onset", "sleep_onset"]:
        if col in df.columns:
            onset_time_col = col
            break

    offset_date_col = "offset_date" if "offset_date" in df.columns else None

    offset_time_col = None
    for col in ["offset_time", "offset", "sleep_offset"]:
        if col in df.columns:
            offset_time_col = col
            break

    # Must have either full datetime columns or time columns
    if onset_time_col is None and onset_datetime_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have onset_time or onset_datetime column. Found: {list(df.columns)}",
        )
    if offset_time_col is None and offset_datetime_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have offset_time or offset_datetime column. Found: {list(df.columns)}",
        )

    type_col = None
    for col in ["marker_type", "type"]:
        if col in df.columns:
            type_col = col
            break

    index_col = None
    for col in ["marker_index", "period_index", "index"]:
        if col in df.columns:
            index_col = col
            break

    consensus_col = None
    for col in ["needs_consensus", "needs_consensus_review"]:
        if col in df.columns:
            consensus_col = col
            break

    # Web export "Is No Sleep" column (TRUE/FALSE)
    no_sleep_col = None
    for col in ["is_no_sleep", "no_sleep"]:
        if col in df.columns:
            no_sleep_col = col
            break

    # Web export "Scored By" column — use for attribution
    scored_by_col = None
    for col in ["scored_by", "scorer", "created_by"]:
        if col in df.columns:
            scored_by_col = col
            break

    files_result = await db.execute(select(FileModel))
    all_files = [f for f in files_result.scalars().all() if not is_excluded_file_obj(f)]
    identities = [build_file_identity(f) for f in all_files]

    filename_to_files: dict[str, list[FileModel]] = {}
    stem_to_files: dict[str, list[FileModel]] = {}
    pid_to_identities: dict[str, list] = {}
    pid_tp_to_identities: dict[tuple[str, str], list] = {}

    for ident in identities:
        filename_to_files.setdefault(ident.normalized_filename, []).append(ident.file)
        stem_to_files.setdefault(ident.normalized_stem, []).append(ident.file)
        if ident.participant_id_norm:
            pid_to_identities.setdefault(ident.participant_id_norm, []).append(ident)
            if ident.timepoint_norm:
                pid_tp_to_identities.setdefault((ident.participant_id_norm, ident.timepoint_norm), []).append(ident)
        if ident.short_pid_norm:
            pid_to_identities.setdefault(ident.short_pid_norm, []).append(ident)
            if ident.timepoint_norm:
                pid_tp_to_identities.setdefault((ident.short_pid_norm, ident.timepoint_norm), []).append(ident)

    file_date_periods: dict[tuple[int, date], list[dict]] = defaultdict(list)
    no_sleep_dates_set: set[tuple[int, date]] = set()
    consensus_dates_set: set[tuple[int, date]] = set()
    dates_skipped = 0
    matched_rows = 0
    total_rows = int(df.height)
    errors: list[str] = []
    unmatched_identifiers: set[str] = set()
    ambiguous_identifiers: set[str] = set()

    for row in df.iter_rows(named=True):
        matched_files: list[FileModel] = []

        # Parse date early for disambiguation when multiple files match same PID
        date_str = str(row[date_col]).strip()
        analysis_date_val = _parse_nonwear_date(date_str)
        if analysis_date_val is None:
            errors.append(f"Invalid date: {date_str}")
            dates_skipped += 1
            continue

        if filename_col is not None:
            row_filename = normalize_filename(row.get(filename_col))
            if row_filename is None:
                dates_skipped += 1
                continue

            candidates = filename_to_files.get(row_filename, [])
            if not candidates:
                row_stem = filename_stem(row_filename)
                if row_stem:
                    candidates = stem_to_files.get(row_stem, [])
                if not candidates and row_stem:
                    fuzzy = [
                        ident.file
                        for ident in identities
                        if row_stem in ident.normalized_stem or ident.normalized_stem in row_stem
                    ]
                    seen_ids: set[int] = set()
                    dedup: list[FileModel] = []
                    for file_obj in fuzzy:
                        if file_obj.id not in seen_ids:
                            seen_ids.add(file_obj.id)
                            dedup.append(file_obj)
                    candidates = dedup

            if len(candidates) == 1:
                matched_files = candidates
            elif len(candidates) > 1:
                matched_files = _files_covering_date(candidates, analysis_date_val)
                if not matched_files:
                    ambiguous_identifiers.add(row_filename)
                    dates_skipped += 1
                    continue
            else:
                unmatched_identifiers.add(row_filename)
                dates_skipped += 1
                continue
        else:
            pid_norm = normalize_participant_id(row.get(pid_col) if pid_col is not None else filename_pid)
            if pid_norm is None:
                dates_skipped += 1
                continue

            tp_norm = normalize_timepoint(row.get(timepoint_col)) if timepoint_col else None
            candidates_ident = []

            if tp_norm:
                candidates_ident = pid_tp_to_identities.get((pid_norm, tp_norm), [])
                if not candidates_ident:
                    pid_pool = pid_to_identities.get(pid_norm, [])
                    if pid_pool:
                        candidates_ident = [
                            ident
                            for ident in pid_pool
                            if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename
                        ]
            else:
                candidates_ident = pid_to_identities.get(pid_norm, [])

            if not candidates_ident:
                fuzzy_all = [ident for ident in identities if pid_norm in ident.normalized_filename]
                if tp_norm and len(fuzzy_all) > 1:
                    fuzzy_filtered = [
                        ident for ident in fuzzy_all
                        if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename
                    ]
                    candidates_ident = fuzzy_filtered if fuzzy_filtered else fuzzy_all
                else:
                    candidates_ident = fuzzy_all

            seen_ids: set[int] = set()
            dedup_ident = []
            for ident in candidates_ident:
                if ident.file.id not in seen_ids:
                    seen_ids.add(ident.file.id)
                    dedup_ident.append(ident)

            if len(dedup_ident) == 1:
                matched_files = [dedup_ident[0].file]
            elif len(dedup_ident) > 1:
                matched_files = _files_covering_date(dedup_ident, analysis_date_val)
                if not matched_files:
                    label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                    ambiguous_identifiers.add(label)
                    dates_skipped += 1
                    continue
            else:
                label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                unmatched_identifiers.add(label)
                dates_skipped += 1
                continue

        matched_rows += 1
        matched_file_ids = [f.id for f in matched_files]

        # Check for "no sleep" via dedicated column (web export) or NO_SLEEP sentinel (desktop)
        if no_sleep_col is not None:
            raw_no_sleep = str(row[no_sleep_col]).strip().lower()
            if raw_no_sleep in ("true", "1", "yes"):
                for fid in matched_file_ids:
                    no_sleep_dates_set.add((fid, analysis_date_val))
                if consensus_col is not None:
                    raw_consensus = str(row[consensus_col]).strip().lower()
                    if raw_consensus in ("true", "1", "yes"):
                        for fid in matched_file_ids:
                            consensus_dates_set.add((fid, analysis_date_val))
                continue

        onset_raw = str(row[onset_time_col]).strip() if onset_time_col else ""
        offset_raw = str(row[offset_time_col]).strip() if offset_time_col else ""

        if onset_raw.upper() == "NO_SLEEP" or offset_raw.upper() == "NO_SLEEP":
            for fid in matched_file_ids:
                no_sleep_dates_set.add((fid, analysis_date_val))
            if consensus_col is not None:
                raw_consensus = str(row[consensus_col]).strip().lower()
                if raw_consensus in ("true", "1", "yes"):
                    for fid in matched_file_ids:
                        consensus_dates_set.add((fid, analysis_date_val))
            continue

        # Try full datetime columns first (web export: "Onset Datetime" / "Offset Datetime")
        onset_ts: float | None = None
        offset_ts: float | None = None

        if onset_datetime_col is not None and offset_datetime_col is not None:
            onset_dt_raw = str(row[onset_datetime_col]).strip()
            offset_dt_raw = str(row[offset_datetime_col]).strip()
            if onset_dt_raw.upper() not in ("NAN", "NONE", "NULL", ""):
                onset_dt_parsed = _parse_full_datetime(onset_dt_raw)
                offset_dt_parsed = _parse_full_datetime(offset_dt_raw)
                if onset_dt_parsed is not None and offset_dt_parsed is not None:
                    onset_ts = float(calendar.timegm(onset_dt_parsed.timetuple()))
                    offset_ts = float(calendar.timegm(offset_dt_parsed.timetuple()))

        # Fall back to time columns (desktop export or web export with Onset Time/Offset Time)
        if onset_ts is None or offset_ts is None:
            if onset_raw.upper() in ("NAN", "NONE", "NULL", "") or offset_raw.upper() in ("NAN", "NONE", "NULL", ""):
                dates_skipped += 1
                continue

            if onset_date_col is not None:
                onset_date_str = str(row[onset_date_col]).strip()
                onset_date_val = _parse_nonwear_date(onset_date_str)
            else:
                onset_date_val = analysis_date_val

            onset_time_str = _extract_time(onset_raw)
            if onset_date_val is None or onset_time_str is None:
                errors.append(f"Invalid onset on {date_str}: {onset_raw}")
                dates_skipped += 1
                continue

            if offset_date_col is not None:
                offset_date_str = str(row[offset_date_col]).strip()
                offset_date_val = _parse_nonwear_date(offset_date_str)
            else:
                offset_date_val = None

            offset_time_str = _extract_time(offset_raw)
            if offset_time_str is None:
                errors.append(f"Invalid offset on {date_str}: {offset_raw}")
                dates_skipped += 1
                continue

            onset_h, onset_m = map(int, onset_time_str.split(":"))
            # For noon-to-noon analysis windows: onset times before noon (e.g. 12:30 AM)
            # belong to the NEXT calendar day relative to analysis_date, because a sleep
            # onset after midnight means the night rolled over past midnight.
            if onset_date_col is None and onset_h < 12:
                onset_day = onset_date_val + timedelta(days=1)
            else:
                onset_day = onset_date_val
            onset_dt = datetime(onset_day.year, onset_day.month, onset_day.day, onset_h, onset_m)

            offset_h, offset_m = map(int, offset_time_str.split(":"))
            if offset_date_val is not None:
                offset_dt = datetime(offset_date_val.year, offset_date_val.month, offset_date_val.day, offset_h, offset_m)
            else:
                offset_dt = datetime(onset_day.year, onset_day.month, onset_day.day, offset_h, offset_m)
                if offset_dt <= onset_dt:
                    offset_dt += timedelta(days=1)

            onset_ts = float(calendar.timegm(onset_dt.timetuple()))
            offset_ts = float(calendar.timegm(offset_dt.timetuple()))

        marker_type = MarkerType.MAIN_SLEEP
        if type_col is not None:
            raw_type = str(row[type_col]).strip().upper()
            if raw_type == "NAP":
                marker_type = MarkerType.NAP
            elif raw_type == "MAIN_SLEEP":
                marker_type = MarkerType.MAIN_SLEEP

        marker_index = None
        if index_col is not None:
            try:
                marker_index = int(float(row[index_col]))
            except (ValueError, TypeError):
                marker_index = None

        if consensus_col is not None:
            raw_consensus = str(row[consensus_col]).strip().lower()
            if raw_consensus in ("true", "1", "yes"):
                for fid in matched_file_ids:
                    consensus_dates_set.add((fid, analysis_date_val))

        for fid in matched_file_ids:
            file_date_periods[(fid, analysis_date_val)].append(
                {
                    "onset_ts": onset_ts,
                    "offset_ts": offset_ts,
                    "marker_type": marker_type,
                    "marker_index": marker_index,
                }
            )

    dates_imported = 0
    markers_created = 0

    for (fid, analysis_date_val), periods in file_date_periods.items():
        await db.execute(
            delete(Marker).where(
                and_(
                    Marker.file_id == fid,
                    Marker.analysis_date == analysis_date_val,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    or_(Marker.created_by == username, Marker.created_by.is_(None)),
                )
            )
        )

        sleep_period_models: list[SleepPeriod] = []
        for i, period in enumerate(periods):
            idx = period["marker_index"] if period["marker_index"] is not None else i + 1
            db_marker = Marker(
                file_id=fid,
                analysis_date=analysis_date_val,
                marker_category=MarkerCategory.SLEEP,
                marker_type=period["marker_type"].value,
                start_timestamp=period["onset_ts"],
                end_timestamp=period["offset_ts"],
                period_index=idx,
                created_by=username,
            )
            db.add(db_marker)
            markers_created += 1
            sleep_period_models.append(
                SleepPeriod(
                    onset_timestamp=period["onset_ts"],
                    offset_timestamp=period["offset_ts"],
                    marker_index=idx,
                    marker_type=period["marker_type"],
                )
            )

        dates_imported += 1
        background_tasks.add_task(
            _calculate_and_store_metrics,
            fid,
            analysis_date_val,
            sleep_period_models,
            username,
        )
        background_tasks.add_task(
            _update_user_annotation,
            fid,
            analysis_date_val,
            username,
            sleep_period_models,
            None,
            None,
            "Imported from desktop export",
            False,
            (fid, analysis_date_val) in consensus_dates_set,
        )

    no_sleep_dates_set -= set(file_date_periods.keys())

    for fid, analysis_date_val in no_sleep_dates_set:
        await db.execute(
            delete(Marker).where(
                and_(
                    Marker.file_id == fid,
                    Marker.analysis_date == analysis_date_val,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    or_(Marker.created_by == username, Marker.created_by.is_(None)),
                )
            )
        )
        background_tasks.add_task(
            _update_user_annotation,
            fid,
            analysis_date_val,
            username,
            None,
            None,
            None,
            "Imported from desktop export (no sleep)",
            True,
            (fid, analysis_date_val) in consensus_dates_set,
        )

    await db.commit()

    if unmatched_identifiers:
        errors.insert(0, f"No matching activity files for: {', '.join(sorted(unmatched_identifiers))}")
    if ambiguous_identifiers:
        errors.insert(0, f"Ambiguous file matches (use filename or timepoint): {', '.join(sorted(ambiguous_identifiers))}")

    return SleepImportResponse(
        dates_imported=dates_imported,
        markers_created=markers_created,
        no_sleep_dates=len(no_sleep_dates_set),
        dates_skipped=dates_skipped,
        errors=errors,
        total_rows=total_rows,
        matched_rows=matched_rows,
        unmatched_identifiers=sorted(unmatched_identifiers),
        ambiguous_identifiers=sorted(ambiguous_identifiers),
    )
# Background Tasks
# =============================================================================


async def _update_user_annotation(
    file_id: int,
    analysis_date: date,
    username: str,
    sleep_markers: list[SleepPeriod] | None,
    nonwear_markers: list[ManualNonwearPeriod] | None,
    algorithm_used: AlgorithmType | None,
    notes: str | None,
    is_no_sleep: bool = False,
    needs_consensus: bool = False,
) -> None:
    """Update or create user annotation for consensus tracking."""
    from sleep_scoring_web.db.session import async_session_maker

    async with async_session_maker() as db:
        # Convert markers to dicts
        sleep_json = [m.model_dump() for m in sleep_markers] if sleep_markers else None
        nonwear_json = [m.model_dump() for m in nonwear_markers] if nonwear_markers else None

        # Upsert annotation
        existing = await db.execute(
            select(UserAnnotation).where(
                and_(
                    UserAnnotation.file_id == file_id,
                    UserAnnotation.analysis_date == analysis_date,
                    UserAnnotation.username == username,
                )
            )
        )
        annotation = existing.scalar_one_or_none()

        if annotation:
            annotation.sleep_markers_json = sleep_json
            annotation.nonwear_markers_json = nonwear_json
            annotation.is_no_sleep = is_no_sleep
            annotation.needs_consensus = needs_consensus
            annotation.algorithm_used = algorithm_used.value if algorithm_used else None
            annotation.notes = notes
            annotation.status = "submitted"
        else:
            annotation = UserAnnotation(
                file_id=file_id,
                analysis_date=analysis_date,
                username=username,
                sleep_markers_json=sleep_json,
                nonwear_markers_json=nonwear_json,
                is_no_sleep=is_no_sleep,
                needs_consensus=needs_consensus,
                algorithm_used=algorithm_used.value if algorithm_used else None,
                notes=notes,
                status="submitted",
            )
            db.add(annotation)

        # Also upsert consensus candidate so imported markers appear in consensus voting
        await _upsert_consensus_candidate_snapshot(
            db,
            file_id=file_id,
            analysis_date=analysis_date,
            source_username=username,
            sleep_markers_json=sleep_json,
            nonwear_markers_json=nonwear_json,
            is_no_sleep=is_no_sleep,
            algorithm_used=algorithm_used.value if algorithm_used else None,
            notes=notes,
        )

        await db.commit()


async def _calculate_and_store_metrics(
    file_id: int,
    analysis_date: date,
    sleep_markers: list[SleepPeriod],
    username: str,
    algorithm_type: str | None = None,
    detection_rule: str | None = None,
) -> None:
    """
    Calculate and store Tudor-Locke sleep metrics for each complete period.

    Uses the TudorLockeSleepMetricsCalculator to compute comprehensive metrics.
    """
    import logging

    from sleep_scoring_web.db.session import async_session_maker
    from sleep_scoring_web.services.metrics import TudorLockeSleepMetricsCalculator

    logger = logging.getLogger(__name__)

    async with async_session_maker() as db:
        # Get activity data for the date
        start_time = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
        end_time = start_time + timedelta(hours=24)

        activity_result = await db.execute(
            select(RawActivityData)
            .where(
                and_(
                    RawActivityData.file_id == file_id,
                    RawActivityData.timestamp >= start_time,
                    RawActivityData.timestamp < end_time,
                )
            )
            .order_by(RawActivityData.timestamp)
        )
        activity_rows = activity_result.scalars().all()

        if not activity_rows:
            logger.warning("No activity data found for file %d on %s", file_id, analysis_date)
            return

        # Run Sadeh algorithm to get sleep scores
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm

        axis_y_data = [row.axis_y or 0 for row in activity_rows]
        timestamps_float = [naive_to_unix(row.timestamp) for row in activity_rows]
        timestamps_dt = [row.timestamp for row in activity_rows]
        algorithm = SadehAlgorithm()
        sleep_scores = algorithm.score(axis_y_data)

        # Delete existing metrics for this file/date/user only
        await db.execute(
            delete(SleepMetric).where(
                and_(
                    SleepMetric.file_id == file_id,
                    SleepMetric.analysis_date == analysis_date,
                    or_(
                        SleepMetric.scored_by == username,
                        SleepMetric.scored_by.is_(None),
                    ),
                )
            )
        )

        # Initialize metrics calculator
        calculator = TudorLockeSleepMetricsCalculator()

        # Calculate metrics for each complete period
        for marker_num, marker in enumerate(sleep_markers, start=1):
            if not marker.is_complete or marker.onset_timestamp is None or marker.offset_timestamp is None:
                continue

            # Find indices for this period
            onset_idx = None
            offset_idx = None
            for i, ts in enumerate(timestamps_float):
                if onset_idx is None and ts >= marker.onset_timestamp:
                    onset_idx = i
                if ts <= marker.offset_timestamp:
                    offset_idx = i
                elif ts > marker.offset_timestamp:
                    break

            if onset_idx is None or offset_idx is None:
                logger.warning(
                    "Could not find indices for marker period %d (onset=%s, offset=%s)",
                    marker_num,
                    marker.onset_timestamp,
                    marker.offset_timestamp,
                )
                continue

            try:
                # Calculate comprehensive metrics using Tudor-Locke calculator
                metrics = calculator.calculate_metrics(
                    sleep_scores=sleep_scores,
                    activity_counts=[float(x) for x in axis_y_data],
                    onset_idx=onset_idx,
                    offset_idx=offset_idx,
                    timestamps=timestamps_dt,
                )

                sleep_metric = SleepMetric(
                    file_id=file_id,
                    analysis_date=analysis_date,
                    period_index=marker.marker_index,
                    # Period boundaries
                    onset_timestamp=marker.onset_timestamp,
                    offset_timestamp=marker.offset_timestamp,
                    in_bed_time=metrics["in_bed_time"],
                    out_bed_time=metrics["out_bed_time"],
                    sleep_onset=metrics["sleep_onset"],
                    sleep_offset=metrics["sleep_offset"],
                    # Duration metrics
                    time_in_bed_minutes=metrics["time_in_bed_minutes"],
                    total_sleep_time_minutes=metrics["total_sleep_time_minutes"],
                    sleep_onset_latency_minutes=metrics["sleep_onset_latency_minutes"],
                    waso_minutes=metrics["waso_minutes"],
                    # Awakening metrics
                    number_of_awakenings=metrics["number_of_awakenings"],
                    average_awakening_length_minutes=metrics["average_awakening_length_minutes"],
                    # Quality indices
                    sleep_efficiency=metrics["sleep_efficiency"],
                    movement_index=metrics["movement_index"],
                    fragmentation_index=metrics["fragmentation_index"],
                    sleep_fragmentation_index=metrics["sleep_fragmentation_index"],
                    # Activity metrics
                    total_activity=metrics["total_activity"],
                    nonzero_epochs=metrics["nonzero_epochs"],
                    # Algorithm info
                    algorithm_type=algorithm_type or AlgorithmType.SADEH_1994_ACTILIFE.value,
                    detection_rule=detection_rule,
                    scored_by=username,
                    verification_status=VerificationStatus.DRAFT.value,
                )
                db.add(sleep_metric)
            except ValueError as e:
                logger.exception("Failed to calculate metrics for period %d: %s", marker.marker_index, e)
                continue

        await db.commit()

        # Compute complexity scores (pre + post) after metrics are stored
        try:
            from sleep_scoring_web.db.models import DiaryEntry, NightComplexity, UserAnnotation
            from sleep_scoring_web.services.algorithms import ChoiAlgorithm
            from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column
            from sleep_scoring_web.services.complexity import compute_post_complexity, compute_pre_complexity

            choi_column = await get_choi_column(db, username)
            choi = ChoiAlgorithm()
            choi_nonwear = choi.detect_mask(extract_choi_input(activity_rows, choi_column))

            # Load diary
            diary_result = await db.execute(
                select(DiaryEntry).where(
                    and_(
                        DiaryEntry.file_id == file_id,
                        DiaryEntry.analysis_date == analysis_date,
                    )
                )
            )
            diary = diary_result.scalar_one_or_none()
            diary_onset = diary.lights_out or diary.bed_time if diary else None
            diary_wake = diary.wake_time or diary.got_up if diary else None
            nap_count = 0
            diary_nonwear_times: list[tuple[str, str]] = []
            if diary:
                if diary.nap_1_start:
                    nap_count += 1
                if diary.nap_2_start:
                    nap_count += 1
                if diary.nap_3_start:
                    nap_count += 1
                # Collect diary-reported nonwear periods
                for i in range(1, 4):
                    nw_s = getattr(diary, f"nonwear_{i}_start", None)
                    nw_e = getattr(diary, f"nonwear_{i}_end", None)
                    if nw_s and nw_e:
                        diary_nonwear_times.append((nw_s, nw_e))

            # Load sensor nonwear periods from the Marker table (marker_type="sensor"),
            # queried by timestamp overlap with the activity data range.
            sensor_nonwear_periods: list[tuple[float, float]] = []
            if timestamps_float:
                data_min_ts = timestamps_float[0]
                data_max_ts = timestamps_float[-1]
                sensor_nw_result = await db.execute(
                    select(Marker).where(
                        and_(
                            Marker.file_id == file_id,
                            Marker.marker_category == MarkerCategory.NONWEAR,
                            Marker.marker_type == "sensor",
                            Marker.start_timestamp <= data_max_ts,
                            Marker.end_timestamp >= data_min_ts,
                        )
                    )
                )
                for nw in sensor_nw_result.scalars().all():
                    if nw.start_timestamp is not None and nw.end_timestamp is not None:
                        sensor_nonwear_periods.append((nw.start_timestamp, nw.end_timestamp))

            pre_score, features = compute_pre_complexity(
                timestamps=timestamps_float,
                activity_counts=[float(x) for x in axis_y_data],
                sleep_scores=sleep_scores,
                choi_nonwear=choi_nonwear,
                diary_onset_time=diary_onset,
                diary_wake_time=diary_wake,
                diary_nap_count=nap_count,
                analysis_date=str(analysis_date),
                sensor_nonwear_periods=sensor_nonwear_periods,
                diary_nonwear_times=diary_nonwear_times,
            )

            # Compute post-scoring adjustments
            marker_pairs = [
                (m.onset_timestamp, m.offset_timestamp)
                for m in sleep_markers
                if m.is_complete and m.onset_timestamp is not None and m.offset_timestamp is not None
            ]
            post_score, updated_features = compute_post_complexity(
                complexity_pre=pre_score,
                features=features,
                sleep_markers=marker_pairs,
                sleep_scores=sleep_scores,
                timestamps=timestamps_float,
            )

            # Upsert complexity
            existing_complexity = await db.execute(
                select(NightComplexity).where(
                    and_(
                        NightComplexity.file_id == file_id,
                        NightComplexity.analysis_date == analysis_date,
                    )
                )
            )
            complexity_row = existing_complexity.scalar_one_or_none()
            if complexity_row:
                complexity_row.complexity_pre = pre_score
                complexity_row.complexity_post = post_score
                complexity_row.features_json = updated_features
            else:
                complexity_row = NightComplexity(
                    file_id=file_id,
                    analysis_date=analysis_date,
                    complexity_pre=pre_score,
                    complexity_post=post_score,
                    features_json=updated_features,
                )
                db.add(complexity_row)

            await db.commit()
        except Exception:
            logger.exception("Failed to compute complexity for file %d date %s", file_id, analysis_date)


# =============================================================================
# Auto-Score Endpoint
# =============================================================================


class AutoScoreResponse(BaseModel):
    """Response with suggested marker placements."""

    sleep_markers: list[dict[str, Any]] = Field(default_factory=list)
    nap_markers: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AutoNonwearResponse(BaseModel):
    """Response with suggested nonwear marker placements."""
    nonwear_markers: list[dict[str, Any]] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AutoScoreBatchRequest(BaseModel):
    """Request payload for background batch auto-score prepopulation."""

    file_ids: list[int] | None = None
    only_missing: bool = True
    algorithm: str = "sadeh_1994_actilife"
    include_diary: bool = True
    onset_epochs: int = Field(default=3, ge=1, le=30)
    offset_minutes: int = Field(default=5, ge=1, le=60)
    detection_rule: str | None = None


class AutoScoreBatchStatusResponse(BaseModel):
    """In-memory batch auto-score progress snapshot."""

    is_running: bool
    total_dates: int
    processed_dates: int
    scored_dates: int
    skipped_existing: int
    skipped_incomplete_diary: int
    skipped_no_activity: int
    skipped_no_markers: int
    failed_dates: int
    started_at: str | None = None
    finished_at: str | None = None
    current_file_id: int | None = None
    current_date: str | None = None
    errors: list[str] = Field(default_factory=list)


@dataclass
class _AutoScoreBatchState:
    is_running: bool = False
    total_dates: int = 0
    processed_dates: int = 0
    scored_dates: int = 0
    skipped_existing: int = 0
    skipped_incomplete_diary: int = 0
    skipped_no_activity: int = 0
    skipped_no_markers: int = 0
    failed_dates: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    current_file_id: int | None = None
    current_date: str | None = None
    errors: list[str] = dc_field(default_factory=list)


_auto_score_batch_state = _AutoScoreBatchState()
_auto_score_batch_task: asyncio.Task | None = None
_auto_score_batch_lock = asyncio.Lock()


def _serialize_auto_score_batch_state() -> AutoScoreBatchStatusResponse:
    state = _auto_score_batch_state
    return AutoScoreBatchStatusResponse(
        is_running=state.is_running,
        total_dates=state.total_dates,
        processed_dates=state.processed_dates,
        scored_dates=state.scored_dates,
        skipped_existing=state.skipped_existing,
        skipped_incomplete_diary=state.skipped_incomplete_diary,
        skipped_no_activity=state.skipped_no_activity,
        skipped_no_markers=state.skipped_no_markers,
        failed_dates=state.failed_dates,
        started_at=state.started_at.isoformat() if state.started_at else None,
        finished_at=state.finished_at.isoformat() if state.finished_at else None,
        current_file_id=state.current_file_id,
        current_date=state.current_date,
        errors=list(state.errors),
    )


def _reset_auto_score_batch_state() -> None:
    global _auto_score_batch_state
    _auto_score_batch_state = _AutoScoreBatchState(
        is_running=True,
        started_at=datetime.utcnow(),
    )


def _diary_time_present(value: str | None) -> bool:
    """Return True when diary time strings are present and non-null-like."""
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized not in {"", "nan", "none", "null"}


async def _run_auto_score_single(
    *,
    file_id: int,
    analysis_date: date,
    db: DbSession,
    algorithm: str,
    include_diary: bool,
    username: str = "",
    onset_epochs: int,
    offset_minutes: int,
    detection_rule: str | None = None,
) -> AutoScoreResponse:
    """Run auto-score for one file/date and persist auto_score annotation."""
    from sleep_scoring_web.db.models import DiaryEntry as DiaryEntryModel
    from sleep_scoring_web.services.algorithms.factory import create_algorithm
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.marker_placement import run_auto_scoring

    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()
    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    start_dt = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
    end_dt = start_dt + timedelta(hours=24)

    data_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= start_dt,
                RawActivityData.timestamp < end_dt,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    rows = data_result.scalars().all()
    if not rows:
        return AutoScoreResponse(notes=["No activity data found for this date"])

    timestamps = [naive_to_unix(row.timestamp) for row in rows]
    activity_counts = [float(row.axis_y or 0) for row in rows]

    algo = create_algorithm(algorithm)
    sleep_scores = algo.score(activity_counts)

    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column

    choi_column = await get_choi_column(db, username)
    choi = ChoiAlgorithm()
    nonwear_results = choi.detect_mask(extract_choi_input(rows, choi_column))

    diary_bed = None
    diary_onset = None
    diary_wake = None
    diary_naps: list[tuple[str | None, str | None]] = []
    diary_nonwear: list[tuple[str | None, str | None]] = []
    if include_diary:
        diary_result = await db.execute(
            select(DiaryEntryModel).where(
                and_(
                    DiaryEntryModel.file_id == file_id,
                    DiaryEntryModel.analysis_date == analysis_date,
                )
            )
        )
        diary = diary_result.scalar_one_or_none()
        has_complete_diary = (
            diary is not None
            and _diary_time_present(diary.lights_out)
            and _diary_time_present(diary.wake_time)
        )
        if not has_complete_diary:
            existing = await db.execute(
                select(UserAnnotation).where(
                    and_(
                        UserAnnotation.file_id == file_id,
                        UserAnnotation.analysis_date == analysis_date,
                        UserAnnotation.username == "auto_score",
                    )
                )
            )
            annotation = existing.scalar_one_or_none()
            if annotation:
                await db.delete(annotation)
                await db.commit()
                await broadcast_consensus_update(
                    file_id=file_id,
                    analysis_date=analysis_date,
                    event="auto_score_cleared",
                    username="auto_score",
                )
            return AutoScoreResponse(
                notes=["Incomplete diary for this date - auto-score requires lights_out and wake_time"]
            )

        diary_bed = diary.bed_time
        diary_onset = diary.lights_out
        diary_wake = diary.wake_time
        for i in range(1, 4):
            nap_start = getattr(diary, f"nap_{i}_start", None)
            nap_end = getattr(diary, f"nap_{i}_end", None)
            if nap_start and nap_end:
                diary_naps.append((nap_start, nap_end))
        for i in range(1, 4):
            nw_start = getattr(diary, f"nonwear_{i}_start", None)
            nw_end = getattr(diary, f"nonwear_{i}_end", None)
            if nw_start and nw_end:
                diary_nonwear.append((nw_start, nw_end))

    result = run_auto_scoring(
        timestamps=timestamps,
        activity_counts=activity_counts,
        sleep_scores=sleep_scores,
        choi_nonwear=nonwear_results,
        diary_bed_time=diary_bed,
        diary_onset_time=diary_onset,
        diary_wake_time=diary_wake,
        diary_naps=diary_naps,
        diary_nonwear=diary_nonwear,
        analysis_date=analysis_date.isoformat(),
        epoch_length_seconds=60,
        onset_min_consecutive_sleep=onset_epochs,
        offset_min_consecutive_minutes=offset_minutes,
    )

    existing = await db.execute(
        select(UserAnnotation).where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
                UserAnnotation.username == "auto_score",
            )
        )
    )
    annotation = existing.scalar_one_or_none()
    all_markers = result["sleep_markers"] + result["nap_markers"]

    if all_markers:
        markers_json = all_markers
        if annotation:
            annotation.sleep_markers_json = markers_json
            annotation.nonwear_markers_json = None
            annotation.is_no_sleep = False
            annotation.algorithm_used = algorithm
            annotation.detection_rule = detection_rule
            annotation.notes = "; ".join(result["notes"]) if result["notes"] else None
            annotation.status = "submitted"
        else:
            annotation = UserAnnotation(
                file_id=file_id,
                analysis_date=analysis_date,
                username="auto_score",
                sleep_markers_json=markers_json,
                nonwear_markers_json=None,
                is_no_sleep=False,
                algorithm_used=algorithm,
                detection_rule=detection_rule,
                notes="; ".join(result["notes"]) if result["notes"] else None,
                status="submitted",
            )
            db.add(annotation)

        await _upsert_consensus_candidate_snapshot(
            db,
            file_id=file_id,
            analysis_date=analysis_date,
            source_username="auto_score",
            sleep_markers_json=markers_json,
            nonwear_markers_json=None,
            is_no_sleep=False,
            algorithm_used=algorithm,
            notes="; ".join(result["notes"]) if result["notes"] else None,
        )
        await db.commit()
        await broadcast_consensus_update(
            file_id=file_id,
            analysis_date=analysis_date,
            event="auto_score_updated",
            username="auto_score",
        )
    elif annotation:
        await db.delete(annotation)
        await db.commit()
        await broadcast_consensus_update(
            file_id=file_id,
            analysis_date=analysis_date,
            event="auto_score_cleared",
            username="auto_score",
        )

    return AutoScoreResponse(
        sleep_markers=result["sleep_markers"],
        nap_markers=result["nap_markers"],
        notes=result["notes"],
    )


async def _build_auto_score_batch_targets(
    *,
    db: DbSession,
    request: AutoScoreBatchRequest,
) -> tuple[list[tuple[int, date]], int, int]:
    """Collect deterministic batch targets from complete diary rows."""
    if request.file_ids:
        files_result = await db.execute(
            select(FileModel.id, FileModel.filename).where(FileModel.id.in_(request.file_ids))
        )
        file_ids = sorted(
            {
                int(fid)
                for fid, filename in files_result.all()
                if not is_excluded_activity_filename(filename)
            }
        )
    else:
        files_result = await db.execute(select(FileModel.id, FileModel.filename))
        file_ids = sorted(
            {
                int(fid)
                for fid, filename in files_result.all()
                if not is_excluded_activity_filename(filename)
            }
        )

    if not file_ids:
        return [], 0, 0

    diary_result = await db.execute(
        select(DiaryEntry).where(DiaryEntry.file_id.in_(file_ids))
    )
    diary_entries = diary_result.scalars().all()

    complete_targets: set[tuple[int, date]] = set()
    skipped_incomplete = 0
    for entry in diary_entries:
        if _diary_time_present(entry.lights_out) and _diary_time_present(entry.wake_time):
            complete_targets.add((entry.file_id, entry.analysis_date))
        else:
            skipped_incomplete += 1

    targets = sorted(complete_targets, key=lambda item: (item[0], item[1]))
    skipped_existing = 0

    if request.only_missing and targets:
        existing_result = await db.execute(
            select(
                UserAnnotation.file_id,
                UserAnnotation.analysis_date,
                UserAnnotation.sleep_markers_json,
            ).where(
                and_(
                    UserAnnotation.username == "auto_score",
                    UserAnnotation.file_id.in_(file_ids),
                )
            )
        )
        existing_dates = {
            (int(row[0]), row[1])
            for row in existing_result.all()
            if row[2]
        }
        filtered_targets = [target for target in targets if target not in existing_dates]
        skipped_existing = len(targets) - len(filtered_targets)
        targets = filtered_targets

    return targets, skipped_existing, skipped_incomplete


async def _run_auto_score_batch(
    *,
    targets: list[tuple[int, date]],
    request: AutoScoreBatchRequest,
    username: str = "",
) -> None:
    """Background worker for prepopulating auto-score annotations."""
    global _auto_score_batch_task
    from sleep_scoring_web.db.session import async_session_maker

    try:
        for file_id, analysis_date in targets:
            _auto_score_batch_state.current_file_id = file_id
            _auto_score_batch_state.current_date = analysis_date.isoformat()
            try:
                async with async_session_maker() as db:
                    result = await _run_auto_score_single(
                        file_id=file_id,
                        analysis_date=analysis_date,
                        db=db,
                        algorithm=request.algorithm,
                        include_diary=request.include_diary,
                        onset_epochs=request.onset_epochs,
                        offset_minutes=request.offset_minutes,
                        username=username,
                        detection_rule=request.detection_rule,
                    )
                marker_count = len(result.sleep_markers) + len(result.nap_markers)
                if marker_count > 0:
                    _auto_score_batch_state.scored_dates += 1
                else:
                    notes = " ".join(result.notes).lower()
                    if "incomplete diary" in notes or "requires lights_out and wake_time" in notes or "requires diary" in notes:
                        _auto_score_batch_state.skipped_incomplete_diary += 1
                    elif "no activity data" in notes:
                        _auto_score_batch_state.skipped_no_activity += 1
                    else:
                        _auto_score_batch_state.skipped_no_markers += 1
            except Exception as exc:
                _auto_score_batch_state.failed_dates += 1
                _auto_score_batch_state.errors.append(
                    f"{file_id}/{analysis_date.isoformat()}: {exc}"
                )
            finally:
                _auto_score_batch_state.processed_dates += 1
                await asyncio.sleep(0)
    finally:
        _auto_score_batch_state.is_running = False
        _auto_score_batch_state.finished_at = datetime.utcnow()
        _auto_score_batch_state.current_file_id = None
        _auto_score_batch_state.current_date = None
        _auto_score_batch_task = None


@router.post("/auto-score/batch")
async def start_auto_score_batch(
    request: AutoScoreBatchRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> AutoScoreBatchStatusResponse:
    """
    Start background auto-score prepopulation across complete-diary dates.

    Uses complete diary rows only; incomplete diary dates are never auto-scored.
    """
    global _auto_score_batch_task

    async with _auto_score_batch_lock:
        if _auto_score_batch_task is not None and not _auto_score_batch_task.done():
            raise HTTPException(status_code=409, detail="Auto-score batch is already running")

        targets, skipped_existing, skipped_incomplete = await _build_auto_score_batch_targets(
            db=db,
            request=request,
        )

        _reset_auto_score_batch_state()
        _auto_score_batch_state.total_dates = len(targets)
        _auto_score_batch_state.skipped_existing = skipped_existing
        _auto_score_batch_state.skipped_incomplete_diary = skipped_incomplete

        _auto_score_batch_task = asyncio.create_task(
            _run_auto_score_batch(
                targets=targets,
                request=request,
                username=username,
            )
        )
        return _serialize_auto_score_batch_state()


@router.get("/auto-score/batch/status")
async def get_auto_score_batch_status(
    _: VerifiedPassword,
) -> AutoScoreBatchStatusResponse:
    """Return in-memory auto-score batch progress."""
    return _serialize_auto_score_batch_state()


@router.post("/{file_id}/{analysis_date}/auto-score")
async def auto_score_markers(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    algorithm: Annotated[str, Query(description="Algorithm type")] = "sadeh_1994_actilife",
    include_diary: Annotated[bool, Query(description="Use diary data for placement")] = True,
    onset_epochs: Annotated[int, Query(description="Min consecutive sleep epochs for onset (e.g. 3 or 5)", ge=1, le=30)] = 3,
    offset_minutes: Annotated[int, Query(description="Min consecutive minutes for offset (e.g. 5 or 10)", ge=1, le=60)] = 5,
    detection_rule: Annotated[str | None, Query(description="Sleep detection rule active at time of scoring")] = None,
) -> AutoScoreResponse:
    """
    Automatically score a date using the rule-based engine.

    Returns suggestions for user to accept/reject.
    Also saves results as a "auto_score" UserAnnotation for consensus comparison.
    """
    await require_file_access(db, username, file_id)

    return await _run_auto_score_single(
        file_id=file_id,
        analysis_date=analysis_date,
        db=db,
        algorithm=algorithm,
        include_diary=include_diary,
        onset_epochs=onset_epochs,
        offset_minutes=offset_minutes,
        username=username,
        detection_rule=detection_rule,
    )


@router.get("/{file_id}/{analysis_date}/auto-score-result")
async def get_auto_score_result(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """
    Get the auto_score user's saved annotation for this file/date.

    Returns the markers in SleepPeriod format so the frontend can
    accept them as the current user's own score.
    """
    await require_file_access(db, username, file_id)

    annotation_result = await db.execute(
        select(UserAnnotation).where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
                UserAnnotation.username == "auto_score",
            )
        )
    )
    annotation = annotation_result.scalar_one_or_none()
    if not annotation or not annotation.sleep_markers_json:
        raise HTTPException(status_code=404, detail="No auto-score result for this date")

    return {
        "sleep_markers": annotation.sleep_markers_json,
        "nonwear_markers": annotation.nonwear_markers_json or [],
        "algorithm_used": annotation.algorithm_used,
        "notes": annotation.notes,
    }


@router.post("/{file_id}/{analysis_date}/auto-nonwear")
async def auto_nonwear_markers(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    threshold: Annotated[int, Query(description="Max activity count to consider as zero", ge=0, le=1000)] = 0,
) -> AutoNonwearResponse:
    """
    Automatically detect nonwear periods using diary anchors and zero-activity detection.
    Returns suggestions for user to accept/reject.
    """
    await require_file_access(db, username, file_id)

    from sleep_scoring_web.db.models import DiaryEntry as DiaryEntryModel
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column
    from sleep_scoring_web.services.marker_placement import place_nonwear_markers

    # Load file
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()
    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Load activity data (noon-to-noon window)
    start_dt = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
    end_dt = start_dt + timedelta(hours=24)

    data_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= start_dt,
                RawActivityData.timestamp < end_dt,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    rows = data_result.scalars().all()
    if not rows:
        return AutoNonwearResponse(notes=["No activity data found for this date"])

    timestamps = [naive_to_unix(row.timestamp) for row in rows]
    # Use max(axis_y, vector_magnitude) per epoch — nonwear requires BOTH to be zero
    activity_counts = [
        float(max(row.axis_y or 0, row.vector_magnitude or 0)) for row in rows
    ]

    # Run Choi nonwear
    choi_column = await get_choi_column(db, username)
    choi = ChoiAlgorithm()
    nonwear_results = choi.detect_mask(extract_choi_input(rows, choi_column))

    # Load diary
    diary_result = await db.execute(
        select(DiaryEntryModel).where(
            and_(
                DiaryEntryModel.file_id == file_id,
                DiaryEntryModel.analysis_date == analysis_date,
            )
        )
    )
    diary = diary_result.scalar_one_or_none()
    diary_nonwear: list[tuple[str | None, str | None]] = []
    if diary:
        for i in range(1, 4):
            nw_start = getattr(diary, f"nonwear_{i}_start", None)
            nw_end = getattr(diary, f"nonwear_{i}_end", None)
            if nw_start and nw_end:
                diary_nonwear.append((nw_start, nw_end))

    # Load sensor nonwear periods
    sensor_nw_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.marker_category == "nonwear",
                Marker.marker_type == "sensor",
            )
        )
    )
    sensor_nw_markers = sensor_nw_result.scalars().all()
    sensor_periods = [
        (m.start_timestamp, m.end_timestamp)
        for m in sensor_nw_markers
        if m.end_timestamp is not None
    ]

    # Load existing sleep markers for this user+date (to avoid overlap)
    ann_result = await db.execute(
        select(UserAnnotation).where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
                UserAnnotation.username == username,
            )
        )
    )
    annotation = ann_result.scalar_one_or_none()
    existing_sleep: list[tuple[float, float]] = []
    if annotation and annotation.sleep_markers_json:
        for sm in annotation.sleep_markers_json:
            onset = sm.get("onset_timestamp")
            offset = sm.get("offset_timestamp")
            if onset is not None and offset is not None:
                existing_sleep.append((float(onset), float(offset)))

    # Also check saved markers in Marker table
    saved_sleep_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.analysis_date == analysis_date,
                Marker.marker_category == "sleep",
                Marker.created_by == username,
            )
        )
    )
    for sm in saved_sleep_result.scalars().all():
        if sm.start_timestamp and sm.end_timestamp:
            existing_sleep.append((sm.start_timestamp, sm.end_timestamp))

    result = place_nonwear_markers(
        timestamps=timestamps,
        activity_counts=activity_counts,
        diary_nonwear=diary_nonwear,
        choi_nonwear=nonwear_results,
        sensor_nonwear_periods=sensor_periods,
        existing_sleep_markers=existing_sleep,
        analysis_date=analysis_date.isoformat(),
        threshold=threshold,
    )

    return AutoNonwearResponse(
        nonwear_markers=result.nonwear_markers,
        notes=result.notes,
    )

