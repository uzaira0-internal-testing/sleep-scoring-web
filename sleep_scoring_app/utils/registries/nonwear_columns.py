#!/usr/bin/env python3
"""Nonwear export column definitions for the column registry."""

from __future__ import annotations

from sleep_scoring_app.core.constants import ExportColumn, ExportUIGroup
from sleep_scoring_app.utils.column_registry import ColumnDefinition, ColumnType, DataType


def register_nonwear_columns(registry) -> None:
    """Register all nonwear export column definitions."""
    registry.register(
        ColumnDefinition(
            name="nonwear_start",
            display_name="Nonwear Start Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            export_column=ExportColumn.NONWEAR_START,
            is_exportable=True,
            ui_order=301,
            ui_group=ExportUIGroup.NONWEAR_MARKERS,
            description="Start time of nonwear period",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_end",
            display_name="Nonwear End Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            export_column=ExportColumn.NONWEAR_END,
            is_exportable=True,
            ui_order=302,
            ui_group=ExportUIGroup.NONWEAR_MARKERS,
            description="End time of nonwear period",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_duration",
            display_name="Duration (minutes)",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            export_column=ExportColumn.NONWEAR_DURATION_MINUTES,
            is_exportable=True,
            ui_order=303,
            ui_group=ExportUIGroup.NONWEAR_MARKERS,
            description="Duration of nonwear period in minutes",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_source",
            display_name="Source",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            export_column=ExportColumn.NONWEAR_SOURCE,
            is_exportable=True,
            ui_order=304,
            ui_group=ExportUIGroup.NONWEAR_MARKERS,
            description="Source of nonwear detection (algorithm, sensor, manual)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_period_index",
            display_name="Period Index",
            column_type=ColumnType.METADATA,
            data_type=DataType.INTEGER,
            export_column=ExportColumn.NONWEAR_PERIOD_INDEX,
            is_exportable=True,
            ui_order=305,
            ui_group=ExportUIGroup.NONWEAR_MARKERS,
            description="Index of nonwear period within the day",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_overlap_minutes",
            display_name="Overlap Minutes",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            export_column=ExportColumn.NONWEAR_OVERLAP_MINUTES,
            is_exportable=True,
            ui_order=306,
            ui_group=ExportUIGroup.NONWEAR_MARKERS,
            description="Minutes of nonwear overlap with sleep periods",
        ),
    )
