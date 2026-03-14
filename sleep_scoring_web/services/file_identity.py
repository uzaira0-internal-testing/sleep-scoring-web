"""
File identity helpers for deterministic cross-file matching.

These utilities normalize participant identifiers, timepoints, and filenames
so diary/nonwear/sleep imports can match rows to activity files without
silently picking the wrong file when multiple candidates exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

_NULL_TOKENS = {"", "nan", "none", "null", "nat"}
_EXCLUDED_FILENAME_PATTERN = re.compile(r"(?i)(ignore|issue)")


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in _NULL_TOKENS:
        return None
    return text


def normalize_participant_id(value: Any) -> str | None:
    """
    Normalize participant identifiers for matching.

    - trims whitespace
    - collapses internal whitespace
    - converts integer-like floats (e.g. "1001.0") to "1001"
    - lowercases for case-insensitive matching
    """
    text = _clean_text(value)
    if text is None:
        return None
    text = re.sub(r"\s+", " ", text)
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    return text.lower()


def normalize_timepoint(value: Any) -> str | None:
    """Normalize timepoint strings to canonical form (e.g. "t1", "T 1" -> "t1")."""
    text = _clean_text(value)
    if text is None:
        return None
    compact = re.sub(r"\s+", "", text).upper()
    match = re.fullmatch(r"T(\d+)", compact)
    if match:
        return f"t{int(match.group(1))}"
    return compact.lower()


def normalize_filename(value: Any) -> str | None:
    """
    Normalize a filename for case-insensitive matching.

    Uses basename only so accidental path prefixes in CSV rows do not matter.
    """
    text = _clean_text(value)
    if text is None:
        return None
    return PurePath(text).name.lower()


def filename_stem(value: Any) -> str | None:
    """Return lowercase filename stem (basename without extension)."""
    normalized = normalize_filename(value)
    if normalized is None:
        return None
    return PurePath(normalized).stem.lower()


def is_excluded_activity_filename(value: Any) -> bool:
    """
    Return True when the filename should be excluded from scoring workflows.

    Current exclusion rule: any filename containing IGNORE or ISSUE.
    """
    normalized = normalize_filename(value)
    if not normalized:
        return False
    stem = filename_stem(normalized) or normalized
    return _EXCLUDED_FILENAME_PATTERN.search(stem) is not None


def is_excluded_file_obj(file_obj: Any) -> bool:
    """Convenience wrapper for DB file rows."""
    return is_excluded_activity_filename(getattr(file_obj, "filename", ""))


def infer_participant_id_and_timepoint_from_filename(filename: str) -> tuple[str | None, str | None]:
    """
    Best-effort extraction of participant_id and timepoint from activity filename.

    Examples:
    - "1000 T1 G1 (2024-01-01)60sec.csv" -> ("1000", "T1")
    - "P1-1036-A-T2 (2023-07-18)60sec.csv" -> ("P1-1036-A", "T2")
    - "DEMO-001.csv" -> ("DEMO-001", None)

    """
    stem = PurePath(filename).stem.strip()
    if not stem:
        return None, None

    # Drop trailing "(...)" date block if present.
    base = re.split(r"\s*\(", stem, maxsplit=1)[0].strip()

    # Detect Tn token with common separators.
    tp_match = re.search(r"(?i)(?:^|[-_\s])(?P<tp>T\d{1,2})(?=$|[-_\s(])", base)
    if tp_match:
        tp = tp_match.group("tp").upper()
        pid_raw = base[:tp_match.start()].rstrip(" -_")
        pid_norm = normalize_participant_id(pid_raw)
        pid = pid_raw if pid_norm is not None else None
        return pid, tp

    # No explicit timepoint token. Use the leading token as participant id.
    first_token = base.split()[0] if base else ""
    first_token = re.sub(r"(?i)[-_]?T\d{1,2}$", "", first_token).rstrip("-_")
    pid_norm = normalize_participant_id(first_token)
    pid = first_token if pid_norm is not None else None
    return pid, None


def _strip_site_suffix(pid: str | None) -> str | None:
    """
    Strip trailing single-letter site/arm suffix (e.g. 'P1-1036-A' -> 'P1-1036').

    Handles patterns like ``-A``, ``-B`` at the end of a PID where the suffix
    is a single letter preceded by a separator.  Returns *None* when the input
    is already None or when stripping would produce an empty string.
    """
    if not pid:
        return None
    stripped = re.sub(r"[-_][A-Za-z]$", "", pid)
    return normalize_participant_id(stripped) if stripped else None


def _strip_rewear_suffix(pid: str | None) -> str | None:
    """
    Strip RA/Rewear suffixes from PID (e.g. 'P3-3035 RA 1' -> 'P3-3035').

    Handles patterns like ``RA``, ``RA 1``, ``RA 2``, ``Rewear`` that indicate
    a re-application of the actigraph for the same participant.
    """
    if not pid:
        return None
    stripped = re.sub(r"(?i)\s+(?:ra\s*\d*|rewear)\s*$", "", pid).strip()
    return normalize_participant_id(stripped) if stripped else None


@dataclass(frozen=True)
class FileIdentity:
    """Normalized lookup data for one file record."""

    file: Any
    normalized_filename: str
    normalized_stem: str
    participant_id_norm: str | None
    short_pid_norm: str | None  # PID without site/arm suffix (e.g. "p1-1036" from "p1-1036-a")
    timepoint_norm: str | None


def build_file_identity(file_obj: Any) -> FileIdentity:
    """Build normalized identity metadata for one DB file row."""
    normalized_name = normalize_filename(getattr(file_obj, "filename", "")) or ""
    normalized_stem = filename_stem(normalized_name) or ""

    explicit_pid_norm = normalize_participant_id(getattr(file_obj, "participant_id", None))
    inferred_pid_raw, inferred_tp_raw = infer_participant_id_and_timepoint_from_filename(
        getattr(file_obj, "filename", "")
    )
    inferred_pid_norm = normalize_participant_id(inferred_pid_raw)
    inferred_tp_norm = normalize_timepoint(inferred_tp_raw)

    pid_norm = explicit_pid_norm or inferred_pid_norm
    # Build short_pid by stripping site suffix (-A) and rewear suffix (RA/Rewear)
    short_pid = _strip_site_suffix(pid_norm)
    # Also try stripping rewear from both the full and site-stripped forms
    short_pid_rw = _strip_rewear_suffix(short_pid) or _strip_rewear_suffix(pid_norm)
    # Use the most stripped form that differs from pid_norm
    best_short = short_pid_rw if (short_pid_rw and short_pid_rw != pid_norm) else short_pid

    return FileIdentity(
        file=file_obj,
        normalized_filename=normalized_name,
        normalized_stem=normalized_stem,
        participant_id_norm=pid_norm,
        short_pid_norm=best_short if best_short != pid_norm else None,
        timepoint_norm=inferred_tp_norm,
    )
