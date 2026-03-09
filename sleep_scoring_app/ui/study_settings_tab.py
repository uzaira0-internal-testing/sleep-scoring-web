#!/usr/bin/env python3
"""
Study Settings Tab Component
Handles study configuration parameters like groups, timepoints, and defaults.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTime, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import (
    NonwearAlgorithm,
    ParadigmInfoText,
    ParadigmWarning,
    SettingsSection,
    StudyDataParadigm,
)
from sleep_scoring_app.services.algorithm_service import get_algorithm_service
from sleep_scoring_app.ui.builders import (
    AlgorithmSectionBuilder,
    DataParadigmSectionBuilder,
    PatternSectionBuilder,
    ValidValuesSectionBuilder,
)
from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import (
        AppStateInterface,
        MarkerOperationsInterface,
        NavigationInterface,
        ServiceContainer,
    )
    from sleep_scoring_app.ui.store import UIState, UIStore

logger = logging.getLogger(__name__)


class DragDropListWidget(QListWidget):
    """Custom list widget with drag-and-drop reordering and inline editing."""

    items_changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)

        # Enable inline editing on double-click
        self.itemDoubleClicked.connect(self._edit_item)

        # Track changes for validation and auto-save
        if (model := self.model()) is not None:
            model.rowsMoved.connect(self.items_changed.emit)
            model.rowsInserted.connect(self.items_changed.emit)
            model.rowsRemoved.connect(self.items_changed.emit)

    def _edit_item(self, item: QListWidgetItem) -> None:
        """Handle double-click to edit list item."""
        text, ok = QInputDialog.getText(
            self,
            "Edit Item",
            "Update item text:",
            text=item.text(),
        )
        if ok and text.strip():
            item.setText(text.strip().upper())
            self.items_changed.emit()

    def add_item_with_validation(self, text: str) -> bool:
        """Add a new item to the list if it doesn't already exist."""
        # Check for duplicates (case-insensitive)
        items = self.get_all_items()
        if text.upper() in [i.upper() for i in items]:
            return False

        self.addItem(text.upper())
        self.items_changed.emit()
        return True

    def get_all_items(self) -> list[str]:
        """Get all items in the list as a list of strings."""
        result = []
        for i in range(self.count()):
            if (item := self.item(i)) is not None:
                result.append(item.text())
        return result


class StudySettingsTab(QWidget):
    """Study Settings Tab for configuring study parameters."""

    # Signals for when groups/timepoints lists change (for real-time dropdown updates)
    groups_changed = pyqtSignal(list)
    timepoints_changed = pyqtSignal(list)

    # Signal for study setting changes: (field_name, value)
    # Connector dispatches to store on behalf of this widget
    studySettingChanged = pyqtSignal(str, object)

    def __init__(
        self,
        store: UIStore,
        navigation: NavigationInterface,
        marker_ops: MarkerOperationsInterface,
        app_state: AppStateInterface,
        services: ServiceContainer,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.navigation = navigation
        self.marker_ops = marker_ops
        self.app_state = app_state
        self.services = services
        # Keep internal reference for logic
        self.parent_logic = navigation

        # Initialize builders using injected services
        self.paradigm_builder = DataParadigmSectionBuilder(services.config_manager)
        self.pattern_builder = PatternSectionBuilder(services.config_manager)
        self.valid_values_builder = ValidValuesSectionBuilder(services.config_manager, DragDropListWidget)
        self.algorithm_builder = AlgorithmSectionBuilder(services.config_manager)

        self.setup_ui()
        self._connect_signals()

    def setup_ui(self) -> None:
        """Create the study settings tab UI."""
        logger.debug("=== StudySettingsTab.setup_ui() START ===")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area with always-visible scrollbars
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        # Create content widget that will be scrollable
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)

        # Add explanation header
        header_label = QLabel(
            "<b>Study Configuration</b><br>"
            "Configure study parameters such as data paradigm, default groups, timepoints, valid values, and "
            "regex patterns for participant information extraction. These settings affect how "
            "participant information is extracted and displayed.",
        )
        header_label.setWordWrap(True)
        header_label.setStyleSheet("QLabel { background-color: #f0f0f0; padding: 10px; border-radius: 5px; }")
        content_layout.addWidget(header_label)

        # Data Paradigm Section (TOP PRIORITY - First thing users see)
        paradigm_group = self.paradigm_builder.build()
        self.data_paradigm_combo = self.paradigm_builder.get_combo_box()
        self.paradigm_info_label = self.paradigm_builder.paradigm_info_label
        content_layout.addWidget(paradigm_group)

        # Regex Patterns Section
        regex_patterns_group = self.pattern_builder.build_regex_patterns_section()
        (
            self.id_pattern_edit,
            self.timepoint_pattern_edit,
            self.group_pattern_edit,
        ) = self.pattern_builder.get_pattern_edits()
        self.validation_timer = self.pattern_builder.validation_timer
        content_layout.addWidget(regex_patterns_group)

        # Live ID Testing Section
        id_testing_group = self.pattern_builder.build_id_testing_section()
        self.test_id_input, self.test_results_display = self.pattern_builder.get_test_widgets()
        content_layout.addWidget(id_testing_group)

        # Study Parameters Section (Unknown Value Placeholder only)
        study_params_group = self._create_study_parameters_section()
        content_layout.addWidget(study_params_group)

        # Valid Groups/Timepoints Section
        valid_values_group = self.valid_values_builder.build()
        self.valid_groups_list, self.valid_timepoints_list = self.valid_values_builder.get_lists()
        content_layout.addWidget(valid_values_group)

        # Default Selection Section
        default_selection_group = self._create_default_selection_section()
        content_layout.addWidget(default_selection_group)

        # Algorithm Configuration Section
        algorithm_config_group = self.algorithm_builder.build()
        (
            self.sleep_algorithm_combo,
            self.sleep_period_detector_combo,
            self.nonwear_algorithm_combo,
            self.choi_axis_combo,
        ) = self.algorithm_builder.get_combo_boxes()
        self.night_start_time, self.night_end_time = self.algorithm_builder.get_time_edits()
        self.choi_axis_widget = self.algorithm_builder.choi_axis_widget
        logger.info(
            "=== Algorithm section built: choi_axis_widget=%s, choi_axis_combo=%s ===",
            self.choi_axis_widget,
            self.choi_axis_combo,
        )
        content_layout.addWidget(algorithm_config_group)

        # Connect algorithm signals to auto-save
        self.data_paradigm_combo.currentIndexChanged.connect(self._on_data_paradigm_changed)
        self.sleep_algorithm_combo.currentIndexChanged.connect(self._on_sleep_algorithm_changed)
        self.sleep_period_detector_combo.currentIndexChanged.connect(self._on_sleep_period_detector_changed)
        self.night_start_time.timeChanged.connect(self._on_night_hours_changed)
        self.night_end_time.timeChanged.connect(self._on_night_hours_changed)
        self.nonwear_algorithm_combo.currentIndexChanged.connect(self._on_nonwear_algorithm_changed)
        self.choi_axis_combo.currentIndexChanged.connect(self._on_nonwear_axis_changed)

        # Action buttons
        buttons_layout = self._create_action_buttons()
        content_layout.addLayout(buttons_layout)

        content_layout.addStretch()

        # Set the content widget in the scroll area
        scroll_area.setWidget(content_widget)

        # Add scroll area to main layout
        layout.addWidget(scroll_area)

        # Load initial settings from store
        self._load_settings_from_state(self.store.state)

    def _load_settings_from_state(self, state: UIState) -> None:
        """
        Load UI components from the provided state.
        This is the SOLE method for updating the UI from the store.
        """
        logger.debug("STUDY SETTINGS: Loading UI from state")

        # Block signals to prevent dispatch-on-load feedback loops
        self._block_all_signals(True)
        try:
            # Set unknown value (only update if different to preserve cursor position)
            if self.unknown_value_edit.text() != state.study_unknown_value:
                self.unknown_value_edit.setText(state.study_unknown_value)

            # Load valid groups
            self.valid_groups_list.clear()
            for group in state.study_valid_groups:
                self.valid_groups_list.addItem(group)

            # Load valid timepoints
            self.valid_timepoints_list.clear()
            for timepoint in state.study_valid_timepoints:
                self.valid_timepoints_list.addItem(timepoint)

            # Update default dropdowns after loading the lists
            self._update_group_dropdown()
            self._update_timepoint_dropdown()

            # Set default group selection
            current_group = state.study_default_group
            if current_group:
                group_index = self.default_group_combo.findText(current_group)
                if group_index >= 0:
                    self.default_group_combo.setCurrentIndex(group_index)

            # Set default timepoint selection
            current_timepoint = state.study_default_timepoint
            if current_timepoint:
                timepoint_index = self.default_timepoint_combo.findText(current_timepoint)
                if timepoint_index >= 0:
                    self.default_timepoint_combo.setCurrentIndex(timepoint_index)

            # Load regex patterns (only update if different to preserve cursor position)
            if state.study_participant_id_patterns:
                new_id_pattern = state.study_participant_id_patterns[0]
                if self.id_pattern_edit.text() != new_id_pattern:
                    self.id_pattern_edit.setText(new_id_pattern)

            if self.timepoint_pattern_edit.text() != state.study_timepoint_pattern:
                self.timepoint_pattern_edit.setText(state.study_timepoint_pattern)
            if self.group_pattern_edit.text() != state.study_group_pattern:
                self.group_pattern_edit.setText(state.study_group_pattern)

            # Validate all patterns after loading
            self._validate_all_patterns()

            # Load algorithm configuration
            if self.data_paradigm_combo is not None:
                current_paradigm = state.data_paradigm
                for i in range(self.data_paradigm_combo.count()):
                    if self.data_paradigm_combo.itemData(i) == current_paradigm:
                        self.data_paradigm_combo.setCurrentIndex(i)
                        break

                self._update_paradigm_info_label()
                self._populate_algorithm_combo()
                self._populate_nonwear_algorithm_combo()
                self._populate_sleep_period_detector_combo()

            # Load sleep algorithm selection
            if self.sleep_algorithm_combo is not None:
                current_algo_id = state.sleep_algorithm_id
                for i in range(self.sleep_algorithm_combo.count()):
                    if self.sleep_algorithm_combo.itemData(i) == current_algo_id:
                        self.sleep_algorithm_combo.setCurrentIndex(i)
                        break

            # Load onset/offset rule selection
            if self.sleep_period_detector_combo is not None:
                current_rule_id = state.onset_offset_rule_id
                for i in range(self.sleep_period_detector_combo.count()):
                    if self.sleep_period_detector_combo.itemData(i) == current_rule_id:
                        self.sleep_period_detector_combo.setCurrentIndex(i)
                        break

            # Load nonwear algorithm selection
            if self.nonwear_algorithm_combo is not None:
                current_nonwear_id = state.nonwear_algorithm_id
                for i in range(self.nonwear_algorithm_combo.count()):
                    if self.nonwear_algorithm_combo.itemData(i) == current_nonwear_id:
                        self.nonwear_algorithm_combo.setCurrentIndex(i)
                        break

                # Use the COMBO's actual selected value for visibility
                # (state value might be incompatible with current paradigm)
                actual_selected = self.nonwear_algorithm_combo.currentData()
                if actual_selected:
                    self._update_choi_axis_visibility(actual_selected)
                    # If state value differs from combo value (paradigm mismatch),
                    # update the state to match the combo's valid selection
                    actual_str = str(actual_selected)
                    if actual_str != current_nonwear_id:
                        logger.warning(
                            "State nonwear_algorithm_id (%r) incompatible with paradigm, updating to combo value: %r",
                            current_nonwear_id,
                            actual_str,
                        )
                        self.studySettingChanged.emit("nonwear_algorithm_id", actual_str)

            # Load night hours
            self.night_start_time.setTime(QTime(state.night_start_hour, 0))
            self.night_end_time.setTime(QTime(state.night_end_hour, 0))

            # Load Choi axis setting
            if self.choi_axis_combo is not None:
                current_axis = state.choi_axis
                for i in range(self.choi_axis_combo.count()):
                    if self.choi_axis_combo.itemData(i) == current_axis:
                        self.choi_axis_combo.setCurrentIndex(i)
                        break

            # Final state logging
            logger.info(
                "=== _load_settings_from_state COMPLETE: choi_widget_visible=%s, nonwear_algo=%s ===",
                self.choi_axis_widget.isVisible() if self.choi_axis_widget else "NO_WIDGET",
                state.nonwear_algorithm_id,
            )

        finally:
            self._block_all_signals(False)

    def _block_all_signals(self, block: bool) -> None:
        """Helper to block/unblock signals for all input widgets."""
        widgets = [
            self.unknown_value_edit,
            self.default_group_combo,
            self.default_timepoint_combo,
            self.id_pattern_edit,
            self.timepoint_pattern_edit,
            self.group_pattern_edit,
            self.data_paradigm_combo,
            self.sleep_algorithm_combo,
            self.sleep_period_detector_combo,
            self.nonwear_algorithm_combo,
            self.choi_axis_combo,
            self.night_start_time,
            self.night_end_time,
            self.valid_groups_list,
            self.valid_timepoints_list,
        ]
        for w in widgets:
            if w:
                w.blockSignals(block)

    def _connect_signals(self) -> None:
        """Connect internal signals for dynamic updates."""
        # Connect list widget changes to update default dropdowns
        self.valid_groups_list.items_changed.connect(self._update_group_dropdown)
        self.valid_timepoints_list.items_changed.connect(self._update_timepoint_dropdown)

        # Connect signals for external listeners (avoid lambda for memory safety)
        self.valid_groups_list.items_changed.connect(self._emit_groups_changed)
        self.valid_timepoints_list.items_changed.connect(self._emit_timepoints_changed)

        # Connect list widget changes to auto-save to config
        self.valid_groups_list.items_changed.connect(self._save_valid_groups)
        self.valid_timepoints_list.items_changed.connect(self._save_valid_timepoints)

        # Connect text field changes to auto-save to config (with debouncing)
        self.unknown_value_edit.textChanged.connect(self._on_unknown_value_changed)
        self.id_pattern_edit.textChanged.connect(self._on_id_pattern_changed)
        self.timepoint_pattern_edit.textChanged.connect(self._on_timepoint_pattern_changed)
        self.group_pattern_edit.textChanged.connect(self._on_group_pattern_changed)

        # Connect pattern changes to live testing
        # test_id_input initialized in pattern_builder.build_id_testing_section() before this
        # Connect test input field - this is the main trigger for live testing
        self.test_id_input.textChanged.connect(self._update_id_test_results)
        # Connect pattern field changes
        self.id_pattern_edit.textChanged.connect(self._update_id_test_results)
        self.timepoint_pattern_edit.textChanged.connect(self._update_id_test_results)
        self.group_pattern_edit.textChanged.connect(self._update_id_test_results)

        # Connect dropdown changes
        self.default_group_combo.currentTextChanged.connect(self._update_id_test_results)
        self.default_timepoint_combo.currentTextChanged.connect(self._update_id_test_results)

        # Connect validation list changes
        self.valid_groups_list.items_changed.connect(self._update_id_test_results)
        self.valid_timepoints_list.items_changed.connect(self._update_id_test_results)

    def _create_study_parameters_section(self) -> QGroupBox:
        """Create the study parameters configuration section."""
        group_box = QGroupBox(SettingsSection.STUDY_PARAMETERS)
        layout = QVBoxLayout(group_box)

        # Unknown Value Placeholder
        unknown_layout = QHBoxLayout()
        unknown_layout.addWidget(QLabel("Unknown Value Placeholder:"))

        self.unknown_value_edit = QLineEdit()
        self.unknown_value_edit.setPlaceholderText("Enter value to use when information cannot be extracted")
        self.unknown_value_edit.setToolTip("Text to display when participant information cannot be determined")
        self.unknown_value_edit.setMaximumWidth(200)
        self.unknown_value_edit.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        unknown_layout.addWidget(self.unknown_value_edit)
        unknown_layout.addStretch()
        layout.addLayout(unknown_layout)

        return group_box

    def _create_default_selection_section(self) -> QGroupBox:
        """Create the default selection section with intelligent dropdowns."""
        group_box = QGroupBox(SettingsSection.DEFAULT_SELECTION)
        layout = QHBoxLayout(group_box)

        # Default Group Selection
        group_layout = QVBoxLayout()
        group_layout.addWidget(QLabel("Default Group:"))

        self.default_group_combo = NoScrollComboBox()
        self.default_group_combo.setToolTip(
            "Default group to use when participant group cannot be determined from filename. Populated from valid groups defined above."
        )
        self.default_group_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.default_group_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.default_group_combo.setMinimumWidth(180)
        self.default_group_combo.currentTextChanged.connect(self._on_default_group_changed)
        group_layout.addWidget(self.default_group_combo)

        layout.addLayout(group_layout)

        # Default Timepoint Selection
        timepoint_layout = QVBoxLayout()
        timepoint_layout.addWidget(QLabel("Default Timepoint:"))

        self.default_timepoint_combo = NoScrollComboBox()
        self.default_timepoint_combo.setToolTip(
            "Default timepoint to use when participant timepoint cannot be determined from filename. Populated from valid timepoints defined above."
        )
        self.default_timepoint_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.default_timepoint_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.default_timepoint_combo.setMinimumWidth(180)
        self.default_timepoint_combo.currentTextChanged.connect(self._on_default_timepoint_changed)
        timepoint_layout.addWidget(self.default_timepoint_combo)

        layout.addLayout(timepoint_layout)

        # Add stretch to push everything to the left
        layout.addStretch()

        return group_box

        """Create a horizontal line separator."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("QFrame { color: #87CEEB; }")  # Light blue color
        return line

    def _create_action_buttons(self) -> QHBoxLayout:
        """Create the action buttons layout."""
        layout = QHBoxLayout()

        # Section label for clarity
        config_label = QLabel(f"<b>{SettingsSection.IMPORT_EXPORT_CONFIG}:</b>")
        config_label.setStyleSheet("QLabel { margin-right: 10px; }")
        layout.addWidget(config_label)

        # Import/Export config buttons
        self.import_config_button = QPushButton("Import Config...")
        self.import_config_button.clicked.connect(self._import_config)
        self.import_config_button.setStyleSheet("QPushButton { padding: 8px; }")
        self.import_config_button.setToolTip("Import study configuration from a file")

        self.export_config_button = QPushButton("Export Config...")
        self.export_config_button.clicked.connect(self._export_config)
        self.export_config_button.setStyleSheet("QPushButton { padding: 8px; }")
        self.export_config_button.setToolTip("Export study configuration to share with collaborators")

        layout.addWidget(self.import_config_button)
        layout.addWidget(self.export_config_button)

        layout.addStretch()

        return layout

    def _import_config(self) -> None:
        """Open the config import dialog."""
        from sleep_scoring_app.ui.config_dialog import ConfigImportDialog

        dialog = ConfigImportDialog(self, self.services.config_manager)
        if dialog.exec() == ConfigImportDialog.DialogCode.Accepted:
            # Reload settings in UI after import
            self._load_current_settings()

    def _export_config(self) -> None:
        """Open the config export dialog."""
        from sleep_scoring_app.ui.config_dialog import ConfigExportDialog

        dialog = ConfigExportDialog(self, self.services.config_manager)
        dialog.exec()

    def _load_current_settings(self) -> None:
        """Load current settings from configuration."""
        try:
            config = self.services.config_manager.config
            if config is None:
                logger.warning("Config not loaded, skipping settings load")
                return

            # Set unknown value (only update if different to preserve cursor position)
            if self.unknown_value_edit.text() != config.study_unknown_value:
                self.unknown_value_edit.setText(config.study_unknown_value)

            # Load valid groups
            self.valid_groups_list.clear()
            for group in config.study_valid_groups:
                self.valid_groups_list.addItem(group)

            # Load valid timepoints
            self.valid_timepoints_list.clear()
            for timepoint in config.study_valid_timepoints:
                self.valid_timepoints_list.addItem(timepoint)

            # Update default dropdowns after loading the lists
            self._update_group_dropdown()
            self._update_timepoint_dropdown()

            # Set default group selection (only if it's a real value, not empty)
            current_group = config.study_default_group
            if current_group:
                group_index = self.default_group_combo.findText(current_group)
                if group_index >= 0:
                    self.default_group_combo.setCurrentIndex(group_index)
                # If not found, keep placeholder selected

            # Set default timepoint selection (only if it's a real value, not empty)
            current_timepoint = config.study_default_timepoint
            if current_timepoint:
                timepoint_index = self.default_timepoint_combo.findText(current_timepoint)
                if timepoint_index >= 0:
                    self.default_timepoint_combo.setCurrentIndex(timepoint_index)
                # If not found, keep placeholder selected

            # Load regex patterns (only update if different to preserve cursor position)
            if config.study_participant_id_patterns:  # study_participant_id_patterns is a dataclass field
                # Use the first ID pattern as the primary one
                new_id_pattern = config.study_participant_id_patterns[0]
                if self.id_pattern_edit.text() != new_id_pattern:
                    self.id_pattern_edit.setText(new_id_pattern)

            # Load basic patterns from config (no defaults unless user set them)
            if self.timepoint_pattern_edit.text() != config.study_timepoint_pattern:
                self.timepoint_pattern_edit.setText(config.study_timepoint_pattern)
            if self.group_pattern_edit.text() != config.study_group_pattern:
                self.group_pattern_edit.setText(config.study_group_pattern)

            # Validate all patterns after loading
            self._validate_all_patterns()

            # Load algorithm configuration
            # Load data paradigm selection (must be loaded before sleep algorithm)
            if self.data_paradigm_combo is not None:  # Initialized in __init__
                self.data_paradigm_combo.blockSignals(True)
                try:
                    current_paradigm = config.data_paradigm
                    for i in range(self.data_paradigm_combo.count()):
                        if self.data_paradigm_combo.itemData(i) == current_paradigm:
                            self.data_paradigm_combo.setCurrentIndex(i)
                            break
                finally:
                    self.data_paradigm_combo.blockSignals(False)
                # Update the info label and repopulate algorithm combos
                self._update_paradigm_info_label()
                self._populate_algorithm_combo()
                self._populate_nonwear_algorithm_combo()
                self._populate_sleep_period_detector_combo()

            # Load sleep algorithm selection
            if self.sleep_algorithm_combo is not None:  # Initialized in __init__
                self.sleep_algorithm_combo.blockSignals(True)
                try:
                    current_algo_id = config.sleep_algorithm_id
                    for i in range(self.sleep_algorithm_combo.count()):
                        if self.sleep_algorithm_combo.itemData(i) == current_algo_id:
                            self.sleep_algorithm_combo.setCurrentIndex(i)
                            break
                finally:
                    self.sleep_algorithm_combo.blockSignals(False)

            # Load onset/offset rule selection
            if self.sleep_period_detector_combo is not None:  # Initialized in __init__
                self.sleep_period_detector_combo.blockSignals(True)
                try:
                    current_rule_id = config.onset_offset_rule_id
                    for i in range(self.sleep_period_detector_combo.count()):
                        if self.sleep_period_detector_combo.itemData(i) == current_rule_id:
                            self.sleep_period_detector_combo.setCurrentIndex(i)
                            break
                finally:
                    self.sleep_period_detector_combo.blockSignals(False)

            # Load nonwear algorithm selection
            if self.nonwear_algorithm_combo is not None:  # Initialized in __init__
                self.nonwear_algorithm_combo.blockSignals(True)
                try:
                    current_nonwear_id = config.nonwear_algorithm_id
                    for i in range(self.nonwear_algorithm_combo.count()):
                        if self.nonwear_algorithm_combo.itemData(i) == current_nonwear_id:
                            self.nonwear_algorithm_combo.setCurrentIndex(i)
                            break
                finally:
                    self.nonwear_algorithm_combo.blockSignals(False)

                # Update Choi axis visibility based on loaded algorithm
                self._update_choi_axis_visibility(current_nonwear_id)

            # Block signals during load to prevent save-on-load feedback loop
            self.night_start_time.blockSignals(True)
            self.night_end_time.blockSignals(True)
            try:
                self.night_start_time.setTime(QTime(config.night_start_hour, 0))
                self.night_end_time.setTime(QTime(config.night_end_hour, 0))
            finally:
                self.night_start_time.blockSignals(False)
                self.night_end_time.blockSignals(False)

            # Load Choi axis setting
            if self.choi_axis_combo is not None:  # Initialized in __init__
                current_axis = config.choi_axis
                for i in range(self.choi_axis_combo.count()):
                    if self.choi_axis_combo.itemData(i) == current_axis:
                        self.choi_axis_combo.setCurrentIndex(i)
                        break

            logger.debug("Study settings loaded from configuration")

        except Exception as e:
            logger.exception("Error loading study settings: %s", e)
            QMessageBox.warning(self, "Configuration Error", f"Error loading study settings: {e}")

    def _update_group_dropdown(self) -> None:
        """Update the default group dropdown with current list values."""
        current_selection = self.default_group_combo.currentText()
        self.default_group_combo.clear()

        # Get current items from the list
        items = self.valid_groups_list.get_all_items()
        if items:
            # Add placeholder option first
            self.default_group_combo.addItem("-- Select Default Group --")
            self.default_group_combo.addItems(items)

            # Try to restore previous selection (skip placeholder)
            index = self.default_group_combo.findText(current_selection)
            if index > 0:  # Must be greater than 0 to skip placeholder
                self.default_group_combo.setCurrentIndex(index)
            else:
                # Keep placeholder selected - don't auto-select first real item
                self.default_group_combo.setCurrentIndex(0)
        else:
            # Add placeholder when no items (keep enabled so user knows they need to add groups)
            self.default_group_combo.addItem("-- No groups defined --")
            # Keep enabled so user can see that they need to add groups

    def _update_timepoint_dropdown(self) -> None:
        """Update the default timepoint dropdown with current list values."""
        current_selection = self.default_timepoint_combo.currentText()
        self.default_timepoint_combo.clear()

        # Get current items from the list
        items = self.valid_timepoints_list.get_all_items()
        if items:
            # Add placeholder option first
            self.default_timepoint_combo.addItem("-- Select Default Timepoint --")
            self.default_timepoint_combo.addItems(items)

            # Try to restore previous selection (skip placeholder)
            index = self.default_timepoint_combo.findText(current_selection)
            if index > 0:  # Must be greater than 0 to skip placeholder
                self.default_timepoint_combo.setCurrentIndex(index)
            else:
                # Keep placeholder selected - don't auto-select first real item
                self.default_timepoint_combo.setCurrentIndex(0)
        else:
            # Add placeholder when no items (keep enabled so user knows they need to add timepoints)
            self.default_timepoint_combo.addItem("-- No timepoints defined --")
            # Keep enabled so user can see that they need to add timepoints

    def _update_default_group_dropdown(self, groups: list[str]) -> None:
        """Update the default group dropdown when groups change via signal."""
        self._update_group_dropdown()

    def _update_default_timepoint_dropdown(self, timepoints: list[str]) -> None:
        """Update the default timepoint dropdown when timepoints change via signal."""
        self._update_timepoint_dropdown()

    def _edit_selected_group(self) -> None:
        """Edit the currently selected group."""
        current_item = self.valid_groups_list.currentItem()
        if current_item:
            self.valid_groups_list._edit_item(current_item)
        else:
            QMessageBox.information(self, "No Selection", "Please select a group to edit.")

    def _edit_selected_timepoint(self) -> None:
        """Edit the currently selected timepoint."""
        current_item = self.valid_timepoints_list.currentItem()
        if current_item:
            self.valid_timepoints_list._edit_item(current_item)
        else:
            QMessageBox.information(self, "No Selection", "Please select a timepoint to edit.")

    def _add_group(self) -> None:
        """Add a new group to the valid groups list with enhanced validation."""
        text, ok = QInputDialog.getText(
            self,
            "Add Group",
            "Enter group name (e.g., G1, G2, etc.):",
            text="G",
        )

        if ok and text.strip():
            group_text = text.strip().upper()

            # Enhanced validation
            if not group_text:
                QMessageBox.warning(self, "Invalid Input", "Group name cannot be empty.")
                return

            if len(group_text) > 10:
                QMessageBox.warning(self, "Invalid Input", "Group name is too long (max 10 characters).")
                return

            success = self.valid_groups_list.add_item_with_validation(group_text)
            if success:
                logger.debug("Added group: %s", group_text)
                # Signal is automatically emitted by DragDropListWidget
            else:
                QMessageBox.information(self, "Duplicate Group", f"Group '{group_text}' already exists.")

    def _remove_group(self) -> None:
        """Remove selected group from the valid groups list with confirmation."""
        current_row = self.valid_groups_list.currentRow()
        if current_row >= 0:
            item = self.valid_groups_list.item(current_row)
            if item:
                removed_text = item.text()
                # Confirm removal
                reply = QMessageBox.question(
                    self,
                    "Confirm Removal",
                    f"Are you sure you want to remove group '{removed_text}'?\n\n⚠️  This may cause configuration validation to fail if no groups remain.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    removed_item = self.valid_groups_list.takeItem(current_row)
                    if removed_item:
                        logger.debug("Removed group: %s", removed_text)

                        # SS-01 FIX: Clear orphaned default if removed group was the default
                        if self.store.state.study_default_group.upper() == removed_text.upper():
                            # Clear the orphaned default via signal
                            self.studySettingChanged.emit("study_default_group", "")
                            logger.info("Cleared orphaned default group '%s' via signal", removed_text)

                        # Explicitly emit signal since takeItem() might not trigger model signals
                        self.valid_groups_list.items_changed.emit()
        else:
            QMessageBox.information(self, "No Selection", "Please select a group to remove.")

    def _add_timepoint(self) -> None:
        """Add a new timepoint to the valid timepoints list with enhanced validation."""
        text, ok = QInputDialog.getText(
            self,
            "Add Timepoint",
            "Enter timepoint name (e.g., BO, P1, P2, etc.):",
            text="P",
        )

        if ok and text.strip():
            timepoint_text = text.strip().upper()

            # Enhanced validation
            if not timepoint_text:
                QMessageBox.warning(self, "Invalid Input", "Timepoint name cannot be empty.")
                return

            if len(timepoint_text) > 10:
                QMessageBox.warning(self, "Invalid Input", "Timepoint name is too long (max 10 characters).")
                return

            success = self.valid_timepoints_list.add_item_with_validation(timepoint_text)
            if success:
                logger.debug("Added timepoint: %s", timepoint_text)
                # Signal is automatically emitted by DragDropListWidget
            else:
                QMessageBox.information(self, "Duplicate Timepoint", f"Timepoint '{timepoint_text}' already exists.")

    def _remove_timepoint(self) -> None:
        """Remove selected timepoint from the valid timepoints list with confirmation."""
        current_row = self.valid_timepoints_list.currentRow()
        if current_row >= 0:
            item = self.valid_timepoints_list.item(current_row)
            if item:
                removed_text = item.text()
                # Confirm removal
                reply = QMessageBox.question(
                    self,
                    "Confirm Removal",
                    f"Are you sure you want to remove timepoint '{removed_text}'?\n\n⚠️  This may cause configuration validation to fail if no timepoints remain.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )

                if reply == QMessageBox.StandardButton.Yes:
                    removed_item = self.valid_timepoints_list.takeItem(current_row)
                    if removed_item:
                        logger.debug("Removed timepoint: %s", removed_text)

                        # SS-01 FIX: Clear orphaned default if removed timepoint was the default
                        if self.store.state.study_default_timepoint.upper() == removed_text.upper():
                            # Clear the orphaned default via signal
                            self.studySettingChanged.emit("study_default_timepoint", "")
                            logger.info("Cleared orphaned default timepoint '%s' via signal", removed_text)

                        # Explicitly emit signal since takeItem() might not trigger model signals
                        self.valid_timepoints_list.items_changed.emit()
        else:
            QMessageBox.information(self, "No Selection", "Please select a timepoint to remove.")

    @pyqtSlot(str)
    def _on_default_group_changed(self, text: str) -> None:
        """Handle default group selection changes."""
        # SS-02 FIX: Skip placeholder selections and validate against valid groups list
        if not text or text.startswith("--"):
            return

        # Validate that the selected value is actually in the valid groups list
        valid_groups = self.valid_groups_list.get_all_items()
        if text not in valid_groups:
            logger.warning("Attempted to save invalid default group '%s' - not in valid groups list", text)
            return

        self.studySettingChanged.emit("study_default_group", text)

    @pyqtSlot(str)
    def _on_default_timepoint_changed(self, text: str) -> None:
        """Handle default timepoint selection changes."""
        # SS-02 FIX: Skip placeholder selections and validate against valid timepoints list
        if not text or text.startswith("--"):
            return

        # Validate that the selected value is actually in the valid timepoints list
        valid_timepoints = self.valid_timepoints_list.get_all_items()
        if text not in valid_timepoints:
            logger.warning("Attempted to save invalid default timepoint '%s' - not in valid timepoints list", text)
            return

        self.studySettingChanged.emit("study_default_timepoint", text)

    def _save_valid_groups(self) -> None:
        """Auto-save valid groups list to config when changed."""
        valid_groups = self.valid_groups_list.get_all_items()
        self.studySettingChanged.emit("study_valid_groups", valid_groups)

    def _emit_groups_changed(self) -> None:
        """Emit groups changed signal (helper to avoid lambda memory leak)."""
        self.groups_changed.emit(self.valid_groups_list.get_all_items())

    def _emit_timepoints_changed(self) -> None:
        """Emit timepoints changed signal (helper to avoid lambda memory leak)."""
        self.timepoints_changed.emit(self.valid_timepoints_list.get_all_items())

    def _save_valid_timepoints(self) -> None:
        """Auto-save valid timepoints list to config when changed."""
        valid_timepoints = self.valid_timepoints_list.get_all_items()
        self.studySettingChanged.emit("study_valid_timepoints", valid_timepoints)

    @pyqtSlot()
    def _on_unknown_value_changed(self) -> None:
        """Handle unknown value text field changes - emits signal for connector."""
        unknown_value = self.unknown_value_edit.text().strip()
        self.studySettingChanged.emit("study_unknown_value", unknown_value)

    @pyqtSlot()
    def _on_id_pattern_changed(self) -> None:
        """Handle ID pattern text field changes - emits signal for connector."""
        id_pattern = self.id_pattern_edit.text().strip()
        # Save as participant_id_patterns list
        participant_id_patterns = [id_pattern] if id_pattern else []
        self.studySettingChanged.emit("study_participant_id_patterns", participant_id_patterns)

    @pyqtSlot()
    def _on_timepoint_pattern_changed(self) -> None:
        """Handle timepoint pattern text field changes - emits signal for connector."""
        timepoint_pattern = self.timepoint_pattern_edit.text().strip()
        self.studySettingChanged.emit("study_timepoint_pattern", timepoint_pattern)

    @pyqtSlot()
    def _on_group_pattern_changed(self) -> None:
        """Handle group pattern text field changes - emits signal for connector."""
        group_pattern = self.group_pattern_edit.text().strip()
        self.studySettingChanged.emit("study_group_pattern", group_pattern)

    def _validate_pattern(self, pattern: str, line_edit: QLineEdit, pattern_type: str) -> bool:
        """
        Validate a regex pattern and provide visual feedback.

        Args:
            pattern: The regex pattern to validate
            line_edit: The QLineEdit widget containing the pattern
            pattern_type: Type of pattern for error messages

        Returns:
            True if pattern is valid, False otherwise

        """
        if not pattern.strip():
            # Empty pattern - neutral styling
            line_edit.setStyleSheet("")
            line_edit.setToolTip(f"{pattern_type} pattern (empty)")
            return True

        try:
            # Test compile the regex
            re.compile(pattern)

            # Valid pattern - green border
            line_edit.setStyleSheet("QLineEdit { border: 2px solid #4CAF50; background-color: #f0fff0; }")
            line_edit.setToolTip(f"{pattern_type} pattern - Valid regex")
            return True

        except re.error as e:
            # Invalid pattern - red border
            line_edit.setStyleSheet("QLineEdit { border: 2px solid #f44336; background-color: #fff0f0; }")
            line_edit.setToolTip(f"{pattern_type} pattern - Invalid regex: {e}")
            return False

    def _validate_id_pattern(self) -> None:
        """Validate the ID pattern with debounced timing."""
        self.validation_timer.start(300)  # 300ms debounce

    def _validate_timepoint_pattern(self) -> None:
        """Validate the timepoint pattern with debounced timing."""
        self.validation_timer.start(300)  # 300ms debounce

    def _validate_group_pattern(self) -> None:
        """Validate the group pattern with debounced timing."""
        self.validation_timer.start(300)  # 300ms debounce

    def _validate_all_patterns(self) -> None:
        """Validate all regex patterns and update visual feedback."""
        try:
            # Validate each pattern
            self._validate_pattern(self.id_pattern_edit.text(), self.id_pattern_edit, "ID")

            self._validate_pattern(self.timepoint_pattern_edit.text(), self.timepoint_pattern_edit, "Timepoint")

            self._validate_pattern(self.group_pattern_edit.text(), self.group_pattern_edit, "Group")

            # Update live test results when patterns change
            # test_id_input initialized in setup_ui, always exists after initialization
            self._update_id_test_results()

        except Exception as e:
            logger.exception("Error validating patterns: %s", e)

    def _update_config_patterns_for_testing(self) -> None:
        """Temporarily update config patterns for live testing without saving."""
        try:
            # Get current patterns from UI
            id_pattern = self.id_pattern_edit.text().strip()
            timepoint_pattern = self.timepoint_pattern_edit.text().strip()
            group_pattern = self.group_pattern_edit.text().strip()

            # Get current validation lists
            valid_groups = self.valid_groups_list.get_all_items()
            valid_timepoints = self.valid_timepoints_list.get_all_items()
            default_group = self.default_group_combo.currentText()
            default_timepoint = self.default_timepoint_combo.currentText()

            # Temporarily update config for testing (doesn't save to disk)
            if not self.services.config_manager or not self.services.config_manager.config:
                return

            config = self.services.config_manager.config

            # Update patterns if they're provided
            from dataclasses import replace

            overrides: dict = {}
            if id_pattern:
                overrides["study_participant_id_patterns"] = [id_pattern]
            if timepoint_pattern:
                overrides["study_timepoint_pattern"] = timepoint_pattern
            if group_pattern:
                overrides["study_group_pattern"] = group_pattern

            # Update validation lists
            overrides["study_valid_groups"] = valid_groups
            overrides["study_valid_timepoints"] = valid_timepoints
            overrides["study_default_group"] = default_group
            overrides["study_default_timepoint"] = default_timepoint
            self.services.config_manager.config = replace(config, **overrides)

        except Exception as e:
            logger.exception("Error updating config patterns for testing: %s", e)

    def _update_id_test_results(self) -> None:
        """Update the live ID test results display using actual extract_participant_info."""
        try:
            test_input = self.test_id_input.text().strip()

            if not test_input:
                self.test_results_display.setHtml("""
                    <div style="color: #666; font-style: italic;">
                        Enter an ID or filename above to see extraction results...
                    </div>
                """)
                return

            # First, update the config with current patterns to test them live
            self._update_config_patterns_for_testing()

            # Use function-based extraction for testing
            from sleep_scoring_app.utils.participant_extractor import extract_participant_info

            try:
                # Get the current config
                if not self.services.config_manager or not self.services.config_manager.config:
                    return

                config = self.services.config_manager.config

                # Test with new function-based approach
                participant_info = extract_participant_info(test_input, config)

                # Get current validation lists
                valid_groups = self.valid_groups_list.get_all_items()
                valid_timepoints = self.valid_timepoints_list.get_all_items()
                default_group = self.default_group_combo.currentText()
                default_timepoint = self.default_timepoint_combo.currentText()

                results_html = f"""
                    <div style="font-family: monospace; font-size: 12px;">
                        <b>Test ID:</b> "{test_input}"<br><br>
                        <b>Extraction Results:</b><br>
                """

                # ID result
                id_value = participant_info.numerical_id
                if id_value and id_value not in (default_group, "Unknown"):
                    color = "#28a745"  # green
                    icon = "✓"
                    status = f'"{id_value}" (matched pattern)'
                else:
                    color = "#dc3545"  # red
                    icon = "✗"
                    status = "not extracted"

                results_html += f"""
                    <span style="color: {color};">{icon} ID:</span> {status}<br>
                """

                # Group result - use group_str for the actual extracted value
                group_value = participant_info.group_str
                if group_value.upper() in [g.upper() for g in valid_groups]:
                    color = "#28a745"  # green
                    icon = "✓"
                    status = f'"{group_value}" (✓ valid group)'
                elif group_value == default_group:
                    color = "#ffc107"  # yellow
                    icon = "⚠"
                    status = f'"{group_value}" (⚠ Could not extract group from input, using default value)'
                else:
                    color = "#ffc107"  # yellow
                    icon = "⚠"
                    status = f'"{group_value}" (✗ Could not extract group from input, using default value)'

                results_html += f"""
                    <span style="color: {color};">{icon} Group:</span> {status}<br>
                """

                # Timepoint result - use timepoint_str for the actual extracted value
                timepoint_value = participant_info.timepoint_str
                if timepoint_value.upper() in [tp.upper() for tp in valid_timepoints]:
                    color = "#28a745"  # green
                    icon = "✓"
                    status = f'"{timepoint_value}" (✓ valid timepoint)'
                elif timepoint_value == default_timepoint:
                    color = "#ffc107"  # yellow
                    icon = "⚠"
                    status = f'"{timepoint_value}" (⚠ Could not extract timepoint from input, using default value)'
                else:
                    color = "#ffc107"  # yellow
                    icon = "⚠"
                    status = f'"{timepoint_value}" (✗ Could not extract timepoint from input, using default value)'

                results_html += f"""
                    <span style="color: {color};">{icon} Timepoint:</span> {status}<br><br>
                """

                results_html += "</div>"

            except Exception as extract_error:
                # Show extraction error
                results_html = f"""
                    <div style="color: #dc3545; font-family: monospace; font-size: 12px;">
                        <b>Extraction Error:</b><br>
                        {extract_error}
                    </div>
                """

            self.test_results_display.setHtml(results_html)

        except Exception as e:
            logger.exception("Error updating ID test results: %s", e)
            # test_results_display initialized in setup_ui, always exists after initialization
            self.test_results_display.setHtml(f"""
                <div style="color: #dc3545;">
                    Error testing patterns: {e}
                </div>
            """)

    def _reset_patterns_to_defaults(self) -> None:
        """Reset all regex patterns to their default values."""
        reply = QMessageBox.question(
            self,
            "Reset Patterns",
            "Are you sure you want to reset all regex patterns to their default values?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Set default patterns
                self.id_pattern_edit.setText(r"^(\d{4,})[_-]")
                self.timepoint_pattern_edit.setText(r"([A-Z0-9]+)")
                self.group_pattern_edit.setText(r"g[123]")

                # Validate all patterns
                self._validate_all_patterns()

                logger.debug("Regex patterns reset to defaults")

            except Exception as e:
                logger.exception("Error resetting patterns: %s", e)
                QMessageBox.critical(self, "Error", f"Error resetting patterns: {e}")

    def _get_current_paradigm(self) -> StudyDataParadigm:
        """Get the currently selected data paradigm."""
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

    def _populate_algorithm_combo(self) -> None:
        """Populate sleep algorithm combo based on current paradigm."""
        # Block signals to prevent triggering change handler during repopulation
        self.sleep_algorithm_combo.blockSignals(True)
        try:
            # Store current selection if any
            current_algo_id = self.sleep_algorithm_combo.currentData()

            # Clear and repopulate
            self.sleep_algorithm_combo.clear()

            paradigm = self._get_current_paradigm()
            available_algorithms = get_algorithm_service().get_available_sleep_algorithms()

            for algo_id, algo_name in available_algorithms.items():
                if paradigm.is_algorithm_compatible(algo_id):
                    self.sleep_algorithm_combo.addItem(algo_name, algo_id)

            # Try to restore previous selection if still compatible
            if current_algo_id and paradigm.is_algorithm_compatible(current_algo_id):
                for i in range(self.sleep_algorithm_combo.count()):
                    if self.sleep_algorithm_combo.itemData(i) == current_algo_id:
                        self.sleep_algorithm_combo.setCurrentIndex(i)
                        break
        finally:
            self.sleep_algorithm_combo.blockSignals(False)

    def _populate_nonwear_algorithm_combo(self) -> None:
        """Populate nonwear algorithm combo based on current paradigm."""
        if self.nonwear_algorithm_combo is None:  # Initialized in __init__
            return

        # Block signals to prevent triggering change handler during repopulation
        self.nonwear_algorithm_combo.blockSignals(True)
        try:
            # Store current selection if any
            current_algo_id = self.nonwear_algorithm_combo.currentData()

            # Clear and repopulate
            self.nonwear_algorithm_combo.clear()

            paradigm = self._get_current_paradigm()
            available_algorithms = get_algorithm_service().get_nonwear_algorithms_for_paradigm(paradigm.value)
            logger.info(
                "=== Populating nonwear combo: paradigm=%s, available=%s ===",
                paradigm.value,
                list(available_algorithms.keys()),
            )

            for algo_id, algo_name in available_algorithms.items():
                self.nonwear_algorithm_combo.addItem(algo_name, algo_id)

            # Try to restore previous selection if still compatible
            if current_algo_id and current_algo_id in available_algorithms:
                for i in range(self.nonwear_algorithm_combo.count()):
                    if self.nonwear_algorithm_combo.itemData(i) == current_algo_id:
                        self.nonwear_algorithm_combo.setCurrentIndex(i)
                        break

            # Update Choi axis visibility based on final selection
            final_algo_id = self.nonwear_algorithm_combo.currentData() if self.nonwear_algorithm_combo.count() > 0 else None
            logger.info(
                "Nonwear combo populated: count=%d, final_algo=%r, choi_widget_exists=%s",
                self.nonwear_algorithm_combo.count(),
                final_algo_id,
                self.choi_axis_widget is not None,
            )
            if final_algo_id:
                self._update_choi_axis_visibility(final_algo_id)
            else:
                logger.warning("!!! No final_algo_id - visibility NOT updated !!!")
        finally:
            self.nonwear_algorithm_combo.blockSignals(False)

    def _populate_sleep_period_detector_combo(self) -> None:
        """Populate sleep period detector combo based on current paradigm."""
        if self.sleep_period_detector_combo is None:  # Initialized in __init__
            return

        # Block signals to prevent triggering change handler during repopulation
        self.sleep_period_detector_combo.blockSignals(True)
        try:
            # Store current selection if any
            current_detector_id = self.sleep_period_detector_combo.currentData()

            # Clear and repopulate
            self.sleep_period_detector_combo.clear()

            paradigm = self._get_current_paradigm()
            available_detectors = get_algorithm_service().get_sleep_period_detectors_for_paradigm(paradigm.value)

            for detector_id, detector_name in available_detectors.items():
                self.sleep_period_detector_combo.addItem(detector_name, detector_id)

            # Try to restore previous selection if still compatible
            if current_detector_id and current_detector_id in available_detectors:
                for i in range(self.sleep_period_detector_combo.count()):
                    if self.sleep_period_detector_combo.itemData(i) == current_detector_id:
                        self.sleep_period_detector_combo.setCurrentIndex(i)
                        break
        finally:
            self.sleep_period_detector_combo.blockSignals(False)

    def _on_data_paradigm_changed(self, index: int) -> None:
        """Handle data paradigm selection change with confirmation."""
        try:
            new_paradigm_value = self.data_paradigm_combo.itemData(index)
            new_paradigm = StudyDataParadigm(new_paradigm_value)

            # Get current paradigm from store state
            current_paradigm_value = self.store.state.data_paradigm

            # If paradigm hasn't changed, just update UI
            if new_paradigm_value == current_paradigm_value:
                self._update_paradigm_info_label()
                return

            # Check if data has been imported
            has_imported_data = False
            if self.services.db_manager:
                try:
                    # Check if there are any imported files
                    file_count = self.services.db_manager.get_imported_file_count()
                    has_imported_data = file_count > 0
                except Exception:
                    pass

            # Show confirmation dialog
            message = ParadigmWarning.RESET_RECOMMENDED
            if has_imported_data:
                message = f"{ParadigmWarning.DATA_EXISTS}\n\n{ParadigmWarning.RESET_RECOMMENDED}"

            reply = QMessageBox.question(
                self,
                ParadigmWarning.TITLE,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if reply != QMessageBox.StandardButton.Yes:
                # User canceled - revert combo box to previous value
                self.data_paradigm_combo.blockSignals(True)
                try:
                    for i in range(self.data_paradigm_combo.count()):
                        if self.data_paradigm_combo.itemData(i) == current_paradigm_value:
                            self.data_paradigm_combo.setCurrentIndex(i)
                            break
                finally:
                    self.data_paradigm_combo.blockSignals(False)
                return

            # User confirmed - proceed with paradigm change
            # Update info label (handled by UI sync)

            # Emit signal for connector to dispatch to store
            # StudySettingsConnector._handle_side_effects watches for data_paradigm
            # changes and calls data_settings_tab.update_loaders_for_paradigm()
            self.studySettingChanged.emit("data_paradigm", new_paradigm_value)
            logger.info("Data paradigm change emitted via signal: %s", new_paradigm.get_display_name())

        except Exception as e:
            logger.exception("Error changing data paradigm: %s", e)

    @pyqtSlot(int)
    def _on_sleep_algorithm_changed(self, index: int) -> None:
        """Handle sleep algorithm selection change."""
        try:
            algorithm_id = self.sleep_algorithm_combo.itemData(index)
            if not algorithm_id:
                return

            self.studySettingChanged.emit("sleep_algorithm_id", algorithm_id)
            logger.info("Sleep algorithm change emitted via signal: %s", algorithm_id)

        except Exception as e:
            logger.exception("Error changing sleep algorithm: %s", e)

    def _on_sleep_period_detector_changed(self, index: int) -> None:
        """Handle sleep period detector selection change."""
        try:
            rule_id = self.sleep_period_detector_combo.itemData(index)
            if not rule_id:
                return

            self.studySettingChanged.emit("onset_offset_rule_id", rule_id)
            logger.info("Onset/offset rule change emitted via signal: %s", rule_id)
        except Exception as e:
            logger.exception("Error changing onset/offset rule: %s", e)

    def _on_night_hours_changed(self) -> None:
        """Handle night hours time changes."""
        try:
            start_hour = self.night_start_time.time().hour()
            end_hour = self.night_end_time.time().hour()

            self.studySettingChanged.emit("night_start_hour", start_hour)
            self.studySettingChanged.emit("night_end_hour", end_hour)
            logger.debug("Night hours change emitted via signal: %d:00 - %d:00", start_hour, end_hour)
        except Exception as e:
            logger.exception("Error changing night hours: %s", e)

    def _on_nonwear_algorithm_changed(self, index: int) -> None:
        """Handle nonwear algorithm selection change."""
        try:
            algo_id = self.nonwear_algorithm_combo.itemData(index)
            if not algo_id:
                return

            # Update Choi axis visibility immediately for responsive UI
            self._update_choi_axis_visibility(algo_id)

            self.studySettingChanged.emit("nonwear_algorithm_id", algo_id)
            logger.info("Nonwear algorithm change emitted via signal: %s", algo_id)
        except Exception as e:
            logger.exception("Error changing nonwear algorithm: %s", e)

    def _update_choi_axis_visibility(self, nonwear_algorithm_id: str | NonwearAlgorithm) -> None:
        """
        Show/hide the Choi axis widget based on selected nonwear algorithm.

        Args:
            nonwear_algorithm_id: The currently selected nonwear algorithm ID (string or enum).

        """
        logger.info(
            "=== _update_choi_axis_visibility called: algo=%r, widget_exists=%s ===",
            nonwear_algorithm_id,
            self.choi_axis_widget is not None,
        )
        if self.choi_axis_widget is not None:  # Initialized in __init__
            # Normalize to string for consistent comparison
            # (handles both str and StrEnum inputs)
            algo_str = str(nonwear_algorithm_id)
            is_choi = algo_str == NonwearAlgorithm.CHOI_2011.value
            logger.info(
                "Setting Choi axis visibility: algo_str=%r, CHOI_VALUE=%r, is_choi=%s",
                algo_str,
                NonwearAlgorithm.CHOI_2011.value,
                is_choi,
            )
            self.choi_axis_widget.setVisible(is_choi)
            logger.info("Choi axis widget.isVisible() after setVisible: %s", self.choi_axis_widget.isVisible())
        else:
            logger.warning("!!! choi_axis_widget is None - cannot set visibility !!!")

    def _on_nonwear_axis_changed(self, index: int) -> None:
        """Handle nonwear activity axis selection change."""
        try:
            axis = self.choi_axis_combo.itemData(index)
            if not axis:
                return

            self.studySettingChanged.emit("choi_axis", axis)
            logger.info("Choi axis change emitted via signal: %s", axis)
        except Exception as e:
            logger.exception("Error saving Choi axis setting: %s", e)
