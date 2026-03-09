"""User settings API endpoints for persisting preferences."""

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from sleep_scoring_web.api.deps import DbSession, Username, VerifiedPassword
from sleep_scoring_web.db.models import UserSettings
from sleep_scoring_web.schemas.enums import (
    ActivityDataPreference,
    AlgorithmType,
    SleepPeriodDetectorType,
)

router = APIRouter(prefix="/settings", tags=["settings"])


# =============================================================================
# Pydantic Models
# =============================================================================


class UserSettingsResponse(BaseModel):
    """Response model for user settings."""

    # Study settings
    sleep_detection_rule: str | None = None
    night_start_hour: str | None = None
    night_end_hour: str | None = None

    # Data settings
    device_preset: str | None = None
    epoch_length_seconds: int | None = None
    skip_rows: int | None = None

    # Display preferences
    preferred_display_column: str | None = None
    view_mode_hours: int | None = None
    default_algorithm: str | None = None

    # Extra settings
    extra_settings: dict[str, Any] | None = None

    class Config:  # noqa: D106
        from_attributes = True


class UserSettingsUpdate(BaseModel):
    """Request model for updating user settings."""

    # Study settings
    sleep_detection_rule: str | None = None
    night_start_hour: str | None = None
    night_end_hour: str | None = None

    # Data settings
    device_preset: str | None = None
    epoch_length_seconds: int | None = None
    skip_rows: int | None = None

    # Display preferences
    preferred_display_column: str | None = None
    view_mode_hours: int | None = None
    default_algorithm: str | None = None

    # Extra settings (for flexibility)
    extra_settings: dict[str, Any] | None = None


# =============================================================================
# Default Settings
# =============================================================================


def get_default_settings() -> UserSettingsResponse:
    """Get default settings for a new user."""
    return UserSettingsResponse(
        sleep_detection_rule=SleepPeriodDetectorType.get_default(),
        night_start_hour="21:00",
        night_end_hour="09:00",
        device_preset="actigraph",
        epoch_length_seconds=60,
        skip_rows=10,
        preferred_display_column=ActivityDataPreference.AXIS_Y,
        view_mode_hours=24,
        default_algorithm=AlgorithmType.get_default(),
        extra_settings={},
    )


# =============================================================================
# API Endpoints
# =============================================================================


@router.get("")
async def get_settings(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> UserSettingsResponse:
    """
    Get current user's settings, merged with study-wide settings.

    Study-wide settings (detection rule, night hours, filename patterns)
    are shared across all users. Per-user settings (algorithm, display
    preferences) are personal.
    """
    result = await db.execute(select(UserSettings).where(UserSettings.username == username))
    settings = result.scalar_one_or_none()

    # Load study-wide settings
    study_result = await db.execute(
        select(UserSettings).where(UserSettings.username == "__study__")
    )
    study_settings = study_result.scalar_one_or_none()

    defaults = get_default_settings()

    # Build extra_settings: start with study extras, overlay user extras
    extra = {}
    if study_settings and study_settings.extra_settings_json:
        extra.update(study_settings.extra_settings_json)
    if settings and settings.extra_settings_json:
        # User extras override study extras for non-study keys
        for k, v in settings.extra_settings_json.items():
            if k not in STUDY_EXTRA_KEYS:
                extra[k] = v

    # Helper: prefer study setting, fall back to user setting, then default
    def _study_first(field: str, default: Any = None) -> Any:
        val = getattr(study_settings, field, None) if study_settings else None
        if val is not None:
            return val
        val = getattr(settings, field, None) if settings else None
        if val is not None:
            return val
        return default

    # Study-wide fields from study row; per-user display prefs from user row
    return UserSettingsResponse(
        sleep_detection_rule=_study_first("sleep_detection_rule", defaults.sleep_detection_rule),
        night_start_hour=_study_first("night_start_hour", defaults.night_start_hour),
        night_end_hour=_study_first("night_end_hour", defaults.night_end_hour),
        device_preset=_study_first("device_preset", defaults.device_preset),
        epoch_length_seconds=_study_first("epoch_length_seconds", defaults.epoch_length_seconds),
        skip_rows=_study_first("skip_rows", defaults.skip_rows),
        default_algorithm=_study_first("default_algorithm", defaults.default_algorithm),
        # Per-user only
        preferred_display_column=(settings.preferred_display_column if settings else None) or defaults.preferred_display_column,
        view_mode_hours=(settings.view_mode_hours if settings else None) or defaults.view_mode_hours,
        extra_settings=extra or defaults.extra_settings,
    )


@router.put("")
async def update_settings(
    settings_data: UserSettingsUpdate,
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> UserSettingsResponse:
    """
    Update current user's settings.

    Creates settings record if it doesn't exist.
    Only updates fields that are provided (non-None).
    """
    result = await db.execute(select(UserSettings).where(UserSettings.username == username))
    settings = result.scalar_one_or_none()

    if settings is None:
        # Create new settings record with defaults merged with provided values
        defaults = get_default_settings()
        settings = UserSettings(
            username=username,
            sleep_detection_rule=settings_data.sleep_detection_rule or defaults.sleep_detection_rule,
            night_start_hour=settings_data.night_start_hour or defaults.night_start_hour,
            night_end_hour=settings_data.night_end_hour or defaults.night_end_hour,
            device_preset=settings_data.device_preset or defaults.device_preset,
            epoch_length_seconds=settings_data.epoch_length_seconds or defaults.epoch_length_seconds,
            skip_rows=settings_data.skip_rows if settings_data.skip_rows is not None else defaults.skip_rows,
            preferred_display_column=settings_data.preferred_display_column or defaults.preferred_display_column,
            view_mode_hours=settings_data.view_mode_hours or defaults.view_mode_hours,
            default_algorithm=settings_data.default_algorithm or defaults.default_algorithm,
            extra_settings_json=settings_data.extra_settings or defaults.extra_settings,
        )
        db.add(settings)
    else:
        # Update existing settings (only non-None values)
        update_data = settings_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            if value is not None:
                if field == "extra_settings":
                    # Merge with existing extra_settings to avoid one page
                    # overwriting another page's keys.
                    # Must create a new dict — in-place mutation is not detected by SQLAlchemy.
                    merged = {**(settings.extra_settings_json or {}), **value}
                    settings.extra_settings_json = merged
                else:
                    setattr(settings, field, value)

    await db.commit()
    await db.refresh(settings)

    return UserSettingsResponse(
        sleep_detection_rule=settings.sleep_detection_rule,
        night_start_hour=settings.night_start_hour,
        night_end_hour=settings.night_end_hour,
        device_preset=settings.device_preset,
        epoch_length_seconds=settings.epoch_length_seconds,
        skip_rows=settings.skip_rows,
        preferred_display_column=settings.preferred_display_column,
        view_mode_hours=settings.view_mode_hours,
        default_algorithm=settings.default_algorithm,
        extra_settings=settings.extra_settings_json,
    )


@router.delete("", status_code=204)
async def reset_settings(
    db: DbSession,
    _: VerifiedPassword,
    username: Username,
) -> None:
    """
    Reset user settings to defaults.

    Deletes the settings record, so next GET will return defaults.
    """
    result = await db.execute(select(UserSettings).where(UserSettings.username == username))
    settings = result.scalar_one_or_none()

    if settings:
        await db.delete(settings)
        await db.commit()


# =============================================================================
# Study-wide settings (shared across all users)
# =============================================================================

STUDY_SETTINGS_USERNAME = "__study__"

# Keys in extra_settings that are study-wide (not per-user)
STUDY_EXTRA_KEYS = {
    "id_pattern",
    "timepoint_pattern",
    "group_pattern",
    "valid_groups",
    "valid_timepoints",
    "default_group",
    "default_timepoint",
    "unknown_value",
    "choi_axis",
    "preferred_activity_column",
    "column_mapping",
}


class StudySettingsResponse(BaseModel):
    """Response model for study-wide settings."""

    sleep_detection_rule: str | None = None
    night_start_hour: str | None = None
    night_end_hour: str | None = None
    device_preset: str | None = None
    epoch_length_seconds: int | None = None
    skip_rows: int | None = None
    default_algorithm: str | None = None
    extra_settings: dict[str, Any] | None = None

    class Config:  # noqa: D106
        from_attributes = True


class StudySettingsUpdate(BaseModel):
    """Request model for updating study-wide settings."""

    sleep_detection_rule: str | None = None
    night_start_hour: str | None = None
    night_end_hour: str | None = None
    device_preset: str | None = None
    epoch_length_seconds: int | None = None
    skip_rows: int | None = None
    default_algorithm: str | None = None
    extra_settings: dict[str, Any] | None = None


@router.get("/study")
async def get_study_settings(
    db: DbSession,
    _: VerifiedPassword,
) -> StudySettingsResponse:
    """Get study-wide settings shared across all users."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.username == STUDY_SETTINGS_USERNAME)
    )
    settings = result.scalar_one_or_none()

    if settings is None:
        defaults = get_default_settings()
        return StudySettingsResponse(
            sleep_detection_rule=defaults.sleep_detection_rule,
            night_start_hour=defaults.night_start_hour,
            night_end_hour=defaults.night_end_hour,
            device_preset=defaults.device_preset,
            epoch_length_seconds=defaults.epoch_length_seconds,
            skip_rows=defaults.skip_rows,
            default_algorithm=defaults.default_algorithm,
            extra_settings={},
        )

    return StudySettingsResponse(
        sleep_detection_rule=settings.sleep_detection_rule,
        night_start_hour=settings.night_start_hour,
        night_end_hour=settings.night_end_hour,
        device_preset=settings.device_preset,
        epoch_length_seconds=settings.epoch_length_seconds,
        skip_rows=settings.skip_rows,
        default_algorithm=settings.default_algorithm,
        extra_settings=settings.extra_settings_json,
    )


@router.put("/study")
async def update_study_settings(
    settings_data: StudySettingsUpdate,
    db: DbSession,
    _: VerifiedPassword,
) -> StudySettingsResponse:
    """Update study-wide settings. These are shared across all users."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.username == STUDY_SETTINGS_USERNAME)
    )
    settings = result.scalar_one_or_none()

    if settings is None:
        defaults = get_default_settings()
        settings = UserSettings(
            username=STUDY_SETTINGS_USERNAME,
            sleep_detection_rule=settings_data.sleep_detection_rule or defaults.sleep_detection_rule,
            night_start_hour=settings_data.night_start_hour or defaults.night_start_hour,
            night_end_hour=settings_data.night_end_hour or defaults.night_end_hour,
            device_preset=settings_data.device_preset or defaults.device_preset,
            epoch_length_seconds=settings_data.epoch_length_seconds or defaults.epoch_length_seconds,
            skip_rows=settings_data.skip_rows if settings_data.skip_rows is not None else defaults.skip_rows,
            default_algorithm=settings_data.default_algorithm or defaults.default_algorithm,
            extra_settings_json=settings_data.extra_settings or {},
        )
        db.add(settings)
    else:
        if settings_data.sleep_detection_rule is not None:
            settings.sleep_detection_rule = settings_data.sleep_detection_rule
        if settings_data.night_start_hour is not None:
            settings.night_start_hour = settings_data.night_start_hour
        if settings_data.night_end_hour is not None:
            settings.night_end_hour = settings_data.night_end_hour
        if settings_data.device_preset is not None:
            settings.device_preset = settings_data.device_preset
        if settings_data.epoch_length_seconds is not None:
            settings.epoch_length_seconds = settings_data.epoch_length_seconds
        if settings_data.skip_rows is not None:
            settings.skip_rows = settings_data.skip_rows
        if settings_data.default_algorithm is not None:
            settings.default_algorithm = settings_data.default_algorithm
        if settings_data.extra_settings is not None:
            merged = {**(settings.extra_settings_json or {}), **settings_data.extra_settings}
            settings.extra_settings_json = merged

    await db.commit()
    await db.refresh(settings)

    return StudySettingsResponse(
        sleep_detection_rule=settings.sleep_detection_rule,
        night_start_hour=settings.night_start_hour,
        night_end_hour=settings.night_end_hour,
        device_preset=settings.device_preset,
        epoch_length_seconds=settings.epoch_length_seconds,
        skip_rows=settings.skip_rows,
        default_algorithm=settings.default_algorithm,
        extra_settings=settings.extra_settings_json,
    )


@router.delete("/study", status_code=204)
async def reset_study_settings(
    db: DbSession,
    _: VerifiedPassword,
) -> None:
    """Reset study-wide settings to defaults."""
    result = await db.execute(
        select(UserSettings).where(UserSettings.username == STUDY_SETTINGS_USERNAME)
    )
    settings = result.scalar_one_or_none()
    if settings:
        await db.delete(settings)
        await db.commit()
