"""
TUS resumable upload router and processing status endpoint.

Uses tuspyserver to handle chunked resumable uploads via the TUS protocol.
After upload completes, spawns a background task to process the file.
"""

from __future__ import annotations

import asyncio
import logging
import secrets

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from tuspyserver import create_tus_router

from sleep_scoring_web.api.deps import DbSession, VerifiedPassword  # noqa: TC001 — FastAPI needs these at runtime
from sleep_scoring_web.config import settings
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.session import async_session_maker
from sleep_scoring_web.schemas.enums import FileStatus
from sleep_scoring_web.schemas.models import ProcessingStatusResponse
from sleep_scoring_web.services.file_identity import infer_participant_id_and_timepoint_from_filename
from sleep_scoring_web.services.processing_tracker import get_progress
from sleep_scoring_web.services.upload_processor import process_uploaded_file

logger = logging.getLogger(__name__)

# Custom router for processing status (separate from TUS router)
router = APIRouter()

# Track background tasks to prevent GC and surface exceptions
_background_tasks: set[asyncio.Task] = set()


def _on_upload_complete(file_path: str, metadata: dict) -> None:
    """
    Called by tuspyserver when a file upload is fully complete.

    Creates a FileModel in the database and spawns background processing.
    """
    filename = metadata.get("filename", "unknown.csv")
    is_gzip = metadata.get("is_gzip", "false").lower() == "true"
    username = metadata.get("username", "anonymous")
    skip_rows_str = metadata.get("skip_rows", "10")
    device_preset = metadata.get("device_preset")

    try:
        skip_rows = int(skip_rows_str)
    except ValueError:
        skip_rows = 10

    logger.info(
        "TUS upload complete: file=%s, path=%s, is_gzip=%s, username=%s",
        filename,
        file_path,
        is_gzip,
        username,
    )

    # Create file record and spawn processing in background
    task = asyncio.ensure_future(
        _create_and_process(
            file_path=file_path,
            filename=filename,
            is_gzip=is_gzip,
            username=username,
            skip_rows=skip_rows,
            device_preset=device_preset,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _create_and_process(
    file_path: str,
    filename: str,
    is_gzip: bool,
    username: str,
    skip_rows: int,
    device_preset: str | None,
) -> None:
    """Create FileModel and start background processing."""
    try:
        async with async_session_maker() as db:
            # Check for existing file
            result = await db.execute(select(FileModel).where(FileModel.filename == filename))
            existing = result.scalar_one_or_none()
            if existing:
                logger.warning("File %s already exists (id=%d), skipping TUS upload", filename, existing.id)
                return

            # Infer participant_id from filename
            participant_id, _timepoint = infer_participant_id_and_timepoint_from_filename(filename)

            file_model = FileModel(
                filename=filename,
                original_path=file_path,
                file_type="csv",
                participant_id=participant_id,
                status=FileStatus.PROCESSING,
                uploaded_by=username,
            )
            db.add(file_model)
            await db.commit()
            await db.refresh(file_model)
            file_id = file_model.id

        # Run processing directly (already in a background task)
        await process_uploaded_file(
            file_id=file_id,
            tus_file_path=file_path,
            original_filename=filename,
            is_gzip=is_gzip,
            username=username,
            skip_rows=skip_rows,
            device_preset=device_preset,
        )

    except Exception:
        logger.exception("Failed to create file record for TUS upload: %s", filename)


def _pre_create_hook(metadata: dict, upload_info: dict) -> None:
    """
    Validate upload before accepting it.

    Checks filename extension and auth metadata.
    """
    filename = metadata.get("filename", "")
    if not filename:
        raise HTTPException(status_code=400, detail="Filename required in upload metadata")

    # Validate extension
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    allowed = {"csv", "xlsx", "xls", "gz"}
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: .{suffix}. Allowed: {', '.join(sorted(allowed))}",
        )

    # Validate auth metadata
    site_password = metadata.get("site_password", "")
    if settings.site_password and not secrets.compare_digest(
        site_password.encode("utf-8"),
        settings.site_password.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="Invalid site password")


# Create TUS router from tuspyserver
tus_router = create_tus_router(
    files_dir=settings.tus_upload_dir,
    max_size=settings.tus_max_upload_size_gb * 1024**3,
    days_to_keep=settings.tus_stale_days,
    on_upload_complete=_on_upload_complete,
    pre_create_hook=_pre_create_hook,
)

# Cache FileStatus values for fast lookup
_FILE_STATUS_VALUES = frozenset(s.value for s in FileStatus)


@router.get("/files/{file_id}/processing-status", response_model=ProcessingStatusResponse)
async def get_processing_status(
    file_id: int,
    db: DbSession,
    _: VerifiedPassword,
) -> ProcessingStatusResponse:
    """Get processing status for a file (in-memory tracker or DB fallback)."""
    # Check in-memory tracker first
    progress = get_progress(file_id)
    if progress is not None:
        return ProcessingStatusResponse(
            file_id=file_id,
            status=FileStatus(progress.status) if progress.status in _FILE_STATUS_VALUES else FileStatus.PROCESSING,
            phase=progress.phase or None,
            percent=progress.percent,
            rows_processed=progress.rows_processed,
            total_rows_estimate=progress.total_rows_estimate,
            error=progress.error,
            started_at=progress.started_at,
        )

    # Fall back to database status
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file_model = result.scalar_one_or_none()
    if file_model is None:
        raise HTTPException(status_code=404, detail="File not found")

    error_msg = None
    if file_model.metadata_json and isinstance(file_model.metadata_json, dict):
        error_msg = file_model.metadata_json.get("error")

    return ProcessingStatusResponse(
        file_id=file_id,
        status=file_model.status,
        phase=None,
        percent=100.0 if file_model.status == FileStatus.READY else 0.0,
        rows_processed=file_model.row_count or 0,
        error=error_msg,
    )
