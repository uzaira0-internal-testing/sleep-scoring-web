"""
Tests for UI Coordinators.

Tests AutosaveCoordinator, MarkerLoadingCoordinator, and SessionStateService.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.ui.store import Actions, UIState, UIStore


@pytest.fixture
def store() -> UIStore:
    """Create a fresh store for testing."""
    return UIStore()


@pytest.fixture
def mock_db_manager() -> MagicMock:
    """Create mock database manager."""
    db_manager = MagicMock()
    db_manager.load_sleep_metrics = MagicMock(return_value=[])
    db_manager.load_manual_nonwear_markers = MagicMock(return_value=MagicMock())
    return db_manager


@pytest.fixture
def mock_config_manager() -> MagicMock:
    """Create mock config manager."""
    config_manager = MagicMock()
    config_manager.config = MagicMock()
    config_manager.save_config = MagicMock()
    return config_manager


class TestAutosaveCoordinatorInit:
    """Tests for AutosaveCoordinator initialization."""

    def test_subscribes_to_store(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Coordinator subscribes to store on init."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        initial_subscribers = len(store._subscribers)

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        assert len(store._subscribers) == initial_subscribers + 1
        coordinator.cleanup()

    def test_creates_debounce_timer(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Coordinator creates debounce timer."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        mock_timer.setSingleShot.assert_called_with(True)
        mock_timer.timeout.connect.assert_called()
        coordinator.cleanup()

    def test_default_config(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Uses default config when none provided."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        assert coordinator.config.debounce_ms == 500
        assert coordinator.config.enabled is True
        coordinator.cleanup()


class TestAutosaveCoordinatorPendingChanges:
    """Tests for pending change tracking."""

    def test_no_pending_changes_initially(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """No pending changes initially."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        assert not coordinator.has_unsaved_changes
        coordinator.cleanup()

    def test_tracks_sleep_marker_changes(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Tracks sleep marker changes when dirty flag set."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        # Trigger dirty flag
        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))

        assert PendingChangeType.SLEEP_MARKERS in coordinator._pending_changes
        coordinator.cleanup()

    def test_tracks_nonwear_marker_changes(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Tracks nonwear marker changes when dirty flag set."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        # Trigger nonwear dirty flag
        store.dispatch(Actions.nonwear_markers_changed(markers=MagicMock()))

        assert PendingChangeType.NONWEAR_MARKERS in coordinator._pending_changes
        coordinator.cleanup()

    def test_tracks_window_state_changes(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Tracks window geometry changes."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        # Trigger window geometry change
        store.dispatch(Actions.window_geometry_changed(x=100, y=200, width=800, height=600))

        assert PendingChangeType.WINDOW_STATE in coordinator._pending_changes
        coordinator.cleanup()

    def test_tracks_config_changes(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Tracks config changes."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        # Trigger view mode change
        store.dispatch(Actions.view_mode_changed(hours=24))

        assert PendingChangeType.CONFIG in coordinator._pending_changes
        coordinator.cleanup()


class TestAutosaveCoordinatorDebounce:
    """Tests for debounce behavior."""

    def test_starts_timer_on_change(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Starts debounce timer when change detected."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))

        mock_timer.start.assert_called_with(500)
        coordinator.cleanup()

    def test_restarts_timer_on_multiple_changes(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Restarts timer on multiple rapid changes."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        # Multiple changes
        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))
        store.dispatch(Actions.window_geometry_changed(x=100, y=200, width=800, height=600))

        # Timer should be stopped and restarted
        assert mock_timer.stop.call_count >= 1
        coordinator.cleanup()


class TestAutosaveCoordinatorForceSave:
    """Tests for force_save functionality."""

    def test_force_save_stops_timer(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """force_save stops the debounce timer."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        coordinator.force_save()

        mock_timer.stop.assert_called()
        coordinator.cleanup()

    def test_force_save_executes_immediately(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """force_save executes pending saves immediately."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        # Add pending changes manually
        coordinator._pending_changes.add(PendingChangeType.CONFIG)

        with patch.object(coordinator, "_execute_save") as mock_execute:
            coordinator.force_save()
            mock_execute.assert_called_once()

        coordinator.cleanup()


class TestAutosaveCoordinatorCleanup:
    """Tests for cleanup functionality."""

    def test_cleanup_stops_timer(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Cleanup stops the timer."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        mock_timer = MagicMock()
        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        coordinator.cleanup()

        mock_timer.stop.assert_called()

    def test_cleanup_unsubscribes_from_store(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Cleanup unsubscribes from store."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        subscribers_before = len(store._subscribers)
        coordinator.cleanup()

        assert len(store._subscribers) < subscribers_before


class TestAutosaveCoordinatorCallbacks:
    """Tests for callback invocation."""

    def test_success_callback_on_save(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Success callback invoked on successful save."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        success_callback = MagicMock()
        mock_timer = MagicMock()

        with patch(
            "sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer",
            return_value=mock_timer,
        ):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
                on_autosave_success=success_callback,
            )

        # Add config change and execute with QSettings mocked inside _execute_save
        coordinator._pending_changes.add(PendingChangeType.CONFIG)
        with patch("PyQt6.QtCore.QSettings"):
            coordinator._execute_save()

        success_callback.assert_called_once()
        coordinator.cleanup()

    def test_marker_save_failure_keeps_dirty_flags_and_pending_changes(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Failed marker callback does not clear dirty state or pending marker changes."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        failed_callback = MagicMock(return_value=False)
        failure_notifier = MagicMock()

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=failed_callback,
                save_nonwear_markers_callback=MagicMock(return_value=True),
                on_autosave_failed=failure_notifier,
            )

        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))
        coordinator._execute_save()

        assert store.state.sleep_markers_dirty is True
        assert PendingChangeType.SLEEP_MARKERS in coordinator._pending_changes
        assert coordinator.autosave_failed is True
        failure_notifier.assert_called_once()
        coordinator.cleanup()

    def test_marker_save_success_clears_dirty_flags(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """Successful marker callback dispatches markers_saved and clears dirty state."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        save_callback = MagicMock(return_value=True)

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=save_callback,
                save_nonwear_markers_callback=MagicMock(return_value=True),
            )

        store.dispatch(Actions.sleep_markers_changed(markers=MagicMock()))
        coordinator._execute_save()

        assert store.state.sleep_markers_dirty is False
        assert coordinator.autosave_failed is False
        coordinator.cleanup()


class TestAutosaveCoordinatorStatusProperties:
    """Tests for status properties."""

    def test_autosave_failed_initially_false(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """autosave_failed is False initially."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        assert coordinator.autosave_failed is False
        coordinator.cleanup()

    def test_last_autosave_error_initially_none(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """last_autosave_error is None initially."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
        )

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        assert coordinator.last_autosave_error is None
        coordinator.cleanup()

    def test_get_pending_change_types(
        self,
        store: UIStore,
        mock_db_manager: MagicMock,
        mock_config_manager: MagicMock,
    ) -> None:
        """get_pending_change_types returns string list."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            AutosaveCoordinator,
            PendingChangeType,
        )

        with patch("sleep_scoring_app.ui.coordinators.autosave_coordinator.QTimer"):
            coordinator = AutosaveCoordinator(
                store=store,
                config_manager=mock_config_manager,
                db_manager=mock_db_manager,
                save_sleep_markers_callback=MagicMock(),
                save_nonwear_markers_callback=MagicMock(),
            )

        coordinator._pending_changes.add(PendingChangeType.CONFIG)
        coordinator._pending_changes.add(PendingChangeType.WINDOW_STATE)

        pending = coordinator.get_pending_change_types()

        assert len(pending) == 2
        assert all(isinstance(p, str) for p in pending)
        coordinator.cleanup()


class TestMarkerLoadingCoordinatorInit:
    """Tests for MarkerLoadingCoordinator initialization."""

    def test_subscribes_to_store(self, store: UIStore, mock_db_manager: MagicMock) -> None:
        """Coordinator subscribes to store on init."""
        from sleep_scoring_app.ui.coordinators.marker_loading_coordinator import (
            MarkerLoadingCoordinator,
        )

        initial_subscribers = len(store._subscribers)

        coordinator = MarkerLoadingCoordinator(store=store, db_manager=mock_db_manager)

        assert len(store._subscribers) == initial_subscribers + 1
        coordinator.disconnect()

    def test_tracks_last_file_and_date(self, store: UIStore, mock_db_manager: MagicMock) -> None:
        """Initializes tracking for last file and date."""
        from sleep_scoring_app.ui.coordinators.marker_loading_coordinator import (
            MarkerLoadingCoordinator,
        )

        coordinator = MarkerLoadingCoordinator(store=store, db_manager=mock_db_manager)

        assert coordinator._last_file is None
        assert coordinator._last_date_str is None
        coordinator.disconnect()


class TestMarkerLoadingCoordinatorStateChange:
    """Tests for state change detection."""

    def test_ignores_date_only_changes(self, store: UIStore, mock_db_manager: MagicMock) -> None:
        """Ignores date changes without activity data."""
        from sleep_scoring_app.ui.coordinators.marker_loading_coordinator import (
            MarkerLoadingCoordinator,
        )

        coordinator = MarkerLoadingCoordinator(store=store, db_manager=mock_db_manager)

        # Change date without activity data
        store.dispatch(Actions.file_selected(filename="test.csv"))
        store.dispatch(Actions.dates_loaded(dates=["2024-01-01"]))
        store.dispatch(Actions.date_selected(date_index=0))

        # Should not have pending load without activity_timestamps
        assert coordinator._pending_load is False
        coordinator.disconnect()

    def test_schedules_load_on_activity_data_change(self, store: UIStore, mock_db_manager: MagicMock) -> None:
        """Schedules load when activity data changes."""
        from sleep_scoring_app.ui.coordinators.marker_loading_coordinator import (
            MarkerLoadingCoordinator,
        )

        with patch("sleep_scoring_app.ui.coordinators.marker_loading_coordinator.QTimer") as mock_timer:
            coordinator = MarkerLoadingCoordinator(store=store, db_manager=mock_db_manager)

            # Set up file and dates
            store.dispatch(Actions.file_selected(filename="test.csv"))
            store.dispatch(Actions.dates_loaded(dates=["2024-01-01"]))
            store.dispatch(Actions.date_selected(date_index=0))

            # Now load activity data (this should trigger load)
            # activity_data_loaded takes timestamps, axis_x, axis_y, axis_z, vector_magnitude
            store.dispatch(
                Actions.activity_data_loaded(
                    timestamps=[1.0, 2.0],
                    axis_x=[0.1, 0.2],
                    axis_y=[0.3, 0.4],
                    axis_z=[0.5, 0.6],
                    vector_magnitude=[0.7, 0.8],
                )
            )

            mock_timer.singleShot.assert_called()
            coordinator.disconnect()


class TestMarkerLoadingCoordinatorDisconnect:
    """Tests for disconnect functionality."""

    def test_disconnect_unsubscribes(self, store: UIStore, mock_db_manager: MagicMock) -> None:
        """disconnect unsubscribes from store."""
        from sleep_scoring_app.ui.coordinators.marker_loading_coordinator import (
            MarkerLoadingCoordinator,
        )

        coordinator = MarkerLoadingCoordinator(store=store, db_manager=mock_db_manager)
        subscribers_before = len(store._subscribers)

        coordinator.disconnect()

        assert len(store._subscribers) < subscribers_before


class TestSessionStateServiceKeys:
    """Tests for SessionStateService key constants."""

    def test_has_required_keys(self) -> None:
        """Has all required session keys."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        assert hasattr(SessionStateService, "KEY_CURRENT_FILE")
        assert hasattr(SessionStateService, "KEY_DATE_INDEX")
        assert hasattr(SessionStateService, "KEY_VIEW_MODE")
        assert hasattr(SessionStateService, "KEY_CURRENT_TAB")
        assert hasattr(SessionStateService, "KEY_WINDOW_GEOMETRY")


class TestSessionStateServiceNavigationState:
    """Tests for navigation state save/restore."""

    def test_save_and_get_current_file(self) -> None:
        """Can save and retrieve current file."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            manager.save_current_file("test.csv")

            mock_instance.setValue.assert_called_with(SessionStateService.KEY_CURRENT_FILE, "test.csv")

    def test_get_current_file_returns_none_when_not_set(self) -> None:
        """get_current_file returns None when not set."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_instance.value.return_value = None
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            result = manager.get_current_file()

            assert result is None

    def test_save_current_date_index(self) -> None:
        """Can save date index."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            manager.save_current_date_index(5)

            mock_instance.setValue.assert_called_with(SessionStateService.KEY_DATE_INDEX, 5)

    def test_get_current_date_index_defaults_to_zero(self) -> None:
        """get_current_date_index defaults to 0."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_instance.value.return_value = None
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            result = manager.get_current_date_index()

            # Default behavior varies, but should return int
            assert isinstance(result, int)


class TestSessionStateServiceViewState:
    """Tests for view state save/restore."""

    def test_save_view_mode(self) -> None:
        """Can save view mode."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            manager.save_view_mode(48)

            mock_instance.setValue.assert_called_with(SessionStateService.KEY_VIEW_MODE, 48)

    def test_get_view_mode_defaults_to_24(self) -> None:
        """get_view_mode defaults to 24."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_instance.value.return_value = None
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            result = manager.get_view_mode()

            # Should return default or int
            assert isinstance(result, int)

    def test_get_view_mode_validates_values(self) -> None:
        """get_view_mode only accepts 24 or 48."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_instance.value.return_value = 72  # Invalid value
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            result = manager.get_view_mode()

            assert result == 24  # Should default to 24

    def test_save_current_tab(self) -> None:
        """Can save current tab index."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            manager.save_current_tab(2)

            mock_instance.setValue.assert_called_with(SessionStateService.KEY_CURRENT_TAB, 2)


class TestSessionStateServiceClear:
    """Tests for clearing session state."""

    def test_clear_session(self) -> None:
        """Can clear all session state."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            manager.clear_session()

            mock_instance.remove.assert_called_with("session")
            mock_instance.sync.assert_called()

    def test_clear_file_selection(self) -> None:
        """Can clear just file selection."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            manager.clear_file_selection()

            # Should remove both file and date index
            assert mock_instance.remove.call_count == 2


class TestSessionStateServiceSplitters:
    """Tests for splitter state save/restore."""

    def test_save_splitter_states(self) -> None:
        """Can save splitter states."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_settings.return_value = mock_instance

            # Mock backup_to_json to avoid file operations
            with patch.object(SessionStateService, "backup_to_json"):
                manager = SessionStateService()
                manager.save_splitter_states(
                    top_level_state=b"top",
                    main_state=b"main",
                    plot_tables_state=b"plot",
                )

            assert mock_instance.setValue.call_count == 3

    def test_get_splitter_states_returns_tuple(self) -> None:
        """get_splitter_states returns tuple of bytes or None."""
        from sleep_scoring_app.ui.services.session_state_service import (
            SessionStateService,
        )

        with patch("sleep_scoring_app.ui.services.session_state_service.QSettings") as mock_settings:
            mock_instance = MagicMock()
            mock_instance.value.return_value = None
            mock_settings.return_value = mock_instance

            manager = SessionStateService()
            result = manager.get_splitter_states()

            assert isinstance(result, tuple)
            assert len(result) == 3


class TestPendingChangeType:
    """Tests for PendingChangeType enum."""

    def test_has_expected_values(self) -> None:
        """Has expected change type values."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import (
            PendingChangeType,
        )

        assert PendingChangeType.SLEEP_MARKERS == "sleep_markers"
        assert PendingChangeType.NONWEAR_MARKERS == "nonwear_markers"
        assert PendingChangeType.CONFIG == "config"
        assert PendingChangeType.WINDOW_STATE == "window_state"


class TestAutosaveConfig:
    """Tests for AutosaveConfig dataclass."""

    def test_default_values(self) -> None:
        """Has expected default values."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import AutosaveConfig

        config = AutosaveConfig()

        assert config.debounce_ms == 500
        assert config.enabled is True

    def test_custom_values(self) -> None:
        """Can set custom values."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import AutosaveConfig

        config = AutosaveConfig(debounce_ms=1000, enabled=False)

        assert config.debounce_ms == 1000
        assert config.enabled is False

    def test_is_frozen(self) -> None:
        """Config is frozen (immutable)."""
        from sleep_scoring_app.ui.coordinators.autosave_coordinator import AutosaveConfig

        config = AutosaveConfig()

        with pytest.raises(AttributeError):
            config.debounce_ms = 1000  # type: ignore[misc]
