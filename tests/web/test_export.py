"""
Tests for the export service and API endpoints.
"""

import pytest

from sleep_scoring_web.services.export_service import (
    COLUMN_CATEGORIES,
    DEFAULT_COLUMNS,
    EXPORT_COLUMNS,
    ColumnDefinition,
    ExportService,
)


class TestColumnRegistry:
    """Tests for the export column registry."""

    def test_export_columns_defined(self):
        """All expected column categories should be defined."""
        assert len(EXPORT_COLUMNS) > 0
        assert len(COLUMN_CATEGORIES) > 0

    def test_all_columns_have_required_fields(self):
        """Each column definition should have all required fields."""
        for col in EXPORT_COLUMNS:
            assert isinstance(col, ColumnDefinition)
            assert col.name, "Column name should not be empty"
            assert col.category, "Column category should not be empty"
            assert col.description, "Column description should not be empty"
            assert col.data_type in ["string", "number", "datetime", "boolean"]

    def test_column_categories_match_columns(self):
        """All columns in categories should exist in EXPORT_COLUMNS."""
        all_column_names = {col.name for col in EXPORT_COLUMNS}

        for category, columns in COLUMN_CATEGORIES.items():
            for col_name in columns:
                assert col_name in all_column_names, f"Column '{col_name}' in category '{category}' not found"

    def test_default_columns_are_valid(self):
        """All default columns should exist in EXPORT_COLUMNS."""
        all_column_names = {col.name for col in EXPORT_COLUMNS}

        for col_name in DEFAULT_COLUMNS:
            assert col_name in all_column_names, f"Default column '{col_name}' not found"

    def test_expected_categories_exist(self):
        """Expected column categories should be present."""
        expected_categories = [
            "File Info",
            "Period Info",
            "Time Markers",
            "Duration Metrics",
            "Quality Indices",
        ]

        for category in expected_categories:
            assert category in COLUMN_CATEGORIES, f"Expected category '{category}' not found"

    def test_expected_columns_exist(self):
        """Key columns should be present."""
        column_names = {col.name for col in EXPORT_COLUMNS}

        expected_columns = [
            "Filename",
            "Study Date",
            "Onset Time",
            "Offset Time",
            "Total Sleep Time (min)",
            "Sleep Efficiency (%)",
            "WASO (min)",
            "Algorithm",
        ]

        for col_name in expected_columns:
            assert col_name in column_names, f"Expected column '{col_name}' not found"


class TestExportService:
    """Tests for the ExportService class."""

    def test_get_available_columns(self):
        """Should return all available columns."""
        columns = ExportService.get_available_columns()
        assert len(columns) == len(EXPORT_COLUMNS)

    def test_get_column_categories(self):
        """Should return categories with columns."""
        categories = ExportService.get_column_categories()
        assert len(categories) > 0

        # Each category should have at least one column
        for category, columns in categories.items():
            assert len(columns) > 0, f"Category '{category}' has no columns"

    def test_get_default_columns(self):
        """Should return default column names."""
        defaults = ExportService.get_default_columns()
        assert len(defaults) > 0
        assert all(isinstance(col, str) for col in defaults)

    def test_sanitize_csv_value_normal_string(self):
        """Normal strings should pass through unchanged."""
        assert ExportService._sanitize_csv_value("normal text") == "normal text"
        assert ExportService._sanitize_csv_value("123") == "123"
        assert ExportService._sanitize_csv_value("file.csv") == "file.csv"

    def test_sanitize_csv_value_formula_injection(self):
        """Potential formula injection should be escaped."""
        # These characters at the start of a cell could be interpreted as formulas
        assert ExportService._sanitize_csv_value("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
        assert ExportService._sanitize_csv_value("+1+1") == "'+1+1"
        assert ExportService._sanitize_csv_value("-1-1") == "'-1-1"
        assert ExportService._sanitize_csv_value("@SUM(A1:A10)") == "'@SUM(A1:A10)"

    def test_sanitize_csv_value_non_string(self):
        """Non-string values should pass through unchanged."""
        assert ExportService._sanitize_csv_value(123) == 123
        assert ExportService._sanitize_csv_value(45.67) == 45.67
        assert ExportService._sanitize_csv_value(None) is None

    def test_format_number_none(self):
        """None should return empty string."""
        assert ExportService._format_number(None) == ""

    def test_format_number_integer(self):
        """Integers should be formatted without decimals."""
        assert ExportService._format_number(42) == "42"
        assert ExportService._format_number(0) == "0"

    def test_format_number_float(self):
        """Floats should be formatted with specified precision."""
        assert ExportService._format_number(42.1234) == "42.12"
        assert ExportService._format_number(42.1234, precision=1) == "42.1"
        assert ExportService._format_number(0.005, precision=3) == "0.005"


class TestCSVGeneration:
    """Tests for CSV generation functionality."""

    def test_generate_csv_empty_rows(self):
        """Empty rows should produce empty CSV."""

        # Create a mock service (without DB)
        class MockService(ExportService):
            def __init__(self):
                pass  # Skip DB init

        service = MockService()
        csv_content = service._generate_csv([], ["Column1", "Column2"])
        lines = csv_content.strip().split("\n")
        assert len(lines) == 1  # Just header
        assert "Column1" in lines[0]

    def test_generate_csv_with_data(self):
        """Should generate valid CSV with data."""

        class MockService(ExportService):
            def __init__(self):
                pass

        service = MockService()
        rows = [
            {"Name": "Test1", "Value": 42},
            {"Name": "Test2", "Value": 100},
        ]
        csv_content = service._generate_csv(rows, ["Name", "Value"])
        lines = csv_content.strip().split("\n")

        assert len(lines) == 3  # Header + 2 rows
        assert "Name,Value" in lines[0]
        assert "Test1,42" in lines[1]

    def test_generate_csv_with_metadata(self):
        """Should include metadata comments when requested."""

        class MockService(ExportService):
            def __init__(self):
                pass

        service = MockService()
        rows = [{"Name": "Test1"}]
        csv_content = service._generate_csv(rows, ["Name"], include_header=True, include_metadata=True)

        assert csv_content.startswith("#")
        assert "Sleep Scoring Export" in csv_content

    def test_generate_csv_without_header(self):
        """Should omit header when requested."""

        class MockService(ExportService):
            def __init__(self):
                pass

        service = MockService()
        rows = [{"Name": "Test1", "Value": 42}]
        csv_content = service._generate_csv(rows, ["Name", "Value"], include_header=False)
        lines = csv_content.strip().split("\n")

        assert len(lines) == 1  # Just data, no header
        assert "Test1,42" in lines[0]

    def test_generate_csv_filters_columns(self):
        """Should only include specified columns."""

        class MockService(ExportService):
            def __init__(self):
                pass

        service = MockService()
        rows = [{"A": 1, "B": 2, "C": 3}]
        csv_content = service._generate_csv(rows, ["A", "C"])
        lines = csv_content.strip().split("\n")

        assert "A,C" in lines[0]
        assert "B" not in lines[0]
