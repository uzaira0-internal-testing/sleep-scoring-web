"""
Time window constants and helpers for the analysis pipeline.

Centralises the noon-to-noon analysis window logic used across all API
endpoints so that the magic numbers live in exactly one place.
"""

from datetime import date, datetime, timedelta

# ---------------------------------------------------------------------------
# Analysis window constants
# ---------------------------------------------------------------------------

ANALYSIS_NOON_OFFSET_HOURS: int = 12
"""Hours past midnight that marks the start of an analysis day (noon)."""

ANALYSIS_WINDOW_HOURS: int = 24
"""Duration of the standard analysis window (noon to noon)."""

ANALYSIS_CONTEXT_HOURS: int = 48
"""Duration of the extended context window used by Sadeh / Choi scoring."""

STALE_UPLOAD_TIMEOUT_HOURS: int = 24
"""Hours after which an UPLOADING file is considered stale."""

GZIP_MIN_SIZE_BYTES: int = 1000
"""Minimum response body size (bytes) before GZip middleware kicks in."""

BLAS_NUM_THREADS: str = "8"
"""Default thread count for BLAS / OpenMP (set via environment variables)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_analysis_window(analysis_date: date) -> tuple[datetime, datetime]:
    """
    Return the standard noon-to-noon window for *analysis_date*.

    Returns ``(start, end)`` where *start* is noon on the given date and
    *end* is noon the following day.
    """
    start = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=ANALYSIS_NOON_OFFSET_HOURS)
    end = start + timedelta(hours=ANALYSIS_WINDOW_HOURS)
    return start, end


def get_context_window(analysis_date: date) -> tuple[datetime, datetime]:
    """
    Return the 48-hour context window for algorithm scoring.

    Returns ``(start, end)`` where *start* is the previous day's noon
    (12 h before the analysis window) and *end* is 48 h later.
    This matches the original pattern: midnight - 12h to midnight + 36h.
    """
    midnight = datetime.combine(analysis_date, datetime.min.time())
    start = midnight - timedelta(hours=ANALYSIS_NOON_OFFSET_HOURS)
    end = start + timedelta(hours=ANALYSIS_CONTEXT_HOURS)
    return start, end
