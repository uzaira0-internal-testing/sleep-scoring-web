"""In-memory processing progress tracker for background file processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sleep_scoring_web.schemas.enums import FileStatus

_MAX_ENTRIES = 100
_STALE_THRESHOLD = timedelta(hours=1)


@dataclass
class ProcessingProgress:
    """Track background file processing progress."""

    file_id: int
    status: str = FileStatus.PROCESSING
    phase: str = ""  # "decompressing" / "reading_csv" / "converting_counts" / "inserting_db"
    percent: float = 0.0
    rows_processed: int = 0
    total_rows_estimate: int | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# Module-level dict (mirrors ScanStatus pattern in files.py)
_processing_status: dict[int, ProcessingProgress] = {}


def _evict_stale_entries() -> None:
    """Remove entries older than 1 hour and cap at _MAX_ENTRIES most recent."""
    now = datetime.now()
    # Remove entries older than the stale threshold
    stale_ids = [fid for fid, p in _processing_status.items() if now - p.updated_at > _STALE_THRESHOLD]
    for fid in stale_ids:
        del _processing_status[fid]

    # If still over the cap, keep only the most recent entries
    if len(_processing_status) > _MAX_ENTRIES:
        sorted_entries = sorted(
            _processing_status.items(),
            key=lambda item: item[1].updated_at,
            reverse=True,
        )
        _processing_status.clear()
        for fid, progress in sorted_entries[:_MAX_ENTRIES]:
            _processing_status[fid] = progress


def start_tracking(file_id: int) -> ProcessingProgress:
    """Start tracking processing for a file."""
    _evict_stale_entries()
    progress = ProcessingProgress(file_id=file_id)
    _processing_status[file_id] = progress
    return progress


def update_progress(
    file_id: int,
    *,
    phase: str | None = None,
    percent: float | None = None,
    rows_processed: int | None = None,
    total_rows_estimate: int | None = None,
    error: str | None = None,
    status: str | None = None,
) -> None:
    """Update processing progress for a file."""
    progress = _processing_status.get(file_id)
    if progress is None:
        return
    if phase is not None:
        progress.phase = phase
    if percent is not None:
        progress.percent = percent
    if rows_processed is not None:
        progress.rows_processed = rows_processed
    if total_rows_estimate is not None:
        progress.total_rows_estimate = total_rows_estimate
    if error is not None:
        progress.error = error
    if status is not None:
        progress.status = status
    progress.updated_at = datetime.now()


def get_progress(file_id: int) -> ProcessingProgress | None:
    """Get processing progress for a file."""
    return _processing_status.get(file_id)


def clear_tracking(file_id: int) -> None:
    """Remove tracking for a file (after completion)."""
    _processing_status.pop(file_id, None)
