#!/usr/bin/env python3
"""
Delete File Confirmation Dialog
Shows confirmation before deleting imported files.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from sleep_scoring_app.core.dataclasses import FileInfo

logger = logging.getLogger(__name__)


class DeleteFileDialog(QDialog):
    """Confirmation dialog for file deletion with warnings."""

    def __init__(self, files: list[FileInfo], parent: QWidget | None = None) -> None:
        """
        Initialize the delete confirmation dialog.

        Args:
            files: List of files to be deleted
            parent: Parent widget

        """
        super().__init__(parent)
        self.files = files
        self.setWindowTitle("Confirm File Deletion")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

        # Check if any files have metrics
        files_with_metrics_count = sum(1 for f in self.files if f.has_metrics)

        # Warning header
        header_text = f"<b>Delete {len(self.files)} file(s)?</b><br><br>"
        header_text += "This will permanently delete the imported data and cannot be undone."

        if files_with_metrics_count > 0:
            header_text += "<br><br>"
            header_text += f"<span style='color: #e67e22;'><b>Warning:</b> {files_with_metrics_count} file(s) have associated sleep metrics that will also be deleted.</span>"

        header_label = QLabel(header_text)
        header_label.setWordWrap(True)
        layout.addWidget(header_label)

        # Table showing files to be deleted
        file_table = QTableWidget()
        file_table.setColumnCount(4)
        file_table.setHorizontalHeaderLabels(["Filename", "Participant ID", "Records", "Has Metrics"])
        file_table.setRowCount(len(self.files))

        for row, file_info in enumerate(self.files):
            # Filename
            filename_item = QTableWidgetItem(file_info.filename)
            filename_item.setFlags(filename_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            file_table.setItem(row, 0, filename_item)

            # Participant ID
            participant_item = QTableWidgetItem(file_info.participant_id)
            participant_item.setFlags(participant_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            participant_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            file_table.setItem(row, 1, participant_item)

            # Record count
            records_item = QTableWidgetItem(str(file_info.total_records))
            records_item.setFlags(records_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            records_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            file_table.setItem(row, 2, records_item)

            # Has metrics
            metrics_text = "Yes" if file_info.has_metrics else "No"
            metrics_item = QTableWidgetItem(metrics_text)
            metrics_item.setFlags(metrics_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            metrics_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if file_info.has_metrics:
                metrics_item.setForeground(Qt.GlobalColor.darkRed)

            file_table.setItem(row, 3, metrics_item)

        file_table.resizeColumnsToContents()
        layout.addWidget(file_table)

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)

        # Style the OK button as Delete
        delete_button = button_box.button(QDialogButtonBox.StandardButton.Ok)
        delete_button.setText("Delete")
        delete_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
        """)

        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
