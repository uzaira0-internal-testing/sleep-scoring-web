"""
Authentication setup for Sleep Scoring Web.

Configures session-based authentication with site-wide protection.
"""

from __future__ import annotations

from global_auth import DatabaseSessionStorage

from sleep_scoring_web.db.models import Session
from sleep_scoring_web.db.session import async_session_maker


def create_session_storage() -> DatabaseSessionStorage:
    """
    Create async database session storage.

    Uses the existing async_session_maker and Session model.
    """
    return DatabaseSessionStorage(
        session_maker=async_session_maker,
        session_model=Session,
    )
