"""
Activity data API endpoints.

Provides endpoints for retrieving activity data in columnar format.

Note: We intentionally avoid `from __future__ import annotations` here
because FastAPI's dependency injection needs actual types, not string
annotations. Using Annotated types requires runtime resolution.
"""

import hashlib
from datetime import date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from sqlalchemy import and_, distinct, func, select

from sleep_scoring_web.api.access import require_file_access, require_file_and_access
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import RawActivityData
from sleep_scoring_web.schemas import ActivityDataColumnar, ActivityDataResponse
from sleep_scoring_web.schemas.enums import AlgorithmType
from sleep_scoring_web.schemas.models import SensorNonwearPeriod
from sleep_scoring_web.utils import naive_to_unix

router = APIRouter()


@router.get("/{file_id}/{analysis_date}")
async def get_activity_data(
    file_id: int,
    analysis_date: date,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    view_hours: Annotated[int, Query(ge=12, le=48, description="Hours of data to return (12-48)")] = 24,
) -> ActivityDataResponse:
    """
    Get activity data for a specific file and date.

    Returns data in columnar format for efficient transfer.
    The view window starts from analysis_date at 12:00 (noon) and extends for view_hours.
    """
    await require_file_access(db, username, file_id)

    # Verify file exists
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = result.scalar_one_or_none()

    if not file:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Calculate time window based on view mode (matches desktop app logic):
    # - 24hr view: noon-to-noon (12:00 PM current day to 12:00 PM next day)
    # - 48hr view: midnight-to-midnight (00:00 current day to 00:00 two days later)
    if view_hours == 48:
        # 48hr view: midnight to midnight+48h
        start_time = datetime.combine(analysis_date, datetime.min.time())
        end_time = start_time + timedelta(hours=48)
    else:
        # 24hr view: noon to noon
        start_time = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
        end_time = start_time + timedelta(hours=24)

    # Query activity data within time window
    result = await db.execute(
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
    activity_rows = result.scalars().all()

    # Convert to columnar format
    timestamps: list[float] = []
    axis_x: list[float] = []
    axis_y: list[float] = []
    axis_z: list[float] = []
    vector_magnitude: list[float] = []

    for row in activity_rows:
        timestamps.append(naive_to_unix(row.timestamp))
        axis_x.append(row.axis_x or 0)
        axis_y.append(row.axis_y or 0)
        axis_z.append(row.axis_z or 0)
        vector_magnitude.append(row.vector_magnitude or 0)

    columnar_data = ActivityDataColumnar(
        timestamps=timestamps,
        axis_x=axis_x,
        axis_y=axis_y,
        axis_z=axis_z,
        vector_magnitude=vector_magnitude,
    )

    # Get available dates for navigation
    dates_result = await db.execute(
        select(distinct(func.date(RawActivityData.timestamp)))
        .where(RawActivityData.file_id == file_id)
        .order_by(func.date(RawActivityData.timestamp))
    )
    available_dates = [str(d) for d in dates_result.scalars().all()]

    # Find current date index
    current_date_str = str(analysis_date)
    current_date_index = available_dates.index(current_date_str) if current_date_str in available_dates else 0

    return ActivityDataResponse(
        data=columnar_data,
        available_dates=available_dates,
        current_date_index=current_date_index,
        file_id=file_id,
        analysis_date=str(analysis_date),
        view_start=naive_to_unix(start_time),
        view_end=naive_to_unix(end_time),
    )


@router.get(
    "/{file_id}/{analysis_date}/score",
    response_model_exclude_none=True,
)
async def get_activity_data_with_scoring(
    file_id: int,
    analysis_date: date,
    request: Request,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    view_hours: Annotated[int, Query(ge=12, le=48)] = 24,
    algorithm: Annotated[str, Query(description="Sleep scoring algorithm to use")] = AlgorithmType.get_default(),
    fields: Annotated[
        str | None, Query(description="Comma-separated optional fields to include (axis_x,axis_z,available_dates). Omit for all.")
    ] = None,
) -> ActivityDataResponse:
    """
    Get activity data with sleep scoring algorithm results.

    Returns data with:
    - Sleep scoring results (1=sleep, 0=wake)
    - Choi nonwear detection results (1=nonwear, 0=wear)

    Available algorithms:
    - sadeh_1994_actilife (default): Sadeh 1994 with ActiLife scaling
    - sadeh_1994_original: Sadeh 1994 original paper version
    - cole_kripke_1992_actilife: Cole-Kripke 1992 with ActiLife scaling
    - cole_kripke_1992_original: Cole-Kripke 1992 original paper version
    """
    from sleep_scoring_web.services.algorithms import ALGORITHM_TYPES, ChoiAlgorithm, create_algorithm
    from sleep_scoring_web.services.choi_helpers import DEFAULT_CHOI_COLUMN, VALID_CHOI_COLUMNS

    # Validate algorithm type
    if algorithm not in ALGORITHM_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown algorithm: {algorithm}. Available: {ALGORITHM_TYPES}",
        )

    # Load file + user settings in a single round-trip using outerjoin.
    # Replaces two sequential queries (require_file_and_access + get_choi_column).
    from sleep_scoring_web.api.access import is_admin_user, user_can_access_file
    from sleep_scoring_web.db.models import UserSettings
    from sleep_scoring_web.services.file_identity import is_excluded_file_obj

    combined = await db.execute(
        select(FileModel, UserSettings.extra_settings_json)
        .outerjoin(UserSettings, UserSettings.username == username)
        .where(FileModel.id == file_id)
    )
    row = combined.first()
    if not row or not row[0] or is_excluded_file_obj(row[0]):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    file = row[0]
    if not is_admin_user(username) and not await user_can_access_file(db, username, file_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Extract choi_column from user settings (loaded in the same query)
    extra_settings = row[1]
    choi_column = DEFAULT_CHOI_COLUMN
    if extra_settings:
        col = extra_settings.get("choi_axis", DEFAULT_CHOI_COLUMN)
        if col in VALID_CHOI_COLUMNS:
            choi_column = col
    etag_src = f"{file_id}:{analysis_date}:{algorithm}:{view_hours}:{choi_column}:{fields or ''}:{file.uploaded_at}"
    etag = '"' + hashlib.md5(etag_src.encode(), usedforsecurity=False).hexdigest() + '"'

    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})  # type: ignore[return-value]

    # Parse requested fields
    requested_fields = set(fields.split(",")) if fields else None

    # --- Inline activity data fetch (avoids redundant file/access queries) ---

    # Calculate time window
    if view_hours == 48:
        start_time = datetime.combine(analysis_date, datetime.min.time())
        end_time = start_time + timedelta(hours=48)
    else:
        start_time = datetime.combine(analysis_date, datetime.min.time()) + timedelta(hours=12)
        end_time = start_time + timedelta(hours=24)

    # Determine which columns to load
    need_axis_x = requested_fields is None or "axis_x" in requested_fields
    need_axis_z = requested_fields is None or "axis_z" in requested_fields

    # Use raw SQL text to skip SQLAlchemy query compilation overhead
    from sqlalchemy import text

    cols = "timestamp, axis_y, vector_magnitude"
    if need_axis_x:
        cols += ", axis_x"
    if need_axis_z:
        cols += ", axis_z"

    result = await db.execute(
        text(
            f"SELECT {cols} FROM raw_activity_data "
            "WHERE file_id = :fid AND timestamp >= :start AND timestamp < :end "
            "ORDER BY timestamp"
        ),
        {"fid": file_id, "start": start_time, "end": end_time},
    )
    activity_rows = result.all()

    # Convert to columnar format — (dt - EPOCH).total_seconds() is 5x faster than timegm
    _EPOCH = datetime(1970, 1, 1)
    timestamps: list[float] = []
    axis_x_list: list[float] = []
    axis_y_list: list[float] = []
    axis_z_list: list[float] = []
    vm_list: list[float] = []

    for row in activity_rows:
        timestamps.append((row.timestamp - _EPOCH).total_seconds())
        axis_y_list.append(row.axis_y or 0)
        vm_list.append(row.vector_magnitude or 0)
        if need_axis_x:
            axis_x_list.append(row.axis_x or 0)
        if need_axis_z:
            axis_z_list.append(row.axis_z or 0)

    columnar_data = ActivityDataColumnar(
        timestamps=timestamps,
        axis_x=axis_x_list,
        axis_y=axis_y_list,
        axis_z=axis_z_list,
        vector_magnitude=vm_list,
    )

    # Derive available_dates from File.start_time/end_time (no DB query needed).
    # The file object is already loaded by require_file_and_access().
    need_dates = requested_fields is None or "available_dates" in requested_fields
    available_dates: list[str] = []
    current_date_index = 0
    if need_dates and file.start_time and file.end_time:
        d = file.start_time.date()
        end_d = file.end_time.date()
        while d <= end_d:
            available_dates.append(str(d))
            d += timedelta(days=1)
        current_date_str = str(analysis_date)
        current_date_index = available_dates.index(current_date_str) if current_date_str in available_dates else 0

    view_start = (start_time - _EPOCH).total_seconds()
    view_end = (end_time - _EPOCH).total_seconds()

    response = ActivityDataResponse(
        data=columnar_data,
        available_dates=available_dates,
        current_date_index=current_date_index,
        file_id=file_id,
        analysis_date=str(analysis_date),
        view_start=view_start,
        view_end=view_end,
    )

    # Run sleep scoring algorithm on the data
    if axis_y_list:
        scorer = create_algorithm(algorithm)
        response.algorithm_results = scorer.score(axis_y_list)

        # Run Choi nonwear detection
        from sleep_scoring_web.services.choi_helpers import extract_choi_input_from_columnar

        choi = ChoiAlgorithm()
        choi_input = extract_choi_input_from_columnar(response.data, choi_column)
        response.nonwear_results = choi.detect_mask(choi_input)

    # Query uploaded sensor nonwear periods using raw SQL
    sensor_nw_result = await db.execute(
        text(
            "SELECT start_timestamp, end_timestamp FROM markers "
            "WHERE file_id = :fid AND marker_category = 'nonwear' "
            "AND marker_type = 'sensor' "
            "AND start_timestamp <= :ve AND end_timestamp >= :vs"
        ),
        {"fid": file_id, "ve": view_end, "vs": view_start},
    )
    response.sensor_nonwear_periods = [
        SensorNonwearPeriod(start_timestamp=row.start_timestamp, end_timestamp=row.end_timestamp)
        for row in sensor_nw_result.all()
    ]

    # Set caching headers — ETag + short max-age for browser cache
    response_headers = {
        "ETag": etag,
        "Cache-Control": "private, max-age=300",
    }

    return Response(
        content=response.model_dump_json(exclude_none=True),
        media_type="application/json",
        headers=response_headers,
    )  # type: ignore[return-value]


@router.get("/{file_id}/{analysis_date}/sadeh")
async def get_activity_data_with_sadeh(
    file_id: int,
    analysis_date: date,
    request: Request,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    view_hours: Annotated[int, Query(ge=12, le=48)] = 24,
) -> ActivityDataResponse:
    """
    Get activity data with Sadeh algorithm results.

    DEPRECATED: Use /{file_id}/{analysis_date}/score?algorithm=sadeh_1994_actilife instead.
    """
    return await get_activity_data_with_scoring(
        file_id=file_id,
        analysis_date=analysis_date,
        request=request,
        db=db,
        _="",  # Auth already verified at route level
        username=username,
        view_hours=view_hours,
        algorithm=AlgorithmType.SADEH_1994_ACTILIFE,
    )
