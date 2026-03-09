"""
Unit tests for DataSourceFactory dependency injection.

Tests the factory pattern implementation for data source loaders.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.core.constants import DataSourceType
from sleep_scoring_app.io.sources.loader_factory import DataSourceFactory
from sleep_scoring_app.io.sources.loader_protocol import DataSourceLoader


class TestDataSourceFactoryCreation:
    """Tests for data source loader creation via factory."""

    def test_create_csv_loader(self) -> None:
        """Test creating CSV data source loader."""
        loader = DataSourceFactory.create("csv")
        assert loader is not None
        assert loader.name == "CSV/XLSX File Loader"
        assert isinstance(loader, DataSourceLoader)

    def test_create_gt3x_loader(self) -> None:
        """Test creating GT3X data source loader."""
        loader = DataSourceFactory.create("gt3x")
        assert loader is not None
        # Name varies based on whether gt3x-rs is available
        assert "GT3X" in loader.name
        assert isinstance(loader, DataSourceLoader)

    def test_create_invalid_loader_raises(self) -> None:
        """Test that creating unknown loader raises ValueError."""
        with pytest.raises(ValueError, match="Unknown data source loader"):
            DataSourceFactory.create("nonexistent_loader")

    def test_create_returns_new_instance_each_time(self) -> None:
        """Test that each create call returns a new instance."""
        loader1 = DataSourceFactory.create("csv")
        loader2 = DataSourceFactory.create("csv")
        assert loader1 is not loader2


class TestDataSourceFactoryRegistry:
    """Tests for factory registry operations."""

    def test_factory_has_expected_loaders(self) -> None:
        """Test that factory has csv and gt3x loaders registered."""
        available = DataSourceFactory.get_available_loaders()
        assert "csv" in available
        assert "gt3x" in available

    def test_get_available_loaders_returns_dict(self) -> None:
        """Test that get_available_loaders returns a dictionary."""
        available = DataSourceFactory.get_available_loaders()
        assert isinstance(available, dict)
        assert len(available) >= 2  # At least csv and gt3x

    def test_get_available_loaders_returns_display_names(self) -> None:
        """Test that available loaders dict has display names as values."""
        available = DataSourceFactory.get_available_loaders()
        assert available["csv"] == "CSV/XLSX File Loader"
        # GT3X loader name varies based on whether gt3x-rs is available
        assert "GT3X File Loader" in available["gt3x"]

    def test_is_registered_csv(self) -> None:
        """Test is_registered returns True for csv."""
        assert DataSourceFactory.is_registered("csv") is True

    def test_is_registered_gt3x(self) -> None:
        """Test is_registered returns True for gt3x."""
        assert DataSourceFactory.is_registered("gt3x") is True

    def test_is_registered_invalid(self) -> None:
        """Test is_registered returns False for unregistered loaders."""
        assert DataSourceFactory.is_registered("nonexistent") is False
        assert DataSourceFactory.is_registered("") is False
        assert DataSourceFactory.is_registered("geneactiv") is False

    def test_get_default_loader_id(self) -> None:
        """Test getting default loader ID."""
        default_id = DataSourceFactory.get_default_loader_id()
        assert default_id == "csv"
        assert DataSourceFactory.is_registered(default_id)


class TestDataSourceFactoryExtensionMapping:
    """Tests for file extension-based loader selection."""

    def test_get_loader_for_extension_csv(self) -> None:
        """Test getting loader for .csv extension."""
        loader = DataSourceFactory.get_loader_for_extension(".csv")
        assert loader.identifier == "csv"

    def test_get_loader_for_extension_xlsx(self) -> None:
        """Test getting loader for .xlsx extension."""
        loader = DataSourceFactory.get_loader_for_extension(".xlsx")
        assert loader.identifier == "csv"

    def test_get_loader_for_extension_xls(self) -> None:
        """Test getting loader for .xls extension."""
        loader = DataSourceFactory.get_loader_for_extension(".xls")
        assert loader.identifier == "csv"

    def test_get_loader_for_extension_gt3x(self) -> None:
        """Test getting loader for .gt3x extension."""
        loader = DataSourceFactory.get_loader_for_extension(".gt3x")
        # Identifier may be "gt3x" or "gt3x_rs" depending on which is available
        assert loader.identifier in ("gt3x", "gt3x_rs")

    def test_get_loader_for_extension_unknown(self) -> None:
        """Test that unknown extension raises ValueError."""
        with pytest.raises(ValueError, match="No loader found for extension"):
            DataSourceFactory.get_loader_for_extension(".unknown")

    def test_get_loader_for_extension_normalizes_case(self) -> None:
        """Test that extension matching is case-insensitive."""
        loader1 = DataSourceFactory.get_loader_for_extension(".CSV")
        loader2 = DataSourceFactory.get_loader_for_extension(".csv")
        assert loader1.identifier == loader2.identifier == "csv"

    def test_get_loader_for_extension_handles_no_dot(self) -> None:
        """Test that extension matching works without leading dot."""
        loader = DataSourceFactory.get_loader_for_extension("csv")
        assert loader.identifier == "csv"

    def test_get_supported_extensions(self) -> None:
        """Test getting all supported extensions."""
        extensions = DataSourceFactory.get_supported_extensions()
        assert isinstance(extensions, set)
        assert ".csv" in extensions
        assert ".xlsx" in extensions
        assert ".xls" in extensions
        assert ".gt3x" in extensions


class TestDataSourceFactoryFilePathMapping:
    """Tests for file path-based loader selection."""

    def test_get_loader_for_file_csv(self) -> None:
        """Test getting loader for CSV file path."""
        loader = DataSourceFactory.get_loader_for_file("/data/activity.csv")
        assert loader.identifier == "csv"

    def test_get_loader_for_file_gt3x(self) -> None:
        """Test getting loader for GT3X file path."""
        loader = DataSourceFactory.get_loader_for_file("/data/activity.gt3x")
        # Identifier may be "gt3x" or "gt3x_rs" depending on which is available
        assert loader.identifier in ("gt3x", "gt3x_rs")

    def test_get_loader_for_file_pathlib(self) -> None:
        """Test getting loader with pathlib.Path object."""
        from pathlib import Path

        loader = DataSourceFactory.get_loader_for_file(Path("/data/activity.xlsx"))
        assert loader.identifier == "csv"


class TestDataSourceTypeEnumAlignment:
    """Tests that DataSourceType enum values match factory registered IDs."""

    def test_datasource_type_enum_matches_factory(self) -> None:
        """Test DataSourceType enum values match factory registered IDs."""
        factory_ids = set(DataSourceFactory.get_available_loaders().keys())

        # Core data source types should be in factory
        assert DataSourceType.CSV.value in factory_ids
        assert DataSourceType.GT3X.value in factory_ids

    def test_create_from_enum_value(self) -> None:
        """Test creating loaders using enum values."""
        # CSV loader
        csv_loader = DataSourceFactory.create(DataSourceType.CSV.value)
        assert csv_loader is not None
        assert csv_loader.identifier == "csv"

        # GT3X loader - may return gt3x_rs if Rust backend is available
        gt3x_loader = DataSourceFactory.create(DataSourceType.GT3X.value)
        assert gt3x_loader is not None
        assert gt3x_loader.identifier in ("gt3x", "gt3x_rs")

    def test_enum_default_matches_factory_default(self) -> None:
        """Test that DataSourceType default matches factory default."""
        enum_default = DataSourceType.get_default()
        factory_default = DataSourceFactory.get_default_loader_id()
        assert enum_default.value == factory_default


class TestDataSourceLoaderBehavior:
    """Tests for loader behavior from factory."""

    def test_csv_loader_properties(self) -> None:
        """Test CSV loader has correct properties."""
        loader = DataSourceFactory.create("csv")
        assert loader.name == "CSV/XLSX File Loader"
        assert loader.identifier == "csv"
        assert ".csv" in loader.supported_extensions
        assert ".xlsx" in loader.supported_extensions
        assert ".xls" in loader.supported_extensions

    def test_gt3x_loader_properties(self) -> None:
        """Test GT3X loader has correct properties."""
        loader = DataSourceFactory.create("gt3x")
        # Name and identifier vary based on whether gt3x-rs is available
        assert "GT3X" in loader.name
        assert loader.identifier in ("gt3x", "gt3x_rs")
        assert ".gt3x" in loader.supported_extensions

    def test_all_loaders_have_load_file_method(self) -> None:
        """Test all loaders implement load_file method."""
        for loader_id in DataSourceFactory.get_available_loaders():
            loader = DataSourceFactory.create(loader_id)
            assert hasattr(loader, "load_file")
            assert callable(loader.load_file)

    def test_all_loaders_have_detect_columns_method(self) -> None:
        """Test all loaders implement detect_columns method."""
        for loader_id in DataSourceFactory.get_available_loaders():
            loader = DataSourceFactory.create(loader_id)
            assert hasattr(loader, "detect_columns")
            assert callable(loader.detect_columns)

    def test_all_loaders_have_validate_data_method(self) -> None:
        """Test all loaders implement validate_data method."""
        for loader_id in DataSourceFactory.get_available_loaders():
            loader = DataSourceFactory.create(loader_id)
            assert hasattr(loader, "validate_data")
            assert callable(loader.validate_data)

    def test_all_loaders_have_get_file_metadata_method(self) -> None:
        """Test all loaders implement get_file_metadata method."""
        for loader_id in DataSourceFactory.get_available_loaders():
            loader = DataSourceFactory.create(loader_id)
            assert hasattr(loader, "get_file_metadata")
            assert callable(loader.get_file_metadata)

    def test_all_loaders_have_name_property(self) -> None:
        """Test all loaders have name property."""
        for loader_id in DataSourceFactory.get_available_loaders():
            loader = DataSourceFactory.create(loader_id)
            assert hasattr(loader, "name")
            assert isinstance(loader.name, str)
            assert len(loader.name) > 0

    def test_all_loaders_have_identifier_property(self) -> None:
        """Test all loaders have identifier property."""
        for loader_id in DataSourceFactory.get_available_loaders():
            loader = DataSourceFactory.create(loader_id)
            assert hasattr(loader, "identifier")
            assert isinstance(loader.identifier, str)
            # "gt3x" may return "gt3x_rs" loader when Rust backend is available
            # "gt3x_pygt3x" is the fallback pygt3x loader with identifier "gt3x"
            if loader_id in ("gt3x", "gt3x_pygt3x"):
                assert loader.identifier in ("gt3x", "gt3x_rs")
            else:
                assert loader.identifier == loader_id

    def test_all_loaders_have_supported_extensions_property(self) -> None:
        """Test all loaders have supported_extensions property."""
        for loader_id in DataSourceFactory.get_available_loaders():
            loader = DataSourceFactory.create(loader_id)
            assert hasattr(loader, "supported_extensions")
            # supported_extensions can be set or frozenset
            assert isinstance(loader.supported_extensions, set | frozenset)
            assert len(loader.supported_extensions) > 0
