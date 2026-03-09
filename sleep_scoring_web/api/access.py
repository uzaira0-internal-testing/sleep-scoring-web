"""Shared access-control helpers for file-scoped API endpoints."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select

from sleep_scoring_web.config import get_settings
from sleep_scoring_web.db.models import FileAssignment


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
    result = await db.execute(
        select(FileAssignment.file_id).where(FileAssignment.username == username)
    )
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
