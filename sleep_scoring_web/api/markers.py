"""
Marker API endpoints for sleep and nonwear marker management.

Provides CRUD operations for markers with optimistic update support.

Note: We intentionally avoid `from __future__ import annotations` here
because FastAPI's dependency injection needs actual types, not string
annotations. Using Annotated types requires runtime resolution.
"""

import calendar
import logging
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Annotated, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, or_, select

from sleep_scoring_web.api.access import require_file_access, require_file_and_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.db.models import ConsensusCandidate, DiaryEntry, Marker, RawActivityData, SleepMetric, UserAnnotation
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.schemas import ManualNonwearPeriod, MarkerUpdateRequest, SleepMetrics, SleepPeriod
from sleep_scoring_web.schemas.enums import AlgorithmType, MarkerCategory, MarkerType, VerificationStatus
from sleep_scoring_web.services.consensus import compute_candidate_hash
from sleep_scoring_web.services.consensus_realtime import broadcast_consensus_update
from sleep_scoring_web.services.file_identity import is_excluded_file_obj

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
    file = await require_file_and_access(db, username, file_id)

    # Fetch markers and metrics concurrently (independent queries).
    async def _fetch_markers():
        # Get markers for THIS user.
        # Exclude sensor nonwear (marker_type="sensor") — those are read-only overlay data
        # returned via the activity endpoint, not editable markers.
        # Fallback to legacy rows (created_by IS NULL) for backward compatibility.
        result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.analysis_date == analysis_date,
                    Marker.created_by == username,
                    Marker.marker_type != "sensor",
                )
            )
        )
        rows = result.scalars().all()
        if not rows:
            legacy_result = await db.execute(
                select(Marker).where(
                    and_(
                        Marker.file_id == file_id,
                        Marker.analysis_date == analysis_date,
                        Marker.created_by.is_(None),
                        Marker.marker_type != "sensor",
                    )
                )
            )
            rows = legacy_result.scalars().all()
            if rows:
                logger.warning("Using legacy markers (created_by IS NULL) for file %d, date %s", file_id, analysis_date)
        return rows

    async def _fetch_metrics():
        # Get metrics for THIS user.
        # Fallback to legacy rows (scored_by IS NULL) for backward compatibility.
        result = await db.execute(
            select(SleepMetric).where(
                and_(
                    SleepMetric.file_id == file_id,
                    SleepMetric.analysis_date == analysis_date,
                    SleepMetric.scored_by == username,
                )
            )
        )
        rows = result.scalars().all()
        if not rows:
            legacy_result = await db.execute(
                select(SleepMetric).where(
                    and_(
                        SleepMetric.file_id == file_id,
                        SleepMetric.analysis_date == analysis_date,
                        SleepMetric.scored_by.is_(None),
                    )
                )
            )
            rows = legacy_result.scalars().all()
            if rows:
                logger.warning("Using legacy metrics (scored_by IS NULL) for file %d, date %s", file_id, analysis_date)
        return rows

    markers = await _fetch_markers()
    db_metrics = await _fetch_metrics()

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
                select(UserAnnotation).where(
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
        select(UserAnnotation).where(
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
    file = await require_file_and_access(db, username, file_id)

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
        select(UserAnnotation).where(
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
        saved_at=datetime.now(UTC),
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
# Background Tasks
# =============================================================================


# NOTE: Table endpoints moved to markers_tables.py
# NOTE: Import endpoints moved to markers_import.py
# NOTE: Auto-score endpoints moved to markers_autoscore.py


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


async def _patch_sleep_annotation(
    file_id: int,
    analysis_date: date,
    username: str,
    sleep_markers: list[SleepPeriod],
    notes: str | None,
    is_no_sleep: bool = False,
    needs_consensus: bool = False,
) -> None:
    """Update only sleep-related fields on an annotation, preserving nonwear data."""
    from sleep_scoring_web.db.session import async_session_maker

    sleep_json = [m.model_dump() for m in sleep_markers] if sleep_markers else None

    async with async_session_maker() as db:
        existing = await db.execute(
            select(UserAnnotation)
            .where(
                and_(
                    UserAnnotation.file_id == file_id,
                    UserAnnotation.analysis_date == analysis_date,
                    UserAnnotation.username == username,
                )
            )
            .with_for_update()
        )
        annotation = existing.scalar_one_or_none()
        existing_nonwear_json = None

        if annotation:
            existing_nonwear_json = annotation.nonwear_markers_json
            annotation.sleep_markers_json = sleep_json
            annotation.is_no_sleep = is_no_sleep
            annotation.needs_consensus = needs_consensus
            annotation.notes = notes
            annotation.status = "submitted"
        else:
            annotation = UserAnnotation(
                file_id=file_id,
                analysis_date=analysis_date,
                username=username,
                sleep_markers_json=sleep_json,
                is_no_sleep=is_no_sleep,
                needs_consensus=needs_consensus,
                notes=notes,
                status="submitted",
            )
            db.add(annotation)

        await _upsert_consensus_candidate_snapshot(
            db,
            file_id=file_id,
            analysis_date=analysis_date,
            source_username=username,
            sleep_markers_json=sleep_json,
            nonwear_markers_json=existing_nonwear_json,
            is_no_sleep=is_no_sleep,
            algorithm_used=None,
            notes=notes,
        )

        await db.commit()


async def _patch_nonwear_annotation(
    file_id: int,
    analysis_date: date,
    username: str,
    nonwear_markers: list[ManualNonwearPeriod],
    notes: str | None = None,
    needs_consensus: bool = False,
) -> None:
    """Update only the nonwear_markers_json on an existing annotation, preserving sleep data."""
    from sleep_scoring_web.db.session import async_session_maker

    nonwear_json = [m.model_dump() for m in nonwear_markers]

    async with async_session_maker() as db:
        existing = await db.execute(
            select(UserAnnotation)
            .where(
                and_(
                    UserAnnotation.file_id == file_id,
                    UserAnnotation.analysis_date == analysis_date,
                    UserAnnotation.username == username,
                )
            )
            .with_for_update()
        )
        annotation = existing.scalar_one_or_none()

        existing_sleep_json = None
        existing_is_no_sleep = False

        if annotation:
            existing_sleep_json = annotation.sleep_markers_json
            existing_is_no_sleep = annotation.is_no_sleep or False
            annotation.nonwear_markers_json = nonwear_json
            annotation.notes = notes or annotation.notes
            annotation.needs_consensus = needs_consensus or annotation.needs_consensus
        else:
            annotation = UserAnnotation(
                file_id=file_id,
                analysis_date=analysis_date,
                username=username,
                nonwear_markers_json=nonwear_json,
                notes=notes,
                needs_consensus=needs_consensus,
                status="submitted",
            )
            db.add(annotation)

        await _upsert_consensus_candidate_snapshot(
            db,
            file_id=file_id,
            analysis_date=analysis_date,
            source_username=username,
            sleep_markers_json=existing_sleep_json,
            nonwear_markers_json=nonwear_json,
            is_no_sleep=existing_is_no_sleep,
            algorithm_used=None,
            notes=annotation.notes,
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
