"""
Tests for column registry system.

Tests centralized column definitions and registry management.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.utils.column_registry import (
    ColumnDefinition,
    ColumnRegistry,
    ColumnType,
    DataType,
    column_registry,
    get_column_registry,
    register_custom_column,
)


class TestColumnType:
    """Tests for ColumnType enum."""

    def test_has_metadata_type(self) -> None:
        """Has METADATA type."""
        assert ColumnType.METADATA is not None

    def test_has_algorithm_type(self) -> None:
        """Has ALGORITHM type."""
        assert ColumnType.ALGORITHM is not None

    def test_has_statistic_type(self) -> None:
        """Has STATISTIC type."""
        assert ColumnType.STATISTIC is not None

    def test_has_marker_type(self) -> None:
        """Has MARKER type."""
        assert ColumnType.MARKER is not None

    def test_has_quality_type(self) -> None:
        """Has QUALITY type."""
        assert ColumnType.QUALITY is not None

    def test_has_custom_type(self) -> None:
        """Has CUSTOM type."""
        assert ColumnType.CUSTOM is not None

    def test_is_str_enum(self) -> None:
        """Is a string enum (can be used as string)."""
        assert isinstance(ColumnType.METADATA, str)


class TestDataType:
    """Tests for DataType enum."""

    def test_has_string_type(self) -> None:
        """Has STRING type."""
        assert DataType.STRING is not None

    def test_has_integer_type(self) -> None:
        """Has INTEGER type."""
        assert DataType.INTEGER is not None

    def test_has_float_type(self) -> None:
        """Has FLOAT type."""
        assert DataType.FLOAT is not None

    def test_has_datetime_type(self) -> None:
        """Has DATETIME type."""
        assert DataType.DATETIME is not None

    def test_has_date_type(self) -> None:
        """Has DATE type."""
        assert DataType.DATE is not None

    def test_has_boolean_type(self) -> None:
        """Has BOOLEAN type."""
        assert DataType.BOOLEAN is not None

    def test_has_json_type(self) -> None:
        """Has JSON type."""
        assert DataType.JSON is not None

    def test_is_str_enum(self) -> None:
        """Is a string enum (can be used as string)."""
        assert isinstance(DataType.STRING, str)


class TestColumnDefinition:
    """Tests for ColumnDefinition dataclass."""

    def test_creates_with_required_fields(self) -> None:
        """Creates with required fields only."""
        col = ColumnDefinition(
            name="test_column",
            display_name="Test Column",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.name == "test_column"
        assert col.display_name == "Test Column"

    def test_default_database_column_is_none(self) -> None:
        """Default database_column is None."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.database_column is None

    def test_default_export_column_is_none(self) -> None:
        """Default export_column is None."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.export_column is None

    def test_default_is_required_is_false(self) -> None:
        """Default is_required is False."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.is_required is False

    def test_default_is_exportable_is_true(self) -> None:
        """Default is_exportable is True."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.is_exportable is True

    def test_default_is_always_exported_is_false(self) -> None:
        """Default is_always_exported is False."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.is_always_exported is False

    def test_default_is_autosaved_is_true(self) -> None:
        """Default is_autosaved is True."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.is_autosaved is True

    def test_default_is_user_visible_is_true(self) -> None:
        """Default is_user_visible is True."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.is_user_visible is True

    def test_default_ui_order_is_1000(self) -> None:
        """Default ui_order is 1000."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.ui_order == 1000

    def test_default_ui_group_is_other(self) -> None:
        """Default ui_group is 'Other'."""
        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
        )

        assert col.ui_group == "Other"

    def test_can_set_calculator(self) -> None:
        """Can set calculator function."""

        def calc(data: dict) -> str:
            return "calculated"

        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.STATISTIC,
            data_type=DataType.STRING,
            calculator=calc,
        )

        assert col.calculator is calc
        assert col.calculator({}) == "calculated"

    def test_can_set_validator(self) -> None:
        """Can set validator function."""

        def validate(value: str) -> bool:
            return len(value) > 0

        col = ColumnDefinition(
            name="test",
            display_name="Test",
            column_type=ColumnType.METADATA,
            data_type=DataType.STRING,
            validator=validate,
        )

        assert col.validator is validate
        assert col.validator("test") is True


class TestColumnRegistry:
    """Tests for ColumnRegistry class."""

    def test_initializes_with_core_columns(self) -> None:
        """Initializes with core columns registered."""
        registry = ColumnRegistry()

        # Should have some columns after initialization
        assert len(registry.get_all()) > 0

    def test_register_adds_column(self) -> None:
        """register() adds a column to the registry."""
        registry = ColumnRegistry()
        col = ColumnDefinition(
            name="unique_test_column_xyz",
            display_name="Unique Test",
            column_type=ColumnType.CUSTOM,
            data_type=DataType.STRING,
        )

        registry.register(col)

        assert registry.get("unique_test_column_xyz") is not None

    def test_register_raises_for_duplicate_name(self) -> None:
        """register() raises for duplicate column name."""
        registry = ColumnRegistry()
        col1 = ColumnDefinition(
            name="duplicate_test_col",
            display_name="Test 1",
            column_type=ColumnType.CUSTOM,
            data_type=DataType.STRING,
        )
        col2 = ColumnDefinition(
            name="duplicate_test_col",
            display_name="Test 2",
            column_type=ColumnType.CUSTOM,
            data_type=DataType.STRING,
        )

        registry.register(col1)

        with pytest.raises(ValueError, match="already registered"):
            registry.register(col2)

    def test_get_returns_column_by_name(self) -> None:
        """get() returns column by name."""
        registry = ColumnRegistry()
        col = ColumnDefinition(
            name="get_test_column",
            display_name="Get Test",
            column_type=ColumnType.CUSTOM,
            data_type=DataType.STRING,
        )
        registry.register(col)

        result = registry.get("get_test_column")

        assert result is col

    def test_get_returns_none_for_unknown(self) -> None:
        """get() returns None for unknown column."""
        registry = ColumnRegistry()

        result = registry.get("nonexistent_column_xyz")

        assert result is None

    def test_get_all_returns_list_of_columns(self) -> None:
        """get_all() returns list of ColumnDefinition."""
        registry = ColumnRegistry()

        result = registry.get_all()

        assert isinstance(result, list)
        assert all(isinstance(c, ColumnDefinition) for c in result)

    def test_get_by_group_returns_columns_in_group(self) -> None:
        """get_by_group() returns columns in specified group."""
        registry = ColumnRegistry()
        col = ColumnDefinition(
            name="grouped_test_col",
            display_name="Grouped Test",
            column_type=ColumnType.CUSTOM,
            data_type=DataType.STRING,
            ui_group="Test Group",
        )
        registry.register(col)

        result = registry.get_by_group("Test Group")

        assert len(result) >= 1
        assert any(c.name == "grouped_test_col" for c in result)

    def test_get_by_group_returns_empty_for_unknown_group(self) -> None:
        """get_by_group() returns empty list for unknown group."""
        registry = ColumnRegistry()

        result = registry.get_by_group("Nonexistent Group XYZ")

        assert result == []

    def test_get_all_groups_returns_group_names(self) -> None:
        """get_all_groups() returns list of group names."""
        registry = ColumnRegistry()

        result = registry.get_all_groups()

        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(g, str) for g in result)

    def test_get_exportable_returns_exportable_columns(self) -> None:
        """get_exportable() returns only exportable columns."""
        registry = ColumnRegistry()

        result = registry.get_exportable()

        assert all(c.is_exportable for c in result)

    def test_get_exportable_sorted_by_ui_order(self) -> None:
        """get_exportable() returns columns sorted by ui_order."""
        registry = ColumnRegistry()

        result = registry.get_exportable()

        if len(result) >= 2:
            for i in range(len(result) - 1):
                assert result[i].ui_order <= result[i + 1].ui_order

    def test_get_groups_with_exportable_columns(self) -> None:
        """get_groups_with_exportable_columns() returns groups with export column names."""
        registry = ColumnRegistry()

        result = registry.get_groups_with_exportable_columns()

        assert isinstance(result, dict)
        for group_name, column_names in result.items():
            assert isinstance(group_name, str)
            assert isinstance(column_names, list)


class TestModuleFunctions:
    """Tests for module-level functions."""

    def test_get_column_registry_returns_global_instance(self) -> None:
        """get_column_registry() returns global registry instance."""
        result = get_column_registry()

        assert result is column_registry

    def test_register_custom_column_adds_to_global(self) -> None:
        """register_custom_column() adds to global registry."""
        col = ColumnDefinition(
            name="global_custom_col_test",
            display_name="Global Custom",
            column_type=ColumnType.CUSTOM,
            data_type=DataType.STRING,
        )

        # Only register if not already registered
        if column_registry.get("global_custom_col_test") is None:
            register_custom_column(col)

        assert column_registry.get("global_custom_col_test") is not None

    def test_global_registry_has_metadata_columns(self) -> None:
        """Global registry has metadata columns registered."""
        registry = get_column_registry()

        # Should have at least some columns in the registry
        all_cols = registry.get_all()
        metadata_cols = [c for c in all_cols if c.column_type == ColumnType.METADATA]

        assert len(metadata_cols) > 0

    def test_global_registry_has_marker_columns(self) -> None:
        """Global registry has marker columns registered."""
        registry = get_column_registry()

        all_cols = registry.get_all()
        marker_cols = [c for c in all_cols if c.column_type == ColumnType.MARKER]

        assert len(marker_cols) > 0
