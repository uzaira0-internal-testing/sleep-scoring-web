"""
Data Source Configuration Builder
Constructs the UI for data source configuration settings.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from sleep_scoring_app.core.constants import DataSourceType, DevicePreset
from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox, NoScrollSpinBox

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QComboBox, QSpinBox

    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class DataSourceConfigBuilder:
    """Builder for data source configuration UI."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings

        """
        self.config_manager = config_manager

        # Main settings widgets
        self.data_source_combo: QComboBox | None = None
        self.device_preset_combo: QComboBox | None = None
        self.epoch_length_spin: QSpinBox | None = None
        self.skip_rows_spin: QSpinBox | None = None

        # Auto-detect buttons
        self.device_autodetect_btn: QPushButton | None = None
        self.epoch_autodetect_btn: QPushButton | None = None
        self.skip_rows_autodetect_btn: QPushButton | None = None
        self.autodetect_all_btn: QPushButton | None = None
        self.configure_columns_btn: QPushButton | None = None

        # GT3X-specific widgets
        self.gt3x_options_widget: QWidget | None = None
        self.gt3x_epoch_length_spin: QSpinBox | None = None
        self.gt3x_return_raw_check: QCheckBox | None = None

        # CSV-specific widgets
        self.csv_options_widget: QWidget | None = None

    def build(self) -> tuple[QGroupBox, QWidget, QWidget]:
        """
        Build the data source configuration section.

        Returns:
            Tuple of (settings_group, csv_options_widget, gt3x_options_widget)

        """
        # Create the main settings grid (this goes inside the parent's activity_group)
        settings_grid = QGridLayout()

        # Data Source Type dropdown
        settings_grid.addWidget(QLabel("Data Source Type:"), 0, 0)
        self.data_source_combo = NoScrollComboBox()
        self.data_source_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.data_source_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.data_source_combo, 0, 1)

        # Device Preset dropdown
        settings_grid.addWidget(QLabel("Device Preset:"), 1, 0)
        self.device_preset_combo = NoScrollComboBox()
        device_display_names = {
            DevicePreset.ACTIGRAPH: "ActiGraph",
            DevicePreset.GENEACTIV: "GENEActiv",
            DevicePreset.AXIVITY: "Axivity",
            DevicePreset.ACTIWATCH: "Actiwatch",
            DevicePreset.MOTIONWATCH: "MotionWatch",
            DevicePreset.GENERIC_CSV: "Generic CSV",
        }
        for preset in DevicePreset:
            self.device_preset_combo.addItem(device_display_names[preset], preset.value)
        self.device_preset_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.device_preset_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.device_preset_combo, 1, 1)

        # Auto-detect device button
        self.device_autodetect_btn = QPushButton("Auto-detect")
        settings_grid.addWidget(self.device_autodetect_btn, 1, 2)

        # Configure Columns button
        self.configure_columns_btn = QPushButton("Configure Columns...")
        settings_grid.addWidget(self.configure_columns_btn, 1, 3)

        # Epoch length
        settings_grid.addWidget(QLabel("Epoch Length (seconds):"), 2, 0)
        self.epoch_length_spin = NoScrollSpinBox()
        self.epoch_length_spin.setRange(1, 300)
        self.epoch_length_spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.epoch_length_spin, 2, 1)

        # Auto-detect epoch length button
        self.epoch_autodetect_btn = QPushButton("Auto-detect")
        settings_grid.addWidget(self.epoch_autodetect_btn, 2, 2)

        # Skip rows
        settings_grid.addWidget(QLabel("Skip Rows:"), 3, 0)
        self.skip_rows_spin = NoScrollSpinBox()
        self.skip_rows_spin.setRange(0, 100)
        self.skip_rows_spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.skip_rows_spin, 3, 1)

        # Auto-detect skip rows button
        self.skip_rows_autodetect_btn = QPushButton("Auto-detect")
        settings_grid.addWidget(self.skip_rows_autodetect_btn, 3, 2)

        # Auto-detect all button
        self.autodetect_all_btn = QPushButton("Auto-detect All")
        self.autodetect_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        settings_grid.addWidget(self.autodetect_all_btn, 3, 3)

        # Create a wrapper group (for consistency, though not strictly needed)
        settings_wrapper = QGroupBox()
        settings_wrapper.setLayout(settings_grid)
        settings_wrapper.setFlat(True)  # No border

        # CSV-specific options
        self.csv_options_widget = QWidget()
        csv_options_layout = QGridLayout(self.csv_options_widget)
        csv_options_layout.setContentsMargins(20, 10, 0, 10)
        csv_options_layout.setColumnStretch(0, 1)

        # GT3X-specific options
        self.gt3x_options_widget = QWidget()
        gt3x_options_layout = QGridLayout(self.gt3x_options_widget)
        gt3x_options_layout.setContentsMargins(20, 10, 0, 10)

        gt3x_options_layout.addWidget(QLabel("GT3X Epoch Length (seconds):"), 0, 0)
        self.gt3x_epoch_length_spin = NoScrollSpinBox()
        self.gt3x_epoch_length_spin.setRange(1, 300)
        self.gt3x_epoch_length_spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.gt3x_epoch_length_spin.setToolTip("Epoch length for GT3X data processing")
        gt3x_options_layout.addWidget(self.gt3x_epoch_length_spin, 0, 1)

        gt3x_options_layout.addWidget(QLabel("Return Raw Data:"), 1, 0)
        self.gt3x_return_raw_check = QCheckBox()
        self.gt3x_return_raw_check.setToolTip("Return raw acceleration data instead of activity counts")
        gt3x_options_layout.addWidget(self.gt3x_return_raw_check, 1, 1)
        gt3x_options_layout.setColumnStretch(2, 1)

        return settings_wrapper, self.csv_options_widget, self.gt3x_options_widget

    def load_from_config(self) -> None:
        """Load current configuration into UI."""
        config = self.config_manager.config

        # Load device preset
        if self.device_preset_combo:
            for i in range(self.device_preset_combo.count()):
                if self.device_preset_combo.itemData(i) == config.device_preset:
                    self.device_preset_combo.setCurrentIndex(i)
                    break

        # Load epoch length
        if self.epoch_length_spin:
            self.epoch_length_spin.setValue(config.epoch_length)

        # Load skip rows
        if self.skip_rows_spin:
            self.skip_rows_spin.setValue(config.skip_rows)

        # Load GT3X settings
        if self.gt3x_epoch_length_spin:
            self.gt3x_epoch_length_spin.blockSignals(True)
            try:
                self.gt3x_epoch_length_spin.setValue(config.gt3x_epoch_length)
            finally:
                self.gt3x_epoch_length_spin.blockSignals(False)

        if self.gt3x_return_raw_check:
            self.gt3x_return_raw_check.blockSignals(True)
            try:
                self.gt3x_return_raw_check.setChecked(config.gt3x_return_raw)
            finally:
                self.gt3x_return_raw_check.blockSignals(False)

        # Update Configure Columns button state
        if self.configure_columns_btn:
            self.configure_columns_btn.setEnabled(config.device_preset == DevicePreset.GENERIC_CSV.value)

    def get_widgets(self) -> dict:
        """
        Get all widgets for external access.

        Returns:
            Dictionary of widget names to widgets

        """
        return {
            "data_source_combo": self.data_source_combo,
            "device_preset_combo": self.device_preset_combo,
            "epoch_length_spin": self.epoch_length_spin,
            "skip_rows_spin": self.skip_rows_spin,
            "device_autodetect_btn": self.device_autodetect_btn,
            "epoch_autodetect_btn": self.epoch_autodetect_btn,
            "skip_rows_autodetect_btn": self.skip_rows_autodetect_btn,
            "autodetect_all_btn": self.autodetect_all_btn,
            "configure_columns_btn": self.configure_columns_btn,
            "gt3x_epoch_length_spin": self.gt3x_epoch_length_spin,
            "gt3x_return_raw_check": self.gt3x_return_raw_check,
            "csv_options_widget": self.csv_options_widget,
            "gt3x_options_widget": self.gt3x_options_widget,
        }

    def update_data_source_visibility(self, loader_id: str) -> None:
        """
        Update visibility of data source specific option sections.

        Args:
            loader_id: The current data source loader ID

        """
        is_csv = loader_id == DataSourceType.CSV
        is_gt3x = loader_id == DataSourceType.GT3X

        if self.csv_options_widget:
            self.csv_options_widget.setVisible(is_csv)
        if self.gt3x_options_widget:
            self.gt3x_options_widget.setVisible(is_gt3x)

    def update_configure_button_state(self, device_preset: str) -> None:
        """
        Update the Configure Columns button enabled state.

        Args:
            device_preset: The current device preset value

        """
        if self.configure_columns_btn:
            self.configure_columns_btn.setEnabled(device_preset == DevicePreset.GENERIC_CSV.value)
