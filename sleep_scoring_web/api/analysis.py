"""Analysis API endpoints for cross-file summary statistics and scoring progress."""

from __future__ import annotations

import datetime
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from sleep_scoring_web.api.access import get_assigned_file_ids, is_admin_user
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword  # noqa: TC001 — FastAPI needs these at runtime
from sleep_scoring_web.db.models import ConsensusResult, DiaryEntry, File, Marker, RawActivityData, SleepMetric, UserAnnotation
from sleep_scoring_web.schemas.enums import FileStatus, MarkerCategory, MarkerType

router = APIRouter(prefix="/analysis", tags=["analysis"])


class FileSummary(BaseModel):
    file_id: int
    filename: str
    participant_id: str | None = None
    total_dates: int = 0
    scored_dates: int = 0
    has_diary: bool = False
    consensus_remaining: int = 0  # manually flagged dates needing consensus
    auto_flagged_count: int = 0  # system-detected: 2+ human scorers disagree


class AggregateMetrics(BaseModel):
    mean_tst_minutes: float | None = None
    mean_sleep_efficiency: float | None = None
    mean_waso_minutes: float | None = None
    mean_sleep_onset_latency: float | None = None
    total_sleep_periods: int = 0
    total_nap_periods: int = 0


class AnalysisSummaryResponse(BaseModel):
    total_files: int = 0
    total_dates: int = 0
    scored_dates: int = 0
    files_summary: list[FileSummary] = Field(default_factory=list)
    aggregate_metrics: AggregateMetrics = Field(default_factory=AggregateMetrics)


@router.get("/summary", response_model=AnalysisSummaryResponse)
async def get_analysis_summary(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> AnalysisSummaryResponse:
    """Get cross-file summary statistics and scoring progress."""
    # Apply assignment visibility for non-admin users.
    if is_admin_user(username):
        files_result = await db.execute(select(File).where(File.status == FileStatus.READY))
    else:
        assigned_ids = await get_assigned_file_ids(db, username)
        if not assigned_ids:
            return AnalysisSummaryResponse()
        files_result = await db.execute(
            select(File).where(
                File.status == FileStatus.READY,
                File.id.in_(assigned_ids),
            )
        )
    files = files_result.scalars().all()

    if not files:
        logger.warning("Analysis summary found no files for user=%s", username)
        return AnalysisSummaryResponse()

    # Batch queries to avoid N+1 per file
    file_ids = [f.id for f in files]

    # Scored dates are per-user, derived from THIS user's annotation state.
    # A date is scored if it has sleep markers OR nonwear markers OR no-sleep flag.
    annotations_result = await db.execute(
        select(
            UserAnnotation.file_id,
            UserAnnotation.analysis_date,
            UserAnnotation.is_no_sleep,
            UserAnnotation.sleep_markers_json,
            UserAnnotation.nonwear_markers_json,
        ).where(
            UserAnnotation.file_id.in_(file_ids),
            UserAnnotation.username == username,
        )
    )
    scored_dates_by_file: dict[int, set] = {}
    for ann in annotations_result.all():
        has_sleep = bool(ann.sleep_markers_json and len(ann.sleep_markers_json) > 0)
        has_nonwear = bool(ann.nonwear_markers_json and len(ann.nonwear_markers_json) > 0)
        if ann.is_no_sleep or has_sleep or has_nonwear:
            scored_dates_by_file.setdefault(ann.file_id, set()).add(ann.analysis_date)

    # Activity-date sets per file
    activity_dates_result = await db.execute(
        select(
            RawActivityData.file_id,
            func.date(RawActivityData.timestamp).label("activity_date"),
        )
        .where(RawActivityData.file_id.in_(file_ids))
        .group_by(RawActivityData.file_id, func.date(RawActivityData.timestamp))
    )
    activity_dates_by_file: dict[int, set] = {}
    for row in activity_dates_result.all():
        ad = row.activity_date
        # func.date() returns str in SQLite but date in PostgreSQL; normalise.
        if isinstance(ad, str):
            ad = datetime.date.fromisoformat(ad)
        activity_dates_by_file.setdefault(row.file_id, set()).add(ad)

    # Diary-date sets per file
    diary_dates_result = await db.execute(
        select(DiaryEntry.file_id, DiaryEntry.analysis_date)
        .where(DiaryEntry.file_id.in_(file_ids))
        .group_by(DiaryEntry.file_id, DiaryEntry.analysis_date)
    )
    diary_dates_by_file: dict[int, set] = {}
    for row in diary_dates_result.all():
        diary_dates_by_file.setdefault(row.file_id, set()).add(row.analysis_date)

    # Use study-date logic: if diary exists, total dates = diary ∩ activity; otherwise activity dates.
    valid_dates_by_file: dict[int, set] = {}
    for fid in file_ids:
        activity_dates = activity_dates_by_file.get(fid, set())
        diary_dates = diary_dates_by_file.get(fid, set())
        valid_dates_by_file[fid] = (activity_dates & diary_dates) if diary_dates else activity_dates

    # Re-count scored dates filtered to only valid (diary-filtered) dates
    scored_by_file: dict[int, int] = {}
    for fid, scored_set in scored_dates_by_file.items():
        valid = valid_dates_by_file.get(fid, set())
        scored_by_file[fid] = len(scored_set & valid) if valid else 0

    # Consensus remaining: dates that need review but haven't reached consensus.
    # A date needs consensus if EITHER:
    #   a) any annotation has status='submitted' (explicitly flagged), OR
    #   b) 2+ human scorers (excluding auto_score) have different marker sets
    #      (detected via distinct candidate_hash in consensus_candidates)
    # Minus dates where ConsensusResult.has_consensus is already True.

    # (a) Explicitly flagged for consensus
    submitted_result = await db.execute(
        select(UserAnnotation.file_id, UserAnnotation.analysis_date)
        .where(
            UserAnnotation.file_id.in_(file_ids),
            UserAnnotation.needs_consensus.is_(True),
        )
        .group_by(UserAnnotation.file_id, UserAnnotation.analysis_date)
    )
    needs_consensus: dict[int, set] = {}
    for row in submitted_result.all():
        needs_consensus.setdefault(row.file_id, set()).add(row.analysis_date)

    # (b) Dates with 2+ distinct human candidate hashes (auto-detected discrepancy)
    from sleep_scoring_web.services.consensus import get_auto_flagged_dates

    auto_flagged = await get_auto_flagged_dates(db, file_ids)

    # Subtract dates where consensus has been reached
    consensus_reached_result = await db.execute(
        select(ConsensusResult.file_id, ConsensusResult.analysis_date).where(
            ConsensusResult.file_id.in_(file_ids),
            ConsensusResult.has_consensus.is_(True),
        )
    )
    consensus_reached: dict[int, set] = {}
    for row in consensus_reached_result.all():
        consensus_reached.setdefault(row.file_id, set()).add(row.analysis_date)

    # Compute counts separately — manual vs auto-flagged
    consensus_remaining_by_file: dict[int, int] = {}
    for fid, dates in needs_consensus.items():
        reached = consensus_reached.get(fid, set())
        consensus_remaining_by_file[fid] = len(dates - reached)

    auto_flagged_by_file: dict[int, int] = {}
    for fid, dates in auto_flagged.items():
        reached = consensus_reached.get(fid, set())
        auto_flagged_by_file[fid] = len(dates - reached)

    files_summary: list[FileSummary] = []
    total_dates = 0
    scored_dates_total = 0

    for f in files:
        file_scored = scored_by_file.get(f.id, 0)
        file_total_dates = len(valid_dates_by_file.get(f.id, set()))
        has_diary = len(diary_dates_by_file.get(f.id, set())) > 0

        files_summary.append(
            FileSummary(
                file_id=f.id,
                filename=f.filename,
                participant_id=f.participant_id,
                total_dates=file_total_dates,
                scored_dates=file_scored,
                has_diary=has_diary,
                consensus_remaining=consensus_remaining_by_file.get(f.id, 0),
                auto_flagged_count=auto_flagged_by_file.get(f.id, 0),
            )
        )
        total_dates += file_total_dates
        scored_dates_total += file_scored

    # Aggregate metrics from sleep_metrics table
    metrics_result = await db.execute(
        select(
            func.avg(SleepMetric.total_sleep_time_minutes),
            func.avg(SleepMetric.sleep_efficiency),
            func.avg(SleepMetric.waso_minutes),
            func.avg(SleepMetric.sleep_onset_latency_minutes),
            func.count(),
        ).where(
            SleepMetric.total_sleep_time_minutes.is_not(None),
            SleepMetric.file_id.in_(file_ids),
            SleepMetric.scored_by == username,
        )
    )
    row = metrics_result.one_or_none()

    # Sleep + nap counts in a single query using conditional aggregation
    from sqlalchemy import case

    marker_counts_result = await db.execute(
        select(
            func.count().label("sleep_count"),
            func.count(case((Marker.marker_type == MarkerType.NAP, 1))).label("nap_count"),
        )
        .select_from(Marker)
        .where(
            Marker.file_id.in_(file_ids),
            Marker.marker_category == MarkerCategory.SLEEP,
            Marker.created_by == username,
        )
    )
    counts_row = marker_counts_result.one()
    sleep_count = counts_row.sleep_count or 0
    nap_count = counts_row.nap_count or 0

    aggregate = AggregateMetrics(
        mean_tst_minutes=round(row[0], 1) if row and row[0] else None,
        mean_sleep_efficiency=round(row[1], 1) if row and row[1] else None,
        mean_waso_minutes=round(row[2], 1) if row and row[2] else None,
        mean_sleep_onset_latency=round(row[3], 1) if row and row[3] else None,
        total_sleep_periods=sleep_count,
        total_nap_periods=nap_count,
    )

    return AnalysisSummaryResponse(
        total_files=len(files),
        total_dates=total_dates,
        scored_dates=scored_dates_total,
        files_summary=files_summary,
        aggregate_metrics=aggregate,
    )
