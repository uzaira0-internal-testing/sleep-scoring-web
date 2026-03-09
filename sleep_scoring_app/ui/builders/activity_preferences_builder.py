"""
Activity Preferences Builder
Constructs the UI for activity column preferences.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QGroupBox, QLabel, QVBoxLayout

from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QComboBox

    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class ActivityPreferencesBuilder:
    """Builder for activity column preferences UI."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings

        """
        self.config_manager = config_manager
        self.preferred_activity_combo: QComboBox | None = None
        self.choi_column_combo: QComboBox | None = None

    def build(self) -> QGroupBox:
        """
        Build the activity preferences section.

        Returns:
            QGroupBox containing the activity preferences UI

        """
        group_box = QGroupBox("Activity Column Preferences")
        group_box.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #cccccc;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)
        layout = QVBoxLayout(group_box)

        # Description
        description = QLabel(
            "Select which activity columns to use for different algorithms. These preferences are applied when loading data from files."
        )
        description.setWordWrap(True)
        description.setStyleSheet("QLabel { color: #666; font-size: 11px; margin-bottom: 10px; }")
        layout.addWidget(description)

        # Preferred activity column
        layout.addWidget(QLabel("Preferred Activity Column:"))
        self.preferred_activity_combo = NoScrollComboBox()
        self.preferred_activity_combo.setToolTip(
            "Primary activity column to use for sleep scoring algorithms. Typically Vector Magnitude or Y-Axis depending on algorithm."
        )
        layout.addWidget(self.preferred_activity_combo)

        # Choi algorithm column
        layout.addWidget(QLabel("Choi Algorithm Column:"))
        self.choi_column_combo = NoScrollComboBox()
        self.choi_column_combo.setToolTip("Activity column to use for Choi nonwear detection. Can be Vector Magnitude, X-Axis, Y-Axis, or Z-Axis.")
        layout.addWidget(self.choi_column_combo)

        return group_box

    def load_from_config(self) -> None:
        """Load current preferences from config."""
        config = self.config_manager.config

        if self.preferred_activity_combo:
            if config.preferred_activity_column:
                self.preferred_activity_combo.setCurrentText(config.preferred_activity_column)

        if self.choi_column_combo:
            if config.choi_axis:
                self.choi_column_combo.setCurrentText(config.choi_axis)

    def update_available_columns(self, columns: list[str]) -> None:
        """
        Update the available columns in the dropdowns.

        Args:
            columns: List of available activity column names

        """
        if not self.preferred_activity_combo or not self.choi_column_combo:
            return

        # Save current selections
        current_preferred = self.preferred_activity_combo.currentText()
        current_choi = self.choi_column_combo.currentText()

        # Update preferred activity combo
        self.preferred_activity_combo.clear()
        self.preferred_activity_combo.addItems(columns)

        # Restore selection if still available
        if current_preferred in columns:
            self.preferred_activity_combo.setCurrentText(current_preferred)

        # Update Choi column combo
        self.choi_column_combo.clear()
        self.choi_column_combo.addItems(columns)

        # Restore selection if still available
        if current_choi in columns:
            self.choi_column_combo.setCurrentText(current_choi)

    def get_preferences(self) -> dict:
        """
        Get current preferences.

        Returns:
            Dictionary of preference settings

        """
        return {
            "preferred_activity_column": self.preferred_activity_combo.currentText() if self.preferred_activity_combo else "",
            "choi_column": self.choi_column_combo.currentText() if self.choi_column_combo else "",
        }

    def set_preferences(self, preferences: dict) -> None:
        """
        Set preferences from a dictionary.

        Args:
            preferences: Dictionary of preference settings

        """
        if self.preferred_activity_combo and "preferred_activity_column" in preferences:
            self.preferred_activity_combo.setCurrentText(preferences["preferred_activity_column"])

        if self.choi_column_combo and "choi_column" in preferences:
            self.choi_column_combo.setCurrentText(preferences["choi_column"])

    def get_widgets(self) -> dict:
        """
        Get all widgets for external access.

        Returns:
            Dictionary of widget names to widgets

        """
        return {
            "preferred_activity_combo": self.preferred_activity_combo,
            "choi_column_combo": self.choi_column_combo,
        }
