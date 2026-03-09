"""
Tests for DiaryQueryService.

Tests diary data retrieval operations.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.services.diary.query_service import DiaryQueryService


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock DatabaseManager."""
    manager = MagicMock()
    manager.db_path = ":memory:"
    manager._validate_table_name = MagicMock(side_effect=lambda x: x)
    manager._validate_column_name = MagicMock(side_effect=lambda x: x)
    return manager


@pytest.fixture
def service(mock_db_manager: MagicMock) -> DiaryQueryService:
    """Create a DiaryQueryService instance."""
    return DiaryQueryService(mock_db_manager)


class TestDiaryQueryServiceInit:
    """Tests for DiaryQueryService initialization."""

    def test_initializes_with_db_manager(self, mock_db_manager: MagicMock) -> None:
        """Initializes with database manager."""
        service = DiaryQueryService(mock_db_manager)

        assert service.db_manager is mock_db_manager


class TestGetDiaryDataForParticipant:
    """Tests for get_diary_data_for_participant method."""

    def test_returns_empty_list_on_no_data(self, service: DiaryQueryService) -> None:
        """Returns empty list when no data found."""
        with (
            patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract,
            patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn,
        ):
            mock_info = MagicMock()
            mock_info.participant_key = "1234_BL_CTRL"
            mock_extract.return_value = mock_info

            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = []
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

            result = service.get_diary_data_for_participant("1234")

        assert result == []

    def test_returns_empty_on_exception(self, service: DiaryQueryService) -> None:
        """Returns empty list on exception."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_extract.side_effect = Exception("Test error")

            result = service.get_diary_data_for_participant("1234")

        assert result == []


class TestGetDiaryDataForDate:
    """Tests for get_diary_data_for_date method."""

    def test_returns_none_on_no_data(self, service: DiaryQueryService) -> None:
        """Returns None when no data found."""
        with (
            patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract,
            patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn,
        ):
            mock_info = MagicMock()
            mock_info.participant_key = "1234_BL_CTRL"
            mock_extract.return_value = mock_info

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

            result = service.get_diary_data_for_date("1234", datetime(2024, 1, 15))

        assert result is None

    def test_returns_none_on_exception(self, service: DiaryQueryService) -> None:
        """Returns None on exception."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_extract.side_effect = Exception("Test error")

            result = service.get_diary_data_for_date("1234", datetime(2024, 1, 15))

        assert result is None


class TestGetAvailableParticipants:
    """Tests for get_available_participants method."""

    def test_returns_participant_list(self, service: DiaryQueryService) -> None:
        """Returns list of participants."""
        with patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [("1234",), ("5678",)]
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

            result = service.get_available_participants()

        assert result == ["1234", "5678"]

    def test_returns_empty_on_exception(self, service: DiaryQueryService) -> None:
        """Returns empty list on exception."""
        with patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn:
            mock_conn.side_effect = Exception("Test error")

            result = service.get_available_participants()

        assert result == []


class TestGetDiaryStats:
    """Tests for get_diary_stats method."""

    def test_returns_stats_dict(self, service: DiaryQueryService) -> None:
        """Returns statistics dictionary."""
        with patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn:
            mock_cursor = MagicMock()
            mock_cursor.fetchone.side_effect = [
                (100,),  # total entries
                (10,),  # unique participants
                ("2024-01-01", "2024-01-31"),  # date range
            ]
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

            result = service.get_diary_stats()

        assert result["total_entries"] == 100
        assert result["unique_participants"] == 10
        assert result["date_range_start"] == "2024-01-01"
        assert result["date_range_end"] == "2024-01-31"

    def test_returns_default_on_exception(self, service: DiaryQueryService) -> None:
        """Returns default stats on exception."""
        with patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn:
            mock_conn.side_effect = Exception("Test error")

            result = service.get_diary_stats()

        assert result["total_entries"] == 0
        assert result["unique_participants"] == 0


class TestCheckParticipantHasDiaryData:
    """Tests for check_participant_has_diary_data method."""

    def test_returns_true_when_data_exists(self, service: DiaryQueryService) -> None:
        """Returns True when participant has diary data."""
        with (
            patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract,
            patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn,
        ):
            mock_info = MagicMock()
            mock_info.participant_key = "1234_BL_CTRL"
            mock_extract.return_value = mock_info

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = (1,)
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

            result = service.check_participant_has_diary_data("1234")

        assert result is True

    def test_returns_false_when_no_data(self, service: DiaryQueryService) -> None:
        """Returns False when no diary data."""
        with (
            patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract,
            patch("sleep_scoring_app.data.repositories.base_repository.BaseRepository._get_connection") as mock_conn,
        ):
            mock_info = MagicMock()
            mock_info.participant_key = "1234_BL_CTRL"
            mock_extract.return_value = mock_info

            mock_cursor = MagicMock()
            mock_cursor.fetchone.return_value = None
            mock_conn.return_value.__enter__.return_value.cursor.return_value = mock_cursor

            result = service.check_participant_has_diary_data("1234")

        assert result is False

    def test_returns_false_on_exception(self, service: DiaryQueryService) -> None:
        """Returns False on exception."""
        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_extract.side_effect = Exception("Test error")

            result = service.check_participant_has_diary_data("1234")

        assert result is False
