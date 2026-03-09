#!/usr/bin/env python3
"""
Configuration Import/Export Dialog UI Component.

Modal dialogs for selectively importing and exporting study configuration settings.
Allows researchers to share reproducible settings between collaborators.
Each individual setting can be selected/deselected for import/export.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import UIColors

if TYPE_CHECKING:
    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


# Setting metadata for display - maps config keys to human-readable names
SETTING_METADATA = {
    # Study settings
    "study.participant_id_patterns": ("Participant ID Pattern", "Regex pattern for extracting participant ID from filenames"),
    "study.timepoint_pattern": ("Timepoint Pattern", "Regex pattern for extracting timepoint (e.g., T1, T2)"),
    "study.group_pattern": ("Group Pattern", "Regex pattern for extracting group (e.g., G1, DEMO)"),
    "study.valid_groups": ("Valid Groups", "List of valid group values"),
    "study.valid_timepoints": ("Valid Timepoints", "List of valid timepoint values"),
    "study.default_group": ("Default Group", "Default group when extraction fails"),
    "study.default_timepoint": ("Default Timepoint", "Default timepoint when extraction fails"),
    "study.unknown_value": ("Unknown Value", "Placeholder for unknown values"),
    # Algorithm settings
    "algorithm.night_start_hour": ("Night Start Hour", "Hour when night period begins (e.g., 22 for 10 PM)"),
    "algorithm.night_end_hour": ("Night End Hour", "Hour when night period ends (e.g., 7 for 7 AM)"),
    "algorithm.choi_axis": ("Choi Algorithm Axis", "Axis for nonwear detection"),
    "algorithm.nonwear_algorithm": ("Nonwear Algorithm", "Algorithm for detecting nonwear periods"),
    # Data processing settings
    "data_processing.epoch_length": ("Epoch Length", "Duration of each data epoch in seconds"),
    "data_processing.skip_rows": ("Activity File Skip Rows", "Header rows to skip when reading activity CSV files"),
    "data_processing.preferred_activity_column": ("Activity Column to Plot", "Which activity column to display on the plot"),
    "data_processing.device_preset": ("Device Preset", "Accelerometer device type preset"),
}


class ConfigExportDialog(QDialog):
    """Dialog for selecting individual config settings to export."""

    def __init__(self, parent, config_manager: ConfigManager) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.setting_checkboxes: dict[str, QCheckBox] = {}
        self.output_path: Path | None = None
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the dialog interface."""
        self.setWindowTitle("Export Study Configuration")
        self.setModal(True)
        self.resize(600, 650)

        layout = QVBoxLayout(self)

        # Title and description
        title_label = QLabel("Export Study Configuration")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "Select individual settings to export.\nThis allows you to share specific study settings with collaborators for reproducibility."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {UIColors.TEXT_SECONDARY}; margin: 5px 10px;")
        layout.addWidget(desc_label)

        # Scrollable settings area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Get current config as dict to show current values
        config = self.config_manager.config
        config_dict = config.to_full_dict(include_paths=False) if config else {}

        # Study Settings Section
        study_group = self._create_section("Study Identification", "study", config_dict.get("study", {}))
        scroll_layout.addWidget(study_group)

        # Algorithm Settings Section
        algo_group = self._create_section("Algorithm Settings", "algorithm", config_dict.get("algorithm", {}))
        scroll_layout.addWidget(algo_group)

        # Data Processing Section
        data_group = self._create_section("Data Processing", "data_processing", config_dict.get("data_processing", {}))
        scroll_layout.addWidget(data_group)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Output file selection
        output_group = QGroupBox("Output File")
        output_layout = QVBoxLayout(output_group)

        self.output_label = QLabel("No file selected")
        self.output_label.setStyleSheet(f"padding: 8px; background-color: white; border: 1px solid {UIColors.PANEL_BORDER}; border-radius: 3px;")
        output_layout.addWidget(self.output_label)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_output_file)
        output_layout.addWidget(browse_btn)

        layout.addWidget(output_group)

        # Buttons
        button_layout = QHBoxLayout()

        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self._select_all)
        button_layout.addWidget(select_all_btn)

        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self._select_none)
        button_layout.addWidget(select_none_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.export_btn = QPushButton("Export")
        self.export_btn.setStyleSheet(f"background-color: {UIColors.BUTTON_PRIMARY}; color: white; font-weight: bold; padding: 8px 20px;")
        self.export_btn.clicked.connect(self._do_export)
        button_layout.addWidget(self.export_btn)

        layout.addLayout(button_layout)

    def _create_section(self, title: str, section_key: str, section_data: dict) -> QGroupBox:
        """Create a section group with individual setting checkboxes."""
        group = QGroupBox(title)
        group.setStyleSheet("QGroupBox { font-weight: bold; padding-top: 15px; margin-top: 10px; }")
        layout = QVBoxLayout(group)

        for key, value in section_data.items():
            full_key = f"{section_key}.{key}"
            metadata = SETTING_METADATA.get(full_key, (key.replace("_", " ").title(), ""))
            display_name, tooltip = metadata

            # Create row for this setting
            row = QFrame()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(5, 2, 5, 2)

            checkbox = QCheckBox(display_name)
            checkbox.setChecked(True)
            checkbox.setToolTip(tooltip)
            row_layout.addWidget(checkbox)

            # Show current value
            value_str = self._format_value(value)
            value_label = QLabel(value_str)
            value_label.setStyleSheet("font-family: monospace;")
            value_label.setToolTip(f"Current value: {value_str}")
            row_layout.addWidget(value_label, 1)

            self.setting_checkboxes[full_key] = checkbox
            layout.addWidget(row)

        return group

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if isinstance(value, list):
            if len(value) > 3:
                return f"[{', '.join(str(v) for v in value[:3])}, ...]"
            return f"[{', '.join(str(v) for v in value)}]"
        if isinstance(value, str) and len(value) > 40:
            return f'"{value[:37]}..."'
        return str(value)

    def _browse_output_file(self) -> None:
        """Open file dialog to select output file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Configuration",
            "study_config.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if file_path:
            self.output_path = Path(file_path)
            self.output_label.setText(str(self.output_path))

    def _select_all(self) -> None:
        """Select all settings."""
        for checkbox in self.setting_checkboxes.values():
            checkbox.setChecked(True)

    def _select_none(self) -> None:
        """Deselect all settings."""
        for checkbox in self.setting_checkboxes.values():
            checkbox.setChecked(False)

    def _do_export(self) -> None:
        """Perform the export with selected settings only."""
        if not self.output_path:
            QMessageBox.warning(self, "No Output File", "Please select an output file.")
            return

        selected_keys = [key for key, cb in self.setting_checkboxes.items() if cb.isChecked()]
        if not selected_keys:
            QMessageBox.warning(self, "No Settings Selected", "Please select at least one setting to export.")
            return

        try:
            # Get full config dict
            config = self.config_manager.config
            if config is None:
                QMessageBox.warning(self, "Error", "Configuration not loaded.")
                return
            full_config = config.to_full_dict(include_paths=False)

            # Build filtered config with only selected settings
            from sleep_scoring_app import __version__ as app_version

            export_config = {
                "config_schema_version": full_config.get("config_schema_version"),
                "app_version": app_version,
                "app_name": full_config.get("app_name"),
            }

            # Group selected keys by section
            for full_key in selected_keys:
                section, key = full_key.split(".", 1)
                if section not in export_config:
                    export_config[section] = {}
                if section in full_config and key in full_config[section]:
                    export_config[section][key] = full_config[section][key]

            # Remove empty sections
            export_config = {k: v for k, v in export_config.items() if v or not isinstance(v, dict)}

            # Write to file
            with open(self.output_path, "w", encoding="utf-8") as f:
                json.dump(export_config, f, indent=2)

            logger.info("Exported config to %s with %d settings", self.output_path, len(selected_keys))

            QMessageBox.information(
                self,
                "Export Successful",
                f"Configuration exported to:\n{self.output_path}\n\nSettings exported: {len(selected_keys)}",
            )
            self.accept()

        except Exception as e:
            logger.exception("Failed to export config")
            QMessageBox.critical(self, "Export Failed", f"Failed to export configuration:\n{e}")


class ConfigImportDialog(QDialog):
    """Dialog for selecting individual config settings to import."""

    def __init__(self, parent, config_manager: ConfigManager) -> None:
        super().__init__(parent)
        self.config_manager = config_manager
        self.import_data: dict | None = None
        self.setting_checkboxes: dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Create the dialog interface."""
        self.setWindowTitle("Import Study Configuration")
        self.setModal(True)
        self.resize(650, 700)

        layout = QVBoxLayout(self)

        # Title and description
        title_label = QLabel("Import Study Configuration")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)

        desc_label = QLabel(
            "Select a configuration file and choose which individual settings to import.\nImporting will overwrite your current values for selected settings."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet(f"color: {UIColors.TEXT_SECONDARY}; margin: 5px 10px;")
        layout.addWidget(desc_label)

        # File selection
        file_group = QGroupBox("Configuration File")
        file_layout = QVBoxLayout(file_group)

        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet(f"padding: 8px; background-color: white; border: 1px solid {UIColors.PANEL_BORDER}; border-radius: 3px;")
        file_layout.addWidget(self.file_label)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_input_file)
        file_layout.addWidget(browse_btn)

        layout.addWidget(file_group)

        # Version info (shown after file is loaded)
        self.version_label = QLabel("")
        self.version_label.setStyleSheet(f"color: {UIColors.TEXT_MUTED}; margin: 5px 10px;")
        layout.addWidget(self.version_label)

        # Scrollable settings area
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_widget)
        self.scroll_layout.addWidget(QLabel("Select a configuration file to see available settings."))
        self.scroll_layout.addStretch()
        self.scroll.setWidget(self.scroll_widget)
        layout.addWidget(self.scroll)  # pyright: ignore[reportArgumentType]

        # Buttons
        button_layout = QHBoxLayout()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._select_all)
        self.select_all_btn.setEnabled(False)
        button_layout.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self._select_none)
        self.select_none_btn.setEnabled(False)
        button_layout.addWidget(self.select_none_btn)

        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.import_btn = QPushButton("Import")
        self.import_btn.setStyleSheet(f"background-color: {UIColors.BUTTON_SUCCESS}; color: white; font-weight: bold; padding: 8px 20px;")
        self.import_btn.clicked.connect(self._do_import)
        self.import_btn.setEnabled(False)
        button_layout.addWidget(self.import_btn)

        layout.addLayout(button_layout)

    def _browse_input_file(self) -> None:
        """Open file dialog to select input file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Configuration",
            "",
            "JSON Files (*.json);;All Files (*)",
        )
        if file_path:
            self._load_config_file(Path(file_path))

    def _load_config_file(self, file_path: Path) -> None:
        """Load and parse the config file."""
        try:
            with open(file_path, encoding="utf-8") as f:
                self.import_data = json.load(f)

            self.file_label.setText(str(file_path))

            # Show version info
            import_data = self.import_data or {}
            schema_version = import_data.get("config_schema_version", "unknown")
            app_version = import_data.get("app_version", "unknown")
            self.version_label.setText(f"Config schema: {schema_version} | Created by app version: {app_version}")

            # Rebuild settings list based on what's in the file
            self._rebuild_settings_list()

            # Enable buttons
            self.select_all_btn.setEnabled(True)
            self.select_none_btn.setEnabled(True)
            self.import_btn.setEnabled(True)

        except json.JSONDecodeError as e:
            QMessageBox.critical(self, "Invalid File", f"The selected file is not valid JSON:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error Loading File", f"Failed to load configuration file:\n{e}")

    def _rebuild_settings_list(self) -> None:
        """Rebuild the settings table based on loaded config."""
        # Clear existing widgets
        while self.scroll_layout.count():
            item = self.scroll_layout.takeAt(0)
            if item is not None and (w := item.widget()) is not None:
                w.deleteLater()

        self.setting_checkboxes.clear()

        # Get current config for comparison
        config = self.config_manager.config
        current_config = config.to_full_dict(include_paths=False) if config else {}

        # Section order and display names
        section_order = [
            ("study", "Study Identification"),
            ("algorithm", "Algorithm Settings"),
            ("data_processing", "Data Processing"),
        ]

        # Collect all settings
        all_settings: list[tuple[str, str, object, object]] = []
        import_data = self.import_data or {}
        for section_key, section_title in section_order:
            if section_key in import_data and isinstance(import_data[section_key], dict):
                section_data = import_data[section_key]
                current_section = current_config.get(section_key, {})
                for key, new_value in section_data.items():
                    full_key = f"{section_key}.{key}"
                    current_value = current_section.get(key)
                    all_settings.append((full_key, section_title, new_value, current_value))

        if not all_settings:
            self.scroll_layout.addWidget(QLabel("No recognized configuration settings found in this file."))
            self.scroll_layout.addStretch()
            return

        # Create table
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["Import", "Setting", "Current Value", "New Value"])
        table.setRowCount(len(all_settings))
        if (vh := table.verticalHeader()) is not None:
            vh.setVisible(False)
        table.setAlternatingRowColors(True)

        # Let table size to content, scroll area handles overflow
        table.setSizeAdjustPolicy(QTableWidget.SizeAdjustPolicy.AdjustToContents)

        # Configure column sizing
        if (header := table.horizontalHeader()) is not None:
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        table.setColumnWidth(0, 50)

        for row, (full_key, section_title, new_value, current_value) in enumerate(all_settings):
            metadata = SETTING_METADATA.get(full_key, (full_key.split(".")[-1].replace("_", " ").title(), ""))
            display_name, tooltip = metadata
            is_different = current_value != new_value

            # Column 0: Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox.setToolTip(tooltip)
            self.setting_checkboxes[full_key] = checkbox
            checkbox_widget = QWidget()
            checkbox_layout = QHBoxLayout(checkbox_widget)
            checkbox_layout.addWidget(checkbox)
            checkbox_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            checkbox_layout.setContentsMargins(0, 0, 0, 0)
            table.setCellWidget(row, 0, checkbox_widget)

            # Column 1: Setting name
            name_item = QTableWidgetItem(display_name)
            name_item.setToolTip(f"{section_title}: {tooltip}")
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 1, name_item)

            # Column 2: Current value
            current_str = self._format_value(current_value)
            current_item = QTableWidgetItem(current_str)
            current_item.setFlags(current_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            table.setItem(row, 2, current_item)

            # Column 3: New value (red if different)
            new_str = self._format_value(new_value)
            new_item = QTableWidgetItem(new_str)
            new_item.setFlags(new_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if is_different:
                from PyQt6.QtGui import QColor

                new_item.setForeground(QColor(UIColors.BUTTON_DANGER))
            table.setItem(row, 3, new_item)

        self.scroll_layout.addWidget(table)

    def _format_value(self, value: Any) -> str:
        """Format a value for display."""
        if value is None:
            return "None"
        if isinstance(value, list):
            if len(value) > 3:
                return f"[{', '.join(str(v) for v in value[:3])}, ...]"
            return f"[{', '.join(str(v) for v in value)}]"
        if isinstance(value, str) and len(value) > 30:
            return f'"{value[:27]}..."'
        return str(value)

    def _select_all(self) -> None:
        """Select all settings."""
        for checkbox in self.setting_checkboxes.values():
            checkbox.setChecked(True)

    def _select_none(self) -> None:
        """Deselect all settings."""
        for checkbox in self.setting_checkboxes.values():
            checkbox.setChecked(False)

    def _do_import(self) -> None:
        """Perform the import with selected settings only."""
        if not self.import_data:
            QMessageBox.warning(self, "No File Loaded", "Please select a configuration file first.")
            return

        selected_keys = [key for key, cb in self.setting_checkboxes.items() if cb.isChecked()]
        if not selected_keys:
            QMessageBox.warning(self, "No Settings Selected", "Please select at least one setting to import.")
            return

        # Confirm import
        result = QMessageBox.question(
            self,
            "Confirm Import",
            f"This will overwrite {len(selected_keys)} setting(s) with values from the imported file.\n\nAre you sure you want to continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if result != QMessageBox.StandardButton.Yes:
            return

        try:
            current_config = self.config_manager.config

            # Apply selected settings to current config
            for full_key in selected_keys:
                section, key = full_key.split(".", 1)
                if section in self.import_data and key in self.import_data[section]:
                    new_value = self.import_data[section][key]
                    self._apply_setting(current_config, section, key, new_value)

            # Save the updated config
            self.config_manager.save_config()

            logger.info("Imported %d config settings", len(selected_keys))

            QMessageBox.information(
                self,
                "Import Successful",
                f"Configuration imported successfully.\n\n"
                f"Settings imported: {len(selected_keys)}\n\n"
                f"You may need to restart the application for all changes to take effect.",
            )
            self.accept()

        except Exception as e:
            logger.exception("Failed to import config")
            QMessageBox.critical(self, "Import Failed", f"Failed to import configuration:\n{e}")

    def _apply_setting(self, config, section: str, key: str, value: Any) -> None:
        """Apply a single setting to the config object."""
        # Map section.key to config attribute name
        attr_mapping = {
            # Study settings
            "study.participant_id_patterns": "study_participant_id_patterns",
            "study.timepoint_pattern": "study_timepoint_pattern",
            "study.group_pattern": "study_group_pattern",
            "study.valid_groups": "study_valid_groups",
            "study.valid_timepoints": "study_valid_timepoints",
            "study.default_group": "study_default_group",
            "study.default_timepoint": "study_default_timepoint",
            "study.unknown_value": "study_unknown_value",
            # Algorithm settings
            "algorithm.night_start_hour": "night_start_hour",
            "algorithm.night_end_hour": "night_end_hour",
            "algorithm.choi_axis": "choi_axis",
            "algorithm.nonwear_algorithm": "nonwear_algorithm",
            # Data processing settings
            "data_processing.epoch_length": "epoch_length",
            "data_processing.skip_rows": "skip_rows",
            "data_processing.preferred_activity_column": "preferred_activity_column",
            "data_processing.device_preset": "device_preset",
        }

        full_key = f"{section}.{key}"
        attr_name = attr_mapping.get(full_key)

        if attr_name and hasattr(config, attr_name):
            setattr(config, attr_name, value)
            logger.debug("Applied setting %s = %s", attr_name, value)
        else:
            logger.warning("Unknown config setting: %s.%s", section, key)
