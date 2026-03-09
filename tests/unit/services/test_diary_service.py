"""
Tests for DiaryService.

Tests sleep diary management and parsing.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from sleep_scoring_app.services.diary_service import DiaryService


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock DatabaseManager."""
    manager = MagicMock()
    manager.db_path = ":memory:"
    manager._validate_table_name = MagicMock(side_effect=lambda x: x)
    manager._validate_column_name = MagicMock(side_effect=lambda x: x)
    return manager


@pytest.fixture
def service(mock_db_manager: MagicMock) -> DiaryService:
    """Create a DiaryService instance."""
    return DiaryService(mock_db_manager)


class TestDiaryServiceInit:
    """Tests for DiaryService initialization."""

    def test_initializes_with_db_manager(self, mock_db_manager: MagicMock) -> None:
        """Initializes with database manager."""
        service = DiaryService(mock_db_manager)

        assert service.db_manager is mock_db_manager

    def test_creates_orchestrator(self, service: DiaryService) -> None:
        """Creates import orchestrator."""
        assert service._import_orchestrator is not None

    def test_creates_query_service(self, service: DiaryService) -> None:
        """Creates query service."""
        assert service._query_service is not None


class TestImportDiaryFiles:
    """Tests for import_diary_files method."""

    def test_delegates_to_orchestrator(self, service: DiaryService) -> None:
        """Delegates to orchestrator."""
        with patch.object(service._import_orchestrator, "import_diary_files") as mock_import:
            mock_result = MagicMock()
            mock_import.return_value = mock_result

            result = service.import_diary_files([Path("/path/to/file.csv")])

        assert result is mock_result
        mock_import.assert_called_once()

    def test_passes_progress_callback(self, service: DiaryService) -> None:
        """Passes progress callback to orchestrator."""
        callback = MagicMock()

        with patch.object(service._import_orchestrator, "import_diary_files") as mock_import:
            mock_import.return_value = MagicMock()

            service.import_diary_files([Path("/path/to/file.csv")], progress_callback=callback)

        call_kwargs = mock_import.call_args
        assert call_kwargs is not None


class TestGetDiaryDataForParticipant:
    """Tests for get_diary_data_for_participant method."""

    def test_delegates_to_query_service(self, service: DiaryService) -> None:
        """Delegates to query service."""
        with patch.object(service._query_service, "get_diary_data_for_participant") as mock_query:
            mock_entries = [MagicMock(), MagicMock()]
            mock_query.return_value = mock_entries

            result = service.get_diary_data_for_participant("1234")

        assert result is mock_entries
        mock_query.assert_called_once_with("1234", None)

    def test_passes_date_range(self, service: DiaryService) -> None:
        """Passes date range to query service."""
        date_range = (datetime(2024, 1, 1), datetime(2024, 1, 31))

        with patch.object(service._query_service, "get_diary_data_for_participant") as mock_query:
            mock_query.return_value = []

            service.get_diary_data_for_participant("1234", date_range=date_range)

        mock_query.assert_called_once_with("1234", date_range)


class TestGetDiaryDataForDate:
    """Tests for get_diary_data_for_date method."""

    def test_delegates_to_query_service(self, service: DiaryService) -> None:
        """Delegates to query service."""
        target_date = datetime(2024, 1, 15)

        with patch.object(service._query_service, "get_diary_data_for_date") as mock_query:
            mock_entry = MagicMock()
            mock_query.return_value = mock_entry

            result = service.get_diary_data_for_date("1234", target_date)

        assert result is mock_entry
        mock_query.assert_called_once_with("1234", target_date)


class TestCheckParticipantHasDiaryData:
    """Tests for check_participant_has_diary_data method."""

    def test_delegates_to_query_service(self, service: DiaryService) -> None:
        """Delegates to query service."""
        with patch.object(service._query_service, "check_participant_has_diary_data") as mock_check:
            mock_check.return_value = True

            result = service.check_participant_has_diary_data("1234")

        assert result is True
        mock_check.assert_called_once_with("1234")


class TestGetAvailableParticipants:
    """Tests for get_available_participants method."""

    def test_delegates_to_query_service(self, service: DiaryService) -> None:
        """Delegates to query service."""
        with patch.object(service._query_service, "get_available_participants") as mock_get:
            mock_get.return_value = ["1234", "5678"]

            result = service.get_available_participants()

        assert result == ["1234", "5678"]
        mock_get.assert_called_once()


class TestGetDiaryStats:
    """Tests for get_diary_stats method."""

    def test_delegates_to_query_service(self, service: DiaryService) -> None:
        """Delegates to query service."""
        with patch.object(service._query_service, "get_diary_stats") as mock_stats:
            mock_stats.return_value = {"total_entries": 100}

            result = service.get_diary_stats()

        assert result == {"total_entries": 100}
        mock_stats.assert_called_once()


class TestProgressProperty:
    """Tests for progress property."""

    def test_returns_orchestrator_progress(self, service: DiaryService) -> None:
        """Access orchestrator's progress directly."""
        progress = service._import_orchestrator.progress

        assert progress is not None
