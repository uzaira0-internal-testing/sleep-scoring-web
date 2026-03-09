"""
Valid Values Section Builder
Constructs the valid groups and timepoints list management UI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from sleep_scoring_app.core.constants import SettingsSection

if TYPE_CHECKING:
    from sleep_scoring_app.ui.study_settings_tab import DragDropListWidget
    from sleep_scoring_app.ui.utils.config import ConfigManager

logger = logging.getLogger(__name__)


class ValidValuesSectionBuilder(QObject):
    """Builder for the valid groups and timepoints configuration section."""

    groups_changed = pyqtSignal(list)
    timepoints_changed = pyqtSignal(list)

    def __init__(self, config_manager: ConfigManager, drag_drop_list_class: type) -> None:
        """
        Initialize the builder.

        Args:
            config_manager: Configuration manager for accessing current settings
            drag_drop_list_class: The DragDropListWidget class to instantiate

        """
        super().__init__()
        self.config_manager = config_manager
        self.drag_drop_list_class = drag_drop_list_class

        # List widgets
        self.valid_groups_list: DragDropListWidget | None = None
        self.valid_timepoints_list: DragDropListWidget | None = None

        # Buttons
        self.add_group_button: QPushButton | None = None
        self.edit_group_button: QPushButton | None = None
        self.remove_group_button: QPushButton | None = None
        self.add_timepoint_button: QPushButton | None = None
        self.edit_timepoint_button: QPushButton | None = None
        self.remove_timepoint_button: QPushButton | None = None

    def build(self) -> QGroupBox:
        """
        Build the valid groups and timepoints section.

        Returns:
            QGroupBox containing the valid values UI

        """
        group_box = QGroupBox(SettingsSection.VALID_VALUES)
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
        layout = QHBoxLayout(group_box)
        layout.setSpacing(20)

        # Valid Groups Section
        groups_layout = self._create_groups_section()
        layout.addLayout(groups_layout)

        # Valid Timepoints Section
        timepoints_layout = self._create_timepoints_section()
        layout.addLayout(timepoints_layout)

        return group_box

    def _create_groups_section(self) -> QVBoxLayout:
        """Create the valid groups section."""
        groups_layout = QVBoxLayout()
        groups_label = QLabel("<b>Valid Groups</b>")
        groups_label.setStyleSheet("QLabel { color: #2c3e50; margin-bottom: 5px; }")
        groups_layout.addWidget(groups_label)

        # Create help text
        groups_help = QLabel("Drag to reorder -> Double-click to edit")
        groups_help.setStyleSheet("QLabel { color: #7f8c8d; font-size: 11px; font-style: italic; }")
        groups_layout.addWidget(groups_help)

        self.valid_groups_list = self.drag_drop_list_class()
        self.valid_groups_list.setMaximumHeight(120)
        self.valid_groups_list.setMinimumHeight(120)
        self.valid_groups_list.setToolTip(
            "Groups that are considered valid for this study.\n"
            "-> Drag items to reorder\n"
            "-> Double-click to edit\n"
            "-> Used for validation and dropdown options"
        )
        self.valid_groups_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #3498db;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #ecf0f1;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e8f4fd;
            }
        """)
        groups_layout.addWidget(self.valid_groups_list)

        # Groups action buttons
        groups_buttons_layout = self._create_groups_buttons()
        groups_layout.addLayout(groups_buttons_layout)

        return groups_layout

    def _create_groups_buttons(self) -> QHBoxLayout:
        """Create action buttons for groups list."""
        groups_buttons_layout = QHBoxLayout()

        self.add_group_button = QPushButton("Add")
        self.add_group_button.clicked.connect(self._add_group)
        self.add_group_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
            QPushButton:pressed {
                background-color: #229954;
            }
        """)

        self.edit_group_button = QPushButton("Edit")
        self.edit_group_button.clicked.connect(self._edit_selected_group)
        self.edit_group_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5dade2;
            }
            QPushButton:pressed {
                background-color: #2980b9;
            }
        """)

        self.remove_group_button = QPushButton("Remove")
        self.remove_group_button.clicked.connect(self._remove_group)
        self.remove_group_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ec7063;
            }
            QPushButton:pressed {
                background-color: #c0392b;
            }
        """)

        groups_buttons_layout.addWidget(self.add_group_button)
        groups_buttons_layout.addWidget(self.edit_group_button)
        groups_buttons_layout.addWidget(self.remove_group_button)
        groups_buttons_layout.addStretch()

        return groups_buttons_layout

    def _create_timepoints_section(self) -> QVBoxLayout:
        """Create the valid timepoints section."""
        timepoints_layout = QVBoxLayout()
        timepoints_label = QLabel("<b>Valid Timepoints</b>")
        timepoints_label.setStyleSheet("QLabel { color: #2c3e50; margin-bottom: 5px; }")
        timepoints_layout.addWidget(timepoints_label)

        # Create help text
        timepoints_help = QLabel("Drag to reorder -> Double-click to edit")
        timepoints_help.setStyleSheet("QLabel { color: #7f8c8d; font-size: 11px; font-style: italic; }")
        timepoints_layout.addWidget(timepoints_help)

        self.valid_timepoints_list = self.drag_drop_list_class()
        self.valid_timepoints_list.setMaximumHeight(120)
        self.valid_timepoints_list.setMinimumHeight(120)
        self.valid_timepoints_list.setToolTip(
            "Timepoints that are considered valid for this study.\n"
            "-> Drag items to reorder\n"
            "-> Double-click to edit\n"
            "-> Used for validation and dropdown options"
        )
        self.valid_timepoints_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #bdc3c7;
                border-radius: 4px;
                background-color: white;
                selection-background-color: #3498db;
                padding: 5px;
            }
            QListWidget::item {
                padding: 5px;
                border-bottom: 1px solid #ecf0f1;
            }
            QListWidget::item:selected {
                background-color: #3498db;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e8f4fd;
            }
        """)
        timepoints_layout.addWidget(self.valid_timepoints_list)

        # Timepoints action buttons
        timepoints_buttons_layout = self._create_timepoints_buttons()
        timepoints_layout.addLayout(timepoints_buttons_layout)

        return timepoints_layout

    def _create_timepoints_buttons(self) -> QHBoxLayout:
        """Create action buttons for timepoints list."""
        timepoints_buttons_layout = QHBoxLayout()

        self.add_timepoint_button = QPushButton("Add")
        self.add_timepoint_button.clicked.connect(self._add_timepoint)
        self.add_timepoint_button.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #2ecc71;
            }
            QPushButton:pressed {
                background-color: #229954;
            }
        """)

        self.edit_timepoint_button = QPushButton("Edit")
        self.edit_timepoint_button.clicked.connect(self._edit_selected_timepoint)
        self.edit_timepoint_button.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5dade2;
            }
            QPushButton:pressed {
                background-color: #2980b9;
            }
        """)

        self.remove_timepoint_button = QPushButton("Remove")
        self.remove_timepoint_button.clicked.connect(self._remove_timepoint)
        self.remove_timepoint_button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ec7063;
            }
            QPushButton:pressed {
                background-color: #c0392b;
            }
        """)

        timepoints_buttons_layout.addWidget(self.add_timepoint_button)
        timepoints_buttons_layout.addWidget(self.edit_timepoint_button)
        timepoints_buttons_layout.addWidget(self.remove_timepoint_button)
        timepoints_buttons_layout.addStretch()

        return timepoints_buttons_layout

    def get_lists(self) -> tuple[DragDropListWidget, DragDropListWidget]:
        """
        Get the list widgets.

        Returns:
            Tuple of (valid_groups_list, valid_timepoints_list)

        """
        if self.valid_groups_list is None or self.valid_timepoints_list is None:
            msg = "Builder must be built before accessing lists"
            raise RuntimeError(msg)
        return self.valid_groups_list, self.valid_timepoints_list

    def load_from_config(self) -> None:
        """Load valid values from config."""
        config = self.config_manager.config
        if config is None or self.valid_groups_list is None or self.valid_timepoints_list is None:
            return

        # Load valid groups
        self.valid_groups_list.clear()
        for group in config.study_valid_groups:
            self.valid_groups_list.addItem(group)

        # Load valid timepoints
        self.valid_timepoints_list.clear()
        for timepoint in config.study_valid_timepoints:
            self.valid_timepoints_list.addItem(timepoint)

    # Group management methods
    def _add_group(self) -> None:
        """Add a new group via dialog."""
        if self.valid_groups_list is None:
            return

        text, ok = QInputDialog.getText(
            None,  # type: ignore[arg-type]
            "Add Group",
            "Enter group name:",
        )

        if ok and text.strip():
            normalized = text.strip().upper()
            if self.valid_groups_list.add_item_with_validation(normalized):
                # add_item_with_validation already emits items_changed signal
                logger.debug("Added group: %s", normalized)
            else:
                QMessageBox.information(None, "Duplicate Group", f"Group '{normalized}' already exists.")  # type: ignore[arg-type]

    def _edit_selected_group(self) -> None:
        """Edit the selected group via inline editing."""
        if self.valid_groups_list is None:
            return

        current_item = self.valid_groups_list.currentItem()
        if current_item:
            self.valid_groups_list._edit_item(current_item)

    def _remove_group(self) -> None:
        """Remove the selected group."""
        if self.valid_groups_list is None:
            return

        current_row = self.valid_groups_list.currentRow()
        if current_row >= 0:
            item = self.valid_groups_list.takeItem(current_row)
            # Emit list's items_changed signal (connected in study_settings_tab)
            # takeItem() doesn't trigger model signals, so we emit manually
            self.valid_groups_list.items_changed.emit()
            logger.debug("Removed group: %s", item.text() if item else "Unknown")

    # Timepoint management methods
    def _add_timepoint(self) -> None:
        """Add a new timepoint via dialog."""
        if self.valid_timepoints_list is None:
            return

        text, ok = QInputDialog.getText(
            None,  # type: ignore[arg-type]
            "Add Timepoint",
            "Enter timepoint name:",
        )

        if ok and text.strip():
            normalized = text.strip().upper()
            if self.valid_timepoints_list.add_item_with_validation(normalized):
                # add_item_with_validation already emits items_changed signal
                logger.debug("Added timepoint: %s", normalized)
            else:
                QMessageBox.information(None, "Duplicate Timepoint", f"Timepoint '{normalized}' already exists.")  # type: ignore[arg-type]

    def _edit_selected_timepoint(self) -> None:
        """Edit the selected timepoint via inline editing."""
        if self.valid_timepoints_list is None:
            return

        current_item = self.valid_timepoints_list.currentItem()
        if current_item:
            self.valid_timepoints_list._edit_item(current_item)

    def _remove_timepoint(self) -> None:
        """Remove the selected timepoint."""
        if self.valid_timepoints_list is None:
            return

        current_row = self.valid_timepoints_list.currentRow()
        if current_row >= 0:
            item = self.valid_timepoints_list.takeItem(current_row)
            # Emit list's items_changed signal (connected in study_settings_tab)
            # takeItem() doesn't trigger model signals, so we emit manually
            self.valid_timepoints_list.items_changed.emit()
            logger.debug("Removed timepoint: %s", item.text() if item else "Unknown")
