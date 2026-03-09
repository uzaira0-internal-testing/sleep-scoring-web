#!/usr/bin/env python3
"""
Marker Drawing Strategy for Activity Plot Widget.

Handles all marker drawing operations including:
- Sleep marker creation and rendering
- Nonwear marker creation and rendering
- Marker positioning and visual updates
- Marker removal from plot
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PyQt6.QtCore import Qt

from sleep_scoring_app.core.constants import MarkerCategory, MarkerPlacementState, UIColors

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import ManualNonwearPeriod, SleepPeriod
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


class MarkerDrawingStrategy:
    """
    Handles marker drawing operations for the activity plot.

    Responsibilities:
    - Create sleep markers (onset/offset lines)
    - Create nonwear markers (start/end lines)
    - Update marker positions
    - Remove markers from plot
    - Apply visual styling
    """

    def __init__(self, plot_widget: ActivityPlotWidget) -> None:
        """Initialize the marker drawing strategy."""
        self.plot_widget = plot_widget
        logger.debug("MarkerDrawingStrategy initialized")

    # ========== Sleep Marker Creation ==========

    def create_marker_line(
        self,
        timestamp: float,
        color: str,
        label: str,
        period: SleepPeriod | None,
        marker_type: str,
        is_selected: bool = False,
    ) -> pg.InfiniteLine:
        """Create a draggable marker line and add it to the plot."""
        line = self._create_marker_line_internal(timestamp, color, label, period, marker_type, is_selected)
        self.plot_widget.plotItem.addItem(line)
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
        return self._create_marker_line_internal(timestamp, color, label, period, marker_type, is_selected)

    def _create_marker_line_internal(
        self,
        timestamp: float,
        color: str,
        label: str,
        period: SleepPeriod | None,
        marker_type: str,
        is_selected: bool = False,
    ) -> pg.InfiniteLine:
        """Internal method to create marker line."""
        # Use thicker line for selected markers
        line_width = 5 if is_selected else 3

        # Use actual data bounds so markers can't be dragged into empty view edges
        data_bounds = self.plot_widget.actual_data_bounds
        drag_bounds = list(data_bounds) if data_bounds else [self.plot_widget.data_start_time, self.plot_widget.data_end_time]

        line = pg.InfiniteLine(
            pos=timestamp,
            angle=90,  # Vertical line
            pen=pg.mkPen(color, width=line_width, style=pg.QtCore.Qt.PenStyle.SolidLine),
            movable=(marker_type != MarkerPlacementState.INCOMPLETE),  # Incomplete markers not draggable
            bounds=drag_bounds,
            label=label,
            labelOpts={
                "position": 0.5,
                "color": (255, 255, 255),
                "fill": pg.mkBrush(color),
                "border": pg.mkPen(color, width=2),
                "rotateAxis": (1, 0),  # Rotate text to be vertical
            },
        )

        # Set hover color to gray for colorblind accessibility
        line.setHoverPen(pg.mkPen(UIColors.HOVERED_MARKER, width=line_width + 1, style=pg.QtCore.Qt.PenStyle.SolidLine))

        # Store period and marker type on line for drag handling
        if marker_type != MarkerPlacementState.INCOMPLETE:
            line.period = period
            line.marker_type = marker_type

        return line

    # ========== Nonwear Marker Creation ==========

    def create_nonwear_marker_line(
        self,
        timestamp: float,
        color: str,
        label: str,
        period: ManualNonwearPeriod | None,
        marker_type: str,
        is_selected: bool = False,
    ) -> pg.InfiniteLine:
        """Create a dashed marker line for manual nonwear periods and add it to the plot."""
        line = self._create_nonwear_marker_line_internal(timestamp, color, label, period, marker_type, is_selected)
        self.plot_widget.plotItem.addItem(line)
        return line

    def _create_nonwear_marker_line_internal(
        self,
        timestamp: float,
        color: str,
        label: str,
        period: ManualNonwearPeriod | None,
        marker_type: str,
        is_selected: bool = False,
    ) -> pg.InfiniteLine:
        """Internal method to create nonwear marker line with dashed style."""
        # Use thicker line for selected markers
        line_width = 4 if is_selected else 2

        # Use actual data bounds so markers can't be dragged into empty view edges
        data_bounds = self.plot_widget.actual_data_bounds
        drag_bounds = list(data_bounds) if data_bounds else [self.plot_widget.data_start_time, self.plot_widget.data_end_time]

        # Create dashed line to distinguish from sleep markers
        line = pg.InfiniteLine(
            pos=timestamp,
            angle=90,  # Vertical line
            pen=pg.mkPen(color, width=line_width, style=Qt.PenStyle.DashLine),
            movable=(marker_type != MarkerPlacementState.INCOMPLETE),
            bounds=drag_bounds,
            label=label,
            labelOpts={
                "position": 0.3,  # Position label lower to avoid overlap with sleep markers
                "color": (255, 255, 255),
                "fill": pg.mkBrush(color),
                "border": pg.mkPen(color, width=2),
                "rotateAxis": (1, 0),
            },
        )

        # Set hover color
        line.setHoverPen(pg.mkPen(UIColors.HOVERED_MARKER, width=line_width + 1, style=Qt.PenStyle.DashLine))

        # Store period and marker type on line for drag handling
        if marker_type != MarkerPlacementState.INCOMPLETE:
            line.period = period
            line.marker_type = marker_type
            line.marker_category = MarkerCategory.NONWEAR

        return line

    # ========== Marker Removal ==========

    def remove_marker(self, marker: pg.InfiniteLine) -> None:
        """Remove a marker from the plot."""
        self.plot_widget.plotItem.removeItem(marker)

    def remove_all_markers(self, marker_list: list[pg.InfiniteLine]) -> None:
        """Remove all markers from a list."""
        for marker in marker_list:
            self.remove_marker(marker)

    # ========== Marker Visual Updates ==========

    def update_marker_pen(self, marker: pg.InfiniteLine, color: str, width: int, is_dashed: bool = False) -> None:
        """Update the pen style of a marker."""
        style = Qt.PenStyle.DashLine if is_dashed else pg.QtCore.Qt.PenStyle.SolidLine
        marker.setPen(pg.mkPen(color, width=width, style=style))

    def update_marker_label(self, marker: pg.InfiniteLine, color: str) -> None:
        """Update the label colors of a marker."""
        if hasattr(marker, "label") and marker.label:
            marker.label.fill = pg.mkBrush(color)
            marker.label.border = pg.mkPen(color, width=2)
            marker.label.prepareGeometryChange()
            marker.label.update()

    def update_marker_label_text(self, marker: pg.InfiniteLine, new_text: str) -> None:
        """Update the label text of a marker."""
        if hasattr(marker, "label") and marker.label:
            current_text = marker.label.format if hasattr(marker.label, "format") else ""
            if current_text != new_text:
                marker.label.format = new_text
                marker.label.update()

    def update_marker_position(self, marker: pg.InfiniteLine, new_pos: float) -> None:
        """Update the position of a marker."""
        marker.setPos(new_pos)
