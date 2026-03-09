#!/usr/bin/env python3
"""Sleep-related column definitions for the column registry."""

from __future__ import annotations

from sleep_scoring_app.core.constants import DatabaseColumn, ExportColumn
from sleep_scoring_app.utils.column_registry import ColumnDefinition, ColumnType, DataType


def register_sleep_columns(registry) -> None:
    """Register all sleep-related columns."""
    # Marker columns - Unix timestamps are internal only, not exported
    registry.register(
        ColumnDefinition(
            name="onset_timestamp",
            display_name="Sleep Onset Timestamp",
            column_type=ColumnType.MARKER,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.ONSET_TIMESTAMP,
            export_column=None,
            is_exportable=False,
            is_required=False,
            ui_order=200,
            ui_group="Sleep Markers",
            description="Unix timestamp of sleep onset (internal use only)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="offset_timestamp",
            display_name="Sleep Offset Timestamp",
            column_type=ColumnType.MARKER,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.OFFSET_TIMESTAMP,
            export_column=None,
            is_exportable=False,
            is_required=False,
            ui_order=201,
            ui_group="Sleep Markers",
            description="Unix timestamp of sleep offset (internal use only)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="onset_time",
            display_name="Sleep Onset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.ONSET_TIME,
            export_column=ExportColumn.ONSET_TIME,
            ui_order=202,
            ui_group="Sleep Markers",
            format_string="%H:%M",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="offset_time",
            display_name="Sleep Offset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.OFFSET_TIME,
            export_column=ExportColumn.OFFSET_TIME,
            ui_order=203,
            ui_group="Sleep Markers",
            format_string="%H:%M",
        ),
    )

    # Statistics columns
    registry.register(
        ColumnDefinition(
            name="total_sleep_time",
            display_name="Total Sleep Time (TST)",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.TOTAL_SLEEP_TIME,
            export_column=ExportColumn.TOTAL_SLEEP_TIME,
            ui_order=300,
            ui_group="Sleep Metrics",
            format_string="{:.1f}",
            unit="minutes",
            calculator=None,
            dependencies=[],
        ),
    )

    registry.register(
        ColumnDefinition(
            name="sleep_efficiency",
            display_name="Sleep Efficiency",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.SLEEP_EFFICIENCY,
            export_column=ExportColumn.EFFICIENCY,
            ui_order=301,
            ui_group="Sleep Metrics",
            format_string="{:.2f}",
            unit="%",
            calculator=None,
            dependencies=[],
        ),
    )

    registry.register(
        ColumnDefinition(
            name="waso",
            display_name="Wake After Sleep Onset (WASO)",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.WASO,
            export_column=ExportColumn.WASO,
            ui_order=302,
            ui_group="Sleep Metrics",
            format_string="{:.1f}",
            unit="minutes",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="awakenings",
            display_name="Number of Awakenings",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.INTEGER,
            database_column=DatabaseColumn.AWAKENINGS,
            export_column=ExportColumn.NUMBER_OF_AWAKENINGS,
            ui_order=303,
            ui_group="Sleep Metrics",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="total_minutes_in_bed",
            display_name="Total Minutes in Bed",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.TOTAL_MINUTES_IN_BED,
            export_column=ExportColumn.TOTAL_MINUTES_IN_BED,
            ui_order=302,
            ui_group="Sleep Metrics",
            format_string="{:.1f}",
            unit="minutes",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="average_awakening_length",
            display_name="Average Awakening Length",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.AVERAGE_AWAKENING_LENGTH,
            export_column=ExportColumn.AVERAGE_AWAKENING_LENGTH,
            ui_order=303,
            ui_group="Sleep Metrics",
            format_string="{:.1f}",
            unit="minutes",
        ),
    )
