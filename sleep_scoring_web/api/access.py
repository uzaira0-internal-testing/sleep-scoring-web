"""Shared access-control helpers for file-scoped API endpoints."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, status
from sqlalchemy import select

from sleep_scoring_web.config import get_settings
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import FileAssignment

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def is_admin_user(username: str) -> bool:
    """Return True when the provided username is configured as admin."""
    if not username:
        return False
    app_settings = get_settings()
    return username.lower() in app_settings.admin_usernames_list


async def get_assigned_file_ids(db, username: str) -> list[int]:
    """Get all file IDs assigned to a username."""
    if not username:
        return []
    result = await db.execute(select(FileAssignment.file_id).where(FileAssignment.username == username))
    return list(result.scalars().all())


async def user_can_access_file(db, username: str, file_id: int) -> bool:
    """Return True if user can access a file by assignment or admin role."""
    if is_admin_user(username):
        return True
    if not username:
        return False
    result = await db.execute(
        select(FileAssignment.id).where(
            FileAssignment.file_id == file_id,
            FileAssignment.username == username,
        )
    )
    return result.scalar_one_or_none() is not None


async def require_file_access(db, username: str, file_id: int) -> None:
    """Raise 404 when a user is not allowed to access a file ID."""
    if await user_can_access_file(db, username, file_id):
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="File not found",
    )


async def get_accessible_files(db: AsyncSession, username: str) -> list[FileModel]:
    """
    Load non-excluded files the user can access in a single DB query.

    For admins, returns all non-excluded files.  For regular users, uses a
    subquery join against ``file_assignments`` so only one round-trip is needed.
    """
    from sleep_scoring_web.api.files import _excluded_filename_sql_filter

    exclusion_filter = ~_excluded_filename_sql_filter()

    if is_admin_user(username):
        stmt = select(FileModel).where(exclusion_filter)
    else:
        assigned_ids = select(FileAssignment.file_id).where(FileAssignment.username == username).correlate(None).scalar_subquery()
        stmt = select(FileModel).where(
            FileModel.id.in_(assigned_ids),
            exclusion_filter,
        )

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def require_file_and_access(db, username: str, file_id: int):
    """
    Load a file and verify access in a single operation.

    Returns the FileModel if access is allowed, raises 404 otherwise.
    Prevents TOCTOU between separate access check + file load queries.
    """
    from sleep_scoring_web.db.models import File as FileModel
    from sleep_scoring_web.services.file_identity import is_excluded_file_obj

    # Load the file first
    result = await db.execute(select(FileModel).where(FileModel.id == file_id))
    file = result.scalar_one_or_none()
    if not file or is_excluded_file_obj(file):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    # Check access
    if not await user_can_access_file(db, username, file_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    return file
