"""
Centralized Choi nonwear detection helpers.

Ensures all Choi call sites (chart overlay, onset/offset tables, full table,
metrics, auto-score) use the same column — either the user's preference from
settings or the default (vector_magnitude).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from sleep_scoring_web.db.models import UserSettings
from sleep_scoring_web.schemas.enums import ActivityDataPreference

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

    from sleep_scoring_web.db.models import RawActivityData
    from sleep_scoring_web.schemas import ActivityDataColumnar

DEFAULT_CHOI_COLUMN = ActivityDataPreference.VECTOR_MAGNITUDE
VALID_CHOI_COLUMNS = {"axis_x", "axis_y", "axis_z", "vector_magnitude"}


async def get_choi_column(db: AsyncSession, username: str) -> str:
    """Read user's choi_axis preference from extra_settings_json, default to vector_magnitude."""
    if not username:
        return DEFAULT_CHOI_COLUMN

    result = await db.execute(select(UserSettings).where(UserSettings.username == username))
    settings = result.scalar_one_or_none()
    if settings and settings.extra_settings_json:
        col = settings.extra_settings_json.get("choi_axis", DEFAULT_CHOI_COLUMN)
        if col in VALID_CHOI_COLUMNS:
            return col
    return DEFAULT_CHOI_COLUMN


def extract_choi_input(activity_rows: list[RawActivityData], column: str) -> list[int]:
    """Extract the correct column from ORM rows for Choi input."""
    return [getattr(row, column, 0) or 0 for row in activity_rows]


def extract_choi_input_from_columnar(data: ActivityDataColumnar, column: str) -> list[int]:
    """Extract the correct column from ActivityDataColumnar for Choi input."""
    return getattr(data, column, data.vector_magnitude)
