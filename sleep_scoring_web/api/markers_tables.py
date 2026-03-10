"""
Marker table endpoints for onset/offset data panels and full-table views.

Provides endpoints that return activity data around markers for tabular display.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select

from sleep_scoring_web.api.access import require_file_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.api.markers import naive_to_unix
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import Marker, RawActivityData
from sleep_scoring_web.schemas.enums import MarkerCategory
from sleep_scoring_web.services.file_identity import is_excluded_file_obj

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================


class OnsetOffsetDataPoint(BaseModel):
    """Single data point for onset/offset tables."""

    timestamp: float
    datetime_str: str
    axis_y: int
    vector_magnitude: int
    algorithm_result: int | None = None  # 0=wake, 1=sleep
    choi_result: int | None = None  # 0=wear, 1=nonwear
    is_nonwear: bool = False  # Manual nonwear marker overlap


class OnsetOffsetTableResponse(BaseModel):
    """Response with data points around a marker for tables."""

    onset_data: list[OnsetOffsetDataPoint] = Field(default_factory=list)
    offset_data: list[OnsetOffsetDataPoint] = Field(default_factory=list)
    period_index: int


class FullTableDataPoint(BaseModel):
    """Single data point for full 48h table."""

    timestamp: float
    datetime_str: str
    axis_y: int
    vector_magnitude: int
    algorithm_result: int | None = None
    choi_result: int | None = None
    is_nonwear: bool = False


class FullTableResponse(BaseModel):
    """Response with full 48h of data for popout table."""

    data: list[FullTableDataPoint] = Field(default_factory=list)
    total_rows: int = 0
    start_time: str | None = None
    end_time: str | None = None


# =============================================================================
# Data Tables Endpoint (for onset/offset panels)
# =============================================================================


@router.get("/{file_id}/{analysis_date}/table/{period_index}")
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

    # Get data around onset (use UTC to match stored timestamps)
    onset_dt = datetime.utcfromtimestamp(onset_timestamp)
    onset_start = onset_dt - timedelta(minutes=window_minutes)
    onset_end = onset_dt + timedelta(minutes=window_minutes)

    onset_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= onset_start,
                RawActivityData.timestamp <= onset_end,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    onset_rows = onset_result.scalars().all()

    # Get data around offset (use UTC to match stored timestamps)
    offset_dt = datetime.utcfromtimestamp(offset_timestamp)
    offset_start = offset_dt - timedelta(minutes=window_minutes)
    offset_end = offset_dt + timedelta(minutes=window_minutes)

    offset_result = await db.execute(
        select(RawActivityData)
        .where(
            and_(
                RawActivityData.file_id == file_id,
                RawActivityData.timestamp >= offset_start,
                RawActivityData.timestamp <= offset_end,
            )
        )
        .order_by(RawActivityData.timestamp)
    )
    offset_rows = offset_result.scalars().all()

    # Get ALL sensor nonwear markers for this file that overlap the table's time range.
    # Don't filter by analysis_date — sensor nonwear spans real timestamps and the
    # table window can cross date boundaries.
    if not onset_rows and not offset_rows:
        # No activity data in either window — skip sensor nonwear query
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
                    Marker.marker_category == MarkerCategory.NONWEAR,
                    Marker.marker_type == "sensor",
                    Marker.start_timestamp <= table_max_ts,
                    Marker.end_timestamp >= table_min_ts,
                )
            )
        )
        sensor_nw_markers = list(sensor_nw_result.scalars().all())

    def is_in_nonwear(ts: float) -> bool:
        """Check if timestamp falls within any sensor nonwear period."""
        for nw in sensor_nw_markers:
            if nw.start_timestamp and nw.end_timestamp:
                if nw.start_timestamp <= ts <= nw.end_timestamp:
                    return True
        return False

    # Run algorithms on the data ranges
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column

    choi_column = await get_choi_column(db, username)

    def compute_algorithm_results(rows: list[RawActivityData]) -> tuple[list[int], list[int]]:
        """Compute Sadeh and Choi results for a set of rows."""
        if not rows:
            return [], []

        axis_y_data = [row.axis_y or 0 for row in rows]

        # Sadeh algorithm
        sadeh = SadehAlgorithm()
        sleep_results = sadeh.score(axis_y_data)

        # Choi nonwear detection using user's preferred column
        choi = ChoiAlgorithm()
        choi_input = extract_choi_input(rows, choi_column)
        choi_results = choi.detect_mask(choi_input)

        return sleep_results, choi_results

    onset_sleep, onset_choi = compute_algorithm_results(onset_rows)
    offset_sleep, offset_choi = compute_algorithm_results(offset_rows)

    # Convert to response format with all columns
    onset_data = [
        OnsetOffsetDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=onset_sleep[i] if i < len(onset_sleep) else None,
            choi_result=onset_choi[i] if i < len(onset_choi) else None,
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
            choi_result=offset_choi[i] if i < len(offset_choi) else None,
            is_nonwear=is_in_nonwear(naive_to_unix(row.timestamp)),
        )
        for i, row in enumerate(offset_rows)
    ]

    return OnsetOffsetTableResponse(
        onset_data=onset_data,
        offset_data=offset_data,
        period_index=period_index,
    )


@router.get("/{file_id}/{analysis_date}/table-full")
async def get_full_table_data(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
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

    # Get 24h of data (noon to noon)
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
        return FullTableResponse(data=[], total_rows=0)

    # Get sensor nonwear markers (from diary/CSV upload) for the "N" column.
    # Query by timestamp overlap with the table's data range (not analysis_date)
    # so sensor nonwear always shows regardless of which date it was stored under.
    table_min_ts = naive_to_unix(rows[0].timestamp)
    table_max_ts = naive_to_unix(rows[-1].timestamp)
    sensor_nw_result = await db.execute(
        select(Marker).where(
            and_(
                Marker.file_id == file_id,
                Marker.marker_category == MarkerCategory.NONWEAR,
                Marker.marker_type == "sensor",
                Marker.start_timestamp <= table_max_ts,
                Marker.end_timestamp >= table_min_ts,
            )
        )
    )
    sensor_nw_markers = list(sensor_nw_result.scalars().all())

    def is_in_nonwear(ts: float) -> bool:
        """Check if timestamp falls within any sensor nonwear period."""
        for nw in sensor_nw_markers:
            if nw.start_timestamp and nw.end_timestamp:
                if nw.start_timestamp <= ts <= nw.end_timestamp:
                    return True
        return False

    # Run algorithms on full data
    from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm
    from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm
    from sleep_scoring_web.services.choi_helpers import extract_choi_input, get_choi_column

    axis_y_data = [row.axis_y or 0 for row in rows]

    sadeh = SadehAlgorithm()
    sleep_results = sadeh.score(axis_y_data)

    choi_column = await get_choi_column(db, username)
    choi = ChoiAlgorithm()
    choi_results = choi.detect_mask(extract_choi_input(rows, choi_column))

    # Convert to response format
    data = [
        FullTableDataPoint(
            timestamp=naive_to_unix(row.timestamp),
            datetime_str=row.timestamp.strftime("%H:%M"),
            axis_y=row.axis_y or 0,
            vector_magnitude=row.vector_magnitude or 0,
            algorithm_result=sleep_results[i] if i < len(sleep_results) else None,
            choi_result=choi_results[i] if i < len(choi_results) else None,
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
