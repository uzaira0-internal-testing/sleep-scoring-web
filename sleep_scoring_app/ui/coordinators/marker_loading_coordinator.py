#!/usr/bin/env python3
"""
Marker Loading Coordinator for Sleep Scoring Application.

Handles async loading of markers from database when navigation changes.
Uses QTimer to break out of Redux dispatch before loading, ensuring
synchronous marker dispatch for immediate UI updates.

This is a Coordinator (not a Connector) because it:
- Uses Qt mechanisms (QTimer) for async coordination
- Dispatches actions (Connectors should NOT dispatch)
- Handles side effects (DB loading)
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

if TYPE_CHECKING:
    from sleep_scoring_app.data.database import DatabaseManager
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class MarkerLoadingCoordinator:
    """
    Coordinates marker loading from database when navigation changes.

    Subscribes to store and detects file/date changes. Uses QTimer.singleShot(0)
    to break out of the dispatch cycle, then loads markers and dispatches
    synchronously for immediate UI updates.
    """

    def __init__(
        self,
        store: "UIStore",
        db_manager: "DatabaseManager",
    ) -> None:
        """
        Initialize the marker loading coordinator.

        Args:
            store: Redux store to subscribe to and dispatch to
            db_manager: Database manager for loading markers

        """
        self.store = store
        self.db_manager = db_manager
        self._last_file: str | None = None
        self._last_date_str: str | None = None
        self._pending_load = False

        # Subscribe to store
        self._unsubscribe = store.subscribe(self._on_state_change)
        logger.info("MarkerLoadingCoordinator initialized")

    def _on_state_change(self, old_state: "UIState", new_state: "UIState") -> None:
        """
        Detect activity data changes and schedule marker loading.

        CRITICAL: We wait for activity_timestamps to change, NOT date index.
        This ensures data bounds are set before we try to load markers.
        The old approach triggered on date change, which raced with data loading
        and caused markers to be rejected as "out of bounds".
        """
        # Get current file and date
        current_file = new_state.current_file
        current_date_str = None
        if 0 <= new_state.current_date_index < len(new_state.available_dates):
            current_date_str = new_state.available_dates[new_state.current_date_index]

        # Check if ACTIVITY DATA changed (not just date index)
        # This means ActivityDataConnector has loaded data and PlotDataConnector has updated bounds
        data_changed = old_state.activity_timestamps != new_state.activity_timestamps
        _file_changed = current_file != self._last_file
        _date_changed = current_date_str != self._last_date_str

        # Only load markers when activity data changes AND we have valid data
        if data_changed and new_state.activity_timestamps and current_file and current_date_str:
            self._last_file = current_file
            self._last_date_str = current_date_str

            # Schedule load OUTSIDE of current dispatch using QTimer
            # This is the Coordinator pattern - use Qt mechanisms for async
            if not self._pending_load:
                self._pending_load = True
                QTimer.singleShot(0, self._load_markers)
                logger.debug(f"MARKER COORDINATOR: Scheduled marker load for {current_file} / {current_date_str}")

    def _load_markers(self) -> None:
        """Load markers from database and dispatch to store."""
        self._pending_load = False

        try:
            file = self._last_file
            date_str = self._last_date_str

            if not file or not date_str:
                logger.debug("MARKER COORDINATOR: No file/date to load")
                return

            filename = Path(file).name
            logger.info(f"MARKER COORDINATOR: Loading markers for {filename} / {date_str}")

            # Load sleep markers
            from sleep_scoring_app.core.dataclasses_markers import DailyNonwearMarkers

            metrics_list = self.db_manager.load_sleep_metrics(filename, date_str)
            sleep_metrics = metrics_list[0] if metrics_list else None

            # Load nonwear markers
            try:
                nonwear_markers = self.db_manager.load_manual_nonwear_markers(filename, date_str)
            except Exception as e:
                logger.warning(f"MARKER COORDINATOR: Error loading nonwear: {e}")
                nonwear_markers = DailyNonwearMarkers()

            # Dispatch markers to store (SYNC - we're outside dispatch now)
            from sleep_scoring_app.ui.store import Actions

            if sleep_metrics:
                from sleep_scoring_app.core.constants import SleepStatusValue

                if sleep_metrics.onset_time == SleepStatusValue.NO_SLEEP:
                    # "No sleep" was marked for this date
                    self.store.dispatch(
                        Actions.markers_loaded(sleep=None, nonwear=nonwear_markers, is_no_sleep=True, needs_consensus=sleep_metrics.needs_consensus)
                    )
                    logger.info("MARKER COORDINATOR: Date marked as 'no sleep'")
                elif sleep_metrics.daily_sleep_markers:
                    self.store.dispatch(
                        Actions.markers_loaded(
                            sleep=sleep_metrics.daily_sleep_markers,
                            nonwear=nonwear_markers,
                            is_no_sleep=False,
                            needs_consensus=sleep_metrics.needs_consensus,
                        )
                    )
                else:
                    self.store.dispatch(
                        Actions.markers_loaded(sleep=None, nonwear=nonwear_markers, is_no_sleep=False, needs_consensus=sleep_metrics.needs_consensus)
                    )
            else:
                # No saved metrics for this date - fresh slate
                self.store.dispatch(Actions.markers_loaded(sleep=None, nonwear=nonwear_markers, is_no_sleep=False))

            logger.info("MARKER COORDINATOR: Markers dispatched successfully")

        except Exception as e:
            logger.exception(f"MARKER COORDINATOR: Error loading markers: {e}")

    def disconnect(self) -> None:
        """Cleanup subscription."""
        self._unsubscribe()
        logger.info("MarkerLoadingCoordinator disconnected")
