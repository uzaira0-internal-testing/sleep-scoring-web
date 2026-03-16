"""
File upload and management API endpoints.

Provides endpoints for uploading, listing, and managing activity data files.
Uses FastAPI BackgroundTasks for non-blocking file processing.

Note: We intentionally avoid `from __future__ import annotations` here
because FastAPI's dependency injection needs actual types, not string
annotations. Using Annotated types requires runtime resolution.
"""

import asyncio
import logging
import math
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

logger = logging.getLogger(__name__)
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import func, or_, select

from sleep_scoring_web.api.access import is_admin_user, require_file_access
from sleep_scoring_web.api.deps import ApiKey, DbSession, Username, VerifiedPassword
from sleep_scoring_web.config import get_settings, settings
from sleep_scoring_web.db.models import DiaryEntry, FileAssignment, RawActivityData, UserSettings
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.session import async_session_maker
from sleep_scoring_web.schemas import DateStatus, FileInfo, FileStatus, FileUploadResponse
from sleep_scoring_web.services.file_identity import (
    infer_participant_id_and_timepoint_from_filename,
    is_excluded_activity_filename,
    is_excluded_file_obj,
)
from sleep_scoring_web.services.loaders.csv_loader import CSVLoaderService

router = APIRouter()


# =============================================================================
# Scan Status Tracking (in-memory, per-process)
# =============================================================================


@dataclass
class ScanStatus:
    """Track background scan progress."""

    is_running: bool = False
    total_files: int = 0
    processed: int = 0
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    current_file: str = ""
    imported_files: list[str] = field(default_factory=list)
    error: str | None = None


# Global scan status (simple in-memory tracking)
_scan_status = ScanStatus()


async def get_user_data_settings(db, username: str) -> tuple[int, str | None]:
    """
    Get skip_rows and device_preset from user settings.

    Checks study-wide settings first, then user settings, then global defaults.

    Returns:
        (skip_rows, device_preset)

    """
    # Check study-wide settings first
    study_result = await db.execute(select(UserSettings).where(UserSettings.username == "__study__"))
    study_settings = study_result.scalar_one_or_none()

    result = await db.execute(select(UserSettings).where(UserSettings.username == username))
    user_settings = result.scalar_one_or_none()

    # skip_rows: study > user > global default
    skip_rows = settings.default_skip_rows
    if study_settings and study_settings.skip_rows is not None:
        skip_rows = study_settings.skip_rows
    if user_settings and user_settings.skip_rows is not None:
        skip_rows = user_settings.skip_rows

    # device_preset: study > user > None
    device_preset = None
    if study_settings and study_settings.device_preset is not None:
        device_preset = study_settings.device_preset
    if user_settings and user_settings.device_preset is not None:
        device_preset = user_settings.device_preset

    return skip_rows, device_preset


def get_upload_path() -> Path:
    """Get upload directory path, creating if needed."""
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_data_path() -> Path:
    """Get data directory path."""
    return Path(settings.data_dir)


async def bulk_insert_activity_data(
    db,
    file_id: int,
    activity_df,
) -> int:
    """
    Bulk insert activity data using PostgreSQL COPY for maximum performance.

    For PostgreSQL: Uses COPY protocol via asyncpg (fastest possible)
    For SQLite: Falls back to executemany with raw connection

    Returns the number of rows inserted.
    """
    import io

    if len(activity_df) == 0:
        return 0

    # Prepare DataFrame with required columns
    activity_df = activity_df.reset_index(drop=True)
    activity_df["file_id"] = file_id
    activity_df["epoch_index"] = range(len(activity_df))

    # Ensure columns exist
    for col in ["axis_x", "axis_y", "axis_z", "vector_magnitude"]:
        if col not in activity_df.columns:
            activity_df[col] = None

    # Select and order columns for COPY
    columns = ["file_id", "timestamp", "epoch_index", "axis_x", "axis_y", "axis_z", "vector_magnitude"]
    export_df = activity_df[columns].copy()

    # Convert to appropriate types (float — supports both integer ActiGraph counts and GENEActiv g-force)
    for col in ["axis_x", "axis_y", "axis_z", "vector_magnitude"]:
        export_df[col] = export_df[col].apply(lambda x: float(x) if x is not None and not (isinstance(x, float) and math.isnan(x)) else None)

    # Get raw connection to use COPY
    raw_conn = await db.connection()
    driver_conn = await raw_conn.get_raw_connection()

    if hasattr(driver_conn, "copy_records_to_table"):
        # PostgreSQL with asyncpg - use COPY protocol (FASTEST)
        records = [
            (row.file_id, row.timestamp, row.epoch_index, row.axis_x, row.axis_y, row.axis_z, row.vector_magnitude)
            for row in export_df.itertuples(index=False)
        ]
        await driver_conn.copy_records_to_table(
            "raw_activity_data",
            records=records,
            columns=columns,
        )
    else:
        # SQLite or other - use executemany (still fast)
        from sqlalchemy import text

        insert_sql = text("""
            INSERT INTO raw_activity_data (file_id, timestamp, epoch_index, axis_x, axis_y, axis_z, vector_magnitude)
            VALUES (:file_id, :timestamp, :epoch_index, :axis_x, :axis_y, :axis_z, :vector_magnitude)
        """)
        records = export_df.to_dict("records")

        # Convert pandas Timestamps to Python datetime for SQLite compatibility
        # Must be done after to_dict() since DataFrame reverts to Timestamp
        for record in records:
            ts = record["timestamp"]
            if hasattr(ts, "to_pydatetime"):
                record["timestamp"] = ts.to_pydatetime()

        await db.execute(insert_sql, records)

    return len(activity_df)


async def import_file_from_disk_async(
    file_path: Path,
    db,
    username: str,
) -> FileUploadResponse | None:
    """Import a single file from disk into the database (async version)."""
    filename = file_path.name
    if is_excluded_activity_filename(filename):
        return None

    # Check if file already exists
    result = await db.execute(select(FileModel).where(FileModel.filename == filename))
    existing_file = result.scalar_one_or_none()
    if existing_file:
        return None  # Skip already imported files

    # Create file record
    inferred_pid, _ = infer_participant_id_and_timepoint_from_filename(filename)
    file_record = FileModel(
        filename=filename,
        original_path=str(file_path.absolute()),
        file_type="csv" if filename.lower().endswith(".csv") else "xlsx",
        participant_id=inferred_pid,
        status=FileStatus.PROCESSING,
        uploaded_by=username,
    )
    db.add(file_record)
    await db.commit()
    await db.refresh(file_record)

    # Process file and load activity data
    try:
        user_skip_rows, user_device_preset = await get_user_data_settings(db, username)
        loader = CSVLoaderService(skip_rows=user_skip_rows, device_preset=user_device_preset)
        result = loader.load_file(file_path)

        activity_df = result["activity_data"]
        metadata = result["metadata"]

        # Update file record with metadata
        file_record.row_count = len(activity_df)
        file_record.start_time = metadata.get("start_time")
        file_record.end_time = metadata.get("end_time")
        file_record.metadata_json = {k: str(v) if isinstance(v, datetime) else v for k, v in metadata.items() if k not in ("start_time", "end_time")}
        file_record.status = FileStatus.READY

        # Bulk insert activity data (FAST)
        await bulk_insert_activity_data(db, file_record.id, activity_df)
        await db.commit()

        return FileUploadResponse(
            file_id=file_record.id,
            filename=filename,
            status=FileStatus.READY,
            row_count=file_record.row_count,
            message=f"Imported from disk: {file_path}",
        )

    except Exception:
        logger.exception("Failed to import file from disk: %s", file_path)
        file_record.status = FileStatus.FAILED
        await db.commit()
        return None


async def _async_scan_files(username: str, csv_files: list[Path]) -> None:
    """
    Async file scan implementation.

    This is the actual async work that imports files into the database.
    """
    async with async_session_maker() as db:
        for file_path in csv_files:
            _scan_status.current_file = file_path.name
            if is_excluded_activity_filename(file_path.name):
                _scan_status.skipped += 1
                _scan_status.processed += 1
                continue
            try:
                result = await import_file_from_disk_async(file_path, db, username)
                if result is None:
                    # Check if skipped or failed
                    existing = await db.execute(select(FileModel).where(FileModel.filename == file_path.name))
                    if existing.scalar_one_or_none():
                        _scan_status.skipped += 1
                    else:
                        _scan_status.failed += 1
                else:
                    _scan_status.imported += 1
                    _scan_status.imported_files.append(result.filename)
            except Exception:
                logger.exception("Failed to import file during scan: %s", file_path.name)
                _scan_status.failed += 1

            _scan_status.processed += 1

    _scan_status.is_running = False
    _scan_status.current_file = ""


def _run_background_scan(username: str, csv_files: list[Path]) -> None:
    """
    Run file scan in background thread.

    Uses anyio.from_thread.run to properly execute async code from
    the thread pool where BackgroundTasks runs sync functions.
    """
    import anyio.from_thread

    try:
        anyio.from_thread.run(_async_scan_files, username, csv_files)
    except Exception as e:
        logger.exception("File scan failed: %s", e)
        _scan_status.is_running = False
        _scan_status.error = str(e)


@router.post("/upload")
async def upload_file(
    file: Annotated[UploadFile, File(description="CSV file to upload")],
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    replace: bool = False,
) -> FileUploadResponse:
    """
    Upload a CSV file for processing.

    The file will be parsed, validated, and stored in the database.
    Activity data will be extracted and made available for analysis.

    Set replace=true to re-upload an existing file (deletes old data first).
    """
    logger.info("Upload request: filename=%r, replace=%s, content_type=%s, size=%s", file.filename, replace, file.content_type, file.size)
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Extract basename — browser folder uploads (webkitdirectory) send
    # relative paths like "folder/file.csv" which are safe to strip.
    filename = PurePosixPath(file.filename).name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )
    if is_excluded_activity_filename(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Files with IGNORE or ISSUE in filename are excluded from scoring",
        )

    # Validate file extension
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and Excel files are supported",
        )

    # Enforce file size limit before writing to disk
    if file.size and file.size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB",
        )

    # Check if file already exists
    result = await db.execute(select(FileModel).where(FileModel.filename == filename))
    existing_file = result.scalar_one_or_none()
    if existing_file:
        if replace:
            # Access check: user must have access to the file being replaced
            await require_file_access(db, username, existing_file.id)
            # Delete old file record (cascade deletes activity data, markers, etc.)
            if existing_file.original_path:
                old_path = Path(existing_file.original_path)
                if old_path.exists():
                    old_path.unlink()
            await db.delete(existing_file)
            await db.commit()
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File '{filename}' already exists. Use replace=true to re-upload.",
            )

    # Save file to upload directory
    upload_path = get_upload_path() / filename
    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e}",
        ) from e
    finally:
        await file.close()

    # Create file record
    inferred_pid, _ = infer_participant_id_and_timepoint_from_filename(filename)  # pyright: ignore[reportAssignmentType]
    file_record = FileModel(
        filename=filename,
        original_path=str(upload_path),
        file_type="csv" if filename.lower().endswith(".csv") else "xlsx",
        participant_id=inferred_pid,
        status=FileStatus.PROCESSING,
        uploaded_by=username,
    )
    db.add(file_record)
    await db.commit()
    await db.refresh(file_record)

    # Process file and load activity data
    try:
        user_skip_rows, user_device_preset = await get_user_data_settings(db, username)
        loader = CSVLoaderService(skip_rows=user_skip_rows, device_preset=user_device_preset)
        result = loader.load_file(upload_path)

        activity_df = result["activity_data"]
        metadata = result["metadata"]

        # Update file record with metadata
        file_record.row_count = len(activity_df)
        file_record.start_time = metadata.get("start_time")
        file_record.end_time = metadata.get("end_time")
        file_record.metadata_json = {k: str(v) if isinstance(v, datetime) else v for k, v in metadata.items() if k not in ("start_time", "end_time")}
        file_record.status = FileStatus.READY

        # Bulk insert using COPY (PostgreSQL) or executemany (SQLite)
        await bulk_insert_activity_data(db, file_record.id, activity_df)
        await db.commit()

        return FileUploadResponse(
            file_id=file_record.id,
            filename=filename,
            status=FileStatus.READY,
            row_count=file_record.row_count,
            message="File uploaded and processed successfully",
        )

    except Exception as e:
        # Mark file as failed
        file_record.status = FileStatus.FAILED
        await db.commit()
        logger.exception("Failed to process uploaded file %s: %s", filename, e)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process file: {e}",
        ) from e


@router.post("/upload/api")
async def upload_file_api(
    file: Annotated[UploadFile, File(description="CSV file to upload")],
    db: DbSession,
    _api_key: ApiKey,
    username: str = "pipeline",
) -> FileUploadResponse:
    """
    Upload a CSV file using API key authentication.

    This endpoint is designed for programmatic/pipeline uploads.
    Uses X-Api-Key header for authentication instead of site password.

    The file will be parsed, validated, and stored in the database.
    Activity data will be extracted and made available for analysis.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )

    # Extract basename — browser folder uploads (webkitdirectory) send
    # relative paths like "folder/file.csv" which are safe to strip.
    filename = PurePosixPath(file.filename).name
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
        )
    if is_excluded_activity_filename(filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Files with IGNORE or ISSUE in filename are excluded from scoring",
        )

    # Validate file extension
    if not filename.lower().endswith((".csv", ".xlsx", ".xls")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV and Excel files are supported",
        )

    # Enforce file size limit before writing to disk
    if file.size and file.size > settings.max_upload_size_mb * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.max_upload_size_mb} MB",
        )

    # Check if file already exists
    result = await db.execute(select(FileModel).where(FileModel.filename == filename))
    existing_file = result.scalar_one_or_none()
    if existing_file:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{filename}' already exists",
        )

    # Save file to upload directory
    upload_path = get_upload_path() / filename
    try:
        with upload_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {e}",
        ) from e
    finally:
        await file.close()

    # Create file record
    inferred_pid, _ = infer_participant_id_and_timepoint_from_filename(filename)
    file_record = FileModel(
        filename=filename,
        original_path=str(upload_path),
        file_type="csv" if filename.lower().endswith(".csv") else "xlsx",
        participant_id=inferred_pid,
        status=FileStatus.PROCESSING,
        uploaded_by=username,
    )
    db.add(file_record)
    await db.commit()
    await db.refresh(file_record)

    # Process file and load activity data
    try:
        user_skip_rows, user_device_preset = await get_user_data_settings(db, username)
        loader = CSVLoaderService(skip_rows=user_skip_rows, device_preset=user_device_preset)
        result = loader.load_file(upload_path)

        activity_df = result["activity_data"]
        metadata = result["metadata"]

        # Update file record with metadata
        file_record.row_count = len(activity_df)
        file_record.start_time = metadata.get("start_time")
        file_record.end_time = metadata.get("end_time")
        file_record.metadata_json = {k: str(v) if isinstance(v, datetime) else v for k, v in metadata.items() if k not in ("start_time", "end_time")}
        file_record.status = FileStatus.READY

        # Bulk insert using COPY (PostgreSQL) or executemany (SQLite)
        await bulk_insert_activity_data(db, file_record.id, activity_df)
        await db.commit()

        return FileUploadResponse(
            file_id=file_record.id,
            filename=filename,
            status=FileStatus.READY,
            row_count=file_record.row_count,
            message="File uploaded and processed successfully via API key",
        )

    except Exception as e:
        # Mark file as failed
        file_record.status = FileStatus.FAILED
        await db.commit()
        logger.exception("Failed to process uploaded file (API) %s: %s", filename, e)

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to process file: {e}",
        ) from e


@router.get("")
async def list_files(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """List uploaded files. Users with assignments see only their files (even admins)."""
    # Check if user has any assignments — assignments always take priority
    assignment_result = await db.execute(select(FileAssignment.file_id).where(FileAssignment.username == username))
    assigned_ids = list(assignment_result.scalars().all())
    is_admin = is_admin_user(username)

    # Security: unassigned non-admin users must not see any file names/metadata.
    if not assigned_ids and not is_admin:
        return {"items": [], "total": 0}

    if assigned_ids:
        # User has assignments → show only assigned files (admin or not)
        result = await db.execute(select(FileModel).where(FileModel.id.in_(assigned_ids)).order_by(FileModel.uploaded_at.desc()))
        files = result.scalars().all()
    else:
        # No assignments → show all files
        result = await db.execute(select(FileModel).order_by(FileModel.uploaded_at.desc()))
        files = result.scalars().all()

    files = [f for f in files if not is_excluded_file_obj(f)]

    items = [
        FileInfo(
            id=f.id,
            filename=f.filename,
            original_path=f.original_path,
            file_type=f.file_type,
            participant_id=f.participant_id,
            status=FileStatus(f.status),
            row_count=f.row_count,
            start_time=f.start_time,
            end_time=f.end_time,
            uploaded_by=f.uploaded_by,
            uploaded_at=f.uploaded_at,
        )
        for f in files
    ]

    return {"items": items, "total": len(items)}


# =============================================================================
# Auth info (MUST be before /{file_id} to avoid route shadowing)
# =============================================================================


def _require_admin(username: str) -> None:
    """Raise 403 if user is not an admin."""
    app_settings = get_settings()
    if username.lower() not in app_settings.admin_usernames_list:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")


def _excluded_filename_sql_filter():
    lowered = func.lower(FileModel.filename)
    return or_(lowered.like("%ignore%"), lowered.like("%issue%"))


@router.get("/auth/me")
async def get_me(
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """Return current user info including admin status."""
    app_settings = get_settings()
    is_admin = username.lower() in app_settings.admin_usernames_list
    return {"username": username, "is_admin": is_admin}


# =============================================================================
# File Assignment CRUD (admin only, MUST be before /{file_id})
# =============================================================================


@router.get("/assignments")
async def list_assignments(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> list[dict]:
    """List all file assignments (admin only)."""
    _require_admin(username)
    result = await db.execute(
        select(FileAssignment, FileModel.filename)
        .join(FileModel, FileAssignment.file_id == FileModel.id)
        .where(~_excluded_filename_sql_filter())
        .order_by(FileAssignment.username, FileModel.filename)
    )
    return [
        {
            "id": fa.id,
            "file_id": fa.file_id,
            "filename": filename,
            "username": fa.username,
            "assigned_by": fa.assigned_by,
            "assigned_at": str(fa.assigned_at) if fa.assigned_at else None,
        }
        for fa, filename in result.all()
    ]


@router.post("/assignments")
async def create_assignments(
    request: dict,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """Assign files to a user (admin only). Body: {"file_ids": [...], "username": "..."}."""
    _require_admin(username)
    file_ids = request.get("file_ids", [])
    target_username = request.get("username", "")
    if not file_ids or not target_username:
        raise HTTPException(status_code=400, detail="file_ids and username are required")

    # Validate that all file_ids exist
    existing_result = await db.execute(
        select(FileModel.id).where(
            FileModel.id.in_(file_ids),
            ~_excluded_filename_sql_filter(),
        )
    )
    found_ids = set(existing_result.scalars().all())
    missing = set(file_ids) - found_ids
    if missing:
        raise HTTPException(status_code=404, detail=f"Files not found: {sorted(missing)}")

    created = 0
    for fid in file_ids:
        # Check if assignment already exists
        existing = await db.execute(
            select(FileAssignment).where(
                FileAssignment.file_id == fid,
                FileAssignment.username == target_username,
            )
        )
        if existing.scalar_one_or_none():
            continue
        db.add(
            FileAssignment(
                file_id=fid,
                username=target_username,
                assigned_by=username,
            )
        )
        created += 1

    await db.commit()
    return {"created": created, "total_requested": len(file_ids)}


@router.delete("/assignments/{target_username}")
async def delete_user_assignments(
    target_username: str,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """Remove all assignments for a user (admin only)."""
    from sqlalchemy import delete as sa_delete

    _require_admin(username)
    result = await db.execute(sa_delete(FileAssignment).where(FileAssignment.username == target_username))
    await db.commit()
    return {"deleted": result.rowcount}


@router.get("/assignments/progress")
async def get_assignment_progress(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> list[dict]:
    """
    Get all assignments with per-user, per-file scoring progress (admin only).

    For each user, returns their assigned files with total_dates and scored_dates.
    Uses the markers table (created_by) for scored dates and raw_activity_data for
    total dates per file. Diary-intersected dates are used when diary exists.
    """
    from collections import defaultdict

    from sleep_scoring_web.db.models import Marker

    _require_admin(username)

    # 1. Get all assignments
    result = await db.execute(
        select(FileAssignment.file_id, FileAssignment.username, FileAssignment.assigned_at, FileModel.filename)
        .join(FileModel, FileAssignment.file_id == FileModel.id)
        .where(~_excluded_filename_sql_filter())
        .order_by(FileAssignment.username, FileModel.filename)
    )
    assignments = result.all()
    if not assignments:
        return []

    # Collect all assigned file IDs
    all_file_ids = list({a.file_id for a in assignments})

    # 2. Get total dates per file (distinct analysis_date from raw_activity_data)
    date_col = func.date(RawActivityData.timestamp).label("d")
    dates_result = await db.execute(
        select(RawActivityData.file_id, func.count(date_col.distinct()))
        .where(RawActivityData.file_id.in_(all_file_ids))
        .group_by(RawActivityData.file_id)
    )
    total_dates_by_file: dict[int, int] = {row[0]: row[1] for row in dates_result.all()}

    # 3. Refine with diary dates where available
    diary_result = await db.execute(
        select(DiaryEntry.file_id, func.count(DiaryEntry.analysis_date.distinct()))
        .where(DiaryEntry.file_id.in_(all_file_ids))
        .group_by(DiaryEntry.file_id)
    )
    diary_dates_by_file: dict[int, int] = {row[0]: row[1] for row in diary_result.all()}
    # If diary exists for a file, use diary date count (study period) instead of all activity dates
    for fid, diary_count in diary_dates_by_file.items():
        total_dates_by_file[fid] = diary_count

    # 4. Get scored dates per (user, file) — distinct dates where user has markers
    scored_result = await db.execute(
        select(
            Marker.created_by,
            Marker.file_id,
            func.count(Marker.analysis_date.distinct()),
        )
        .where(Marker.file_id.in_(all_file_ids))
        .group_by(Marker.created_by, Marker.file_id)
    )
    scored_dates: dict[tuple[str, int], int] = {}
    for created_by, file_id, count in scored_result.all():
        scored_dates[(created_by or "", file_id)] = count

    # 5. Build response grouped by username
    users: dict[str, dict] = {}
    for a in assignments:
        if a.username not in users:
            users[a.username] = {
                "username": a.username,
                "files": [],
                "total_files": 0,
                "total_dates": 0,
                "scored_dates": 0,
            }
        user = users[a.username]
        file_total = total_dates_by_file.get(a.file_id, 0)
        file_scored = scored_dates.get((a.username, a.file_id), 0)
        user["files"].append(
            {
                "file_id": a.file_id,
                "filename": a.filename,
                "total_dates": file_total,
                "scored_dates": file_scored,
                "assigned_at": str(a.assigned_at) if a.assigned_at else None,
            }
        )
        user["total_files"] += 1
        user["total_dates"] += file_total
        user["scored_dates"] += file_scored

    return list(users.values())


@router.get("/assignments/unassigned")
async def get_unassigned_files(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> list[dict]:
    """Get files with zero assignments (admin only)."""
    _require_admin(username)

    result = await db.execute(
        select(FileModel.id, FileModel.filename, FileModel.participant_id, FileModel.status)
        .outerjoin(FileAssignment, FileModel.id == FileAssignment.file_id)
        .where(FileAssignment.id.is_(None))
        .where(~_excluded_filename_sql_filter())
        .where(FileModel.status == FileStatus.READY)
        .order_by(FileModel.filename)
    )
    return [{"id": row[0], "filename": row[1], "participant_id": row[2], "status": row[3]} for row in result.all()]


@router.post("/purge-excluded")
async def purge_excluded_files(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    delete_disk_files: bool = True,
) -> dict:
    """Delete all files whose names contain IGNORE or ISSUE."""
    _require_admin(username)

    result = await db.execute(select(FileModel).where(_excluded_filename_sql_filter()).order_by(FileModel.id))
    files = result.scalars().all()

    deleted_filenames: list[str] = []
    for file in files:
        if delete_disk_files and file.original_path:
            upload_path = Path(file.original_path)
            try:
                if upload_path.exists():
                    upload_path.unlink()
            except Exception:
                logger.exception("Failed deleting excluded file from disk: %s", upload_path)
        deleted_filenames.append(file.filename)
        await db.delete(file)

    await db.commit()
    return {
        "deleted_count": len(deleted_filenames),
        "deleted_filenames": deleted_filenames,
    }


@router.get("/{file_id}")
async def get_file(
    file_id: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> FileInfo:
    """Get file metadata by ID."""
    await require_file_access(db, username, file_id)

    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = result.scalar_one_or_none()

    if not file or is_excluded_file_obj(file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    return FileInfo(
        id=file.id,
        filename=file.filename,
        original_path=file.original_path,
        file_type=file.file_type,
        participant_id=file.participant_id,
        status=FileStatus(file.status),
        row_count=file.row_count,
        start_time=file.start_time,
        end_time=file.end_time,
        uploaded_by=file.uploaded_by,
        uploaded_at=file.uploaded_at,
    )


@router.post("/backfill-participant-ids")
async def backfill_participant_ids(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """
    Infer and persist missing File.participant_id values from filenames.

    Useful for older datasets imported before participant_id inference existed.
    """
    _require_admin(username)

    result = await db.execute(select(FileModel))
    files = result.scalars().all()

    updated = 0
    eligible_total = 0
    for f in files:
        if is_excluded_file_obj(f):
            continue
        eligible_total += 1
        if f.participant_id:
            continue
        inferred_pid, _ = infer_participant_id_and_timepoint_from_filename(f.filename)  # pyright: ignore[reportAssignmentType]
        if inferred_pid:
            f.participant_id = inferred_pid
            updated += 1

    await db.commit()
    return {"updated": updated, "total_files": eligible_total}


@router.get("/{file_id}/dates")
async def get_file_dates(
    file_id: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> list[str]:
    """Get available dates for a file. If diary exists, only return study-period dates."""
    await require_file_access(db, username, file_id)

    # Verify file exists
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = result.scalar_one_or_none()

    if not file or is_excluded_file_obj(file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Get distinct dates from activity data
    date_col = func.date(RawActivityData.timestamp).label("date")
    result = await db.execute(select(date_col).where(RawActivityData.file_id == file_id).group_by(date_col).order_by(date_col))
    all_dates = [str(d) for d in result.scalars().all()]

    # Check if diary entries exist for this file
    diary_result = await db.execute(select(DiaryEntry.analysis_date).where(DiaryEntry.file_id == file_id))
    diary_dates = {str(d) for d in diary_result.scalars().all()}

    if diary_dates:
        # Diary defines study period — only return dates that have diary entries
        return [d for d in all_dates if d in diary_dates]

    # No diary uploaded yet — return all activity dates as fallback
    return all_dates


@router.get("/{file_id}/dates/status")
async def get_file_dates_status(
    file_id: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> Response:
    """Get dates with per-user annotation status, auto-score availability, and complexity."""
    from sleep_scoring_web.db.models import NightComplexity, UserAnnotation

    from sleep_scoring_web.api.access import is_admin_user
    from sqlalchemy import text

    # Single raw SQL query: file access check + dates + annotations + complexity
    # Folds file existence + access check + 5 data queries into a single DB round-trip.
    # Returns empty result set when file doesn't exist or user lacks access.
    raw_sql = text("""
        WITH file_check AS (
            SELECT id, filename FROM files WHERE id = :file_id
        ),
        access_check AS (
            SELECT 1 AS ok WHERE (
                :is_admin = true
                OR EXISTS(SELECT 1 FROM file_assignments WHERE file_id = :file_id AND username = :username)
            )
        ),
        activity_dates AS (
            SELECT DISTINCT date(timestamp) AS d
            FROM raw_activity_data
            WHERE file_id = :file_id
              AND EXISTS(SELECT 1 FROM file_check)
              AND EXISTS(SELECT 1 FROM access_check)
        ),
        diary_dates AS (
            SELECT analysis_date AS d FROM diary_entries WHERE file_id = :file_id
        ),
        has_diary AS (
            SELECT EXISTS(SELECT 1 FROM diary_dates) AS val
        ),
        filtered_dates AS (
            SELECT ad.d
            FROM activity_dates ad, has_diary hd
            WHERE hd.val = false OR ad.d IN (SELECT d FROM diary_dates)
        )
        SELECT
            fd.d::text AS date,
            COALESCE(ua.is_no_sleep, false) AS is_no_sleep,
            COALESCE(ua.needs_consensus, false) AS needs_consensus,
            COALESCE(ua.is_no_sleep, false)
                OR (ua.sleep_markers_json IS NOT NULL AND ua.sleep_markers_json::text NOT IN ('[]', 'null'))
                OR (ua.nonwear_markers_json IS NOT NULL AND ua.nonwear_markers_json::text NOT IN ('[]', 'null'))
                AS has_markers,
            auto_ua.sleep_markers_json IS NOT NULL
                AND auto_ua.sleep_markers_json::text NOT IN ('[]', 'null')
                AS has_auto_score,
            nc.complexity_pre,
            nc.complexity_post
        FROM filtered_dates fd
        LEFT JOIN user_annotations ua
            ON ua.file_id = :file_id AND ua.analysis_date = fd.d AND ua.username = :username
        LEFT JOIN user_annotations auto_ua
            ON auto_ua.file_id = :file_id AND auto_ua.analysis_date = fd.d AND auto_ua.username = 'auto_score'
        LEFT JOIN night_complexity nc
            ON nc.file_id = :file_id AND nc.analysis_date = fd.d
        ORDER BY fd.d
    """)

    result = await db.execute(raw_sql, {
        "file_id": file_id,
        "username": username,
        "is_admin": is_admin_user(username),
    })
    rows = result.fetchall()

    # If no rows returned, check whether the file exists or user lacks access
    if not rows:
        file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
        file = file_result.scalar_one_or_none()
        if not file or is_excluded_file_obj(file):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        if not is_admin_user(username):
            from sleep_scoring_web.db.models import FileAssignment as FA
            access_result = await db.execute(select(FA.id).where(FA.file_id == file_id, FA.username == username))
            if access_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
        # File exists and is accessible but has no activity data — return empty list

    # Check if any dates are missing complexity — auto-compute if needed
    missing_complexity_dates = [row.date for row in rows if row.complexity_pre is None]
    if missing_complexity_dates:
        try:
            missing_date_objs = [datetime.strptime(d, "%Y-%m-%d").date() for d in missing_complexity_dates]
            await _compute_complexity_for_file(file_id, missing_date_objs)
            # Re-fetch after computing
            result = await db.execute(raw_sql, {"file_id": file_id, "username": username, "is_admin": is_admin_user(username)})
            rows = result.fetchall()
        except Exception:
            logger.exception(
                "Failed auto-computing missing complexity rows for file %d (%d missing dates)",
                file_id,
                len(missing_complexity_dates),
            )

    import json as _json

    payload = [
        {
            "date": row.date,
            "has_markers": bool(row.has_markers),
            "is_no_sleep": bool(row.is_no_sleep),
            "needs_consensus": bool(row.needs_consensus),
            "has_auto_score": bool(row.has_auto_score),
            "complexity_pre": float(row.complexity_pre) if row.complexity_pre is not None else None,
            "complexity_post": float(row.complexity_post) if row.complexity_post is not None else None,
        }
        for row in rows
    ]
    return Response(
        content=_json.dumps(payload),
        media_type="application/json",
    )


@router.post("/{file_id}/compute-complexity")
async def compute_complexity(
    file_id: int,
    background_tasks: BackgroundTasks,
    db: DbSession,
    _: VerifiedPassword,
) -> dict:
    """
    Trigger batch complexity computation for all dates in a file.

    Runs in background: loads activity data, runs Sadeh + Choi, loads diary,
    computes complexity_pre for each date, and upserts into NightComplexity table.
    """
    # Verify file exists
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = result.scalar_one_or_none()
    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Get all dates
    date_col = func.date(RawActivityData.timestamp).label("date")
    result = await db.execute(select(date_col).where(RawActivityData.file_id == file_id).group_by(date_col).order_by(date_col))
    dates = list(result.scalars().all())

    background_tasks.add_task(_compute_complexity_for_file, file_id, dates)

    return {"message": f"Computing complexity for {len(dates)} dates", "date_count": len(dates)}


@router.get("/{file_id}/{analysis_date}/complexity")
async def get_complexity_detail(
    file_id: int,
    analysis_date: str,
    db: DbSession,
    _: VerifiedPassword,
) -> dict:
    """Get full complexity feature breakdown for a file/date."""
    from sleep_scoring_web.db.models import NightComplexity

    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file_obj = file_result.scalar_one_or_none()
    if not file_obj or is_excluded_file_obj(file_obj):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    date_obj = datetime.strptime(analysis_date, "%Y-%m-%d").date()
    result = await db.execute(
        select(NightComplexity).where(
            NightComplexity.file_id == file_id,
            NightComplexity.analysis_date == date_obj,
        )
    )
    complexity = result.scalar_one_or_none()

    if not complexity:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complexity not computed for this date")

    return {
        "complexity_pre": complexity.complexity_pre,
        "complexity_post": complexity.complexity_post,
        "features": complexity.features_json or {},
        "computed_at": str(complexity.computed_at) if complexity.computed_at else None,
    }


async def _compute_complexity_for_file(file_id: int, dates: list) -> None:
    """Background task: compute complexity_pre for all dates in a file."""
    import logging

    from sqlalchemy import and_

    from sleep_scoring_web.db.models import DiaryEntry, Marker, NightComplexity
    from sleep_scoring_web.db.session import async_session_maker
    from sleep_scoring_web.schemas.enums import MarkerCategory
    from sleep_scoring_web.services.algorithms import ChoiAlgorithm, SadehAlgorithm
    from sleep_scoring_web.services.complexity import compute_pre_complexity

    logger = logging.getLogger(__name__)

    from sleep_scoring_web.utils import naive_to_unix

    async with async_session_maker() as db:
        for analysis_date in dates:
            try:
                # Load activity data (noon-to-noon window)
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
                    continue

                timestamps = [naive_to_unix(r.timestamp) for r in rows]
                axis_y = [r.axis_y or 0 for r in rows]

                # Run algorithms
                sadeh = SadehAlgorithm()
                sleep_scores = sadeh.score(axis_y)
                choi = ChoiAlgorithm()
                choi_nonwear = choi.detect_mask(axis_y)

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
                if timestamps:
                    data_min_ts = timestamps[0]
                    data_max_ts = timestamps[-1]
                    sensor_nw_result = await db.execute(
                        select(Marker).where(
                            and_(
                                Marker.file_id == file_id,
                                Marker.sensor_nonwear_filter(),
                                Marker.start_timestamp <= data_max_ts,
                                Marker.end_timestamp >= data_min_ts,
                            )
                        )
                    )
                    for nw in sensor_nw_result.scalars().all():
                        if nw.start_timestamp is not None and nw.end_timestamp is not None:
                            sensor_nonwear_periods.append((nw.start_timestamp, nw.end_timestamp))

                score, features = compute_pre_complexity(
                    timestamps=timestamps,
                    activity_counts=[float(x) for x in axis_y],
                    sleep_scores=sleep_scores,
                    choi_nonwear=choi_nonwear,
                    diary_onset_time=diary_onset,
                    diary_wake_time=diary_wake,
                    diary_nap_count=nap_count,
                    analysis_date=str(analysis_date),
                    sensor_nonwear_periods=sensor_nonwear_periods,
                    diary_nonwear_times=diary_nonwear_times,
                )

                # Compute post-complexity if sleep markers exist
                post_score = 0
                sleep_marker_result = await db.execute(
                    select(Marker).where(
                        and_(
                            Marker.file_id == file_id,
                            Marker.analysis_date == analysis_date,
                            Marker.marker_category == MarkerCategory.SLEEP,
                        )
                    )
                )
                sleep_markers_db = sleep_marker_result.scalars().all()
                marker_pairs = [
                    (m.start_timestamp, m.end_timestamp) for m in sleep_markers_db if m.start_timestamp is not None and m.end_timestamp is not None
                ]
                if marker_pairs:
                    from sleep_scoring_web.services.complexity import compute_post_complexity

                    post_score, features = compute_post_complexity(
                        complexity_pre=score,
                        features=features,
                        sleep_markers=marker_pairs,
                        sleep_scores=sleep_scores,
                        timestamps=timestamps,
                    )

                # Upsert
                existing = await db.execute(
                    select(NightComplexity).where(
                        and_(
                            NightComplexity.file_id == file_id,
                            NightComplexity.analysis_date == analysis_date,
                        )
                    )
                )
                row = existing.scalar_one_or_none()
                if row:
                    row.complexity_pre = score
                    row.complexity_post = post_score
                    row.features_json = features
                else:
                    row = NightComplexity(
                        file_id=file_id,
                        analysis_date=analysis_date,
                        complexity_pre=score,
                        complexity_post=post_score,
                        features_json=features,
                    )
                    db.add(row)

                await db.commit()
            except Exception:
                logger.exception("Failed to compute complexity for file %d date %s", file_id, analysis_date)
                await db.rollback()


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_file(
    file_id: int,
    db: DbSession,
    _: VerifiedPassword,
):
    """Delete a file and its associated data."""
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = result.scalar_one_or_none()

    if not file or is_excluded_file_obj(file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Delete the file from disk
    if file.original_path:
        upload_path = Path(file.original_path)
        if upload_path.exists():
            upload_path.unlink()

    # Delete from database (cascade will handle related records)
    await db.delete(file)
    await db.commit()


@router.delete("", status_code=status.HTTP_200_OK)
async def delete_all_files(
    db: DbSession,
    _: VerifiedPassword,
    status_filter: str | None = None,
) -> dict:
    """
    Delete all files from the database.

    Optionally filter by status (e.g., 'failed' to delete only failed files).
    """
    # Build query
    query = select(FileModel)
    if status_filter:
        query = query.where(FileModel.status == status_filter)

    result = await db.execute(query)
    files = result.scalars().all()

    deleted_count = 0
    for file in files:
        # Delete the file from disk if it exists
        if file.original_path:
            upload_path = Path(file.original_path)
            if upload_path.exists():
                upload_path.unlink()

        await db.delete(file)
        deleted_count += 1

    await db.commit()

    return {
        "message": f"Deleted {deleted_count} files",
        "deleted_count": deleted_count,
    }


@router.post("/scan")
async def scan_data_directory(
    background_tasks: BackgroundTasks,
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """
    Start a background scan of the data directory for CSV files.

    Files already in the database are skipped.
    Returns immediately with scan status - poll GET /scan/status for progress.
    """
    # Check if scan is already running
    if _scan_status.is_running:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A scan is already in progress. Check GET /api/v1/files/scan/status",
        )

    data_path = get_data_path()
    if not data_path.exists():
        return {
            "message": f"Data directory '{data_path}' does not exist",
            "started": False,
            "total_files": 0,
        }

    # Find all CSV files
    csv_files = list(data_path.glob("*.csv")) + list(data_path.glob("*.CSV"))
    csv_files = [path for path in csv_files if not is_excluded_activity_filename(path.name)]

    if not csv_files:
        return {
            "message": "No CSV files found in data directory",
            "started": False,
            "total_files": 0,
        }

    # Reset scan status
    _scan_status.is_running = True
    _scan_status.total_files = len(csv_files)
    _scan_status.processed = 0
    _scan_status.imported = 0
    _scan_status.skipped = 0
    _scan_status.failed = 0
    _scan_status.current_file = ""
    _scan_status.imported_files = []
    _scan_status.error = None

    # Start background task
    background_tasks.add_task(_run_background_scan, username, csv_files)

    return {
        "message": f"Background scan started for {len(csv_files)} files",
        "started": True,
        "total_files": len(csv_files),
        "status_url": "/api/v1/files/scan/status",
    }


@router.get("/scan/status")
async def get_scan_status(
    _: VerifiedPassword,
) -> dict:
    """
    Get the current status of the background file scan.

    Poll this endpoint to track import progress.
    """
    return {
        "is_running": _scan_status.is_running,
        "total_files": _scan_status.total_files,
        "processed": _scan_status.processed,
        "imported": _scan_status.imported,
        "skipped": _scan_status.skipped,
        "failed": _scan_status.failed,
        "current_file": _scan_status.current_file,
        "progress_percent": (round(_scan_status.processed / _scan_status.total_files * 100, 1) if _scan_status.total_files > 0 else 0),
        "imported_files": _scan_status.imported_files[-10:],  # Last 10 imported
        "error": _scan_status.error,
    }


@router.get("/watcher/status")
async def get_watcher_status(
    _: VerifiedPassword,
) -> dict:
    """
    Get the current status of the automatic file watcher.

    The file watcher monitors the data directory for new CSV files
    and automatically ingests them into the database.
    """
    from sleep_scoring_web.services.file_watcher import get_watcher_status as get_status

    return get_status()


@router.delete("/{file_id}/assignments/{target_username}")
async def delete_file_assignment(
    file_id: int,
    target_username: str,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> dict:
    """Remove a single file assignment (admin only)."""
    from sqlalchemy import delete as sa_delete

    _require_admin(username)
    result = await db.execute(
        sa_delete(FileAssignment).where(
            FileAssignment.file_id == file_id,
            FileAssignment.username == target_username,
        )
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return {"deleted": 1}
