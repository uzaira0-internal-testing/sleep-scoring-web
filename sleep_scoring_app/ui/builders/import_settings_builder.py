"""
Import Settings Builder
Constructs the UI for import-related settings and controls.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
)

from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollSpinBox

if TYPE_CHECKING:
    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class ImportSettingsBuilder:
    """Builder for import settings UI."""

    def __init__(self, config_manager: ConfigManager) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings

        """
        self.config_manager = config_manager

        # Settings widgets
        self.import_mode_new_only: QCheckBox | None = None
        self.show_progress_details: QCheckBox | None = None
        self.file_size_limit_spin: NoScrollSpinBox | None = None

        # Progress widgets
        self.progress_label: QLabel | None = None
        self.progress_bar: QProgressBar | None = None

    def build(self) -> QGroupBox:
        """
        Build the import settings section.

        Returns:
            QGroupBox containing the import settings UI

        """
        group_box = QGroupBox("Import Settings")
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

        # Import mode
        self.import_mode_new_only = QCheckBox("Import new files only (skip duplicates)")
        self.import_mode_new_only.setToolTip(
            "When checked, files that have already been imported will be skipped. When unchecked, all files will be re-imported."
        )
        layout.addWidget(self.import_mode_new_only)

        # Progress details
        self.show_progress_details = QCheckBox("Show detailed progress information")
        self.show_progress_details.setToolTip("Display detailed file-by-file progress during import")
        layout.addWidget(self.show_progress_details)

        # File size limit
        size_limit_layout = QHBoxLayout()
        size_limit_layout.addWidget(QLabel("Max file size (MB):"))
        self.file_size_limit_spin = NoScrollSpinBox()
        self.file_size_limit_spin.setRange(1, 1000)
        self.file_size_limit_spin.setValue(100)
        self.file_size_limit_spin.setToolTip("Skip files larger than this size (in megabytes)")
        self.file_size_limit_spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        size_limit_layout.addWidget(self.file_size_limit_spin)
        size_limit_layout.addStretch()
        layout.addLayout(size_limit_layout)

        # Progress display section
        progress_section = self._create_progress_section()
        layout.addWidget(progress_section)

        return group_box

    def _create_progress_section(self) -> QGroupBox:
        """Create the progress display section."""
        progress_group = QGroupBox("Import Progress")
        progress_layout = QVBoxLayout(progress_group)

        # Progress label
        self.progress_label = QLabel("Ready to import")
        self.progress_label.setVisible(False)
        progress_layout.addWidget(self.progress_label)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setMinimumHeight(20)
        self.progress_bar.setVisible(False)
        progress_layout.addWidget(self.progress_bar)

        return progress_group

    def load_from_config(self) -> None:
        """Load current settings from config."""
        config = self.config_manager.config

        if self.import_mode_new_only:
            self.import_mode_new_only.setChecked(config.import_new_files_only)

        if self.show_progress_details:
            self.show_progress_details.setChecked(config.show_import_progress_details)

        if self.file_size_limit_spin:
            self.file_size_limit_spin.setValue(config.max_import_file_size_mb)

    def get_settings(self) -> dict:
        """
        Get current import settings.

        Returns:
            Dictionary of import settings

        """
        return {
            "import_new_only": self.import_mode_new_only.isChecked() if self.import_mode_new_only else True,
            "show_progress_details": self.show_progress_details.isChecked() if self.show_progress_details else False,
            "max_file_size_mb": self.file_size_limit_spin.value() if self.file_size_limit_spin else 100,
        }

    def set_settings(self, settings: dict) -> None:
        """
        Set import settings from a dictionary.

        Args:
            settings: Dictionary of import settings

        """
        if self.import_mode_new_only and "import_new_only" in settings:
            self.import_mode_new_only.setChecked(settings["import_new_only"])

        if self.show_progress_details and "show_progress_details" in settings:
            self.show_progress_details.setChecked(settings["show_progress_details"])

        if self.file_size_limit_spin and "max_file_size_mb" in settings:
            self.file_size_limit_spin.setValue(settings["max_file_size_mb"])

    def show_progress(self, message: str, current: int = 0, total: int = 100) -> None:
        """
        Show import progress.

        Args:
            message: Progress message to display
            current: Current progress value
            total: Total progress value

        """
        if self.progress_label:
            self.progress_label.setText(message)
            self.progress_label.setVisible(True)

        if self.progress_bar:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(current)
            self.progress_bar.setVisible(True)

    def hide_progress(self) -> None:
        """Hide the progress display."""
        if self.progress_label:
            self.progress_label.setVisible(False)

        if self.progress_bar:
            self.progress_bar.setVisible(False)

    def get_widgets(self) -> dict:
        """
        Get all widgets for external access.

        Returns:
            Dictionary of widget names to widgets

        """
        return {
            "import_mode_new_only": self.import_mode_new_only,
            "show_progress_details": self.show_progress_details,
            "file_size_limit_spin": self.file_size_limit_spin,
            "progress_label": self.progress_label,
            "progress_bar": self.progress_bar,
        }
