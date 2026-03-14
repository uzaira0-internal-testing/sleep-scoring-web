"""Diary API endpoints for importing and retrieving sleep diary data."""

import logging
from datetime import date, datetime
from io import StringIO
from typing import Any

logger = logging.getLogger(__name__)

import polars as pl
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, select

from sleep_scoring_web.api.access import get_accessible_files, require_file_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.db.models import DiaryEntry
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.services.file_identity import (
    build_file_identity,
    filename_stem,
    is_excluded_file_obj,
    normalize_filename,
    normalize_participant_id,
    normalize_timepoint,
)
from sleep_scoring_web.services.redcap_diary_converter import (
    convert_redcap_wide_to_long,
    is_redcap_wide_format,
)

router = APIRouter(prefix="/diary", tags=["diary"])

# Desktop column name → web DB field mapping.
# Each web field maps to a list of possible CSV column names (tried in order).
_DESKTOP_COLUMN_ALIASES: dict[str, list[str]] = {
    "bed_time": ["in_bed_time", "bedtime", "in_bed_time_auto", "inbed_time", "bed_time", "time_to_bed"],
    "wake_time": ["sleep_offset_time", "sleep_offset_time_auto", "wake_time", "waketime", "time_woke"],
    "lights_out": ["sleep_onset_time", "sleep_onset_time_auto", "asleep_time", "lights_out", "lightsout"],
    "got_up": ["got_up", "gotup", "out_of_bed"],
    "sleep_quality": ["sleep_quality", "quality"],
    "time_to_fall_asleep_minutes": ["time_to_fall_asleep", "sol", "sleep_latency"],
    "number_of_awakenings": ["awakenings", "number_of_awakenings", "waso_count"],
    "notes": ["notes", "comments"],
    # Nap periods
    "nap_1_start": ["napstart_1_time", "nap_onset_time", "nap_onset_time_auto", "nap_1_start", "nap1_start"],
    "nap_1_end": ["napend_1_time", "nap_offset_time", "nap_offset_time_auto", "nap_1_end", "nap1_end"],
    "nap_2_start": ["nap_onset_time_2", "nap_2_start", "nap2_start"],
    "nap_2_end": ["nap_offset_time_2", "nap_2_end", "nap2_end"],
    "nap_3_start": ["nap_onset_time_3", "nap_3_start", "nap3_start"],
    "nap_3_end": ["nap_offset_time_3", "nap_3_end", "nap3_end"],
    # Nonwear periods
    "nonwear_1_start": ["nonwear_start_time", "nonwear_1_start", "nw_1_start"],
    "nonwear_1_end": ["nonwear_end_time", "nonwear_1_end", "nw_1_end"],
    "nonwear_1_reason": ["nonwear_reason", "nonwear_1_reason", "nw_1_reason"],
    "nonwear_2_start": ["nonwear_start_time_2", "nonwear_2_start", "nw_2_start"],
    "nonwear_2_end": ["nonwear_end_time_2", "nonwear_2_end", "nw_2_end"],
    "nonwear_2_reason": ["nonwear_reason_2", "nonwear_2_reason", "nw_2_reason"],
    "nonwear_3_start": ["nonwear_start_time_3", "nonwear_3_start", "nw_3_start"],
    "nonwear_3_end": ["nonwear_end_time_3", "nonwear_3_end", "nw_3_end"],
    "nonwear_3_reason": ["nonwear_reason_3", "nonwear_3_reason", "nw_3_reason"],
}

# Nonwear reason code → text mapping (matches desktop)
_NONWEAR_REASON_CODES: dict[str, str] = {
    "1": "Bath/Shower",
    "1.0": "Bath/Shower",
    "2": "Swimming",
    "2.0": "Swimming",
    "3": "Other",
    "3.0": "Other",
}


# =============================================================================
# Pydantic Models
# =============================================================================


class DiaryEntryResponse(BaseModel):
    """Response model for a single diary entry."""

    id: int
    file_id: int
    analysis_date: date
    bed_time: str | None = None
    wake_time: str | None = None
    lights_out: str | None = None
    got_up: str | None = None
    sleep_quality: int | None = None
    time_to_fall_asleep_minutes: int | None = None
    number_of_awakenings: int | None = None
    notes: str | None = None
    # Nap periods
    nap_1_start: str | None = None
    nap_1_end: str | None = None
    nap_2_start: str | None = None
    nap_2_end: str | None = None
    nap_3_start: str | None = None
    nap_3_end: str | None = None
    # Nonwear periods
    nonwear_1_start: str | None = None
    nonwear_1_end: str | None = None
    nonwear_1_reason: str | None = None
    nonwear_2_start: str | None = None
    nonwear_2_end: str | None = None
    nonwear_2_reason: str | None = None
    nonwear_3_start: str | None = None
    nonwear_3_end: str | None = None
    nonwear_3_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DiaryEntryCreate(BaseModel):
    """Request model for creating/updating a diary entry."""

    bed_time: str | None = None
    wake_time: str | None = None
    lights_out: str | None = None
    got_up: str | None = None
    sleep_quality: int | None = None
    time_to_fall_asleep_minutes: int | None = None
    number_of_awakenings: int | None = None
    notes: str | None = None
    # Nap periods
    nap_1_start: str | None = None
    nap_1_end: str | None = None
    nap_2_start: str | None = None
    nap_2_end: str | None = None
    nap_3_start: str | None = None
    nap_3_end: str | None = None
    # Nonwear periods
    nonwear_1_start: str | None = None
    nonwear_1_end: str | None = None
    nonwear_1_reason: str | None = None
    nonwear_2_start: str | None = None
    nonwear_2_end: str | None = None
    nonwear_2_reason: str | None = None
    nonwear_3_start: str | None = None
    nonwear_3_end: str | None = None
    nonwear_3_reason: str | None = None


class DiaryUploadResponse(BaseModel):
    """Response after uploading diary CSV."""

    entries_imported: int
    entries_skipped: int
    errors: list[str]
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_identifiers: list[str] = Field(default_factory=list)
    ambiguous_identifiers: list[str] = Field(default_factory=list)


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("/{file_id}")
async def list_diary_entries(
    file_id: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> list[DiaryEntryResponse]:
    """Get all diary entries for a file, ordered by date."""
    await require_file_access(db, username, file_id)

    result = await db.execute(
        select(DiaryEntry)
        .where(DiaryEntry.file_id == file_id)
        .order_by(DiaryEntry.analysis_date)
    )
    entries = result.scalars().all()
    return [DiaryEntryResponse.model_validate(e) for e in entries]


@router.get("/{file_id}/{analysis_date}", response_model=DiaryEntryResponse | None)
async def get_diary_entry(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> DiaryEntryResponse | None:
    """
    Get diary entry for a specific file and date.

    Returns None if no diary entry exists for the given file/date.
    """
    await require_file_access(db, username, file_id)

    result = await db.execute(
        select(DiaryEntry).where(
            and_(
                DiaryEntry.file_id == file_id,
                DiaryEntry.analysis_date == analysis_date,
            )
        )
    )
    entry = result.scalar_one_or_none()

    if entry is None:
        return None

    return DiaryEntryResponse.model_validate(entry)


@router.put("/{file_id}/{analysis_date}")
async def update_diary_entry(
    file_id: int,
    analysis_date: date,
    entry_data: DiaryEntryCreate,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> DiaryEntryResponse:
    """Create or update a diary entry for a specific file and date."""
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()
    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Check for existing entry
    result = await db.execute(
        select(DiaryEntry).where(
            and_(
                DiaryEntry.file_id == file_id,
                DiaryEntry.analysis_date == analysis_date,
            )
        )
    )
    entry = result.scalar_one_or_none()

    if entry:
        # Update existing
        for field, value in entry_data.model_dump(exclude_unset=True).items():
            setattr(entry, field, value)
    else:
        # Create new
        entry = DiaryEntry(
            file_id=file_id,
            analysis_date=analysis_date,
            imported_by=username,
            **entry_data.model_dump(),
        )
        db.add(entry)

    await db.commit()
    await db.refresh(entry)

    return DiaryEntryResponse.model_validate(entry)


@router.delete("/{file_id}/{analysis_date}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_diary_entry(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> None:
    """Delete a diary entry."""
    await require_file_access(db, username, file_id)

    result = await db.execute(
        select(DiaryEntry).where(
            and_(
                DiaryEntry.file_id == file_id,
                DiaryEntry.analysis_date == analysis_date,
            )
        )
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Diary entry not found")

    await db.delete(entry)
    await db.commit()


@router.post("/upload")
async def upload_diary_csv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> DiaryUploadResponse:
    """
    Upload a diary CSV file (study-wide).

    Matching priority:
    1) filename column (exact/stem)
    2) participant_id + optional timepoint
    3) unique filename token fallback

    Ambiguous matches are skipped and reported (never guessed).
    """
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            text = content.decode("cp1252")

    try:
        df = pl.read_csv(StringIO(text))
    except Exception as e:
        logger.exception("Failed to parse diary CSV: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {e}",
        ) from e

    # Auto-detect REDCap wide format and pivot to long before normal processing
    if is_redcap_wide_format(df.columns):
        df = convert_redcap_wide_to_long(df)

    df = df.rename({col: col.lower().strip().replace(" ", "_") for col in df.columns})

    date_col = None
    for col in ["startdate", "date", "analysis_date", "diary_date", "date_of_last_night"]:
        if col in df.columns:
            date_col = col
            break
    if date_col is None:
        first_cols = df.columns[:20]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have a date column (startdate, date, analysis_date, or diary_date). First 20 columns: {first_cols}",
        )

    diary_filename_col = None
    for col in ["filename", "file", "file_name"]:
        if col in df.columns:
            diary_filename_col = col
            break

    pid_col = None
    filename_pid: str | None = None
    for col in ["participant_id", "participantid", "pid", "subject_id", "id"]:
        if col in df.columns:
            pid_col = col
            break

    timepoint_col = None
    for col in ["participant_timepoint", "timepoint", "tp"]:
        if col in df.columns:
            timepoint_col = col
            break

    if pid_col is None and diary_filename_col is None:
        filename_pid = filename_stem(file.filename)
        if not filename_pid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="CSV must include participant_id or filename, or upload filename must identify participant",
            )

    all_files = await get_accessible_files(db, username)
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
                pid_tp_to_identities.setdefault(
                    (ident.participant_id_norm, ident.timepoint_norm), []
                ).append(ident)

    entries_imported = 0
    entries_skipped = 0
    matched_rows = 0
    total_rows = int(df.height)
    unmatched_identifiers: set[str] = set()
    ambiguous_identifiers: set[str] = set()
    errors: list[str] = []
    affected_file_ids: set[int] = set()

    for row in df.iter_rows(named=True):
        try:
            matched_files: list[FileModel] = []

            # Parse date early so it can be used for date-range matching
            date_str = str(row[date_col])
            analysis_date = _parse_date(date_str)
            if analysis_date is None:
                errors.append(f"Invalid date: {date_str}")
                entries_skipped += 1
                continue

            if diary_filename_col is not None:
                row_filename = normalize_filename(row.get(diary_filename_col))
                if row_filename is None:
                    entries_skipped += 1
                    continue

                candidates = filename_to_files.get(row_filename, [])
                if not candidates:
                    row_stem = filename_stem(row_filename)
                    if row_stem:
                        candidates = stem_to_files.get(row_stem, [])
                    if not candidates and row_stem:
                        fuzzy = [
                            ident.file for ident in identities
                            if row_stem in ident.normalized_stem or ident.normalized_stem in row_stem
                        ]
                        seen_ids: set[int] = set()
                        dedup: list[FileModel] = []
                        for f in fuzzy:
                            if f.id not in seen_ids:
                                seen_ids.add(f.id)
                                dedup.append(f)
                        candidates = dedup

                if len(candidates) == 1:
                    matched_files = [candidates[0]]
                elif len(candidates) > 1:
                    # Multiple files for same PID — assign to all whose date range covers this date
                    matched_files = _files_covering_date(candidates, analysis_date)
                    if not matched_files:
                        ambiguous_identifiers.add(row_filename)
                        entries_skipped += 1
                        continue
                else:
                    unmatched_identifiers.add(row_filename)
                    entries_skipped += 1
                    continue
            else:
                pid_norm = normalize_participant_id(
                    row.get(pid_col) if pid_col is not None else filename_pid
                )
                if pid_norm is None:
                    entries_skipped += 1
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
                    candidates_ident = [
                        ident for ident in identities if pid_norm in ident.normalized_filename
                    ]

                seen_ids: set[int] = set()
                dedup_ident = []
                for ident in candidates_ident:
                    if ident.file.id not in seen_ids:
                        seen_ids.add(ident.file.id)
                        dedup_ident.append(ident)

                if len(dedup_ident) == 1:
                    matched_files = [dedup_ident[0].file]
                elif len(dedup_ident) > 1:
                    # Multiple files for same PID — assign to all whose date range covers this date
                    matched_files = _files_covering_date(dedup_ident, analysis_date)
                    if not matched_files:
                        label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                        ambiguous_identifiers.add(label)
                        entries_skipped += 1
                        continue
                else:
                    label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                    unmatched_identifiers.add(label)
                    entries_skipped += 1
                    continue

            entry_data: dict[str, str | int | None] = {}
            for db_field, csv_aliases in _DESKTOP_COLUMN_ALIASES.items():
                if db_field in ("sleep_quality", "time_to_fall_asleep_minutes", "number_of_awakenings"):
                    entry_data[db_field] = _get_int_field(row, csv_aliases)
                elif db_field.endswith("_reason"):
                    raw = _get_str_field(row, csv_aliases)
                    if raw and raw in _NONWEAR_REASON_CODES:
                        raw = _NONWEAR_REASON_CODES[raw]
                    entry_data[db_field] = raw
                elif db_field == "notes":
                    entry_data[db_field] = _get_str_field(row, csv_aliases)
                else:
                    entry_data[db_field] = _get_time_field(row, csv_aliases)

            # Insert/update diary entry for every file that covers this date
            for matched_file in matched_files:
                affected_file_ids.add(matched_file.id)
                result = await db.execute(
                    select(DiaryEntry).where(
                        and_(
                            DiaryEntry.file_id == matched_file.id,
                            DiaryEntry.analysis_date == analysis_date,
                        )
                    )
                )
                existing = result.scalar_one_or_none()

                if existing:
                    for field, value in entry_data.items():
                        if value is not None:
                            setattr(existing, field, value)
                else:
                    entry = DiaryEntry(
                        file_id=matched_file.id,
                        analysis_date=analysis_date,
                        imported_by=username,
                        **{k: v for k, v in entry_data.items() if v is not None},
                    )
                    db.add(entry)

            entries_imported += 1
            matched_rows += 1

        except Exception as e:
            errors.append(f"Error processing row: {e}")
            entries_skipped += 1

    await db.commit()

    # Recompute complexity for all files that got diary entries
    if affected_file_ids:
        _schedule_complexity_recompute(background_tasks, db, affected_file_ids)

    if unmatched_identifiers:
        errors.insert(0, f"No matching activity files for: {', '.join(sorted(unmatched_identifiers))}")
    if ambiguous_identifiers:
        errors.insert(0, f"Ambiguous file matches (use filename or timepoint): {', '.join(sorted(ambiguous_identifiers))}")

    return DiaryUploadResponse(
        entries_imported=entries_imported,
        entries_skipped=entries_skipped,
        errors=errors,
        total_rows=total_rows,
        matched_rows=matched_rows,
        unmatched_identifiers=sorted(unmatched_identifiers),
        ambiguous_identifiers=sorted(ambiguous_identifiers),
    )


@router.post("/{file_id}/upload")
async def upload_diary_csv_for_file(
    file_id: int,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> DiaryUploadResponse:
    """
    Upload a diary CSV for a specific activity file (legacy endpoint).

    This endpoint does NOT require a participant_id column — all rows
    are assigned to the specified file_id.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    db_file = file_result.scalar_one_or_none()
    if not db_file or is_excluded_file_obj(db_file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Read uploaded CSV
    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    try:
        df = pl.read_csv(StringIO(text))
    except Exception as e:
        logger.exception("Failed to parse diary CSV: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {e}",
        ) from e

    # Auto-detect REDCap wide format and pivot to long before normal processing
    if is_redcap_wide_format(df.columns):
        df = convert_redcap_wide_to_long(df)

    df = df.rename({col: col.lower().strip().replace(" ", "_") for col in df.columns})

    date_col = None
    for col in ["startdate", "date", "analysis_date", "diary_date", "date_of_last_night"]:
        if col in df.columns:
            date_col = col
            break

    if date_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV must have a date column (startdate, date, analysis_date, or diary_date)",
        )

    entries_imported = 0
    entries_skipped = 0
    errors: list[str] = []

    for row in df.iter_rows(named=True):
        try:
            date_str = str(row[date_col])
            analysis_date = _parse_date(date_str)
            if analysis_date is None:
                errors.append(f"Invalid date: {date_str}")
                entries_skipped += 1
                continue

            entry_data: dict[str, str | int | None] = {}
            for db_field, csv_aliases in _DESKTOP_COLUMN_ALIASES.items():
                if db_field in ("sleep_quality", "time_to_fall_asleep_minutes", "number_of_awakenings"):
                    entry_data[db_field] = _get_int_field(row, csv_aliases)
                elif db_field.endswith("_reason"):
                    raw = _get_str_field(row, csv_aliases)
                    if raw and raw in _NONWEAR_REASON_CODES:
                        raw = _NONWEAR_REASON_CODES[raw]
                    entry_data[db_field] = raw
                elif db_field == "notes":
                    entry_data[db_field] = _get_str_field(row, csv_aliases)
                else:
                    entry_data[db_field] = _get_time_field(row, csv_aliases)

            result = await db.execute(
                select(DiaryEntry).where(
                    and_(
                        DiaryEntry.file_id == file_id,
                        DiaryEntry.analysis_date == analysis_date,
                    )
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                for field, value in entry_data.items():
                    if value is not None:
                        setattr(existing, field, value)
            else:
                entry = DiaryEntry(
                    file_id=file_id,
                    analysis_date=analysis_date,
                    imported_by=username,
                    **{k: v for k, v in entry_data.items() if v is not None},
                )
                db.add(entry)

            entries_imported += 1

        except Exception as e:
            errors.append(f"Error processing row: {e}")
            entries_skipped += 1

    await db.commit()

    # Recompute complexity now that diary data is available
    if entries_imported > 0:
        _schedule_complexity_recompute(background_tasks, db, {file_id})

    return DiaryUploadResponse(
        entries_imported=entries_imported,
        entries_skipped=entries_skipped,
        errors=errors[:10],
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _schedule_complexity_recompute(
    background_tasks: BackgroundTasks,
    db: Any,
    file_ids: set[int],
) -> None:
    """Schedule background complexity recomputation for files that got new diary data."""
    from sleep_scoring_web.api.files import _compute_complexity_for_file
    from sleep_scoring_web.db.models import RawActivityData

    async def _recompute_for_file(fid: int) -> None:
        from sleep_scoring_web.db.session import async_session_maker

        async with async_session_maker() as recompute_db:
            date_col = func.date(RawActivityData.timestamp).label("date")
            result = await recompute_db.execute(
                select(date_col).where(RawActivityData.file_id == fid).group_by(date_col).order_by(date_col)
            )
            dates = list(result.scalars().all())
            if dates:
                await _compute_complexity_for_file(fid, dates)

    for fid in file_ids:
        background_tasks.add_task(_recompute_for_file, fid)
    logger.info("Scheduled complexity recomputation for %d files after diary import", len(file_ids))


def _parse_date(date_str: str) -> date | None:
    """Parse a date string, trying multiple formats."""
    date_str = date_str.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _files_covering_date(candidates: list, row_date: date | None) -> list:
    """
    Return all files whose start_time..end_time range contains row_date.

    ``candidates`` may be FileModel objects or FileIdentity objects (uses ``.file``).
    If row_date is None, returns an empty list.
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


def _get_time_field(row: dict, field_names: list[str]) -> str | None:
    """Extract a time field from row, trying multiple column names."""
    for name in field_names:
        if name in row and row[name] is not None:
            value = str(row[name]).strip()
            if value and value.lower() not in ("", "nan", "none", "null"):
                # Validate time format (HH:MM or HH:MM:SS)
                try:
                    if ":" in value:
                        parts = value.split(":")
                        if len(parts) >= 2:
                            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
                except (ValueError, IndexError):
                    pass
                return value
    return None


def _get_int_field(row: dict, field_names: list[str]) -> int | None:
    """Extract an integer field from row, trying multiple column names."""
    for name in field_names:
        if name in row and row[name] is not None:
            try:
                return int(float(row[name]))
            except (ValueError, TypeError):
                pass
    return None


def _get_str_field(row: dict, field_names: list[str]) -> str | None:
    """Extract a string field from row, trying multiple column names."""
    for name in field_names:
        if name in row and row[name] is not None:
            value = str(row[name]).strip()
            if value and value.lower() not in ("nan", "none", "null"):
                return value
    return None
