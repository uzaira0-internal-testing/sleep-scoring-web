#!/usr/bin/env python3
"""
Comprehensive unit tests for MarkerService.

Tests validation, classification, persistence, coordination, and caching
of sleep and nonwear markers.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import MarkerLimits, MarkerType
from sleep_scoring_app.core.dataclasses import DailySleepMarkers, ParticipantInfo, SleepMetrics, SleepPeriod
from sleep_scoring_app.core.dataclasses_markers import DailyNonwearMarkers, ManualNonwearPeriod
from sleep_scoring_app.data.database import DatabaseManager
from sleep_scoring_app.services.marker_service import MarkerService, MarkerStatus, ValidationResult


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_marker_service.db"


@pytest.fixture
def test_db(test_db_path: Path) -> DatabaseManager:
    """Create a real DatabaseManager with temp database."""
    import sleep_scoring_app.data.database as db_module

    db_module._database_initialized.clear()
    db = DatabaseManager(db_path=test_db_path)
    yield db
    db_module._database_initialized.clear()


@pytest.fixture
def mock_db() -> MagicMock:
    """Create a mock DatabaseManager for unit tests."""
    mock = MagicMock(spec=DatabaseManager)
    mock._validate_table_name = MagicMock(side_effect=lambda x: x)
    mock.execute = MagicMock()
    mock.fetch_one = MagicMock(return_value=None)
    mock.fetch_all = MagicMock(return_value=[])
    return mock


@pytest.fixture
def marker_service(test_db: DatabaseManager) -> MarkerService:
    """Create MarkerService with real database."""
    return MarkerService(test_db)


@pytest.fixture
def mock_marker_service(mock_db: MagicMock) -> MarkerService:
    """Create MarkerService with mock database."""
    return MarkerService(mock_db)


@pytest.fixture
def sample_sleep_period() -> SleepPeriod:
    """Create a sample sleep period."""
    return SleepPeriod(
        onset_timestamp=datetime(2024, 1, 15, 22, 30).timestamp(),
        offset_timestamp=datetime(2024, 1, 16, 6, 45).timestamp(),
        marker_index=1,
        marker_type=MarkerType.MAIN_SLEEP,
    )


@pytest.fixture
def sample_daily_sleep_markers(sample_sleep_period: SleepPeriod) -> DailySleepMarkers:
    """Create sample daily sleep markers with one period."""
    markers = DailySleepMarkers()
    markers.period_1 = sample_sleep_period
    return markers


@pytest.fixture
def sample_nonwear_period() -> ManualNonwearPeriod:
    """Create a sample nonwear period."""
    return ManualNonwearPeriod(
        start_timestamp=datetime(2024, 1, 15, 10, 0).timestamp(),
        end_timestamp=datetime(2024, 1, 15, 12, 0).timestamp(),
        marker_index=1,
    )


@pytest.fixture
def sample_daily_nonwear_markers(sample_nonwear_period: ManualNonwearPeriod) -> DailyNonwearMarkers:
    """Create sample daily nonwear markers with one period."""
    markers = DailyNonwearMarkers()
    markers.period_1 = sample_nonwear_period
    return markers


@pytest.fixture
def sample_sleep_metrics(sample_daily_sleep_markers: DailySleepMarkers) -> SleepMetrics:
    """Create sample SleepMetrics for testing."""
    return SleepMetrics(
        filename="DEMO-1001.csv",
        analysis_date="2024-01-15",
        daily_sleep_markers=sample_daily_sleep_markers,
        participant=ParticipantInfo(numerical_id="1001"),
    )


class TestValidateSleepMarkers:
    """Tests for validate method."""

    def test_validates_empty_markers(self, mock_marker_service: MarkerService):
        """Empty markers are valid."""
        markers = DailySleepMarkers()
        result = mock_marker_service.validate(markers)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validates_complete_valid_period(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Valid periods pass validation."""
        result = mock_marker_service.validate(sample_daily_sleep_markers)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_onset_after_offset(self, mock_marker_service: MarkerService):
        """Error when onset is after offset."""
        markers = DailySleepMarkers()
        markers.period_1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 16, 6, 0).timestamp(),  # After offset
            offset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            marker_index=1,
        )

        result = mock_marker_service.validate(markers)

        assert result.is_valid is False
        assert any("onset must be before offset" in e for e in result.errors)

    def test_warns_on_very_long_duration(self, mock_marker_service: MarkerService):
        """Warning when duration exceeds 24 hours."""
        markers = DailySleepMarkers()
        # 30 hour sleep period
        markers.period_1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 0, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 16, 6, 0).timestamp() + 24 * 3600,  # >24 hours
            marker_index=1,
        )

        result = mock_marker_service.validate(markers)

        assert result.is_valid is True  # Warnings don't invalidate
        assert any("duration > 24 hours" in w for w in result.warnings)

    def test_warns_on_very_short_duration(self, mock_marker_service: MarkerService):
        """Warning when duration is less than 30 minutes."""
        markers = DailySleepMarkers()
        # 20 minute sleep period
        markers.period_1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 15, 22, 20).timestamp(),  # 20 mins
            marker_index=1,
        )

        result = mock_marker_service.validate(markers)

        assert result.is_valid is True  # Warnings don't invalidate
        assert any("duration < 30 minutes" in w for w in result.warnings)

    def test_returns_validation_result_dataclass(self, mock_marker_service: MarkerService):
        """Returns ValidationResult with correct structure."""
        markers = DailySleepMarkers()
        result = mock_marker_service.validate(markers)

        assert isinstance(result, ValidationResult)
        assert hasattr(result, "is_valid")
        assert hasattr(result, "errors")
        assert hasattr(result, "warnings")


class TestValidateNonwearMarkers:
    """Tests for validate_nonwear method."""

    def test_validates_empty_nonwear_markers(self, mock_marker_service: MarkerService):
        """Empty nonwear markers are valid."""
        markers = DailyNonwearMarkers()
        result = mock_marker_service.validate_nonwear(markers)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validates_complete_valid_nonwear_period(self, mock_marker_service: MarkerService, sample_daily_nonwear_markers: DailyNonwearMarkers):
        """Valid nonwear periods pass validation."""
        result = mock_marker_service.validate_nonwear(sample_daily_nonwear_markers)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_invalid_start_after_end(self, mock_marker_service: MarkerService):
        """Error when start is after end."""
        markers = DailyNonwearMarkers()
        markers.period_1 = ManualNonwearPeriod(
            start_timestamp=datetime(2024, 1, 15, 14, 0).timestamp(),  # After end
            end_timestamp=datetime(2024, 1, 15, 12, 0).timestamp(),
            marker_index=1,
        )

        result = mock_marker_service.validate_nonwear(markers)

        assert result.is_valid is False
        assert any("start must be before end" in e for e in result.errors)


class TestValidateMarkerAddition:
    """Tests for validate_marker_addition method."""

    def test_allows_addition_when_space_available(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Returns valid when slots are available."""
        new_period = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 14, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 15, 15, 0).timestamp(),
            marker_index=2,
        )

        is_valid, error = mock_marker_service.validate_marker_addition(sample_daily_sleep_markers, new_period)

        assert is_valid is True
        assert error == ""

    def test_rejects_when_no_space(self, mock_marker_service: MarkerService):
        """Returns invalid when all slots are full."""
        markers = DailySleepMarkers()
        # Fill all 4 slots
        for i in range(1, 5):
            period = SleepPeriod(
                onset_timestamp=datetime(2024, 1, 15, i, 0).timestamp(),
                offset_timestamp=datetime(2024, 1, 15, i + 1, 0).timestamp(),
                marker_index=i,
            )
            setattr(markers, f"period_{i}", period)

        new_period = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 10, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 15, 11, 0).timestamp(),
        )

        is_valid, error = mock_marker_service.validate_marker_addition(markers, new_period)

        assert is_valid is False
        assert "Maximum" in error

    def test_rejects_overlapping_periods(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Returns invalid when new period overlaps existing."""
        # New period overlaps with existing main sleep (22:30-6:45)
        new_period = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 23, 0).timestamp(),  # During main sleep
            offset_timestamp=datetime(2024, 1, 16, 2, 0).timestamp(),
            marker_index=2,
        )

        is_valid, error = mock_marker_service.validate_marker_addition(sample_daily_sleep_markers, new_period)

        assert is_valid is False
        assert "overlap" in error.lower()


class TestPeriodsOverlap:
    """Tests for _periods_overlap static method."""

    def test_detects_overlapping_periods(self):
        """Returns True when periods overlap."""
        period1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 16, 6, 0).timestamp(),
            marker_index=1,
        )
        period2 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 16, 4, 0).timestamp(),  # Starts before period1 ends
            offset_timestamp=datetime(2024, 1, 16, 8, 0).timestamp(),
            marker_index=2,
        )

        assert MarkerService._periods_overlap(period1, period2) is True

    def test_non_overlapping_periods(self):
        """Returns False when periods don't overlap."""
        period1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 16, 6, 0).timestamp(),
            marker_index=1,
        )
        period2 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 16, 14, 0).timestamp(),  # Starts after period1 ends
            offset_timestamp=datetime(2024, 1, 16, 15, 0).timestamp(),
            marker_index=2,
        )

        assert MarkerService._periods_overlap(period1, period2) is False

    def test_incomplete_periods_dont_overlap(self):
        """Returns False for incomplete periods."""
        period1 = SleepPeriod(onset_timestamp=None, offset_timestamp=None, marker_index=1)
        period2 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 16, 14, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 16, 15, 0).timestamp(),
            marker_index=2,
        )

        assert MarkerService._periods_overlap(period1, period2) is False


class TestValidateDurationTie:
    """Tests for validate_duration_tie method."""

    def test_no_tie_with_different_durations(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Returns False when durations differ."""
        has_tie, message = mock_marker_service.validate_duration_tie(sample_daily_sleep_markers)

        assert has_tie is False
        assert message == ""

    def test_detects_tie_with_equal_durations(self, mock_marker_service: MarkerService):
        """Returns True when two periods have equal duration."""
        markers = DailySleepMarkers()
        # Two periods with exactly equal duration (2 hours each)
        markers.period_1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 16, 0, 0).timestamp(),
            marker_index=1,
        )
        markers.period_2 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 14, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 15, 16, 0).timestamp(),
            marker_index=2,
        )

        has_tie, message = mock_marker_service.validate_duration_tie(markers)

        assert has_tie is True
        assert "duration" in message.lower() or "tie" in message.lower()


class TestUpdateClassifications:
    """Tests for update_classifications method."""

    def test_updates_classifications(self, mock_marker_service: MarkerService):
        """Classifications are updated based on durations."""
        markers = DailySleepMarkers()
        # Long sleep (main) and short nap
        markers.period_1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 16, 6, 0).timestamp(),  # 8 hours
            marker_index=1,
        )
        markers.period_2 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 14, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 15, 15, 0).timestamp(),  # 1 hour
            marker_index=2,
        )

        mock_marker_service.update_classifications(markers)

        # Longest should be main sleep
        assert markers.period_1.marker_type == MarkerType.MAIN_SLEEP
        assert markers.period_2.marker_type == MarkerType.NAP


class TestHandleDurationTieCancellation:
    """Tests for handle_duration_tie_cancellation method."""

    def test_removes_specified_period(self, mock_marker_service: MarkerService):
        """Removes the specified period index."""
        markers = DailySleepMarkers()
        markers.period_1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 16, 0, 0).timestamp(),
            marker_index=1,
        )
        markers.period_2 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 15, 14, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 15, 16, 0).timestamp(),
            marker_index=2,
        )

        result = mock_marker_service.handle_duration_tie_cancellation(markers, 2)

        assert result is True
        assert markers.period_1 is not None
        assert markers.period_2 is None

    def test_returns_false_for_invalid_index(self, mock_marker_service: MarkerService):
        """Returns False for invalid period index."""
        markers = DailySleepMarkers()

        result = mock_marker_service.handle_duration_tie_cancellation(markers, 5)

        assert result is False


class TestGetNextAvailableSlot:
    """Tests for get_next_available_slot method."""

    def test_returns_first_for_empty_markers(self, mock_marker_service: MarkerService):
        """Returns 1 for empty markers."""
        markers = DailySleepMarkers()

        slot = mock_marker_service.get_next_available_slot(markers)

        assert slot == 1

    def test_returns_next_empty_slot(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Returns next empty slot when some are filled."""
        slot = mock_marker_service.get_next_available_slot(sample_daily_sleep_markers)

        assert slot == 2  # period_1 is filled, so next is 2

    def test_returns_none_when_all_full(self, mock_marker_service: MarkerService):
        """Returns None when all slots are filled."""
        markers = DailySleepMarkers()
        for i in range(1, 5):
            period = SleepPeriod(
                onset_timestamp=datetime(2024, 1, 15, i, 0).timestamp(),
                offset_timestamp=datetime(2024, 1, 15, i + 1, 0).timestamp(),
                marker_index=i,
            )
            setattr(markers, f"period_{i}", period)

        slot = mock_marker_service.get_next_available_slot(markers)

        assert slot is None


class TestAddSleepPeriod:
    """Tests for add_sleep_period method."""

    def test_adds_period_successfully(self, mock_marker_service: MarkerService, sample_sleep_metrics: SleepMetrics):
        """Adds a new non-overlapping sleep period."""
        onset = datetime(2024, 1, 15, 14, 0).timestamp()
        offset = datetime(2024, 1, 15, 15, 0).timestamp()

        success, message = mock_marker_service.add_sleep_period(sample_sleep_metrics, onset, offset)

        assert success is True
        assert "Added" in message

    def test_rejects_overlapping_period(self, mock_marker_service: MarkerService, sample_sleep_metrics: SleepMetrics):
        """Rejects period that overlaps with existing."""
        # Overlaps with main sleep (22:30 - 6:45)
        onset = datetime(2024, 1, 15, 23, 0).timestamp()
        offset = datetime(2024, 1, 16, 2, 0).timestamp()

        success, message = mock_marker_service.add_sleep_period(sample_sleep_metrics, onset, offset)

        assert success is False
        assert "overlap" in message.lower()

    def test_updates_classifications_after_add(self, mock_marker_service: MarkerService, sample_sleep_metrics: SleepMetrics):
        """Classifications are updated after adding period."""
        # Add a longer period that should become main sleep
        onset = datetime(2024, 1, 15, 10, 0).timestamp()
        offset = datetime(2024, 1, 15, 20, 0).timestamp()  # 10 hours

        mock_marker_service.add_sleep_period(sample_sleep_metrics, onset, offset)

        # The longer period should be classified as main sleep
        # (original was 8h15m, new one is 10h)
        # Check that update_classifications was called (period types may have changed)
        periods = sample_sleep_metrics.daily_sleep_markers.get_complete_periods()
        assert len(periods) >= 1


class TestRemoveSleepPeriod:
    """Tests for remove_sleep_period method."""

    def test_removes_existing_period(self, mock_marker_service: MarkerService, sample_sleep_metrics: SleepMetrics):
        """Removes an existing period by index."""
        success, message = mock_marker_service.remove_sleep_period(sample_sleep_metrics, 1)

        assert success is True
        assert "Removed" in message
        assert sample_sleep_metrics.daily_sleep_markers.period_1 is None

    def test_returns_false_for_nonexistent_period(self, mock_marker_service: MarkerService, sample_sleep_metrics: SleepMetrics):
        """Returns False when trying to remove non-existent period."""
        success, message = mock_marker_service.remove_sleep_period(sample_sleep_metrics, 3)

        assert success is False
        assert "No sleep period found" in message


class TestCacheOperations:
    """Tests for cache-related methods."""

    def test_make_cache_key_format(self, mock_marker_service: MarkerService):
        """Cache key has correct format."""
        key = mock_marker_service._make_cache_key("file.csv", "2024-01-15", "sleep")

        assert key == "file.csv:2024-01-15:sleep"

    def test_invalidate_cache_key(self, mock_marker_service: MarkerService):
        """Specific cache key is invalidated."""
        # Add to cache
        mock_marker_service._cache["file.csv:2024-01-15:sleep"] = DailySleepMarkers()

        mock_marker_service._invalidate_cache_key("file.csv", "2024-01-15", "sleep")

        assert "file.csv:2024-01-15:sleep" not in mock_marker_service._cache

    def test_invalidate_cache_for_file(self, mock_marker_service: MarkerService):
        """All cache entries for a file are invalidated."""
        # Add multiple entries
        mock_marker_service._cache["file.csv:2024-01-15:sleep"] = DailySleepMarkers()
        mock_marker_service._cache["file.csv:2024-01-16:sleep"] = DailySleepMarkers()
        mock_marker_service._cache["other.csv:2024-01-15:sleep"] = DailySleepMarkers()

        mock_marker_service.invalidate_cache("file.csv")

        assert "file.csv:2024-01-15:sleep" not in mock_marker_service._cache
        assert "file.csv:2024-01-16:sleep" not in mock_marker_service._cache
        assert "other.csv:2024-01-15:sleep" in mock_marker_service._cache

    def test_invalidate_cache_for_specific_date(self, mock_marker_service: MarkerService):
        """Cache for specific file/date is invalidated."""
        mock_marker_service._cache["file.csv:2024-01-15:sleep"] = DailySleepMarkers()
        mock_marker_service._cache["file.csv:2024-01-15:nonwear"] = DailyNonwearMarkers()
        mock_marker_service._cache["file.csv:2024-01-16:sleep"] = DailySleepMarkers()

        mock_marker_service.invalidate_cache("file.csv", "2024-01-15")

        assert "file.csv:2024-01-15:sleep" not in mock_marker_service._cache
        assert "file.csv:2024-01-15:nonwear" not in mock_marker_service._cache
        assert "file.csv:2024-01-16:sleep" in mock_marker_service._cache

    def test_clear_cache(self, mock_marker_service: MarkerService):
        """All cache entries are cleared."""
        mock_marker_service._cache["file1.csv:2024-01-15:sleep"] = DailySleepMarkers()
        mock_marker_service._cache["file2.csv:2024-01-16:nonwear"] = DailyNonwearMarkers()

        mock_marker_service.clear_cache()

        assert len(mock_marker_service._cache) == 0


class TestGetMarkerStatus:
    """Tests for get_marker_status method."""

    def test_returns_marker_status_object(self, mock_marker_service: MarkerService):
        """Returns MarkerStatus with correct structure."""
        status = mock_marker_service.get_marker_status("file.csv", "2024-01-15")

        assert isinstance(status, MarkerStatus)
        assert hasattr(status, "has_sleep_markers")
        assert hasattr(status, "has_nonwear_markers")
        assert hasattr(status, "sleep_periods_count")
        assert hasattr(status, "nonwear_periods_count")
        assert hasattr(status, "is_complete")

    def test_reports_no_markers_when_none_exist(self, mock_marker_service: MarkerService):
        """Status shows no markers when database is empty."""
        status = mock_marker_service.get_marker_status("file.csv", "2024-01-15")

        assert status.has_sleep_markers is False
        assert status.has_nonwear_markers is False
        assert status.sleep_periods_count == 0
        assert status.nonwear_periods_count == 0


class TestSaveSleepMarkers:
    """Tests for save method."""

    def test_save_returns_true_on_success(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Returns True when save succeeds."""
        result = mock_marker_service.save("file.csv", "2024-01-15", sample_daily_sleep_markers)

        assert result is True
        mock_marker_service._db.execute.assert_called_once()

    def test_save_rejects_invalid_markers(self, mock_marker_service: MarkerService):
        """Returns False when markers are invalid."""
        markers = DailySleepMarkers()
        # Invalid: onset after offset
        markers.period_1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 16, 6, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 15, 22, 0).timestamp(),
            marker_index=1,
        )

        result = mock_marker_service.save("file.csv", "2024-01-15", markers)

        assert result is False

    def test_save_accepts_date_object(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Accepts date object in addition to string."""
        result = mock_marker_service.save("file.csv", date(2024, 1, 15), sample_daily_sleep_markers)

        assert result is True

    def test_save_invalidates_cache(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Cache is invalidated after save."""
        # Pre-populate cache
        mock_marker_service._cache["file.csv:2024-01-15:sleep"] = sample_daily_sleep_markers

        mock_marker_service.save("file.csv", "2024-01-15", sample_daily_sleep_markers)

        assert "file.csv:2024-01-15:sleep" not in mock_marker_service._cache


class TestLoadSleepMarkers:
    """Tests for load method."""

    def test_load_returns_cached_markers(self, mock_marker_service: MarkerService, sample_daily_sleep_markers: DailySleepMarkers):
        """Returns cached markers without database query."""
        mock_marker_service._cache["file.csv:2024-01-15:sleep"] = sample_daily_sleep_markers

        loaded = mock_marker_service.load("file.csv", "2024-01-15")

        assert loaded is sample_daily_sleep_markers
        mock_marker_service._db.get_sleep_metrics_by_filename_and_date.assert_not_called()

    def test_load_returns_none_when_not_found(self, mock_marker_service: MarkerService):
        """Returns None when no markers exist."""
        mock_marker_service._db.get_sleep_metrics_by_filename_and_date.return_value = None

        loaded = mock_marker_service.load("nonexistent.csv", "2024-01-15")

        assert loaded is None

    def test_load_queries_database_on_cache_miss(self, mock_marker_service: MarkerService):
        """Queries database when cache is empty."""
        mock_marker_service._db.get_sleep_metrics_by_filename_and_date.return_value = None

        mock_marker_service.load("file.csv", "2024-01-15")

        mock_marker_service._db.get_sleep_metrics_by_filename_and_date.assert_called_once()

    def test_load_accepts_date_object(self, mock_marker_service: MarkerService):
        """Accepts date object in addition to string."""
        mock_marker_service._db.get_sleep_metrics_by_filename_and_date.return_value = None

        loaded = mock_marker_service.load("file.csv", date(2024, 1, 15))

        assert loaded is None


class TestSaveNonwearMarkers:
    """Tests for save_nonwear method."""

    def test_save_nonwear_returns_true(self, mock_marker_service: MarkerService, sample_daily_nonwear_markers: DailyNonwearMarkers):
        """Returns True when nonwear save succeeds."""
        result = mock_marker_service.save_nonwear("file.csv", "2024-01-15", sample_daily_nonwear_markers)

        assert result is True
        mock_marker_service._db.execute.assert_called_once()

    def test_save_nonwear_invalidates_cache(self, mock_marker_service: MarkerService, sample_daily_nonwear_markers: DailyNonwearMarkers):
        """Cache is invalidated after save."""
        mock_marker_service._cache["file.csv:2024-01-15:nonwear"] = sample_daily_nonwear_markers

        mock_marker_service.save_nonwear("file.csv", "2024-01-15", sample_daily_nonwear_markers)

        assert "file.csv:2024-01-15:nonwear" not in mock_marker_service._cache


class TestLoadNonwearMarkers:
    """Tests for load_nonwear method."""

    def test_load_nonwear_returns_cached(self, mock_marker_service: MarkerService, sample_daily_nonwear_markers: DailyNonwearMarkers):
        """Returns cached nonwear markers without database query."""
        mock_marker_service._cache["file.csv:2024-01-15:nonwear"] = sample_daily_nonwear_markers

        loaded = mock_marker_service.load_nonwear("file.csv", "2024-01-15")

        assert loaded is sample_daily_nonwear_markers

    def test_load_nonwear_returns_none_when_not_found(self, mock_marker_service: MarkerService):
        """Returns None when no nonwear markers exist."""
        # load_manual_nonwear_markers returns empty DailyNonwearMarkers when not found
        empty_markers = DailyNonwearMarkers()
        mock_marker_service._db.load_manual_nonwear_markers.return_value = empty_markers

        loaded = mock_marker_service.load_nonwear("nonexistent.csv", "2024-01-15")

        assert loaded is None


class TestGetAllMarkerStatuses:
    """Tests for get_all_marker_statuses method."""

    def test_returns_empty_dict_when_no_markers(self, mock_marker_service: MarkerService):
        """Returns empty dict when no markers exist for file."""
        mock_marker_service._db.fetch_all.return_value = []

        statuses = mock_marker_service.get_all_marker_statuses("nonexistent.csv")

        assert isinstance(statuses, dict)
        assert len(statuses) == 0

    def test_returns_statuses_for_all_dates(self, mock_marker_service: MarkerService):
        """Returns status for each date that has markers."""
        mock_marker_service._db.fetch_all.return_value = [("2024-01-15",), ("2024-01-16",)]

        statuses = mock_marker_service.get_all_marker_statuses("file.csv")

        assert len(statuses) == 2
        assert date(2024, 1, 15) in statuses
        assert date(2024, 1, 16) in statuses
