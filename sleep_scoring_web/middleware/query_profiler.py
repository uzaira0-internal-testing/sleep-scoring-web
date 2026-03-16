"""
SQLAlchemy slow query logger.

Logs queries exceeding a configurable threshold (default 100ms).
Enable by setting SLOW_QUERY_THRESHOLD_MS environment variable.
Set to 0 to log all queries with timing.
"""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

from sqlalchemy import event

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

logger = logging.getLogger("slow_query")

_THRESHOLD_MS = float(os.environ.get("SLOW_QUERY_THRESHOLD_MS", "100"))
_ENABLED = os.environ.get("SLOW_QUERY_THRESHOLD_MS") is not None
_installed = False


def install_query_profiler(engine: Engine) -> None:
    """Attach before/after cursor execute events for query timing."""
    global _installed
    if not _ENABLED or _installed:
        return
    _installed = True

    logger.setLevel(logging.DEBUG)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(name)s] %(message)s"))
        logger.addHandler(handler)

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        conn.info["query_start_time"] = time.perf_counter()

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        start = conn.info.get("query_start_time")
        if start is None:
            return  # before_cursor_execute didn't fire for this query
        elapsed_ms = (time.perf_counter() - start) * 1000
        if elapsed_ms >= _THRESHOLD_MS:
            short_stmt = statement[:200].replace("\n", " ")
            logger.warning("SLOW QUERY (%.1fms): %s", elapsed_ms, short_stmt)
        elif _THRESHOLD_MS <= 0:
            short_stmt = statement[:200].replace("\n", " ")
            logger.debug("Query (%.1fms): %s", elapsed_ms, short_stmt)

    logger.info("Query profiler enabled (threshold: %.0fms)", _THRESHOLD_MS)
