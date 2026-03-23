"""
arq worker: background job definitions and WorkerSettings.

Run with:
    python -m arq sleep_scoring_web.worker.WorkerSettings
"""

from __future__ import annotations

import logging
import os
from typing import ClassVar

# Set BLAS/OpenMP thread limits BEFORE numpy/agcounts are imported at module level.
# If set in on_startup() it's too late — BLAS initializes on first import.
from sleep_scoring_web.constants import BLAS_NUM_THREADS

os.environ.setdefault("OMP_NUM_THREADS", BLAS_NUM_THREADS)
os.environ.setdefault("OPENBLAS_NUM_THREADS", BLAS_NUM_THREADS)

from arq.connections import RedisSettings
from sqlalchemy import delete, select

from sleep_scoring_web.config import settings
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import RawActivityData
from sleep_scoring_web.db.session import async_session_maker, init_db
from sleep_scoring_web.schemas.enums import FileStatus
from sleep_scoring_web.services.file_identity import infer_participant_id_and_timepoint_from_filename
from sleep_scoring_web.services.upload_processor import process_uploaded_file

logger = logging.getLogger(__name__)


async def process_file_job(
    ctx: dict,
    *,
    file_path: str,
    filename: str,
    is_gzip: bool,
    username: str,
    skip_rows: int,
    device_preset: str | None,
    replace: bool = False,
) -> None:
    """
    Arq job: create the DB record (if needed) then process the uploaded file.

    All heavy I/O and CPU work happens here in the worker process,
    keeping the web process event loop completely free.
    """
    async with async_session_maker() as db:
        result = await db.execute(select(FileModel).where(FileModel.filename == filename))
        existing = result.scalar_one_or_none()

        if existing:
            if not replace:
                logger.warning("File %s already exists (id=%d), skipping", filename, existing.id)
                return
            logger.info("Replacing existing file %s (id=%d)", filename, existing.id)
            await db.execute(delete(RawActivityData).where(RawActivityData.file_id == existing.id))
            existing.status = FileStatus.PROCESSING
            existing.row_count = None
            existing.original_path = file_path
            await db.commit()
            file_id = existing.id
        else:
            participant_id, _ = infer_participant_id_and_timepoint_from_filename(filename)
            file_model = FileModel(
                filename=filename,
                original_path=file_path,
                file_type="csv" if filename.lower().endswith((".csv", ".gz")) else "xlsx",
                participant_id=participant_id,
                status=FileStatus.PROCESSING,
                uploaded_by=username,
            )
            db.add(file_model)
            await db.commit()
            await db.refresh(file_model)
            file_id = file_model.id

    await process_uploaded_file(
        file_id=file_id,
        tus_file_path=file_path,
        original_filename=filename,
        is_gzip=is_gzip,
        username=username,
        skip_rows=skip_rows,
        device_preset=device_preset,
    )


async def startup(ctx: dict) -> None:
    """Worker startup: initialize DB tables."""
    await init_db()
    logger.info("arq worker started (max_jobs=%d)", settings.arq_max_jobs)


async def shutdown(ctx: dict) -> None:
    logger.info("arq worker shutting down")


class WorkerSettings:
    """arq worker configuration."""

    functions: ClassVar[list] = [process_file_job]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = settings.arq_max_jobs
    job_timeout = 7200  # 2 hours — large GENEActiv files can take a while
    keep_result = 3600  # Keep job result in Redis for 1 hour after completion
    health_check_interval = 30
