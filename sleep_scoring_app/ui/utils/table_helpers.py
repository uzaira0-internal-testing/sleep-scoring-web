#!/usr/bin/env python3
"""
Table Helper Utilities
Shared table creation and management functions to eliminate code duplication.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import (
    TableColumn,
    TableDimensions,
    TooltipText,
)

if TYPE_CHECKING:
    from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


def _populate_table_for_viewport(table: QTableWidget) -> None:
    """
    Populate table with exactly as many rows as fit in viewport, centered on marker.

    OPTIMIZED: Reuses existing QTableWidgetItem objects instead of creating new ones.
    Only adds/removes rows when the count changes. Only updates colors when needed.

    No scrollbars - calculates visible rows from container height.
    """
    container = table.parent()
    if not container:
        return

    # Get stored data from container
    data = getattr(container, "_table_data", None)
    marker_row_in_data = getattr(container, "_marker_row", None)
    marker_bg_color = getattr(container, "_marker_bg_color", QColor(135, 206, 235))
    marker_fg_color = getattr(container, "_marker_fg_color", QColor(0, 0, 0))

    if data is None or len(data) == 0:
        if table.rowCount() > 0:
            table.setRowCount(0)
        return

    # Use our constant for row height (same as what we set with setRowHeight)
    row_height = TableDimensions.ROW_HEIGHT

    # Calculate available height from container
    container_height = container.height()
    header_height = table.horizontalHeader().height() if table.horizontalHeader() and table.horizontalHeader().isVisible() else 0
    # Account for margins, pop-out button above table, borders, and frame padding
    # Button height (~25px) + safety margin to prevent row bleeding
    overhead = TableDimensions.TABLE_MARGINS * 2 + 50
    available_height = container_height - header_height - overhead

    visible_row_count = max(1, available_height // row_height)

    # Ensure odd number of rows so marker is always centered
    if visible_row_count % 2 == 0:
        visible_row_count -= 1

    # Determine data slice centered on marker
    data_len = len(data)

    if marker_row_in_data is not None and data_len > 0:
        half_visible = visible_row_count // 2
        start_idx = max(0, marker_row_in_data - half_visible)

        # Adjust if we'd go past the end
        if start_idx + visible_row_count > data_len:
            start_idx = max(0, data_len - visible_row_count)
    else:
        start_idx = 0

    # Calculate actual rows to show
    rows_to_show = min(visible_row_count, data_len - start_idx)

    # Store start index for click handlers
    container._visible_start_idx = start_idx

    # Check if we can do an incremental update (same row count, items exist)
    current_row_count = table.rowCount()
    can_reuse_items = current_row_count == rows_to_show and current_row_count > 0 and table.item(0, 0) is not None

    # Precompute default colors once
    default_bg = QColor(255, 255, 255)
    default_fg = QColor(0, 0, 0)
    non_editable_flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled

    # Update table
    table.setUpdatesEnabled(False)
    try:
        # Only change row count if needed (expensive operation)
        if current_row_count != rows_to_show:
            table.setRowCount(rows_to_show)
            can_reuse_items = False  # Must create new items

        for table_row in range(rows_to_show):
            data_idx = start_idx + table_row
            row_data = data[data_idx]

            # Prepare cell values
            time_text = row_data.get("time", "--:--")
            axis_y_value = row_data.get("axis_y", row_data.get("activity", "--"))
            axis_y_text = str(axis_y_value) if axis_y_value != "--" else "--"
            vm_value = row_data.get("vm", "--")
            vm_text = str(vm_value) if vm_value != "--" else "--"
            sleep_value = row_data.get("sleep_score")
            sleep_text = "S" if sleep_value == 1 else ("W" if sleep_value == 0 else "--")
            choi_value = row_data.get("choi")
            choi_text = "Off" if choi_value == 1 else ("On" if choi_value == 0 else "--")
            nwt_value = row_data.get("nwt_sensor")
            nwt_text = "Off" if nwt_value == 1 else ("On" if nwt_value == 0 else "--")

            # Determine colors for this row
            is_marker_row = data_idx == marker_row_in_data
            bg_color = marker_bg_color if is_marker_row else default_bg
            fg_color = marker_fg_color if is_marker_row else default_fg

            texts = [time_text, axis_y_text, vm_text, sleep_text, choi_text, nwt_text]

            if can_reuse_items:
                # FAST PATH: Reuse existing items - just update text and colors
                for col, text in enumerate(texts):
                    item = table.item(table_row, col)
                    if item:
                        # Only update if changed
                        if item.text() != text:
                            item.setText(text)
                        # Only update colors if this row's marker status might have changed
                        item.setBackground(bg_color)
                        item.setForeground(fg_color)
                    else:
                        # Item missing, create it
                        item = QTableWidgetItem(text)
                        item.setBackground(bg_color)
                        item.setForeground(fg_color)
                        item.setFlags(non_editable_flags)
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        table.setItem(table_row, col, item)
            else:
                # SLOW PATH: Create new items (only when row count changes)
                for col, text in enumerate(texts):
                    item = QTableWidgetItem(text)
                    item.setBackground(bg_color)
                    item.setForeground(fg_color)
                    item.setFlags(non_editable_flags)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(table_row, col, item)

                # Set row height only when creating new rows
                table.setRowHeight(table_row, TableDimensions.ROW_HEIGHT)
    finally:
        table.setUpdatesEnabled(True)


def _populate_table_all_rows(
    table: QTableWidget,
    data: list[dict[str, Any]],
    marker_row: int | None,
    marker_bg_color: QColor,
    marker_fg_color: QColor,
) -> None:
    """Populate table with all data rows (for popout tables with scrollbars)."""
    if not data:
        table.setRowCount(0)
        return

    table.setUpdatesEnabled(False)
    try:
        table.setRowCount(len(data))

        for row_idx, row_data in enumerate(data):
            time_item = QTableWidgetItem(row_data.get("time", "--:--"))

            axis_y_value = row_data.get("axis_y", row_data.get("activity", "--"))
            axis_y_item = QTableWidgetItem(str(axis_y_value) if axis_y_value != "--" else "--")

            vm_value = row_data.get("vm", "--")
            vm_item = QTableWidgetItem(str(vm_value) if vm_value != "--" else "--")

            sleep_value = row_data.get("sleep_score")
            sleep_text = "S" if sleep_value == 1 else ("W" if sleep_value == 0 else "--")
            sadeh_item = QTableWidgetItem(sleep_text)

            choi_value = row_data.get("choi")
            choi_text = "Off" if choi_value == 1 else ("On" if choi_value == 0 else "--")
            choi_item = QTableWidgetItem(choi_text)

            nwt_value = row_data.get("nwt_sensor")
            nwt_text = "Off" if nwt_value == 1 else ("On" if nwt_value == 0 else "--")
            nwt_item = QTableWidgetItem(nwt_text)

            # Set colors
            if row_idx == marker_row:
                bg_color, fg_color = marker_bg_color, marker_fg_color
            else:
                bg_color, fg_color = QColor(255, 255, 255), QColor(0, 0, 0)

            for item in [time_item, axis_y_item, vm_item, sadeh_item, choi_item, nwt_item]:
                item.setBackground(bg_color)
                item.setForeground(fg_color)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            table.setItem(row_idx, 0, time_item)
            table.setItem(row_idx, 1, axis_y_item)
            table.setItem(row_idx, 2, vm_item)
            table.setItem(row_idx, 3, sadeh_item)
            table.setItem(row_idx, 4, choi_item)
            table.setItem(row_idx, 5, nwt_item)

        # Scroll to marker row
        if marker_row is not None:
            table.scrollTo(table.model().index(marker_row, 0), QTableWidget.ScrollHint.PositionAtCenter)
    finally:
        table.setUpdatesEnabled(True)


class _TableResizeFilter(QObject):
    """Event filter to repopulate table on resize."""

    def __init__(self, table: QTableWidget) -> None:
        super().__init__()
        self._table = table

    def eventFilter(self, obj: QObject | None, event: QEvent | None) -> bool:  # type: ignore[override]
        if event is not None and event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            container = self._table.parent()
            # Only do dynamic rows if enabled
            if container and getattr(container, "_dynamic_rows", True):
                _populate_table_for_viewport(self._table)
        return False


def create_marker_data_table(title: str, sleep_algorithm_name: str | None = None) -> QWidget:
    """
    Create a standardized data table widget for showing surrounding marker data.

    This consolidates the duplicate table creation logic from analysis_tab.py
    and main_window.py into a single shared function.

    Args:
        title: Title for the table (not displayed, but used for identification)
        sleep_algorithm_name: Display name of the sleep/wake algorithm (e.g., "Sadeh", "Cole-Kripke").
                              If None, defaults to "Sleep" as a generic column header.

    Returns:
        QWidget containing the configured table

    """
    container = QWidget()
    container.setMinimumWidth(TableDimensions.TABLE_MIN_WIDTH)
    # No max width - allow splitter to resize freely
    container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    layout = QVBoxLayout(container)
    layout.setContentsMargins(
        TableDimensions.TABLE_MARGINS, TableDimensions.TABLE_MARGINS, TableDimensions.TABLE_MARGINS, TableDimensions.TABLE_MARGINS
    )
    layout.setSpacing(TableDimensions.TABLE_SPACING)

    # Determine the sleep algorithm column header
    algorithm_column_name = sleep_algorithm_name if sleep_algorithm_name else TableColumn.SLEEP_SCORE

    # Table widget (pop-out button is now created separately in analysis_tab.py)
    table = QTableWidget()
    table.setColumnCount(6)  # Full functionality with Choi and NWT restored (2025-09-08)
    table.setHorizontalHeaderLabels(
        [
            TableColumn.TIME,
            TableColumn.AXIS_Y,
            TableColumn.VM,  # Vector Magnitude column
            algorithm_column_name,  # Dynamic sleep/wake algorithm column
            TableColumn.CHOI,  # Re-enabled (2025-09-08)
            TableColumn.NWT_SENSOR,  # Re-enabled (2025-09-08)
        ]
    )
    # Start with 0 rows - rows are created dynamically based on viewport size
    table.setRowCount(0)

    # Store the algorithm name for later reference
    container.sleep_algorithm_name = sleep_algorithm_name

    # Create tooltip for sleep algorithm column
    algorithm_tooltip = f"{algorithm_column_name} Algorithm: S=Sleep, W=Wake" if sleep_algorithm_name else TooltipText.SLEEP_SCORE_COLUMN

    # Center align all headers and add tooltips
    tooltips = [
        TooltipText.TIME_COLUMN,
        TooltipText.ACTIVITY_COLUMN,
        TooltipText.VM_COLUMN,
        algorithm_tooltip,  # Dynamic tooltip for sleep algorithm
        TooltipText.CHOI_COLUMN,
        TooltipText.NWT_SENSOR_COLUMN,
    ]

    for i, tooltip_text in enumerate(tooltips):
        header_item = table.horizontalHeaderItem(i)
        if header_item:
            header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            header_item.setToolTip(tooltip_text)

    # Configure table behavior
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # Enable focus for keyboard navigation
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)  # Enable multi-row selection
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # Select entire rows when clicked
    table.setAlternatingRowColors(True)
    table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    # Enable right-click context menu for marker movement
    table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    # Add hover and selection styling
    from sleep_scoring_app.core.constants import UIColors

    table.setStyleSheet(f"""
        QTableWidget::item:hover {{
            background-color: {UIColors.DIARY_SELECTION_DARKER};
            color: white;
        }}
        QTableWidget::item:selected {{
            background-color: {UIColors.DIARY_SELECTION_DARKER};
            color: white;
        }}
    """)

    # Configure headers
    horizontal_header = table.horizontalHeader()
    if horizontal_header:
        horizontal_header.setMaximumHeight(TableDimensions.TABLE_HEADER_HEIGHT)
        horizontal_header.setStretchLastSection(False)
        # Use dynamic column sizing
        horizontal_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Time
        horizontal_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Axis1
        horizontal_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # VM
        horizontal_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Sadeh
        horizontal_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Choi - Re-enabled (2025-09-08)
        horizontal_header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # NWT - Re-enabled (2025-09-08)

    vertical_header = table.verticalHeader()
    if vertical_header:
        vertical_header.setVisible(False)
        vertical_header.setDefaultSectionSize(TableDimensions.ROW_HEIGHT)

    # Set font
    font = table.font()
    font.setPointSize(TableDimensions.TABLE_FONT_SIZE)
    table.setFont(font)

    # Store reference to table widget for external access
    container.table_widget = table

    # Rows are created dynamically based on viewport size when data is loaded
    # Table starts with 0 rows

    # Add table to layout
    layout.addWidget(table)

    # Configure size policy - table fills available space
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    # Install resize event filter on container to recalculate visible rows
    resize_filter = _TableResizeFilter(table)
    container.installEventFilter(resize_filter)
    # Keep reference to prevent garbage collection
    container._resize_filter = resize_filter

    return container


def update_table_sleep_algorithm_header(table_container: QWidget, algorithm_name: str) -> None:
    """
    Update the sleep algorithm column header in a marker data table.

    This allows dynamically changing the algorithm display name when
    the user selects a different sleep/wake algorithm in study settings.

    Args:
        table_container: The QWidget container returned by create_marker_data_table
        algorithm_name: Display name of the sleep/wake algorithm (e.g., "Sadeh", "Cole-Kripke")

    """
    if not hasattr(table_container, "table_widget"):
        logger.warning("Table container does not have table_widget attribute")
        return

    table = table_container.table_widget
    if not isinstance(table, QTableWidget):
        logger.warning("table_widget is not a QTableWidget")
        return

    # Update the header label (column index 3 is the sleep algorithm column)
    sleep_column_index = 3
    header_item = table.horizontalHeaderItem(sleep_column_index)
    if header_item:
        header_item.setText(algorithm_name)
        header_item.setToolTip(f"{algorithm_name} Algorithm: S=Sleep, W=Wake")
    else:
        # Create new header item if it doesn't exist
        new_header = QTableWidgetItem(algorithm_name)
        new_header.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        new_header.setToolTip(f"{algorithm_name} Algorithm: S=Sleep, W=Wake")
        table.setHorizontalHeaderItem(sleep_column_index, new_header)

    # Store the algorithm name on the container for reference
    table_container.sleep_algorithm_name = algorithm_name

    logger.debug("Updated table sleep algorithm header to: %s", algorithm_name)


def update_marker_table(
    table_container: QWidget,
    data: list[dict[str, Any]],
    marker_bg_color: QColor,
    marker_fg_color: QColor,
    custom_table_colors: dict[str, str] | None = None,
    dynamic_rows: bool = True,
) -> None:
    """
    Update a marker data table with surrounding marker information.

    Args:
        table_container: Widget containing the table
        data: List of data rows with time, activity, sadeh, choi, nwt_sensor, is_marker
        marker_bg_color: Background color for marker row
        marker_fg_color: Foreground color for marker row
        custom_table_colors: Optional dict with custom colors for onset/offset highlights
        dynamic_rows: If True, limit rows to viewport height. If False, show all rows with scrolling.

    """
    table = getattr(table_container, "table_widget", None)
    if not table:
        logger.warning("Table widget not found in container")
        return

    # Find the marker row index in data
    marker_row = None
    for row_idx, row_data in enumerate(data):
        if row_data.get("is_marker"):
            marker_row = row_idx
            break

    # Store data, marker_row, and colors on container for dynamic resize/repopulation
    table_container._table_data = data
    table_container._marker_row = marker_row
    table_container._marker_bg_color = marker_bg_color
    table_container._marker_fg_color = marker_fg_color
    table_container._dynamic_rows = dynamic_rows

    if dynamic_rows:
        # Populate table with rows that fit in the viewport
        _populate_table_for_viewport(table)
    else:
        # Populate all rows (for popout tables with scrollbars)
        _populate_table_all_rows(table, data, marker_row, marker_bg_color, marker_fg_color)


def get_marker_surrounding_data(plot_widget: ActivityPlotWidget, marker_timestamp: float) -> list[dict[str, Any]]:
    """
    Get surrounding data (±10 minutes) for a marker timestamp using robust index finding.

    This moves the duplicate method from main_window.py to a shared location.

    Args:
        plot_widget: The activity plot widget containing data
        marker_timestamp: Timestamp of the marker

    Returns:
        List of data rows containing time, activity, sadeh, choi, nwt_sensor, is_marker

    """
    surrounding_data = []

    # Get data from plot widget
    if not plot_widget.timestamps:
        logger.debug("No timestamps available in plot widget")
        return surrounding_data

    # Use the plot widget's robust closest index finding method
    marker_idx = plot_widget._find_closest_data_index(marker_timestamp)

    if marker_idx is None:
        logger.debug(f"Could not find index for timestamp {marker_timestamp}")
        return surrounding_data

    # Load enough data to fill any reasonable viewport (±100 minutes = 200 rows max)
    elements_around_marker = 100

    logger.debug(f"Found marker index {marker_idx} for timestamp {marker_timestamp} - retrieving ±{elements_around_marker} data points")

    # Get various result arrays from plot widget
    # CRITICAL FIX: Use same data source prioritization as main_window.py
    sadeh_results = getattr(plot_widget, "main_48h_sadeh_results", getattr(plot_widget, "sadeh_results", []))

    # If no Sadeh results available, trigger algorithm calculation
    if not sadeh_results:
        try:
            logger.debug("No Sadeh results available, triggering algorithm calculation")
            plot_widget.plot_algorithms()
            # Re-check with same prioritization after algorithm run
            sadeh_results = getattr(plot_widget, "main_48h_sadeh_results", getattr(plot_widget, "sadeh_results", []))
        except Exception as e:
            logger.exception("Failed to run algorithms for table helper: %s", e)
    # PlotWidgetProtocol guarantees these methods exist
    choi_results = plot_widget.get_choi_results_per_minute()
    nonwear_sensor_results = plot_widget.get_nonwear_sensor_results_per_minute()

    # Get elements around marker
    start_idx = max(0, marker_idx - elements_around_marker)
    end_idx = min(len(plot_widget.timestamps), marker_idx + elements_around_marker + 1)

    for i in range(start_idx, end_idx):
        # Improved bounds checking with early continue for safety
        if i >= len(plot_widget.timestamps):
            logger.debug(f"Index {i} exceeds timestamps length {len(plot_widget.timestamps)}, skipping")
            continue

        # Check if axis_y_data exists and has valid index (PlotWidgetProtocol guarantees attribute exists)
        if not plot_widget.axis_y_data:
            logger.debug("No axis_y_data available in plot widget")
            continue

        if i >= len(plot_widget.axis_y_data):
            logger.debug(f"Index {i} exceeds axis_y_data length {len(plot_widget.axis_y_data)}, skipping")
            continue

        is_marker = i == marker_idx

        # Safe bounds-checked access for all arrays
        sadeh_value = sadeh_results[i] if sadeh_results and i < len(sadeh_results) else 0
        choi_value = choi_results[i] if choi_results and i < len(choi_results) else 0
        nwt_value = nonwear_sensor_results[i] if nonwear_sensor_results and i < len(nonwear_sensor_results) else 0

        # Ensure axis_y_data value is numeric before converting to int
        try:
            activity_value = int(plot_widget.axis_y_data[i])
        except (ValueError, TypeError):
            logger.warning(f"Invalid activity value at index {i}: {plot_widget.axis_y_data[i]}")
            activity_value = 0

        surrounding_data.append(
            {
                "time": plot_widget.timestamps[i].strftime("%H:%M"),
                "timestamp": plot_widget.timestamps[i].timestamp(),  # Add Unix timestamp for click handler
                "activity": activity_value,
                "sadeh": sadeh_value,
                "choi": choi_value,
                "nwt_sensor": nwt_value,
                "is_marker": is_marker,
            }
        )

    return surrounding_data
