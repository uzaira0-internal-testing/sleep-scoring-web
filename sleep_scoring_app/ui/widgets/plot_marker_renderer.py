#!/usr/bin/env python3
"""
Plot Marker Renderer for Activity Plot Widget.

Manages all marker rendering operations for the activity plot including:
- Sleep marker creation and rendering
- Marker visual state management
- Marker drag handling
- Adjacent day marker display
- Marker selection and highlighting

This class now acts as a coordinator, delegating to:
- MarkerDrawingStrategy: Marker creation and rendering
- MarkerInteractionHandler: Marker interaction and dragging
"""

from __future__ import annotations

import logging
from functools import partial
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PyQt6.QtCore import Qt

from sleep_scoring_app.core.constants import MarkerEndpoint, MarkerPlacementState, SleepMarkerEndpoint, UIColors
from sleep_scoring_app.core.dataclasses import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    ManualNonwearPeriod,
    MarkerType,
    SleepPeriod,
)
from sleep_scoring_app.ui.widgets.marker_drawing_strategy import MarkerDrawingStrategy
from sleep_scoring_app.ui.widgets.marker_interaction_handler import MarkerInteractionHandler

if TYPE_CHECKING:
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


class PlotMarkerRenderer:
    """
    Manages marker rendering for the activity plot widget.

    Responsibilities:
    - Coordinate marker creation and rendering (delegates to MarkerDrawingStrategy)
    - Coordinate marker interactions (delegates to MarkerInteractionHandler)
    - Manage marker selection state
    - Update marker visual appearance
    - Display adjacent day markers
    """

    def __init__(self, parent: ActivityPlotWidget) -> None:
        """Initialize the plot marker renderer."""
        self.parent = parent

        # Initialize strategy components
        self.drawing_strategy = MarkerDrawingStrategy(parent)
        self.interaction_handler = MarkerInteractionHandler(parent)

        logger.info("PlotMarkerRenderer initialized")

    # ========== Marker State Access ==========

    @property
    def daily_sleep_markers(self) -> DailySleepMarkers:
        """Get daily sleep markers from parent."""
        return self.parent.daily_sleep_markers

    @daily_sleep_markers.setter
    def daily_sleep_markers(self, value: DailySleepMarkers) -> None:
        """Set daily sleep markers on parent."""
        self.parent.daily_sleep_markers = value

    @property
    def marker_lines(self) -> list:
        """Get marker lines from parent."""
        return self.parent.marker_lines

    @marker_lines.setter
    def marker_lines(self, value: list) -> None:
        """Set marker lines on parent."""
        self.parent.marker_lines = value

    @property
    def selected_marker_set_index(self) -> int:
        """Get selected marker set index from parent."""
        return self.parent.selected_marker_set_index

    @selected_marker_set_index.setter
    def selected_marker_set_index(self, value: int) -> None:
        """Set selected marker set index on parent."""
        self.parent.selected_marker_set_index = value

    # ========== Nonwear Marker State Access ==========

    @property
    def daily_nonwear_markers(self) -> DailyNonwearMarkers:
        """Get daily nonwear markers from parent."""
        return self.parent._daily_nonwear_markers

    @daily_nonwear_markers.setter
    def daily_nonwear_markers(self, value: DailyNonwearMarkers) -> None:
        """Set daily nonwear markers on parent."""
        self.parent._daily_nonwear_markers = value

    @property
    def nonwear_marker_lines(self) -> list:
        """Get nonwear marker lines from parent."""
        return self.parent._nonwear_marker_lines

    @nonwear_marker_lines.setter
    def nonwear_marker_lines(self, value: list) -> None:
        """Set nonwear marker lines on parent."""
        self.parent._nonwear_marker_lines = value

    @property
    def selected_nonwear_marker_index(self) -> int:
        """Get selected nonwear marker index from parent."""
        return self.parent._selected_nonwear_marker_index

    @selected_nonwear_marker_index.setter
    def selected_nonwear_marker_index(self, value: int) -> None:
        """
        Set selected nonwear marker index on parent.

        Uses property setter to emit nonwear_selection_changed signal for Redux.
        """
        self.parent.selected_nonwear_marker_index = value

    @property
    def nonwear_markers_visible(self) -> bool:
        """Get nonwear markers visibility from parent."""
        return self.parent._nonwear_markers_visible

    @nonwear_markers_visible.setter
    def nonwear_markers_visible(self, value: bool) -> None:
        """Set nonwear markers visibility on parent."""
        self.parent._nonwear_markers_visible = value

    # ========== Nap Numbering ==========

    def get_nap_number(self, period: SleepPeriod) -> int:
        """Get the sequential nap number for a given period."""
        naps = self.daily_sleep_markers.get_naps()
        # Sort naps by onset time to ensure consistent numbering
        sorted_naps = sorted(naps, key=lambda p: p.onset_timestamp or 0)
        for i, nap in enumerate(sorted_naps, 1):
            if nap is period:
                return i
        return 1  # Default to 1 if not found

    # ========== Marker Creation (delegated to MarkerDrawingStrategy) ==========

    def create_marker_line(
        self,
        timestamp: float,
        color: str,
        label: str,
        period: SleepPeriod | None,
        marker_type: str,
        is_selected: bool = False,
    ) -> pg.InfiniteLine:
        """Create a draggable marker line with proper styling and behavior."""
        line = self.drawing_strategy.create_marker_line_no_add(timestamp, color, label, period, marker_type, is_selected)

        # Connect drag events for complete markers
        if marker_type != MarkerPlacementState.INCOMPLETE:
            line.sigPositionChangeFinished.connect(partial(self._on_marker_drag_finished_wrapper, line))
            line.sigPositionChanged.connect(partial(self._on_marker_dragged_wrapper, line))
            line.sigClicked.connect(partial(self._on_marker_clicked_wrapper, line))

        # Add to plot
        if (plot_item := self.parent.plotItem) is not None:
            plot_item.addItem(line)
        return line

    def create_marker_line_no_add(
        self,
        timestamp: float,
        color: str,
        label: str,
        period: SleepPeriod | None,
        marker_type: str,
        is_selected: bool = False,
    ) -> pg.InfiniteLine:
        """Create a draggable marker line without adding to plot (for batch operations)."""
        line = self.drawing_strategy.create_marker_line_no_add(timestamp, color, label, period, marker_type, is_selected)

        # Connect drag events for complete markers
        if marker_type != MarkerPlacementState.INCOMPLETE:
            line.sigPositionChangeFinished.connect(partial(self._on_marker_drag_finished_wrapper, line))
            line.sigPositionChanged.connect(partial(self._on_marker_dragged_wrapper, line))
            line.sigClicked.connect(partial(self._on_marker_clicked_wrapper, line))

        return line

    # ========== Marker Drawing ==========

    def prepare_sleep_period_markers(self, period: SleepPeriod, is_main_sleep: bool) -> list[pg.InfiniteLine]:
        """Prepare onset and offset markers for a sleep period (optimized for batch operations)."""
        if not period.is_complete:
            return []

        # Check if this period is currently selected
        selected_period = self.get_selected_marker_period()
        is_selected = period is selected_period

        # Get colors based on selection state
        onset_color, offset_color = self._get_marker_colors(is_selected)

        # Create labels
        if is_main_sleep:
            onset_label = "Main Sleep Onset"
            offset_label = "Main Sleep Offset"
        else:
            nap_number = self.get_nap_number(period)
            onset_label = f"Nap {nap_number} Onset"
            offset_label = f"Nap {nap_number} Offset"

        # Create markers (but don't add to plot yet)
        # Type narrowing: is_complete guarantees these are not None
        onset_ts = period.onset_timestamp
        offset_ts = period.offset_timestamp
        if onset_ts is None or offset_ts is None:
            return []

        onset_line = self.create_marker_line_no_add(onset_ts, onset_color, onset_label, period, SleepMarkerEndpoint.ONSET, is_selected)
        offset_line = self.create_marker_line_no_add(offset_ts, offset_color, offset_label, period, SleepMarkerEndpoint.OFFSET, is_selected)

        return [onset_line, offset_line]

    def draw_sleep_period(self, period: SleepPeriod, is_main_sleep: bool) -> None:
        """Draw onset and offset markers for a sleep period."""
        if not period.is_complete:
            return

        # Check if this period is currently selected
        selected_period = self.get_selected_marker_period()
        is_selected = period is selected_period

        # Get colors based on selection state
        onset_color, offset_color = self._get_marker_colors(is_selected)

        # Create labels
        if is_main_sleep:
            onset_label = "Main Sleep Onset"
            offset_label = "Main Sleep Offset"
        else:
            nap_number = self.get_nap_number(period)
            onset_label = f"Nap {nap_number} Onset"
            offset_label = f"Nap {nap_number} Offset"

        # Type narrowing: is_complete guarantees these are not None
        onset_ts = period.onset_timestamp
        offset_ts = period.offset_timestamp
        if onset_ts is None or offset_ts is None:
            return

        # Draw onset marker
        onset_line = self.create_marker_line(onset_ts, onset_color, onset_label, period, SleepMarkerEndpoint.ONSET, is_selected)
        self.marker_lines.append(onset_line)

        # Draw offset marker
        offset_line = self.create_marker_line(offset_ts, offset_color, offset_label, period, SleepMarkerEndpoint.OFFSET, is_selected)
        self.marker_lines.append(offset_line)

    def draw_incomplete_marker(self, period: SleepPeriod) -> None:
        """Draw a temporary marker for an incomplete sleep period."""
        # Use the actual marker type from the period being placed
        if period.marker_type == MarkerType.MAIN_SLEEP:
            label = "Main Sleep Onset?"
        else:
            # For naps, count how many naps are already complete to determine which number this will be
            existing_naps = self.daily_sleep_markers.get_naps()
            complete_naps = [nap for nap in existing_naps if nap.is_complete]
            nap_number = len(complete_naps) + 1  # This will be the next nap
            label = f"Nap {nap_number} Onset?"

        onset_ts = period.onset_timestamp
        if onset_ts is None:
            return

        line = self.create_marker_line(
            onset_ts,
            UIColors.INCOMPLETE_MARKER,  # Gray color for incomplete
            label,
            None,
            MarkerPlacementState.INCOMPLETE,
        )
        self.marker_lines.append(line)

    def _get_marker_colors(self, is_selected: bool) -> tuple[str, str]:
        """Get onset and offset colors based on selection state."""
        custom_colors = getattr(self.parent, "custom_colors", {})
        if is_selected:
            onset_color = custom_colors.get("selected_onset", UIColors.SELECTED_MARKER_ONSET)
            offset_color = custom_colors.get("selected_offset", UIColors.SELECTED_MARKER_OFFSET)
        else:
            onset_color = custom_colors.get("unselected_onset", UIColors.UNSELECTED_MARKER_ONSET)
            offset_color = custom_colors.get("unselected_offset", UIColors.UNSELECTED_MARKER_OFFSET)
        return onset_color, offset_color

    # ========== Marker Redrawing ==========

    def redraw_markers(self) -> None:
        """Redraw all sleep markers with proper colors for main sleep vs naps (optimized)."""
        plot_item = self.parent.plotItem
        # Batch remove existing visual markers for better performance
        if self.marker_lines and plot_item is not None:
            for line in self.marker_lines:
                plot_item.removeItem(line)
            self.marker_lines.clear()

        # Get all complete periods
        complete_periods = self.daily_sleep_markers.get_complete_periods()
        if not complete_periods:
            # Show incomplete marker being placed
            current_marker = self.parent.current_marker_being_placed
            if current_marker and current_marker.onset_timestamp:
                self.draw_incomplete_marker(current_marker)
            return

        # Batch create markers for better performance
        main_sleep = self.daily_sleep_markers.get_main_sleep()
        markers_to_add = []

        # Prepare all markers first, then add them in batch
        for period in complete_periods:
            is_main_sleep = period is main_sleep
            period_markers = self.prepare_sleep_period_markers(period, is_main_sleep)
            markers_to_add.extend(period_markers)

        # Add all markers in batch
        if plot_item is not None:
            for marker in markers_to_add:
                plot_item.addItem(marker)
                self.marker_lines.append(marker)

        # Show incomplete marker being placed
        current_marker = self.parent.current_marker_being_placed
        if current_marker and current_marker.onset_timestamp:
            self.draw_incomplete_marker(current_marker)

        # Apply sleep scoring rules for selected marker period
        # BUT skip if we're being called from a context that will apply rules separately
        if not getattr(self.parent, "_skip_auto_apply_rules", False):
            selected_period = self.get_selected_marker_period()
            if selected_period and selected_period.is_complete:
                self.parent.apply_sleep_scoring_rules(selected_period)

        # Ensure visual state is properly updated
        self.update_marker_visual_state()

    def clear_sleep_markers(self) -> None:
        """Clear all sleep markers from the plot (visual only)."""
        if (plot_item := self.parent.plotItem) is not None:
            for line in self.marker_lines:
                plot_item.removeItem(line)
        self.marker_lines.clear()
        self.daily_sleep_markers = DailySleepMarkers()
        self.parent.current_marker_being_placed = None

    # ========== Marker Selection ==========

    def get_selected_marker_period(self) -> SleepPeriod | None:
        """Get the currently selected marker period."""
        if self.selected_marker_set_index == 1:
            return self.daily_sleep_markers.period_1
        if self.selected_marker_set_index == 2:
            return self.daily_sleep_markers.period_2
        if self.selected_marker_set_index == 3:
            return self.daily_sleep_markers.period_3
        if self.selected_marker_set_index == 4:
            return self.daily_sleep_markers.period_4
        return None

    def select_marker_set_by_period(self, period: SleepPeriod) -> None:
        """Select the marker set that contains the given period."""
        old_selection = self.selected_marker_set_index

        # Find which slot this period belongs to
        if period is self.daily_sleep_markers.period_1:
            self.selected_marker_set_index = 1
        elif period is self.daily_sleep_markers.period_2:
            self.selected_marker_set_index = 2
        elif period is self.daily_sleep_markers.period_3:
            self.selected_marker_set_index = 3
        elif period is self.daily_sleep_markers.period_4:
            self.selected_marker_set_index = 4
        else:
            logger.warning("Period not found in daily_sleep_markers - cannot select")
            return

        logger.debug(f"Auto-selected marker set changed from {old_selection} to {self.selected_marker_set_index}")

        # Only update UI if selection actually changed
        if old_selection != self.selected_marker_set_index:
            self.update_marker_visual_state()
            self.parent.mark_sleep_markers_dirty()  # Mark state as dirty via Redux

    def auto_select_marker_set(self) -> None:
        """Automatically select an appropriate marker set when the current one is cleared."""
        logger.debug("auto_select_marker_set called")

        # If the current selection is still valid, keep it
        current_period = self.get_selected_marker_period()
        if current_period is not None:
            logger.debug(f"Current period is valid (index={self.selected_marker_set_index}), keeping selection")
            return

        # Try to select the main sleep period first
        old_index = self.selected_marker_set_index
        main_sleep = self.daily_sleep_markers.get_main_sleep()
        if main_sleep:
            if main_sleep is self.daily_sleep_markers.period_1:
                self.selected_marker_set_index = 1
            elif main_sleep is self.daily_sleep_markers.period_2:
                self.selected_marker_set_index = 2
            elif main_sleep is self.daily_sleep_markers.period_3:
                self.selected_marker_set_index = 3
            elif main_sleep is self.daily_sleep_markers.period_4:
                self.selected_marker_set_index = 4
        # If no main sleep, select the first available period
        elif self.daily_sleep_markers.period_1:
            self.selected_marker_set_index = 1
        elif self.daily_sleep_markers.period_2:
            self.selected_marker_set_index = 2
        elif self.daily_sleep_markers.period_3:
            self.selected_marker_set_index = 3
        elif self.daily_sleep_markers.period_4:
            self.selected_marker_set_index = 4

        logger.debug(f"auto_select_marker_set: {old_index} -> {self.selected_marker_set_index}")
        logger.debug("NOTE: auto_select_marker_set does NOT emit sleep_markers_changed signal")

        # Update sleep scoring rules for the newly selected period
        self.parent._update_sleep_scoring_rules()

    # ========== Marker Visual State ==========

    def update_marker_visual_state(self) -> None:
        """Update the visual state of all markers to reflect current selection."""
        if not self.marker_lines:
            return

        # Get the currently selected period
        selected_period = self.get_selected_marker_period()

        # If no period is explicitly selected but we have markers, auto-select one
        if selected_period is None and self.daily_sleep_markers.get_complete_periods():
            self.auto_select_marker_set()
            selected_period = self.get_selected_marker_period()

        self._apply_marker_visual_state(selected_period)

    def _update_marker_visual_state_no_auto_select(self) -> None:
        """
        Update the visual state of all markers WITHOUT auto-selecting.

        Use this when intentionally deselecting all sleep markers (e.g., when
        switching to nonwear mode).
        """
        if not self.marker_lines:
            return

        # Get the currently selected period (may be None if index is 0)
        selected_period = self.get_selected_marker_period()
        self._apply_marker_visual_state(selected_period)

    def _apply_marker_visual_state(self, selected_period: SleepPeriod | None) -> None:
        """Apply visual state to all marker lines based on the selected period."""
        for line in self.marker_lines:
            if hasattr(line, "period") and line.period and hasattr(line, "marker_type"):
                is_selected = line.period is selected_period

                # Get colors based on selection state
                custom_colors = getattr(self.parent, "custom_colors", {})
                if is_selected:
                    if line.marker_type == SleepMarkerEndpoint.ONSET:
                        new_color = custom_colors.get("selected_onset", UIColors.SELECTED_MARKER_ONSET)
                    else:
                        new_color = custom_colors.get("selected_offset", UIColors.SELECTED_MARKER_OFFSET)
                elif line.marker_type == SleepMarkerEndpoint.ONSET:
                    new_color = custom_colors.get("unselected_onset", UIColors.UNSELECTED_MARKER_ONSET)
                else:
                    new_color = custom_colors.get("unselected_offset", UIColors.UNSELECTED_MARKER_OFFSET)

                # Update line width and color
                line_width = 5 if is_selected else 3
                line.setPen(pg.mkPen(new_color, width=line_width, style=pg.QtCore.Qt.PenStyle.SolidLine))

                # Update flag (label) colors to match
                if hasattr(line, "label") and line.label:
                    line.label.fill = pg.mkBrush(new_color)
                    line.label.border = pg.mkPen(new_color, width=2)
                    line.label.prepareGeometryChange()
                    line.label.update()

    def update_marker_labels_text_only(self) -> None:
        """Update labels for all marker lines based on current classifications (lightweight)."""
        main_sleep = self.daily_sleep_markers.get_main_sleep()

        for line in self.marker_lines:
            if hasattr(line, "period") and line.period and hasattr(line, "marker_type"):
                is_main_sleep = line.period is main_sleep

                # Update label text
                if is_main_sleep:
                    if line.marker_type == SleepMarkerEndpoint.ONSET:
                        new_label = "Main Sleep Onset"
                    else:
                        new_label = "Main Sleep Offset"
                else:
                    nap_number = self.get_nap_number(line.period)
                    if line.marker_type == SleepMarkerEndpoint.ONSET:
                        new_label = f"Nap {nap_number} Onset"
                    else:
                        new_label = f"Nap {nap_number} Offset"

                # Update label if changed
                if hasattr(line, "label") and line.label:
                    current_text = line.label.format if hasattr(line.label, "format") else ""
                    if current_text != new_label:
                        line.label.format = new_label
                        line.label.update()

    def update_marker_line_position(self, period: SleepPeriod, marker_type: str, new_position: float) -> None:
        """
        Update the position of a specific marker line during drag swap.

        Args:
            period: The SleepPeriod the line belongs to
            marker_type: "onset" or "offset"
            new_position: The new timestamp position for the line

        """
        for line in self.marker_lines:
            if hasattr(line, "period") and line.period is period and hasattr(line, "marker_type"):
                if line.marker_type == marker_type:
                    line.setPos(new_position)
                    return
        logger.warning(f"Could not find marker line for period with marker_type={marker_type}")

    # ========== Drag Event Handlers (delegated to MarkerInteractionHandler) ==========

    def _on_marker_drag_finished_wrapper(self, line: pg.InfiniteLine) -> None:
        """Wrapper to handle signal without lambda."""
        self.interaction_handler.on_marker_drag_finished(line)

    def _on_marker_dragged_wrapper(self, line: pg.InfiniteLine) -> None:
        """Wrapper to handle signal without lambda."""
        self.interaction_handler.on_marker_dragged(line)

    def _on_marker_clicked_wrapper(self, line: pg.InfiniteLine) -> None:
        """Wrapper to handle signal without lambda."""
        self.interaction_handler.on_marker_clicked(line)

    # ========== Adjacent Day Markers ==========

    def display_adjacent_day_markers(self, adjacent_day_markers_data: list) -> None:
        """Display adjacent day markers from adjacent days."""
        logger.info(f"ADJACENT DAY MARKERS: display_adjacent_day_markers called with {len(adjacent_day_markers_data)} markers")

        # Clear existing adjacent day markers first
        self.clear_adjacent_day_markers()

        # Initialize lists if not already present (defensive coding for external calls)
        if not self.parent.adjacent_day_marker_lines:
            self.parent.adjacent_day_marker_lines = []
        if not self.parent.adjacent_day_marker_labels:
            self.parent.adjacent_day_marker_labels = []

        plot_item = self.parent.plotItem
        if plot_item is None:
            return

        for i, marker_data in enumerate(adjacent_day_markers_data):
            logger.info(f"ADJACENT DAY MARKERS: Processing marker {i}: {marker_data}")

            onset_time = marker_data.get("onset_datetime")
            offset_time = marker_data.get("offset_datetime")
            adjacent_date = marker_data.get("adjacent_date", "")

            logger.info(f"ADJACENT DAY MARKERS: Marker {i} - onset: {onset_time}, offset: {offset_time}, date: {adjacent_date}")

            # Create adjacent day onset marker if exists
            if onset_time:
                onset_line = pg.InfiniteLine(
                    pos=onset_time,
                    angle=90,
                    pen=pg.mkPen(
                        color="#000000",
                        width=3,
                        style=Qt.PenStyle.DashLine,
                    ),
                    movable=False,
                )
                onset_line.setOpacity(0.4)
                plot_item.addItem(onset_line)
                self.parent.adjacent_day_marker_lines.append(onset_line)

                # Add date label for onset
                onset_label = pg.TextItem(
                    text=f"{adjacent_date} Onset",
                    color="#000000",
                    anchor=(0.5, 0),
                )
                if (view_box := plot_item.getViewBox()) is not None:
                    y_range = view_box.viewRange()[1]
                    onset_label.setPos(onset_time, y_range[1] * 0.9)
                plot_item.addItem(onset_label)
                self.parent.adjacent_day_marker_labels.append(onset_label)

            # Create adjacent day offset marker if exists
            if offset_time:
                offset_line = pg.InfiniteLine(
                    pos=offset_time,
                    angle=90,
                    pen=pg.mkPen(
                        color="#000000",
                        width=3,
                        style=Qt.PenStyle.DashLine,
                    ),
                    movable=False,
                )
                offset_line.setOpacity(0.4)
                plot_item.addItem(offset_line)
                self.parent.adjacent_day_marker_lines.append(offset_line)

                # Add date label for offset
                offset_label = pg.TextItem(
                    text=f"{adjacent_date} Offset",
                    color="#000000",
                    anchor=(0.5, 0),
                )
                if (view_box := plot_item.getViewBox()) is not None:
                    y_range = view_box.viewRange()[1]
                    offset_label.setPos(offset_time, y_range[1] * 0.85)
                plot_item.addItem(offset_label)
                self.parent.adjacent_day_marker_labels.append(offset_label)

    def clear_adjacent_day_markers(self) -> None:
        """Clear all adjacent day markers from the plot."""
        plot_item = self.parent.plotItem
        if plot_item is None:
            return

        if self.parent.adjacent_day_marker_lines:
            for line in self.parent.adjacent_day_marker_lines:
                plot_item.removeItem(line)
            self.parent.adjacent_day_marker_lines.clear()

        if self.parent.adjacent_day_marker_labels:
            for label in self.parent.adjacent_day_marker_labels:
                plot_item.removeItem(label)
            self.parent.adjacent_day_marker_labels.clear()

    # ========== Marker Loading ==========

    def load_daily_sleep_markers(self, daily_markers: DailySleepMarkers) -> None:
        """
        Load existing daily sleep markers into the plot widget.

        Expects a pre-filtered copy — callers must not pass Redux state directly.
        Bounds filtering is done upstream in the MarkersConnector.
        """
        logger.info("=== PlotMarkerRenderer.load_daily_sleep_markers START ===")
        logger.debug(f"daily_markers complete periods: {len(daily_markers.get_complete_periods()) if daily_markers else 0}")

        self.daily_sleep_markers = daily_markers
        self.parent.current_marker_being_placed = None

        self.redraw_markers()
        logger.debug("Called redraw_markers()")

        # Auto-select an appropriate marker set when loading
        logger.debug("Calling auto_select_marker_set()...")
        self.auto_select_marker_set()
        logger.debug(f"After auto_select_marker_set - markers_saved = {self.parent.markers_saved}")

        # Ensure visual state is properly updated
        self.update_marker_visual_state()

        # Extract view subset from main Sadeh results before applying rules
        if self.parent.main_48h_sadeh_results:
            self.parent._extract_view_subset_from_main_results()

        # Always update sleep scoring rules after loading markers
        self.parent._update_sleep_scoring_rules()
        logger.info(f"=== PlotMarkerRenderer.load_daily_sleep_markers END - markers_saved={self.parent.markers_saved} ===")

    def get_daily_sleep_markers(self) -> DailySleepMarkers:
        """Get the current daily sleep markers."""
        return self.daily_sleep_markers

    # ========== Marker Period Operations ==========

    def remove_sleep_period(self, period_index: int) -> bool:
        """Remove a sleep period by its index (1, 2, 3, or 4)."""
        try:
            if period_index == 1 and self.daily_sleep_markers.period_1:
                self.daily_sleep_markers.period_1 = None
            elif period_index == 2 and self.daily_sleep_markers.period_2:
                self.daily_sleep_markers.period_2 = None
            elif period_index == 3 and self.daily_sleep_markers.period_3:
                self.daily_sleep_markers.period_3 = None
            elif period_index == 4 and self.daily_sleep_markers.period_4:
                self.daily_sleep_markers.period_4 = None
            else:
                return False

            self.daily_sleep_markers.update_classifications()
            self.redraw_markers()
            self.parent.mark_sleep_markers_dirty()  # Mark state as dirty via Redux
            return True

        except Exception as e:
            logger.exception("Error removing sleep period %d: %s", period_index, e)
            self.parent.error_occurred.emit(f"Failed to remove sleep period {period_index}: {e}")
            return False

    def clear_selected_marker_set(self) -> None:
        """Clear the currently selected marker set."""
        logger.debug(f"Clearing selected marker set {self.selected_marker_set_index}")

        selected_period = self.get_selected_marker_period()
        plot_item = self.parent.plotItem

        if selected_period is None:
            logger.debug("No selected period to clear - trying to clear any existing markers")
            if self.marker_lines and plot_item is not None:
                logger.debug(f"Found {len(self.marker_lines)} marker lines to clear")
                for line in self.marker_lines:
                    plot_item.removeItem(line)
                self.marker_lines.clear()

                self.daily_sleep_markers = DailySleepMarkers()
                self.parent.mark_sleep_markers_dirty()  # Mark state as dirty via Redux
                self.parent.clear_sleep_onset_offset_markers()
            return

        # Remove visual markers for this period
        if plot_item is not None:
            lines_to_remove = [line for line in self.marker_lines if line.period == selected_period]
            for line in lines_to_remove:
                plot_item.removeItem(line)
        self.parent.marker_lines = [line for line in self.marker_lines if line.period != selected_period]

        # Clear the period from daily_sleep_markers
        if self.selected_marker_set_index == 1:
            self.daily_sleep_markers.period_1 = None
        elif self.selected_marker_set_index == 2:
            self.daily_sleep_markers.period_2 = None
        elif self.selected_marker_set_index == 3:
            self.daily_sleep_markers.period_3 = None
        elif self.selected_marker_set_index == 4:
            self.daily_sleep_markers.period_4 = None

        self.daily_sleep_markers.update_classifications()
        self.redraw_markers()
        self.parent.mark_sleep_markers_dirty()  # Mark state as dirty via Redux
        self.parent.clear_sleep_onset_offset_markers()
        self.auto_select_marker_set()
        self.update_marker_visual_state()

    def cancel_incomplete_marker(self) -> None:
        """Cancel the current incomplete marker placement and remove its visual indicator."""
        if self.parent.current_marker_being_placed is not None:
            logger.debug("Cancelling incomplete marker placement")
            self.parent.current_marker_being_placed = None
            self.redraw_markers()
            logger.debug("Incomplete marker cancelled")

    def adjust_selected_marker(self, marker_type: str, seconds_delta: int) -> None:
        """Adjust selected marker set by specified number of seconds."""
        selected_period = self.get_selected_marker_period()
        if not selected_period or not selected_period.is_complete:
            return

        # Use actual data bounds (not view bounds) for marker positioning
        if self.parent.x_data is None or len(self.parent.x_data) == 0:
            return
        data_start = float(self.parent.x_data[0])
        data_end = float(self.parent.x_data[-1])

        # Get current timestamp and narrow types
        onset_ts = selected_period.onset_timestamp
        offset_ts = selected_period.offset_timestamp
        if onset_ts is None or offset_ts is None:
            return

        if marker_type == SleepMarkerEndpoint.ONSET:
            current_timestamp = onset_ts
        elif marker_type == SleepMarkerEndpoint.OFFSET:
            current_timestamp = offset_ts
        else:
            return

        # Calculate new timestamp
        new_timestamp = current_timestamp + seconds_delta

        # Ensure timestamp is within data bounds
        if not (data_start <= new_timestamp <= data_end):
            return

        # Update the timestamp
        if marker_type == SleepMarkerEndpoint.ONSET:
            if new_timestamp < offset_ts:
                selected_period.onset_timestamp = new_timestamp
            else:
                return
        elif marker_type == SleepMarkerEndpoint.OFFSET:
            if new_timestamp > onset_ts:
                selected_period.offset_timestamp = new_timestamp
            else:
                return

        self.daily_sleep_markers.update_classifications()
        self.redraw_markers()
        self.parent.mark_sleep_markers_dirty()  # Mark state as dirty via Redux
        self.parent._update_sleep_scoring_rules()
        self.update_marker_visual_state()

    # =========================================================================
    # MANUAL NONWEAR MARKER METHODS
    # =========================================================================

    def create_nonwear_marker_line(
        self,
        timestamp: float,
        color: str,
        label: str,
        period: ManualNonwearPeriod | None,
        marker_type: str,
        is_selected: bool = False,
    ) -> pg.InfiniteLine:
        """Create a dashed marker line for manual nonwear periods."""
        line = self.drawing_strategy.create_nonwear_marker_line(timestamp, color, label, period, marker_type, is_selected)

        # Connect drag events for complete markers
        if marker_type != MarkerPlacementState.INCOMPLETE:
            line.sigPositionChangeFinished.connect(partial(self._on_nonwear_marker_drag_finished_wrapper, line))
            line.sigPositionChanged.connect(partial(self._on_nonwear_marker_dragged_wrapper, line))
            line.sigClicked.connect(partial(self._on_nonwear_marker_clicked_wrapper, line))

        return line

    def _get_nonwear_marker_colors(self, is_selected: bool) -> tuple[str, str]:
        """
        Get color for nonwear markers based on selection state.

        Returns same color for both start and end markers.
        """
        custom_colors = getattr(self.parent, "custom_colors", {})
        if is_selected:
            # Use single color for both start and end when selected
            color = custom_colors.get("selected_manual_nwt", UIColors.SELECTED_MANUAL_NWT_START)
        else:
            # Use single color for both start and end when unselected
            color = custom_colors.get("unselected_manual_nwt", UIColors.UNSELECTED_MANUAL_NWT_START)
        return color, color

    def draw_nonwear_period(self, period: ManualNonwearPeriod, is_selected: bool) -> None:
        """Draw start and end markers for a nonwear period."""
        if not period.is_complete:
            return

        # Type narrowing: is_complete guarantees these are not None
        start_ts = period.start_timestamp
        end_ts = period.end_timestamp
        if start_ts is None or end_ts is None:
            return

        start_color, end_color = self._get_nonwear_marker_colors(is_selected)

        # Create labels
        start_label = f"NW {period.marker_index} Start"
        end_label = f"NW {period.marker_index} End"

        # Draw start marker
        start_line = self.create_nonwear_marker_line(start_ts, start_color, start_label, period, MarkerEndpoint.START, is_selected)
        self.nonwear_marker_lines.append(start_line)

        # Draw end marker
        end_line = self.create_nonwear_marker_line(end_ts, end_color, end_label, period, MarkerEndpoint.END, is_selected)
        self.nonwear_marker_lines.append(end_line)

    def draw_incomplete_nonwear_marker(self, period: ManualNonwearPeriod) -> None:
        """Draw a temporary marker for an incomplete nonwear period."""
        start_ts = period.start_timestamp
        if start_ts is None:
            return

        label = f"NW {period.marker_index} Start?"

        line = self.create_nonwear_marker_line(
            start_ts,
            UIColors.INCOMPLETE_MANUAL_NWT,
            label,
            None,
            MarkerPlacementState.INCOMPLETE,
        )
        self.nonwear_marker_lines.append(line)

    def redraw_nonwear_markers(self) -> None:
        """Redraw all manual nonwear markers."""
        plot_item = self.parent.plotItem
        # Remove existing nonwear marker lines
        if plot_item is not None:
            for line in self.nonwear_marker_lines:
                plot_item.removeItem(line)
        self.nonwear_marker_lines.clear()

        # Don't draw if visibility is off
        if not self.nonwear_markers_visible:
            return

        # Get all complete periods
        complete_periods = self.daily_nonwear_markers.get_complete_periods()

        # Draw each complete period
        for period in complete_periods:
            is_selected = period.marker_index == self.selected_nonwear_marker_index
            self.draw_nonwear_period(period, is_selected)

        # Draw incomplete marker being placed
        current_nonwear_marker = getattr(self.parent, "_current_nonwear_marker_being_placed", None)
        if current_nonwear_marker and current_nonwear_marker.start_timestamp:
            self.draw_incomplete_nonwear_marker(current_nonwear_marker)

    def clear_nonwear_markers(self) -> None:
        """Clear all manual nonwear markers from the plot."""
        if (plot_item := self.parent.plotItem) is not None:
            for line in self.nonwear_marker_lines:
                plot_item.removeItem(line)
        self.nonwear_marker_lines.clear()
        self.daily_nonwear_markers = DailyNonwearMarkers()
        self.parent._current_nonwear_marker_being_placed = None

    def get_selected_nonwear_period(self) -> ManualNonwearPeriod | None:
        """Get the currently selected nonwear period."""
        return self.daily_nonwear_markers.get_period_by_slot(self.selected_nonwear_marker_index)

    def select_nonwear_marker_by_period(self, period: ManualNonwearPeriod) -> None:
        """Select the nonwear marker set that contains the given period."""
        old_selection = self.selected_nonwear_marker_index
        self.selected_nonwear_marker_index = period.marker_index

        if old_selection != self.selected_nonwear_marker_index:
            logger.debug(f"Nonwear marker selection changed from {old_selection} to {self.selected_nonwear_marker_index}")
            self.update_nonwear_marker_visual_state()

    def update_nonwear_marker_line_position(self, period: ManualNonwearPeriod, marker_type: str, new_position: float) -> None:
        """
        Update the position of a specific nonwear marker line during drag swap.

        Args:
            period: The ManualNonwearPeriod the line belongs to
            marker_type: "start" or "end"
            new_position: The new timestamp position for the line

        """
        for line in self.nonwear_marker_lines:
            if hasattr(line, "period") and line.period is period and hasattr(line, "marker_type"):
                if line.marker_type == marker_type:
                    line.setPos(new_position)
                    return
        logger.warning(f"Could not find nonwear marker line for period with marker_type={marker_type}")

    def update_nonwear_marker_visual_state(self) -> None:
        """Update the visual state of all nonwear markers to reflect current selection."""
        self._apply_nonwear_marker_visual_state()

    def _update_nonwear_marker_visual_state_no_auto_select(self) -> None:
        """
        Update the visual state of all nonwear markers WITHOUT auto-selecting.

        Use this when you explicitly want to deselect without triggering auto-selection.
        """
        self._apply_nonwear_marker_visual_state()

    def auto_select_nonwear_marker(self) -> None:
        """Automatically select the first available nonwear marker."""
        logger.debug("auto_select_nonwear_marker called")

        # If the current selection is still valid, keep it
        current_period = self.get_selected_nonwear_period()
        if current_period is not None:
            logger.debug(f"Current nonwear period is valid (index={self.selected_nonwear_marker_index}), keeping selection")
            return

        # Select the first available period
        old_index = self.selected_nonwear_marker_index
        for i in range(1, 11):  # Slots 1-10
            period = self.daily_nonwear_markers.get_period_by_slot(i)
            if period is not None:
                self.selected_nonwear_marker_index = i
                break

        logger.debug(f"auto_select_nonwear_marker: {old_index} -> {self.selected_nonwear_marker_index}")

        # Update visual state
        self._apply_nonwear_marker_visual_state()

    def _apply_nonwear_marker_visual_state(self) -> None:
        """Apply visual state to all nonwear marker lines based on current selection."""
        if not self.nonwear_marker_lines:
            return

        for line in self.nonwear_marker_lines:
            if hasattr(line, "period") and line.period and hasattr(line, "marker_type"):
                is_selected = line.period.marker_index == self.selected_nonwear_marker_index

                start_color, end_color = self._get_nonwear_marker_colors(is_selected)
                if line.marker_type == MarkerEndpoint.START:
                    new_color = start_color
                else:
                    new_color = end_color

                line_width = 4 if is_selected else 2
                line.setPen(pg.mkPen(new_color, width=line_width, style=Qt.PenStyle.DashLine))

                # Update label colors
                if hasattr(line, "label") and line.label:
                    line.label.fill = pg.mkBrush(new_color)
                    line.label.border = pg.mkPen(new_color, width=2)
                    line.label.prepareGeometryChange()
                    line.label.update()

    def set_nonwear_markers_visibility(self, visible: bool) -> None:
        """Set visibility of manual nonwear markers."""
        self.nonwear_markers_visible = visible
        self.redraw_nonwear_markers()

    # ========== Nonwear Marker Drag Handlers (delegated to MarkerInteractionHandler) ==========

    def _on_nonwear_marker_drag_finished_wrapper(self, line: pg.InfiniteLine) -> None:
        """Wrapper to handle signal without lambda."""
        self.interaction_handler.on_nonwear_marker_drag_finished(line)

    def _on_nonwear_marker_dragged_wrapper(self, line: pg.InfiniteLine) -> None:
        """Wrapper to handle signal without lambda."""
        self.interaction_handler.on_nonwear_marker_dragged(line)

    def _on_nonwear_marker_clicked_wrapper(self, line: pg.InfiniteLine) -> None:
        """Wrapper to handle signal without lambda."""
        self.interaction_handler.on_nonwear_marker_clicked(line)

    # ========== Nonwear Marker Period Operations ==========

    def clear_selected_nonwear_marker(self) -> None:
        """Clear the currently selected nonwear marker."""
        selected_period = self.get_selected_nonwear_period()
        if selected_period is None:
            return

        # Remove from data structure
        self.daily_nonwear_markers.remove_period_by_slot(self.selected_nonwear_marker_index)

        # Redraw
        self.redraw_nonwear_markers()

        # Mark as unsaved via Redux store
        self.parent.mark_nonwear_markers_dirty()

        # Auto-select next available
        self._auto_select_next_nonwear_marker()

    def _auto_select_next_nonwear_marker(self) -> None:
        """Automatically select the next available nonwear marker."""
        complete_periods = self.daily_nonwear_markers.get_complete_periods()
        if complete_periods:
            self.selected_nonwear_marker_index = complete_periods[0].marker_index
        else:
            self.selected_nonwear_marker_index = 0  # 0 = no selection

    def adjust_selected_nonwear_marker(self, marker_type: str, seconds_delta: int) -> None:
        """Adjust selected nonwear marker by specified number of seconds."""
        selected_period = self.get_selected_nonwear_period()
        if not selected_period or not selected_period.is_complete:
            return

        # Use actual data bounds (not view bounds) for marker positioning
        if self.parent.x_data is None or len(self.parent.x_data) == 0:
            return
        data_start = float(self.parent.x_data[0])
        data_end = float(self.parent.x_data[-1])

        # Type narrowing for timestamps
        start_ts = selected_period.start_timestamp
        end_ts = selected_period.end_timestamp
        if start_ts is None or end_ts is None:
            return

        # Get current timestamp
        if marker_type == MarkerEndpoint.START:
            current_timestamp = start_ts
        elif marker_type == MarkerEndpoint.END:
            current_timestamp = end_ts
        else:
            return

        # Calculate new timestamp
        new_timestamp = current_timestamp + seconds_delta

        # Ensure timestamp is within data bounds
        if not (data_start <= new_timestamp <= data_end):
            return

        # CRITICAL FIX #2: Store original values for potential revert on overlap detection
        original_start = start_ts
        original_end = end_ts

        # Update the timestamp
        if marker_type == MarkerEndpoint.START:
            if new_timestamp < end_ts:
                selected_period.start_timestamp = new_timestamp
            else:
                return
        elif marker_type == MarkerEndpoint.END:
            if new_timestamp > start_ts:
                selected_period.end_timestamp = new_timestamp
            else:
                return

        # Get updated timestamps for overlap check (handle None case)
        check_start = selected_period.start_timestamp
        check_end = selected_period.end_timestamp
        if check_start is None or check_end is None:
            return

        # CRITICAL FIX #2: Validate no overlap with other periods
        if self.daily_nonwear_markers.check_overlap(
            check_start,
            check_end,
            exclude_slot=selected_period.marker_index,
        ):
            # Overlap detected - revert and notify user
            selected_period.start_timestamp = original_start
            selected_period.end_timestamp = original_end
            self.parent.marker_limit_exceeded.emit("Nonwear periods cannot overlap")
            return

        self.redraw_nonwear_markers()

        # Mark as unsaved via Redux store
        self.parent.mark_nonwear_markers_dirty()

    def load_daily_nonwear_markers(self, daily_markers: DailyNonwearMarkers) -> None:
        """
        Load existing daily nonwear markers into the plot widget.

        Expects a pre-filtered copy — callers must not pass Redux state directly.
        Bounds filtering is done upstream in the MarkersConnector.
        """
        self.daily_nonwear_markers = daily_markers
        self.parent._current_nonwear_marker_being_placed = None
        self.redraw_nonwear_markers()

        # Auto-select first available
        self._auto_select_next_nonwear_marker()
        self.update_nonwear_marker_visual_state()

    def get_daily_nonwear_markers(self) -> DailyNonwearMarkers:
        """Get the current daily nonwear markers."""
        return self.daily_nonwear_markers

    def cancel_incomplete_nonwear_marker(self) -> None:
        """Cancel the current incomplete nonwear marker placement."""
        if self.parent._current_nonwear_marker_being_placed is not None:
            logger.debug("Cancelling incomplete nonwear marker placement")
            self.parent._current_nonwear_marker_being_placed = None
            self.redraw_nonwear_markers()
