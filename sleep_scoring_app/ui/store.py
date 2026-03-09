"""
Redux/Vuex-style State Management for Sleep Scoring App.

This module implements a unidirectional data flow pattern:
    Action -> Dispatch -> Reducer -> New State -> Notify Subscribers

Usage:
    # Create store (typically in main_window.py)
    store = UIStore()

    # Components subscribe to state changes
    store.subscribe(my_callback)

    # Dispatch actions to change state
    store.dispatch(Actions.file_selected(filename="file.gt3x"))
    store.dispatch(Actions.view_mode_changed(hours=24))

    # Components react to state changes in their callbacks
    def my_callback(old_state: UIState, new_state: UIState):
        if old_state.current_file != new_state.current_file:
            self._load_new_file(new_state.current_file)

Marker state is now managed entirely in the Redux store for unified state management.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    AlgorithmType,
    MarkerCategory,
    NonwearAlgorithm,
    SleepPeriodDetectorType,
    StudyDataParadigm,
)

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import FileInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UIState:
    """
    Immutable UI state container - Single source of truth for all application state.

    State can only be changed by dispatching actions to the store.
    Components subscribe to state changes and react accordingly.

    State is organized into logical sections:
    - File/Date Selection: current file, date index, available dates
    - Window Geometry: position, size (persisted to QSettings)
    - Algorithm Settings: selected algorithm for processing
    - View Mode: 24h vs 48h view
    - Marker State: current markers, dirty flags, save time
    - Metadata: last save info (for UI feedback)
    """

    # === File/Date Selection State ===
    current_file: str | None = None
    current_date_index: int = -1
    available_dates: tuple[str, ...] = ()  # ISO date strings for immutability
    available_files: tuple[FileInfo, ...] = ()  # File info objects

    # === Activity Data (SINGLE SOURCE OF TRUTH) ===
    # TODO(refactor): Review this section - is storing all 4 columns optimal?
    # Consider: memory usage, whether we need axis_x/axis_z, lazy loading
    # All activity data lives here - widgets just display it
    # Unified loading guarantees ALL columns have SAME timestamps (no alignment bugs)
    activity_timestamps: tuple = ()  # Immutable tuple of datetime
    axis_x_data: tuple = ()  # Immutable tuple of float
    axis_y_data: tuple = ()  # Immutable tuple of float (used by Sadeh)
    axis_z_data: tuple = ()  # Immutable tuple of float
    vector_magnitude_data: tuple = ()  # Immutable tuple of float
    preferred_display_column: str = ActivityDataPreference.AXIS_Y  # Which column to display
    sadeh_results: tuple = ()  # Immutable tuple of int (0=wake, 1=sleep)

    # === Algorithm State ===
    current_algorithm: str = AlgorithmType.SADEH_1994_ACTILIFE

    # === View Mode State ===
    view_mode_hours: int = 48  # 24 or 48
    database_mode: bool = False
    auto_save_enabled: bool = True
    marker_mode: MarkerCategory = MarkerCategory.SLEEP
    show_adjacent_markers: bool = True
    auto_calibrate_enabled: bool = True
    impute_gaps_enabled: bool = True

    # === Pending Requests (for effect handlers) ===
    # These flags are set by reducer and cleared by effect handlers after processing
    pending_clear_activity: bool = False
    pending_refresh_files: bool = False

    # === Navigation ===
    current_sleep_markers: Any = None  # DailySleepMarkers | None
    current_nonwear_markers: Any = None  # DailyNonwearMarkers | None
    sleep_markers_dirty: bool = False
    nonwear_markers_dirty: bool = False
    last_markers_save_time: float | None = None
    last_marker_update_time: float = 0.0  # Force updates for in-place mutations
    selected_period_index: int | None = None
    selected_nonwear_index: int = 0  # Which nonwear marker is selected (0 = none)
    is_no_sleep_marked: bool = False  # True if current date is marked as "no sleep"
    needs_consensus: bool = False  # True if current date needs consensus review

    # === Window Geometry (persisted to QSettings) ===
    window_x: int | None = None
    window_y: int | None = None
    window_width: int | None = None
    window_height: int | None = None
    window_maximized: bool = False

    # === Study Settings (persisted to Config) ===
    study_unknown_value: str = "Unknown"
    study_valid_groups: tuple[str, ...] = ("G1", "DEMO")
    study_valid_timepoints: tuple[str, ...] = ("T1", "T2", "T3")
    study_default_group: str = "G1"
    study_default_timepoint: str = "T1"
    study_participant_id_patterns: tuple[str, ...] = (r"(DEMO-\d{3})",)
    study_timepoint_pattern: str = r"(T[123])"
    study_group_pattern: str = r"(G1|DEMO)"
    data_paradigm: str = StudyDataParadigm.EPOCH_BASED
    sleep_algorithm_id: str = AlgorithmType.SADEH_1994_ACTILIFE
    onset_offset_rule_id: str = SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S
    night_start_hour: int = 22
    night_end_hour: int = 7
    nonwear_algorithm_id: str = NonwearAlgorithm.CHOI_2011
    choi_axis: str = ActivityDataPreference.VECTOR_MAGNITUDE

    # === UI Control State ===
    ui_controls_enabled: bool = True  # Enable/disable main UI controls

    # === Metadata (for UI feedback) ===
    last_saved_file: str | None = None
    last_saved_date: str | None = None

    # === Error Notification ===
    # Used by connectors to show errors to the user via status bar
    last_error_message: str | None = None
    last_error_time: float = 0.0  # Timestamp to distinguish same-message errors


class ActionType(StrEnum):
    """All possible action types."""

    # Initialization
    STATE_INITIALIZED = auto()

    # File/Date navigation
    FILE_SELECTED = auto()
    FILES_LOADED = auto()
    DATE_SELECTED = auto()
    DATES_LOADED = auto()  # Available dates for current file

    # Activity data loading
    ACTIVITY_DATA_LOADED = auto()  # Main activity data loaded
    SADEH_RESULTS_COMPUTED = auto()  # Sadeh algorithm completed
    ACTIVITY_DATA_CLEARED = auto()  # Clear all activity data

    # Algorithm state
    ALGORITHM_CHANGED = auto()

    # === Application Mode ===
    VIEW_MODE_CHANGED = "view_mode_changed"
    DATABASE_MODE_TOGGLED = "database_mode_toggled"
    REFRESH_FILES_REQUESTED = "refresh_files_requested"
    DELETE_FILES_REQUESTED = "delete_files_requested"
    CLEAR_ACTIVITY_DATA_REQUESTED = "clear_activity_data_requested"
    PENDING_REQUEST_CLEARED = "pending_request_cleared"
    AUTO_SAVE_TOGGLED = "auto_save_toggled"
    MARKER_MODE_CHANGED = auto()
    ADJACENT_MARKERS_TOGGLED = auto()
    DATE_NAVIGATED = auto()
    SELECTED_PERIOD_CHANGED = auto()
    SELECTED_NONWEAR_CHANGED = auto()
    CALIBRATION_TOGGLED = auto()
    IMPUTATION_TOGGLED = auto()
    PREFERRED_DISPLAY_COLUMN_CHANGED = auto()

    # === Navigation ===

    SLEEP_MARKERS_CHANGED = auto()
    NONWEAR_MARKERS_CHANGED = auto()
    MARKERS_SAVED = auto()
    MARKERS_LOADED = auto()
    MARKERS_CLEARED = auto()

    # Window geometry
    WINDOW_GEOMETRY_CHANGED = auto()
    WINDOW_MAXIMIZED_CHANGED = auto()

    # Study settings
    STUDY_SETTINGS_CHANGED = auto()

    # UI Controls
    UI_CONTROLS_ENABLED_CHANGED = auto()

    # State management
    RESET_STATE = auto()
    STATE_CLEARED = auto()  # Compound action: reset file, dates, markers, activity, files
    STATE_LOADED_FROM_SETTINGS = auto()

    # Error handling
    ERROR_OCCURRED = auto()
    ERROR_CLEARED = auto()

    # Consensus review flag
    CONSENSUS_FLAG_TOGGLED = auto()
    CONSENSUS_FLAG_LOADED = auto()


@dataclass(frozen=True)
class Action:
    """
    Represents an action that can change state.

    Actions are immutable and describe what happened, not how to update state.
    """

    type: ActionType
    payload: dict[str, Any] | None = None


class Actions:
    """
    Action creators - factory methods for creating actions.

    Usage:
        store.dispatch(Actions.file_selected(filename="file.gt3x"))
    """

    @staticmethod
    def file_selected(filename: str | None) -> Action:
        """Create action for when a file is selected."""
        return Action(
            type=ActionType.FILE_SELECTED,
            payload={"filename": filename},
        )

    @staticmethod
    def date_selected(date_index: int) -> Action:
        """Create action for when a date is selected."""
        return Action(
            type=ActionType.DATE_SELECTED,
            payload={"date_index": date_index},
        )

    @staticmethod
    def algorithm_changed(algorithm: str) -> Action:
        """Create action for when algorithm is changed."""
        return Action(
            type=ActionType.ALGORITHM_CHANGED,
            payload={"algorithm": algorithm},
        )

    @staticmethod
    def ui_controls_enabled_changed(enabled: bool) -> Action:
        """Create action for enabling/disabling main UI controls."""
        return Action(
            type=ActionType.UI_CONTROLS_ENABLED_CHANGED,
            payload={"enabled": enabled},
        )

    @staticmethod
    def reset_state() -> Action:
        """Create action for resetting all state to defaults."""
        return Action(type=ActionType.RESET_STATE)

    @staticmethod
    def state_cleared() -> Action:
        """Create compound action that resets file, dates, markers, activity data, and file list."""
        return Action(type=ActionType.STATE_CLEARED)

    @staticmethod
    def error_occurred(message: str) -> Action:
        """Create action for when an error occurs that should be shown to the user."""
        return Action(
            type=ActionType.ERROR_OCCURRED,
            payload={"message": message, "timestamp": time.time()},
        )

    @staticmethod
    def error_cleared() -> Action:
        """Create action for clearing the error message."""
        return Action(type=ActionType.ERROR_CLEARED)

    @staticmethod
    def dates_loaded(dates: list) -> Action:
        """
        Create action for when available dates are loaded.

        Args:
            dates: List of date objects or ISO format strings.

        """
        return Action(
            type=ActionType.DATES_LOADED,
            payload={"dates": dates},
        )

    @staticmethod
    def files_loaded(files: list[FileInfo]) -> Action:
        """Create action for when available files are loaded."""
        return Action(
            type=ActionType.FILES_LOADED,
            payload={"files": files},
        )

    @staticmethod
    def activity_data_loaded(
        timestamps: list,
        axis_x: list[float],
        axis_y: list[float],
        axis_z: list[float],
        vector_magnitude: list[float],
    ) -> Action:
        """
        Create action for when unified activity data is loaded.

        All columns come from ONE query with SAME timestamps - no alignment bugs.
        """
        return Action(
            type=ActionType.ACTIVITY_DATA_LOADED,
            payload={
                "timestamps": timestamps,
                "axis_x": axis_x,
                "axis_y": axis_y,
                "axis_z": axis_z,
                "vector_magnitude": vector_magnitude,
            },
        )

    @staticmethod
    def sadeh_results_computed(results: list[int]) -> Action:
        """Create action for when Sadeh algorithm completes."""
        return Action(
            type=ActionType.SADEH_RESULTS_COMPUTED,
            payload={"results": results},
        )

    @staticmethod
    def activity_data_cleared() -> Action:
        """Create action for clearing all activity data."""
        return Action(type=ActionType.ACTIVITY_DATA_CLEARED)

    @staticmethod
    def view_mode_changed(hours: int) -> Action:
        """Create action for changing view mode (24h or 48h)."""
        return Action(
            type=ActionType.VIEW_MODE_CHANGED,
            payload={"hours": hours},
        )

    @staticmethod
    def refresh_files_requested() -> Action:
        """Action representing a request to reload files from disk/db."""
        return Action(type=ActionType.REFRESH_FILES_REQUESTED)

    @staticmethod
    def delete_files_requested(filenames: list[str]) -> Action:
        """Action representing a request to delete files."""
        return Action(type=ActionType.DELETE_FILES_REQUESTED, payload={"filenames": filenames})

    @staticmethod
    def clear_activity_data_requested() -> Action:
        """Action representing a request to clear all activity data."""
        return Action(type=ActionType.CLEAR_ACTIVITY_DATA_REQUESTED)

    @staticmethod
    def pending_request_cleared(request_type: str) -> Action:
        """Clear a pending request flag after effect handler processes it."""
        return Action(type=ActionType.PENDING_REQUEST_CLEARED, payload={"request_type": request_type})

    @staticmethod
    def database_mode_toggled(enabled: bool) -> Action:
        return Action(type=ActionType.DATABASE_MODE_TOGGLED, payload={"enabled": enabled})

    @staticmethod
    def auto_save_toggled(enabled: bool) -> Action:
        return Action(type=ActionType.AUTO_SAVE_TOGGLED, payload={"enabled": enabled})

    @staticmethod
    def marker_mode_changed(category: MarkerCategory) -> Action:
        return Action(type=ActionType.MARKER_MODE_CHANGED, payload={"category": category})

    @staticmethod
    def adjacent_markers_toggled(enabled: bool) -> Action:
        return Action(type=ActionType.ADJACENT_MARKERS_TOGGLED, payload={"enabled": enabled})

    @staticmethod
    def date_navigated(direction: int) -> Action:
        return Action(type=ActionType.DATE_NAVIGATED, payload={"direction": direction})

    @staticmethod
    def selected_period_changed(index: int | None) -> Action:
        return Action(type=ActionType.SELECTED_PERIOD_CHANGED, payload={"index": index})

    @staticmethod
    def selected_nonwear_changed(index: int) -> Action:
        return Action(type=ActionType.SELECTED_NONWEAR_CHANGED, payload={"index": index})

    @staticmethod
    def calibration_toggled(enabled: bool) -> Action:
        return Action(type=ActionType.CALIBRATION_TOGGLED, payload={"enabled": enabled})

    @staticmethod
    def imputation_toggled(enabled: bool) -> Action:
        return Action(type=ActionType.IMPUTATION_TOGGLED, payload={"enabled": enabled})

    @staticmethod
    def preferred_display_column_changed(column: str) -> Action:
        """Create action for display column preference change (e.g., axis_y, vector_magnitude)."""
        return Action(type=ActionType.PREFERRED_DISPLAY_COLUMN_CHANGED, payload={"column": column})

    # === Navigation ===

    @staticmethod
    def window_geometry_changed(x: int, y: int, width: int, height: int) -> Action:
        """Create action for window geometry changes."""
        return Action(
            type=ActionType.WINDOW_GEOMETRY_CHANGED,
            payload={"x": x, "y": y, "width": width, "height": height},
        )

    @staticmethod
    def window_maximized_changed(maximized: bool) -> Action:
        """Create action for window maximized state changes."""
        return Action(
            type=ActionType.WINDOW_MAXIMIZED_CHANGED,
            payload={"maximized": maximized},
        )

    @staticmethod
    def state_loaded_from_settings(state_dict: dict[str, Any]) -> Action:
        """Create action for loading state from QSettings."""
        return Action(
            type=ActionType.STATE_LOADED_FROM_SETTINGS,
            payload=state_dict,
        )

    @staticmethod
    def study_settings_changed(settings: dict[str, Any]) -> Action:
        """Create action for updating study settings."""
        return Action(
            type=ActionType.STUDY_SETTINGS_CHANGED,
            payload=settings,
        )

    @staticmethod
    def sleep_markers_changed(markers: Any) -> Action:
        """Create action for when sleep markers are changed (sets dirty=True)."""
        return Action(
            type=ActionType.SLEEP_MARKERS_CHANGED,
            payload={"markers": markers},
        )

    @staticmethod
    def nonwear_markers_changed(markers: Any) -> Action:
        """Create action for when nonwear markers are changed (sets dirty=True)."""
        return Action(
            type=ActionType.NONWEAR_MARKERS_CHANGED,
            payload={"markers": markers},
        )

    @staticmethod
    def markers_saved() -> Action:
        """Create action for when markers are saved (sets both dirty=False, updates save_time)."""
        return Action(type=ActionType.MARKERS_SAVED)

    @staticmethod
    def markers_loaded(
        sleep: Any = None,
        nonwear: Any = None,
        is_no_sleep: bool = False,
        needs_consensus: bool = False,
    ) -> Action:
        """Create action for when markers are loaded from DB (clean load, not dirty)."""
        return Action(
            type=ActionType.MARKERS_LOADED,
            payload={
                "sleep": sleep,
                "nonwear": nonwear,
                "is_no_sleep": is_no_sleep,
                "needs_consensus": needs_consensus,
            },
        )

    @staticmethod
    def markers_cleared() -> Action:
        """Create action for when markers are cleared."""
        return Action(type=ActionType.MARKERS_CLEARED)

    @staticmethod
    def consensus_flag_toggled(needs_consensus: bool) -> Action:
        """Create action for when consensus flag checkbox is toggled."""
        return Action(
            type=ActionType.CONSENSUS_FLAG_TOGGLED,
            payload={"needs_consensus": needs_consensus},
        )

    @staticmethod
    def consensus_flag_loaded(needs_consensus: bool) -> Action:
        """Create action for when consensus flag is loaded from database for current date."""
        return Action(
            type=ActionType.CONSENSUS_FLAG_LOADED,
            payload={"needs_consensus": needs_consensus},
        )


def ui_reducer(state: UIState, action: Action) -> UIState:
    """
    Pure function that takes current state and action, returns new state.

    This is the ONLY place where state changes are defined.
    """
    match action.type:
        case ActionType.STATE_INITIALIZED:
            payload = action.payload or {}
            return replace(state, **payload)

        case ActionType.FILE_SELECTED:
            payload = action.payload or {}
            filename = payload.get("filename")

            # Database queries require filename-only, not full paths
            if filename and ("/" in filename or "\\" in filename):
                from pathlib import Path

                original = filename
                filename = Path(filename).name
                logger.warning(
                    "FILENAME FORMAT CORRECTED: Received path '%s', extracted filename '%s'. Database queries require filename-only.",
                    original,
                    filename,
                )

            return replace(
                state,
                current_file=filename,
                current_date_index=-1,  # Reset date when file changes
                available_dates=(),  # Clear dates - will be loaded separately
                # Reset marker state to prevent stale data from previous file
                current_sleep_markers=None,
                current_nonwear_markers=None,
                sleep_markers_dirty=False,
                nonwear_markers_dirty=False,
                selected_period_index=None,
                selected_nonwear_index=0,
                is_no_sleep_marked=False,
                needs_consensus=False,
                sadeh_results=(),
                activity_timestamps=(),
                last_marker_update_time=0.0,
            )

        case ActionType.FILES_LOADED:
            payload = action.payload or {}
            files = payload.get("files", [])
            return replace(
                state,
                available_files=tuple(files),
            )

        case ActionType.DATE_SELECTED:
            payload = action.payload or {}
            return replace(
                state,
                current_date_index=payload.get("date_index", -1),
            )

        case ActionType.DATES_LOADED:
            payload = action.payload or {}
            raw_dates = payload.get("dates", [])

            # Normalize to pure YYYY-MM-DD strings
            formatted_dates = []
            for d in raw_dates:
                if hasattr(d, "isoformat"):
                    # Datetime or Date object
                    formatted_dates.append(d.isoformat()[:10])
                else:
                    # String (could be ISO timestamp or pure date)
                    d_str = str(d)
                    if "T" in d_str:
                        formatted_dates.append(d_str.split("T")[0])
                    elif " " in d_str:
                        formatted_dates.append(d_str.split(" ")[0])
                    else:
                        formatted_dates.append(d_str[:10])

            dates_tuple = tuple(formatted_dates)

            # Try to preserve index if it's still valid, otherwise reset to 0
            new_index = state.current_date_index
            if new_index < 0 or new_index >= len(dates_tuple):
                new_index = 0 if dates_tuple else -1

            return replace(
                state,
                available_dates=dates_tuple,
                current_date_index=new_index,
            )

        case ActionType.ALGORITHM_CHANGED:
            payload = action.payload or {}
            return replace(
                state,
                current_algorithm=payload.get("algorithm", state.current_algorithm),
            )

        case ActionType.ACTIVITY_DATA_LOADED:
            payload = action.payload or {}
            return replace(
                state,
                activity_timestamps=tuple(payload.get("timestamps", [])),
                axis_x_data=tuple(payload.get("axis_x", [])),
                axis_y_data=tuple(payload.get("axis_y", [])),
                axis_z_data=tuple(payload.get("axis_z", [])),
                vector_magnitude_data=tuple(payload.get("vector_magnitude", [])),
                sadeh_results=(),  # Clear sadeh when new data loaded
            )

        case ActionType.SADEH_RESULTS_COMPUTED:
            payload = action.payload or {}
            return replace(
                state,
                sadeh_results=tuple(payload.get("results", [])),
            )

        case ActionType.ACTIVITY_DATA_CLEARED:
            return replace(
                state,
                activity_timestamps=(),
                axis_x_data=(),
                axis_y_data=(),
                axis_z_data=(),
                vector_magnitude_data=(),
                sadeh_results=(),
            )

        case ActionType.VIEW_MODE_CHANGED:
            payload = action.payload or {}
            return replace(
                state,
                view_mode_hours=payload.get("hours", 48),
            )

        case ActionType.DATABASE_MODE_TOGGLED:
            payload = action.payload or {}
            return replace(state, database_mode=payload.get("enabled", False))

        case ActionType.AUTO_SAVE_TOGGLED:
            payload = action.payload or {}
            return replace(state, auto_save_enabled=payload.get("enabled", True))

        case ActionType.UI_CONTROLS_ENABLED_CHANGED:
            payload = action.payload or {}
            return replace(state, ui_controls_enabled=payload.get("enabled", True))

        case ActionType.REFRESH_FILES_REQUESTED:
            # Set pending flag - effect handler will process and clear
            return replace(state, pending_refresh_files=True)

        case ActionType.CLEAR_ACTIVITY_DATA_REQUESTED:
            # Set pending flag - effect handler will process and clear
            return replace(state, pending_clear_activity=True)

        case ActionType.PENDING_REQUEST_CLEARED:
            payload = action.payload or {}
            request_type = payload.get("request_type", "")
            if request_type == "clear_activity":
                return replace(state, pending_clear_activity=False)
            if request_type == "refresh_files":
                return replace(state, pending_refresh_files=False)
            return state

        case ActionType.MARKER_MODE_CHANGED:
            payload = action.payload or {}
            return replace(state, marker_mode=payload.get("category", MarkerCategory.SLEEP))

        case ActionType.ADJACENT_MARKERS_TOGGLED:
            payload = action.payload or {}
            return replace(state, show_adjacent_markers=payload.get("enabled", True))

        case ActionType.DATE_NAVIGATED:
            payload = action.payload or {}
            direction = payload.get("direction", 0)
            if state.current_date_index != -1 and state.available_dates:
                new_index = state.current_date_index + direction
                # Bound check
                new_index = max(0, min(new_index, len(state.available_dates) - 1))
                return replace(state, current_date_index=new_index)
            return state

        case ActionType.SELECTED_PERIOD_CHANGED:
            payload = action.payload or {}
            return replace(state, selected_period_index=payload.get("index"))

        case ActionType.SELECTED_NONWEAR_CHANGED:
            payload = action.payload or {}
            return replace(state, selected_nonwear_index=payload.get("index", 0))

        case ActionType.CALIBRATION_TOGGLED:
            payload = action.payload or {}
            return replace(state, auto_calibrate_enabled=payload.get("enabled", True))

        case ActionType.IMPUTATION_TOGGLED:
            payload = action.payload or {}
            return replace(state, impute_gaps_enabled=payload.get("enabled", True))

        case ActionType.PREFERRED_DISPLAY_COLUMN_CHANGED:
            payload = action.payload or {}
            return replace(state, preferred_display_column=payload.get("column", ActivityDataPreference.AXIS_Y))

        case ActionType.WINDOW_GEOMETRY_CHANGED:
            payload = action.payload or {}
            return replace(
                state,
                window_x=payload.get("x"),
                window_y=payload.get("y"),
                window_width=payload.get("width"),
                window_height=payload.get("height"),
            )

        case ActionType.WINDOW_MAXIMIZED_CHANGED:
            payload = action.payload or {}
            return replace(
                state,
                window_maximized=payload.get("maximized", False),
            )

        case ActionType.STATE_LOADED_FROM_SETTINGS:
            payload = action.payload or {}

            loaded_file = payload.get("current_file", state.current_file)
            if loaded_file and ("/" in loaded_file or "\\" in loaded_file):
                from pathlib import Path

                original = loaded_file
                loaded_file = Path(loaded_file).name
                logger.warning("FILENAME FORMAT CORRECTED (settings load): Received path '%s', extracted filename '%s'.", original, loaded_file)

            # Merge loaded state with current state
            return replace(
                state,
                current_file=loaded_file,
                view_mode_hours=payload.get("view_mode_hours", state.view_mode_hours),
                database_mode=payload.get("database_mode", state.database_mode),
                window_x=payload.get("window_x", state.window_x),
                window_y=payload.get("window_y", state.window_y),
                window_width=payload.get("window_width", state.window_width),
                window_height=payload.get("window_height", state.window_height),
                window_maximized=payload.get("window_maximized", state.window_maximized),
            )

        case ActionType.STUDY_SETTINGS_CHANGED:
            payload = action.payload or {}
            # Filter payload to only include valid UIState fields
            valid_fields = {k: v for k, v in payload.items() if k in UIState.__dataclass_fields__}

            # Ensure lists are converted to tuples for immutability in state
            for k, v in valid_fields.items():
                if isinstance(v, list):
                    valid_fields[k] = tuple(v)

            return replace(state, **valid_fields)

        case ActionType.SLEEP_MARKERS_CHANGED:
            payload = action.payload or {}
            return replace(
                state,
                current_sleep_markers=payload.get("markers"),
                sleep_markers_dirty=True,
                last_marker_update_time=time.time(),
            )

        case ActionType.NONWEAR_MARKERS_CHANGED:
            payload = action.payload or {}
            return replace(
                state,
                current_nonwear_markers=payload.get("markers"),
                nonwear_markers_dirty=True,
                last_marker_update_time=time.time(),
            )

        case ActionType.MARKERS_SAVED:
            return replace(
                state,
                sleep_markers_dirty=False,
                nonwear_markers_dirty=False,
                last_markers_save_time=time.time(),
                last_saved_file=state.current_file,
                last_saved_date=state.available_dates[state.current_date_index]
                if 0 <= state.current_date_index < len(state.available_dates)
                else None,
                # Only clear "no sleep" flag when sleep markers were dirty (saving sleep means there IS sleep)
                is_no_sleep_marked=False if state.sleep_markers_dirty else state.is_no_sleep_marked,
            )

        case ActionType.MARKERS_LOADED:
            payload = action.payload or {}
            return replace(
                state,
                current_sleep_markers=payload.get("sleep"),
                current_nonwear_markers=payload.get("nonwear"),
                sleep_markers_dirty=False,
                nonwear_markers_dirty=False,
                last_markers_save_time=None,
                is_no_sleep_marked=payload.get("is_no_sleep", False),
                needs_consensus=payload.get("needs_consensus", False),
            )

        case ActionType.MARKERS_CLEARED:
            return replace(
                state,
                current_sleep_markers=None,
                current_nonwear_markers=None,
                sleep_markers_dirty=False,
                nonwear_markers_dirty=False,
                last_markers_save_time=None,
                is_no_sleep_marked=False,
                needs_consensus=False,
            )

        case ActionType.STATE_CLEARED:
            # Compound reset: file, dates, markers, activity, file list
            # Preserves window geometry, study settings, view mode, etc.
            return replace(
                state,
                current_file=None,
                current_date_index=-1,
                available_dates=(),
                available_files=(),
                current_sleep_markers=None,
                current_nonwear_markers=None,
                sleep_markers_dirty=False,
                nonwear_markers_dirty=False,
                last_markers_save_time=None,
                last_marker_update_time=0.0,
                selected_period_index=None,
                selected_nonwear_index=0,
                is_no_sleep_marked=False,
                needs_consensus=False,
                activity_timestamps=(),
                axis_x_data=(),
                axis_y_data=(),
                axis_z_data=(),
                vector_magnitude_data=(),
                sadeh_results=(),
            )

        case ActionType.RESET_STATE:
            return UIState()  # Return fresh default state

        case ActionType.ERROR_OCCURRED:
            if action.payload is None:
                return state
            return replace(
                state,
                last_error_message=action.payload["message"],
                last_error_time=action.payload["timestamp"],
            )

        case ActionType.ERROR_CLEARED:
            return replace(
                state,
                last_error_message=None,
            )

        case ActionType.CONSENSUS_FLAG_TOGGLED:
            payload = action.payload or {}
            return replace(
                state,
                needs_consensus=payload.get("needs_consensus", False),
            )

        case ActionType.CONSENSUS_FLAG_LOADED:
            payload = action.payload or {}
            return replace(
                state,
                needs_consensus=payload.get("needs_consensus", False),
            )

        case _:
            logger.warning("Unknown action type: %s", action.type)
            return state


class Selectors:
    """
    Selector functions to derive computed state.

    Selectors provide a clean API for accessing state and can compute derived values.
    Use these instead of directly accessing state fields.

    NOTE: Marker dirty state selectors require the save state manager to be passed in.
    """

    @staticmethod
    def current_file(state: UIState) -> str | None:
        """Get currently selected file."""
        return state.current_file

    @staticmethod
    def current_date_index(state: UIState) -> int:
        """Get currently selected date index."""
        return state.current_date_index

    @staticmethod
    def available_dates(state: UIState) -> tuple[str, ...]:
        """Get available dates for current file."""
        return state.available_dates

    @staticmethod
    def has_file_selected(state: UIState) -> bool:
        """Check if a file is currently selected."""
        return state.current_file is not None

    @staticmethod
    def has_date_selected(state: UIState) -> bool:
        """Check if a date is currently selected."""
        return state.current_date_index >= 0

    @staticmethod
    def current_date_string(state: UIState) -> str | None:
        """Get currently selected date as string."""
        if 0 <= state.current_date_index < len(state.available_dates):
            return state.available_dates[state.current_date_index]
        return None

    @staticmethod
    def current_algorithm(state: UIState) -> str:
        """Get currently selected algorithm."""
        return state.current_algorithm

    @staticmethod
    def view_mode_hours(state: UIState) -> int:
        """Get current view mode in hours (24 or 48)."""
        return state.view_mode_hours

    @staticmethod
    def is_database_mode(state: UIState) -> bool:
        """Check if database mode is enabled."""
        return state.database_mode

    @staticmethod
    def window_geometry(state: UIState) -> tuple[int | None, int | None, int | None, int | None]:
        """Get window geometry as (x, y, width, height)."""
        return (state.window_x, state.window_y, state.window_width, state.window_height)

    @staticmethod
    def is_window_maximized(state: UIState) -> bool:
        """Check if window is maximized."""
        return state.window_maximized

    @staticmethod
    def current_sleep_markers(state: UIState) -> Any:
        """Get current sleep markers."""
        return state.current_sleep_markers

    @staticmethod
    def current_nonwear_markers(state: UIState) -> Any:
        """Get current nonwear markers."""
        return state.current_nonwear_markers

    @staticmethod
    def is_sleep_markers_dirty(state: UIState) -> bool:
        """Check if sleep markers have unsaved changes."""
        return state.sleep_markers_dirty

    @staticmethod
    def is_nonwear_markers_dirty(state: UIState) -> bool:
        """Check if nonwear markers have unsaved changes."""
        return state.nonwear_markers_dirty

    @staticmethod
    def is_any_markers_dirty(state: UIState) -> bool:
        """Check if ANY marker type has unsaved changes."""
        return state.sleep_markers_dirty or state.nonwear_markers_dirty

    @staticmethod
    def last_markers_save_time(state: UIState) -> float | None:
        """Get the timestamp of the last marker save."""
        return state.last_markers_save_time

    @staticmethod
    def last_saved_file(state: UIState) -> str | None:
        """Get last saved file."""
        return state.last_saved_file

    @staticmethod
    def last_saved_date(state: UIState) -> str | None:
        """Get last saved date."""
        return state.last_saved_date


# Type for subscriber callbacks
StateChangeCallback = Callable[[UIState, UIState], None]
UnsubscribeFunction = Callable[[], None]


class UIStore:
    """
    Central store that holds state and manages subscriptions.

    The store:
    - Holds the single source of truth for UI state
    - Dispatches actions through the reducer
    - Notifies subscribers when state changes
    - Supports middleware for logging, async actions, etc.
    """

    def __init__(self, initial_state: UIState | None = None) -> None:
        """
        Initialize the store.

        Args:
            initial_state: Optional initial state, defaults to UIState()

        """
        self._state = initial_state or UIState()
        self._subscribers: list[StateChangeCallback] = []
        self._middleware: list[Callable[[Action], Action | None]] = []
        self._is_dispatching = False

        logger.info("UIStore initialized with state: %s", self._state)

    @property
    def state(self) -> UIState:
        """Get current state (read-only)."""
        return self._state

    def dispatch(self, action: Action) -> None:
        """Dispatch an action to change state."""
        if self._is_dispatching:
            msg = f"Cannot dispatch {action.type} while a dispatch is in progress."
            raise RuntimeError(msg)

        try:
            self._is_dispatching = True
            logger.info(f"ACTION DISPATCHED: {action.type} | Payload: {action.payload}")

            # Run middleware
            processed_action: Action | None = action
            for middleware in self._middleware:
                if processed_action is None:
                    return
                processed_action = middleware(processed_action)

            if processed_action is None:
                return

            # Get new state from reducer
            old_state = self._state
            new_state = ui_reducer(old_state, processed_action)

            # Only notify if state actually changed
            if old_state != new_state:
                diff = self._get_state_diff(old_state, new_state)
                self._state = new_state
                logger.info(f"STATE CHANGED: {processed_action.type} | Diff: {diff}")
                self._notify_subscribers(old_state, new_state)
            else:
                logger.debug(f"STATE UNCHANGED: {processed_action.type}")

        finally:
            self._is_dispatching = False

    def dispatch_async(self, action: Action) -> None:
        """
        Dispatch an action asynchronously on the next event loop iteration.
        Useful for dispatching from within subscriber callbacks.
        """
        logger.debug(f"ASYNC DISPATCH QUEUED: {action.type}")
        from PyQt6.QtCore import QTimer

        QTimer.singleShot(0, lambda: self.dispatch(action))

    @property
    def is_dispatching(self) -> bool:
        """Check if a dispatch is currently in progress."""
        return self._is_dispatching

    def dispatch_safe(self, action: Action) -> None:
        """
        Dispatch sync if safe, async if in dispatch.
        Use this when you want immediate dispatch when possible.
        """
        if self._is_dispatching:
            logger.debug(f"DISPATCH_SAFE: Using async for {action.type} (in dispatch)")
            self.dispatch_async(action)
        else:
            logger.debug(f"DISPATCH_SAFE: Using sync for {action.type}")
            self.dispatch(action)

    def dispatch_then(self, action: Action, callback: Callable[[], None]) -> None:
        """
        Dispatch an action and call callback immediately after dispatch completes.
        If already in dispatch, queues both for after current dispatch.
        """
        if self._is_dispatching:
            from PyQt6.QtCore import QTimer

            def run_both() -> None:
                self.dispatch(action)
                callback()

            QTimer.singleShot(0, run_both)
        else:
            self.dispatch(action)
            callback()

    def subscribe(self, callback: StateChangeCallback) -> UnsubscribeFunction:
        """Subscribe to state changes."""
        self._subscribers.append(callback)
        cb_name = getattr(callback, "__qualname__", str(callback))
        logger.info(f"SUBSCRIBER ADDED: {cb_name} | Total subscribers: {len(self._subscribers)}")

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)
                logger.info(f"SUBSCRIBER REMOVED: {cb_name}")

        return unsubscribe

    def add_middleware(self, middleware: Callable[[Action], Action | None]) -> None:
        """
        Add middleware to process actions before they reach the reducer.

        Middleware can:
        - Log actions
        - Modify actions
        - Cancel actions (return None)
        - Trigger side effects

        Args:
            middleware: Function that takes an action and returns modified action or None

        """
        self._middleware.append(middleware)

    def _notify_subscribers(self, old_state: UIState, new_state: UIState) -> None:
        """Notify all subscribers of state change."""
        for callback in self._subscribers[:]:  # Copy list to allow unsubscribe during iteration
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.exception("Error in subscriber callback: %s", e)

    def _get_state_diff(self, old_state: UIState, new_state: UIState) -> dict[str, tuple[Any, Any]]:
        """Get dictionary of changed fields for logging."""
        diff = {}
        for field in UIState.__dataclass_fields__:
            old_val = getattr(old_state, field)
            new_val = getattr(new_state, field)
            if old_val != new_val:
                diff[field] = (old_val, new_val)
        return diff

    def load_from_qsettings(self, settings: Any) -> None:
        """
        Load state from QSettings at application startup.

        This should be called once after creating the store but before
        connecting components.

        Args:
            settings: QSettings instance to load from

        """
        from sleep_scoring_app.ui.store import Actions

        state_dict = {
            "current_file": settings.value("current_file", "") or None,
            "view_mode_hours": settings.value("view_mode_hours", 48, type=int),
            "database_mode": settings.value("database_mode", False, type=bool),
            "window_x": settings.value("window_x", type=int),
            "window_y": settings.value("window_y", type=int),
            "window_width": settings.value("window_width", type=int),
            "window_height": settings.value("window_height", type=int),
            "window_maximized": settings.value("window_maximized", False, type=bool),
        }

        # Filter out None values for geometry (if not set)
        state_dict = {k: v for k, v in state_dict.items() if v is not None}

        self.dispatch(Actions.state_loaded_from_settings(state_dict))
        logger.info("Loaded state from QSettings: %s", state_dict)

    def initialize_from_config(self, config: Any) -> None:
        """Initialize Redux state from application configuration."""
        initial_state = {
            "view_mode_hours": getattr(config, "view_mode_hours", 48),
            "auto_save_enabled": getattr(config, "auto_save_markers", True),
            "database_mode": getattr(config, "use_database", False),
            "show_adjacent_markers": getattr(config, "show_adjacent_day_markers", True),
            "auto_calibrate_enabled": getattr(config, "auto_calibrate", True),
            "impute_gaps_enabled": getattr(config, "impute_gaps", True),
            "current_algorithm": getattr(config, "sleep_algorithm_id", AlgorithmType.SADEH_1994_ACTILIFE),
            # Study Settings
            "study_unknown_value": getattr(config, "study_unknown_value", "Unknown"),
            "study_valid_groups": tuple(getattr(config, "study_valid_groups", ["G1", "DEMO"])),
            "study_valid_timepoints": tuple(getattr(config, "study_valid_timepoints", ["T1", "T2", "T3"])),
            "study_default_group": getattr(config, "study_default_group", "G1"),
            "study_default_timepoint": getattr(config, "study_default_timepoint", "T1"),
            "study_participant_id_patterns": tuple(getattr(config, "study_participant_id_patterns", [r"(DEMO-\d{3})"])),
            "study_timepoint_pattern": getattr(config, "study_timepoint_pattern", r"(T[123])"),
            "study_group_pattern": getattr(config, "study_group_pattern", r"(G1|DEMO)"),
            "data_paradigm": getattr(config, "data_paradigm", StudyDataParadigm.EPOCH_BASED),
            "sleep_algorithm_id": getattr(config, "sleep_algorithm_id", AlgorithmType.SADEH_1994_ACTILIFE),
            "onset_offset_rule_id": getattr(config, "onset_offset_rule_id", SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S),
            "night_start_hour": getattr(config, "night_start_hour", 22),
            "night_end_hour": getattr(config, "night_end_hour", 7),
            "nonwear_algorithm_id": getattr(config, "nonwear_algorithm_id", NonwearAlgorithm.CHOI_2011),
            "choi_axis": getattr(config, "choi_axis", ActivityDataPreference.VECTOR_MAGNITUDE),
        }
        self.dispatch(Action(type=ActionType.STATE_INITIALIZED, payload=initial_state))
        logger.info("Initialized state from AppConfig: %s", initial_state)


def logging_middleware(action: Action) -> Action:
    """Middleware that logs all actions."""
    logger.info("Action dispatched: %s, payload: %s", action.type, action.payload)
    return action


def create_side_effect_middleware(
    side_effects: dict[ActionType, Callable[[Action], None]],
) -> Callable[[Action], Action]:
    """
    Create middleware that triggers side effects for specific actions.

    This is where you put effects like cache invalidation, API calls, etc.

    Args:
        side_effects: Dict mapping action types to side effect functions

    Returns:
        Middleware function

    """

    def middleware(action: Action) -> Action:
        if action.type in side_effects:
            try:
                side_effects[action.type](action)
            except Exception as e:
                logger.exception("Error in side effect for %s: %s", action.type, e)
        return action

    return middleware


def connect_component(
    store: UIStore,
    component: Any,
    state_to_props: Callable[[UIState], dict[str, Any]],
    handlers: dict[str, Callable[[Any], None]],
) -> UnsubscribeFunction:
    """
    Connect a component to the store (similar to Redux connect()).

    Args:
        store: The UI store
        component: The component to connect
        state_to_props: Function that extracts relevant state for this component
        handlers: Dict mapping prop names to handler functions

    Returns:
        Unsubscribe function

    Example:
        connect_component(
            store,
            save_button,
            state_to_props=lambda s: {"saved": s.markers_saved},
            handlers={"saved": lambda saved: button.setText("Saved" if saved else "Save")}
        )

    """
    last_props: dict[str, Any] = {}

    def on_state_change(old_state: UIState, new_state: UIState) -> None:
        nonlocal last_props
        new_props = state_to_props(new_state)

        for prop_name, value in new_props.items():
            if prop_name not in last_props or last_props[prop_name] != value:
                if prop_name in handlers:
                    handlers[prop_name](value)

        last_props = new_props

    # Initial render with current state
    initial_props = state_to_props(store.state)
    for prop_name, value in initial_props.items():
        if prop_name in handlers:
            handlers[prop_name](value)
    last_props = initial_props

    return store.subscribe(on_state_change)
