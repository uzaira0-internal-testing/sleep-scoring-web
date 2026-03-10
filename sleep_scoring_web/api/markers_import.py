"""
Marker import endpoints for nonwear sensor CSV and sleep marker CSV uploads.

Provides bulk import of markers from CSV files (desktop export, web export, nonwear sensor data).
"""

import calendar
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from io import StringIO
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, or_, select

from sleep_scoring_web.api.access import require_file_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.api.markers import (
    _calculate_and_store_metrics,
    _patch_nonwear_annotation,
    _patch_sleep_annotation,
    _update_user_annotation,
    _upsert_consensus_candidate_snapshot,
    naive_to_unix,
)
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import Marker
from sleep_scoring_web.schemas import ManualNonwearPeriod, SleepPeriod
from sleep_scoring_web.schemas.enums import MarkerCategory, MarkerType
from sleep_scoring_web.services.file_identity import (
    build_file_identity,
    filename_stem,
    is_excluded_file_obj,
    normalize_filename,
    normalize_participant_id,
    normalize_timepoint,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Nonwear Sensor Data Upload
# =============================================================================


class NonwearUploadResponse(BaseModel):
    """Response after uploading nonwear sensor CSV."""

    dates_imported: int
    markers_created: int
    dates_skipped: int
    errors: list[str] = Field(default_factory=list)
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_identifiers: list[str] = Field(default_factory=list)
    ambiguous_identifiers: list[str] = Field(default_factory=list)


@router.post("/nonwear/upload")
async def upload_nonwear_csv(
    file: Annotated[UploadFile, File(description="Nonwear CSV file")],
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> NonwearUploadResponse:
    """
    Upload nonwear sensor data CSV (study-wide).

    Matches rows to activity files by participant_id column.

    Expected CSV columns (case-insensitive):
    - participant_id: Participant identifier (matched to activity filenames)
    - date / startdate: Analysis date (YYYY-MM-DD or MM/DD/YYYY)
    - start_time / nonwear_start: Nonwear start time (HH:MM)
    - end_time / nonwear_end: Nonwear end time (HH:MM)

    For each date+file, existing nonwear markers are replaced.
    Multiple nonwear periods per date are supported (one row per period).
    """
    return await _process_nonwear_csv(file, db, username, file_id=None)


@router.post("/{file_id}/nonwear/upload")
async def upload_nonwear_csv_for_file(
    file_id: int,
    file: Annotated[UploadFile, File(description="Nonwear CSV file")],
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> NonwearUploadResponse:
    """
    Upload nonwear sensor data CSV for a specific activity file (legacy).

    Does not require participant_id — all rows go to the specified file.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file_obj = file_result.scalar_one_or_none()
    if not file_obj or is_excluded_file_obj(file_obj):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return await _process_nonwear_csv(file, db, username, file_id=file_id)


async def _process_nonwear_csv(
    file: UploadFile,
    db: DbSession,
    username: str,
    file_id: int | None,
) -> NonwearUploadResponse:
    """Shared implementation for nonwear CSV processing."""
    import polars as pl

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            text = content.decode("cp1252")

    lines = text.splitlines()
    filtered_lines = [line for line in lines if not line.startswith("#")]
    text = "\n".join(filtered_lines)

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty after removing comment lines",
        )

    try:
        df = pl.read_csv(StringIO(text))
    except Exception as e:
        logger.exception("Failed to parse CSV: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {e}",
        ) from e

    df = df.rename({col: col.lower().strip().replace(" ", "_") for col in df.columns})

    date_col = None
    for col in ["date", "startdate", "analysis_date", "diary_date", "date_of_last_night"]:
        if col in df.columns:
            date_col = col
            break

    start_col = None
    for col in [
        "start_time",
        "start",
        "nonwear_start",
        "nonwear_start_time",
        "nw_start",
        "start_datetime",
        "nonwear_start_datetime",
    ]:
        if col in df.columns:
            start_col = col
            break
    end_col = None
    for col in [
        "end_time",
        "end",
        "nonwear_end",
        "nonwear_end_time",
        "nw_end",
        "end_datetime",
        "nonwear_end_datetime",
    ]:
        if col in df.columns:
            end_col = col
            break
    if start_col is None or end_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have start and end columns. Found columns: {list(df.columns)}",
        )

    if date_col is None and start_col:
        date_col = None

    pid_col = None
    nw_filename_col = None
    timepoint_col = None
    filename_pid: str | None = None
    all_files: list[FileModel] = []
    identities = []
    filename_to_files: dict[str, list[FileModel]] = {}
    stem_to_files: dict[str, list[FileModel]] = {}
    pid_to_identities: dict[str, list[Any]] = {}
    pid_tp_to_identities: dict[tuple[str, str], list[Any]] = {}
    unmatched_identifiers: set[str] = set()
    ambiguous_identifiers: set[str] = set()

    if file_id is None:
        for col in ["filename", "file", "file_name"]:
            if col in df.columns:
                nw_filename_col = col
                break

        if nw_filename_col is None:
            for col in ["participant_id", "participantid", "pid", "subject_id", "id"]:
                if col in df.columns:
                    pid_col = col
                    break
            for col in ["participant_timepoint", "timepoint", "tp"]:
                if col in df.columns:
                    timepoint_col = col
                    break
            if pid_col is None:
                filename_pid = filename_stem(file.filename)
                if not filename_pid:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="CSV must have participant_id or filename column, or upload filename must identify participant",
                    )

        files_result = await db.execute(select(FileModel))
        all_files = [f for f in files_result.scalars().all() if not is_excluded_file_obj(f)]
        identities = [build_file_identity(f) for f in all_files]
        for ident in identities:
            filename_to_files.setdefault(ident.normalized_filename, []).append(ident.file)
            stem_to_files.setdefault(ident.normalized_stem, []).append(ident.file)
            if ident.participant_id_norm:
                pid_to_identities.setdefault(ident.participant_id_norm, []).append(ident)
                if ident.timepoint_norm:
                    pid_tp_to_identities.setdefault((ident.participant_id_norm, ident.timepoint_norm), []).append(ident)
            if ident.short_pid_norm:
                pid_to_identities.setdefault(ident.short_pid_norm, []).append(ident)
                if ident.timepoint_norm:
                    pid_tp_to_identities.setdefault((ident.short_pid_norm, ident.timepoint_norm), []).append(ident)

    file_date_periods: dict[tuple[int, date], list[tuple[str, str]]] = defaultdict(list)
    dates_skipped = 0
    matched_rows = 0
    total_rows = int(df.height)
    errors: list[str] = []

    for row in df.iter_rows(named=True):
        matched_file_ids: list[int] = [file_id] if file_id is not None else []

        # Parse date early for date-range matching when multiple files share a PID
        start_raw = str(row[start_col]).strip()
        end_raw = str(row[end_col]).strip()
        row_date_for_match: date | None = None
        if date_col is not None:
            row_date_for_match = _parse_nonwear_date(str(row[date_col]).strip())
        elif start_raw and start_raw.lower() not in ("nan", "none"):
            row_date_for_match = _parse_nonwear_date(start_raw.split(" ")[0].split("T")[0])

        if not matched_file_ids:
            if nw_filename_col is not None:
                raw_fn = normalize_filename(row.get(nw_filename_col))
                if raw_fn is None:
                    dates_skipped += 1
                    continue
                candidates = filename_to_files.get(raw_fn, [])
                if not candidates:
                    raw_stem = filename_stem(raw_fn)
                    if raw_stem:
                        candidates = stem_to_files.get(raw_stem, [])
                    if not candidates and raw_stem:
                        fuzzy = [ident.file for ident in identities if raw_stem in ident.normalized_stem or ident.normalized_stem in raw_stem]
                        seen_ids: set[int] = set()
                        dedup: list[FileModel] = []
                        for f in fuzzy:
                            if f.id not in seen_ids:
                                seen_ids.add(f.id)
                                dedup.append(f)
                        candidates = dedup
                if len(candidates) == 1:
                    matched_file_ids = [candidates[0].id]
                elif len(candidates) > 1:
                    covering = _files_covering_date(candidates, row_date_for_match)
                    if covering:
                        matched_file_ids = [f.id for f in covering]
                    else:
                        ambiguous_identifiers.add(raw_fn)
                        dates_skipped += 1
                        continue
                else:
                    unmatched_identifiers.add(raw_fn)
                    dates_skipped += 1
                    continue
            else:
                pid_norm = normalize_participant_id(row.get(pid_col) if pid_col is not None else filename_pid)
                if pid_norm is None:
                    dates_skipped += 1
                    continue

                tp_norm = normalize_timepoint(row.get(timepoint_col)) if timepoint_col else None
                candidates_ident = []

                if tp_norm:
                    candidates_ident = pid_tp_to_identities.get((pid_norm, tp_norm), [])
                    if not candidates_ident:
                        pid_pool = pid_to_identities.get(pid_norm, [])
                        if pid_pool:
                            candidates_ident = [
                                ident for ident in pid_pool if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename
                            ]
                else:
                    candidates_ident = pid_to_identities.get(pid_norm, [])

                if not candidates_ident:
                    fuzzy_all = [ident for ident in identities if pid_norm in ident.normalized_filename]
                    if tp_norm and len(fuzzy_all) > 1:
                        fuzzy_filtered = [ident for ident in fuzzy_all if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename]
                        candidates_ident = fuzzy_filtered or fuzzy_all
                    else:
                        candidates_ident = fuzzy_all

                seen_ids: set[int] = set()
                dedup_ident = []
                for ident in candidates_ident:
                    if ident.file.id not in seen_ids:
                        seen_ids.add(ident.file.id)
                        dedup_ident.append(ident)

                if len(dedup_ident) == 1:
                    matched_file_ids = [dedup_ident[0].file.id]
                elif len(dedup_ident) > 1:
                    covering = _files_covering_date(dedup_ident, row_date_for_match)
                    if covering:
                        matched_file_ids = [f.id for f in covering]
                    else:
                        label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                        ambiguous_identifiers.add(label)
                        dates_skipped += 1
                        continue
                else:
                    label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                    unmatched_identifiers.add(label)
                    dates_skipped += 1
                    continue

            matched_rows += 1
        if not start_raw or not end_raw or start_raw.lower() in ("nan", "none") or end_raw.lower() in ("nan", "none"):
            dates_skipped += 1
            continue

        if date_col is not None:
            date_str = str(row[date_col]).strip()
            analysis_date_val = _parse_nonwear_date(date_str)
        else:
            analysis_date_val = _parse_nonwear_date(start_raw.split(" ")[0].split("T")[0])

        if analysis_date_val is None:
            errors.append(f"Invalid date from row: {start_raw}")
            dates_skipped += 1
            continue

        start_time = _extract_time(start_raw)
        end_time = _extract_time(end_raw)
        if start_time is None or end_time is None:
            errors.append(f"Invalid time on {analysis_date_val}: {start_raw} - {end_raw}")
            dates_skipped += 1
            continue

        for fid in matched_file_ids:
            file_date_periods[(fid, analysis_date_val)].append((start_time, end_time))

    dates_imported = 0
    markers_created = 0

    # Delete ALL existing sensor nonwear for each affected file before inserting.
    # Per-date deletion is unreliable because analysis_date may not match between
    # old and new uploads (e.g., different CSV date formats or noon-vs-calendar day).
    deleted_file_ids: set[int] = set()
    for fid, _ in file_date_periods:
        if fid not in deleted_file_ids:
            await db.execute(
                delete(Marker).where(
                    and_(
                        Marker.file_id == fid,
                        Marker.marker_category == MarkerCategory.NONWEAR,
                        Marker.marker_type == "sensor",
                    )
                )
            )
            deleted_file_ids.add(fid)

    for (fid, analysis_date_val), periods in file_date_periods.items():
        for i, (start_time, end_time) in enumerate(periods):
            start_h, start_m = map(int, start_time.split(":"))
            end_h, end_m = map(int, end_time.split(":"))

            start_dt = datetime(
                analysis_date_val.year,
                analysis_date_val.month,
                analysis_date_val.day,
                start_h,
                start_m,
            )
            end_dt = datetime(
                analysis_date_val.year,
                analysis_date_val.month,
                analysis_date_val.day,
                end_h,
                end_m,
            )
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)

            start_ts = float(calendar.timegm(start_dt.timetuple()))
            end_ts = float(calendar.timegm(end_dt.timetuple()))

            db_marker = Marker(
                file_id=fid,
                analysis_date=analysis_date_val,
                marker_category=MarkerCategory.NONWEAR,
                marker_type="sensor",
                start_timestamp=start_ts,
                end_timestamp=end_ts,
                period_index=i + 1,
                created_by=username,
            )
            db.add(db_marker)
            markers_created += 1

        dates_imported += 1

    await db.commit()

    if unmatched_identifiers:
        errors.insert(0, f"No matching activity files for: {', '.join(sorted(unmatched_identifiers))}")
    if ambiguous_identifiers:
        errors.insert(0, f"Ambiguous file matches (use filename or timepoint): {', '.join(sorted(ambiguous_identifiers))}")

    return NonwearUploadResponse(
        dates_imported=dates_imported,
        markers_created=markers_created,
        dates_skipped=dates_skipped,
        errors=errors,
        total_rows=total_rows,
        matched_rows=matched_rows,
        unmatched_identifiers=sorted(unmatched_identifiers),
        ambiguous_identifiers=sorted(ambiguous_identifiers),
    )


def _extract_time(value: str) -> str | None:
    """
    Extract HH:MM time from a time or datetime string.

    Handles:
      - "10:30" -> "10:30"
      - "2025-08-01 10:30:00" -> "10:30"
      - "2025-08-01T10:30:00" -> "10:30"
      - "10:30 AM" -> "10:30"  (already HH:MM, AM/PM stripped)
    """
    v = value.strip()
    if not v or v.lower() in ("nan", "none", "null", ""):
        return None

    # If it contains a space or T, try to extract time portion from datetime
    time_part = v
    if "T" in v:
        time_part = v.split("T")[1].split("+")[0].split("Z")[0]
    elif " " in v:
        # Could be "2025-08-01 10:30:00" or "10:30 AM"
        parts = v.split(" ", 1)
        # If first part looks like a date (contains -), use second part as time
        if "-" in parts[0] or "/" in parts[0]:
            time_part = parts[1]
        # Otherwise keep full string (it may be "10:30 AM")

    # Strip AM/PM for now (we just need HH:MM)
    time_part = time_part.strip()
    is_pm = "PM" in time_part.upper()
    is_am = "AM" in time_part.upper()
    time_part = time_part.upper().replace("PM", "").replace("AM", "").strip()

    try:
        colon_parts = time_part.split(":")
        h = int(colon_parts[0])
        m = int(colon_parts[1]) if len(colon_parts) > 1 else 0

        if is_am or is_pm:
            if h == 12:
                h = 0 if is_am else 12
            elif is_pm:
                h += 12

        return f"{h:02d}:{m:02d}"
    except (ValueError, IndexError):
        return None


def _files_covering_date(candidates: list[Any], row_date: date | None) -> list[Any]:
    """
    Return all files whose start_time..end_time range contains row_date.

    Candidates may be FileModel objects or FileIdentity objects (uses ``.file``).
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


def _parse_nonwear_date(date_str: str) -> date | None:
    """Parse a date string, trying multiple formats."""
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue
    return None


def _parse_full_datetime(dt_str: str) -> datetime | None:
    """Parse a full datetime string (from web export Onset/Offset Datetime columns)."""
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
    ):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    return None


# =============================================================================
# Sleep Marker Import (Desktop + Web Export)
# =============================================================================


class SleepImportResponse(BaseModel):
    """Response after importing sleep marker CSV (desktop or web export)."""

    dates_imported: int
    markers_created: int
    nonwear_markers_created: int = 0
    no_sleep_dates: int
    dates_skipped: int
    errors: list[str] = Field(default_factory=list)
    total_rows: int = 0
    matched_rows: int = 0
    unmatched_identifiers: list[str] = Field(default_factory=list)
    ambiguous_identifiers: list[str] = Field(default_factory=list)


@router.post("/sleep/upload")
async def upload_sleep_csv(
    file: Annotated[UploadFile, File(description="Desktop sleep marker CSV export")],
    background_tasks: BackgroundTasks,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> SleepImportResponse:
    """
    Upload a sleep marker export CSV (desktop or web app format).

    Supports both desktop export CSVs (with onset_time/offset_time) and
    web export CSVs (with Onset Datetime/Offset Datetime, Study Date, etc.).

    Matches rows to activity files by `filename` column, or by
    `participant_id` + `timepoint` columns when no filename is present.

    For each (file, date), existing sleep markers are replaced and metrics recalculated.

    Expected CSV columns (comment lines starting with # are stripped):
    - filename OR (numerical_participant_id + participant_timepoint)
    - sleep_date / study_date / date: Analysis date (YYYY-MM-DD)
    - onset_time + offset_time (HH:MM), OR onset_datetime + offset_datetime (full datetime)
    - marker_type (optional): MAIN_SLEEP / NAP (default: MAIN_SLEEP)
    - marker_index / period_index (optional): Period index (default: sequential)
    - is_no_sleep (optional): TRUE/FALSE -- marks date as no-sleep
    - needs_consensus (optional): TRUE/FALSE -- flags for consensus review
    - Rows with NO_SLEEP onset/offset are treated as no-sleep dates.
    """
    return await _process_sleep_csv(file, background_tasks, db, username)


async def _process_sleep_csv(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    db: DbSession,
    username: str,
) -> SleepImportResponse:
    """Process a sleep marker CSV export (desktop or web format)."""
    import polars as pl

    content = await file.read()
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError:
            text = content.decode("cp1252")

    lines = text.splitlines()
    filtered_lines = [line for line in lines if not line.startswith("#")]
    text = "\n".join(filtered_lines)

    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="CSV file is empty after removing comment lines",
        )

    try:
        df = pl.read_csv(StringIO(text))
    except Exception as e:
        logger.exception("Failed to parse CSV: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse CSV: {e}",
        ) from e

    df = df.rename({col: col.lower().strip().replace(" ", "_") for col in df.columns})

    # --- Detect columns (supports both desktop and web export formats) ---
    # After rename, web export "Study Date" -> "study_date", "Period Index" -> "period_index", etc.

    filename_col = None
    for col in ["filename", "file", "file_name"]:
        if col in df.columns:
            filename_col = col
            break

    pid_col = None
    timepoint_col = None
    filename_pid: str | None = None
    if filename_col is None:
        for col in ["numerical_participant_id", "participant_id", "participantid", "pid"]:
            if col in df.columns:
                pid_col = col
                break
        for col in ["participant_timepoint", "timepoint", "tp"]:
            if col in df.columns:
                timepoint_col = col
                break
        if pid_col is None:
            filename_pid = filename_stem(file.filename)
            if not filename_pid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV must have filename or participant_id columns, or upload filename must identify participant",
                )

    date_col = None
    for col in ["sleep_date", "study_date", "date", "analysis_date"]:
        if col in df.columns:
            date_col = col
            break
    if date_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have a date column (sleep_date, study_date, date, or analysis_date). Found: {list(df.columns)}",
        )

    # Full datetime columns (web export: "Onset Datetime", "Offset Datetime")
    onset_datetime_col = None
    for col in ["onset_datetime", "onset_date_time"]:
        if col in df.columns:
            onset_datetime_col = col
            break

    offset_datetime_col = None
    for col in ["offset_datetime", "offset_date_time"]:
        if col in df.columns:
            offset_datetime_col = col
            break

    onset_date_col = "onset_date" if "onset_date" in df.columns else None

    onset_time_col = None
    for col in ["onset_time", "onset", "sleep_onset"]:
        if col in df.columns:
            onset_time_col = col
            break

    offset_date_col = "offset_date" if "offset_date" in df.columns else None

    offset_time_col = None
    for col in ["offset_time", "offset", "sleep_offset"]:
        if col in df.columns:
            offset_time_col = col
            break

    # Must have either full datetime columns or time columns
    if onset_time_col is None and onset_datetime_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have onset_time or onset_datetime column. Found: {list(df.columns)}",
        )
    if offset_time_col is None and offset_datetime_col is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"CSV must have offset_time or offset_datetime column. Found: {list(df.columns)}",
        )

    type_col = None
    for col in ["marker_type", "type"]:
        if col in df.columns:
            type_col = col
            break

    index_col = None
    for col in ["marker_index", "period_index", "index"]:
        if col in df.columns:
            index_col = col
            break

    consensus_col = None
    for col in ["needs_consensus", "needs_consensus_review"]:
        if col in df.columns:
            consensus_col = col
            break

    # Web export "Is No Sleep" column (TRUE/FALSE)
    no_sleep_col = None
    for col in ["is_no_sleep", "no_sleep"]:
        if col in df.columns:
            no_sleep_col = col
            break

    # Web export "Scored By" column -- use for attribution
    scored_by_col = None
    for col in ["scored_by", "scorer", "created_by"]:
        if col in df.columns:
            scored_by_col = col
            break

    files_result = await db.execute(select(FileModel))
    all_files = [f for f in files_result.scalars().all() if not is_excluded_file_obj(f)]
    identities = [build_file_identity(f) for f in all_files]

    filename_to_files: dict[str, list[FileModel]] = {}
    stem_to_files: dict[str, list[FileModel]] = {}
    pid_to_identities: dict[str, list[Any]] = {}
    pid_tp_to_identities: dict[tuple[str, str], list[Any]] = {}

    for ident in identities:
        filename_to_files.setdefault(ident.normalized_filename, []).append(ident.file)
        stem_to_files.setdefault(ident.normalized_stem, []).append(ident.file)
        if ident.participant_id_norm:
            pid_to_identities.setdefault(ident.participant_id_norm, []).append(ident)
            if ident.timepoint_norm:
                pid_tp_to_identities.setdefault((ident.participant_id_norm, ident.timepoint_norm), []).append(ident)
        if ident.short_pid_norm:
            pid_to_identities.setdefault(ident.short_pid_norm, []).append(ident)
            if ident.timepoint_norm:
                pid_tp_to_identities.setdefault((ident.short_pid_norm, ident.timepoint_norm), []).append(ident)

    file_date_periods: dict[tuple[int, date], list[dict[str, Any]]] = defaultdict(list)
    file_date_nonwear: dict[tuple[int, date], list[dict[str, Any]]] = defaultdict(list)
    no_sleep_dates_set: set[tuple[int, date]] = set()
    consensus_dates_set: set[tuple[int, date]] = set()
    dates_skipped = 0
    matched_rows = 0
    total_rows = int(df.height)
    errors: list[str] = []
    unmatched_identifiers: set[str] = set()
    ambiguous_identifiers: set[str] = set()

    for row in df.iter_rows(named=True):
        matched_files: list[FileModel] = []

        # Parse date early for disambiguation when multiple files match same PID
        date_str = str(row[date_col]).strip()
        analysis_date_val = _parse_nonwear_date(date_str)
        if analysis_date_val is None:
            errors.append(f"Invalid date: {date_str}")
            dates_skipped += 1
            continue

        if filename_col is not None:
            row_filename = normalize_filename(row.get(filename_col))
            if row_filename is None:
                dates_skipped += 1
                continue

            candidates = filename_to_files.get(row_filename, [])
            if not candidates:
                row_stem = filename_stem(row_filename)
                if row_stem:
                    candidates = stem_to_files.get(row_stem, [])
                if not candidates and row_stem:
                    fuzzy = [ident.file for ident in identities if row_stem in ident.normalized_stem or ident.normalized_stem in row_stem]
                    seen_ids: set[int] = set()
                    dedup: list[FileModel] = []
                    for file_obj in fuzzy:
                        if file_obj.id not in seen_ids:
                            seen_ids.add(file_obj.id)
                            dedup.append(file_obj)
                    candidates = dedup

            if len(candidates) == 1:
                matched_files = candidates
            elif len(candidates) > 1:
                matched_files = _files_covering_date(candidates, analysis_date_val)
                if not matched_files:
                    ambiguous_identifiers.add(row_filename)
                    dates_skipped += 1
                    continue
            else:
                unmatched_identifiers.add(row_filename)
                dates_skipped += 1
                continue
        else:
            pid_norm = normalize_participant_id(row.get(pid_col) if pid_col is not None else filename_pid)
            if pid_norm is None:
                dates_skipped += 1
                continue

            tp_norm = normalize_timepoint(row.get(timepoint_col)) if timepoint_col else None
            candidates_ident = []

            if tp_norm:
                candidates_ident = pid_tp_to_identities.get((pid_norm, tp_norm), [])
                if not candidates_ident:
                    pid_pool = pid_to_identities.get(pid_norm, [])
                    if pid_pool:
                        candidates_ident = [ident for ident in pid_pool if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename]
            else:
                candidates_ident = pid_to_identities.get(pid_norm, [])

            if not candidates_ident:
                fuzzy_all = [ident for ident in identities if pid_norm in ident.normalized_filename]
                if tp_norm and len(fuzzy_all) > 1:
                    fuzzy_filtered = [ident for ident in fuzzy_all if ident.timepoint_norm == tp_norm or tp_norm in ident.normalized_filename]
                    candidates_ident = fuzzy_filtered or fuzzy_all
                else:
                    candidates_ident = fuzzy_all

            seen_ids: set[int] = set()
            dedup_ident = []
            for ident in candidates_ident:
                if ident.file.id not in seen_ids:
                    seen_ids.add(ident.file.id)
                    dedup_ident.append(ident)

            if len(dedup_ident) == 1:
                matched_files = [dedup_ident[0].file]
            elif len(dedup_ident) > 1:
                matched_files = _files_covering_date(dedup_ident, analysis_date_val)
                if not matched_files:
                    label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                    ambiguous_identifiers.add(label)
                    dates_skipped += 1
                    continue
            else:
                label = f"{pid_norm} {tp_norm}".strip() if tp_norm else pid_norm
                unmatched_identifiers.add(label)
                dates_skipped += 1
                continue

        matched_rows += 1
        matched_file_ids = [f.id for f in matched_files]

        # Check for "no sleep" via dedicated column (web export) or NO_SLEEP sentinel (desktop)
        if no_sleep_col is not None:
            raw_no_sleep = str(row[no_sleep_col]).strip().lower()
            if raw_no_sleep in ("true", "1", "yes"):
                for fid in matched_file_ids:
                    no_sleep_dates_set.add((fid, analysis_date_val))
                if consensus_col is not None:
                    raw_consensus = str(row[consensus_col]).strip().lower()
                    if raw_consensus in ("true", "1", "yes"):
                        for fid in matched_file_ids:
                            consensus_dates_set.add((fid, analysis_date_val))
                continue

        onset_raw = str(row[onset_time_col]).strip() if onset_time_col else ""
        offset_raw = str(row[offset_time_col]).strip() if offset_time_col else ""

        if onset_raw.upper() == "NO_SLEEP" or offset_raw.upper() == "NO_SLEEP":
            for fid in matched_file_ids:
                no_sleep_dates_set.add((fid, analysis_date_val))
            if consensus_col is not None:
                raw_consensus = str(row[consensus_col]).strip().lower()
                if raw_consensus in ("true", "1", "yes"):
                    for fid in matched_file_ids:
                        consensus_dates_set.add((fid, analysis_date_val))
            continue

        # Try full datetime columns first (web export: "Onset Datetime" / "Offset Datetime")
        onset_ts: float | None = None
        offset_ts: float | None = None

        if onset_datetime_col is not None and offset_datetime_col is not None:
            onset_dt_raw = str(row[onset_datetime_col]).strip()
            offset_dt_raw = str(row[offset_datetime_col]).strip()
            if onset_dt_raw.upper() not in ("NAN", "NONE", "NULL", ""):
                onset_dt_parsed = _parse_full_datetime(onset_dt_raw)
                offset_dt_parsed = _parse_full_datetime(offset_dt_raw)
                if onset_dt_parsed is not None and offset_dt_parsed is not None:
                    onset_ts = float(calendar.timegm(onset_dt_parsed.timetuple()))
                    offset_ts = float(calendar.timegm(offset_dt_parsed.timetuple()))

        # Fall back to time columns (desktop export or web export with Onset Time/Offset Time)
        if onset_ts is None or offset_ts is None:
            if onset_raw.upper() in ("NAN", "NONE", "NULL", "") or offset_raw.upper() in ("NAN", "NONE", "NULL", ""):
                dates_skipped += 1
                continue

            if onset_date_col is not None:
                onset_date_str = str(row[onset_date_col]).strip()
                onset_date_val = _parse_nonwear_date(onset_date_str)
            else:
                onset_date_val = analysis_date_val

            onset_time_str = _extract_time(onset_raw)
            if onset_date_val is None or onset_time_str is None:
                errors.append(f"Invalid onset on {date_str}: {onset_raw}")
                dates_skipped += 1
                continue

            if offset_date_col is not None:
                offset_date_str = str(row[offset_date_col]).strip()
                offset_date_val = _parse_nonwear_date(offset_date_str)
            else:
                offset_date_val = None

            offset_time_str = _extract_time(offset_raw)
            if offset_time_str is None:
                errors.append(f"Invalid offset on {date_str}: {offset_raw}")
                dates_skipped += 1
                continue

            onset_h, onset_m = map(int, onset_time_str.split(":"))
            # For noon-to-noon analysis windows: onset times before noon (e.g. 12:30 AM)
            # belong to the NEXT calendar day relative to analysis_date, because a sleep
            # onset after midnight means the night rolled over past midnight.
            if onset_date_col is None and onset_h < 12:
                onset_day = onset_date_val + timedelta(days=1)
            else:
                onset_day = onset_date_val
            onset_dt = datetime(onset_day.year, onset_day.month, onset_day.day, onset_h, onset_m)

            offset_h, offset_m = map(int, offset_time_str.split(":"))
            if offset_date_val is not None:
                offset_dt = datetime(offset_date_val.year, offset_date_val.month, offset_date_val.day, offset_h, offset_m)
            else:
                offset_dt = datetime(onset_day.year, onset_day.month, onset_day.day, offset_h, offset_m)
                if offset_dt <= onset_dt:
                    offset_dt += timedelta(days=1)

            onset_ts = float(calendar.timegm(onset_dt.timetuple()))
            offset_ts = float(calendar.timegm(offset_dt.timetuple()))

        # Detect nonwear vs sleep rows
        is_nonwear_row = False
        marker_type = MarkerType.MAIN_SLEEP
        if type_col is not None:
            raw_type = str(row[type_col]).strip().upper().replace(" ", "_")
            if raw_type in ("MANUAL_NONWEAR", "NONWEAR"):
                is_nonwear_row = True
            elif raw_type == "NAP":
                marker_type = MarkerType.NAP
            elif raw_type == "MAIN_SLEEP":
                marker_type = MarkerType.MAIN_SLEEP

        marker_index = None
        if index_col is not None:
            try:
                marker_index = int(float(row[index_col]))
            except (ValueError, TypeError):
                marker_index = None

        if consensus_col is not None:
            raw_consensus = str(row[consensus_col]).strip().lower()
            if raw_consensus in ("true", "1", "yes"):
                for fid in matched_file_ids:
                    consensus_dates_set.add((fid, analysis_date_val))

        if is_nonwear_row:
            for fid in matched_file_ids:
                file_date_nonwear[(fid, analysis_date_val)].append({"start_ts": onset_ts, "end_ts": offset_ts})
        else:
            for fid in matched_file_ids:
                file_date_periods[(fid, analysis_date_val)].append(
                    {
                        "onset_ts": onset_ts,
                        "offset_ts": offset_ts,
                        "marker_type": marker_type,
                        "marker_index": marker_index,
                    }
                )

    dates_imported = 0
    markers_created = 0
    nonwear_markers_created = 0

    # Collect sleep and nonwear models per (file_id, date) for merged annotation updates
    sleep_models_by_key: dict[tuple[int, date], list[SleepPeriod]] = {}
    nonwear_models_by_key: dict[tuple[int, date], list[ManualNonwearPeriod]] = {}

    # --- Persist sleep markers ---
    for (fid, analysis_date_val), periods in file_date_periods.items():
        await db.execute(
            delete(Marker).where(
                and_(
                    Marker.file_id == fid,
                    Marker.analysis_date == analysis_date_val,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    or_(Marker.created_by == username, Marker.created_by.is_(None)),
                )
            )
        )

        sleep_period_models: list[SleepPeriod] = []
        for i, period in enumerate(periods):
            idx = period["marker_index"] if period["marker_index"] is not None else i + 1
            db_marker = Marker(
                file_id=fid,
                analysis_date=analysis_date_val,
                marker_category=MarkerCategory.SLEEP,
                marker_type=period["marker_type"].value,
                start_timestamp=period["onset_ts"],
                end_timestamp=period["offset_ts"],
                period_index=idx,
                created_by=username,
            )
            db.add(db_marker)
            markers_created += 1
            sleep_period_models.append(
                SleepPeriod(
                    onset_timestamp=period["onset_ts"],
                    offset_timestamp=period["offset_ts"],
                    marker_index=idx,
                    marker_type=period["marker_type"],
                )
            )

        dates_imported += 1
        sleep_models_by_key[(fid, analysis_date_val)] = sleep_period_models
        background_tasks.add_task(
            _calculate_and_store_metrics,
            fid,
            analysis_date_val,
            sleep_period_models,
            username,
        )

    # --- Persist nonwear markers ---
    for (fid, analysis_date_val), nw_periods in file_date_nonwear.items():
        # Delete existing manual nonwear markers (preserve sensor nonwear)
        await db.execute(
            delete(Marker).where(
                and_(
                    Marker.file_id == fid,
                    Marker.analysis_date == analysis_date_val,
                    Marker.marker_category == MarkerCategory.NONWEAR,
                    Marker.marker_type != "sensor",
                    or_(Marker.created_by == username, Marker.created_by.is_(None)),
                )
            )
        )

        nonwear_period_models: list[ManualNonwearPeriod] = []
        for i, nw in enumerate(nw_periods):
            db_marker = Marker(
                file_id=fid,
                analysis_date=analysis_date_val,
                marker_category=MarkerCategory.NONWEAR,
                marker_type="manual",
                start_timestamp=nw["start_ts"],
                end_timestamp=nw["end_ts"],
                period_index=i + 1,
                created_by=username,
            )
            db.add(db_marker)
            nonwear_markers_created += 1
            nonwear_period_models.append(
                ManualNonwearPeriod(
                    start_timestamp=nw["start_ts"],
                    end_timestamp=nw["end_ts"],
                    marker_index=i + 1,
                )
            )

        nonwear_models_by_key[(fid, analysis_date_val)] = nonwear_period_models
        # Count as imported date if not already counted from sleep
        if (fid, analysis_date_val) not in file_date_periods:
            dates_imported += 1

    # --- Resolve no-sleep dates BEFORE annotation scheduling ---
    # Only remove no-sleep flag if the date has MAIN_SLEEP markers.
    # Dates with only NAP markers stay in no_sleep_dates_set.
    for key, periods in file_date_periods.items():
        if any(p.get("marker_type") == MarkerType.MAIN_SLEEP for p in periods):
            no_sleep_dates_set.discard(key)

    # --- Deferred annotation updates (merged sleep + nonwear) ---
    # Keys with both sleep and nonwear get a single merged update.
    # Keys with only one type must NOT null out the other type's annotation.
    # Exclude no-sleep dates -- they're handled separately below to avoid
    # racing background tasks (one setting is_no_sleep=False, the other True).
    sleep_keys = set(file_date_periods.keys()) - no_sleep_dates_set
    nonwear_keys = set(file_date_nonwear.keys()) - no_sleep_dates_set
    both_keys = sleep_keys & nonwear_keys
    sleep_only_keys = sleep_keys - both_keys
    nonwear_only_keys = nonwear_keys - both_keys

    for key in both_keys:
        fid, analysis_date_val = key
        background_tasks.add_task(
            _update_user_annotation,
            fid,
            analysis_date_val,
            username,
            sleep_models_by_key.get(key),
            nonwear_models_by_key.get(key),
            None,
            "Imported from export",
            False,
            key in consensus_dates_set,
        )
    for key in sleep_only_keys:
        fid, analysis_date_val = key
        background_tasks.add_task(
            _patch_sleep_annotation,
            fid,
            analysis_date_val,
            username,
            sleep_models_by_key[key],
            "Imported from export",
            False,
            key in consensus_dates_set,
        )
    for key in nonwear_only_keys:
        fid, analysis_date_val = key
        background_tasks.add_task(
            _patch_nonwear_annotation,
            fid,
            analysis_date_val,
            username,
            nonwear_models_by_key[key],
            "Imported from export",
            key in consensus_dates_set,
        )

    # --- No-sleep dates: delete MAIN_SLEEP, preserve NAPs, set is_no_sleep=True ---
    for fid, analysis_date_val in no_sleep_dates_set:
        await db.execute(
            delete(Marker).where(
                and_(
                    Marker.file_id == fid,
                    Marker.analysis_date == analysis_date_val,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    Marker.marker_type == MarkerType.MAIN_SLEEP,
                    or_(Marker.created_by == username, Marker.created_by.is_(None)),
                )
            )
        )
        # Pass any NAP/nonwear models that were imported for this no-sleep date
        nap_models = sleep_models_by_key.get((fid, analysis_date_val), [])
        nw_models = nonwear_models_by_key.get((fid, analysis_date_val))
        if nw_models is not None:
            # Has both NAP and nonwear data -- full annotation update
            background_tasks.add_task(
                _update_user_annotation,
                fid,
                analysis_date_val,
                username,
                nap_models,
                nw_models,
                None,
                "Imported from export (no sleep)",
                True,
                (fid, analysis_date_val) in consensus_dates_set,
            )
        else:
            # Sleep-only (NAPs or empty) -- preserve existing nonwear
            background_tasks.add_task(
                _patch_sleep_annotation,
                fid,
                analysis_date_val,
                username,
                nap_models,
                "Imported from export (no sleep)",
                True,
                (fid, analysis_date_val) in consensus_dates_set,
            )

    await db.commit()

    if unmatched_identifiers:
        errors.insert(0, f"No matching activity files for: {', '.join(sorted(unmatched_identifiers))}")
    if ambiguous_identifiers:
        errors.insert(0, f"Ambiguous file matches (use filename or timepoint): {', '.join(sorted(ambiguous_identifiers))}")

    return SleepImportResponse(
        dates_imported=dates_imported,
        markers_created=markers_created,
        nonwear_markers_created=nonwear_markers_created,
        no_sleep_dates=len(no_sleep_dates_set),
        dates_skipped=dates_skipped,
        errors=errors,
        total_rows=total_rows,
        matched_rows=matched_rows,
        unmatched_identifiers=sorted(unmatched_identifiers),
        ambiguous_identifiers=sorted(ambiguous_identifiers),
    )
