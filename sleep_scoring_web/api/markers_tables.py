"""
Marker table endpoints for onset/offset data panels and full-table views.

Provides endpoints that return activity data around markers for tabular display.
"""

import logging
from bisect import bisect_right
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import and_, select

from sleep_scoring_web.api.access import require_file_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.constants import get_analysis_window, get_context_window
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import Marker, RawActivityData
from sleep_scoring_web.schemas.enums import AlgorithmType, MarkerCategory
from sleep_scoring_web.schemas.models import (
    FullTableColumnar,
    FullTableDataPoint,
    FullTableResponse,
    OnsetOffsetColumnar,
    OnsetOffsetColumnarResponse,
    OnsetOffsetDataPoint,
    OnsetOffsetTableResponse,
)
from sleep_scoring_web.services.algorithms import ALGORITHM_TYPES, create_algorithm
from sleep_scoring_web.services.file_identity import is_excluded_file_obj
from sleep_scoring_web.utils import ensure_seconds, naive_to_unix

logger = logging.getLogger(__name__)

router = APIRouter()


def _build_nonwear_checker(sensor_nw_markers: list[Marker]) -> Callable[[float], bool]:
    """
    Build an efficient nonwear lookup from sensor nonwear intervals.

    Merges overlapping intervals then uses bisect for O(log n) per-timestamp lookup.
    """
    raw = sorted(
        (nw.start_timestamp, nw.end_timestamp) for nw in sensor_nw_markers if nw.start_timestamp is not None and nw.end_timestamp is not None
    )
    if not raw:
        return lambda _ts: False

    # Merge overlapping/adjacent intervals so bisect is correct
    merged: list[tuple[float, float]] = [raw[0]]
    for start, end in raw[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))

    starts = [s for s, _ in merged]
    ends = [e for _, e in merged]

    def is_in_nonwear(ts: float) -> bool:
        idx = bisect_right(starts, ts) - 1
        return idx >= 0 and ts <= ends[idx]

    return is_in_nonwear


# =============================================================================
# Data Tables Endpoint (for onset/offset panels)
# =============================================================================


@router.get("/{file_id}/{analysis_date}/table/{period_index}", response_model=OnsetOffsetTableResponse)
async def get_onset_offset_data(
    file_id: int,
    analysis_date: date,
    period_index: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    window_minutes: Annotated[int, Query(ge=5, le=120)] = 100,
    onset_ts: Annotated[float | None, Query(description="Onset timestamp in seconds (use instead of DB lookup)")] = None,
    offset_ts: Annotated[float | None, Query(description="Offset timestamp in seconds (use instead of DB lookup)")] = None,
    algorithm: Annotated[str, Query(description="Sleep scoring algorithm")] = AlgorithmType.get_default(),
) -> OnsetOffsetTableResponse:
    """
    Get activity data around a marker for onset/offset tables.

    Returns data points within window_minutes of the onset and offset timestamps.
    Accepts optional onset_ts/offset_ts query params to use client-side timestamps
    instead of requiring a saved marker in the database.
    """
    await require_file_access(db, username, file_id)

    # Determine onset/offset timestamps - prefer query params, fall back to DB
    onset_timestamp: float | None = onset_ts
    offset_timestamp: float | None = offset_ts

    if onset_timestamp is None or offset_timestamp is None:
        # Fall back to THIS user's saved marker lookup.
        marker_result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.analysis_date == analysis_date,
                    Marker.period_index == period_index,
                    Marker.marker_category == MarkerCategory.SLEEP,
                    Marker.created_by == username,
                )
            )
        )
        marker = marker_result.scalar_one_or_none()
        if marker is None:
            legacy_marker_result = await db.execute(
                select(Marker).where(
                    and_(
                        Marker.file_id == file_id,
                        Marker.analysis_date == analysis_date,
                        Marker.period_index == period_index,
                        Marker.marker_category == MarkerCategory.SLEEP,
                        Marker.created_by.is_(None),
                    )
                )
            )
            marker = legacy_marker_result.scalar_one_or_none()

        if not marker:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Marker not found")

        onset_timestamp = marker.start_timestamp
        offset_timestamp = marker.end_timestamp

    if onset_timestamp is None or offset_timestamp is None:
        return OnsetOffsetTableResponse(onset_data=[], offset_data=[], period_index=period_index)

    # Normalize ms → seconds (frontend historically sent ms)
    onset_timestamp = ensure_seconds(onset_timestamp)
    offset_timestamp = ensure_seconds(offset_timestamp)

    # Strip tzinfo — raw_activity_data uses "timestamp without time zone" and
    # asyncpg rejects tz-aware comparisons.
    onset_dt = datetime.fromtimestamp(onset_timestamp, tz=UTC).replace(tzinfo=None)
    onset_start = onset_dt - timedelta(minutes=window_minutes)
    onset_end = onset_dt + timedelta(minutes=window_minutes)

    offset_dt = datetime.fromtimestamp(offset_timestamp, tz=UTC).replace(tzinfo=None)
    offset_start = offset_dt - timedelta(minutes=window_minutes)
    offset_end = offset_dt + timedelta(minutes=window_minutes)

    # Single wide query covering 48h Sadeh context + onset/offset windows + Choi context.
    # Eliminates 3 redundant queries (onset, offset, choi each loaded overlapping subsets).
    day_start, day_end = get_context_window(analysis_date)
    context_start = min(day_start, onset_start, offset_start)
    context_end = max(day_end, onset_end, offset_end)

    context_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= context_start,
                RawActivityData.timestamp < context_end,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    context_rows = context_result.scalars().all()

    # Partition display rows from the superset
    onset_rows = [r for r in context_rows if onset_start <= r.timestamp <= onset_end]
    offset_rows = [r for r in context_rows if offset_start <= r.timestamp <= offset_end]

    # Sensor nonwear markers for the "N" column
    if not onset_rows and not offset_rows:
        sensor_nw_markers = []
    else:
        table_min_ts = min(
            naive_to_unix(onset_rows[0].timestamp) if onset_rows else naive_to_unix(offset_rows[0].timestamp),
            naive_to_unix(offset_rows[0].timestamp) if offset_rows else naive_to_unix(onset_rows[0].timestamp),
        )
        table_max_ts = max(
            naive_to_unix(onset_rows[-1].timestamp) if onset_rows else naive_to_unix(offset_rows[-1].timestamp),
            naive_to_unix(offset_rows[-1].timestamp) if offset_rows else naive_to_unix(onset_rows[-1].timestamp),
        )
        sensor_nw_result = await db.execute(
            select(Marker).where(
                and_(
                    Marker.file_id == file_id,
                    Marker.sensor_nonwear_filter(),
                    Marker.start_timestamp <= table_max_ts,
                    Marker.end_timestamp >= table_min_ts,
                )
            )
        )
        sensor_nw_markers = list(sensor_nw_result.scalars().all())

    is_in_nonwear = _build_nonwear_checker(sensor_nw_markers)

    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column

    if algorithm not in ALGORITHM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown algorithm: {algorithm}. Available: {ALGORITHM_TYPES}",
        )

    choi_column = await get_choi_column(db, username)
    scorer = create_algorithm(algorithm)

    # Score Sadeh + Choi on the full context so boundary epochs get real neighbours
    sadeh_results = scorer.score([row.axis_y or 0 for row in context_rows])
    sadeh_by_timestamp: dict[datetime, int] = {row.timestamp: sadeh_results[i] for i, row in enumerate(context_rows) if i < len(sadeh_results)}
    onset_sleep = [sadeh_by_timestamp.get(row.timestamp) for row in onset_rows]
    offset_sleep = [sadeh_by_timestamp.get(row.timestamp) for row in offset_rows]

    choi_results_list = ChoiAlgorithm().detect_mask(extract_choi_input(context_rows, choi_column))
    choi_by_timestamp: dict[datetime, int] = {row.timestamp: choi_results_list[i] for i, row in enumerate(context_rows) if i < len(choi_results_list)}

    # Convert to response format with all columns
    onset_data = [
        OnsetOffsetDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=onset_sleep[i] if i < len(onset_sleep) else None,
            choi_result=choi_by_timestamp.get(row.timestamp),
            is_nonwear=is_in_nonwear(naive_to_unix(row.timestamp)),
        )
        for i, row in enumerate(onset_rows)
    ]

    offset_data = [
        OnsetOffsetDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=offset_sleep[i] if i < len(offset_sleep) else None,
            choi_result=choi_by_timestamp.get(row.timestamp),
            is_nonwear=is_in_nonwear(naive_to_unix(row.timestamp)),
        )
        for i, row in enumerate(offset_rows)
    ]

    return OnsetOffsetTableResponse(
        onset_data=onset_data,
        offset_data=offset_data,
        period_index=period_index,
    )


def _points_to_columnar(points: list[OnsetOffsetDataPoint]) -> OnsetOffsetColumnar:
    """Convert row-based data points to columnar format."""
    return OnsetOffsetColumnar(
        timestamps=[p.timestamp for p in points],
        axis_y=[p.axis_y for p in points],
        vector_magnitude=[p.vector_magnitude for p in points],
        algorithm_result=[p.algorithm_result for p in points],
        choi_result=[p.choi_result for p in points],
        is_nonwear=[p.is_nonwear for p in points],
    )


@router.get("/{file_id}/{analysis_date}/table/{period_index}/columnar", response_model=OnsetOffsetColumnarResponse)
async def get_onset_offset_data_columnar(
    file_id: int,
    analysis_date: date,
    period_index: int,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    window_minutes: Annotated[int, Query(ge=5, le=120)] = 100,
    onset_ts: Annotated[float | None, Query(description="Onset timestamp in seconds")] = None,
    offset_ts: Annotated[float | None, Query(description="Offset timestamp in seconds")] = None,
    algorithm: Annotated[str, Query(description="Sleep scoring algorithm")] = AlgorithmType.get_default(),
) -> OnsetOffsetColumnarResponse:
    """
    Get activity data around a marker in columnar format (smaller payload).

    Delegates to the row-based endpoint and converts the result.
    """
    row_response = await get_onset_offset_data(
        file_id,
        analysis_date,
        period_index,
        db,
        _,
        username,
        window_minutes,
        onset_ts,
        offset_ts,
        algorithm,
    )
    return OnsetOffsetColumnarResponse(
        onset_data=_points_to_columnar(row_response.onset_data),
        offset_data=_points_to_columnar(row_response.offset_data),
        period_index=row_response.period_index,
    )


@router.get("/{file_id}/{analysis_date}/table-full", response_model=FullTableResponse)
async def get_full_table_data(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    algorithm: Annotated[str, Query(description="Sleep scoring algorithm")] = AlgorithmType.get_default(),
) -> FullTableResponse:
    """
    Get full 48h of activity data for popout table display.

    Returns all epochs from noon of analysis_date to noon of next day.
    Includes algorithm results and nonwear detection.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    file_result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = file_result.scalar_one_or_none()

    if not file or is_excluded_file_obj(file):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Single query: 48h context (noon-12h to noon+36h) covers 24h display + algorithm context
    start_time, end_time = get_analysis_window(analysis_date)
    context_start, context_end = get_context_window(analysis_date)

    context_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= context_start,
                RawActivityData.timestamp < context_end,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    context_rows = context_result.scalars().all()

    # Display rows: 24h subset (noon to noon)
    rows = [r for r in context_rows if start_time <= r.timestamp < end_time]

    if not rows:
        return FullTableResponse(data=[], total_rows=0)

    # Sensor nonwear markers for the "N" column
    table_min_ts = naive_to_unix(rows[0].timestamp)
    table_max_ts = naive_to_unix(rows[-1].timestamp)
    sensor_nw_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.sensor_nonwear_filter(),
                Marker.start_timestamp <= table_max_ts,
                Marker.end_timestamp >= table_min_ts,
            )
        )
    )
    sensor_nw_markers = list(sensor_nw_result.scalars().all())

    is_in_nonwear = _build_nonwear_checker(sensor_nw_markers)

    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column

    if algorithm not in ALGORITHM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown algorithm: {algorithm}. Available: {ALGORITHM_TYPES}",
        )

    # Score Sadeh + Choi on full 48h context so boundary epochs get real neighbours
    scorer = create_algorithm(algorithm)
    sadeh_context = scorer.score([r.axis_y or 0 for r in context_rows])
    sadeh_by_ts: dict[datetime, int] = {r.timestamp: sadeh_context[i] for i, r in enumerate(context_rows) if i < len(sadeh_context)}

    choi_column = await get_choi_column(db, username)
    choi = ChoiAlgorithm()
    choi_context = choi.detect_mask(extract_choi_input(context_rows, choi_column))
    choi_by_ts: dict[datetime, int] = {r.timestamp: choi_context[i] for i, r in enumerate(context_rows) if i < len(choi_context)}

    # Convert to response format (display rows stay 24h)
    data = [
        FullTableDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=sadeh_by_ts.get(row.timestamp),
            choi_result=choi_by_ts.get(row.timestamp),
            is_nonwear=is_in_nonwear(naive_to_unix(row.timestamp)),
        )
        for i, row in enumerate(rows)
    ]

    return FullTableResponse(
        data=data,
        total_rows=len(data),
        start_time=rows[0].timestamp.strftime("%Y-%m-%d %H:%M:%S") if rows else None,
        end_time=rows[-1].timestamp.strftime("%Y-%m-%d %H:%M:%S") if rows else None,
    )


@router.get("/{file_id}/{analysis_date}/table-full/columnar", response_model=FullTableColumnar)
async def get_full_table_data_columnar(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    algorithm: Annotated[str, Query(description="Sleep scoring algorithm")] = AlgorithmType.get_default(),
) -> FullTableColumnar:
    """
    Get full 24h of activity data in columnar format (smaller payload).

    Delegates to the row-based endpoint and converts the result.
    Frontend derives HH:MM from timestamps (datetime_str dropped).
    """
    row_response = await get_full_table_data(file_id, analysis_date, db, _, username, algorithm)
    points = row_response.data

    return FullTableColumnar(
        timestamps=[p.timestamp for p in points],
        axis_y=[p.axis_y for p in points],
        vector_magnitude=[p.vector_magnitude for p in points],
        algorithm_result=[p.algorithm_result for p in points],
        choi_result=[p.choi_result for p in points],
        is_nonwear=[p.is_nonwear for p in points],
        total_rows=row_response.total_rows,
        start_time=row_response.start_time,
        end_time=row_response.end_time,
    )
