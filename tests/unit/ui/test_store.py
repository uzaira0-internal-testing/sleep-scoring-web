"""
Tests for Redux-style UI Store.

Tests UIState, Actions, ui_reducer, Selectors, and UIStore.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import AlgorithmType, MarkerCategory
from sleep_scoring_app.ui.store import (
    Action,
    Actions,
    ActionType,
    Selectors,
    UIState,
    UIStore,
    create_side_effect_middleware,
    logging_middleware,
    ui_reducer,
)


class TestUIState:
    """Tests for UIState immutable dataclass."""

    def test_creates_with_defaults(self) -> None:
        """Creates state with default values."""
        state = UIState()

        assert state.current_file is None
        assert state.current_date_index == -1
        assert state.available_dates == ()
        assert state.view_mode_hours == 48

    def test_is_frozen(self) -> None:
        """State is immutable (frozen dataclass)."""
        state = UIState()

        with pytest.raises(AttributeError):
            state.current_file = "test.csv"

    def test_default_algorithm(self) -> None:
        """Default algorithm is Sadeh ActiLife."""
        state = UIState()

        assert state.current_algorithm == AlgorithmType.SADEH_1994_ACTILIFE

    def test_default_marker_mode(self) -> None:
        """Default marker mode is SLEEP."""
        state = UIState()

        assert state.marker_mode == MarkerCategory.SLEEP

    def test_default_marker_state(self) -> None:
        """Default marker state is clean (not dirty)."""
        state = UIState()

        assert state.current_sleep_markers is None
        assert state.current_nonwear_markers is None
        assert state.sleep_markers_dirty is False
        assert state.nonwear_markers_dirty is False

    def test_default_pending_requests(self) -> None:
        """Default pending requests are False."""
        state = UIState()

        assert state.pending_clear_activity is False
        assert state.pending_refresh_files is False

    def test_activity_data_defaults(self) -> None:
        """Activity data defaults to empty tuples."""
        state = UIState()

        assert state.activity_timestamps == ()
        assert state.axis_x_data == ()
        assert state.axis_y_data == ()
        assert state.axis_z_data == ()
        assert state.vector_magnitude_data == ()
        assert state.sadeh_results == ()


class TestAction:
    """Tests for Action dataclass."""

    def test_creates_with_type(self) -> None:
        """Creates action with type only."""
        action = Action(type=ActionType.RESET_STATE)

        assert action.type == ActionType.RESET_STATE
        assert action.payload is None

    def test_creates_with_payload(self) -> None:
        """Creates action with type and payload."""
        action = Action(
            type=ActionType.FILE_SELECTED,
            payload={"filename": "test.csv"},
        )

        assert action.type == ActionType.FILE_SELECTED
        assert action.payload == {"filename": "test.csv"}


class TestActionsFactory:
    """Tests for Actions static factory methods."""

    def test_file_selected(self) -> None:
        """Creates file_selected action."""
        action = Actions.file_selected(filename="test.csv")

        assert action.type == ActionType.FILE_SELECTED
        assert action.payload == {"filename": "test.csv"}

    def test_date_selected(self) -> None:
        """Creates date_selected action."""
        action = Actions.date_selected(date_index=5)

        assert action.type == ActionType.DATE_SELECTED
        assert action.payload == {"date_index": 5}

    def test_algorithm_changed(self) -> None:
        """Creates algorithm_changed action."""
        action = Actions.algorithm_changed(algorithm="cole_kripke_1992_actilife")

        assert action.type == ActionType.ALGORITHM_CHANGED
        assert action.payload == {"algorithm": "cole_kripke_1992_actilife"}

    def test_reset_state(self) -> None:
        """Creates reset_state action."""
        action = Actions.reset_state()

        assert action.type == ActionType.RESET_STATE
        assert action.payload is None

    def test_dates_loaded(self) -> None:
        """Creates dates_loaded action."""
        dates = ["2024-01-01", "2024-01-02"]
        action = Actions.dates_loaded(dates=dates)

        assert action.type == ActionType.DATES_LOADED
        assert action.payload == {"dates": dates}

    def test_files_loaded(self) -> None:
        """Creates files_loaded action."""
        files = [MagicMock()]
        action = Actions.files_loaded(files=files)

        assert action.type == ActionType.FILES_LOADED
        assert action.payload == {"files": files}

    def test_activity_data_loaded(self) -> None:
        """Creates activity_data_loaded action."""
        action = Actions.activity_data_loaded(
            timestamps=[1.0, 2.0],
            axis_x=[0.1, 0.2],
            axis_y=[0.3, 0.4],
            axis_z=[0.5, 0.6],
            vector_magnitude=[1.0, 1.1],
        )

        assert action.type == ActionType.ACTIVITY_DATA_LOADED
        assert action.payload["timestamps"] == [1.0, 2.0]
        assert action.payload["axis_y"] == [0.3, 0.4]

    def test_sadeh_results_computed(self) -> None:
        """Creates sadeh_results_computed action."""
        action = Actions.sadeh_results_computed(results=[0, 1, 1, 0])

        assert action.type == ActionType.SADEH_RESULTS_COMPUTED
        assert action.payload == {"results": [0, 1, 1, 0]}

    def test_activity_data_cleared(self) -> None:
        """Creates activity_data_cleared action."""
        action = Actions.activity_data_cleared()

        assert action.type == ActionType.ACTIVITY_DATA_CLEARED

    def test_view_mode_changed(self) -> None:
        """Creates view_mode_changed action."""
        action = Actions.view_mode_changed(hours=24)

        assert action.type == ActionType.VIEW_MODE_CHANGED
        assert action.payload == {"hours": 24}

    def test_database_mode_toggled(self) -> None:
        """Creates database_mode_toggled action."""
        action = Actions.database_mode_toggled(enabled=True)

        assert action.type == ActionType.DATABASE_MODE_TOGGLED
        assert action.payload == {"enabled": True}

    def test_auto_save_toggled(self) -> None:
        """Creates auto_save_toggled action."""
        action = Actions.auto_save_toggled(enabled=False)

        assert action.type == ActionType.AUTO_SAVE_TOGGLED
        assert action.payload == {"enabled": False}

    def test_marker_mode_changed(self) -> None:
        """Creates marker_mode_changed action."""
        action = Actions.marker_mode_changed(category=MarkerCategory.NONWEAR)

        assert action.type == ActionType.MARKER_MODE_CHANGED
        assert action.payload == {"category": MarkerCategory.NONWEAR}

    def test_date_navigated(self) -> None:
        """Creates date_navigated action."""
        action = Actions.date_navigated(direction=1)

        assert action.type == ActionType.DATE_NAVIGATED
        assert action.payload == {"direction": 1}

    def test_sleep_markers_changed(self) -> None:
        """Creates sleep_markers_changed action."""
        markers = MagicMock()
        action = Actions.sleep_markers_changed(markers=markers)

        assert action.type == ActionType.SLEEP_MARKERS_CHANGED
        assert action.payload == {"markers": markers}

    def test_nonwear_markers_changed(self) -> None:
        """Creates nonwear_markers_changed action."""
        markers = MagicMock()
        action = Actions.nonwear_markers_changed(markers=markers)

        assert action.type == ActionType.NONWEAR_MARKERS_CHANGED
        assert action.payload == {"markers": markers}

    def test_markers_saved(self) -> None:
        """Creates markers_saved action."""
        action = Actions.markers_saved()

        assert action.type == ActionType.MARKERS_SAVED

    def test_markers_loaded(self) -> None:
        """Creates markers_loaded action."""
        sleep = MagicMock()
        nonwear = MagicMock()
        action = Actions.markers_loaded(sleep=sleep, nonwear=nonwear, is_no_sleep=True)

        assert action.type == ActionType.MARKERS_LOADED
        assert action.payload["sleep"] is sleep
        assert action.payload["nonwear"] is nonwear
        assert action.payload["is_no_sleep"] is True

    def test_markers_cleared(self) -> None:
        """Creates markers_cleared action."""
        action = Actions.markers_cleared()

        assert action.type == ActionType.MARKERS_CLEARED

    def test_window_geometry_changed(self) -> None:
        """Creates window_geometry_changed action."""
        action = Actions.window_geometry_changed(x=100, y=200, width=800, height=600)

        assert action.type == ActionType.WINDOW_GEOMETRY_CHANGED
        assert action.payload == {"x": 100, "y": 200, "width": 800, "height": 600}

    def test_study_settings_changed(self) -> None:
        """Creates study_settings_changed action."""
        settings = {"night_start_hour": 22}
        action = Actions.study_settings_changed(settings=settings)

        assert action.type == ActionType.STUDY_SETTINGS_CHANGED
        assert action.payload == settings


class TestUIReducer:
    """Tests for ui_reducer pure function."""

    @pytest.fixture
    def initial_state(self) -> UIState:
        """Create initial state for tests."""
        return UIState()

    def test_file_selected(self, initial_state: UIState) -> None:
        """FILE_SELECTED sets current_file and resets date."""
        action = Actions.file_selected(filename="test.csv")

        new_state = ui_reducer(initial_state, action)

        assert new_state.current_file == "test.csv"
        assert new_state.current_date_index == -1
        assert new_state.available_dates == ()

    def test_file_selected_extracts_filename_from_path(self, initial_state: UIState) -> None:
        """FILE_SELECTED extracts filename from full path."""
        action = Actions.file_selected(filename="C:\\Users\\data\\test.csv")

        new_state = ui_reducer(initial_state, action)

        assert new_state.current_file == "test.csv"

    def test_date_selected(self, initial_state: UIState) -> None:
        """DATE_SELECTED updates current_date_index."""
        action = Actions.date_selected(date_index=3)

        new_state = ui_reducer(initial_state, action)

        assert new_state.current_date_index == 3

    def test_dates_loaded(self, initial_state: UIState) -> None:
        """DATES_LOADED sets available_dates."""
        action = Actions.dates_loaded(dates=["2024-01-01", "2024-01-02"])

        new_state = ui_reducer(initial_state, action)

        assert new_state.available_dates == ("2024-01-01", "2024-01-02")
        assert new_state.current_date_index == 0

    def test_dates_loaded_normalizes_datetime_objects(self, initial_state: UIState) -> None:
        """DATES_LOADED normalizes datetime objects to YYYY-MM-DD."""
        from datetime import datetime

        dates = [datetime(2024, 1, 15, 12, 30, 0)]
        action = Actions.dates_loaded(dates=dates)

        new_state = ui_reducer(initial_state, action)

        assert new_state.available_dates == ("2024-01-15",)

    def test_dates_loaded_normalizes_iso_timestamps(self, initial_state: UIState) -> None:
        """DATES_LOADED normalizes ISO timestamps to YYYY-MM-DD."""
        dates = ["2024-01-15T12:30:00"]
        action = Actions.dates_loaded(dates=dates)

        new_state = ui_reducer(initial_state, action)

        assert new_state.available_dates == ("2024-01-15",)

    def test_algorithm_changed(self, initial_state: UIState) -> None:
        """ALGORITHM_CHANGED updates current_algorithm."""
        action = Actions.algorithm_changed(algorithm="cole_kripke_1992_actilife")

        new_state = ui_reducer(initial_state, action)

        assert new_state.current_algorithm == "cole_kripke_1992_actilife"

    def test_activity_data_loaded(self, initial_state: UIState) -> None:
        """ACTIVITY_DATA_LOADED sets all activity data."""
        action = Actions.activity_data_loaded(
            timestamps=[1.0, 2.0],
            axis_x=[0.1, 0.2],
            axis_y=[0.3, 0.4],
            axis_z=[0.5, 0.6],
            vector_magnitude=[1.0, 1.1],
        )

        new_state = ui_reducer(initial_state, action)

        assert new_state.activity_timestamps == (1.0, 2.0)
        assert new_state.axis_x_data == (0.1, 0.2)
        assert new_state.axis_y_data == (0.3, 0.4)
        assert new_state.axis_z_data == (0.5, 0.6)
        assert new_state.vector_magnitude_data == (1.0, 1.1)
        assert new_state.sadeh_results == ()  # Cleared when new data loaded

    def test_sadeh_results_computed(self, initial_state: UIState) -> None:
        """SADEH_RESULTS_COMPUTED sets sadeh_results."""
        action = Actions.sadeh_results_computed(results=[0, 1, 1, 0])

        new_state = ui_reducer(initial_state, action)

        assert new_state.sadeh_results == (0, 1, 1, 0)

    def test_activity_data_cleared(self) -> None:
        """ACTIVITY_DATA_CLEARED clears all activity data."""
        state = UIState(
            activity_timestamps=(1.0, 2.0),
            axis_y_data=(0.1, 0.2),
            sadeh_results=(0, 1),
        )
        action = Actions.activity_data_cleared()

        new_state = ui_reducer(state, action)

        assert new_state.activity_timestamps == ()
        assert new_state.axis_y_data == ()
        assert new_state.sadeh_results == ()

    def test_view_mode_changed(self, initial_state: UIState) -> None:
        """VIEW_MODE_CHANGED updates view_mode_hours."""
        action = Actions.view_mode_changed(hours=24)

        new_state = ui_reducer(initial_state, action)

        assert new_state.view_mode_hours == 24

    def test_database_mode_toggled(self, initial_state: UIState) -> None:
        """DATABASE_MODE_TOGGLED updates database_mode."""
        action = Actions.database_mode_toggled(enabled=True)

        new_state = ui_reducer(initial_state, action)

        assert new_state.database_mode is True

    def test_auto_save_toggled(self, initial_state: UIState) -> None:
        """AUTO_SAVE_TOGGLED updates auto_save_enabled."""
        action = Actions.auto_save_toggled(enabled=False)

        new_state = ui_reducer(initial_state, action)

        assert new_state.auto_save_enabled is False

    def test_refresh_files_requested(self, initial_state: UIState) -> None:
        """REFRESH_FILES_REQUESTED sets pending flag."""
        action = Actions.refresh_files_requested()

        new_state = ui_reducer(initial_state, action)

        assert new_state.pending_refresh_files is True

    def test_clear_activity_data_requested(self, initial_state: UIState) -> None:
        """CLEAR_ACTIVITY_DATA_REQUESTED sets pending flag."""
        action = Actions.clear_activity_data_requested()

        new_state = ui_reducer(initial_state, action)

        assert new_state.pending_clear_activity is True

    def test_pending_request_cleared(self) -> None:
        """PENDING_REQUEST_CLEARED clears specific flag."""
        state = UIState(pending_clear_activity=True, pending_refresh_files=True)
        action = Actions.pending_request_cleared(request_type="clear_activity")

        new_state = ui_reducer(state, action)

        assert new_state.pending_clear_activity is False
        assert new_state.pending_refresh_files is True  # Unchanged

    def test_marker_mode_changed(self, initial_state: UIState) -> None:
        """MARKER_MODE_CHANGED updates marker_mode."""
        action = Actions.marker_mode_changed(category=MarkerCategory.NONWEAR)

        new_state = ui_reducer(initial_state, action)

        assert new_state.marker_mode == MarkerCategory.NONWEAR

    def test_date_navigated_forward(self) -> None:
        """DATE_NAVIGATED moves forward."""
        state = UIState(
            available_dates=("2024-01-01", "2024-01-02", "2024-01-03"),
            current_date_index=1,
        )
        action = Actions.date_navigated(direction=1)

        new_state = ui_reducer(state, action)

        assert new_state.current_date_index == 2

    def test_date_navigated_backward(self) -> None:
        """DATE_NAVIGATED moves backward."""
        state = UIState(
            available_dates=("2024-01-01", "2024-01-02", "2024-01-03"),
            current_date_index=1,
        )
        action = Actions.date_navigated(direction=-1)

        new_state = ui_reducer(state, action)

        assert new_state.current_date_index == 0

    def test_date_navigated_bounds_check(self) -> None:
        """DATE_NAVIGATED respects bounds."""
        state = UIState(
            available_dates=("2024-01-01", "2024-01-02"),
            current_date_index=1,
        )
        action = Actions.date_navigated(direction=1)  # Try to go past end

        new_state = ui_reducer(state, action)

        assert new_state.current_date_index == 1  # Stays at end

    def test_sleep_markers_changed(self, initial_state: UIState) -> None:
        """SLEEP_MARKERS_CHANGED sets markers and dirty flag."""
        markers = MagicMock()
        action = Actions.sleep_markers_changed(markers=markers)

        new_state = ui_reducer(initial_state, action)

        assert new_state.current_sleep_markers is markers
        assert new_state.sleep_markers_dirty is True

    def test_nonwear_markers_changed(self, initial_state: UIState) -> None:
        """NONWEAR_MARKERS_CHANGED sets markers and dirty flag."""
        markers = MagicMock()
        action = Actions.nonwear_markers_changed(markers=markers)

        new_state = ui_reducer(initial_state, action)

        assert new_state.current_nonwear_markers is markers
        assert new_state.nonwear_markers_dirty is True

    def test_markers_saved(self) -> None:
        """MARKERS_SAVED clears dirty flags."""
        state = UIState(
            sleep_markers_dirty=True,
            nonwear_markers_dirty=True,
            available_dates=("2024-01-15",),
            current_date_index=0,
            current_file="test.csv",
        )
        action = Actions.markers_saved()

        new_state = ui_reducer(state, action)

        assert new_state.sleep_markers_dirty is False
        assert new_state.nonwear_markers_dirty is False
        assert new_state.last_markers_save_time is not None
        assert new_state.last_saved_file == "test.csv"
        assert new_state.last_saved_date == "2024-01-15"

    def test_markers_loaded(self, initial_state: UIState) -> None:
        """MARKERS_LOADED sets markers without dirty flag."""
        sleep = MagicMock()
        nonwear = MagicMock()
        action = Actions.markers_loaded(sleep=sleep, nonwear=nonwear)

        new_state = ui_reducer(initial_state, action)

        assert new_state.current_sleep_markers is sleep
        assert new_state.current_nonwear_markers is nonwear
        assert new_state.sleep_markers_dirty is False
        assert new_state.nonwear_markers_dirty is False

    def test_markers_cleared(self) -> None:
        """MARKERS_CLEARED resets all marker state."""
        state = UIState(
            current_sleep_markers=MagicMock(),
            current_nonwear_markers=MagicMock(),
            sleep_markers_dirty=True,
        )
        action = Actions.markers_cleared()

        new_state = ui_reducer(state, action)

        assert new_state.current_sleep_markers is None
        assert new_state.current_nonwear_markers is None
        assert new_state.sleep_markers_dirty is False

    def test_reset_state(self) -> None:
        """RESET_STATE returns fresh default state."""
        state = UIState(
            current_file="test.csv",
            current_date_index=5,
            view_mode_hours=24,
        )
        action = Actions.reset_state()

        new_state = ui_reducer(state, action)

        assert new_state.current_file is None
        assert new_state.current_date_index == -1
        assert new_state.view_mode_hours == 48

    def test_window_geometry_changed(self, initial_state: UIState) -> None:
        """WINDOW_GEOMETRY_CHANGED updates geometry."""
        action = Actions.window_geometry_changed(x=100, y=200, width=800, height=600)

        new_state = ui_reducer(initial_state, action)

        assert new_state.window_x == 100
        assert new_state.window_y == 200
        assert new_state.window_width == 800
        assert new_state.window_height == 600

    def test_unknown_action_returns_same_state(self, initial_state: UIState) -> None:
        """Unknown action type returns same state."""
        action = Action(type="UNKNOWN_ACTION")

        new_state = ui_reducer(initial_state, action)

        assert new_state is initial_state


class TestSelectors:
    """Tests for Selectors static methods."""

    def test_current_file(self) -> None:
        """current_file returns current file."""
        state = UIState(current_file="test.csv")

        assert Selectors.current_file(state) == "test.csv"

    def test_current_date_index(self) -> None:
        """current_date_index returns date index."""
        state = UIState(current_date_index=5)

        assert Selectors.current_date_index(state) == 5

    def test_available_dates(self) -> None:
        """available_dates returns dates tuple."""
        dates = ("2024-01-01", "2024-01-02")
        state = UIState(available_dates=dates)

        assert Selectors.available_dates(state) == dates

    def test_has_file_selected_true(self) -> None:
        """has_file_selected returns True when file set."""
        state = UIState(current_file="test.csv")

        assert Selectors.has_file_selected(state) is True

    def test_has_file_selected_false(self) -> None:
        """has_file_selected returns False when no file."""
        state = UIState(current_file=None)

        assert Selectors.has_file_selected(state) is False


class TestUIStore:
    """Tests for UIStore class."""

    def test_creates_with_default_state(self) -> None:
        """Creates store with default state."""
        store = UIStore()

        assert store.state is not None
        assert store.state.current_file is None

    def test_creates_with_initial_state(self) -> None:
        """Creates store with provided initial state."""
        initial = UIState(current_file="test.csv")
        store = UIStore(initial_state=initial)

        assert store.state.current_file == "test.csv"

    def test_dispatch_changes_state(self) -> None:
        """dispatch() changes state via reducer."""
        store = UIStore()
        action = Actions.file_selected(filename="test.csv")

        store.dispatch(action)

        assert store.state.current_file == "test.csv"

    def test_dispatch_notifies_subscribers(self) -> None:
        """dispatch() notifies subscribers on state change."""
        store = UIStore()
        callback = MagicMock()
        store.subscribe(callback)

        store.dispatch(Actions.file_selected(filename="test.csv"))

        callback.assert_called_once()
        old_state, new_state = callback.call_args[0]
        assert old_state.current_file is None
        assert new_state.current_file == "test.csv"

    def test_dispatch_no_notify_if_no_change(self) -> None:
        """dispatch() does not notify if state unchanged."""
        store = UIStore(initial_state=UIState(view_mode_hours=48))
        callback = MagicMock()
        store.subscribe(callback)

        store.dispatch(Actions.view_mode_changed(hours=48))  # Same value

        callback.assert_not_called()

    def test_cannot_dispatch_during_dispatch(self) -> None:
        """Cannot dispatch while dispatch in progress (error is logged, not raised)."""
        store = UIStore()
        error_caught = []

        def nested_dispatch(old, new):
            try:
                store.dispatch(Actions.reset_state())
            except RuntimeError as e:
                error_caught.append(str(e))
                raise  # Re-raise for store to catch

        store.subscribe(nested_dispatch)

        # Store catches subscriber errors, so this won't raise
        store.dispatch(Actions.file_selected(filename="test.csv"))

        # But the error was logged and caught
        assert len(error_caught) == 1
        assert "Cannot dispatch" in error_caught[0]

    def test_subscribe_returns_unsubscribe(self) -> None:
        """subscribe() returns unsubscribe function."""
        store = UIStore()
        callback = MagicMock()

        unsubscribe = store.subscribe(callback)
        store.dispatch(Actions.file_selected(filename="first.csv"))

        assert callback.call_count == 1

        unsubscribe()
        store.dispatch(Actions.file_selected(filename="second.csv"))

        assert callback.call_count == 1  # Not called again

    def test_middleware_processes_actions(self) -> None:
        """Middleware processes actions before reducer."""
        store = UIStore()
        middleware_calls = []

        def track_middleware(action):
            middleware_calls.append(action.type)
            return action

        store.add_middleware(track_middleware)
        store.dispatch(Actions.file_selected(filename="test.csv"))

        assert ActionType.FILE_SELECTED in middleware_calls

    def test_middleware_can_cancel_action(self) -> None:
        """Middleware can cancel action by returning None."""
        store = UIStore()

        def cancel_middleware(action):
            return None  # Cancel all actions

        store.add_middleware(cancel_middleware)
        store.dispatch(Actions.file_selected(filename="test.csv"))

        assert store.state.current_file is None  # Action was cancelled

    def test_is_dispatching_property(self) -> None:
        """is_dispatching property reflects dispatch state."""
        store = UIStore()
        dispatching_during_callback = None

        def check_dispatching(old, new):
            nonlocal dispatching_during_callback
            dispatching_during_callback = store.is_dispatching

        store.subscribe(check_dispatching)
        store.dispatch(Actions.file_selected(filename="test.csv"))

        assert dispatching_during_callback is True
        assert store.is_dispatching is False  # After dispatch

    def test_dispatch_safe_uses_async_when_dispatching(self) -> None:
        """dispatch_safe uses async when already dispatching."""
        store = UIStore()
        safe_dispatch_called = False

        def callback(old, new):
            nonlocal safe_dispatch_called
            # This should not raise, uses async
            with patch.object(store, "dispatch_async") as mock_async:
                store.dispatch_safe(Actions.reset_state())
                safe_dispatch_called = mock_async.called

        store.subscribe(callback)
        store.dispatch(Actions.file_selected(filename="test.csv"))

        assert safe_dispatch_called is True

    def test_subscriber_error_does_not_stop_others(self) -> None:
        """Subscriber error does not prevent other subscribers."""
        store = UIStore()
        results = []

        def failing_callback(old, new):
            raise RuntimeError("Callback error")

        def success_callback(old, new):
            results.append("success")

        store.subscribe(failing_callback)
        store.subscribe(success_callback)

        # Should not raise
        store.dispatch(Actions.file_selected(filename="test.csv"))

        assert "success" in results


class TestMiddleware:
    """Tests for middleware functions."""

    def test_logging_middleware_returns_action(self) -> None:
        """logging_middleware returns action unchanged."""
        action = Actions.file_selected(filename="test.csv")

        result = logging_middleware(action)

        assert result is action

    def test_create_side_effect_middleware(self) -> None:
        """create_side_effect_middleware triggers side effects."""
        side_effect_called = []

        def file_selected_effect(action):
            side_effect_called.append(action.payload["filename"])

        side_effects = {ActionType.FILE_SELECTED: file_selected_effect}
        middleware = create_side_effect_middleware(side_effects)

        action = Actions.file_selected(filename="test.csv")
        result = middleware(action)

        assert result is action
        assert "test.csv" in side_effect_called

    def test_side_effect_middleware_handles_errors(self) -> None:
        """Side effect middleware handles errors gracefully."""

        def failing_effect(action):
            raise RuntimeError("Effect error")

        side_effects = {ActionType.FILE_SELECTED: failing_effect}
        middleware = create_side_effect_middleware(side_effects)

        action = Actions.file_selected(filename="test.csv")
        result = middleware(action)  # Should not raise

        assert result is action
