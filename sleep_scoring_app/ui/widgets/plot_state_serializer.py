#!/usr/bin/env python3
"""
Plot State Serializer - Handles state capture and restoration for ActivityPlotWidget.

Extracted from ActivityPlotWidget to reduce god class size.
Manages complete UI state serialization for seamless data source switching.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.dataclasses import DailySleepMarkers, SleepPeriod

if TYPE_CHECKING:
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


class PlotStateSerializer:
    """Manages state capture and restoration for ActivityPlotWidget."""

    def __init__(self, parent: ActivityPlotWidget) -> None:
        """
        Initialize the state serializer with parent reference.

        Args:
            parent: The ActivityPlotWidget that owns this serializer

        """
        self.parent = parent

    def capture_complete_state(self) -> dict[str, Any]:
        """
        Capture complete UI state for seamless data source switching.

        Returns:
            Dictionary containing all state information needed for restoration

        """
        try:
            logger.debug("Capturing complete ActivityPlotWidget state")

            state = {
                "version": "1.0",
                "capture_timestamp": datetime.now().isoformat(),
            }

            # 1. VIEW STATE - PyQtGraph ViewBox state
            state["view_state"] = self._capture_view_state()

            # 2. DATA BOUNDARIES STATE
            state["data_boundaries"] = {
                "data_start_time": self.parent.data_start_time,
                "data_end_time": self.parent.data_end_time,
                "data_min_y": self.parent.data_min_y,
                "data_max_y": self.parent.data_max_y,
                "current_view_hours": self.parent.current_view_hours,
            }

            # 3. MARKER STATE
            state["marker_state"] = self._capture_marker_state()

            # 4. ALGORITHM STATE
            state["algorithm_state"] = self._capture_algorithm_state()

            # 5. NONWEAR STATE
            state["nonwear_state"] = self._capture_nonwear_state()

            # 6. VISUAL OVERLAY STATE
            state["overlay_state"] = self._capture_overlay_state()

            # 7. FILE AND UI STATE
            state["ui_state"] = self._capture_ui_state()

            # 8. MOUSE INTERACTION STATE
            state["mouse_state"] = {
                "has_mouse_timer": getattr(self.parent, "_mouse_move_timer", None) is not None,
                "has_last_mouse_pos": getattr(self.parent, "_last_mouse_pos", None) is not None,
            }

            logger.debug(f"Successfully captured state with {len(state)} top-level sections")
            return state

        except Exception as e:
            logger.exception(f"Failed to capture complete state: {e}")
            return {
                "version": "1.0",
                "error": str(e),
                "capture_timestamp": datetime.now().isoformat(),
                "partial_state": True,
            }

    def _capture_view_state(self) -> dict[str, Any]:
        """Capture PyQtGraph ViewBox state."""
        view_state = {}
        try:
            vb = getattr(self.parent, "vb", None)
            if vb is not None:
                current_range = vb.viewRange()
                view_state.update(
                    {
                        "x_range": list(current_range[0]),
                        "y_range": list(current_range[1]),
                        "auto_range_enabled": [vb.autoRangeEnabled()[0], vb.autoRangeEnabled()[1]],
                        "mouse_mode": vb.state["mouseMode"],
                        "aspect_locked": vb.state.get("aspectLocked", False),
                    }
                )
            else:
                view_state = {"not_initialized": True}
        except Exception as e:
            logger.warning(f"Failed to capture view state: {e}")
            view_state = {"error": str(e)}
        return view_state

    def _capture_marker_state(self) -> dict[str, Any]:
        """Capture sleep marker system state."""
        marker_state = {
            "daily_sleep_markers": {
                "period_1": self._serialize_sleep_period(self.parent.daily_sleep_markers.period_1),
                "period_2": self._serialize_sleep_period(self.parent.daily_sleep_markers.period_2),
                "period_3": self._serialize_sleep_period(self.parent.daily_sleep_markers.period_3),
                "period_4": self._serialize_sleep_period(self.parent.daily_sleep_markers.period_4),
            },
            "selected_marker_set_index": self.parent.selected_marker_set_index,
            "current_marker_being_placed": self._serialize_sleep_period(self.parent.current_marker_being_placed),
            "marker_click_in_progress": getattr(self.parent, "_marker_click_in_progress", False),
        }

        # Capture marker visual properties
        marker_visual_state = []
        for line in self.parent.marker_lines:
            try:
                marker_info = {
                    "timestamp": float(line.value()),
                    "marker_type": getattr(line, "marker_type", "unknown"),
                    "period": self._serialize_sleep_period(getattr(line, "period", None)),
                    "is_selected": getattr(line, "is_selected", False),
                    "pen_color": line.pen.color().name() if hasattr(line.pen, "color") else None,
                    "pen_width": line.pen.width() if hasattr(line.pen, "width") else None,
                    "label": line.label.toPlainText() if hasattr(line, "label") and line.label else None,
                    "is_draggable": line.movable,
                }
                marker_visual_state.append(marker_info)
            except Exception as e:
                logger.warning(f"Failed to capture marker visual state: {e}")

        marker_state["visual_markers"] = marker_visual_state
        return marker_state

    def _capture_algorithm_state(self) -> dict[str, Any]:
        """Capture algorithm cached results state."""
        sadeh_results = getattr(self.parent, "sadeh_results", None)
        algorithm_cache = getattr(self.parent, "_algorithm_cache", None)

        algorithm_state = {
            "has_sadeh_results": sadeh_results is not None,
            "sadeh_results_length": len(sadeh_results) if sadeh_results else 0,
            "has_algorithm_cache": algorithm_cache is not None,
            "cache_keys": list(algorithm_cache.keys()) if algorithm_cache else [],
        }

        if sadeh_results is not None:
            try:
                algorithm_state["sadeh_results"] = list(sadeh_results)
            except Exception as e:
                logger.warning(f"Failed to serialize Sadeh results: {e}")

        if algorithm_cache:
            try:
                cache_data = {}
                for key, value in algorithm_cache.items():
                    cache_entry = {}
                    if "sadeh" in value and value["sadeh"] is not None:
                        cache_entry["sadeh"] = list(value["sadeh"])
                    if "choi" in value and value["choi"] is not None:
                        cache_entry["choi"] = value["choi"]
                    cache_data[key] = cache_entry
                algorithm_state["algorithm_cache"] = cache_data
            except Exception as e:
                logger.warning(f"Failed to serialize algorithm cache: {e}")

        return algorithm_state

    def _capture_nonwear_state(self) -> dict[str, Any]:
        """Capture nonwear data state."""
        nonwear_data = getattr(self.parent, "nonwear_data", None)
        nonwear_regions = getattr(self.parent, "nonwear_regions", None)

        nonwear_state = {
            "has_nonwear_data": nonwear_data is not None,
            "has_nonwear_regions": nonwear_regions is not None and bool(nonwear_regions),
            "nonwear_regions_count": len(nonwear_regions) if nonwear_regions else 0,
        }

        if nonwear_data is not None:
            try:
                nonwear_state.update(
                    {
                        "nonwear_data_id": id(nonwear_data),
                        "choi_mask_length": len(nonwear_data.choi_mask),
                        "sensor_mask_length": len(nonwear_data.sensor_mask),
                        "data_source": str(nonwear_data.data_source),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to capture nonwear data info: {e}")

        return nonwear_state

    def _capture_overlay_state(self) -> dict[str, Any]:
        """Capture visual overlay state."""
        sleep_rule_markers = getattr(self.parent, "sleep_rule_markers", None)
        overlay_state = {
            "has_sleep_rule_markers": sleep_rule_markers is not None and bool(sleep_rule_markers),
            "sleep_rule_markers_count": len(sleep_rule_markers) if sleep_rule_markers else 0,
        }

        if sleep_rule_markers:
            rule_markers = []
            for marker in sleep_rule_markers:
                try:
                    marker_info = {
                        "item_type": type(marker).__name__,
                        "position": [marker.pos().x(), marker.pos().y()] if hasattr(marker, "pos") else None,
                        "text": marker.toPlainText() if hasattr(marker, "toPlainText") else None,
                    }
                    rule_markers.append(marker_info)
                except Exception as e:
                    logger.warning(f"Failed to capture sleep rule marker: {e}")
            overlay_state["sleep_rule_markers_details"] = rule_markers

        return overlay_state

    def _capture_ui_state(self) -> dict[str, Any]:
        """Capture file and UI state."""
        ui_state = {
            "current_filename": getattr(self.parent, "current_filename", None),
            "has_file_info_label": getattr(self.parent, "file_info_label", None) is not None,
        }

        try:
            plot_item = getattr(self.parent, "plotItem", None)
            ui_state["plot_menu_enabled"] = plot_item.menuEnabled() if plot_item is not None else False
        except (AttributeError, RuntimeError) as e:
            logger.debug("Could not get plot menu state: %s", e)
            ui_state["plot_menu_enabled"] = False

        try:
            vb = getattr(self.parent, "vb", None)
            ui_state["viewbox_menu_enabled"] = vb.menuEnabled() if vb else False
        except (AttributeError, RuntimeError) as e:
            logger.debug("Could not get viewbox menu state: %s", e)
            ui_state["viewbox_menu_enabled"] = False

        file_info_label = getattr(self.parent, "file_info_label", None)
        if file_info_label:
            try:
                ui_state.update(
                    {
                        "file_info_text": file_info_label.toPlainText(),
                        "file_info_position": [file_info_label.pos().x(), file_info_label.pos().y()],
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to capture file info label state: {e}")

        return ui_state

    def restore_complete_state(self, state_dict: dict[str, Any]) -> bool:
        """
        Restore complete UI state for seamless data source switching.

        Args:
            state_dict: State dictionary from capture_complete_state()

        Returns:
            True if restoration was successful, False otherwise

        """
        if not state_dict:
            logger.warning("Cannot restore from empty state dictionary")
            return False

        try:
            logger.debug("Restoring complete ActivityPlotWidget state")

            version = state_dict.get("version", "unknown")
            if version != "1.0":
                logger.warning(f"State version {version} may not be fully compatible")

            if state_dict.get("error"):
                logger.warning(f"Restoring from state that had capture errors: {state_dict['error']}")

            success_count = 0
            total_sections = 0

            # 1. RESTORE DATA BOUNDARIES
            if "data_boundaries" in state_dict:
                total_sections += 1
                if self._restore_data_boundaries(state_dict["data_boundaries"]):
                    success_count += 1

            # 2. RESTORE MARKER STATE
            if "marker_state" in state_dict:
                total_sections += 1
                if self._restore_marker_state(state_dict["marker_state"]):
                    success_count += 1

            # 3. RESTORE ALGORITHM STATE (clear, don't restore)
            if "algorithm_state" in state_dict:
                total_sections += 1
                if self._clear_algorithm_state():
                    success_count += 1

            # 4. RESTORE NONWEAR STATE
            if "nonwear_state" in state_dict:
                total_sections += 1
                if self._restore_nonwear_state():
                    success_count += 1

            # 5. RESTORE UI STATE
            if "ui_state" in state_dict:
                total_sections += 1
                if self._restore_ui_state(state_dict["ui_state"]):
                    success_count += 1

            # 6. RESTORE VIEW STATE (last)
            if "view_state" in state_dict and not state_dict["view_state"].get("error"):
                total_sections += 1
                if self._restore_view_state(state_dict["view_state"]):
                    success_count += 1

            success_rate = success_count / total_sections if total_sections > 0 else 0
            logger.debug(f"State restoration completed: {success_count}/{total_sections} sections ({success_rate:.1%})")

            return success_rate >= 0.75

        except Exception as e:
            logger.exception(f"Failed to restore complete state: {e}")
            return False

    def _restore_data_boundaries(self, boundaries: dict[str, Any]) -> bool:
        """Restore data boundaries."""
        try:
            self.parent.data_start_time = boundaries.get("data_start_time")
            self.parent.data_end_time = boundaries.get("data_end_time")
            self.parent.data_min_y = boundaries.get("data_min_y", 0)
            self.parent.data_max_y = boundaries.get("data_max_y", 100)
            self.parent.current_view_hours = boundaries.get("current_view_hours", 24)
            logger.debug("Restored data boundaries")
            return True
        except Exception as e:
            logger.warning(f"Failed to restore data boundaries: {e}")
            return False

    def _restore_marker_state(self, marker_state: dict[str, Any]) -> bool:
        """Restore marker state."""
        try:
            daily_markers = marker_state.get("daily_sleep_markers", {})
            self.parent.daily_sleep_markers = DailySleepMarkers(
                period_1=self._deserialize_sleep_period(daily_markers.get("period_1")),
                period_2=self._deserialize_sleep_period(daily_markers.get("period_2")),
                period_3=self._deserialize_sleep_period(daily_markers.get("period_3")),
                period_4=self._deserialize_sleep_period(daily_markers.get("period_4")),
            )

            self.parent.selected_marker_set_index = marker_state.get("selected_marker_set_index", 1)
            self.parent.current_marker_being_placed = self._deserialize_sleep_period(marker_state.get("current_marker_being_placed"))
            self.parent._marker_click_in_progress = marker_state.get("marker_click_in_progress", False)

            self.parent.redraw_markers()
            logger.debug("Restored marker state")
            return True
        except Exception as e:
            logger.warning(f"Failed to restore marker state: {e}")
            return False

    def _clear_algorithm_state(self) -> bool:
        """Clear algorithm state instead of restoring (prevents stale results)."""
        try:
            logger.debug("Skipping algorithm cache restoration to prevent stale results")

            # _algorithm_cache is always initialized in ActivityPlotWidget.__init__
            self.parent._algorithm_cache.clear()

            self.parent.main_48h_sadeh_results = None
            self.parent.main_48h_sadeh_timestamps = None  # CRITICAL: Clear alongside results

            # sadeh_results is always initialized in ActivityPlotWidget.__init__
            self.parent.sadeh_results = None

            logger.debug("Cleared algorithm state instead of restoring (cache invalidation fix)")
            return True
        except Exception as e:
            logger.warning(f"Failed to clear algorithm state: {e}")
            return False

    def _restore_nonwear_state(self) -> bool:
        """Restore nonwear state (clear visualizations)."""
        try:
            nonwear_regions = getattr(self.parent, "nonwear_regions", None)
            if nonwear_regions:
                self.parent.clear_nonwear_visualizations()

            logger.debug("Restored nonwear state (cleared visualizations)")
            return True
        except Exception as e:
            logger.warning(f"Failed to restore nonwear state: {e}")
            return False

    def _restore_ui_state(self, ui_state: dict[str, Any]) -> bool:
        """Restore UI state."""
        try:
            self.parent.current_filename = ui_state.get("current_filename")

            file_info_label = getattr(self.parent, "file_info_label", None)
            plot_item = getattr(self.parent, "plotItem", None)
            if file_info_label and plot_item is not None:
                try:
                    plot_item.removeItem(file_info_label)
                except (RuntimeError, ValueError) as e:
                    logger.debug("Could not remove file info label: %s", e)
                self.parent.file_info_label = None

            logger.debug("Restored UI state")
            return True
        except Exception as e:
            logger.warning(f"Failed to restore UI state: {e}")
            return False

    def _restore_view_state(self, view_state: dict[str, Any]) -> bool:
        """Restore view state."""
        try:
            if view_state.get("not_initialized"):
                logger.debug("View state was not initialized during capture, skipping restoration")
                return True

            vb = getattr(self.parent, "vb", None)
            if vb is not None:
                vb.blockSignals(True)

                try:
                    x_range = view_state.get("x_range")
                    y_range = view_state.get("y_range")

                    if x_range and y_range:
                        vb.setRange(xRange=x_range, yRange=y_range, padding=0)

                    auto_range = view_state.get("auto_range_enabled")
                    if auto_range:
                        vb.enableAutoRange(x=auto_range[0], y=auto_range[1])

                    mouse_mode = view_state.get("mouse_mode")
                    if mouse_mode is not None:
                        vb.setMouseMode(mouse_mode)

                finally:
                    vb.blockSignals(False)

            logger.debug("Restored view state")
            return True
        except Exception as e:
            logger.warning(f"Failed to restore view state: {e}")
            return False

    def _serialize_sleep_period(self, period: SleepPeriod | None) -> dict[str, Any] | None:
        """Serialize a SleepPeriod to a dictionary for state storage."""
        if period is None:
            return None

        try:
            return {
                "onset_timestamp": period.onset_timestamp,
                "offset_timestamp": period.offset_timestamp,
                "marker_index": period.marker_index,
                "marker_type": str(period.marker_type),
            }
        except Exception as e:
            logger.warning(f"Failed to serialize sleep period: {e}")
            return None

    def _deserialize_sleep_period(self, data: dict[str, Any] | None) -> SleepPeriod | None:
        """Deserialize a dictionary back to a SleepPeriod."""
        if not data:
            return None

        try:
            from sleep_scoring_app.core.constants import MarkerType

            return SleepPeriod(
                onset_timestamp=data.get("onset_timestamp"),
                offset_timestamp=data.get("offset_timestamp"),
                marker_index=data.get("marker_index", 1),
                marker_type=MarkerType(data.get("marker_type", MarkerType.MAIN_SLEEP)),
            )
        except Exception as e:
            logger.warning(f"Failed to deserialize sleep period: {e}")
            return None
