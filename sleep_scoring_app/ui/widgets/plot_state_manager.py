#!/usr/bin/env python3
"""
Plot State Manager for Activity Plot Widget.

Manages state capture and restoration for the activity plot including:
- Complete state serialization for tab switching
- Marker state preservation
- View configuration saving
- Algorithm result caching
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


class PlotStateManager:
    """
    Manages state operations for the activity plot widget.

    Responsibilities:
    - Capture complete widget state
    - Restore widget state
    - Manage state transitions
    - Handle state validation
    """

    def __init__(self, parent: ActivityPlotWidget) -> None:
        """Initialize the plot state manager."""
        self.parent = parent
        self.saved_state: dict[str, Any] | None = None
        logger.info("PlotStateManager initialized")

    def capture_complete_state(self) -> dict[str, Any]:
        """
        Capture the complete state of the plot widget.

        This will replace the 222-line monster method in ActivityPlotWidget.

        Returns:
            Complete state dictionary

        """
        state = {}

        # Capture data state
        state["data"] = self._capture_data_state()

        # Capture marker state
        state["markers"] = self._capture_marker_state()

        # Capture view state
        state["view"] = self._capture_view_state()

        # Capture algorithm state
        state["algorithms"] = self._capture_algorithm_state()

        # Capture visual state
        state["visual"] = self._capture_visual_state()

        # Capture interaction state
        state["interaction"] = self._capture_interaction_state()

        logger.debug("Captured complete plot state")
        return state

    def _capture_data_state(self) -> dict[str, Any]:
        """Capture data-related state."""
        return {
            "timestamps": self.parent.timestamps,
            "activity_data": self.parent.activity_data,
            "main_48h_timestamps": self.parent.main_48h_timestamps,
            "main_48h_activity": self.parent.main_48h_activity,
            "main_48h_axis_y_data": self.parent.main_48h_axis_y_data,
            "main_48h_sadeh_results": self.parent.main_48h_sadeh_results,
            "data_start_time": getattr(self.parent, "data_start_time", None),
            "data_end_time": getattr(self.parent, "data_end_time", None),
        }

    def _capture_marker_state(self) -> dict[str, Any]:
        """Capture marker-related state."""
        return {
            "daily_sleep_markers": getattr(self.parent, "daily_sleep_markers", None),
            "current_marker_being_placed": getattr(self.parent, "current_marker_being_placed", None),
            "selected_marker_set_index": getattr(self.parent, "selected_marker_set_index", 1),
            "marker_lines": getattr(self.parent, "marker_lines", {}),
            "marker_labels": getattr(self.parent, "marker_labels", {}),
            "sleep_period_regions": getattr(self.parent, "sleep_period_regions", {}),
        }

    def _capture_view_state(self) -> dict[str, Any]:
        """Capture view-related state."""
        view_range = self.parent.getViewBox().viewRange()
        return {
            "view_range": view_range,
            "view_start_idx": getattr(self.parent, "view_start_idx", 0),
            "view_end_idx": getattr(self.parent, "view_end_idx", 0),
            "current_view_hours": getattr(self.parent, "current_view_hours", 48),
            "x_range": view_range[0] if view_range else None,
            "y_range": view_range[1] if view_range else None,
        }

    def _capture_algorithm_state(self) -> dict[str, Any]:
        """Capture algorithm-related state."""
        return {
            "sadeh_results": getattr(self.parent, "sadeh_results", []),
            "choi_nonwear_cache": getattr(self.parent, "_choi_nonwear_cache", {}),
            "nonwear_regions": getattr(self.parent, "nonwear_regions", []),
            "sleep_rule_arrows": getattr(self.parent, "sleep_rule_arrows", {}),
        }

    def _capture_visual_state(self) -> dict[str, Any]:
        """Capture visual-related state."""
        return {
            "activity_curve": getattr(self.parent, "activity_curve", None),
            "sadeh_curve": getattr(self.parent, "sadeh_curve", None),
            "choi_curve": getattr(self.parent, "choi_curve", None),
            "custom_table_colors": getattr(self.parent, "custom_table_colors", None),
            "adjacent_day_items": getattr(self.parent, "adjacent_day_items", []),
        }

    def _capture_interaction_state(self) -> dict[str, Any]:
        """Capture interaction-related state."""
        return {
            "interaction_enabled": getattr(self.parent, "interaction_enabled", True),
            "marker_drag_in_progress": getattr(self.parent, "marker_drag_in_progress", False),
            "dragged_marker": getattr(self.parent, "dragged_marker", None),
            "is_dragging": getattr(self.parent, "is_dragging", False),
        }

    def restore_complete_state(self, state: dict[str, Any]) -> None:
        """
        Restore the complete state of the plot widget.

        This will replace the 196-line monster method in ActivityPlotWidget.

        Args:
            state: Complete state dictionary to restore

        """
        if not state:
            logger.warning("No state to restore")
            return

        try:
            # Restore in specific order for dependencies
            self._restore_data_state(state.get("data", {}))
            self._restore_view_state(state.get("view", {}))
            self._restore_marker_state(state.get("markers", {}))
            self._restore_algorithm_state(state.get("algorithms", {}))
            self._restore_visual_state(state.get("visual", {}))
            self._restore_interaction_state(state.get("interaction", {}))

            # Trigger UI updates (protocol-guaranteed method)
            self.parent.redraw_plot()

            logger.debug("Restored complete plot state")

        except Exception as e:
            logger.error(f"Error restoring plot state: {e}", exc_info=True)

    def _restore_data_state(self, data_state: dict[str, Any]) -> None:
        """Restore data-related state."""
        if not data_state:
            return

        self.parent.timestamps = data_state.get("timestamps", [])
        self.parent.activity_data = data_state.get("activity_data", [])
        self.parent.main_48h_timestamps = data_state.get("main_48h_timestamps")
        self.parent.main_48h_activity = data_state.get("main_48h_activity")
        self.parent.main_48h_axis_y_data = data_state.get("main_48h_axis_y_data")
        self.parent.main_48h_sadeh_results = data_state.get("main_48h_sadeh_results")

        if "data_start_time" in data_state:
            self.parent.data_start_time = data_state["data_start_time"]
        if "data_end_time" in data_state:
            self.parent.data_end_time = data_state["data_end_time"]

    def _restore_view_state(self, view_state: dict[str, Any]) -> None:
        """Restore view-related state."""
        if not view_state:
            return

        self.parent.view_start_idx = view_state.get("view_start_idx", 0)
        self.parent.view_end_idx = view_state.get("view_end_idx", 0)
        self.parent.current_view_hours = view_state.get("current_view_hours", 48)

        # Restore view range
        if view_state.get("view_range"):
            try:
                self.parent.getViewBox().setRange(xRange=view_state["view_range"][0], yRange=view_state["view_range"][1], padding=0)
            except Exception as e:
                logger.warning(f"Could not restore view range: {e}")

    def _restore_marker_state(self, marker_state: dict[str, Any]) -> None:
        """Restore marker-related state."""
        if not marker_state:
            return

        self.parent.daily_sleep_markers = marker_state.get("daily_sleep_markers")
        self.parent.current_marker_being_placed = marker_state.get("current_marker_being_placed")
        self.parent.selected_marker_set_index = marker_state.get("selected_marker_set_index", 1)
        self.parent.marker_lines = marker_state.get("marker_lines", {})
        self.parent.marker_labels = marker_state.get("marker_labels", {})
        self.parent.sleep_period_regions = marker_state.get("sleep_period_regions", {})

    def _restore_algorithm_state(self, algorithm_state: dict[str, Any]) -> None:
        """Restore algorithm-related state."""
        if not algorithm_state:
            return

        self.parent.sadeh_results = algorithm_state.get("sadeh_results", [])
        self.parent._choi_nonwear_cache = algorithm_state.get("choi_nonwear_cache", {})
        self.parent.nonwear_regions = algorithm_state.get("nonwear_regions", [])
        self.parent.sleep_rule_arrows = algorithm_state.get("sleep_rule_arrows", {})

    def _restore_visual_state(self, visual_state: dict[str, Any]) -> None:
        """Restore visual-related state."""
        if not visual_state:
            return

        self.parent.activity_curve = visual_state.get("activity_curve")
        self.parent.sadeh_curve = visual_state.get("sadeh_curve")
        self.parent.choi_curve = visual_state.get("choi_curve")
        self.parent.custom_table_colors = visual_state.get("custom_table_colors")
        self.parent.adjacent_day_items = visual_state.get("adjacent_day_items", [])

    def _restore_interaction_state(self, interaction_state: dict[str, Any]) -> None:
        """Restore interaction-related state."""
        if not interaction_state:
            return

        self.parent.interaction_enabled = interaction_state.get("interaction_enabled", True)
        self.parent.marker_drag_in_progress = interaction_state.get("marker_drag_in_progress", False)
        self.parent.dragged_marker = interaction_state.get("dragged_marker")
        self.parent.is_dragging = interaction_state.get("is_dragging", False)

    def save_state(self) -> None:
        """Save the current state internally."""
        self.saved_state = self.capture_complete_state()
        logger.debug("Saved plot state internally")

    def restore_saved_state(self) -> None:
        """Restore the internally saved state."""
        if self.saved_state:
            self.restore_complete_state(self.saved_state)
            logger.debug("Restored saved plot state")
        else:
            logger.warning("No saved state to restore")

    def clear_saved_state(self) -> None:
        """Clear the internally saved state."""
        self.saved_state = None
        logger.debug("Cleared saved plot state")
