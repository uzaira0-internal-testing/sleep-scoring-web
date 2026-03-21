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
from sleep_scoring_web.schemas.enums import FileStatus
from sleep_scoring_web.schemas.models import ProcessingStatusResponse
from sleep_scoring_web.services.processing_tracker import get_progress

logger = logging.getLogger(__name__)

# Custom router for processing status (separate from TUS router)
router = APIRouter()

# Track short-lived enqueue tasks to prevent GC
_background_tasks: set[asyncio.Task] = set()


def _on_upload_complete(file_path: str, metadata: dict) -> None:
    """
    Called by tuspyserver when a file upload is fully complete.

    Enqueues a background job via arq to create the DB record and process the file.
    The actual work runs in a separate worker process — the web event loop stays free.
    """
    filename = metadata.get("filename", "unknown.csv")
    is_gzip = metadata.get("is_gzip", "false").lower() == "true"
    username = metadata.get("username", "anonymous")
    skip_rows_str = metadata.get("skip_rows", "10")
    device_preset = metadata.get("device_preset")
    replace = metadata.get("replace", "false").lower() == "true"

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

    async def _enqueue() -> None:
        try:
            from sleep_scoring_web import queue
            from sleep_scoring_web.worker import process_file_job

            pool = queue.get_pool()
            job = await pool.enqueue_job(
                process_file_job.__name__,
                file_path=file_path,
                filename=filename,
                is_gzip=is_gzip,
                username=username,
                skip_rows=skip_rows,
                device_preset=device_preset,
                replace=replace,
            )
            logger.info("Enqueued processing job %s for %s", job and job.job_id, filename)
        except Exception:
            logger.exception("Failed to enqueue processing job for %s — falling back to inline processing", filename)
            try:
                from sleep_scoring_web.services.upload_processor import process_uploaded_file

                await process_uploaded_file(file_path, filename, is_gzip, username, skip_rows=skip_rows)
                logger.info("Inline processing completed for %s", filename)
            except Exception:
                logger.exception("Inline processing also failed for %s — file will need manual reprocessing", filename)

    task = asyncio.ensure_future(_enqueue())
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


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
