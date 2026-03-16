"""
Convert REDCap wide-format sleep diary exports to long format.

REDCap exports GNSM sleep diaries as one row per participant with 20 study days
spread across 107-column blocks (suffixed _v1 through _v20). This module pivots
that into one row per participant-day so the existing diary importers can handle it.

Pure functions — no database, no Qt, no FastAPI dependencies.
"""

from __future__ import annotations

import logging

import polars as pl

logger = logging.getLogger(__name__)

# Nonwear reason code → text mapping (matches diary.py _NONWEAR_REASON_CODES)
_NONWEAR_REASON_CODES: dict[str, str] = {
    "1": "Bath/Shower",
    "1.0": "Bath/Shower",
    "2": "Swimming",
    "2.0": "Swimming",
    "3": "Other",
    "3.0": "Other",
}

# Maximum number of study days in REDCap wide format
_MAX_DAYS = 20

# Schema for the output DataFrame (all string columns)
_OUTPUT_SCHEMA = {
    "participant_id": pl.Utf8,
    "startdate": pl.Utf8,
    "in_bed_time": pl.Utf8,
    "sleep_onset_time": pl.Utf8,
    "sleep_offset_time": pl.Utf8,
    "napstart_1_time": pl.Utf8,
    "napend_1_time": pl.Utf8,
    "nap_onset_time_2": pl.Utf8,
    "nap_offset_time_2": pl.Utf8,
    "nap_onset_time_3": pl.Utf8,
    "nap_offset_time_3": pl.Utf8,
    "nonwear_start_time": pl.Utf8,
    "nonwear_end_time": pl.Utf8,
    "nonwear_reason": pl.Utf8,
    "nonwear_start_time_2": pl.Utf8,
    "nonwear_end_time_2": pl.Utf8,
    "nonwear_reason_2": pl.Utf8,
    "nonwear_start_time_3": pl.Utf8,
    "nonwear_end_time_3": pl.Utf8,
    "nonwear_reason_3": pl.Utf8,
}


def is_redcap_wide_format(columns: list[str]) -> bool:
    """Detect REDCap wide format by checking for signature day-1 columns."""
    lower = {c.lower().strip() for c in columns}
    return {"id_v1", "date_lastnight_v1", "inbed_hour_v1"}.issubset(lower)


def convert_redcap_wide_to_long(df: pl.DataFrame) -> pl.DataFrame:
    """
    Pivot REDCap wide diary into long format matching existing importer expectations.

    Each input row = one participant with up to 20 study days in 107-column blocks.
    Each output row = one participant-day with standard column names that match
    ``_DESKTOP_COLUMN_ALIASES`` in ``diary.py``.
    """
    # Lowercase all column names for consistent access
    df = df.rename({c: c.lower().strip() for c in df.columns})
    col_set = set(df.columns)

    records: list[dict[str, str | None]] = []

    for row_idx in range(df.height):
        row = df.row(row_idx, named=True)

        for day in range(1, _MAX_DAYS + 1):
            v = f"_v{day}"

            # Skip days without a date
            date_val = _safe_str(row, f"date_lastnight{v}", col_set)
            if not date_val:
                continue

            pid = _safe_str(row, f"id{v}", col_set)
            if not pid:
                continue

            record: dict[str, str | None] = {
                "participant_id": pid,
                "startdate": date_val,
                # Sleep times
                "in_bed_time": _combine_time(row, f"inbed_hour{v}", f"inbed_min{v}", f"time_ampm{v}", col_set),
                "sleep_onset_time": _combine_time(row, f"asleep_hour{v}", f"asleep_min{v}", f"time_ampm_2{v}", col_set),
                "sleep_offset_time": _combine_time(row, f"wake_hour{v}", f"wake_min{v}", f"time_ampm_3{v}", col_set),
                # Nap 1
                "napstart_1_time": _combine_time(row, f"napstart_hour_1{v}", f"napstart_min_1{v}", f"time_ampm_10{v}", col_set),
                "napend_1_time": _combine_time(row, f"napend_hour_1{v}", f"napend_min_1{v}", f"time_ampm_13{v}", col_set),
                # Nap 2
                "nap_onset_time_2": _combine_time(row, f"napstart_hour_2{v}", f"napstart_min_2{v}", f"time_ampm_11{v}", col_set),
                "nap_offset_time_2": _combine_time(row, f"napend_hour_2{v}", f"napend_min_2{v}", f"time_ampm_14{v}", col_set),
                # Nap 3
                "nap_onset_time_3": _combine_time(row, f"napstart_hour_3{v}", f"napstart_min_3{v}", f"time_ampm_12{v}", col_set),
                "nap_offset_time_3": _combine_time(row, f"napend_hour_3{v}", f"napend_min_3{v}", f"time_ampm_15{v}", col_set),
                # Nonwear 1
                "nonwear_start_time": _combine_time(row, f"takeoffstart_hour_1{v}", f"takeoffstart_min_1{v}", f"time_ampm_16{v}", col_set),
                "nonwear_end_time": _combine_time(row, f"takeoffend_hour_1{v}", f"takeoffend_min_1{v}", f"time_ampm_17{v}", col_set),
                "nonwear_reason": _convert_reason(row, f"why_timeoff_1{v}", col_set),
                # Nonwear 2
                "nonwear_start_time_2": _combine_time(row, f"takeoffstart_hour_2{v}", f"takeoffstart_min_2{v}", f"time_ampm_18{v}", col_set),
                "nonwear_end_time_2": _combine_time(row, f"takeoffend_hour_2{v}", f"takeoffend_min_2{v}", f"time_ampm_19{v}", col_set),
                "nonwear_reason_2": _convert_reason(row, f"why_timeoff_2{v}", col_set),
                # Nonwear 3
                "nonwear_start_time_3": _combine_time(row, f"takeoffstart_hour_3{v}", f"takeoffstart_min_3{v}", f"time_ampm_20{v}", col_set),
                "nonwear_end_time_3": _combine_time(row, f"takeoffend_hour_3{v}", f"takeoffend_min_3{v}", f"time_ampm_21{v}", col_set),
                "nonwear_reason_3": _convert_reason(row, f"why_timeoff_3{v}", col_set),
            }

            records.append(record)

    if not records:
        return pl.DataFrame(schema=_OUTPUT_SCHEMA)

    logger.info(
        "Converted REDCap wide format: %d participant-days from %d rows",
        len(records),
        df.height,
    )
    return pl.DataFrame(records, schema=_OUTPUT_SCHEMA)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _safe_str(row: dict, col: str, col_set: set[str]) -> str | None:
    """Get a string value from a row, returning None for missing/empty values."""
    if col not in col_set:
        return None
    val = row.get(col)
    if val is None:
        return None
    s = str(val).strip()
    if s.lower() in ("", "nan", "none", "null"):
        return None
    return s


def _safe_num(row: dict, col: str, col_set: set[str]) -> int | None:
    """Get an integer value from a row, returning None for missing/empty."""
    s = _safe_str(row, col, col_set)
    if s is None:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _combine_time(
    row: dict,
    hour_col: str,
    min_col: str,
    ampm_col: str,
    col_set: set[str],
) -> str | None:
    """
    Combine hour/minute/ampm fields into HH:MM (24h) string.

    AM/PM codes: 1=AM, 2=PM.
    """
    hour = _safe_num(row, hour_col, col_set)
    minute = _safe_num(row, min_col, col_set)
    ampm = _safe_num(row, ampm_col, col_set)

    if hour is None or minute is None or ampm is None:
        return None

    # Convert 12h to 24h
    if ampm == 1:  # AM
        if hour == 12:
            hour = 0
    elif ampm == 2:  # PM
        if hour != 12:
            hour += 12

    return f"{hour:02d}:{minute:02d}"


def _convert_reason(row: dict, col: str, col_set: set[str]) -> str | None:
    """Convert nonwear reason code to text."""
    s = _safe_str(row, col, col_set)
    if s is None:
        return None
    return _NONWEAR_REASON_CODES.get(s, s)
