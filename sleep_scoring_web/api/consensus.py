"""Consensus API endpoints for multi-user annotation comparison and resolution."""

from __future__ import annotations

import secrets
from collections import OrderedDict
from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select, tuple_
from sqlalchemy.exc import IntegrityError

from sleep_scoring_web.api.access import (
    get_assigned_file_ids,
    is_admin_user,
    require_file_access,
    user_can_access_file,
)
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword  # noqa: TC001 — FastAPI needs these at runtime
from sleep_scoring_web.config import get_settings
from sleep_scoring_web.db.models import (
    ConsensusCandidate,
    ConsensusResult,
    ConsensusVote,
    Marker,
    ResolvedAnnotation,
    UserAnnotation,
)
from sleep_scoring_web.db.models import (
    File as FileModel,
)
from sleep_scoring_web.schemas.enums import VerificationStatus
from sleep_scoring_web.services.consensus import compute_candidate_hash
from sleep_scoring_web.services.consensus_realtime import (
    broadcast_consensus_update,
    consensus_realtime_broker,
)

router = APIRouter(prefix="/consensus", tags=["consensus"])


# =============================================================================
# Pydantic Models
# =============================================================================


class AnnotationSummary(BaseModel):
    """Summary of a single user's annotation for a file/date."""

    username: str
    sleep_markers_json: list[dict[str, Any]] | None = None
    nonwear_markers_json: list[dict[str, Any]] | None = None
    is_no_sleep: bool = False
    algorithm_used: str | None = None
    status: str = VerificationStatus.DRAFT
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class ConsensusDateResponse(BaseModel):
    """All annotations for a specific file/date."""

    file_id: int
    analysis_date: date
    annotations: list[AnnotationSummary] = Field(default_factory=list)
    has_resolution: bool = False
    resolution: ResolvedAnnotationResponse | None = None


class ResolvedAnnotationResponse(BaseModel):
    """Admin-resolved annotation data."""

    resolved_by: str
    resolved_at: str | None = None
    resolution_notes: str | None = None
    final_sleep_markers_json: list[dict[str, Any]] | None = None
    final_nonwear_markers_json: list[dict[str, Any]] | None = None


class ResolveRequest(BaseModel):
    """Request to resolve a disputed annotation."""

    final_sleep_markers_json: list[dict[str, Any]] = Field(default_factory=list)
    final_nonwear_markers_json: list[dict[str, Any]] = Field(default_factory=list)
    resolution_notes: str | None = None


class ConsensusOverviewItem(BaseModel):
    """Overview item for dates needing consensus review."""

    file_id: int
    filename: str
    analysis_date: date
    annotation_count: int
    usernames: list[str]
    has_resolution: bool = False


class ConsensusOverviewResponse(BaseModel):
    """Overview of all dates with multiple annotations."""

    items: list[ConsensusOverviewItem] = Field(default_factory=list)
    total_dates_with_multiple: int = 0


class CandidateVoteSummary(BaseModel):
    """Consensus candidate marker set with vote counts."""

    candidate_id: int
    label: str
    source_type: str  # "auto" | "user"
    sleep_markers_json: list[dict[str, Any]] | None = None
    nonwear_markers_json: list[dict[str, Any]] | None = None
    is_no_sleep: bool = False
    vote_count: int = 0
    selected_by_me: bool = False
    created_at: str | None = None


class ConsensusBallotResponse(BaseModel):
    """Ballot view for voting on marker sets."""

    file_id: int
    analysis_date: date
    candidates: list[CandidateVoteSummary] = Field(default_factory=list)
    total_votes: int = 0
    leading_candidate_id: int | None = None
    my_vote_candidate_id: int | None = None
    updated_at: str | None = None


class VoteRequest(BaseModel):
    """Cast/replace vote for a candidate; null clears vote."""

    candidate_id: int | None = None


async def _verify_websocket_auth(websocket: WebSocket) -> str | None:
    """Validate site password query param for websocket clients."""
    settings = get_settings()
    username = (websocket.query_params.get("username") or "anonymous").strip() or "anonymous"

    if settings.site_password:
        provided_password = websocket.query_params.get("site_password") or ""
        if not provided_password or not secrets.compare_digest(
            provided_password.encode("utf-8"),
            settings.site_password.encode("utf-8"),
        ):
            await websocket.close(code=1008, reason="Invalid site password")
            return None

    return username


# =============================================================================
# Internal Helpers
# =============================================================================


async def _backfill_candidates_from_annotations(
    db: DbSession,
    *,
    file_id: int,
    analysis_date: date,
) -> None:
    """
    Ensure each submitted annotation is represented as a candidate.

    This lets legacy data vote immediately after rollout.
    """
    ann_result = await db.execute(
        select(UserAnnotation).where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
                UserAnnotation.status == VerificationStatus.SUBMITTED,
            )
        )
    )
    annotations = ann_result.scalars().all()
    if not annotations:
        return

    existing_result = await db.execute(
        select(ConsensusCandidate.source_username).where(
            and_(
                ConsensusCandidate.file_id == file_id,
                ConsensusCandidate.analysis_date == analysis_date,
            )
        )
    )
    existing_usernames = {row[0] for row in existing_result.all()}

    inserted = False
    for ann in annotations:
        # Skip if this user already has a candidate for this file/date
        if ann.username in existing_usernames:
            continue

        # Skip broken annotations: no markers AND not flagged as no-sleep
        has_markers = ann.sleep_markers_json and len(ann.sleep_markers_json) > 0
        if not has_markers and not ann.is_no_sleep:
            continue

        candidate_hash = compute_candidate_hash(
            sleep_markers=ann.sleep_markers_json,
            nonwear_markers=ann.nonwear_markers_json,
            is_no_sleep=ann.is_no_sleep,
        )
        db.add(
            ConsensusCandidate(
                file_id=file_id,
                analysis_date=analysis_date,
                source_username=ann.username,
                candidate_hash=candidate_hash,
                sleep_markers_json=ann.sleep_markers_json,
                nonwear_markers_json=ann.nonwear_markers_json,
                is_no_sleep=ann.is_no_sleep,
                algorithm_used=ann.algorithm_used,
                notes=ann.notes,
            )
        )
        existing_usernames.add(ann.username)
        inserted = True

    if inserted:
        try:
            await db.commit()
        except IntegrityError:
            # Concurrent ballot view already inserted the same candidate — safe to ignore
            await db.rollback()


async def _build_ballot_response(
    db: DbSession,
    *,
    file_id: int,
    analysis_date: date,
    username: str,
) -> ConsensusBallotResponse:
    # Backfill legacy annotations on read so old data is immediately votable.
    await _backfill_candidates_from_annotations(db, file_id=file_id, analysis_date=analysis_date)

    candidates_result = await db.execute(
        select(ConsensusCandidate)
        .where(
            and_(
                ConsensusCandidate.file_id == file_id,
                ConsensusCandidate.analysis_date == analysis_date,
            )
        )
        .order_by(ConsensusCandidate.created_at.asc(), ConsensusCandidate.id.asc())
    )
    candidates = candidates_result.scalars().all()

    vote_counts_result = await db.execute(
        select(ConsensusVote.candidate_id, func.count(ConsensusVote.id))
        .where(
            and_(
                ConsensusVote.file_id == file_id,
                ConsensusVote.analysis_date == analysis_date,
                ConsensusVote.candidate_id.is_not(None),
            )
        )
        .group_by(ConsensusVote.candidate_id)
    )
    vote_counts = {row[0]: int(row[1]) for row in vote_counts_result.all()}

    my_vote_result = await db.execute(
        select(ConsensusVote).where(
            and_(
                ConsensusVote.file_id == file_id,
                ConsensusVote.analysis_date == analysis_date,
                ConsensusVote.voter_username == username,
            )
        )
    )
    my_vote = my_vote_result.scalar_one_or_none()
    my_vote_candidate_id = my_vote.candidate_id if my_vote else None

    total_votes = sum(vote_counts.values())

    # Group candidates by candidate_hash so identical marker sets show as one
    # card with comma-separated scorer names.
    groups: OrderedDict[str, list[ConsensusCandidate]] = OrderedDict()
    for c in candidates:
        key = c.candidate_hash or f"__nohash_{c.id}"
        groups.setdefault(key, []).append(c)

    # Map any member candidate_id → canonical (first in group) for vote mapping
    id_to_canonical: dict[int, int] = {}
    for group in groups.values():
        canonical_id = group[0].id
        for c in group:
            id_to_canonical[c.id] = canonical_id

    # Remap my_vote to canonical so frontend .find() matches
    canonical_my_vote = id_to_canonical.get(my_vote_candidate_id) if my_vote_candidate_id else None

    summaries: list[CandidateVoteSummary] = []
    for idx, (_, group) in enumerate(groups.items(), start=1):
        canonical = group[0]
        # Merge labels
        labels: list[str] = []
        has_auto = False
        for c in group:
            if c.source_username == "auto_score":
                labels.append("Auto-Score")
                has_auto = True
            else:
                labels.append(c.source_username or f"Set {idx}")
        merged_label = ", ".join(labels)
        # Sum votes across all IDs in the group
        total_group_votes = sum(vote_counts.get(c.id, 0) for c in group)
        # selected_by_me if my vote points to any member
        selected = my_vote_candidate_id is not None and any(c.id == my_vote_candidate_id for c in group)
        summaries.append(
            CandidateVoteSummary(
                candidate_id=canonical.id,
                label=merged_label,
                source_type="auto" if has_auto else "user",
                sleep_markers_json=canonical.sleep_markers_json,
                nonwear_markers_json=canonical.nonwear_markers_json,
                is_no_sleep=canonical.is_no_sleep,
                vote_count=total_group_votes,
                selected_by_me=selected,
                created_at=canonical.created_at.isoformat() if canonical.created_at else None,
            )
        )

    leader = None
    if summaries:
        leader = max(summaries, key=lambda s: (s.vote_count, -s.candidate_id))
        leading_candidate_id = leader.candidate_id if leader.vote_count > 0 else None
    else:
        leading_candidate_id = None

    latest_update_result = await db.execute(
        select(func.max(ConsensusVote.updated_at)).where(
            and_(
                ConsensusVote.file_id == file_id,
                ConsensusVote.analysis_date == analysis_date,
            )
        )
    )
    latest_update = latest_update_result.scalar_one_or_none()

    return ConsensusBallotResponse(
        file_id=file_id,
        analysis_date=analysis_date,
        candidates=summaries,
        total_votes=total_votes,
        leading_candidate_id=leading_candidate_id,
        my_vote_candidate_id=canonical_my_vote,
        updated_at=latest_update.isoformat() if latest_update else None,
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.websocket("/stream")
async def consensus_stream(websocket: WebSocket) -> None:
    """
    Subscribe to realtime consensus updates for one file/date.

    Query params:
    - file_id: int
    - analysis_date: YYYY-MM-DD
    - username: optional (honor-system display identity)
    - site_password: required if site password is configured
    """
    username = await _verify_websocket_auth(websocket)
    if username is None:
        return

    file_id_raw = websocket.query_params.get("file_id")
    analysis_date_raw = websocket.query_params.get("analysis_date")
    if not file_id_raw or not analysis_date_raw:
        await websocket.close(code=1008, reason="Missing file_id or analysis_date")
        return

    try:
        file_id = int(file_id_raw)
        analysis_date = date.fromisoformat(analysis_date_raw)
    except ValueError:
        await websocket.close(code=1008, reason="Invalid file_id or analysis_date")
        return

    # Enforce assignment access before subscribing to this file/date channel.
    from sleep_scoring_web.db.session import async_session_maker

    async with async_session_maker() as db:
        allowed = await user_can_access_file(db, username, file_id)
    if not allowed:
        await websocket.close(code=1008, reason="File not found")
        return

    await websocket.accept()
    await consensus_realtime_broker.subscribe(
        websocket,
        file_id=file_id,
        analysis_date=analysis_date,
    )
    await websocket.send_json(
        {
            "type": "consensus_connected",
            "file_id": file_id,
            "analysis_date": analysis_date.isoformat(),
            "username": username,
        }
    )

    try:
        while True:
            await websocket.receive()
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Starlette test websocket sessions can surface disconnect as RuntimeError.
        pass
    finally:
        await consensus_realtime_broker.unsubscribe(
            websocket,
            file_id=file_id,
            analysis_date=analysis_date,
        )


@router.get("/overview", response_model=ConsensusOverviewResponse)
async def get_consensus_overview(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> ConsensusOverviewResponse:
    """
    Get overview of all dates with 2+ user annotations.

    Returns dates that need consensus review, ordered by annotation count descending.
    """
    # Subquery: group annotations by file_id + analysis_date, count and filter >= 2
    annotation_counts = (
        select(
            UserAnnotation.file_id,
            UserAnnotation.analysis_date,
            func.count(UserAnnotation.id).label("annotation_count"),
        )
        .where(UserAnnotation.status == VerificationStatus.SUBMITTED)
        .group_by(UserAnnotation.file_id, UserAnnotation.analysis_date)
        .having(func.count(UserAnnotation.id) >= 2)
        .subquery()
    )

    # Join with files to get filename
    query = (
        select(
            annotation_counts.c.file_id,
            FileModel.filename,
            annotation_counts.c.analysis_date,
            annotation_counts.c.annotation_count,
        )
        .join(FileModel, FileModel.id == annotation_counts.c.file_id)
        .order_by(annotation_counts.c.annotation_count.desc())
    )
    if not is_admin_user(username):
        assigned_ids = await get_assigned_file_ids(db, username)
        if not assigned_ids:
            return ConsensusOverviewResponse(items=[], total_dates_with_multiple=0)
        query = query.where(annotation_counts.c.file_id.in_(assigned_ids))

    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return ConsensusOverviewResponse(items=[], total_dates_with_multiple=0)

    # Batch: get all usernames for matching file/date pairs
    file_date_pairs = [(row.file_id, row.analysis_date) for row in rows]
    users_result = await db.execute(
        select(
            UserAnnotation.file_id,
            UserAnnotation.analysis_date,
            UserAnnotation.username,
        ).where(
            and_(
                UserAnnotation.status == VerificationStatus.SUBMITTED,
                # Filter to exact (file_id, analysis_date) pairs — not just file_id
                tuple_(UserAnnotation.file_id, UserAnnotation.analysis_date).in_(file_date_pairs),
            )
        )
    )
    # Build a lookup: (file_id, analysis_date) -> [usernames]
    usernames_lookup: dict[tuple[int, Any], list[str]] = {}
    for u_row in users_result.all():
        key = (u_row.file_id, u_row.analysis_date)
        usernames_lookup.setdefault(key, []).append(u_row.username)

    # Batch: check which file/date pairs have resolutions
    resolved_result = await db.execute(
        select(ResolvedAnnotation.file_id, ResolvedAnnotation.analysis_date).where(
            tuple_(ResolvedAnnotation.file_id, ResolvedAnnotation.analysis_date).in_(file_date_pairs)
        )
    )
    resolved_set = {(r.file_id, r.analysis_date) for r in resolved_result.all()}

    items: list[ConsensusOverviewItem] = []
    for row in rows:
        key = (row.file_id, row.analysis_date)
        items.append(
            ConsensusOverviewItem(
                file_id=row.file_id,
                filename=row.filename,
                analysis_date=row.analysis_date,
                annotation_count=row.annotation_count,
                usernames=usernames_lookup.get(key, []),
                has_resolution=key in resolved_set,
            )
        )

    return ConsensusOverviewResponse(
        items=items,
        total_dates_with_multiple=len(items),
    )


@router.get("/{file_id}/{analysis_date}", response_model=ConsensusDateResponse)
async def get_consensus_for_date(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> ConsensusDateResponse:
    """
    Get all user annotations for a specific file/date.

    Returns all submitted annotations plus any admin resolution.
    """
    await require_file_access(db, username, file_id)

    # Get all annotations
    result = await db.execute(
        select(UserAnnotation).where(
            and_(
                UserAnnotation.file_id == file_id,
                UserAnnotation.analysis_date == analysis_date,
            )
        )
    )
    annotations = result.scalars().all()

    annotation_summaries = [
        AnnotationSummary(
            username=a.username,
            sleep_markers_json=a.sleep_markers_json,
            nonwear_markers_json=a.nonwear_markers_json,
            is_no_sleep=a.is_no_sleep,
            algorithm_used=a.algorithm_used,
            status=a.status,
            notes=a.notes,
            created_at=a.created_at.isoformat() if a.created_at else None,
            updated_at=a.updated_at.isoformat() if a.updated_at else None,
        )
        for a in annotations
    ]

    # Check for resolution
    resolved_result = await db.execute(
        select(ResolvedAnnotation).where(
            and_(
                ResolvedAnnotation.file_id == file_id,
                ResolvedAnnotation.analysis_date == analysis_date,
            )
        )
    )
    resolved = resolved_result.scalar_one_or_none()

    resolution = None
    if resolved:
        resolution = ResolvedAnnotationResponse(
            resolved_by=resolved.resolved_by,
            resolved_at=resolved.resolved_at.isoformat() if resolved.resolved_at else None,
            resolution_notes=resolved.resolution_notes,
            final_sleep_markers_json=resolved.final_sleep_markers_json,
            final_nonwear_markers_json=resolved.final_nonwear_markers_json,
        )

    return ConsensusDateResponse(
        file_id=file_id,
        analysis_date=analysis_date,
        annotations=annotation_summaries,
        has_resolution=resolved is not None,
        resolution=resolution,
    )


@router.get("/{file_id}/{analysis_date}/ballot", response_model=ConsensusBallotResponse)
async def get_consensus_ballot(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> ConsensusBallotResponse:
    """Get vote-ready candidate marker sets with aggregate counts."""
    await require_file_access(db, username, file_id)

    # require_file_access short-circuits for admins without checking file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    if not file_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return await _build_ballot_response(
        db,
        file_id=file_id,
        analysis_date=analysis_date,
        username=username,
    )


@router.post("/{file_id}/{analysis_date}/vote", response_model=ConsensusBallotResponse)
async def cast_consensus_vote(
    file_id: int,
    analysis_date: date,
    data: VoteRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> ConsensusBallotResponse:
    """
    Cast or replace vote for a consensus candidate.

    One active vote per user/date. candidate_id=null clears the vote.
    """
    await require_file_access(db, username, file_id)

    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    if not file_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if data.candidate_id is not None:
        candidate_result = await db.execute(
            select(ConsensusCandidate).where(
                and_(
                    ConsensusCandidate.id == data.candidate_id,
                    ConsensusCandidate.file_id == file_id,
                    ConsensusCandidate.analysis_date == analysis_date,
                )
            )
        )
        if not candidate_result.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # Race-safe upsert: retry once if concurrent insert violates uniqueness.
    for attempt in range(2):
        existing_vote_result = await db.execute(
            select(ConsensusVote).where(
                and_(
                    ConsensusVote.file_id == file_id,
                    ConsensusVote.analysis_date == analysis_date,
                    ConsensusVote.voter_username == username,
                )
            )
        )
        existing_vote = existing_vote_result.scalar_one_or_none()

        if existing_vote:
            existing_vote.candidate_id = data.candidate_id
        else:
            db.add(
                ConsensusVote(
                    file_id=file_id,
                    analysis_date=analysis_date,
                    voter_username=username,
                    candidate_id=data.candidate_id,
                )
            )

        try:
            await db.commit()
            break
        except IntegrityError:
            await db.rollback()
            db.expunge_all()
            if attempt == 1:
                raise
    await broadcast_consensus_update(
        file_id=file_id,
        analysis_date=analysis_date,
        event="vote_changed",
        username=username,
        candidate_id=data.candidate_id,
    )

    return await _build_ballot_response(
        db,
        file_id=file_id,
        analysis_date=analysis_date,
        username=username,
    )


@router.post("/{file_id}/{analysis_date}/resolve", response_model=ResolvedAnnotationResponse)
async def resolve_consensus(
    file_id: int,
    analysis_date: date,
    data: ResolveRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> ResolvedAnnotationResponse:
    """
    Admin resolves disputed annotations for a file/date.

    Creates or updates the resolved annotation with the final markers.
    Stores resolution separately — does NOT overwrite the main Marker table.
    Main markers are preserved but the date is marked as "resolved" status
    via the resolved_annotations table.
    """
    await require_file_access(db, username, file_id)

    # Admin check: only users in ADMIN_USERNAMES can resolve consensus
    from sleep_scoring_web.config import get_settings

    settings = get_settings()
    if username.lower() not in settings.admin_usernames_list:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin users can resolve consensus disputes",
        )
    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    if not file_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Check for existing resolution
    result = await db.execute(
        select(ResolvedAnnotation).where(
            and_(
                ResolvedAnnotation.file_id == file_id,
                ResolvedAnnotation.analysis_date == analysis_date,
            )
        )
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.final_sleep_markers_json = data.final_sleep_markers_json
        existing.final_nonwear_markers_json = data.final_nonwear_markers_json
        existing.resolution_notes = data.resolution_notes
        existing.resolved_by = username
        resolved = existing
    else:
        resolved = ResolvedAnnotation(
            file_id=file_id,
            analysis_date=analysis_date,
            final_sleep_markers_json=data.final_sleep_markers_json,
            final_nonwear_markers_json=data.final_nonwear_markers_json,
            resolved_by=username,
            resolution_notes=data.resolution_notes,
        )
        db.add(resolved)

    # Update consensus_results to reflect resolution
    consensus_result = await db.execute(
        select(ConsensusResult).where(
            and_(
                ConsensusResult.file_id == file_id,
                ConsensusResult.analysis_date == analysis_date,
            )
        )
    )
    existing_consensus = consensus_result.scalar_one_or_none()
    if existing_consensus:
        existing_consensus.has_consensus = True
        existing_consensus.consensus_sleep_markers_json = data.final_sleep_markers_json
        existing_consensus.consensus_nonwear_markers_json = data.final_nonwear_markers_json
    else:
        new_consensus = ConsensusResult(
            file_id=file_id,
            analysis_date=analysis_date,
            has_consensus=True,
            consensus_sleep_markers_json=data.final_sleep_markers_json,
            consensus_nonwear_markers_json=data.final_nonwear_markers_json,
        )
        db.add(new_consensus)

    await db.commit()
    await db.refresh(resolved)
    await broadcast_consensus_update(
        file_id=file_id,
        analysis_date=analysis_date,
        event="consensus_resolved",
        username=username,
    )

    return ResolvedAnnotationResponse(
        resolved_by=resolved.resolved_by,
        resolved_at=resolved.resolved_at.isoformat() if resolved.resolved_at else None,
        resolution_notes=resolved.resolution_notes,
        final_sleep_markers_json=resolved.final_sleep_markers_json,
        final_nonwear_markers_json=resolved.final_nonwear_markers_json,
    )
