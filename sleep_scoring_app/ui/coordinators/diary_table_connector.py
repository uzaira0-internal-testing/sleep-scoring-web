#!/usr/bin/env python3
"""
Diary Table Connector
Manages diary table display and interaction.
"""

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidgetItem

from sleep_scoring_app.core.constants import DiaryTableColumn

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from sleep_scoring_app.services.protocols import UnifiedDataProtocol
    from sleep_scoring_app.ui.coordinators.diary_integration_coordinator import DiaryIntegrationCoordinator
    from sleep_scoring_app.ui.store import UIStore

logger = logging.getLogger(__name__)


class DiaryTableConnector:
    """Manages diary table operations."""

    def __init__(
        self,
        store: "UIStore",
        data_service: "UnifiedDataProtocol",
        diary_coordinator: "DiaryIntegrationCoordinator | None",
        diary_table_widget: "QWidget | None",
    ) -> None:
        """
        Initialize the diary table connector.

        Args:
            store: The UI store
            data_service: The unified data service
            diary_coordinator: The diary integration coordinator
            diary_table_widget: The diary table widget container

        """
        self.store = store
        self.data_service = data_service
        self.diary_coordinator = diary_coordinator
        self.diary_table_widget = diary_table_widget

    def update_diary_display(self) -> None:
        """
        Update diary table with data for current participant.

        Hides the diary section completely if no diary data is available
        for the current participant.
        """
        logger.info("=== DiaryTableConnector.update_diary_display START ===")

        if not self.data_service:
            logger.warning("No data_service - hiding diary section")
            self._hide_diary_section()
            return

        try:
            # First check if participant has any diary data at all
            # Get current file from store - service is headless
            current_file = self.store.state.current_file if self.store else None
            logger.info(f"DiaryTableConnector: store.current_file = {current_file}")

            if not current_file:
                logger.info("DiaryTableConnector: No current file - hiding section")
                self._hide_diary_section()
                return

            has_data = self.data_service.check_current_participant_has_diary_data(current_file)
            logger.info(f"check_current_participant_has_diary_data returned: {has_data}")

            if not has_data:
                # Hide the entire diary section if no diary data for this participant
                logger.info("DiaryTableConnector: No diary data - hiding section")
                self._hide_diary_section()
                return

            # Show the diary section since participant has data
            logger.info("DiaryTableConnector: HAS diary data - SHOWING section")
            self._show_diary_section()
            logger.info(
                f"DiaryTableConnector: After _show_diary_section, widget visible: {self.diary_table_widget.isVisible() if self.diary_table_widget else 'N/A'}"
            )

            # Load diary data for current file
            diary_entries = self.data_service.load_diary_data_for_current_file(current_file)
            logger.info(f"load_diary_data_for_current_file returned {len(diary_entries) if diary_entries else 0} entries")

            if not diary_entries:
                self._clear_diary_table()
                return

            # Display the diary data
            self._populate_diary_table(diary_entries)
            logger.info("=== DiaryTableConnector.update_diary_display COMPLETE ===")

        except Exception as e:
            logger.exception(f"=== DiaryTableConnector.update_diary_display FAILED: {e} ===")
            self._clear_diary_table()

    def _populate_diary_table(self, diary_entries) -> None:
        """Populate diary table with actual data."""
        table = self.diary_table_widget.diary_table

        # Set row count
        table.setRowCount(len(diary_entries))

        for row, entry in enumerate(diary_entries):
            # Helper function to format date - strip time if present
            def format_date(date_str: str | None) -> str:
                if not date_str:
                    return "--"
                # Remove timestamp portion if present (anything after space)
                return date_str.split()[0] if " " in date_str else date_str

            # Helper function to format boolean values
            def format_bool(value: bool | None) -> str:
                if value is None:
                    return "--"
                return "Yes" if value else "No"

            # Helper function to format nap count from diary entry
            def format_nap_count(value: int | None) -> str:
                """Format nap count value (should already be 0-3 from diary data)."""
                if value is None:
                    return "--"
                return str(value)

            # Create table items
            items = [
                QTableWidgetItem(format_date(entry.diary_date)),
                QTableWidgetItem(entry.in_bed_time or entry.bedtime or "--:--"),  # Try in_bed_time first, fallback to bedtime
                QTableWidgetItem(entry.sleep_onset_time or "--:--"),
                QTableWidgetItem(entry.sleep_offset_time or "--:--"),
                # Nap information - show actual count from diary data
                QTableWidgetItem(format_nap_count(entry.nap_occurred)),
                QTableWidgetItem(entry.nap_onset_time or "--:--"),
                QTableWidgetItem(entry.nap_offset_time or "--:--"),
                QTableWidgetItem(entry.nap_onset_time_2 or "--:--"),
                QTableWidgetItem(entry.nap_offset_time_2 or "--:--"),
                QTableWidgetItem(entry.nap_onset_time_3 or "--:--"),
                QTableWidgetItem(entry.nap_offset_time_3 or "--:--"),
                # Nonwear information
                QTableWidgetItem(format_bool(entry.nonwear_occurred)),
                QTableWidgetItem(entry.nonwear_start_time or "--:--"),
                QTableWidgetItem(entry.nonwear_end_time or "--:--"),
                QTableWidgetItem(entry.nonwear_reason or "--"),
                QTableWidgetItem(entry.nonwear_start_time_2 or "--:--"),
                QTableWidgetItem(entry.nonwear_end_time_2 or "--:--"),
                QTableWidgetItem(entry.nonwear_reason_2 or "--"),
                QTableWidgetItem(entry.nonwear_start_time_3 or "--:--"),
                QTableWidgetItem(entry.nonwear_end_time_3 or "--:--"),
                QTableWidgetItem(entry.nonwear_reason_3 or "--"),
            ]

            # Set items in table
            for col, item in enumerate(items):
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                # Center align all columns
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, col, item)

    def _clear_diary_table(self) -> None:
        """Clear the diary table."""
        table = self.diary_table_widget.diary_table
        table.setRowCount(0)

    def _show_diary_error(self, message: str) -> None:
        """Show error message in diary status label."""
        # Status label removed - errors can be logged instead
        logger.error(f"Diary error: {message}")

    def _show_diary_info(self, message: str) -> None:
        """Show info message in diary status label."""
        # Status label removed - info can be logged instead
        logger.info(f"Diary info: {message}")

    def _hide_diary_section(self) -> None:
        """Hide the diary table section completely."""
        if self.diary_table_widget:
            self.diary_table_widget.setVisible(False)
            logger.debug("Diary section hidden - no diary data available for participant")

    def _show_diary_section(self) -> None:
        """Show the diary table section."""
        if self.diary_table_widget:
            self.diary_table_widget.setVisible(True)
            logger.debug("Diary section shown")

    def on_diary_row_clicked(self, item) -> None:
        """Handle click on diary table row to set sleep markers from diary times."""
        if not item:
            return

        column = item.column()
        row = item.row()
        logger.debug(f"Diary click: row={row}, column={column}")

        # Get column type from diary_columns definition stored on the widget
        if hasattr(self.diary_table_widget, "diary_columns"):
            if column < len(self.diary_table_widget.diary_columns):
                column_def = self.diary_table_widget.diary_columns[column]
                column_type = column_def.id

                # Only handle clicks on time columns that set markers
                marker_columns = [
                    DiaryTableColumn.SLEEP_ONSET,
                    DiaryTableColumn.SLEEP_OFFSET,
                    DiaryTableColumn.NAP_1_START,
                    DiaryTableColumn.NAP_1_END,
                    DiaryTableColumn.NAP_2_START,
                    DiaryTableColumn.NAP_2_END,
                    DiaryTableColumn.NAP_3_START,
                    DiaryTableColumn.NAP_3_END,
                ]

                if column_type in marker_columns:
                    logger.debug(f"Diary click: marker column {column_type}")
                    # Use DiaryIntegrationCoordinator for marker placement
                    if self.diary_coordinator:
                        self.diary_coordinator.set_markers_from_diary_column(row, column_type)
                    else:
                        logger.debug("DiaryIntegrationCoordinator not available")
                else:
                    logger.debug(f"Clicked on non-marker column: {column_type}")
            else:
                logger.debug(f"Column index {column} out of range (max: {len(self.diary_table_widget.diary_columns) - 1})")
        else:
            logger.debug("Diary columns definition not found on diary_table_widget")
