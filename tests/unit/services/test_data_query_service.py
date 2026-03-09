"""
Tests for DataQueryService.

Tests lookups, filtering, and participant info extraction.
"""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.services.data_query_service import DataQueryService


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock DatabaseManager."""
    manager = MagicMock()
    manager.db_path = ":memory:"
    manager.get_import_statistics = MagicMock(
        return_value={
            "total_files": 10,
            "imported_files": 8,
            "total_activity_records": 10000,
        }
    )
    manager.get_available_files = MagicMock(
        return_value=[
            {"filename": "test.csv", "participant_id": "1234", "participant_group": "CTRL", "participant_timepoint": "BL"},
        ]
    )
    return manager


@pytest.fixture
def service(mock_db_manager: MagicMock) -> DataQueryService:
    """Create a DataQueryService instance."""
    return DataQueryService(mock_db_manager)


class TestDataQueryServiceInit:
    """Tests for DataQueryService initialization."""

    def test_initializes_with_db_manager(self, mock_db_manager: MagicMock) -> None:
        """Initializes with database manager."""
        service = DataQueryService(mock_db_manager)

        assert service.db_manager is mock_db_manager

    def test_use_database_enabled_by_default(self, service: DataQueryService) -> None:
        """Database mode enabled by default."""
        assert service.use_database is True


class TestFilterTo24hView:
    """Tests for filter_to_24h_view method."""

    def test_handles_empty_input(self, service: DataQueryService) -> None:
        """Handles empty input gracefully."""
        result_ts, result_act = service.filter_to_24h_view([], [], date(2024, 1, 15))

        assert result_ts == []
        assert result_act == []

    def test_returns_two_lists(self, service: DataQueryService) -> None:
        """Returns tuple of two lists."""
        result = service.filter_to_24h_view([], [], date(2024, 1, 15))

        assert isinstance(result, tuple)
        assert len(result) == 2


class TestExtractEnhancedParticipantInfo:
    """Tests for extract_enhanced_participant_info method."""

    def test_extracts_from_filename(self, service: DataQueryService) -> None:
        """Extracts participant info from filename."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "1234"
            mock_extract.return_value = mock_info

            result = service.extract_enhanced_participant_info("1234_G1_T1.csv")

        assert result is mock_info
        mock_extract.assert_called_once()

    def test_handles_path_input(self, service: DataQueryService) -> None:
        """Handles full path input."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_extract.return_value = mock_info

            result = service.extract_enhanced_participant_info("/path/to/1234.csv")

        assert result is mock_info

    def test_handles_none_input(self, service: DataQueryService) -> None:
        """Handles None input."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_extract.return_value = mock_info

            result = service.extract_enhanced_participant_info(None)

        assert result is mock_info


class TestExtractGroupFromPath:
    """Tests for extract_group_from_path method."""

    def test_extracts_group_from_path(self, service: DataQueryService) -> None:
        """Extracts group from path."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.group_str = "CTRL"
            mock_extract.return_value = mock_info

            result = service.extract_group_from_path("/data/CTRL/1234.csv")

        assert result == "CTRL"

    def test_returns_none_for_default_group(self, service: DataQueryService) -> None:
        """Returns None when group is default G1."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.group_str = "G1"  # Default group
            mock_extract.return_value = mock_info

            result = service.extract_group_from_path("/data/1234.csv")

        assert result is None

    def test_returns_none_for_empty_path(self, service: DataQueryService) -> None:
        """Returns None for empty/None path."""
        result = service.extract_group_from_path(None)

        assert result is None


class TestGetDatabaseStatistics:
    """Tests for get_database_statistics method."""

    def test_returns_statistics_dict(self, service: DataQueryService) -> None:
        """Returns statistics dictionary."""
        stats = service.get_database_statistics()

        assert isinstance(stats, dict)

    def test_includes_file_count(self, service: DataQueryService) -> None:
        """Includes file count in statistics."""
        stats = service.get_database_statistics()

        assert "total_files" in stats

    def test_returns_empty_when_database_disabled(self, service: DataQueryService) -> None:
        """Returns empty stats when database disabled."""
        service.use_database = False

        stats = service.get_database_statistics()

        assert stats["total_files"] == 0


class TestIsFileImported:
    """Tests for is_file_imported method."""

    def test_returns_true_for_imported_file(self, service: DataQueryService, mock_db_manager: MagicMock) -> None:
        """Returns True for imported file."""
        result = service.is_file_imported("test.csv")

        assert result is True

    def test_returns_false_for_missing_file(self, service: DataQueryService, mock_db_manager: MagicMock) -> None:
        """Returns False for non-imported file."""
        result = service.is_file_imported("missing.csv")

        assert result is False

    def test_returns_false_when_database_disabled(self, service: DataQueryService) -> None:
        """Returns False when database disabled."""
        service.use_database = False

        result = service.is_file_imported("test.csv")

        assert result is False


class TestGetParticipantInfoFromDatabase:
    """Tests for get_participant_info_from_database method."""

    def test_returns_participant_dict(self, service: DataQueryService, mock_db_manager: MagicMock) -> None:
        """Returns participant info dictionary."""
        result = service.get_participant_info_from_database("test.csv")

        assert result is not None
        assert "numerical_participant_id" in result

    def test_returns_none_for_missing(self, service: DataQueryService, mock_db_manager: MagicMock) -> None:
        """Returns None for missing participant."""
        result = service.get_participant_info_from_database("unknown.csv")

        assert result is None

    def test_returns_none_when_database_disabled(self, service: DataQueryService) -> None:
        """Returns None when database disabled."""
        service.use_database = False

        result = service.get_participant_info_from_database("test.csv")

        assert result is None


class TestToggleDatabaseMode:
    """Tests for database mode toggle."""

    def test_can_disable_database_mode(self, service: DataQueryService) -> None:
        """Can disable database mode."""
        service.use_database = False

        assert service.use_database is False

    def test_can_enable_database_mode(self, service: DataQueryService) -> None:
        """Can enable database mode."""
        service.use_database = False
        service.use_database = True

        assert service.use_database is True
