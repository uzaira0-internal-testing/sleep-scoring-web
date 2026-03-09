"""In-memory processing progress tracker for background file processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ProcessingProgress:
    """Track background file processing progress."""

    file_id: int
    status: str = "processing"
    phase: str = ""  # "decompressing" / "reading_csv" / "converting_counts" / "inserting_db"
    percent: float = 0.0
    rows_processed: int = 0
    total_rows_estimate: int | None = None
    error: str | None = None
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)


# Module-level dict (mirrors ScanStatus pattern in files.py)
_processing_status: dict[int, ProcessingProgress] = {}


def start_tracking(file_id: int) -> ProcessingProgress:
    """Start tracking processing for a file."""
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
