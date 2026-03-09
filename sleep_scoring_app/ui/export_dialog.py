#!/usr/bin/env python3
"""
Export Dialog UI Component
Modal dialog for configuring data export options.
"""

from __future__ import annotations

import pandas as pd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import ButtonText, ExportColumn, ExportUIGroup, WindowTitle
from sleep_scoring_app.utils.column_registry import column_registry


class ExportDialog(QDialog):
    """Modal dialog for configuring data export options."""

    def __init__(self, parent, backup_file_path) -> None:
        super().__init__(parent)
        self.backup_file_path = backup_file_path
        self.grouping_option = None
        self.output_path = None
        self.sleep_column_checkboxes: dict[str, QCheckBox] = {}
        self.nonwear_column_checkboxes: dict[str, QCheckBox] = {}
        self.setup_ui()

    def setup_ui(self) -> None:
        """Create the dialog interface."""
        self.setWindowTitle(WindowTitle.EXPORT_DIALOG)
        self.setModal(True)
        self.resize(700, 600)

        layout = QVBoxLayout(self)

        # Title
        title_label = QLabel("Export Sleep and Nonwear Data")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        # Data summary - create placeholder first, load data after dialog shows
        self.summary_label = QLabel("Loading data summary...")
        self.summary_label.setStyleSheet("margin: 10px; padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(self.summary_label)

        # Tab widget for Sleep and Nonwear column selection
        tab_widget = QTabWidget()

        # Sleep columns tab
        sleep_tab = self._create_sleep_columns_tab()
        tab_widget.addTab(sleep_tab, "Sleep Columns")

        # Nonwear columns tab
        nonwear_tab = self._create_nonwear_columns_tab()
        tab_widget.addTab(nonwear_tab, "Nonwear Columns")

        layout.addWidget(tab_widget)

        # Grouping options
        grouping_group = QGroupBox("Grouping Options")
        grouping_layout = QVBoxLayout(grouping_group)

        self.grouping_group = QButtonGroup()

        # All data in one file
        all_radio = QRadioButton("All data in one file")
        all_radio.setChecked(True)
        self.grouping_group.addButton(all_radio, 0)
        grouping_layout.addWidget(all_radio)

        # By participant ID
        participant_radio = QRadioButton("Separate file for each participant")
        self.grouping_group.addButton(participant_radio, 1)
        grouping_layout.addWidget(participant_radio)

        # By group
        group_radio = QRadioButton("Separate file for each group")
        self.grouping_group.addButton(group_radio, 2)
        grouping_layout.addWidget(group_radio)

        # By timepoint
        timepoint_radio = QRadioButton("Separate file for each timepoint")
        self.grouping_group.addButton(timepoint_radio, 3)
        grouping_layout.addWidget(timepoint_radio)

        layout.addWidget(grouping_group)

        # Output directory selection
        output_group = QGroupBox("Output Directory")
        output_layout = QVBoxLayout(output_group)

        self.output_label = QLabel("No directory selected")
        self.output_label.setStyleSheet("padding: 5px; background-color: white; border: 1px solid #ccc;")
        output_layout.addWidget(self.output_label)

        browse_btn = QPushButton(ButtonText.BROWSE)
        browse_btn.clicked.connect(self.browse_output_directory)
        output_layout.addWidget(browse_btn)

        layout.addWidget(output_group)

        # Buttons
        button_layout = QHBoxLayout()

        export_btn = QPushButton(ButtonText.EXPORT)
        export_btn.clicked.connect(self.accept)
        export_btn.setDefault(True)
        button_layout.addWidget(export_btn)

        cancel_btn = QPushButton(ButtonText.CANCEL)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        layout.addLayout(button_layout)

        # Load data after dialog is visible
        QTimer.singleShot(0, self._load_data_summary)

    def _create_sleep_columns_tab(self) -> QWidget:
        """Create tab for sleep column selection."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Header
        header = QLabel("Select columns to include in sleep data export")
        header.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(header)

        # Select/Deselect buttons
        button_layout = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._select_all_sleep_columns(True))
        button_layout.addWidget(select_all)

        deselect_all = QPushButton("Deselect All")
        deselect_all.clicked.connect(lambda: self._select_all_sleep_columns(False))
        button_layout.addWidget(deselect_all)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Scroll area for checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # Get sleep-related columns (excluding Nonwear Markers group)
        exportable_columns = column_registry.get_exportable()
        for col in sorted(exportable_columns, key=lambda c: c.ui_order):
            if col.export_column and col.ui_group != ExportUIGroup.NONWEAR_MARKERS and not col.is_always_exported:
                checkbox = QCheckBox(col.display_name)
                checkbox.setChecked(True)
                checkbox.setToolTip(col.description or f"Export column: {col.export_column}")
                scroll_layout.addWidget(checkbox)
                self.sleep_column_checkboxes[col.export_column] = checkbox

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return tab

    def _create_nonwear_columns_tab(self) -> QWidget:
        """Create tab for nonwear column selection."""
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # Header
        header = QLabel("Select columns to include in nonwear data export")
        header.setStyleSheet("font-weight: bold; padding: 5px;")
        layout.addWidget(header)

        # Select/Deselect buttons
        button_layout = QHBoxLayout()
        select_all = QPushButton("Select All")
        select_all.clicked.connect(lambda: self._select_all_nonwear_columns(True))
        button_layout.addWidget(select_all)

        deselect_all = QPushButton("Deselect All")
        deselect_all.clicked.connect(lambda: self._select_all_nonwear_columns(False))
        button_layout.addWidget(deselect_all)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Scroll area for checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)

        # Get nonwear-related columns (from Nonwear Markers group)
        exportable_columns = column_registry.get_exportable()
        for col in sorted(exportable_columns, key=lambda c: c.ui_order):
            if col.export_column and col.ui_group == ExportUIGroup.NONWEAR_MARKERS:
                checkbox = QCheckBox(col.display_name)
                checkbox.setChecked(True)
                checkbox.setToolTip(col.description or f"Export column: {col.export_column}")
                scroll_layout.addWidget(checkbox)
                self.nonwear_column_checkboxes[col.export_column] = checkbox

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        return tab

    def _select_all_sleep_columns(self, checked: bool) -> None:
        """Select or deselect all sleep columns."""
        for checkbox in self.sleep_column_checkboxes.values():
            checkbox.setChecked(checked)

    def _select_all_nonwear_columns(self, checked: bool) -> None:
        """Select or deselect all nonwear columns."""
        for checkbox in self.nonwear_column_checkboxes.values():
            checkbox.setChecked(checked)

    def _load_data_summary(self) -> None:
        """Load data summary after dialog is shown to prevent blocking."""
        try:
            df = pd.read_csv(self.backup_file_path, comment="#")
            summary_text = f"Data to export: {len(df)} records from backup file"

            # Try to show some sample data info
            if ExportColumn.FULL_PARTICIPANT_ID in df.columns:
                unique_participants = df[ExportColumn.FULL_PARTICIPANT_ID].nunique()
                summary_text += f"\nParticipants: {unique_participants}"

            if ExportColumn.PARTICIPANT_GROUP in df.columns:
                unique_groups = df[ExportColumn.PARTICIPANT_GROUP].nunique()
                summary_text += f"\nGroups: {unique_groups}"

        except (OSError, PermissionError, pd.errors.ParserError, ValueError) as e:
            summary_text = f"Error reading backup file: {e}"

        self.summary_label.setText(summary_text)

    def browse_output_directory(self) -> None:
        """Handle directory selection."""
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if directory:
            self.output_path = directory
            self.output_label.setText(directory)

    def get_grouping_option(self) -> int:
        """Return selected grouping option."""
        return self.grouping_group.checkedId()

    def get_output_path(self) -> str | None:
        """Return selected output path."""
        return self.output_path

    def get_selected_sleep_columns(self) -> list[str]:
        """Get list of selected sleep export column names."""
        selected = [col for col, cb in self.sleep_column_checkboxes.items() if cb.isChecked()]
        # Add always-exported columns
        for col in column_registry.get_exportable():
            if col.is_always_exported and col.export_column and col.export_column not in selected:
                selected.insert(0, col.export_column)
        return selected

    def get_selected_nonwear_columns(self) -> list[str]:
        """Get list of selected nonwear export column names."""
        selected = [col for col, cb in self.nonwear_column_checkboxes.items() if cb.isChecked()]
        # Add always-exported columns if they're in the Nonwear Markers group
        for col in column_registry.get_exportable():
            if col.is_always_exported and col.ui_group == ExportUIGroup.NONWEAR_MARKERS and col.export_column and col.export_column not in selected:
                selected.insert(0, col.export_column)
        return selected
