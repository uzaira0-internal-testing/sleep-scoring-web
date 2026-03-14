"""
Audit log API — append-only action log per file/date/user.

Used for ML training data, reproducibility, and session replay.
"""

from __future__ import annotations

from datetime import date  # noqa: TC003 — Pydantic needs this at runtime
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi_logging import get_logger
from pydantic import BaseModel, Field
from sqlalchemy import func as sa_func
from sqlalchemy import select as sa_select
from sqlalchemy import tuple_
from sqlalchemy.exc import IntegrityError

from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword  # noqa: TC001 — FastAPI needs these at runtime
from sleep_scoring_web.db.models import AuditLogEntry

logger = get_logger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AuditEvent(BaseModel):
    """Single audit event from the frontend."""

    action: str = Field(max_length=50)
    client_timestamp: float = Field(description="Unix seconds when the action occurred")
    session_id: str = Field(max_length=36)
    sequence: int = Field(ge=0)
    payload: dict[str, Any] | None = None


class AuditBatchRequest(BaseModel):
    """Batch of audit events for a single file/date."""

    file_id: int
    analysis_date: date
    events: list[AuditEvent] = Field(min_length=1, max_length=500)


class AuditBatchResponse(BaseModel):
    """Response after logging audit events."""

    logged: int


class AuditLogResponse(BaseModel):
    """Single audit log entry returned to the client."""

    id: int
    action: str
    client_timestamp: float
    session_id: str
    sequence: int
    payload: dict | None
    username: str


class AuditSummaryResponse(BaseModel):
    """Summary of audit activity for a file/date."""

    total_events: int
    users: list[str]
    sessions: int
    first_event: float | None = None
    last_event: float | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/log", response_model=AuditBatchResponse)
async def log_audit_events(
    request: AuditBatchRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> AuditBatchResponse:
    """
    Append a batch of audit events for a file/date.

    Idempotent: duplicate (session_id, sequence) pairs are skipped.
    This handles the case where the client crashes after server receipt
    but before deleting from IndexedDB, causing a re-send on next load.
    """
    # Collect unique keys from the incoming batch
    incoming_keys = {(e.session_id, e.sequence) for e in request.events}

    # Check which already exist — filter on exact (session_id, sequence) pairs
    existing_result = await db.execute(
        sa_select(AuditLogEntry.session_id, AuditLogEntry.sequence).where(
            tuple_(AuditLogEntry.session_id, AuditLogEntry.sequence).in_(incoming_keys),
        )
    )
    existing_keys = {(row[0], row[1]) for row in existing_result.fetchall()}

    # Only insert events that don't already exist
    new_events = [e for e in request.events if (e.session_id, e.sequence) not in existing_keys]

    if not new_events:
        logger.debug(
            "All %d events already logged for file=%d date=%s user=%s",
            len(request.events),
            request.file_id,
            request.analysis_date,
            username,
        )
        return AuditBatchResponse(logged=0)

    entries = [
        AuditLogEntry(
            file_id=request.file_id,
            analysis_date=request.analysis_date,
            username=username,
            action=event.action,
            client_timestamp=event.client_timestamp,
            session_id=event.session_id,
            sequence=event.sequence,
            payload=event.payload,
        )
        for event in new_events
    ]

    try:
        db.add_all(entries)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        # Narrow check: only suppress the dedup constraint violation
        exc_str = str(exc).lower()
        if "uq_audit_session_sequence" in exc_str:
            logger.debug(
                "Concurrent flush dedup for file=%d date=%s user=%s",
                request.file_id,
                request.analysis_date,
                username,
            )
            return AuditBatchResponse(logged=0)
        # Unexpected constraint violation (FK, NOT NULL, etc.) — propagate
        logger.exception("Unexpected IntegrityError in audit log: %s", exc)
        raise

    logger.debug(
        "Logged %d audit events for file=%d date=%s user=%s",
        len(new_events),
        request.file_id,
        request.analysis_date,
        username,
    )
    return AuditBatchResponse(logged=len(new_events))


@router.get("/{file_id}/{analysis_date}", response_model=list[AuditLogResponse])
async def get_audit_log(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Annotated[str | None, Query(description="Filter by username")] = None,
    session_id: Annotated[str | None, Query(description="Filter by session")] = None,
    limit: Annotated[int, Query(ge=1, le=10000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AuditLogResponse]:
    """
    Retrieve audit log entries for a file/date, ordered chronologically.

    Supports filtering by username and/or session_id.
    """
    query = (
        sa_select(AuditLogEntry)
        .where(
            AuditLogEntry.file_id == file_id,
            AuditLogEntry.analysis_date == analysis_date,
        )
        .order_by(AuditLogEntry.client_timestamp, AuditLogEntry.sequence)
        .offset(offset)
        .limit(limit)
    )
    if username is not None:
        query = query.where(AuditLogEntry.username == username)
    if session_id is not None:
        query = query.where(AuditLogEntry.session_id == session_id)

    result = await db.execute(query)
    rows = result.scalars().all()
    return [
        AuditLogResponse(
            id=row.id,
            action=row.action,
            client_timestamp=row.client_timestamp,
            session_id=row.session_id,
            sequence=row.sequence,
            payload=row.payload,
            username=row.username,
        )
        for row in rows
    ]


@router.get("/{file_id}/{analysis_date}/summary", response_model=AuditSummaryResponse)
async def get_audit_summary(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
) -> AuditSummaryResponse:
    """Summary statistics for audit activity on a file/date."""
    base = sa_select(AuditLogEntry).where(
        AuditLogEntry.file_id == file_id,
        AuditLogEntry.analysis_date == analysis_date,
    )

    # Total events
    count_result = await db.execute(
        sa_select(sa_func.count()).select_from(base.subquery())
    )
    total = count_result.scalar() or 0

    if total == 0:
        return AuditSummaryResponse(total_events=0, users=[], sessions=0)

    # Distinct users
    users_result = await db.execute(
        sa_select(AuditLogEntry.username)
        .where(
            AuditLogEntry.file_id == file_id,
            AuditLogEntry.analysis_date == analysis_date,
        )
        .distinct()
    )
    users = [row[0] for row in users_result.fetchall()]

    # Distinct sessions
    sessions_result = await db.execute(
        sa_select(sa_func.count(AuditLogEntry.session_id.distinct())).where(
            AuditLogEntry.file_id == file_id,
            AuditLogEntry.analysis_date == analysis_date,
        )
    )
    sessions = sessions_result.scalar() or 0

    # Time range
    range_result = await db.execute(
        sa_select(
            sa_func.min(AuditLogEntry.client_timestamp),
            sa_func.max(AuditLogEntry.client_timestamp),
        ).where(
            AuditLogEntry.file_id == file_id,
            AuditLogEntry.analysis_date == analysis_date,
        )
    )
    row = range_result.fetchone()
    first_event = row[0] if row else None
    last_event = row[1] if row else None

    return AuditSummaryResponse(
        total_events=total,
        users=users,
        sessions=sessions,
        first_event=first_event,
        last_event=last_event,
    )
