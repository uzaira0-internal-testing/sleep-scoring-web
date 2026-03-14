"""
Auto-scoring endpoints for automated sleep and nonwear marker placement.

Provides single-date and batch auto-scoring using rule-based engines.
"""

import asyncio
import logging
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select

from sleep_scoring_web.api.access import require_file_access, require_file_and_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.api.markers import (
    _upsert_consensus_candidate_snapshot,
    naive_to_unix,
    upsert_user_annotation,
)
from sleep_scoring_web.db.models import DiaryEntry, Marker, RawActivityData, UserAnnotation
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.schemas.enums import AlgorithmType, MarkerCategory, VerificationStatus
from sleep_scoring_web.schemas.pipeline import PipelineConfigRequest
from sleep_scoring_web.services.consensus_realtime import broadcast_consensus_update
from sleep_scoring_web.services.file_identity import is_excluded_activity_filename, is_excluded_file_obj

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
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
    algorithm: str = AlgorithmType.SADEH_1994_ACTILIFE
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


# =============================================================================
# Module-level state for batch auto-score
# =============================================================================


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
_auto_score_batch_task: asyncio.Task[None] | None = None
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
        started_at=datetime.now(tz=UTC),
    )


def _diary_time_present(value: str | None) -> bool:
    """Return True when diary time strings are present and non-null-like."""
    if value is None:
        return False
    normalized = value.strip().lower()
    return normalized not in {"", "nan", "none", "null"}


def _extract_diary_periods(
    diary: Any,
) -> tuple[list[tuple[str | None, str | None]], list[tuple[str | None, str | None]]]:
    """Extract nap and nonwear period tuples from a DiaryEntry row."""
    naps: list[tuple[str | None, str | None]] = []
    nonwear: list[tuple[str | None, str | None]] = []
    for i in range(1, 4):
        nap_start = getattr(diary, f"nap_{i}_start", None)
        nap_end = getattr(diary, f"nap_{i}_end", None)
        if nap_start and nap_end:
            naps.append((nap_start, nap_end))
    for i in range(1, 4):
        nw_start = getattr(diary, f"nonwear_{i}_start", None)
        nw_end = getattr(diary, f"nonwear_{i}_end", None)
        if nw_start and nw_end:
            nonwear.append((nw_start, nw_end))
    return naps, nonwear


# =============================================================================
# Core auto-score logic
# =============================================================================


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
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.algorithms.factory import create_algorithm
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
        has_complete_diary = diary is not None and _diary_time_present(diary.lights_out) and _diary_time_present(diary.wake_time)
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
            return AutoScoreResponse(notes=["Incomplete diary for this date - auto-score requires lights_out and wake_time"])

        diary_bed = diary.bed_time
        diary_onset = diary.lights_out
        diary_wake = diary.wake_time
        diary_naps, diary_nonwear = _extract_diary_periods(diary)

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

    all_markers = result["sleep_markers"] + result["nap_markers"]

    if all_markers:
        markers_json = all_markers
        notes_str = "; ".join(result["notes"]) if result["notes"] else None
        await upsert_user_annotation(
            db,
            file_id=file_id,
            analysis_date=analysis_date,
            username="auto_score",
            sleep_markers_json=markers_json,
            nonwear_markers_json=None,
            is_no_sleep=False,
            algorithm_used=algorithm,
            detection_rule=detection_rule,
            notes=notes_str,
        )

        await _upsert_consensus_candidate_snapshot(
            db,
            file_id=file_id,
            analysis_date=analysis_date,
            source_username="auto_score",
            sleep_markers_json=markers_json,
            nonwear_markers_json=None,
            is_no_sleep=False,
            algorithm_used=algorithm,
            notes=notes_str,
        )
        await db.commit()
        await broadcast_consensus_update(
            file_id=file_id,
            analysis_date=analysis_date,
            event="auto_score_updated",
            username="auto_score",
        )
    else:
        # No markers produced — clean up any existing auto_score annotation
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
        sleep_markers=result["sleep_markers"],
        nap_markers=result["nap_markers"],
        notes=result["notes"],
    )


# =============================================================================
# Batch auto-score helpers
# =============================================================================


async def _build_auto_score_batch_targets(
    *,
    db: DbSession,
    request: AutoScoreBatchRequest,
) -> tuple[list[tuple[int, date]], int, int]:
    """Collect deterministic batch targets from complete diary rows."""
    if request.file_ids:
        files_result = await db.execute(select(FileModel.id, FileModel.filename).where(FileModel.id.in_(request.file_ids)))
        file_ids = sorted({int(fid) for fid, filename in files_result.all() if not is_excluded_activity_filename(filename)})
    else:
        files_result = await db.execute(select(FileModel.id, FileModel.filename))
        file_ids = sorted({int(fid) for fid, filename in files_result.all() if not is_excluded_activity_filename(filename)})

    if not file_ids:
        return [], 0, 0

    diary_result = await db.execute(select(DiaryEntry).where(DiaryEntry.file_id.in_(file_ids)))
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
        existing_dates = {(int(row[0]), row[1]) for row in existing_result.all() if row[2]}
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
                _auto_score_batch_state.errors.append(f"{file_id}/{analysis_date.isoformat()}: {exc}")
            finally:
                _auto_score_batch_state.processed_dates += 1
                await asyncio.sleep(0)
    finally:
        _auto_score_batch_state.is_running = False
        _auto_score_batch_state.finished_at = datetime.now(tz=UTC)
        _auto_score_batch_state.current_file_id = None
        _auto_score_batch_state.current_date = None
        _auto_score_batch_task = None


# =============================================================================
# Endpoints
# =============================================================================


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
    algorithm: Annotated[str, Query(description="Algorithm type")] = AlgorithmType.SADEH_1994_ACTILIFE,
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
) -> dict[str, Any]:
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
    # Use max(axis_y, vector_magnitude) per epoch -- nonwear requires BOTH to be zero
    activity_counts = [float(max(row.axis_y or 0, row.vector_magnitude or 0)) for row in rows]

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
        _, diary_nonwear = _extract_diary_periods(diary)

    # Load sensor nonwear periods
    sensor_nw_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.sensor_nonwear_filter(),
            )
        )
    )
    sensor_nw_markers = sensor_nw_result.scalars().all()
    sensor_periods = [(m.start_timestamp, m.end_timestamp) for m in sensor_nw_markers if m.end_timestamp is not None]

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
                Marker.marker_category == MarkerCategory.SLEEP,
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


# =============================================================================
# Pipeline v2 endpoints
# =============================================================================


@router.get("/pipeline/discover")
async def discover_pipeline(
    _: VerifiedPassword,
) -> dict[str, Any]:
    """Return available pipeline components per role and their parameter schemas."""
    from sleep_scoring_web.schemas.pipeline import PARAM_JSON_SCHEMAS
    from sleep_scoring_web.services.pipeline import describe_pipeline

    roles = describe_pipeline()
    return {"roles": roles, "param_schemas": PARAM_JSON_SCHEMAS}


@router.post("/{file_id}/{analysis_date}/auto-score-v2")
async def auto_score_v2(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    request: PipelineConfigRequest | None = None,
) -> AutoScoreResponse:
    """Auto-score using the configurable pipeline."""
    from sleep_scoring_web.services.pipeline import (
        RawDiaryInput,
        ScoringPipeline,
    )

    await require_file_and_access(db, username, file_id)

    if request is None:
        request = PipelineConfigRequest()

    # Load activity data (noon-to-noon)
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

    params = request.to_pipeline_params()

    # Build raw diary
    raw_diary: RawDiaryInput | None = None
    from sleep_scoring_web.services.pipeline.params import GUIDER_NONE

    if request.period_guider != GUIDER_NONE:
        from sleep_scoring_web.db.models import DiaryEntry as DiaryEntryModel

        diary_result = await db.execute(
            select(DiaryEntryModel).where(
                and_(
                    DiaryEntryModel.file_id == file_id,
                    DiaryEntryModel.analysis_date == analysis_date,
                )
            )
        )
        diary = diary_result.scalar_one_or_none()
        if diary and _diary_time_present(diary.lights_out) and _diary_time_present(diary.wake_time):
            diary_naps, diary_nonwear = _extract_diary_periods(diary)

            raw_diary = RawDiaryInput(
                bed_time=diary.bed_time,
                onset_time=diary.lights_out,
                wake_time=diary.wake_time,
                naps=diary_naps,
                nonwear=diary_nonwear,
                analysis_date=analysis_date.isoformat(),
            )
        else:
            return AutoScoreResponse(notes=["Incomplete diary for this date - auto-score requires lights_out and wake_time"])

    # Run pipeline
    pipeline = ScoringPipeline(params)
    result = pipeline.run(
        timestamps,
        activity_counts,
        raw_diary=raw_diary,
    )

    legacy = result.to_legacy_dict()
    return AutoScoreResponse(
        sleep_markers=legacy["sleep_markers"],
        nap_markers=legacy["nap_markers"],
        notes=legacy["notes"],
    )
