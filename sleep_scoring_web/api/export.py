"""
Export API endpoints.

Provides endpoints for generating CSV exports of sleep scoring data.
Sleep and nonwear markers are exported as separate CSV files.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from sleep_scoring_web.api.access import get_assigned_file_ids, is_admin_user
from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.schemas import (
    ExportColumnCategory,
    ExportColumnInfo,
    ExportColumnsResponse,
    ExportRequest,
    ExportResponse,
)
from sleep_scoring_web.services.export_service import (
    COLUMN_CATEGORIES,
    EXPORT_COLUMNS,
    ExportService,
)

router = APIRouter()


async def _filter_visible_file_ids(db: DbSession, username: str, requested_ids: list[int]) -> list[int]:
    """Return only the file IDs visible to this user."""
    if is_admin_user(username):
        return requested_ids
    assigned_ids = set(await get_assigned_file_ids(db, username))
    return [file_id for file_id in requested_ids if file_id in assigned_ids]


async def _run_export(service: ExportService, request: ExportRequest, visible_file_ids: list[int]):
    """Run export and return the ExportResult."""
    return await service.export_csv(
        file_ids=visible_file_ids,
        date_range=request.date_range,
        columns=request.columns,
        include_header=request.include_header,
        include_metadata=request.include_metadata,
    )


def _error_csv(message: str) -> StreamingResponse:
    """Return an error as a CSV comment file."""
    return StreamingResponse(
        iter([f"# Export Error\n# {message}\n"]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="export_error.csv"'},
    )


@router.get("/columns")
async def get_export_columns(
    _: VerifiedPassword,
) -> ExportColumnsResponse:
    """
    Get list of available export columns.

    Returns all available columns with their metadata, grouped by category.
    """
    columns = [
        ExportColumnInfo(
            name=col.name,
            category=col.category,
            description=col.description,
            data_type=col.data_type,
            is_default=col.is_default,
        )
        for col in EXPORT_COLUMNS
    ]

    categories = [ExportColumnCategory(name=name, columns=cols) for name, cols in COLUMN_CATEGORIES.items()]

    return ExportColumnsResponse(columns=columns, categories=categories)


@router.post("/csv")
async def generate_csv_export(
    request: ExportRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> ExportResponse:
    """
    Generate CSV export for specified files.

    Returns metadata about the export. Use /csv/download to get the actual file.
    """
    service = ExportService(db)
    visible_file_ids = await _filter_visible_file_ids(db, username, request.file_ids)
    result = await _run_export(service, request, visible_file_ids)

    return ExportResponse(
        success=result.success,
        filename=result.filename,
        row_count=result.row_count,
        file_count=result.file_count,
        message=f"Exported {result.row_count} rows from {result.file_count} files" if result.success else "Export failed",
        warnings=result.warnings + result.errors,
    )


@router.post("/csv/download")
async def download_csv_export(
    request: ExportRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> StreamingResponse:
    """Download sleep marker CSV export."""
    service = ExportService(db)
    visible_file_ids = await _filter_visible_file_ids(db, username, request.file_ids)
    result = await _run_export(service, request, visible_file_ids)

    if not result.success:
        return _error_csv("; ".join(result.errors))

    return StreamingResponse(
        iter([result.csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )


@router.post("/csv/download/nonwear")
async def download_nonwear_csv_export(
    request: ExportRequest,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> StreamingResponse:
    """Download nonwear marker CSV export (separate from sleep)."""
    service = ExportService(db)
    visible_file_ids = await _filter_visible_file_ids(db, username, request.file_ids)
    result = await _run_export(service, request, visible_file_ids)

    if not result.success:
        return _error_csv("; ".join(result.errors))

    if not result.nonwear_csv_content:
        return _error_csv("No nonwear markers found for selected files")

    return StreamingResponse(
        iter([result.nonwear_csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{result.nonwear_filename}"'},
    )


@router.get("/csv/quick")
async def quick_export(
    file_ids: Annotated[str, Query(description="Comma-separated file IDs")],
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
    start_date: Annotated[date | None, Query(description="Start date filter")] = None,
    end_date: Annotated[date | None, Query(description="End date filter")] = None,
) -> StreamingResponse:
    """
    Quick export endpoint for simple GET requests.

    Uses default columns and returns CSV directly.
    """
    # Parse file IDs
    try:
        ids = [int(x.strip()) for x in file_ids.split(",") if x.strip()]
    except ValueError:
        return _error_csv("Invalid file IDs format")

    visible_ids = await _filter_visible_file_ids(db, username, ids)

    if not visible_ids:
        return _error_csv("No file IDs provided")

    service = ExportService(db)

    date_range = (start_date, end_date) if start_date and end_date else None

    result = await service.export_csv(
        file_ids=visible_ids,
        date_range=date_range,
        columns=None,  # Use default columns
        include_header=True,
        include_metadata=True,
    )

    if not result.success:
        return _error_csv("; ".join(result.errors))

    return StreamingResponse(
        iter([result.csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{result.filename}"'},
    )
