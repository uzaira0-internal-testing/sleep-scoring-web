"""
Activity data connector.

Connects activity data loading to the Redux store.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class ActivityDataConnector:
    """
    Connects activity data loading to the Redux store.

    Sole authority for loading activity data from the data service into the store.
    Subscribes to file/date selection changes and dispatches all columns
    (timestamps, axis_x, axis_y, axis_z, vector_magnitude) to the store.
    """

    def __init__(self, store: UIStore, main_window: MainWindowProtocol) -> None:
        self.store = store
        self.main_window = main_window
        self._last_date_str: str | None = None
        self._last_file: str | None = None
        self._unsubscribe = store.subscribe(self._on_state_change)

        logger.info("ACTIVITY DATA CONNECTOR: Initialized")

    def _on_state_change(self, old_state: UIState, new_state: UIState) -> None:
        """React to file/date/config changes by loading activity data."""
        # Calculate current date string
        current_date_str = None
        if 0 <= new_state.current_date_index < len(new_state.available_dates):
            current_date_str = new_state.available_dates[new_state.current_date_index]

        # Check what changed
        file_changed = new_state.current_file != self._last_file
        date_changed = current_date_str != self._last_date_str
        config_changed = (
            old_state.auto_calibrate_enabled != new_state.auto_calibrate_enabled
            or old_state.impute_gaps_enabled != new_state.impute_gaps_enabled
            or old_state.preferred_display_column != new_state.preferred_display_column
        )

        should_reload = (file_changed or date_changed or config_changed) and new_state.current_file and current_date_str

        if should_reload:
            logger.info(
                f"ACTIVITY DATA CONNECTOR: Loading data. file_changed={file_changed}, "
                f"date_changed={date_changed}, config_changed={config_changed}, "
                f"file={new_state.current_file}, date={current_date_str}"
            )
            self._last_file = new_state.current_file
            self._last_date_str = current_date_str
            self._load_activity_data(new_state)

    def _load_activity_data(self, state: UIState) -> None:
        """
        Load unified activity data and dispatch to store.

        Calls data service DIRECTLY - no MainWindow intermediary.
        """
        from datetime import date

        from sleep_scoring_app.ui.store import Actions

        if not state.current_file or state.current_date_index < 0:
            logger.warning("ACTIVITY DATA CONNECTOR: Cannot load - no file or date selected")
            return

        if state.current_date_index >= len(state.available_dates):
            logger.warning("ACTIVITY DATA CONNECTOR: Date index out of range")
            return

        date_str = state.available_dates[state.current_date_index]
        target_date = date.fromisoformat(date_str)

        try:
            # MED-005 FIX: Use public API instead of accessing private _loading_service
            # Load ALL columns in ONE query - unified data
            unified_data = self.main_window.data_service.load_unified_activity_data(
                state.current_file,
                target_date,
                hours=48,
            )

            if not unified_data or not unified_data.get("timestamps"):
                logger.warning("ACTIVITY DATA CONNECTOR: Unified load returned no data")
                # Dispatch empty data - use dispatch_safe (sync when possible)
                self.store.dispatch_safe(
                    Actions.activity_data_loaded(
                        timestamps=[],
                        axis_x=[],
                        axis_y=[],
                        axis_z=[],
                        vector_magnitude=[],
                    )
                )
                return

            # Dispatch ALL columns to store - store is now single source of truth
            timestamps = unified_data["timestamps"]
            axis_x = unified_data.get("axis_x", [])
            axis_y = unified_data.get("axis_y", [])
            axis_z = unified_data.get("axis_z", [])
            vector_magnitude = unified_data.get("vector_magnitude", [])

            logger.info(
                f"ACTIVITY DATA CONNECTOR: Loaded {len(timestamps)} rows. "
                f"Dispatching to store: timestamps={len(timestamps)}, "
                f"axis_x={len(axis_x)}, axis_y={len(axis_y)}, "
                f"axis_z={len(axis_z)}, vm={len(vector_magnitude)}"
            )

            # Use dispatch_safe - sync when possible, async only if already in dispatch
            self.store.dispatch_safe(
                Actions.activity_data_loaded(
                    timestamps=list(timestamps),
                    axis_x=list(axis_x),
                    axis_y=list(axis_y),
                    axis_z=list(axis_z),
                    vector_magnitude=list(vector_magnitude),
                )
            )

        except Exception as e:
            logger.exception(f"ACTIVITY DATA CONNECTOR: Error loading data: {e}")
            # Dispatch empty data on error
            self.store.dispatch_safe(
                Actions.activity_data_loaded(
                    timestamps=[],
                    axis_x=[],
                    axis_y=[],
                    axis_z=[],
                    vector_magnitude=[],
                )
            )
            self.store.dispatch_safe(Actions.error_occurred(f"Failed to load activity data: {e}"))

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()
