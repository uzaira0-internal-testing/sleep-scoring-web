#!/usr/bin/env python3
"""Marker-related column definitions for the column registry."""

from __future__ import annotations

from sleep_scoring_app.core.constants import DatabaseColumn, ExportColumn, SleepPeriodDetectorType
from sleep_scoring_app.utils.column_registry import ColumnDefinition, ColumnType, DataType


def register_marker_columns(registry) -> None:
    """Register all marker-related columns."""
    # Extended marker columns for multiple sleep periods
    registry.register(
        ColumnDefinition(
            name="marker_index",
            display_name="Sleep Period Index",
            column_type=ColumnType.MARKER,
            data_type=DataType.INTEGER,
            database_column=DatabaseColumn.MARKER_INDEX,
            export_column=ExportColumn.MARKER_INDEX,
            is_required=False,
            ui_order=204,
            ui_group="Sleep Markers",
            description="Index of sleep period (1, 2, 3, or 4)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="marker_type",
            display_name="Marker Type",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.MARKER_TYPE,
            is_exportable=True,
            export_column=ExportColumn.MARKER_TYPE,
            ui_order=205,
            ui_group="Sleep Markers",
            description="Type of sleep marker (main_sleep, nap, nwt)",
        ),
    )

    # Onset/offset rule column (NEW - for DI pattern)
    registry.register(
        ColumnDefinition(
            name="sleep_period_detector_id",
            display_name="Onset/Offset Rule",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.ONSET_OFFSET_RULE,
            export_column=ExportColumn.ONSET_OFFSET_RULE,
            is_always_exported=True,
            ui_order=206,
            ui_group="Sleep Markers",
            default_value=SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S,
            description="Rule used to detect sleep onset and offset (e.g., Consecutive 3/5 Minutes, Tudor-Locke)",
        ),
    )

    # Daily sleep markers (complete structure with naps)
    registry.register(
        ColumnDefinition(
            name="daily_sleep_markers",
            display_name="Daily Sleep Markers",
            column_type=ColumnType.METADATA,
            data_type=DataType.JSON,
            database_column=DatabaseColumn.DAILY_SLEEP_MARKERS,
            is_exportable=False,  # Internal structure, not for direct export
            ui_order=999,  # Keep at end
            ui_group="Sleep Markers",
            description="Complete daily sleep markers including all periods and naps",
        ),
    )
