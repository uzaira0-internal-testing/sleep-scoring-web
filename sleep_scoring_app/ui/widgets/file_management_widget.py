#!/usr/bin/env python3
"""
File Management Widget (Dumb Presenter)
Displays a list of files and emits signals for user actions.
No business logic or service references allowed.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import FileInfo

logger = logging.getLogger(__name__)


class FileManagementWidget(QWidget):
    """Presentational widget for managing imported files."""

    # Signals for user actions
    refreshRequested = pyqtSignal()
    deleteRequested = pyqtSignal(list)  # list of filenames

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initialize the presentational widget."""
        super().__init__(parent)
        self._file_data: list[FileInfo] = []
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the widget UI."""
        layout = QVBoxLayout(self)

        # Table for file list
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(7)
        self.file_table.setHorizontalHeaderLabels(["Filename", "Participant ID", "Start Date", "End Date", "Records", "Has Metrics", "Actions"])

        # Configure table visuals
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.setSelectionMode(QTableWidget.SelectionMode.MultiSelection)
        self.file_table.setAlternatingRowColors(True)
        self.file_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.file_table)

        # Button row
        button_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.clicked.connect(self.refreshRequested.emit)
        button_layout.addWidget(self.refresh_btn)

        button_layout.addStretch()

        self.delete_selected_btn = QPushButton("Delete Selected")
        self.delete_selected_btn.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")
        self.delete_selected_btn.clicked.connect(self._on_delete_selected_clicked)
        button_layout.addWidget(self.delete_selected_btn)

        layout.addLayout(button_layout)

    def set_files(self, files: list[FileInfo]) -> None:
        """
        Update the displayed files (Data Injection).
        This is called by the Connector.
        """
        self._file_data = list(files)
        self.file_table.setRowCount(len(files))

        for row, file_info in enumerate(files):
            filename = file_info.filename
            self.file_table.setItem(row, 0, QTableWidgetItem(filename))
            self.file_table.setItem(row, 1, QTableWidgetItem(file_info.participant_id))
            self.file_table.setItem(row, 2, QTableWidgetItem(file_info.start_date or ""))
            self.file_table.setItem(row, 3, QTableWidgetItem(file_info.end_date or ""))
            self.file_table.setItem(row, 4, QTableWidgetItem(str(file_info.total_records)))

            metrics_item = QTableWidgetItem("Yes" if file_info.has_metrics else "No")
            if file_info.has_metrics:
                metrics_item.setForeground(Qt.GlobalColor.darkGreen)
            self.file_table.setItem(row, 5, metrics_item)

            # Delete button for single row
            del_btn = QPushButton("Delete")
            del_btn.clicked.connect(lambda checked, f=filename: self.deleteRequested.emit([f]))
            self.file_table.setCellWidget(row, 6, del_btn)

    def _on_delete_selected_clicked(self) -> None:
        """Gather selected filenames and emit signal."""
        selected_rows = {item.row() for item in self.file_table.selectedItems()}
        filenames = [self._file_data[row].filename for row in selected_rows if row < len(self._file_data)]
        if filenames:
            self.deleteRequested.emit(filenames)
