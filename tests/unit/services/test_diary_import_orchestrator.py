"""
Tests for DiaryImportOrchestrator.

Tests diary file import orchestration.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sleep_scoring_app.core.exceptions import SleepScoringImportError, ValidationError
from sleep_scoring_app.services.diary.import_orchestrator import DiaryImportOrchestrator


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock DatabaseManager."""
    manager = MagicMock()
    manager.db_path = ":memory:"
    manager._validate_table_name = MagicMock(side_effect=lambda x: x)
    manager._validate_column_name = MagicMock(side_effect=lambda x: x)
    return manager


@pytest.fixture
def orchestrator(mock_db_manager: MagicMock) -> DiaryImportOrchestrator:
    """Create a DiaryImportOrchestrator instance."""
    return DiaryImportOrchestrator(mock_db_manager)


class TestDiaryImportOrchestratorInit:
    """Tests for DiaryImportOrchestrator initialization."""

    def test_initializes_with_db_manager(self, mock_db_manager: MagicMock) -> None:
        """Initializes with database manager."""
        orchestrator = DiaryImportOrchestrator(mock_db_manager)

        assert orchestrator.db_manager is mock_db_manager

    def test_creates_extractor(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Creates data extractor."""
        assert orchestrator._extractor is not None

    def test_creates_progress_tracker(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Creates progress tracker."""
        assert orchestrator._progress is not None


class TestProgressProperty:
    """Tests for progress property."""

    def test_returns_progress_object(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Returns progress object."""
        progress = orchestrator.progress

        assert progress is orchestrator._progress


class TestValidateImportInputs:
    """Tests for _validate_import_inputs method."""

    def test_raises_for_empty_file_list(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Raises ValidationError for empty file list."""
        with pytest.raises(ValidationError):
            orchestrator._validate_import_inputs([])

    def test_raises_for_nonexistent_file(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Raises ValidationError for nonexistent file."""
        with pytest.raises(ValidationError):
            orchestrator._validate_import_inputs([Path("/nonexistent/file.csv")])

    def test_raises_for_unsupported_format(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Raises ValidationError for unsupported format."""
        txt_file = tmp_path / "diary.txt"
        txt_file.write_text("content")

        with pytest.raises(ValidationError):
            orchestrator._validate_import_inputs([txt_file])

    def test_accepts_csv_files(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Accepts CSV files."""
        csv_file = tmp_path / "diary.csv"
        csv_file.write_text("col1,col2\nval1,val2\n")

        # Should not raise
        orchestrator._validate_import_inputs([csv_file])

    def test_accepts_xlsx_files(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Accepts XLSX files."""
        xlsx_file = tmp_path / "diary.xlsx"
        df = pd.DataFrame({"col1": ["val1"]})
        df.to_excel(xlsx_file, index=False)

        # Should not raise
        orchestrator._validate_import_inputs([xlsx_file])


class TestLoadColumnMapping:
    """Tests for _load_column_mapping method."""

    def test_loads_embedded_mapping(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Loads embedded column mapping."""
        mapping = orchestrator._load_column_mapping()

        assert mapping is not None
        assert mapping.participant_id_column_name == "participant_id"

    def test_mapping_has_sleep_columns(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Mapping has sleep onset/offset columns."""
        mapping = orchestrator._load_column_mapping()

        assert mapping.sleep_onset_time_column_name is not None
        assert mapping.sleep_offset_time_column_name is not None


class TestGetExcelSheetNames:
    """Tests for _get_excel_sheet_names method."""

    def test_returns_sheet_names(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Returns sheet names from Excel file."""
        xlsx_file = tmp_path / "multi_sheet.xlsx"
        with pd.ExcelWriter(xlsx_file) as writer:
            pd.DataFrame({"a": [1]}).to_excel(writer, sheet_name="Sheet1", index=False)
            pd.DataFrame({"b": [2]}).to_excel(writer, sheet_name="Sheet2", index=False)

        names = orchestrator._get_excel_sheet_names(xlsx_file)

        assert "Sheet1" in names
        assert "Sheet2" in names

    def test_returns_empty_on_error(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Returns empty list on error."""
        invalid_file = tmp_path / "invalid.xlsx"
        invalid_file.write_bytes(b"not an excel file")

        names = orchestrator._get_excel_sheet_names(invalid_file)

        assert names == []


class TestLoadSheetData:
    """Tests for _load_sheet_data method."""

    def test_loads_csv_data(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Loads data from CSV file."""
        csv_file = tmp_path / "diary.csv"
        csv_file.write_text("participant_id,value\n1234,100\n")

        data = orchestrator._load_sheet_data(csv_file, None)

        assert len(data) == 1
        assert "participant_id" in data.columns

    def test_loads_excel_sheet(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Loads data from Excel sheet."""
        xlsx_file = tmp_path / "diary.xlsx"
        df = pd.DataFrame({"participant_id": ["1234"], "value": [100]})
        df.to_excel(xlsx_file, sheet_name="Data", index=False)

        data = orchestrator._load_sheet_data(xlsx_file, "Data")

        assert len(data) == 1

    def test_raises_for_unsupported_format(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Raises for unsupported file format."""
        txt_file = tmp_path / "diary.txt"
        txt_file.write_text("content")

        with pytest.raises((ValueError, SleepScoringImportError)):
            orchestrator._load_sheet_data(txt_file, None)


class TestCalculateFileHash:
    """Tests for _calculate_file_hash method."""

    def test_returns_hash_string(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Returns hash string."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("test content")

        hash_value = orchestrator._calculate_file_hash(test_file)

        assert isinstance(hash_value, str)
        assert len(hash_value) == 64  # SHA256 hex length

    def test_same_content_same_hash(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Same content produces same hash."""
        file1 = tmp_path / "file1.csv"
        file2 = tmp_path / "file2.csv"
        file1.write_text("identical content")
        file2.write_text("identical content")

        hash1 = orchestrator._calculate_file_hash(file1)
        hash2 = orchestrator._calculate_file_hash(file2)

        assert hash1 == hash2

    def test_different_content_different_hash(self, orchestrator: DiaryImportOrchestrator, tmp_path: Path) -> None:
        """Different content produces different hash."""
        file1 = tmp_path / "file1.csv"
        file2 = tmp_path / "file2.csv"
        file1.write_text("content one")
        file2.write_text("content two")

        hash1 = orchestrator._calculate_file_hash(file1)
        hash2 = orchestrator._calculate_file_hash(file2)

        assert hash1 != hash2


class TestExtractParticipantInfoFromFilename:
    """Tests for _extract_participant_info_from_filename method."""

    def test_extracts_info_from_filename(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Extracts participant info from filename."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_extract.return_value = mock_info

            result = orchestrator._extract_participant_info_from_filename("1234_BL_CTRL.csv")

        assert result is mock_info

    def test_returns_none_on_error(self, orchestrator: DiaryImportOrchestrator) -> None:
        """Returns None on extraction error."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_extract.side_effect = Exception("Parse error")

            result = orchestrator._extract_participant_info_from_filename("invalid")

        assert result is None
