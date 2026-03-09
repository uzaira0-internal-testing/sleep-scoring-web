"""
Pattern Section Builder
Constructs the regex pattern configuration and live testing UI sections.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
)

from sleep_scoring_app.core.constants import SettingsSection

if TYPE_CHECKING:
    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class PatternSectionBuilder:
    """Builder for regex pattern configuration and live testing sections."""

    # Signals for validation updates
    patterns_changed = pyqtSignal()

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings

        """
        self.config_manager = config_manager

        # Pattern edit widgets
        self.id_pattern_edit: QLineEdit | None = None
        self.timepoint_pattern_edit: QLineEdit | None = None
        self.group_pattern_edit: QLineEdit | None = None

        # Testing widgets
        self.test_id_input: QLineEdit | None = None
        self.test_results_display: QTextEdit | None = None

        # Validation timer (for UI validation feedback only)
        self.validation_timer = QTimer()
        self.validation_timer.setSingleShot(True)

    def build_regex_patterns_section(self) -> QGroupBox:
        """
        Build the regex patterns configuration section.

        Returns:
            QGroupBox containing the pattern configuration UI

        """
        group_box = QGroupBox(SettingsSection.PARTICIPANT_IDENTIFICATION)
        layout = QVBoxLayout(group_box)

        # Description
        description_label = QLabel(
            "Configure regex patterns used to extract participant IDs, timepoints, and groups from filenames. "
            "Patterns are validated in real-time with visual feedback."
        )
        description_label.setWordWrap(True)
        description_label.setStyleSheet("QLabel { color: #666; font-style: italic; margin-bottom: 10px; }")
        layout.addWidget(description_label)

        # Create form layout for regex patterns
        form_layout = QFormLayout()
        form_layout.setHorizontalSpacing(15)
        form_layout.setVerticalSpacing(10)

        # ID Regex Pattern
        self.id_pattern_edit = QLineEdit()
        self.id_pattern_edit.setPlaceholderText("Enter regex pattern to extract participant IDs")
        self.id_pattern_edit.setToolTip(
            "Regex pattern to match participant IDs in filenames.\nExample: r'^(\\d{4,})[_-]' matches '4000_data.csv' and extracts '4000'"
        )
        self.id_pattern_edit.setMaximumWidth(400)
        self.id_pattern_edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        id_label = QLabel("ID Pattern:")
        id_label.setToolTip("Primary regex pattern for extracting participant IDs")
        form_layout.addRow(id_label, self.id_pattern_edit)

        # Timepoint Regex Pattern
        self.timepoint_pattern_edit = QLineEdit()
        self.timepoint_pattern_edit.setPlaceholderText("Enter regex pattern to extract timepoint codes")
        self.timepoint_pattern_edit.setToolTip(
            "Regex pattern to match timepoints in filenames.\nExample: r'([A-Z0-9]+)' matches 'BO', 'P1', 'P2' in filenames"
        )
        self.timepoint_pattern_edit.setMaximumWidth(400)
        self.timepoint_pattern_edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        timepoint_label = QLabel("Timepoint Pattern:")
        timepoint_label.setToolTip("Regex pattern for extracting timepoint codes")
        form_layout.addRow(timepoint_label, self.timepoint_pattern_edit)

        # Group Regex Pattern
        self.group_pattern_edit = QLineEdit()
        self.group_pattern_edit.setPlaceholderText("Enter regex pattern to extract group identifiers")
        self.group_pattern_edit.setToolTip("Regex pattern to match groups in filenames.\nExample: r'g[123]' matches 'g1', 'g2', 'g3' in filenames")
        self.group_pattern_edit.setMaximumWidth(400)
        self.group_pattern_edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        group_label = QLabel("Group Pattern:")
        group_label.setToolTip("Regex pattern for extracting group identifiers")
        form_layout.addRow(group_label, self.group_pattern_edit)

        layout.addLayout(form_layout)

        return group_box

    def build_id_testing_section(self) -> QGroupBox:
        """
        Build the live ID testing section.

        Returns:
            QGroupBox containing the ID testing UI

        """
        group_box = QGroupBox(SettingsSection.LIVE_ID_TESTING)
        layout = QVBoxLayout(group_box)

        # Description
        description_label = QLabel(
            "Test your regex patterns by entering a participant ID or filename. See real-time feedback about pattern matching and validation."
        )
        description_label.setWordWrap(True)
        description_label.setStyleSheet("QLabel { color: #666; font-style: italic; margin-bottom: 10px; }")
        layout.addWidget(description_label)

        # Input section
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Test ID:"))

        self.test_id_input = QLineEdit()
        self.test_id_input.setPlaceholderText("Enter ID or filename to test patterns...")
        input_layout.addWidget(self.test_id_input)

        layout.addLayout(input_layout)

        # Results display
        self.test_results_display = QTextEdit()
        self.test_results_display.setMaximumHeight(120)
        self.test_results_display.setReadOnly(True)
        self.test_results_display.setStyleSheet("""
            QTextEdit {
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background-color: #f8f9fa;
                font-family: monospace;
                font-size: 12px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.test_results_display)

        # Initialize with empty state
        self.test_results_display.setHtml("""
            <div style="color: #666; font-style: italic;">
                Enter an ID or filename above to see extraction results...
            </div>
        """)

        return group_box

    def get_pattern_edits(self) -> tuple[QLineEdit, QLineEdit, QLineEdit]:
        """
        Get the pattern edit widgets.

        Returns:
            Tuple of (id_pattern_edit, timepoint_pattern_edit, group_pattern_edit)

        """
        if self.id_pattern_edit is None or self.timepoint_pattern_edit is None or self.group_pattern_edit is None:
            msg = "Builder must be built before accessing pattern edits"
            raise RuntimeError(msg)
        return self.id_pattern_edit, self.timepoint_pattern_edit, self.group_pattern_edit

    def get_test_widgets(self) -> tuple[QLineEdit, QTextEdit]:
        """
        Get the test input and results widgets.

        Returns:
            Tuple of (test_id_input, test_results_display)

        """
        if self.test_id_input is None or self.test_results_display is None:
            msg = "Builder must be built before accessing test widgets"
            raise RuntimeError(msg)
        return self.test_id_input, self.test_results_display

    def load_from_config(self) -> None:
        """Load patterns from config."""
        config = self.config_manager.config
        if config is None:
            return

        if self.id_pattern_edit is not None and config.study_participant_id_patterns:
            self.id_pattern_edit.setText(config.study_participant_id_patterns[0])

        if self.timepoint_pattern_edit is not None:
            self.timepoint_pattern_edit.setText(config.study_timepoint_pattern)

        if self.group_pattern_edit is not None:
            self.group_pattern_edit.setText(config.study_group_pattern)

    def set_default_patterns(self) -> None:
        """Reset patterns to default values."""
        if self.id_pattern_edit is not None:
            self.id_pattern_edit.setText(r"^(\d{4,})[_-]")

        if self.timepoint_pattern_edit is not None:
            self.timepoint_pattern_edit.setText(r"([A-Z0-9]+)")

        if self.group_pattern_edit is not None:
            self.group_pattern_edit.setText(r"g[123]")
