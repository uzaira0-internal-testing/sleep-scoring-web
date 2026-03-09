"""
Column Mapping Dialog
Dialog for configuring custom column mappings for Generic CSV format.
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


class ColumnMappingDialog(QDialog):
    """Dialog for configuring custom column mappings for Generic CSV format."""

    def __init__(
        self,
        parent: QWidget | None = None,
        config_manager: ConfigManager | None = None,
        sample_file: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.sample_file = sample_file
        self.detected_columns: list[str] = []

        self.setWindowTitle("Configure Column Mappings")
        self.setModal(True)
        self.setMinimumWidth(600)
        self.setMinimumHeight(500)

        self._setup_ui()
        self._load_current_config()

        if sample_file:
            self._detect_columns_from_file()

    def _setup_ui(self) -> None:
        """Set up the dialog UI."""
        layout = QVBoxLayout(self)

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
        browse_btn.clicked.connect(self._browse_sample_file)
        file_layout.addWidget(browse_btn)
        detect_btn = QPushButton("Detect Columns")
        detect_btn.clicked.connect(self._detect_columns_from_file)
        file_layout.addWidget(detect_btn)
        layout.addLayout(file_layout)

        # Column mapping section - Datetime
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

        layout.addWidget(datetime_group)

        # Axis columns section
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

        layout.addWidget(axis_group)

        # Preview section
        preview_group = QGroupBox("Data Preview (first 5 rows)")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_table = QTableWidget()
        self.preview_table.setMaximumHeight(120)
        preview_layout.addWidget(self.preview_table)
        layout.addWidget(preview_group)

        # Detected columns info
        self.columns_info_label = QLabel("")
        self.columns_info_label.setStyleSheet("color: #666; font-style: italic;")
        self.columns_info_label.setWordWrap(True)
        layout.addWidget(self.columns_info_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Ok)
        button_box.rejected.connect(self.reject)
        button_box.accepted.connect(self._save_and_accept)
        layout.addWidget(button_box)

    def _load_current_config(self) -> None:
        """Load current configuration into UI."""
        if not self.config_manager:
            return

        config = self.config_manager.config
        if config is None:
            return

        # Set datetime combined checkbox
        self.datetime_combined_check.setChecked(config.datetime_combined)
        self._on_datetime_format_changed()

        # Set datetime column values if they exist
        if config.custom_date_column:
            self.date_column_combo.setCurrentText(config.custom_date_column)
        if config.custom_time_column:
            self.time_column_combo.setCurrentText(config.custom_time_column)

        # Set axis column values if they exist
        if config.custom_axis_y_column:
            self.axis_y_combo.setCurrentText(config.custom_axis_y_column)
        if config.custom_axis_x_column:
            self.axis_x_combo.setCurrentText(config.custom_axis_x_column)
        if config.custom_axis_z_column:
            self.axis_z_combo.setCurrentText(config.custom_axis_z_column)
        if config.custom_vector_magnitude_column:
            self.vector_magnitude_combo.setCurrentText(config.custom_vector_magnitude_column)

    def _on_datetime_format_changed(self) -> None:
        """Handle datetime format checkbox change."""
        is_combined = self.datetime_combined_check.isChecked()
        self.time_label.setVisible(not is_combined)
        self.time_column_combo.setVisible(not is_combined)

        # Update date label
        if is_combined:
            self.date_column_combo.setToolTip("Column containing combined date and time")
        else:
            self.date_column_combo.setToolTip("Column containing date only")

    def _browse_sample_file(self) -> None:
        """Browse for a sample CSV file."""
        start_dir = str(self.sample_file.parent) if self.sample_file else str(Path.home())
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Sample CSV File",
            start_dir,
            "CSV Files (*.csv);;All Files (*.*)",
        )
        if file_path:
            self.sample_file = Path(file_path)
            self.file_label.setText(self.sample_file.name)
            self.file_label.setStyleSheet("color: #333;")
            self._detect_columns_from_file()

    def _detect_columns_from_file(self) -> None:
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
                self.columns_info_label.setText(
                    f"Detected {len(self.detected_columns)} columns: {', '.join(self.detected_columns[:10])}"
                    + ("..." if len(self.detected_columns) > 10 else "")
                )

                # Auto-select likely columns
                self._auto_select_columns()

        except Exception as e:
            logger.exception("Error detecting columns from file")
            QMessageBox.warning(self, "Detection Error", f"Failed to detect columns: {e}")

    def _is_numeric(self, value: str) -> bool:
        """Check if a string value is numeric."""
        try:
            float(value.replace(",", ""))
            return True
        except ValueError:
            return False

    def _populate_column_combos(self) -> None:
        """Populate column combo boxes with detected columns."""
        # Save current selections
        current_date = self.date_column_combo.currentText()
        current_time = self.time_column_combo.currentText()
        current_axis_y = self.axis_y_combo.currentText()
        current_axis_x = self.axis_x_combo.currentText()
        current_axis_z = self.axis_z_combo.currentText()
        current_vm = self.vector_magnitude_combo.currentText()

        # Datetime combos - just add columns directly
        for combo in [self.date_column_combo, self.time_column_combo]:
            combo.clear()
            combo.addItems(self.detected_columns)

        # Axis combos - add "(not available)" option first, then columns
        for combo in [self.axis_y_combo, self.axis_x_combo, self.axis_z_combo, self.vector_magnitude_combo]:
            combo.clear()
            combo.addItem("(not available)", "")
            combo.addItems(self.detected_columns)

        # Restore selections if they exist in new columns
        if current_date in self.detected_columns:
            self.date_column_combo.setCurrentText(current_date)
        if current_time in self.detected_columns:
            self.time_column_combo.setCurrentText(current_time)
        if current_axis_y in self.detected_columns:
            self.axis_y_combo.setCurrentText(current_axis_y)
        if current_axis_x in self.detected_columns:
            self.axis_x_combo.setCurrentText(current_axis_x)
        if current_axis_z in self.detected_columns:
            self.axis_z_combo.setCurrentText(current_axis_z)
        if current_vm in self.detected_columns:
            self.vector_magnitude_combo.setCurrentText(current_vm)

    def _auto_select_columns(self) -> None:
        """Auto-select likely column names based on common patterns."""
        columns_lower = {c.lower(): c for c in self.detected_columns}

        # Date patterns
        date_patterns = ["date", "datetime", "timestamp", "time"]
        for pattern in date_patterns:
            for col_lower, col_orig in columns_lower.items():
                if pattern in col_lower:
                    self.date_column_combo.setCurrentText(col_orig)
                    # Check if it's likely a combined datetime
                    if "datetime" in col_lower or "timestamp" in col_lower:
                        self.datetime_combined_check.setChecked(True)
                    break
            else:
                continue
            break

        # Time patterns (only if not combined)
        if not self.datetime_combined_check.isChecked():
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
        for col_lower, col_orig in columns_lower.items():
            if col_lower == "y" or "axis_y" in col_lower or "axis y" in col_lower or "axisy" in col_lower:
                self.axis_y_combo.setCurrentText(col_orig)
                break

        # X-Axis patterns (ActiGraph: Axis2 = X-axis lateral, GENEActiv/Axivity: x)
        for col_lower, col_orig in columns_lower.items():
            if col_lower == "x" or "axis2" in col_lower or "axis 2" in col_lower:
                self.axis_x_combo.setCurrentText(col_orig)
                break

        # Z-Axis patterns (ActiGraph: Axis3 = Z-axis forward, GENEActiv/Axivity: z)
        for col_lower, col_orig in columns_lower.items():
            if col_lower == "z" or "axis3" in col_lower or "axis 3" in col_lower:
                self.axis_z_combo.setCurrentText(col_orig)
                break

        # Vector Magnitude patterns
        vm_patterns = ["vector magnitude", "vectormagnitude", "vm", "svm", "magnitude"]
        for col_lower, col_orig in columns_lower.items():
            if any(p in col_lower for p in vm_patterns):
                self.vector_magnitude_combo.setCurrentText(col_orig)
                break

    def _update_preview(self, lines: list[list[str]], header_idx: int, dialect) -> None:
        """Update the preview table with sample data."""
        if not lines or header_idx >= len(lines):
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

    def _save_and_accept(self) -> None:
        """Save configuration and accept dialog."""
        if not self.config_manager:
            self.accept()
            return

        # Get values
        date_col = self.date_column_combo.currentText().strip()
        time_col = self.time_column_combo.currentText().strip()
        is_combined = self.datetime_combined_check.isChecked()

        # Get axis columns
        axis_y_col = self._get_combo_value(self.axis_y_combo)
        axis_x_col = self._get_combo_value(self.axis_x_combo)
        axis_z_col = self._get_combo_value(self.axis_z_combo)
        vm_col = self._get_combo_value(self.vector_magnitude_combo)

        # Validate datetime columns
        if not date_col:
            QMessageBox.warning(self, "Validation Error", "Please select a date column.")
            return

        if not is_combined and not time_col:
            QMessageBox.warning(self, "Validation Error", "Please select a time column.")
            return

        # Warn if Y-Axis not set (required for Sadeh - vertical axis)
        if not axis_y_col:
            reply = QMessageBox.warning(
                self,
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
            self.accept()
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

        self.accept()
