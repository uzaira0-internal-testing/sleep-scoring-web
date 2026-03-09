#!/usr/bin/env python3
"""Diary-related column definitions for the column registry."""

from __future__ import annotations

from sleep_scoring_app.core.constants import DatabaseColumn, ExportColumn
from sleep_scoring_app.utils.column_registry import ColumnDefinition, ColumnType, DataType


def register_diary_columns(registry) -> None:
    """Register all diary-related columns."""
    # Diary-specific nap columns
    registry.register(
        ColumnDefinition(
            name="nap_occurred",
            display_name="Diary: Nap 1 Occurred",
            column_type=ColumnType.MARKER,
            data_type=DataType.BOOLEAN,
            database_column=DatabaseColumn.NAP_OCCURRED,
            export_column=ExportColumn.NAP_OCCURRED,
            is_exportable=True,
            ui_order=250,
            ui_group="Diary: Nap Information",
            default_value=False,
            description="Whether a nap occurred during this period",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nap_onset_time",
            display_name="Diary: Nap 1 Onset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NAP_ONSET_TIME,
            export_column=ExportColumn.NAP_ONSET_TIME,
            is_exportable=True,
            ui_order=251,
            ui_group="Diary: Nap Information",
            format_string="%H:%M",
            description="Time when nap began",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nap_offset_time",
            display_name="Diary: Nap 1 Offset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NAP_OFFSET_TIME,
            export_column=ExportColumn.NAP_OFFSET_TIME,
            is_exportable=True,
            ui_order=252,
            ui_group="Diary: Nap Information",
            format_string="%H:%M",
            description="Time when nap ended",
        ),
    )

    # Second nap columns
    registry.register(
        ColumnDefinition(
            name="nap_onset_time_2",
            display_name="Diary: Nap 2 Onset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NAP_ONSET_TIME_2,
            export_column=ExportColumn.NAP_ONSET_TIME_2,
            is_exportable=True,
            ui_order=253,
            ui_group="Diary: Nap Information",
            format_string="%H:%M",
            description="Time when second nap began",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nap_offset_time_2",
            display_name="Diary: Nap 2 Offset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NAP_OFFSET_TIME_2,
            export_column=ExportColumn.NAP_OFFSET_TIME_2,
            is_exportable=True,
            ui_order=254,
            ui_group="Diary: Nap Information",
            format_string="%H:%M",
            description="Time when second nap ended",
        ),
    )

    # Third nap columns
    registry.register(
        ColumnDefinition(
            name="nap_onset_time_3",
            display_name="Diary: Nap 3 Onset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NAP_ONSET_TIME_3,
            export_column=ExportColumn.NAP_ONSET_TIME_3,
            is_exportable=True,
            ui_order=255,
            ui_group="Diary: Nap Information",
            format_string="%H:%M",
            description="Time when third nap began",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nap_offset_time_3",
            display_name="Diary: Nap 3 Offset Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NAP_OFFSET_TIME_3,
            export_column=ExportColumn.NAP_OFFSET_TIME_3,
            is_exportable=True,
            ui_order=256,
            ui_group="Diary: Nap Information",
            format_string="%H:%M",
            description="Time when third nap ended",
        ),
    )

    # Diary-specific nonwear time columns
    registry.register(
        ColumnDefinition(
            name="nonwear_occurred",
            display_name="Diary: Nonwear Occurred",
            column_type=ColumnType.MARKER,
            data_type=DataType.BOOLEAN,
            database_column=DatabaseColumn.NONWEAR_OCCURRED,
            export_column=ExportColumn.NONWEAR_OCCURRED,
            is_exportable=True,
            ui_order=260,
            ui_group="Diary: Nonwear Information",
            default_value=False,
            description="Whether device was not worn during this period",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_reason",
            display_name="Diary: Nonwear Reason",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_REASON,
            export_column=ExportColumn.NONWEAR_REASON,
            is_exportable=True,
            ui_order=261,
            ui_group="Diary: Nonwear Information",
            description="Reason for device not being worn",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_start_time",
            display_name="Diary: Nonwear Start Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_START_TIME,
            export_column=ExportColumn.NONWEAR_START_TIME,
            is_exportable=True,
            ui_order=262,
            ui_group="Diary: Nonwear Information",
            format_string="%H:%M",
            description="Time when device was removed",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_end_time",
            display_name="Diary: Nonwear End Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_END_TIME,
            export_column=ExportColumn.NONWEAR_END_TIME,
            is_exportable=True,
            ui_order=263,
            ui_group="Diary: Nonwear Information",
            format_string="%H:%M",
            description="Time when device was put back on",
        ),
    )

    # Additional nonwear period columns
    registry.register(
        ColumnDefinition(
            name="nonwear_reason_2",
            display_name="Diary: Nonwear 2 Reason",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_REASON_2,
            export_column=ExportColumn.NONWEAR_REASON_2,
            is_exportable=True,
            ui_order=264,
            ui_group="Diary: Nonwear Information",
            description="Reason for second nonwear period",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_start_time_2",
            display_name="Diary: Nonwear 2 Start Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_START_TIME_2,
            export_column=ExportColumn.NONWEAR_START_TIME_2,
            is_exportable=True,
            ui_order=265,
            ui_group="Diary: Nonwear Information",
            format_string="%H:%M",
            description="Time when device was removed (2nd period)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_end_time_2",
            display_name="Diary: Nonwear 2 End Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_END_TIME_2,
            export_column=ExportColumn.NONWEAR_END_TIME_2,
            is_exportable=True,
            ui_order=266,
            ui_group="Diary: Nonwear Information",
            format_string="%H:%M",
            description="Time when device was put back on (2nd period)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_reason_3",
            display_name="Diary: Nonwear 3 Reason",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_REASON_3,
            export_column=ExportColumn.NONWEAR_REASON_3,
            is_exportable=True,
            ui_order=267,
            ui_group="Diary: Nonwear Information",
            description="Reason for third nonwear period",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_start_time_3",
            display_name="Diary: Nonwear 3 Start Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_START_TIME_3,
            export_column=ExportColumn.NONWEAR_START_TIME_3,
            is_exportable=True,
            ui_order=268,
            ui_group="Diary: Nonwear Information",
            format_string="%H:%M",
            description="Time when device was removed (3rd period)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="nonwear_end_time_3",
            display_name="Diary: Nonwear 3 End Time",
            column_type=ColumnType.MARKER,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.NONWEAR_END_TIME_3,
            export_column=ExportColumn.NONWEAR_END_TIME_3,
            is_exportable=True,
            ui_order=269,
            ui_group="Diary: Nonwear Information",
            format_string="%H:%M",
            description="Time when device was put back on (3rd period)",
        ),
    )
