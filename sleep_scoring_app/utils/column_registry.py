#!/usr/bin/env python3
"""
Column Registry System for Sleep Scoring Application
Provides a centralized way to register and manage data columns across the application.

This file now serves as a facade over domain-specific registries.
Column definitions are organized in:
- registries/metadata_columns.py
- registries/sleep_columns.py
- registries/marker_columns.py
- registries/activity_columns.py
- registries/diary_columns.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable


class ColumnType(StrEnum):
    """Types of columns that can be registered."""

    METADATA = auto()  # Participant info, dates, etc.
    ALGORITHM = auto()  # Algorithm results
    STATISTIC = auto()  # Calculated statistics
    MARKER = auto()  # Sleep markers
    QUALITY = auto()  # Data quality metrics
    CUSTOM = auto()  # User-defined columns


class DataType(StrEnum):
    """Data types for columns."""

    STRING = auto()
    INTEGER = auto()
    FLOAT = auto()
    DATETIME = auto()
    DATE = auto()  # Date-only (no time component)
    BOOLEAN = auto()
    JSON = auto()


@dataclass
class ColumnDefinition:
    """Definition of a data column."""

    # Basic properties
    name: str  # Internal column name
    display_name: str  # User-friendly display name
    column_type: ColumnType  # Category of column
    data_type: DataType  # Data type

    # Storage properties
    database_column: str | None = None  # Database column name
    export_column: str | None = None  # Export CSV column name

    # Behavior properties
    is_required: bool = False  # Required for data integrity
    is_exportable: bool = True  # Show in export dialog and can be toggled
    is_always_exported: bool = False  # Always exported, not toggleable in dialog
    is_autosaved: bool = True  # Include in autosave
    is_user_visible: bool = True  # Show in UI

    # Calculation properties
    calculator: Callable[[dict[str, Any]], Any] | None = None  # Function to calculate value
    dependencies: list[str] = field(default_factory=list)  # Other columns this depends on

    # Validation
    validator: Callable[[Any], bool] | None = None  # Validation function
    default_value: Any = None  # Default if not provided

    # UI properties
    ui_order: int = 1000  # Display order in UI
    ui_group: str = "Other"  # Grouping in UI
    format_string: str | None = None  # Display format (e.g., "{:.2f}" for floats)
    unit: str | None = None  # Unit of measurement
    description: str = ""  # Help text for users


class ColumnRegistry:
    """
    Central registry for all data columns in the application.
    Provides a single source of truth for column definitions.
    """

    def __init__(self) -> None:
        self._columns: dict[str, ColumnDefinition] = {}
        self._groups: dict[str, list[str]] = {}
        self._initialize_core_columns()

    def _initialize_core_columns(self) -> None:
        """Initialize the core columns that come with the application."""
        # Import domain-specific registration functions
        from .registries import (
            register_activity_columns,
            register_diary_columns,
            register_marker_columns,
            register_metadata_columns,
            register_nonwear_columns,
            register_sleep_columns,
        )

        # Register all columns from domain-specific modules
        register_metadata_columns(self)
        register_sleep_columns(self)
        register_marker_columns(self)
        register_activity_columns(self)
        register_diary_columns(self)
        register_nonwear_columns(self)

    def register(self, column: ColumnDefinition) -> None:
        """Register a new column definition."""
        if column.name in self._columns:
            msg = f"Column '{column.name}' is already registered"
            raise ValueError(msg)

        self._columns[column.name] = column

        # Update group tracking
        if column.ui_group not in self._groups:
            self._groups[column.ui_group] = []
        self._groups[column.ui_group].append(column.name)

    def get(self, column_name: str) -> ColumnDefinition | None:
        """Get a column definition by name."""
        return self._columns.get(column_name)

    def get_all(self) -> list[ColumnDefinition]:
        """Get all registered columns."""
        return list(self._columns.values())

    def get_by_group(self, group_name: str) -> list[ColumnDefinition]:
        """Get all columns in a specific UI group."""
        column_names = self._groups.get(group_name, [])
        return [self._columns[name] for name in column_names]

    def get_all_groups(self) -> list[str]:
        """Get all UI group names."""
        return list(self._groups.keys())

    def get_groups_with_exportable_columns(self) -> dict[str, list[str]]:
        """Get groups that contain exportable columns with their export column names."""
        groups = {}
        for group_name in self._groups:
            exportable_columns = []
            for column_name in self._groups[group_name]:
                column = self._columns[column_name]
                if column.is_exportable and column.export_column:
                    exportable_columns.append(column.export_column)
            if exportable_columns:
                groups[group_name] = exportable_columns
        return groups

    def get_exportable(self) -> list[ColumnDefinition]:
        """Get all columns that should be included in exports, sorted by ui_order."""
        exportable_columns = [col for col in self._columns.values() if col.is_exportable]
        return sorted(exportable_columns, key=lambda col: col.ui_order)


# Global registry instance
column_registry = ColumnRegistry()


def register_custom_column(column: ColumnDefinition) -> None:
    """Convenience function to register a custom column."""
    column_registry.register(column)


def get_column_registry() -> ColumnRegistry:
    """Get the global column registry instance."""
    return column_registry
