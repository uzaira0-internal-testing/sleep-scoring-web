#!/usr/bin/env python3
"""Metadata column definitions for the column registry."""

from __future__ import annotations

from sleep_scoring_app.core.constants import DatabaseColumn, ExportColumn
from sleep_scoring_app.utils.column_registry import ColumnDefinition, ColumnType, DataType


def register_metadata_columns(registry) -> None:
    """Register all metadata columns."""
    # Participant information
    registry.register(
        ColumnDefinition(
            name="participant_id",
            display_name="Participant ID",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.PARTICIPANT_ID,
            export_column=ExportColumn.NUMERICAL_PARTICIPANT_ID,
            is_required=True,
            ui_order=100,
            ui_group="Participant Information",
            description="Numerical participant identifier",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="full_participant_id",
            display_name="Full Participant ID",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            export_column=ExportColumn.FULL_PARTICIPANT_ID,
            is_required=True,
            ui_order=101,
            ui_group="Participant Information",
            description="Full participant ID including timepoint",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="participant_group",
            display_name="Participant Group",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.PARTICIPANT_GROUP,
            export_column=ExportColumn.PARTICIPANT_GROUP,
            ui_order=103,
            ui_group="Participant Information",
            default_value="G1",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="participant_timepoint",
            display_name="Timepoint",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.PARTICIPANT_TIMEPOINT,
            export_column=ExportColumn.PARTICIPANT_TIMEPOINT,
            ui_order=102,
            ui_group="Participant Information",
            default_value="BO",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="analysis_date",
            display_name="Sleep Date",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.ANALYSIS_DATE,
            export_column=ExportColumn.SLEEP_DATE,
            is_always_exported=True,
            ui_order=104,
            ui_group="Participant Information",
            description="The date/night being analyzed (from UI dropdown)",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="saved_date",
            display_name="Saved Date",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.UPDATED_AT,
            export_column=ExportColumn.SAVED_AT,
            is_always_exported=True,
            ui_order=105,
            ui_group="Metadata",
            description="Date when record was saved",
        ),
    )

    # Import information
    registry.register(
        ColumnDefinition(
            name="import_status",
            display_name="Import Status",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.STATUS,
            is_exportable=False,  # Internal metadata, not for research export
            ui_order=106,
            ui_group="Import Information",
            description="Status of file import",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="file_hash",
            display_name="File Hash",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            database_column=DatabaseColumn.FILE_HASH,
            is_exportable=False,  # Internal metadata, not for research export
            is_user_visible=False,
            ui_order=107,
            ui_group="Import Information",
            description="SHA256 hash for change detection",
        ),
    )

    # Data coverage
    registry.register(
        ColumnDefinition(
            name="date_range_start",
            display_name="Data Start Date",
            column_type=ColumnType.METADATA,
            data_type=DataType.DATETIME,
            database_column=DatabaseColumn.DATE_RANGE_START,
            is_exportable=False,  # Internal metadata, not for research export
            ui_order=109,
            ui_group="Data Coverage",
            description="Earliest timestamp in dataset",
        ),
    )

    registry.register(
        ColumnDefinition(
            name="date_range_end",
            display_name="Data End Date",
            column_type=ColumnType.METADATA,
            data_type=DataType.DATETIME,
            database_column=DatabaseColumn.DATE_RANGE_END,
            is_exportable=False,  # Internal metadata, not for research export
            ui_order=110,
            ui_group="Data Coverage",
            description="Latest timestamp in dataset",
        ),
    )

    # Consensus review flag
    registry.register(
        ColumnDefinition(
            name="needs_consensus",
            display_name="Needs Consensus Review",
            column_type=ColumnType.METADATA,
            data_type=DataType.BOOLEAN,
            database_column=DatabaseColumn.NEEDS_CONSENSUS,
            export_column=ExportColumn.NEEDS_CONSENSUS,
            is_exportable=True,
            is_always_exported=True,  # Always include in exports
            default_value=False,
            ui_order=106,
            ui_group="Quality Control",
            description="Flag indicating this date needs consensus review by a second scorer",
        ),
    )
