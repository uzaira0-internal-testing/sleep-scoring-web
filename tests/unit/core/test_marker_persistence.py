"""
Tests for marker persistence implementations.

Tests SleepMarkerPersistence, NonwearMarkerPersistence, and UnifiedMarkerHandler.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import AlgorithmType
from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes, ValidationError
from sleep_scoring_app.core.markers.persistence import (
    NonwearMarkerPersistence,
    SleepMarkerPersistence,
    UnifiedMarkerHandler,
)


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create a mock database manager."""
    return MagicMock()


@pytest.fixture
def mock_metrics_saver() -> MagicMock:
    """Create a mock metrics saver."""
    mock = MagicMock()
    mock.save_comprehensive_sleep_metrics = MagicMock(return_value=True)
    return mock


@pytest.fixture
def mock_markers() -> MagicMock:
    """Create a mock markers object."""
    return MagicMock()


@pytest.fixture
def mock_sleep_metrics() -> MagicMock:
    """Create a mock sleep metrics object."""
    return MagicMock()


@pytest.fixture
def test_date() -> datetime:
    """Create a test date."""
    return datetime(2024, 1, 15, 12, 0, 0)


@pytest.fixture
def sleep_persistence(
    mock_db_manager: MagicMock,
    mock_metrics_saver: MagicMock,
) -> SleepMarkerPersistence:
    """Create SleepMarkerPersistence instance."""
    return SleepMarkerPersistence(
        db_manager=mock_db_manager,
        metrics_saver=mock_metrics_saver,
    )


@pytest.fixture
def nonwear_persistence(
    mock_db_manager: MagicMock,
) -> NonwearMarkerPersistence:
    """Create NonwearMarkerPersistence instance."""
    return NonwearMarkerPersistence(db_manager=mock_db_manager)


class TestSleepMarkerPersistenceInit:
    """Tests for SleepMarkerPersistence initialization."""

    def test_creates_instance(
        self,
        mock_db_manager: MagicMock,
        mock_metrics_saver: MagicMock,
    ) -> None:
        """Creates persistence instance."""
        persistence = SleepMarkerPersistence(
            db_manager=mock_db_manager,
            metrics_saver=mock_metrics_saver,
        )

        assert persistence is not None
        assert persistence._db_manager is mock_db_manager
        assert persistence._metrics_saver is mock_metrics_saver

    def test_accepts_metrics_calculator(
        self,
        mock_db_manager: MagicMock,
        mock_metrics_saver: MagicMock,
    ) -> None:
        """Accepts optional metrics calculator."""
        mock_calculator = MagicMock()
        persistence = SleepMarkerPersistence(
            db_manager=mock_db_manager,
            metrics_saver=mock_metrics_saver,
            metrics_calculator=mock_calculator,
        )

        assert persistence._metrics_calculator is mock_calculator


class TestSleepMarkerPersistenceSave:
    """Tests for SleepMarkerPersistence.save method."""

    def test_save_with_metrics_succeeds(
        self,
        sleep_persistence: SleepMarkerPersistence,
        mock_markers: MagicMock,
        mock_sleep_metrics: MagicMock,
        test_date: datetime,
    ) -> None:
        """Saves markers with provided sleep metrics."""
        result = sleep_persistence.save(
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            markers=mock_markers,
            sleep_metrics=mock_sleep_metrics,
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
        )

        assert result is True
        sleep_persistence._metrics_saver.save_comprehensive_sleep_metrics.assert_called_once()

    def test_save_without_metrics_raises_validation_error(
        self,
        sleep_persistence: SleepMarkerPersistence,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Raises ValidationError when no sleep metrics provided."""
        with pytest.raises(ValidationError) as exc_info:
            sleep_persistence.save(
                filename="test.csv",
                participant_id="PART-001",
                date=test_date,
                markers=mock_markers,
                sleep_metrics=None,
            )

        assert "No sleep metrics provided" in str(exc_info.value)

    def test_save_attaches_markers_to_metrics(
        self,
        sleep_persistence: SleepMarkerPersistence,
        mock_markers: MagicMock,
        mock_sleep_metrics: MagicMock,
        test_date: datetime,
    ) -> None:
        """Attaches markers to sleep metrics before saving."""
        sleep_persistence.save(
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            markers=mock_markers,
            sleep_metrics=mock_sleep_metrics,
        )

        assert mock_sleep_metrics.daily_sleep_markers is mock_markers
        assert mock_sleep_metrics.analysis_date == "2024-01-15"
        assert mock_sleep_metrics.filename == "test.csv"

    def test_save_uses_default_algorithm_type(
        self,
        sleep_persistence: SleepMarkerPersistence,
        mock_markers: MagicMock,
        mock_sleep_metrics: MagicMock,
        test_date: datetime,
    ) -> None:
        """Uses default algorithm type when none provided."""
        sleep_persistence.save(
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            markers=mock_markers,
            sleep_metrics=mock_sleep_metrics,
        )

        call_args = sleep_persistence._metrics_saver.save_comprehensive_sleep_metrics.call_args
        assert call_args[0][1] == AlgorithmType.SADEH_1994_ACTILIFE

    def test_save_failure_raises_database_error(
        self,
        sleep_persistence: SleepMarkerPersistence,
        mock_markers: MagicMock,
        mock_sleep_metrics: MagicMock,
        test_date: datetime,
    ) -> None:
        """Raises DatabaseError when save fails."""
        sleep_persistence._metrics_saver.save_comprehensive_sleep_metrics.return_value = False

        with pytest.raises(DatabaseError) as exc_info:
            sleep_persistence.save(
                filename="test.csv",
                participant_id="PART-001",
                date=test_date,
                markers=mock_markers,
                sleep_metrics=mock_sleep_metrics,
            )

        assert "Failed to save sleep metrics" in str(exc_info.value)


class TestSleepMarkerPersistenceLoad:
    """Tests for SleepMarkerPersistence.load method."""

    def test_load_returns_markers_when_found(
        self,
        sleep_persistence: SleepMarkerPersistence,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Returns markers when found in database."""
        mock_metrics = MagicMock()
        mock_metrics.daily_sleep_markers = mock_markers
        sleep_persistence._db_manager.get_sleep_metrics_by_filename_and_date.return_value = mock_metrics

        result = sleep_persistence.load("test.csv", test_date)

        assert result is mock_markers
        sleep_persistence._db_manager.get_sleep_metrics_by_filename_and_date.assert_called_once_with("test.csv", "2024-01-15")

    def test_load_returns_none_when_not_found(
        self,
        sleep_persistence: SleepMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Returns None when no markers found."""
        sleep_persistence._db_manager.get_sleep_metrics_by_filename_and_date.return_value = None

        result = sleep_persistence.load("test.csv", test_date)

        assert result is None

    def test_load_returns_none_when_no_markers_attached(
        self,
        sleep_persistence: SleepMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Returns None when metrics exist but no markers attached."""
        mock_metrics = MagicMock()
        mock_metrics.daily_sleep_markers = None
        sleep_persistence._db_manager.get_sleep_metrics_by_filename_and_date.return_value = mock_metrics

        result = sleep_persistence.load("test.csv", test_date)

        assert result is None

    def test_load_reraises_database_error(
        self,
        sleep_persistence: SleepMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Re-raises DatabaseError from db_manager."""
        sleep_persistence._db_manager.get_sleep_metrics_by_filename_and_date.side_effect = DatabaseError("DB error", ErrorCodes.DB_QUERY_FAILED)

        with pytest.raises(DatabaseError):
            sleep_persistence.load("test.csv", test_date)

    def test_load_wraps_unexpected_error(
        self,
        sleep_persistence: SleepMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Wraps unexpected errors in DatabaseError."""
        sleep_persistence._db_manager.get_sleep_metrics_by_filename_and_date.side_effect = RuntimeError("Unexpected")

        with pytest.raises(DatabaseError) as exc_info:
            sleep_persistence.load("test.csv", test_date)

        assert "Failed to load sleep markers" in str(exc_info.value)


class TestSleepMarkerPersistenceDelete:
    """Tests for SleepMarkerPersistence.delete method."""

    def test_delete_calls_db_manager(
        self,
        sleep_persistence: SleepMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Calls db_manager.delete_sleep_metrics_for_date."""
        result = sleep_persistence.delete("test.csv", test_date)

        assert result is True
        sleep_persistence._db_manager.delete_sleep_metrics_for_date.assert_called_once_with("test.csv", "2024-01-15")

    def test_delete_reraises_database_error(
        self,
        sleep_persistence: SleepMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Re-raises DatabaseError from db_manager."""
        sleep_persistence._db_manager.delete_sleep_metrics_for_date.side_effect = DatabaseError("DB error", ErrorCodes.DB_DELETE_FAILED)

        with pytest.raises(DatabaseError):
            sleep_persistence.delete("test.csv", test_date)

    def test_delete_wraps_unexpected_error(
        self,
        sleep_persistence: SleepMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Wraps unexpected errors in DatabaseError."""
        sleep_persistence._db_manager.delete_sleep_metrics_for_date.side_effect = RuntimeError("Unexpected")

        with pytest.raises(DatabaseError) as exc_info:
            sleep_persistence.delete("test.csv", test_date)

        assert "Failed to delete sleep markers" in str(exc_info.value)


class TestNonwearMarkerPersistenceInit:
    """Tests for NonwearMarkerPersistence initialization."""

    def test_creates_instance(
        self,
        mock_db_manager: MagicMock,
    ) -> None:
        """Creates persistence instance."""
        persistence = NonwearMarkerPersistence(db_manager=mock_db_manager)

        assert persistence is not None
        assert persistence._db_manager is mock_db_manager


class TestNonwearMarkerPersistenceSave:
    """Tests for NonwearMarkerPersistence.save method."""

    def test_save_calls_db_manager(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Calls db_manager.save_manual_nonwear_markers."""
        result = nonwear_persistence.save(
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            markers=mock_markers,
        )

        assert result is True
        nonwear_persistence._db_manager.save_manual_nonwear_markers.assert_called_once_with(
            filename="test.csv",
            participant_id="PART-001",
            sleep_date="2024-01-15",
            daily_nonwear_markers=mock_markers,
        )

    def test_save_reraises_database_error(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Re-raises DatabaseError from db_manager."""
        nonwear_persistence._db_manager.save_manual_nonwear_markers.side_effect = DatabaseError("DB error", ErrorCodes.DB_INSERT_FAILED)

        with pytest.raises(DatabaseError):
            nonwear_persistence.save(
                filename="test.csv",
                participant_id="PART-001",
                date=test_date,
                markers=mock_markers,
            )

    def test_save_wraps_unexpected_error(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Wraps unexpected errors in DatabaseError."""
        nonwear_persistence._db_manager.save_manual_nonwear_markers.side_effect = RuntimeError("Unexpected")

        with pytest.raises(DatabaseError) as exc_info:
            nonwear_persistence.save(
                filename="test.csv",
                participant_id="PART-001",
                date=test_date,
                markers=mock_markers,
            )

        assert "Failed to save nonwear markers" in str(exc_info.value)


class TestNonwearMarkerPersistenceLoad:
    """Tests for NonwearMarkerPersistence.load method."""

    def test_load_calls_db_manager(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Calls db_manager.load_manual_nonwear_markers."""
        nonwear_persistence._db_manager.load_manual_nonwear_markers.return_value = mock_markers

        result = nonwear_persistence.load("test.csv", test_date)

        assert result is mock_markers
        nonwear_persistence._db_manager.load_manual_nonwear_markers.assert_called_once_with(
            filename="test.csv",
            sleep_date="2024-01-15",
        )

    def test_load_reraises_database_error(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Re-raises DatabaseError from db_manager."""
        nonwear_persistence._db_manager.load_manual_nonwear_markers.side_effect = DatabaseError("DB error", ErrorCodes.DB_QUERY_FAILED)

        with pytest.raises(DatabaseError):
            nonwear_persistence.load("test.csv", test_date)

    def test_load_wraps_unexpected_error(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Wraps unexpected errors in DatabaseError."""
        nonwear_persistence._db_manager.load_manual_nonwear_markers.side_effect = RuntimeError("Unexpected")

        with pytest.raises(DatabaseError) as exc_info:
            nonwear_persistence.load("test.csv", test_date)

        assert "Failed to load nonwear markers" in str(exc_info.value)


class TestNonwearMarkerPersistenceDelete:
    """Tests for NonwearMarkerPersistence.delete method."""

    def test_delete_calls_db_manager(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Calls db_manager.delete_manual_nonwear_markers."""
        result = nonwear_persistence.delete("test.csv", test_date)

        assert result is True
        nonwear_persistence._db_manager.delete_manual_nonwear_markers.assert_called_once_with(
            filename="test.csv",
            sleep_date="2024-01-15",
        )

    def test_delete_reraises_database_error(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Re-raises DatabaseError from db_manager."""
        nonwear_persistence._db_manager.delete_manual_nonwear_markers.side_effect = DatabaseError("DB error", ErrorCodes.DB_DELETE_FAILED)

        with pytest.raises(DatabaseError):
            nonwear_persistence.delete("test.csv", test_date)

    def test_delete_wraps_unexpected_error(
        self,
        nonwear_persistence: NonwearMarkerPersistence,
        test_date: datetime,
    ) -> None:
        """Wraps unexpected errors in DatabaseError."""
        nonwear_persistence._db_manager.delete_manual_nonwear_markers.side_effect = RuntimeError("Unexpected")

        with pytest.raises(DatabaseError) as exc_info:
            nonwear_persistence.delete("test.csv", test_date)

        assert "Failed to delete nonwear markers" in str(exc_info.value)


class TestUnifiedMarkerHandlerInit:
    """Tests for UnifiedMarkerHandler initialization."""

    def test_creates_instance(self) -> None:
        """Creates handler instance."""
        sleep_persistence = MagicMock()
        nonwear_persistence = MagicMock()

        handler = UnifiedMarkerHandler(
            sleep_persistence=sleep_persistence,
            nonwear_persistence=nonwear_persistence,
        )

        assert handler is not None
        assert handler._sleep_persistence is sleep_persistence
        assert handler._nonwear_persistence is nonwear_persistence

    def test_initializes_empty_callbacks(self) -> None:
        """Initializes with empty callback list."""
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=MagicMock(),
        )

        assert handler._on_save_callbacks == []


class TestUnifiedMarkerHandlerCallbacks:
    """Tests for UnifiedMarkerHandler callback management."""

    def test_add_on_save_callback(self) -> None:
        """Adds callback to list."""
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=MagicMock(),
        )
        callback = MagicMock()

        handler.add_on_save_callback(callback)

        assert callback in handler._on_save_callbacks

    def test_multiple_callbacks(self) -> None:
        """Supports multiple callbacks."""
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=MagicMock(),
        )
        callback1 = MagicMock()
        callback2 = MagicMock()

        handler.add_on_save_callback(callback1)
        handler.add_on_save_callback(callback2)

        assert len(handler._on_save_callbacks) == 2


class TestUnifiedMarkerHandlerSleepMarkersChanged:
    """Tests for UnifiedMarkerHandler.on_sleep_markers_changed method."""

    def test_calls_sleep_persistence_save(
        self,
        mock_markers: MagicMock,
        mock_sleep_metrics: MagicMock,
        test_date: datetime,
    ) -> None:
        """Calls sleep persistence save method."""
        sleep_persistence = MagicMock()
        handler = UnifiedMarkerHandler(
            sleep_persistence=sleep_persistence,
            nonwear_persistence=MagicMock(),
        )

        handler.on_sleep_markers_changed(
            markers=mock_markers,
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            sleep_metrics=mock_sleep_metrics,
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
        )

        sleep_persistence.save.assert_called_once_with(
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            markers=mock_markers,
            sleep_metrics=mock_sleep_metrics,
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
        )

    def test_invokes_callbacks_after_save(
        self,
        mock_markers: MagicMock,
        mock_sleep_metrics: MagicMock,
        test_date: datetime,
    ) -> None:
        """Invokes callbacks after successful save."""
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=MagicMock(),
        )
        callback = MagicMock()
        handler.add_on_save_callback(callback)

        handler.on_sleep_markers_changed(
            markers=mock_markers,
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            sleep_metrics=mock_sleep_metrics,
        )

        callback.assert_called_once_with("sleep", "test.csv", test_date)

    def test_callback_failure_does_not_stop_others(
        self,
        mock_markers: MagicMock,
        mock_sleep_metrics: MagicMock,
        test_date: datetime,
    ) -> None:
        """Callback failure doesn't prevent other callbacks."""
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=MagicMock(),
        )
        failing_callback = MagicMock(side_effect=RuntimeError("Callback error"))
        success_callback = MagicMock()
        handler.add_on_save_callback(failing_callback)
        handler.add_on_save_callback(success_callback)

        handler.on_sleep_markers_changed(
            markers=mock_markers,
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            sleep_metrics=mock_sleep_metrics,
        )

        success_callback.assert_called_once()


class TestUnifiedMarkerHandlerNonwearMarkersChanged:
    """Tests for UnifiedMarkerHandler.on_nonwear_markers_changed method."""

    def test_calls_nonwear_persistence_save(
        self,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Calls nonwear persistence save method."""
        nonwear_persistence = MagicMock()
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=nonwear_persistence,
        )

        handler.on_nonwear_markers_changed(
            markers=mock_markers,
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
        )

        nonwear_persistence.save.assert_called_once_with(
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
            markers=mock_markers,
        )

    def test_invokes_callbacks_after_save(
        self,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Invokes callbacks after successful save."""
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=MagicMock(),
        )
        callback = MagicMock()
        handler.add_on_save_callback(callback)

        handler.on_nonwear_markers_changed(
            markers=mock_markers,
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
        )

        callback.assert_called_once_with("nonwear", "test.csv", test_date)

    def test_callback_failure_does_not_stop_others(
        self,
        mock_markers: MagicMock,
        test_date: datetime,
    ) -> None:
        """Callback failure doesn't prevent other callbacks."""
        handler = UnifiedMarkerHandler(
            sleep_persistence=MagicMock(),
            nonwear_persistence=MagicMock(),
        )
        failing_callback = MagicMock(side_effect=RuntimeError("Callback error"))
        success_callback = MagicMock()
        handler.add_on_save_callback(failing_callback)
        handler.add_on_save_callback(success_callback)

        handler.on_nonwear_markers_changed(
            markers=mock_markers,
            filename="test.csv",
            participant_id="PART-001",
            date=test_date,
        )

        success_callback.assert_called_once()
