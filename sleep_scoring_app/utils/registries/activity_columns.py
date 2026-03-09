#!/usr/bin/env python3
"""Activity-related column definitions for the column registry."""

from __future__ import annotations

from sleep_scoring_app.core.constants import AlgorithmType, DatabaseColumn, ExportColumn
from sleep_scoring_app.utils.column_registry import ColumnDefinition, ColumnType, DataType


def register_activity_columns(registry) -> None:
    """Register all activity-related columns."""
    # Activity metrics columns
    registry.register(
        ColumnDefinition(
            name="total_activity",
            display_name="Total Activity Counts",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.TOTAL_ACTIVITY,
            export_column=ExportColumn.TOTAL_COUNTS,
            is_exportable=True,
            ui_order=350,
            ui_group="Activity Metrics",
            format_string="{:.1f}",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="movement_index",
            display_name="Movement Index",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.MOVEMENT_INDEX,
            export_column=ExportColumn.MOVEMENT_INDEX,
            is_exportable=True,
            ui_order=351,
            ui_group="Activity Metrics",
            format_string="{:.2f}",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="fragmentation_index",
            display_name="Fragmentation Index",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.FRAGMENTATION_INDEX,
            export_column=ExportColumn.FRAGMENTATION_INDEX,
            is_exportable=True,
            ui_order=352,
            ui_group="Activity Metrics",
            format_string="{:.2f}",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="sleep_fragmentation_index",
            display_name="Sleep Fragmentation Index",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.FLOAT,
            database_column=DatabaseColumn.SLEEP_FRAGMENTATION_INDEX,
            export_column=ExportColumn.SLEEP_FRAGMENTATION_INDEX,
            is_exportable=True,
            ui_order=353,
            ui_group="Activity Metrics",
            format_string="{:.2f}",
        ),
    )

    # Algorithm columns
    registry.register(
        ColumnDefinition(
            name="algorithm_type",
            display_name="Algorithm Type",
            column_type=ColumnType.ALGORITHM,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.ALGORITHM_TYPE,
            export_column=ExportColumn.SLEEP_ALGORITHM,
            ui_order=400,
            ui_group="Algorithm Results",
            default_value=AlgorithmType.SADEH_1994_ACTILIFE,
            description="Type of algorithm used (Manual, Combined, etc.)",
        ),
    )

    # Generic sleep algorithm identifier (NEW - for DI pattern)
    registry.register(
        ColumnDefinition(
            name="sleep_algorithm_name",
            display_name="Sleep Algorithm",
            column_type=ColumnType.ALGORITHM,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.SLEEP_ALGORITHM_NAME,
            export_column=ExportColumn.SLEEP_ALGORITHM_NAME,
            is_always_exported=True,
            ui_order=401,
            ui_group="Algorithm Results",
            default_value=AlgorithmType.SADEH_1994_ACTILIFE,
            description="Sleep scoring algorithm identifier (e.g., sadeh_1994_actilife, cole_kripke_1992_actilife)",
        ),
    )

    # Algorithm result columns for onset/offset values
    registry.register(
        ColumnDefinition(
            name="sleep_algorithm_onset",
            display_name="Sleep Algorithm Onset Value",
            column_type=ColumnType.ALGORITHM,
            data_type=DataType.INTEGER,
            database_column=DatabaseColumn.SLEEP_ALGORITHM_ONSET,
            export_column=ExportColumn.SLEEP_ALGORITHM_ONSET,
            ui_order=402,
            ui_group="Algorithm Results",
            description="Sleep scoring algorithm value at onset marker",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="sleep_algorithm_offset",
            display_name="Sleep Algorithm Offset Value",
            column_type=ColumnType.ALGORITHM,
            data_type=DataType.INTEGER,
            database_column=DatabaseColumn.SLEEP_ALGORITHM_OFFSET,
            export_column=ExportColumn.SLEEP_ALGORITHM_OFFSET,
            ui_order=403,
            ui_group="Algorithm Results",
            description="Sleep scoring algorithm value at offset marker",
        ),
    )

    # Overlapping nonwear minutes during sleep period
    registry.register(
        ColumnDefinition(
            name="overlapping_nonwear_minutes_algorithm",
            display_name="Overlapping Nonwear Minutes (Algorithm)",
            column_type=ColumnType.ALGORITHM,
            data_type=DataType.INTEGER,
            database_column=DatabaseColumn.OVERLAPPING_NONWEAR_MINUTES_ALGORITHM,
            export_column=ExportColumn.OVERLAPPING_NONWEAR_MINUTES_ALGORITHM,
            is_exportable=True,
            ui_order=403,
            ui_group="Nonwear",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="overlapping_nonwear_minutes_sensor",
            display_name="Overlapping Nonwear Minutes (Sensor)",
            column_type=ColumnType.ALGORITHM,
            data_type=DataType.INTEGER,
            database_column=DatabaseColumn.OVERLAPPING_NONWEAR_MINUTES_SENSOR,
            export_column=ExportColumn.OVERLAPPING_NONWEAR_MINUTES_SENSOR,
            is_exportable=True,
            ui_order=404,
            ui_group="Nonwear",
        ),
    )

    # Data quality metrics
    registry.register(
        ColumnDefinition(
            name="total_records",
            display_name="Total Records",
            column_type=ColumnType.QUALITY,
            data_type=DataType.INTEGER,
            database_column=DatabaseColumn.TOTAL_RECORDS,
            is_exportable=False,  # Internal metadata, not for research export
            ui_order=108,
            ui_group="Data Quality",
            description="Total number of activity records",
        ),
    )
