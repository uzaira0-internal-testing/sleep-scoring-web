"""
Data Paradigm Section Builder
Constructs the paradigm selection UI section.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGroupBox, QLabel, QSizePolicy, QVBoxLayout

from sleep_scoring_app.core.constants import (
    ParadigmInfoText,
    ParadigmStyle,
    ParadigmTooltip,
    SettingsSection,
    StudyDataParadigm,
)
from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QComboBox

    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class DataParadigmSectionBuilder:
    """Builder for the Data Paradigm configuration section."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings

        """
        self.config_manager = config_manager
        self.data_paradigm_combo: QComboBox | None = None
        self.paradigm_info_label: QLabel | None = None

    def build(self) -> QGroupBox:
        """
        Build the data paradigm selection section.

        Returns:
            QGroupBox containing the paradigm selection UI

        """
        group_box = QGroupBox(SettingsSection.DATA_PARADIGM)
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
                border: 3px solid #3498db;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 15px;
                background-color: #f8f9fa;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #2c3e50;
            }
        """)
        layout = QVBoxLayout(group_box)
        layout.setSpacing(15)

        # Description
        description_label = QLabel(
            "<b>Select the type of data files you will use for this study.</b><br>"
            "This is the <b>most important setting</b> and controls which file types you can import "
            "and which algorithms are available. Choose carefully based on your data source."
        )
        description_label.setWordWrap(True)
        description_label.setStyleSheet("QLabel { color: #2c3e50; font-size: 12px; margin-bottom: 10px; background: transparent; }")
        layout.addWidget(description_label)

        # Paradigm selection with prominent radio-button-style display
        paradigm_selection_layout = QVBoxLayout()
        paradigm_selection_layout.setSpacing(10)

        # Paradigm label
        paradigm_label = QLabel("Data Paradigm:")
        paradigm_label.setStyleSheet(ParadigmStyle.SECTION_TITLE)
        paradigm_selection_layout.addWidget(paradigm_label)

        # Combo box for paradigm selection
        self.data_paradigm_combo = NoScrollComboBox()
        self.data_paradigm_combo.setStyleSheet("""
            QComboBox {
                font-size: 12px;
                font-weight: bold;
                padding: 8px;
                border: 2px solid #3498db;
                border-radius: 4px;
                background-color: white;
                min-width: 300px;
            }
            QComboBox:hover {
                border: 2px solid #2980b9;
                background-color: #ecf0f1;
            }
            QComboBox::drop-down {
                border: none;
                width: 30px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 8px solid #3498db;
                margin-right: 8px;
            }
        """)

        # Populate paradigm options from enum
        for paradigm in StudyDataParadigm:
            self.data_paradigm_combo.addItem(paradigm.get_display_name(), paradigm.value)

        self.data_paradigm_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.data_paradigm_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.data_paradigm_combo.setToolTip(f"{ParadigmTooltip.COMBO_BOX}\n\n{ParadigmTooltip.EPOCH_BASED}\n\n{ParadigmTooltip.RAW_ACCELEROMETER}")
        paradigm_selection_layout.addWidget(self.data_paradigm_combo)

        layout.addLayout(paradigm_selection_layout)

        # Paradigm info label (dynamically updated based on selection)
        self.paradigm_info_label = QLabel()
        self.paradigm_info_label.setWordWrap(True)
        self.paradigm_info_label.setStyleSheet(ParadigmStyle.INFO_LABEL)
        self._update_paradigm_info_label()
        layout.addWidget(self.paradigm_info_label)

        # Add warning about paradigm changes
        warning_label = QLabel(
            "⚠️ <b>Important:</b> Changing the paradigm after importing data may require "
            "re-importing files to ensure compatibility with the selected paradigm."
        )
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet(ParadigmStyle.WARNING_BOX)
        layout.addWidget(warning_label)

        # Connect signal to update info label when paradigm changes
        self.data_paradigm_combo.currentIndexChanged.connect(self._update_paradigm_info_label)

        return group_box

    def get_combo_box(self) -> QComboBox:
        """
        Get the paradigm combo box widget.

        Returns:
            The data paradigm combo box

        """
        if self.data_paradigm_combo is None:
            msg = "Builder must be built before accessing combo box"
            raise RuntimeError(msg)
        return self.data_paradigm_combo

    def load_from_config(self) -> None:
        """Load the current paradigm from config."""
        if self.data_paradigm_combo is None:
            return

        config = self.config_manager.config
        if config is None:
            return

        # Find and set the paradigm in the combo box
        for i in range(self.data_paradigm_combo.count()):
            if self.data_paradigm_combo.itemData(i) == config.data_paradigm:
                self.data_paradigm_combo.setCurrentIndex(i)
                break

    def _get_current_paradigm(self) -> StudyDataParadigm:
        """Get the currently selected data paradigm."""
        if self.data_paradigm_combo is None:
            return StudyDataParadigm.get_default()

        paradigm_value = self.data_paradigm_combo.currentData()
        try:
            return StudyDataParadigm(paradigm_value)
        except ValueError:
            return StudyDataParadigm.get_default()

    def _update_paradigm_info_label(self) -> None:
        """Update the paradigm info label based on current selection."""
        if self.paradigm_info_label is None:
            return

        paradigm = self._get_current_paradigm()
        if paradigm == StudyDataParadigm.EPOCH_BASED:
            self.paradigm_info_label.setText(ParadigmInfoText.EPOCH_BASED_INFO)
        else:
            self.paradigm_info_label.setText(ParadigmInfoText.RAW_ACCELEROMETER_INFO)
