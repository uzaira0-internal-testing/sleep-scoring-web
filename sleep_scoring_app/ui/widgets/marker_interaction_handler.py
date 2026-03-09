#!/usr/bin/env python3
"""
Marker Interaction Handler for Activity Plot Widget.

Handles all marker interaction operations including:
- Marker click handling
- Marker drag handling
- Marker selection
- Validation during drag operations
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer

from sleep_scoring_app.core.constants import MarkerCategory, MarkerEndpoint, SleepMarkerEndpoint

if TYPE_CHECKING:
    import pyqtgraph as pg

    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget
    from sleep_scoring_app.ui.widgets.plot_marker_renderer import PlotMarkerRenderer

logger = logging.getLogger(__name__)


class MarkerInteractionHandler:
    """
    Handles marker interaction operations for the activity plot.

    Responsibilities:
    - Handle marker clicks
    - Handle marker dragging
    - Validate marker positions
    - Update marker selection state
    """

    def __init__(self, plot_widget: ActivityPlotWidget) -> None:
        """Initialize the marker interaction handler."""
        self.plot_widget = plot_widget
        logger.debug("MarkerInteractionHandler initialized")

    # ========== Sleep Marker Interaction ==========

    def on_marker_clicked(self, line: pg.InfiniteLine) -> None:
        """Handle marker click to select the marker set."""
        logger.debug(f"Marker clicked: {line}")

        # Only allow interaction with sleep markers when in SLEEP mode
        if self.plot_widget.get_active_marker_category() != MarkerCategory.SLEEP:
            logger.debug("Ignoring sleep marker click - not in SLEEP mode")
            return

        self.plot_widget._marker_click_in_progress = True
        QTimer.singleShot(50, lambda: setattr(self.plot_widget, "_marker_click_in_progress", False))

        if hasattr(line, "period") and line.period:
            renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer
            old_selection = renderer.selected_marker_set_index

            renderer.select_marker_set_by_period(line.period)

            # Deselect nonwear markers when sleep marker is selected
            self._deselect_nonwear_markers()

            # Always update sleep scoring rules when clicking a marker
            self._update_sleep_scoring_rules()

            if old_selection != renderer.selected_marker_set_index:
                renderer.update_marker_visual_state()
                self.plot_widget.mark_sleep_markers_dirty()  # Mark state as dirty via Redux
                self.plot_widget.setFocus()

    def on_marker_dragged(self, line: pg.InfiniteLine) -> None:
        """
        Handle marker drag in progress with real-time feedback.

        All updates are synchronous for immediate visual feedback.
        """
        # Only allow dragging sleep markers when in SLEEP mode
        if self.plot_widget.get_active_marker_category() != MarkerCategory.SLEEP:
            return

        self.plot_widget._marker_drag_in_progress = True
        new_pos = line.getPos()[0]

        # Find closest data index for snapping
        new_idx = self.plot_widget._find_closest_data_index(new_pos)
        if new_idx is None:
            return

        # Only proceed if index actually changed (throttle updates)
        last_idx = getattr(line, "_last_drag_idx", -1)
        if new_idx == last_idx:
            return

        line._last_drag_idx = new_idx
        snapped_ts = self.plot_widget.x_data[new_idx]

        if hasattr(line, "period") and line.period:
            renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer

            # Auto-select the marker set being dragged
            selected_period = renderer.get_selected_marker_period()
            if line.period is not selected_period:
                renderer.select_marker_set_by_period(line.period)

            # Update marker position during drag (swap logic is handled on drop only)
            if line.marker_type == SleepMarkerEndpoint.ONSET:
                line.period.onset_timestamp = snapped_ts
            elif line.marker_type == SleepMarkerEndpoint.OFFSET:
                line.period.offset_timestamp = snapped_ts

            # Update classifications
            renderer.daily_sleep_markers.update_classifications()

            # Lightweight label updates during drag
            renderer.update_marker_labels_text_only()

            # Update sleep scoring rule arrows immediately during drag
            if line.period.is_complete:
                self.plot_widget.apply_sleep_scoring_rules(line.period)

            # Sync dispatch to Redux - tables/time fields update immediately
            self.plot_widget.mark_sleep_markers_dirty()

    def on_marker_drag_finished(self, line: pg.InfiniteLine) -> None:
        """Handle marker drag completion with snapping and validation."""
        # Clear drag flag - expensive operations can now proceed
        self.plot_widget._marker_drag_in_progress = False

        # Only allow dragging sleep markers when in SLEEP mode
        if self.plot_widget.get_active_marker_category() != MarkerCategory.SLEEP:
            # Revert to original position
            if hasattr(line, "period") and line.period:
                original_pos = line.period.onset_timestamp if line.marker_type == SleepMarkerEndpoint.ONSET else line.period.offset_timestamp
                line.setPos(original_pos)
            logger.debug("Reverting sleep marker drag - not in SLEEP mode")
            return

        new_pos = line.getPos()[0]

        # Snap to nearest actual data epoch, not just the nearest minute
        new_idx = self.plot_widget._find_closest_data_index(new_pos)
        if new_idx is not None and new_idx < len(self.plot_widget.x_data):
            snapped_pos = self.plot_widget.x_data[new_idx]
        else:
            # Fallback to minute rounding if no data index found
            snapped_pos = round(new_pos / 60) * 60
        line.setPos(snapped_pos)

        # Update the period with new timestamp
        if hasattr(line, "period") and line.period:
            renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer

            # Store original values for potential revert (before modifying)
            original_onset = line.period.onset_timestamp
            original_offset = line.period.offset_timestamp

            if line.marker_type == SleepMarkerEndpoint.ONSET:
                line.period.onset_timestamp = snapped_pos
            elif line.marker_type == SleepMarkerEndpoint.OFFSET:
                line.period.offset_timestamp = snapped_pos

            # Validate period is still valid (onset before offset)
            if line.period.is_complete and line.period.onset_timestamp >= line.period.offset_timestamp:
                # Invalid order - revert to original timestamps
                line.period.onset_timestamp = original_onset
                line.period.offset_timestamp = original_offset
                line.setPos(original_onset if line.marker_type == SleepMarkerEndpoint.ONSET else original_offset)
                # Still dispatch dirty so tables sync with the reverted position
                self.plot_widget.mark_sleep_markers_dirty()
                return

            # Update classifications and check for duration ties
            renderer.daily_sleep_markers.update_classifications()
            if renderer.daily_sleep_markers.check_duration_tie():
                self.plot_widget.marker_limit_exceeded.emit("Warning: Multiple periods with identical duration detected")

            # Full redraw after drag completion
            renderer.redraw_markers()

            # Reapply sleep scoring rules if this is the selected period
            selected_period = renderer.get_selected_marker_period()
            if line.period is selected_period:
                self.plot_widget.apply_sleep_scoring_rules(line.period)

            # Emit signal to trigger all updates that were skipped during drag
            self.plot_widget.mark_sleep_markers_dirty()  # Mark state as dirty via Redux

    # ========== Nonwear Marker Interaction ==========

    def on_nonwear_marker_clicked(self, line: pg.InfiniteLine) -> None:
        """
        Handle nonwear marker click to select.

        Mirrors on_marker_clicked (sleep) exactly for symmetry.
        """
        logger.debug(f"Nonwear marker clicked: {line}")

        # Only allow interaction with nonwear markers when in NONWEAR mode
        if self.plot_widget.get_active_marker_category() != MarkerCategory.NONWEAR:
            logger.debug("Ignoring nonwear marker click - not in NONWEAR mode")
            return

        self.plot_widget._marker_click_in_progress = True
        QTimer.singleShot(50, lambda: setattr(self.plot_widget, "_marker_click_in_progress", False))

        if hasattr(line, "period") and line.period:
            renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer
            old_selection = renderer.selected_nonwear_marker_index

            renderer.select_nonwear_marker_by_period(line.period)

            # Deselect sleep markers when nonwear marker is selected (same as sleep)
            self._deselect_sleep_markers()

            if old_selection != renderer.selected_nonwear_marker_index:
                renderer.update_nonwear_marker_visual_state()
                self.plot_widget.mark_nonwear_markers_dirty()  # Mark state as dirty via Redux (same as sleep)
                self.plot_widget.setFocus()

    def on_nonwear_marker_dragged(self, line: pg.InfiniteLine) -> None:
        """
        Handle nonwear marker drag in progress with real-time feedback.

        Mirrors on_marker_dragged (sleep) exactly for symmetry.
        """
        # Only allow dragging nonwear markers when in NONWEAR mode
        if self.plot_widget.get_active_marker_category() != MarkerCategory.NONWEAR:
            return

        self.plot_widget._marker_drag_in_progress = True
        new_pos = line.getPos()[0]

        # Find closest data index for snapping (same as sleep)
        new_idx = self.plot_widget._find_closest_data_index(new_pos)
        if new_idx is None:
            return

        # Only proceed if index actually changed (throttle updates - same as sleep)
        last_idx = getattr(line, "_last_drag_idx", -1)
        if new_idx == last_idx:
            return

        line._last_drag_idx = new_idx
        snapped_ts = self.plot_widget.x_data[new_idx]

        if hasattr(line, "period") and line.period:
            renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer

            # Auto-select the marker being dragged (same as sleep)
            if line.period.marker_index != renderer.selected_nonwear_marker_index:
                renderer.select_nonwear_marker_by_period(line.period)
                # Also deselect sleep markers when dragging nonwear
                self._deselect_sleep_markers()

            # Check for crossing and swap if needed (same as sleep)
            if line.period.is_complete:
                if line.marker_type == MarkerEndpoint.START and snapped_ts >= line.period.end_timestamp:
                    # Start crossed end - swap them
                    old_end = line.period.end_timestamp
                    line.period.end_timestamp = snapped_ts
                    line.period.start_timestamp = old_end
                    line.marker_type = MarkerEndpoint.END
                    # Update the OTHER line (start) to the old end position
                    renderer.update_nonwear_marker_line_position(line.period, MarkerEndpoint.START, old_end)
                    logger.debug("Nonwear markers swapped: start crossed end")
                elif line.marker_type == MarkerEndpoint.END and snapped_ts <= line.period.start_timestamp:
                    # End crossed start - swap them
                    old_start = line.period.start_timestamp
                    line.period.start_timestamp = snapped_ts
                    line.period.end_timestamp = old_start
                    line.marker_type = MarkerEndpoint.START
                    # Update the OTHER line (end) to the old start position
                    renderer.update_nonwear_marker_line_position(line.period, MarkerEndpoint.END, old_start)
                    logger.debug("Nonwear markers swapped: end crossed start")
                # Normal update - no crossing
                elif line.marker_type == MarkerEndpoint.START:
                    line.period.start_timestamp = snapped_ts
                elif line.marker_type == MarkerEndpoint.END:
                    line.period.end_timestamp = snapped_ts
            # Period not complete, just update
            elif line.marker_type == MarkerEndpoint.START:
                line.period.start_timestamp = snapped_ts
            elif line.marker_type == MarkerEndpoint.END:
                line.period.end_timestamp = snapped_ts

            # Sync dispatch to Redux - tables update immediately (same as sleep)
            self.plot_widget.mark_nonwear_markers_dirty()

    def on_nonwear_marker_drag_finished(self, line: pg.InfiniteLine) -> None:
        """Handle nonwear marker drag completion with snapping and validation."""
        # Clear drag flag - expensive operations can now proceed
        self.plot_widget._marker_drag_in_progress = False

        # Only allow dragging nonwear markers when in NONWEAR mode
        if self.plot_widget.get_active_marker_category() != MarkerCategory.NONWEAR:
            # Revert to original position
            if hasattr(line, "period") and line.period:
                original_pos = line.period.start_timestamp if line.marker_type == MarkerEndpoint.START else line.period.end_timestamp
                line.setPos(original_pos)
            logger.debug("Reverting nonwear marker drag - not in NONWEAR mode")
            return

        new_pos = line.getPos()[0]

        # Snap to nearest actual data epoch, not just the nearest minute
        new_idx = self.plot_widget._find_closest_data_index(new_pos)
        if new_idx is not None and new_idx < len(self.plot_widget.x_data):
            snapped_pos = self.plot_widget.x_data[new_idx]
        else:
            # Fallback to minute rounding if no data index found
            snapped_pos = round(new_pos / 60) * 60
        line.setPos(snapped_pos)

        if hasattr(line, "period") and line.period:
            renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer

            # Store original values for potential revert
            original_start = line.period.start_timestamp
            original_end = line.period.end_timestamp

            if line.marker_type == MarkerEndpoint.START:
                line.period.start_timestamp = snapped_pos
            elif line.marker_type == MarkerEndpoint.END:
                line.period.end_timestamp = snapped_pos

            # Validate period (start before end)
            if line.period.is_complete and line.period.start_timestamp >= line.period.end_timestamp:
                # Invalid order - revert
                line.period.start_timestamp = original_start
                line.period.end_timestamp = original_end
                line.setPos(original_start if line.marker_type == MarkerEndpoint.START else original_end)
                return

            # Validate no overlap with other periods
            if line.period.is_complete and renderer.daily_nonwear_markers.check_overlap(
                line.period.start_timestamp,
                line.period.end_timestamp,
                exclude_slot=line.period.marker_index,
            ):
                # Overlap detected - revert and notify user
                line.period.start_timestamp = original_start
                line.period.end_timestamp = original_end
                line.setPos(original_start if line.marker_type == MarkerEndpoint.START else original_end)
                self.plot_widget.marker_limit_exceeded.emit("Nonwear periods cannot overlap")
                return

            # Full redraw after drag completion
            renderer.redraw_nonwear_markers()

            # Mark as unsaved via Redux store (same as sleep - mark_nonwear_markers_dirty handles everything)
            self.plot_widget.mark_nonwear_markers_dirty()

    # ========== Helper Methods ==========

    def _deselect_nonwear_markers(self) -> None:
        """
        Deselect all nonwear markers (make them all unselected visually).

        Mirrors _deselect_sleep_markers exactly for symmetry.
        """
        renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer
        # Set selected index to 0 (no selection) - this is a special value meaning none selected
        renderer.selected_nonwear_marker_index = 0
        # Use the no-auto-select version to prevent re-selection
        renderer._update_nonwear_marker_visual_state_no_auto_select()

    def _deselect_sleep_markers(self) -> None:
        """Deselect all sleep markers (make them all unselected visually)."""
        renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer
        # Set selected index to 0 (no selection) - this is a special value meaning none selected
        renderer.selected_marker_set_index = 0
        # Use the no-auto-select version to prevent re-selection
        renderer._update_marker_visual_state_no_auto_select()

    def _update_sleep_scoring_rules(self) -> None:
        """Update sleep scoring rules for the currently selected marker period."""
        renderer: PlotMarkerRenderer = self.plot_widget.marker_renderer
        selected_period = renderer.get_selected_marker_period()
        if selected_period and selected_period.is_complete:
            self.plot_widget.apply_sleep_scoring_rules(selected_period)
