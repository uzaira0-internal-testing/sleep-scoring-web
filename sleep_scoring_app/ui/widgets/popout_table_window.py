"""Pop-out table window for viewing marker data in a larger, resizable window with multi-select."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHeaderView,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import TableColumn, TableDimensions, TooltipText, UIColors

if TYPE_CHECKING:
    from PyQt6.QtGui import QCloseEvent


class PopOutTableWindow(QDialog):
    """Resizable pop-out window for marker data tables with multi-row selection."""

    def __init__(self, parent: QWidget | None, title: str, table_type: str) -> None:
        """
        Initialize pop-out table window.

        Args:
            parent: Parent widget
            title: Window title
            table_type: Type of table ("onset" or "offset")

        """
        super().__init__(parent)
        self.table_type = table_type
        self._table_data = []  # Store full table data for click handling

        # Window configuration
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(False)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Create table widget
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(
            [
                TableColumn.TIME,
                TableColumn.AXIS_Y,
                TableColumn.VM,
                TableColumn.SLEEP_SCORE,
                TableColumn.CHOI,
                TableColumn.NWT_SENSOR,
            ]
        )
        # Pop-out tables show full 48-hour period (2880 minutes) instead of limited view
        self.table.setRowCount(2880)

        # Configure tooltips
        tooltips = [
            TooltipText.TIME_COLUMN,
            TooltipText.ACTIVITY_COLUMN,
            TooltipText.VM_COLUMN,
            TooltipText.SLEEP_SCORE_COLUMN,
            TooltipText.CHOI_COLUMN,
            TooltipText.NWT_SENSOR_COLUMN,
        ]
        for i, tooltip_text in enumerate(tooltips):
            header_item = self.table.horizontalHeaderItem(i)
            if header_item:
                header_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                header_item.setToolTip(tooltip_text)

        # Enable multi-row selection with drag
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # Enable right-click context menu for marker movement
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Enable vertical scroll bar only (columns stretch to fill width)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Styling
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(f"""
            QTableWidget::item:selected {{
                background-color: {UIColors.DIARY_SELECTION_DARKER};
                color: white;
            }}
            QTableWidget::item:hover {{
                background-color: {UIColors.DIARY_SELECTION_DARKER};
                color: white;
            }}
        """)

        # Configure headers
        horizontal_header = self.table.horizontalHeader()
        if horizontal_header:
            horizontal_header.setStretchLastSection(True)
            for i in range(6):
                horizontal_header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)

        vertical_header = self.table.verticalHeader()
        if vertical_header:
            vertical_header.setVisible(True)
            vertical_header.setDefaultSectionSize(TableDimensions.ROW_HEIGHT)

        layout.addWidget(self.table)

        # Restore window size and position
        self._restore_geometry()

    def update_table_data(self, data: list[dict]) -> None:
        """
        Update table with new data.

        Args:
            data: List of dictionaries with keys: time, activity, sadeh, choi, nwt_sensor, is_marker

        """
        from PyQt6.QtGui import QColor

        from sleep_scoring_app.core.constants import TableDimensions
        from sleep_scoring_app.ui.utils.table_helpers import update_marker_table

        # Store the data for click handling
        self._table_data = data

        # Use same update function as embedded tables
        onset_bg = QColor(TableDimensions.ONSET_MARKER_BACKGROUND)
        onset_fg = QColor(TableDimensions.ONSET_MARKER_FOREGROUND)
        offset_bg = QColor(TableDimensions.OFFSET_MARKER_BACKGROUND)
        offset_fg = QColor(TableDimensions.OFFSET_MARKER_FOREGROUND)

        bg_color = onset_bg if self.table_type == "onset" else offset_bg
        fg_color = onset_fg if self.table_type == "onset" else offset_fg

        # Create a wrapper widget-like object with table_widget attribute
        class TableWrapper:
            def __init__(self, table) -> None:
                self.table_widget = table

        wrapper = TableWrapper(self.table)
        # Popout tables show all rows with scrollbars, not dynamic row limiting
        update_marker_table(wrapper, data, bg_color, fg_color, {}, dynamic_rows=False)

    def get_timestamp_for_row(self, row: int) -> float | None:
        """Get the Unix timestamp for a given table row."""
        if 0 <= row < len(self._table_data):
            return self._table_data[row].get("timestamp")
        return None

    def scroll_to_row(self, row: int) -> None:
        """Scroll the table to center on a specific row."""
        if 0 <= row < self.table.rowCount():
            # Scroll to the row, positioning it in the center of the viewport
            self.table.scrollToItem(self.table.item(row, 0), hint=self.table.ScrollHint.PositionAtCenter)

    def closeEvent(self, event: QCloseEvent) -> None:  # type: ignore[override]
        """Save window geometry before closing."""
        self._save_geometry()
        super().closeEvent(event)

    def _save_geometry(self) -> None:
        """Save window size and position."""
        settings = QSettings("SleepResearch", "SleepScoringApp")
        settings.setValue(f"popout/{self.table_type}_geometry", self.saveGeometry())
        settings.setValue(f"popout/{self.table_type}_pos", self.pos())

    def _restore_geometry(self) -> None:
        """Restore window size and position."""
        settings = QSettings("SleepResearch", "SleepScoringApp")

        # Restore geometry if available
        geometry = settings.value(f"popout/{self.table_type}_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # Default size
            self.resize(600, 500)

        # Restore position if available
        pos = settings.value(f"popout/{self.table_type}_pos")
        if pos:
            self.move(pos)

        # Safety check: ensure window is visible on at least one screen
        self._ensure_on_screen()

    def _ensure_on_screen(self) -> None:
        """Ensure the window is visible on at least one screen."""
        from PyQt6.QtWidgets import QApplication

        # Get all available screens
        screens = QApplication.screens()
        if not screens:
            return

        # Get window geometry
        window_rect = self.frameGeometry()

        # Check if window intersects with any screen
        on_screen = False
        for screen in screens:
            if screen.availableGeometry().intersects(window_rect):
                on_screen = True
                break

        # If not on any screen, move to primary screen center
        if not on_screen:
            primary_screen = QApplication.primaryScreen()
            if primary_screen:
                screen_geometry = primary_screen.availableGeometry()
                x = screen_geometry.x() + (screen_geometry.width() - self.width()) // 2
                y = screen_geometry.y() + (screen_geometry.height() - self.height()) // 2
                self.move(x, y)
