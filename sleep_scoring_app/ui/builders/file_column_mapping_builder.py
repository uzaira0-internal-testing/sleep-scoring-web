"""
File Column Mapping Builder
Constructs the UI for configuring custom column mappings for Generic CSV format.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QComboBox

    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class FileColumnMappingBuilder:
    """Builder for file column mapping configuration UI."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings

        """
        self.config_manager = config_manager
        self.datetime_combined_check: QCheckBox | None = None
        self.date_column_combo: NoScrollComboBox | None = None
        self.time_column_combo: NoScrollComboBox | None = None
        self.time_label: QLabel | None = None
        self.axis_y_combo: NoScrollComboBox | None = None
        self.axis_x_combo: NoScrollComboBox | None = None
        self.axis_z_combo: NoScrollComboBox | None = None
        self.vector_magnitude_combo: NoScrollComboBox | None = None
        self.preview_table: QTableWidget | None = None
        self.columns_info_label: QLabel | None = None
        self.file_label: QLabel | None = None
        self.sample_file: Path | None = None
        self.detected_columns: list[str] = []

    def build(self, sample_file: Path | None = None) -> QDialog:
        """
        Build the column mapping dialog.

        Args:
            sample_file: Optional sample file to auto-detect columns from

        Returns:
            QDialog for column mapping configuration

        """
        self.sample_file = sample_file
        dialog = QDialog()
        dialog.setWindowTitle("Configure Column Mappings")
        dialog.setModal(True)
        dialog.setMinimumWidth(600)
        dialog.setMinimumHeight(500)

        layout = QVBoxLayout(dialog)

        # Instructions
        instructions = QLabel(
            "<b>Custom Column Mapping</b><br><br>"
            "Configure which columns contain your date, time, and activity data. "
            "Select a sample file to auto-detect available columns.<br>"
            "<span style='color: #666;'>Note: Sadeh algorithm requires Y-Axis (vertical). "
            "Choi algorithm can use Vector Magnitude or any axis.</span>"
        )
        instructions.setWordWrap(True)
        layout.addWidget(instructions)

        # File selection for column detection
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Sample File:"))
        self.file_label = QLabel(self.sample_file.name if self.sample_file else "No file selected")
        self.file_label.setStyleSheet("color: #666;")
        file_layout.addWidget(self.file_label, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_sample_file(dialog))
        file_layout.addWidget(browse_btn)
        detect_btn = QPushButton("Detect Columns")
        detect_btn.clicked.connect(lambda: self._detect_columns_from_file(dialog))
        file_layout.addWidget(detect_btn)
        layout.addLayout(file_layout)

        # Column mapping section - Datetime
        datetime_group = self._create_datetime_section()
        layout.addWidget(datetime_group)

        # Axis columns section
        axis_group = self._create_axis_section()
        layout.addWidget(axis_group)

        # Preview section
        preview_group = self._create_preview_section()
        layout.addWidget(preview_group)

        # Detected columns info
        self.columns_info_label = QLabel("")
        self.columns_info_label.setStyleSheet("color: #666; font-style: italic;")
        self.columns_info_label.setWordWrap(True)
        layout.addWidget(self.columns_info_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        button_box.rejected.connect(dialog.reject)
        button_box.accepted.connect(lambda: self._save_and_accept(dialog))
        layout.addWidget(button_box)

        # Load current config
        self._load_current_config()

        # Auto-detect columns if sample file provided
        if sample_file:
            self._detect_columns_from_file(dialog)

        return dialog

    def _create_datetime_section(self) -> QGroupBox:
        """Create datetime column mapping section."""
        datetime_group = QGroupBox("Datetime Columns")
        datetime_layout = QGridLayout(datetime_group)

        # Datetime format selection
        datetime_layout.addWidget(QLabel("Format:"), 0, 0)
        self.datetime_combined_check = QCheckBox("Combined datetime in single column")
        self.datetime_combined_check.stateChanged.connect(self._on_datetime_format_changed)
        datetime_layout.addWidget(self.datetime_combined_check, 0, 1, 1, 2)

        # Date column
        datetime_layout.addWidget(QLabel("Date Column:"), 1, 0)
        self.date_column_combo = NoScrollComboBox()
        self.date_column_combo.setEditable(True)
        self.date_column_combo.setMinimumWidth(200)
        datetime_layout.addWidget(self.date_column_combo, 1, 1, 1, 2)

        # Time column
        self.time_label = QLabel("Time Column:")
        datetime_layout.addWidget(self.time_label, 2, 0)
        self.time_column_combo = NoScrollComboBox()
        self.time_column_combo.setEditable(True)
        self.time_column_combo.setMinimumWidth(200)
        datetime_layout.addWidget(self.time_column_combo, 2, 1, 1, 2)

        return datetime_group

    def _create_axis_section(self) -> QGroupBox:
        """Create axis column mapping section."""
        axis_group = QGroupBox("Activity/Axis Columns")
        axis_layout = QGridLayout(axis_group)

        # Helper to create optional combo with "(not available)" option
        def create_axis_combo() -> NoScrollComboBox:
            combo = NoScrollComboBox()
            combo.setEditable(True)
            combo.setMinimumWidth(180)
            combo.addItem("(not available)", "")
            return combo

        # Y-Axis (vertical - required for Sadeh, ActiGraph Axis1)
        axis_y_label = QLabel("Y-Axis (Vertical):")
        axis_y_label.setToolTip("Required for Sadeh algorithm. ActiGraph: Axis1")
        axis_layout.addWidget(axis_y_label, 0, 0)
        self.axis_y_combo = create_axis_combo()
        axis_layout.addWidget(self.axis_y_combo, 0, 1)
        axis_layout.addWidget(QLabel("<span style='color: #e67e22;'>*Required for Sadeh</span>"), 0, 2)

        # X-Axis (lateral - ActiGraph Axis2)
        axis_layout.addWidget(QLabel("X-Axis (Lateral):"), 1, 0)
        self.axis_x_combo = create_axis_combo()
        axis_layout.addWidget(self.axis_x_combo, 1, 1)
        axis_layout.addWidget(QLabel("<span style='color: #999;'>(optional)</span>"), 1, 2)

        # Z-Axis (forward - ActiGraph Axis3)
        axis_layout.addWidget(QLabel("Z-Axis (Forward):"), 2, 0)
        self.axis_z_combo = create_axis_combo()
        axis_layout.addWidget(self.axis_z_combo, 2, 1)
        axis_layout.addWidget(QLabel("<span style='color: #999;'>(optional)</span>"), 2, 2)

        # Vector Magnitude
        vm_label = QLabel("Vector Magnitude:")
        vm_label.setToolTip("Recommended for Choi algorithm")
        axis_layout.addWidget(vm_label, 3, 0)
        self.vector_magnitude_combo = create_axis_combo()
        axis_layout.addWidget(self.vector_magnitude_combo, 3, 1)
        axis_layout.addWidget(QLabel("<span style='color: #27ae60;'>*Recommended for Choi</span>"), 3, 2)

        return axis_group

    def _create_preview_section(self) -> QGroupBox:
        """Create data preview section."""
        preview_group = QGroupBox("Data Preview (first 5 rows)")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_table = QTableWidget()
        self.preview_table.setMaximumHeight(120)
        preview_layout.addWidget(self.preview_table)
        return preview_group

    def _load_current_config(self) -> None:
        """Load current configuration into UI."""
        config = self.config_manager.config
        if config is None:
            return

        # Set datetime combined checkbox
        if self.datetime_combined_check:
            self.datetime_combined_check.setChecked(config.datetime_combined)
            self._on_datetime_format_changed()

        # Set datetime column values if they exist
        if config.custom_date_column and self.date_column_combo:
            self.date_column_combo.setCurrentText(config.custom_date_column)
        if config.custom_time_column and self.time_column_combo:
            self.time_column_combo.setCurrentText(config.custom_time_column)

        # Set axis column values if they exist
        if config.custom_axis_y_column and self.axis_y_combo:
            self.axis_y_combo.setCurrentText(config.custom_axis_y_column)
        if config.custom_axis_x_column and self.axis_x_combo:
            self.axis_x_combo.setCurrentText(config.custom_axis_x_column)
        if config.custom_axis_z_column and self.axis_z_combo:
            self.axis_z_combo.setCurrentText(config.custom_axis_z_column)
        if config.custom_vector_magnitude_column and self.vector_magnitude_combo:
            self.vector_magnitude_combo.setCurrentText(config.custom_vector_magnitude_column)

    def _on_datetime_format_changed(self) -> None:
        """Handle datetime format checkbox change."""
        if not self.datetime_combined_check or not self.time_label or not self.time_column_combo:
            return

        is_combined = self.datetime_combined_check.isChecked()
        self.time_label.setVisible(not is_combined)
        self.time_column_combo.setVisible(not is_combined)

        # Update date label
        if self.date_column_combo:
            if is_combined:
                self.date_column_combo.setToolTip("Column containing combined date and time")
            else:
                self.date_column_combo.setToolTip("Column containing date only")

    def _browse_sample_file(self, parent: QWidget) -> None:
        """Browse for a sample CSV file."""
        start_dir = str(self.sample_file.parent) if self.sample_file else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            parent,
            "Select Sample CSV File",
            start_dir,
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if file_path:
            self.sample_file = Path(file_path)
            if self.file_label:
                self.file_label.setText(self.sample_file.name)
                self.file_label.setStyleSheet("color: #333;")
            self._detect_columns_from_file(parent)

    def _detect_columns_from_file(self, parent: QWidget) -> None:
        """Detect columns from the sample file."""
        if not self.sample_file or not self.sample_file.exists():
            return

        try:
            # Read first few lines to detect columns
            with open(self.sample_file, encoding="utf-8", errors="ignore") as f:
                # Detect delimiter
                sample = f.read(8192)
                f.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
                except csv.Error:
                    dialect = csv.excel

                reader = csv.reader(f, dialect)
                lines = []
                for i, row in enumerate(reader):
                    if i >= 20:  # Read first 20 lines to find header
                        break
                    lines.append(row)

            # Find the header row (first row with mostly non-numeric strings)
            header_row_idx = 0
            for i, row in enumerate(lines):
                non_numeric = sum(1 for c in row if c and not self._is_numeric(c))
                if non_numeric >= len(row) * 0.5 and len(row) >= 3:
                    header_row_idx = i
                    break

            # Get columns from header row
            if lines:
                self.detected_columns = [c.strip() for c in lines[header_row_idx] if c.strip()]
                self._populate_column_combos()
                self._update_preview(lines, header_row_idx, dialect)

                # Show detected columns
                if self.columns_info_label:
                    self.columns_info_label.setText(
                        f"Detected {len(self.detected_columns)} columns: {', '.join(self.detected_columns[:10])}"
                        + ("..." if len(self.detected_columns) > 10 else "")
                    )

                # Auto-select likely columns
                self._auto_select_columns()

        except Exception as e:
            logger.exception("Error detecting columns from file")
            QMessageBox.warning(parent, "Detection Error", f"Failed to detect columns: {e}")

    def _is_numeric(self, value: str) -> bool:
        """Check if a string value is numeric."""
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False

    def _populate_column_combos(self) -> None:
        """Populate column combo boxes with detected columns."""
        if not self.date_column_combo or not self.time_column_combo:
            return

        # Save current selections
        current_date = self.date_column_combo.currentText()
        current_time = self.time_column_combo.currentText()
        current_axis_y = self.axis_y_combo.currentText() if self.axis_y_combo else ""
        current_axis_x = self.axis_x_combo.currentText() if self.axis_x_combo else ""
        current_axis_z = self.axis_z_combo.currentText() if self.axis_z_combo else ""
        current_vm = self.vector_magnitude_combo.currentText() if self.vector_magnitude_combo else ""

        # Datetime combos - just add columns directly
        for combo in [self.date_column_combo, self.time_column_combo]:
            combo.clear()
            combo.addItems(self.detected_columns)

        # Axis combos - add "(not available)" option first, then columns
        for combo in [self.axis_y_combo, self.axis_x_combo, self.axis_z_combo, self.vector_magnitude_combo]:
            if combo:
                combo.clear()
                combo.addItem("(not available)", "")
                combo.addItems(self.detected_columns)

        # Restore selections if they exist in new columns
        if current_date in self.detected_columns:
            self.date_column_combo.setCurrentText(current_date)
        if current_time in self.detected_columns:
            self.time_column_combo.setCurrentText(current_time)
        if self.axis_y_combo and current_axis_y in self.detected_columns:
            self.axis_y_combo.setCurrentText(current_axis_y)
        if self.axis_x_combo and current_axis_x in self.detected_columns:
            self.axis_x_combo.setCurrentText(current_axis_x)
        if self.axis_z_combo and current_axis_z in self.detected_columns:
            self.axis_z_combo.setCurrentText(current_axis_z)
        if self.vector_magnitude_combo and current_vm in self.detected_columns:
            self.vector_magnitude_combo.setCurrentText(current_vm)

    def _auto_select_columns(self) -> None:
        """Auto-select likely column names based on common patterns."""
        if not self.date_column_combo or not self.time_column_combo:
            return

        columns_lower = {c.lower(): c for c in self.detected_columns}

        # Date patterns
        date_patterns = ["date", "datetime", "timestamp", "time"]
        for pattern in date_patterns:
            for col_lower, col_orig in columns_lower.items():
                if pattern in col_lower:
                    self.date_column_combo.setCurrentText(col_orig)
                    # Check if it's likely a combined datetime
                    if self.datetime_combined_check and ("datetime" in col_lower or "timestamp" in col_lower):
                        self.datetime_combined_check.setChecked(True)
                    break
            else:
                continue
            break

        # Time patterns (only if not combined)
        if self.datetime_combined_check and not self.datetime_combined_check.isChecked():
            time_patterns = ["time"]
            for pattern in time_patterns:
                for col_lower, col_orig in columns_lower.items():
                    if col_lower == pattern or col_lower.endswith("time"):
                        self.time_column_combo.setCurrentText(col_orig)
                        break
                else:
                    continue
                break

        # Y-Axis patterns (ActiGraph: Axis1 = Y-axis vertical, GENEActiv/Axivity: y)
        if self.axis_y_combo:
            for col_lower, col_orig in columns_lower.items():
                if col_lower == "y" or "axis_y" in col_lower or "axis y" in col_lower or "axisy" in col_lower:
                    self.axis_y_combo.setCurrentText(col_orig)
                    break

        # X-Axis patterns (ActiGraph: Axis2 = X-axis lateral, GENEActiv/Axivity: x)
        if self.axis_x_combo:
            for col_lower, col_orig in columns_lower.items():
                if col_lower == "x" or "axis2" in col_lower or "axis 2" in col_lower:
                    self.axis_x_combo.setCurrentText(col_orig)
                    break

        # Z-Axis patterns (ActiGraph: Axis3 = Z-axis forward, GENEActiv/Axivity: z)
        if self.axis_z_combo:
            for col_lower, col_orig in columns_lower.items():
                if col_lower == "z" or "axis3" in col_lower or "axis 3" in col_lower:
                    self.axis_z_combo.setCurrentText(col_orig)
                    break

        # Vector Magnitude patterns
        if self.vector_magnitude_combo:
            vm_patterns = ["vector magnitude", "vectormagnitude", "vm", "svm", "magnitude"]
            for col_lower, col_orig in columns_lower.items():
                if any(p in col_lower for p in vm_patterns):
                    self.vector_magnitude_combo.setCurrentText(col_orig)
                    break

    def _update_preview(self, lines: list[list[str]], header_idx: int, dialect) -> None:
        """Update the preview table with sample data."""
        if not self.preview_table or not lines or header_idx >= len(lines):
            return

        headers = lines[header_idx]
        data_rows = lines[header_idx + 1 : header_idx + 6]  # Next 5 rows

        self.preview_table.clear()
        self.preview_table.setColumnCount(min(len(headers), 8))  # Limit to 8 columns
        self.preview_table.setRowCount(len(data_rows))
        self.preview_table.setHorizontalHeaderLabels(headers[: min(len(headers), 8)])

        for row_idx, row in enumerate(data_rows):
            for col_idx, value in enumerate(row[: min(len(row), 8)]):
                item = QTableWidgetItem(value)
                self.preview_table.setItem(row_idx, col_idx, item)

        self.preview_table.resizeColumnsToContents()

    def _get_combo_value(self, combo: QComboBox) -> str:
        """Get combo value, returning empty string for '(not available)'."""
        text = combo.currentText().strip()
        return "" if text == "(not available)" else text

    def _save_and_accept(self, dialog: QDialog) -> None:
        """Save configuration and accept dialog."""
        if not self.date_column_combo or not self.time_column_combo:
            return

        # Get values
        date_col = self.date_column_combo.currentText().strip()
        time_col = self.time_column_combo.currentText().strip()
        is_combined = self.datetime_combined_check.isChecked() if self.datetime_combined_check else False

        # Get axis columns
        axis_y_col = self._get_combo_value(self.axis_y_combo) if self.axis_y_combo else ""
        axis_x_col = self._get_combo_value(self.axis_x_combo) if self.axis_x_combo else ""
        axis_z_col = self._get_combo_value(self.axis_z_combo) if self.axis_z_combo else ""
        vm_col = self._get_combo_value(self.vector_magnitude_combo) if self.vector_magnitude_combo else ""

        # Validate datetime columns
        if not date_col:
            QMessageBox.warning(dialog, "Validation Error", "Please select a date column.")
            return

        if not is_combined and not time_col:
            QMessageBox.warning(dialog, "Validation Error", "Please select a time column.")
            return

        # Warn if Y-Axis not set (required for Sadeh - vertical axis)
        if not axis_y_col:
            reply = QMessageBox.warning(
                dialog,
                "Missing Y-Axis",
                "Y-Axis (vertical) column is not set. The Sadeh algorithm requires Y-Axis data.\n\nContinue anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # Save to config
        config = self.config_manager.config
        if config is None:
            dialog.accept()
            return

        from dataclasses import replace

        self.config_manager.config = replace(
            config,
            custom_date_column=date_col,
            custom_time_column=time_col if not is_combined else "",
            datetime_combined=is_combined,
            custom_axis_y_column=axis_y_col,
            custom_axis_x_column=axis_x_col,
            custom_axis_z_column=axis_z_col,
            custom_vector_magnitude_column=vm_col,
        )
        self.config_manager.save_config()

        logger.info(
            "Column mapping saved: date=%s, time=%s, combined=%s, axis_y=%s, axis_x=%s, axis_z=%s, vm=%s",
            date_col,
            time_col,
            is_combined,
            axis_y_col,
            axis_x_col,
            axis_z_col,
            vm_col,
        )

        dialog.accept()
