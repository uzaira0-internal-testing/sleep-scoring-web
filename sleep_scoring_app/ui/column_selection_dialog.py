#!/usr/bin/env python3
"""
Column Selection Dialog for Export
Allows users to select which columns to include in exports.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.utils.column_registry import ColumnDefinition, column_registry


class ColumnSelectionDialog(QDialog):
    """Dialog for selecting columns to export."""

    def __init__(self, parent: QWidget, selected_columns: list[str]) -> None:
        super().__init__(parent)
        self.selected_columns = selected_columns.copy()
        self.column_checkboxes: dict[str, QCheckBox] = {}
        self.setup_ui()

    def setup_ui(self) -> None:
        """Set up the dialog UI."""
        self.setWindowTitle("Select Export Columns")
        self.setMinimumSize(500, 600)
        self.resize(550, 700)

        layout = QVBoxLayout(self)

        # Header with always-exported info - dynamically list always-exported columns
        always_exported = [c.display_name for c in column_registry.get_exportable() if c.is_always_exported]
        self._always_exported_count = len(always_exported)
        always_exported_str = ", ".join(always_exported) if always_exported else "None"
        header_label = QLabel(f"Select which columns to include in the export.\nAlways included: {always_exported_str}")
        header_label.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(header_label)

        # Select All / Deselect All buttons
        button_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all_columns)
        button_layout.addWidget(select_all_btn)

        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self._deselect_all_columns)
        button_layout.addWidget(deselect_all_btn)

        button_layout.addStretch()

        self.column_count_label = QLabel()
        button_layout.addWidget(self.column_count_label)

        layout.addLayout(button_layout)

        # Scroll area for column checkboxes
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(10)

        # Get exportable columns grouped by ui_group
        exportable_columns = column_registry.get_exportable()
        columns_by_group: dict[str, list[ColumnDefinition]] = {}

        for col in exportable_columns:
            if col.export_column and not col.is_always_exported:
                group_name = col.ui_group
                if group_name not in columns_by_group:
                    columns_by_group[group_name] = []
                columns_by_group[group_name].append(col)

        # Create a sub-group for each category
        for group_name in sorted(columns_by_group.keys()):
            columns = columns_by_group[group_name]
            category_group = QGroupBox(group_name)
            category_layout = QVBoxLayout(category_group)
            category_layout.setSpacing(2)

            for col in sorted(columns, key=lambda c: c.ui_order):
                checkbox = QCheckBox(col.display_name)
                checkbox.setChecked(col.export_column in self.selected_columns)
                checkbox.setToolTip(col.description or f"Export column: {col.export_column}")
                checkbox.stateChanged.connect(self._update_column_count)
                category_layout.addWidget(checkbox)
                self.column_checkboxes[col.export_column] = checkbox

            scroll_layout.addWidget(category_group)

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._update_column_count()

    def _select_all_columns(self) -> None:
        """Select all export columns."""
        for checkbox in self.column_checkboxes.values():
            checkbox.setChecked(True)

    def _deselect_all_columns(self) -> None:
        """Deselect all export columns."""
        for checkbox in self.column_checkboxes.values():
            checkbox.setChecked(False)

    def _update_column_count(self) -> None:
        """Update the column count label."""
        selected = sum(1 for cb in self.column_checkboxes.values() if cb.isChecked())
        total = len(self.column_checkboxes)
        # Add always-exported columns to counts
        always_count = self._always_exported_count
        self.column_count_label.setText(f"{selected + always_count}/{total + always_count} columns selected")

    def get_selected_columns(self) -> list[str]:
        """Get list of selected export column names."""
        selected = [export_col for export_col, checkbox in self.column_checkboxes.items() if checkbox.isChecked()]
        # Always include columns marked as is_always_exported
        for col in column_registry.get_exportable():
            if col.is_always_exported and col.export_column and col.export_column not in selected:
                selected.insert(0, col.export_column)
        return selected
