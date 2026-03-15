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


# =============================================================================
# Additional export service tests for higher coverage
# =============================================================================


class TestEmptyMetricFields:
    """Tests for _empty_metric_fields helper."""

    def test_default_empty_fields(self):
        from sleep_scoring_web.services.export_service import _empty_metric_fields

        fields = _empty_metric_fields()
        assert fields["Time in Bed (min)"] == ""
        assert fields["Total Sleep Time (min)"] == ""
        assert fields["WASO (min)"] == ""
        assert fields["Sleep Onset Latency (min)"] == ""
        assert fields["Number of Awakenings"] == ""
        assert fields["Avg Awakening Length (min)"] == ""
        assert fields["Sleep Efficiency (%)"] == ""
        assert fields["Movement Index"] == ""
        assert fields["Fragmentation Index"] == ""
        assert fields["Sleep Fragmentation Index"] == ""
        assert fields["Total Activity Counts"] == ""
        assert fields["Non-zero Epochs"] == ""
        assert fields["Algorithm"] == ""
        assert fields["Detection Rule"] == ""
        assert fields["Verification Status"] == ""

    def test_custom_detection_rule(self):
        from sleep_scoring_web.services.export_service import _empty_metric_fields

        fields = _empty_metric_fields(detection_rule="3 Epochs / 5 Min")
        assert fields["Detection Rule"] == "3 Epochs / 5 Min"

    def test_custom_verification_status(self):
        from sleep_scoring_web.services.export_service import _empty_metric_fields

        fields = _empty_metric_fields(verification_status="Verified")
        assert fields["Verification Status"] == "Verified"


class TestDisplayMaps:
    """Tests for display mapping dictionaries."""

    def test_marker_type_display(self):
        from sleep_scoring_web.services.export_service import _MARKER_TYPE_DISPLAY

        from sleep_scoring_web.schemas.enums import MarkerType

        assert _MARKER_TYPE_DISPLAY[MarkerType.MAIN_SLEEP] == "Main Sleep"
        assert _MARKER_TYPE_DISPLAY[MarkerType.NAP] == "Nap"
        assert _MARKER_TYPE_DISPLAY[MarkerType.MANUAL_NONWEAR] == "Manual Nonwear"

    def test_algorithm_display(self):
        from sleep_scoring_web.services.export_service import _ALGORITHM_DISPLAY

        from sleep_scoring_web.schemas.enums import AlgorithmType

        assert _ALGORITHM_DISPLAY[AlgorithmType.SADEH_1994_ACTILIFE] == "Sadeh 1994 (ActiLife)"
        assert _ALGORITHM_DISPLAY[AlgorithmType.COLE_KRIPKE_1992_ORIGINAL] == "Cole-Kripke 1992 (Original)"
        assert _ALGORITHM_DISPLAY[AlgorithmType.MANUAL] == "Manual"

    def test_detection_rule_display(self):
        from sleep_scoring_web.services.export_service import _DETECTION_RULE_DISPLAY

        from sleep_scoring_web.schemas.enums import SleepPeriodDetectorType

        assert _DETECTION_RULE_DISPLAY[SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S] == "3 Epochs / 5 Min"
        assert _DETECTION_RULE_DISPLAY[SleepPeriodDetectorType.TUDOR_LOCKE_2014] == "Tudor-Locke 2014"

    def test_verification_display(self):
        from sleep_scoring_web.services.export_service import _VERIFICATION_DISPLAY

        from sleep_scoring_web.schemas.enums import VerificationStatus

        assert _VERIFICATION_DISPLAY[VerificationStatus.DRAFT] == "Draft"
        assert _VERIFICATION_DISPLAY[VerificationStatus.SUBMITTED] == "Submitted"
        assert _VERIFICATION_DISPLAY[VerificationStatus.VERIFIED] == "Verified"
        assert _VERIFICATION_DISPLAY[VerificationStatus.DISPUTED] == "Disputed"
        assert _VERIFICATION_DISPLAY[VerificationStatus.RESOLVED] == "Resolved"


class TestExportResultDataclass:
    """Tests for ExportResult dataclass."""

    def test_default_values(self):
        from sleep_scoring_web.services.export_service import ExportResult

        result = ExportResult(success=False)
        assert result.success is False
        assert result.csv_content == ""
        assert result.filename == ""
        assert result.row_count == 0
        assert result.file_count == 0
        assert result.warnings == []
        assert result.errors == []
        assert result.nonwear_csv_content == ""
        assert result.nonwear_row_count == 0
        assert result.nonwear_filename == ""

    def test_mutable_lists(self):
        from sleep_scoring_web.services.export_service import ExportResult

        r1 = ExportResult(success=True)
        r2 = ExportResult(success=True)
        r1.warnings.append("warning1")
        # r2 should not be affected (mutable default factory)
        assert r2.warnings == []


class TestCSVSanitizationEdgeCases:
    """Additional sanitization edge cases."""

    def test_tab_injection(self):
        assert ExportService._sanitize_csv_value("\tcmd") == "'\tcmd"

    def test_carriage_return_injection(self):
        assert ExportService._sanitize_csv_value("\rcmd") == "'\rcmd"

    def test_empty_string_not_sanitized(self):
        assert ExportService._sanitize_csv_value("") == ""

    def test_boolean_passthrough(self):
        assert ExportService._sanitize_csv_value(True) is True
        assert ExportService._sanitize_csv_value(False) is False


class TestCSVGenerationRealData:
    """CSV generation with realistic export row data."""

    def _make_service(self):
        class MockService(ExportService):
            def __init__(self):
                pass
        return MockService()

    def test_generate_csv_with_export_columns(self):
        """Simulate a realistic export row and verify CSV output."""
        import csv
        import io

        service = self._make_service()

        rows = [
            {
                "Filename": "1000 T1 (2024-01-01)60sec.csv",
                "File ID": 1,
                "Participant ID": "1000",
                "Study Date": "2024-01-01",
                "Period Index": 0,
                "Marker Type": "Main Sleep",
                "Onset Time": "22:30",
                "Offset Time": "06:15",
                "Onset Datetime": "2024-01-01 22:30:00",
                "Offset Datetime": "2024-01-02 06:15:00",
                "Time in Bed (min)": "465.00",
                "Total Sleep Time (min)": "420.50",
                "WASO (min)": "30.25",
                "Sleep Onset Latency (min)": "14.25",
                "Number of Awakenings": 5,
                "Avg Awakening Length (min)": "6.05",
                "Sleep Efficiency (%)": "90.43",
                "Movement Index": "12.30",
                "Fragmentation Index": "8.50",
                "Sleep Fragmentation Index": "20.80",
                "Total Activity Counts": 15432,
                "Non-zero Epochs": 75,
                "Algorithm": "Sadeh 1994 (ActiLife)",
                "Detection Rule": "3 Epochs / 5 Min",
                "Verification Status": "Draft",
                "Scored By": "testadmin",
                "Is No Sleep": "False",
                "Needs Consensus": "False",
                "Notes": "",
            }
        ]

        columns = [
            "Filename", "Study Date", "Period Index", "Marker Type",
            "Onset Time", "Offset Time", "Total Sleep Time (min)",
            "Sleep Efficiency (%)", "Algorithm",
        ]

        csv_content = service._generate_csv(rows, columns, include_header=True)

        # Parse with csv module to validate structure
        reader = csv.DictReader(io.StringIO(csv_content))
        parsed_rows = list(reader)
        assert len(parsed_rows) == 1

        row = parsed_rows[0]
        assert row["Filename"] == "1000 T1 (2024-01-01)60sec.csv"
        assert row["Study Date"] == "2024-01-01"
        assert row["Total Sleep Time (min)"] == "420.50"
        assert row["Algorithm"] == "Sadeh 1994 (ActiLife)"

    def test_generate_csv_no_sleep_sentinel_row(self):
        """No-sleep sentinel rows should have empty marker/metric fields."""
        import csv
        import io

        service = self._make_service()

        from sleep_scoring_web.services.export_service import _empty_metric_fields

        rows = [
            {
                "Filename": "1000 T1.csv",
                "File ID": 1,
                "Participant ID": "1000",
                "Study Date": "2024-01-02",
                "Period Index": "",
                "Marker Type": "",
                "Onset Time": "",
                "Offset Time": "",
                "Onset Datetime": "",
                "Offset Datetime": "",
                "Scored By": "testadmin",
                "Is No Sleep": "True",
                "Needs Consensus": "False",
                "Notes": "",
                **_empty_metric_fields(),
            }
        ]

        columns = ["Filename", "Study Date", "Is No Sleep", "Marker Type", "Onset Time"]
        csv_content = service._generate_csv(rows, columns)

        reader = csv.DictReader(io.StringIO(csv_content))
        parsed = list(reader)
        assert len(parsed) == 1
        assert parsed[0]["Is No Sleep"] == "True"
        assert parsed[0]["Marker Type"] == ""
        assert parsed[0]["Onset Time"] == ""

    def test_metadata_header_content(self):
        """Metadata should include key comment lines."""
        service = self._make_service()

        rows = [
            {"Filename": "a.csv", "File ID": 1},
            {"Filename": "b.csv", "File ID": 2},
        ]

        csv_content = service._generate_csv(rows, ["Filename"], include_metadata=True)

        assert "# Sleep Scoring Export" in csv_content
        assert "# Total Rows: 2" in csv_content
        assert "# Files: 2" in csv_content


class TestExportCSVEmptyFileIds:
    """Test export_csv with empty file_ids."""

    @pytest.mark.asyncio
    async def test_no_files_returns_error(self):
        from unittest.mock import AsyncMock

        mock_db = AsyncMock()
        service = ExportService(mock_db)
        result = await service.export_csv(file_ids=[])
        assert result.success is False
        assert len(result.errors) > 0
        assert "No files specified" in result.errors[0]

    @pytest.mark.asyncio
    async def test_invalid_columns_skipped(self):
        """Invalid columns should be skipped with a warning, not cause failure."""
        from unittest.mock import AsyncMock, MagicMock

        mock_db = AsyncMock()
        service = ExportService(mock_db)

        # Use only invalid columns
        result = await service.export_csv(
            file_ids=[1],
            columns=["InvalidCol1", "InvalidCol2"],
        )
        assert result.success is False
        assert any("No valid columns" in e for e in result.errors)

    @pytest.mark.asyncio
    async def test_mixed_valid_invalid_columns(self):
        """Mix of valid and invalid columns should warn and proceed."""
        from unittest.mock import AsyncMock, MagicMock

        # Need to mock the fetch to return empty data
        mock_db = AsyncMock()
        mock_execute_result = MagicMock()
        mock_execute_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_execute_result

        service = ExportService(mock_db)
        result = await service.export_csv(
            file_ids=[1],
            columns=["Filename", "BogusColumn", "Study Date"],
        )
        # Should have a warning about invalid columns
        assert any("Skipping invalid columns" in w for w in result.warnings)
