#!/usr/bin/env python3
"""
Data Settings Tab Component
Handles data source configuration and import functionality.

All data is stored in the database. Import operations are one-time actions
that load data from files into the database. Settings are global and apply
to all import operations.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path
from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.core.constants import ButtonText, DataSourceType, DevicePreset, InfoMessage, StudyDataParadigm, TabName
from sleep_scoring_app.io.sources.loader_factory import DataSourceFactory
from sleep_scoring_app.ui.dialogs import ColumnMappingDialog
from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox, NoScrollSpinBox

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import AppConfig
    from sleep_scoring_app.ui.protocols import (
        AppStateInterface,
        MainWindowProtocol,
        ServiceContainer,
    )
    from sleep_scoring_app.ui.store import UIStore

logger = logging.getLogger(__name__)


class DataSettingsTab(QWidget):
    """
    Data Settings Tab for configuring data sources and imports.

    All data is stored in the database. Import operations load data from files
    into the database as a one-time operation. Settings are global and apply
    to all import operations.
    """

    # Signals emitted instead of direct store.dispatch calls
    fileCleared = pyqtSignal()  # Was: store.dispatch(Actions.file_selected(None)) + dates_loaded([])
    clearActivityDataRequested = pyqtSignal()  # Was: store.dispatch(Actions.clear_activity_data_requested())
    refreshFilesRequested = pyqtSignal()  # Was: store.dispatch(Actions.refresh_files_requested())
    clearNwtDataRequested = pyqtSignal()  # Was: db_manager.clear_nwt_data() direct call
    clearDiaryDataRequested = pyqtSignal()  # Was: db_manager.clear_diary_data() direct call

    # Signal for data setting config changes: (field_name, value)
    # Connector persists to config on behalf of this widget
    dataSettingChanged = pyqtSignal(str, object)

    # Signals emitted instead of direct main_window method connections
    epochLengthChanged = pyqtSignal(int)
    skipRowsChanged = pyqtSignal(int)
    browseActivityFilesRequested = pyqtSignal()
    startActivityImportRequested = pyqtSignal()
    browseNonwearFilesRequested = pyqtSignal()
    startNonwearImportRequested = pyqtSignal()

    def __init__(self, store: UIStore, app_state: AppStateInterface, services: ServiceContainer, parent: MainWindowProtocol) -> None:
        """Initialize the data settings tab presentational shell."""
        super().__init__(cast("QWidget", parent))
        self.app_state = app_state
        self.services = services

        # Purely UI state
        self.import_worker = None
        self.selected_diary_files: list[Path] = []

        self.setup_ui()
        logger.info("DataSettingsTab initialized as Presenter")

    @property
    def _config(self) -> AppConfig:
        """Safely access config, raising if unavailable."""
        if (c := self.services.config_manager.config) is None:
            msg = "Config not loaded"
            raise RuntimeError(msg)
        return c

    @property
    def _config_or_none(self) -> AppConfig | None:
        """Safely access config, returning None if unavailable."""
        # TODO(refactor): pattern-violation Init-time config reads still go through services directly
        return self.services.config_manager.config

    def setup_ui(self) -> None:
        """Create the presentational layout."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)

        # 1. Header
        header_label = QLabel(
            "<b>Data Configuration</b><br>Configure settings for data import. All data is stored in the database for fast loading.",
        )
        header_label.setWordWrap(True)
        header_label.setStyleSheet("background-color: #f0f0f0; padding: 10px; border-radius: 5px;")
        content_layout.addWidget(header_label)

        # 2. Paradigm Indicator
        content_layout.addWidget(self._create_paradigm_indicator())

        # 3. Activity Data Section (includes file management)
        content_layout.addWidget(self._create_activity_data_section())

        # 4. Diary Section
        content_layout.addWidget(self._create_diary_data_section())

        # 5. NWT Sensor Data Section (Nonwear Detection)
        content_layout.addWidget(self._create_nwt_data_section())

        content_layout.addStretch()
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)

    def _handle_current_file_deleted(self) -> None:
        """
        Handle cleanup when the currently selected file is deleted.

        Emits fileCleared signal - the connector dispatches Redux actions.
        Connectors will handle the UI updates in response to state changes.
        """
        try:
            self.fileCleared.emit()

            # Note: DateDropdownConnector handles dropdown clearing
            # StatusConnector handles status bar updates
            # PlotConnector handles plot clearing (if exists)

            logger.info("Emitted fileCleared signal for file deletion cleanup")
        except Exception as e:
            logger.warning("Error during file deletion cleanup: %s", e)

    def _create_paradigm_indicator(self) -> QWidget:
        """Create a paradigm indicator showing current paradigm with link to change it."""
        indicator_widget = QWidget()
        indicator_layout = QHBoxLayout(indicator_widget)
        indicator_layout.setContentsMargins(0, 10, 0, 10)

        # Get current paradigm via services
        try:
            config = self._config
            paradigm_value = config.data_paradigm if config else None
            paradigm = StudyDataParadigm(paradigm_value) if paradigm_value else StudyDataParadigm.get_default()
        except (ValueError, AttributeError):
            paradigm = StudyDataParadigm.get_default()

        # Create indicator label
        self.paradigm_indicator_label = QLabel()
        self._update_paradigm_indicator_label(paradigm)
        indicator_layout.addWidget(self.paradigm_indicator_label)

        # Add button to change paradigm (links to Study Settings tab)
        change_paradigm_btn = QPushButton("Change Data Paradigm...")
        change_paradigm_btn.setStyleSheet("""
            QPushButton {
                background-color: #3498db;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
        """)
        change_paradigm_btn.setToolTip("Go to Study Settings to change the Data Paradigm")
        change_paradigm_btn.clicked.connect(self._go_to_study_settings)
        indicator_layout.addWidget(change_paradigm_btn)

        indicator_layout.addStretch()

        return indicator_widget

    def _update_paradigm_indicator_label(self, paradigm: StudyDataParadigm) -> None:
        """Update the paradigm indicator label text and style."""
        if paradigm == StudyDataParadigm.EPOCH_BASED:
            text = "📊 <b>Current Data Paradigm:</b> Epoch-Based (CSV with activity counts)"
            bg_color = "#e8f5e9"
            border_color = "#4caf50"
        else:
            text = "📈 <b>Current Data Paradigm:</b> Raw Accelerometer (GT3X / Raw CSV)"
            bg_color = "#e3f2fd"
            border_color = "#2196f3"

        self.paradigm_indicator_label.setText(text)
        self.paradigm_indicator_label.setStyleSheet(f"""
            QLabel {{
                font-size: 12px;
                padding: 10px 15px;
                background-color: {bg_color};
                border-left: 4px solid {border_color};
                border-radius: 4px;
            }}
        """)
        self.paradigm_indicator_label.setWordWrap(True)

    def _go_to_study_settings(self) -> None:
        """Switch to the Study Settings tab."""
        if self.services.tab_widget:
            # Find Study Settings tab index
            for i in range(self.services.tab_widget.count()):
                if self.services.tab_widget.tabText(i) == TabName.STUDY_SETTINGS:
                    self.services.tab_widget.setCurrentIndex(i)
                    break

    def _create_section_separator(self) -> QFrame:
        """Create a horizontal line separator."""
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        line.setStyleSheet("QFrame { color: #87CEEB; }")  # Light blue color
        return line

    def _create_path_label(self, initial_text: str = "") -> QLabel:
        """
        Create a path label with proper size constraints to prevent layout expansion.

        The label uses elided text to handle long paths gracefully.
        """
        label = QLabel(initial_text or InfoMessage.NO_DIRECTORY_SELECTED)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        label.setMinimumWidth(100)
        label.setMaximumWidth(350)
        label.setStyleSheet("QLabel { color: #555; }")
        return label

    def _set_path_label_text(self, label: QLabel, full_path: str) -> None:
        """
        Set text on a path label with elision for long paths.

        Shows the full path in a tooltip on hover.
        """
        if not full_path or full_path == InfoMessage.NO_DIRECTORY_SELECTED:
            label.setText(InfoMessage.NO_DIRECTORY_SELECTED)
            label.setToolTip("")
            label.setStyleSheet("QLabel { color: #999; }")
            return

        metrics = QFontMetrics(label.font())
        # Use a reasonable width for elision (account for padding)
        available_width = label.maximumWidth() - 10
        elided = metrics.elidedText(full_path, Qt.TextElideMode.ElideMiddle, available_width)
        label.setText(elided)
        label.setToolTip(full_path)  # Show full path on hover
        label.setStyleSheet("QLabel { color: #333; }")

    def _create_activity_data_section(self) -> QGroupBox:
        """Create Activity Data section with global settings and import."""
        # Make title paradigm-aware
        try:
            paradigm_value = self._config.data_paradigm
            paradigm = StudyDataParadigm(paradigm_value)
        except (ValueError, AttributeError, RuntimeError):
            paradigm = StudyDataParadigm.get_default()

        # Set title based on paradigm
        if paradigm == StudyDataParadigm.EPOCH_BASED:
            title = "Activity Data (CSV/Excel with epoch counts)"
        else:
            title = "Activity Data (GT3X or raw CSV files)"

        self.activity_group = QGroupBox(title)
        activity_layout = QVBoxLayout(self.activity_group)

        # Global Settings Grid
        settings_grid = QGridLayout()

        # Data Source Type dropdown (DI pattern)
        settings_grid.addWidget(QLabel("Data Source Type:"), 0, 0)
        self.data_source_combo = NoScrollComboBox()

        # Populate from factory - filtered by current paradigm
        # Note: update_loaders_for_paradigm() is called after combo is set up
        # to properly filter based on the current paradigm setting
        from sleep_scoring_app.io.sources.loader_factory import DataSourceFactory

        # Initial population with all loaders (will be filtered by paradigm)
        available_loaders = DataSourceFactory.get_available_loaders()
        for loader_id, display_name in available_loaders.items():
            self.data_source_combo.addItem(display_name, loader_id)

        # Set current value from config (block signals during initialization)
        self.data_source_combo.blockSignals(True)
        try:
            current_loader_id = self._config.data_source_type_id
            for i in range(self.data_source_combo.count()):
                if self.data_source_combo.itemData(i) == current_loader_id:
                    self.data_source_combo.setCurrentIndex(i)
                    break
        finally:
            self.data_source_combo.blockSignals(False)

        self.data_source_combo.currentIndexChanged.connect(self._on_data_source_changed)
        self.data_source_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.data_source_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.data_source_combo, 0, 1)

        # Device Preset dropdown with auto-detect
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

        # Set current value from config via services
        current_preset = self._config.device_preset
        for i in range(self.device_preset_combo.count()):
            if self.device_preset_combo.itemData(i) == current_preset:
                self.device_preset_combo.setCurrentIndex(i)
                break

        self.device_preset_combo.currentIndexChanged.connect(self._on_device_preset_changed)
        self.device_preset_combo.setSizeAdjustPolicy(NoScrollComboBox.SizeAdjustPolicy.AdjustToContents)
        self.device_preset_combo.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.device_preset_combo, 1, 1)

        # Auto-detect device button
        self.device_autodetect_btn = QPushButton("Auto-detect")
        self.device_autodetect_btn.clicked.connect(self._autodetect_device_format)
        settings_grid.addWidget(self.device_autodetect_btn, 1, 2)

        # Configure Columns button (enabled only for Generic CSV)
        self.configure_columns_btn = QPushButton("Configure Columns...")
        self.configure_columns_btn.setEnabled(current_preset == DevicePreset.GENERIC_CSV.value)
        self.configure_columns_btn.clicked.connect(self._open_column_mapping_dialog)
        settings_grid.addWidget(self.configure_columns_btn, 1, 3)

        # Epoch length
        settings_grid.addWidget(QLabel("Epoch Length (seconds):"), 2, 0)
        self.epoch_length_spin = NoScrollSpinBox()
        self.epoch_length_spin.setRange(1, 300)
        self.epoch_length_spin.setValue(self._config.epoch_length)
        # Signal forwarded to connector instead of direct main_window connection
        self.epoch_length_spin.valueChanged.connect(self.epochLengthChanged.emit)
        self.epoch_length_spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.epoch_length_spin, 2, 1)

        # Auto-detect button for Epoch Length
        self.epoch_autodetect_btn = QPushButton("Auto-detect")
        self.epoch_autodetect_btn.clicked.connect(self._autodetect_epoch_length)
        settings_grid.addWidget(self.epoch_autodetect_btn, 2, 2)

        # Skip rows
        settings_grid.addWidget(QLabel("Skip Rows:"), 3, 0)
        self.skip_rows_spin = NoScrollSpinBox()
        self.skip_rows_spin.setRange(0, 100)
        self.skip_rows_spin.setValue(self._config.skip_rows)
        # Signal forwarded to connector instead of direct main_window connection
        self.skip_rows_spin.valueChanged.connect(self.skipRowsChanged.emit)
        self.skip_rows_spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        settings_grid.addWidget(self.skip_rows_spin, 3, 1)

        # Auto-detect button for Skip Rows
        self.skip_rows_autodetect_btn = QPushButton("Auto-detect")
        self.skip_rows_autodetect_btn.clicked.connect(self._autodetect_skip_rows)
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
        self.autodetect_all_btn.clicked.connect(self._autodetect_all)
        settings_grid.addWidget(self.autodetect_all_btn, 3, 3)

        activity_layout.addLayout(settings_grid)

        # CSV-specific options section (placeholder for future CSV-only settings)
        # Note: Skip Rows is now in the main settings section with auto-detect
        self.csv_options_widget = QWidget()
        csv_options_layout = QGridLayout(self.csv_options_widget)
        csv_options_layout.setContentsMargins(20, 10, 0, 10)
        # Currently empty - CSV uses Skip Rows from main settings
        csv_options_layout.setColumnStretch(0, 1)

        activity_layout.addWidget(self.csv_options_widget)
        # Hide CSV options widget since it's empty
        self.csv_options_widget.setVisible(False)

        # GT3X-specific options section
        self.gt3x_options_widget = QWidget()
        gt3x_options_layout = QGridLayout(self.gt3x_options_widget)
        gt3x_options_layout.setContentsMargins(20, 10, 0, 10)

        gt3x_options_layout.addWidget(QLabel("GT3X Epoch Length (seconds):"), 0, 0)
        self.gt3x_epoch_length_spin = NoScrollSpinBox()
        self.gt3x_epoch_length_spin.setRange(1, 300)
        self.gt3x_epoch_length_spin.blockSignals(True)
        try:
            self.gt3x_epoch_length_spin.setValue(self._config.gt3x_epoch_length)
        finally:
            self.gt3x_epoch_length_spin.blockSignals(False)
        self.gt3x_epoch_length_spin.valueChanged.connect(self._on_gt3x_epoch_length_changed)
        self.gt3x_epoch_length_spin.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.gt3x_epoch_length_spin.setToolTip("Epoch length for GT3X data processing")
        gt3x_options_layout.addWidget(self.gt3x_epoch_length_spin, 0, 1)

        gt3x_options_layout.addWidget(QLabel("Return Raw Data:"), 1, 0)
        self.gt3x_return_raw_check = QCheckBox()
        self.gt3x_return_raw_check.blockSignals(True)
        try:
            self.gt3x_return_raw_check.setChecked(self._config.gt3x_return_raw)
        finally:
            self.gt3x_return_raw_check.blockSignals(False)
        self.gt3x_return_raw_check.stateChanged.connect(self._on_gt3x_return_raw_changed)
        self.gt3x_return_raw_check.setToolTip("Return raw acceleration data instead of activity counts")
        gt3x_options_layout.addWidget(self.gt3x_return_raw_check, 1, 1)
        gt3x_options_layout.setColumnStretch(2, 1)

        activity_layout.addWidget(self.gt3x_options_widget)

        # Update visibility based on current selection
        self._update_data_source_visibility()

        # Column mapping status (for Generic CSV)
        self.column_mapping_status = QLabel()
        self.column_mapping_status.setStyleSheet("color: #666; font-size: 10px; padding-left: 5px;")
        self._update_column_mapping_status()
        activity_layout.addWidget(self.column_mapping_status)

        # Import section separator
        activity_layout.addWidget(self._create_section_separator())

        # Import controls
        import_label = QLabel("<b>Import Activity Data:</b>")
        activity_layout.addWidget(import_label)

        import_layout = QHBoxLayout()
        import_layout.addWidget(QLabel("Files:"))

        self.activity_import_files_label = self._create_path_label()
        import_layout.addWidget(self.activity_import_files_label)

        self.activity_browse_btn = QPushButton("Select Files...")
        # Signal forwarded to connector instead of direct main_window connection
        self.activity_browse_btn.clicked.connect(lambda: self.browseActivityFilesRequested.emit())
        import_layout.addWidget(self.activity_browse_btn)

        self.activity_import_btn = QPushButton("Import")
        self.activity_import_btn.setEnabled(False)
        self.activity_import_btn.setToolTip("Select CSV files to enable import")
        # Signal forwarded to connector instead of direct main_window connection
        self.activity_import_btn.clicked.connect(lambda: self.startActivityImportRequested.emit())
        self.activity_import_btn.setStyleSheet("""
            QPushButton:enabled {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
            }
            QPushButton:enabled:hover {
                background-color: #229954;
            }
        """)
        import_layout.addWidget(self.activity_import_btn)

        activity_layout.addLayout(import_layout)

        # Progress components - initially hidden
        self.activity_progress_label = QLabel(InfoMessage.READY_TO_IMPORT)
        self.activity_progress_label.setVisible(False)
        activity_layout.addWidget(self.activity_progress_label)

        self.activity_progress_bar = QProgressBar()
        self.activity_progress_bar.setRange(0, 100)
        self.activity_progress_bar.setMinimumHeight(20)
        self.activity_progress_bar.setVisible(False)
        activity_layout.addWidget(self.activity_progress_bar)

        # Status label
        self.activity_status_label = QLabel()
        activity_layout.addWidget(self.activity_status_label)

        # File Management Section
        activity_layout.addWidget(self._create_section_separator())
        file_mgmt_label = QLabel("<b>Manage Imported Files:</b>")
        activity_layout.addWidget(file_mgmt_label)

        # Initialize file management widget
        from sleep_scoring_app.ui.widgets.file_management_widget import FileManagementWidget

        self.file_management_widget = FileManagementWidget(parent=self)
        activity_layout.addWidget(self.file_management_widget)

        # Clear buttons row
        clear_layout = QHBoxLayout()
        clear_layout.addStretch()

        self.clear_markers_btn = QPushButton(ButtonText.CLEAR_MARKERS)
        self.clear_markers_btn.setStyleSheet("""
            QPushButton {
                background-color: #f39c12;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: none;
            }
            QPushButton:hover {
                background-color: #d68910;
            }
        """)
        self.clear_markers_btn.setToolTip("Clear all sleep markers and metrics (preserves imported data)")
        self.clear_markers_btn.clicked.connect(self.app_state.clear_all_markers)
        clear_layout.addWidget(self.clear_markers_btn)

        clear_activity_btn = self._create_clear_button(
            ButtonText.CLEAR_ACTIVITY_DATA,
            "Clear all imported activity data, sleep markers, and metrics",
            self._clear_activity_data,
        )
        clear_layout.addWidget(clear_activity_btn)

        activity_layout.addLayout(clear_layout)

        return self.activity_group

    def _create_nwt_data_section(self) -> QGroupBox:
        """Create NWT Sensor Data section."""
        nwt_group = QGroupBox("NWT Sensor Data (Nonwear Detection)")
        nwt_layout = QVBoxLayout(nwt_group)

        # Import section
        import_label = QLabel("<b>Import NWT Data:</b>")
        nwt_layout.addWidget(import_label)

        import_layout = QHBoxLayout()
        import_layout.addWidget(QLabel("Files:"))

        self.nwt_import_files_label = self._create_path_label()
        import_layout.addWidget(self.nwt_import_files_label)

        self.nwt_browse_btn = QPushButton("Select Files...")
        # Signal forwarded to connector instead of direct main_window connection
        self.nwt_browse_btn.clicked.connect(lambda: self.browseNonwearFilesRequested.emit())
        import_layout.addWidget(self.nwt_browse_btn)

        self.nwt_import_btn = QPushButton("Import")
        self.nwt_import_btn.setEnabled(False)
        self.nwt_import_btn.setToolTip("Select NWT sensor data files to enable import")
        # Signal forwarded to connector instead of direct main_window connection
        self.nwt_import_btn.clicked.connect(lambda: self.startNonwearImportRequested.emit())
        self.nwt_import_btn.setStyleSheet("""
            QPushButton:enabled {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
            }
            QPushButton:enabled:hover {
                background-color: #229954;
            }
        """)
        import_layout.addWidget(self.nwt_import_btn)

        nwt_layout.addLayout(import_layout)

        # Progress components - initially hidden
        self.nwt_progress_label = QLabel("Ready to import NWT data")
        self.nwt_progress_label.setVisible(False)
        nwt_layout.addWidget(self.nwt_progress_label)

        self.nwt_progress_bar = QProgressBar()
        self.nwt_progress_bar.setRange(0, 100)
        self.nwt_progress_bar.setMinimumHeight(20)
        self.nwt_progress_bar.setVisible(False)
        nwt_layout.addWidget(self.nwt_progress_bar)

        # Status label
        self.nwt_status_label = QLabel("")
        self.nwt_status_label.setStyleSheet("color: #666; font-size: 10px;")
        self.nwt_status_label.setWordWrap(True)
        nwt_layout.addWidget(self.nwt_status_label)

        # Clear button
        clear_layout = QHBoxLayout()
        clear_layout.addStretch()

        clear_nwt_btn = self._create_clear_button(
            ButtonText.CLEAR_NWT_DATA,
            "Clear all imported NWT sensor data",
            self._clear_nwt_data,
        )
        clear_layout.addWidget(clear_nwt_btn)

        nwt_layout.addLayout(clear_layout)

        return nwt_group

    def _create_diary_data_section(self) -> QGroupBox:
        """Create Diary Data section."""
        diary_group = QGroupBox("Sleep Diary Data (.xlsx/.csv files)")
        diary_layout = QVBoxLayout(diary_group)

        # Import section
        diary_layout.addWidget(self._create_section_separator())
        import_label = QLabel("<b>Import Diary Data:</b>")
        diary_layout.addWidget(import_label)

        # File selection
        import_file_row = QHBoxLayout()
        import_file_row.addWidget(QLabel("Files:"))

        self.diary_import_files_label = QLabel("No files selected")
        self.diary_import_files_label.setStyleSheet("color: #666;")
        self.diary_import_files_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.diary_import_files_label.setMinimumWidth(100)
        self.diary_import_files_label.setMaximumWidth(350)
        import_file_row.addWidget(self.diary_import_files_label)

        self.diary_import_browse_btn = QPushButton("Browse...")
        self.diary_import_browse_btn.clicked.connect(self._select_diary_import_files)
        import_file_row.addWidget(self.diary_import_browse_btn)

        self.diary_import_btn = QPushButton("Import")
        self.diary_import_btn.clicked.connect(self._import_diary_data)
        self.diary_import_btn.setEnabled(False)
        self.diary_import_btn.setToolTip("Select diary files to enable import")
        self.diary_import_btn.setStyleSheet("""
            QPushButton:enabled {
                background-color: #27ae60;
                color: white;
                font-weight: bold;
            }
            QPushButton:enabled:hover {
                background-color: #229954;
            }
        """)
        import_file_row.addWidget(self.diary_import_btn)

        diary_layout.addLayout(import_file_row)

        # Progress components - initially hidden (matching activity/nonwear pattern)
        self.diary_progress_label = QLabel(InfoMessage.READY_TO_IMPORT)
        self.diary_progress_label.setVisible(False)
        diary_layout.addWidget(self.diary_progress_label)

        self.diary_progress = QProgressBar()
        self.diary_progress.setVisible(False)
        diary_layout.addWidget(self.diary_progress)

        # Status label
        self.diary_status_label = QLabel("")
        self.diary_status_label.setStyleSheet("color: #666; font-size: 10px;")
        self.diary_status_label.setWordWrap(True)
        diary_layout.addWidget(self.diary_status_label)

        # Clear button
        clear_layout = QHBoxLayout()
        clear_layout.addStretch()

        clear_diary_btn = self._create_clear_button(
            ButtonText.CLEAR_DIARY_DATA,
            "Clear all imported diary data",
            self._clear_diary_data,
        )
        clear_layout.addWidget(clear_diary_btn)

        diary_layout.addLayout(clear_layout)

        return diary_group

    def _create_clear_button(self, text: str, tooltip: str, click_handler) -> QPushButton:
        """Create a standardized clear button with consistent styling."""
        button = QPushButton(text)
        button.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border: none;
                border-radius: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #c0392b;
            }
            QPushButton:pressed {
                background-color: #a93226;
            }
        """)
        button.setToolTip(tooltip)
        button.clicked.connect(click_handler)
        return button

    def _update_column_mapping_status(self) -> None:
        """Update the column mapping status label."""
        config = self._config

        if config.device_preset != DevicePreset.GENERIC_CSV.value:
            self.column_mapping_status.setText("")
            self.column_mapping_status.setVisible(False)
            return

        self.column_mapping_status.setVisible(True)

        if config.custom_activity_column:
            if config.datetime_combined:
                status = f"Columns: datetime={config.custom_date_column}, activity={config.custom_activity_column}"
            else:
                status = f"Columns: date={config.custom_date_column}, time={config.custom_time_column}, activity={config.custom_activity_column}"
            self.column_mapping_status.setText(f"✓ {status}")
            self.column_mapping_status.setStyleSheet("color: #27ae60; font-size: 10px; padding-left: 5px;")
        else:
            self.column_mapping_status.setText("⚠ Column mapping not configured - click 'Configure Columns...'")
            self.column_mapping_status.setStyleSheet("color: #e67e22; font-size: 10px; padding-left: 5px;")

    # Settings change handlers
    def _on_device_preset_changed(self, index: int) -> None:
        """Handle device preset selection change."""
        preset = self.device_preset_combo.itemData(index)

        # Enable/disable Configure Columns button based on preset
        self.configure_columns_btn.setEnabled(preset == DevicePreset.GENERIC_CSV.value)

        # Update column mapping status
        self._update_column_mapping_status()

        # Emit signal - connector persists to config
        self.dataSettingChanged.emit("device_preset", preset)

    def _on_data_source_changed(self, index: int) -> None:
        """Handle data source type selection change."""
        loader_id = self.data_source_combo.itemData(index)

        # Emit signal - connector persists to config
        self.dataSettingChanged.emit("data_source_type_id", loader_id)

        # Update visibility of data source specific sections
        self._update_data_source_visibility()

    def _update_data_source_visibility(self) -> None:
        """Update visibility of data source specific option sections."""
        current_index = self.data_source_combo.currentIndex()
        loader_id = self.data_source_combo.itemData(current_index)

        is_csv = loader_id == DataSourceType.CSV
        is_gt3x = loader_id == DataSourceType.GT3X

        self.csv_options_widget.setVisible(is_csv)
        self.gt3x_options_widget.setVisible(is_gt3x)

    def update_loaders_for_paradigm(self, paradigm: StudyDataParadigm | None = None) -> None:
        """Filter available data loaders based on the current data paradigm."""
        try:
            if paradigm is None:
                # Use current paradigm from config via services
                config = self._config_or_none
                if config is not None:
                    paradigm_val = config.data_paradigm
                    paradigm = StudyDataParadigm(paradigm_val)
                else:
                    paradigm = StudyDataParadigm.get_default()
            elif isinstance(paradigm, str):
                paradigm = StudyDataParadigm(paradigm)
        except Exception as e:
            logger.warning(f"Error getting current paradigm: {e}")
            paradigm = StudyDataParadigm.get_default()

        # Store current selection to try to restore it
        current_loader_id = self.data_source_combo.currentData()

        # Block signals during update
        self.data_source_combo.blockSignals(True)
        try:
            self.data_source_combo.clear()

            # Get all available loaders
            available_loaders = DataSourceFactory.get_available_loaders()

            # Filter loaders based on paradigm
            if paradigm == StudyDataParadigm.EPOCH_BASED:
                # Epoch-based: only CSV loader (GT3X requires raw processing)
                filtered_loaders = {k: v for k, v in available_loaders.items() if k == DataSourceType.CSV}
            else:
                # Raw accelerometer: all loaders available
                filtered_loaders = available_loaders

            # Populate combo with filtered loaders
            for loader_id, display_name in filtered_loaders.items():
                self.data_source_combo.addItem(display_name, loader_id)

            # Try to restore previous selection if still available
            restored = False
            if current_loader_id:
                for i in range(self.data_source_combo.count()):
                    if self.data_source_combo.itemData(i) == current_loader_id:
                        self.data_source_combo.setCurrentIndex(i)
                        restored = True
                        break

            # If previous selection not available, select first item
            if not restored and self.data_source_combo.count() > 0:
                self.data_source_combo.setCurrentIndex(0)
                new_loader_id = self.data_source_combo.currentData()

                # Emit signal - connector persists to config
                self.dataSettingChanged.emit("data_source_type_id", new_loader_id)
        finally:
            self.data_source_combo.blockSignals(False)

        # Update visibility of loader-specific options
        self._update_data_source_visibility()

        # Update paradigm indicator
        if self.paradigm_indicator_label is not None:
            self._update_paradigm_indicator_label(paradigm)

        # Update Activity Data GroupBox title
        if self.activity_group is not None:
            if paradigm == StudyDataParadigm.EPOCH_BASED:
                self.activity_group.setTitle("Activity Data (CSV/Excel with epoch counts)")
            else:
                self.activity_group.setTitle("Activity Data (GT3X or raw CSV files)")

        logger.info("Updated data source loaders for paradigm: %s", paradigm.name)

    def _on_gt3x_epoch_length_changed(self, value: int) -> None:
        """Handle GT3X epoch length spin box change."""
        # Emit signal - connector persists to config
        self.dataSettingChanged.emit("gt3x_epoch_length", value)

    def _on_gt3x_return_raw_changed(self, state: int) -> None:
        """Handle GT3X return raw check box change."""
        # Emit signal - connector persists to config
        self.dataSettingChanged.emit("gt3x_return_raw", bool(state))

    def _open_column_mapping_dialog(self) -> None:
        """Open the column mapping configuration dialog."""
        # TODO(refactor): pattern-violation Passes config_manager directly to ColumnMappingDialog constructor
        # Try to get a sample file from selected files via services interface
        sample_file: Path | None = None
        selected_files = getattr(self.services, "_selected_activity_files", None)
        config = self._config_or_none
        if selected_files:
            # Use one of the selected files
            csv_files = [f for f in selected_files if f.suffix.lower() == ".csv"]
            if csv_files:
                sample_file = random.choice(csv_files)
        elif config is not None and config.import_activity_directory:
            # Fall back to import directory
            folder = Path(config.import_activity_directory)
            if folder.exists():
                csv_files = list(folder.glob("*.csv"))
                if csv_files:
                    sample_file = random.choice(csv_files)

        dialog = ColumnMappingDialog(self, self.services.config_manager, sample_file)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Update status after dialog closed
            self._update_column_mapping_status()

    def _autodetect_device_format(self) -> None:
        """Auto-detect device format from CSV file."""
        from sleep_scoring_app.services.format_detector import FormatDetector

        # Get sample CSV files
        csv_files = self._get_sample_csv_files()
        if not csv_files:
            QMessageBox.warning(self, "No CSV Files", "Please select CSV files first.")
            return

        sample_file = random.choice(csv_files)
        detector = FormatDetector()

        try:
            device_preset, confidence = detector.detect_device_format(sample_file)

            confidence_pct = int(confidence * 100)
            color = "#27ae60" if confidence >= 0.7 else "#f39c12" if confidence >= 0.5 else "#e74c3c"

            # Get display name
            device_names = {
                DevicePreset.ACTIGRAPH: "ActiGraph",
                DevicePreset.GENEACTIV: "GENEActiv",
                DevicePreset.AXIVITY: "Axivity",
                DevicePreset.ACTIWATCH: "Actiwatch",
                DevicePreset.MOTIONWATCH: "MotionWatch",
                DevicePreset.GENERIC_CSV: "Generic CSV",
            }
            device_name = device_names.get(device_preset, str(device_preset))

            reply = QMessageBox.question(
                self,
                "Device Format Detected",
                f"Detected: <b>{device_name}</b><br>"
                f"Confidence: <span style='color:{color}'><b>{confidence_pct}%</b></span><br><br>"
                f"Sample file: {sample_file.name}<br><br>"
                "Apply this value?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Find and select the detected preset
                for i in range(self.device_preset_combo.count()):
                    if self.device_preset_combo.itemData(i) == device_preset.value:
                        self.device_preset_combo.setCurrentIndex(i)
                        break

        except Exception as e:
            QMessageBox.critical(self, "Detection Error", f"Failed to detect device format: {e}")
            logger.exception("Failed to detect device format")

    def _autodetect_epoch_length(self) -> None:
        """Auto-detect epoch length from CSV file."""
        from sleep_scoring_app.services.format_detector import FormatDetector

        # Get sample CSV files
        csv_files = self._get_sample_csv_files()
        if not csv_files:
            QMessageBox.warning(self, "No CSV Files", "Please select CSV files first.")
            return

        sample_file = random.choice(csv_files)
        detector = FormatDetector()

        try:
            skip_rows = self.skip_rows_spin.value()
            epoch_length, confidence = detector.detect_epoch_length(sample_file, skip_rows)

            confidence_pct = int(confidence * 100)
            color = "#27ae60" if confidence >= 0.9 else "#f39c12" if confidence >= 0.7 else "#e74c3c"

            reply = QMessageBox.question(
                self,
                "Epoch Length Detected",
                f"Detected: <b>{epoch_length} seconds</b><br>"
                f"Confidence: <span style='color:{color}'><b>{confidence_pct}%</b></span><br><br>"
                f"Sample file: {sample_file.name}<br><br>"
                "Apply this value?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.epoch_length_spin.setValue(epoch_length)

        except Exception as e:
            QMessageBox.critical(self, "Detection Error", f"Failed to detect epoch length: {e}")
            logger.exception("Failed to detect epoch length")

    def _autodetect_skip_rows(self) -> None:
        """Auto-detect number of rows to skip."""
        from sleep_scoring_app.services.format_detector import FormatDetector

        # Get sample CSV files
        csv_files = self._get_sample_csv_files()
        if not csv_files:
            QMessageBox.warning(self, "No CSV Files", "Please select CSV files first.")
            return

        sample_file = random.choice(csv_files)
        detector = FormatDetector()

        try:
            skip_rows, confidence = detector.detect_header_rows(sample_file)

            confidence_pct = int(confidence * 100)
            color = "#27ae60" if confidence >= 0.9 else "#f39c12" if confidence >= 0.7 else "#e74c3c"

            reply = QMessageBox.question(
                self,
                "Header Rows Detected",
                f"Detected: <b>{skip_rows} header rows</b><br>"
                f"Confidence: <span style='color:{color}'><b>{confidence_pct}%</b></span><br><br>"
                f"Sample file: {sample_file.name}<br><br>"
                "Apply this value?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.skip_rows_spin.setValue(skip_rows)

        except Exception as e:
            QMessageBox.critical(self, "Detection Error", f"Failed to detect header rows: {e}")
            logger.exception("Failed to detect header rows")

    def _autodetect_all(self) -> None:
        """Auto-detect all settings at once."""
        from sleep_scoring_app.services.format_detector import FormatDetector

        # Get sample CSV files
        csv_files = self._get_sample_csv_files()
        if not csv_files:
            QMessageBox.warning(self, "No CSV Files", "Please select CSV files first.")
            return

        sample_file = random.choice(csv_files)
        detector = FormatDetector()

        try:
            # Detect all three
            skip_rows, skip_conf = detector.detect_header_rows(sample_file)
            epoch_length, epoch_conf = detector.detect_epoch_length(sample_file, skip_rows)
            device_preset, device_conf = detector.detect_device_format(sample_file)

            # Get device display name
            device_names = {
                DevicePreset.ACTIGRAPH: "ActiGraph",
                DevicePreset.GENEACTIV: "GENEActiv",
                DevicePreset.AXIVITY: "Axivity",
                DevicePreset.ACTIWATCH: "Actiwatch",
                DevicePreset.MOTIONWATCH: "MotionWatch",
                DevicePreset.GENERIC_CSV: "Generic CSV",
            }
            device_name = device_names.get(device_preset, str(device_preset))

            def conf_color(conf: float) -> str:
                if conf >= 0.8:
                    return "#27ae60"
                if conf >= 0.6:
                    return "#f39c12"
                return "#e74c3c"

            message = (
                f"<b>Auto-Detection Results</b><br><br>"
                f"Sample file: {sample_file.name}<br><br>"
                f"<b>Device:</b> {device_name} "
                f"<span style='color:{conf_color(device_conf)}'>[{int(device_conf * 100)}%]</span><br>"
                f"<b>Skip Rows:</b> {skip_rows} "
                f"<span style='color:{conf_color(skip_conf)}'>[{int(skip_conf * 100)}%]</span><br>"
                f"<b>Epoch Length:</b> {epoch_length}s "
                f"<span style='color:{conf_color(epoch_conf)}'>[{int(epoch_conf * 100)}%]</span><br><br>"
                f"Apply these values?"
            )

            reply = QMessageBox.question(
                self,
                "Auto-Detection Results",
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Apply all values
                self.skip_rows_spin.setValue(skip_rows)
                self.epoch_length_spin.setValue(epoch_length)
                for i in range(self.device_preset_combo.count()):
                    if self.device_preset_combo.itemData(i) == device_preset.value:
                        self.device_preset_combo.setCurrentIndex(i)
                        break

        except Exception as e:
            QMessageBox.critical(self, "Detection Error", f"Auto-detection failed: {e}")
            logger.exception("Auto-detection failed")

    def _get_sample_csv_files(self) -> list[Path]:
        """Get CSV files for sampling - from selected files or fallback to directories."""
        # Try selected activity files first via services interface
        selected_files = getattr(self.services, "_selected_activity_files", None)
        if selected_files:
            csv_files = [f for f in selected_files if f.suffix.lower() == ".csv"]
            if csv_files:
                return csv_files

        config = self._config_or_none
        if config is None:
            return []

        # Fall back to config import directory via services
        if config.import_activity_directory:
            folder = Path(config.import_activity_directory)
            if folder.exists():
                csv_files = list(folder.glob("*.csv"))
                if csv_files:
                    return csv_files

        # Fall back to config data folder via services
        if config.data_folder:
            folder = Path(config.data_folder)
            if folder.exists():
                csv_files = list(folder.glob("*.csv"))
                if csv_files:
                    return csv_files

        return []

    # Diary import methods
    def _select_diary_import_files(self) -> None:
        """Select diary files for import to database."""
        # Start from last used diary directory via services
        config = self._config_or_none
        start_dir = (config.diary_import_directory if config else None) or str(Path.home())
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Diary Files to Import",
            start_dir,
            "Excel and CSV files (*.xlsx *.xls *.csv);;Excel files (*.xlsx *.xls);;CSV files (*.csv)",
        )

        if files:
            self.selected_diary_files = [Path(f) for f in files]
            if len(files) == 1:
                self.diary_import_files_label.setText(f"1 file: {Path(files[0]).name}")
            else:
                self.diary_import_files_label.setText(f"{len(files)} files selected")
            self.diary_import_files_label.setStyleSheet("color: #333;")
            self.diary_import_btn.setEnabled(True)

            # Save the directory of the first selected file for next time
            if config is not None:
                from dataclasses import replace

                first_file_dir = str(Path(files[0]).parent)
                self.services.config_manager.config = replace(config, diary_import_directory=first_file_dir)
                self.services.config_manager.save_config()
        else:
            self.selected_diary_files = []
            self.diary_import_files_label.setText("No files selected")
            self.diary_import_files_label.setStyleSheet("color: #666;")
            self.diary_import_btn.setEnabled(False)

    def _import_diary_data(self) -> None:
        """Import diary data using selected files."""
        logger.info("=== DIARY IMPORT START ===")
        logger.info(f"Selected diary files: {self.selected_diary_files}")

        if not self.selected_diary_files:
            logger.warning("No diary files selected")
            self._show_diary_status("No files selected", error=True)
            return

        # Start import process
        logger.info(f"Importing {len(self.selected_diary_files)} diary files...")
        self.diary_import_btn.setEnabled(False)
        self.diary_import_btn.setText("Import in Progress...")
        self.diary_progress_label.setText("Starting import...")
        self.diary_progress_label.setVisible(True)
        self.diary_progress.setVisible(True)
        self.diary_progress.setRange(0, 0)  # Indeterminate progress

        try:
            # Use the simplified diary service for import via services interface
            diary_service = self.services.data_service.diary_service if self.services.data_service else None

            if diary_service:
                logger.info("Calling diary_service.import_diary_files()...")
                result = diary_service.import_diary_files(
                    self.selected_diary_files,
                    progress_callback=self._on_diary_import_progress,
                )
                logger.info(
                    f"Diary import result: successful={len(result.successful_files)}, failed={len(result.failed_files)}, entries={result.total_entries_imported}"
                )

                # Show results
                if result.successful_files:
                    success_msg = f"Successfully imported {len(result.successful_files)} files with {result.total_entries_imported} entries"
                    self._show_diary_status(success_msg)

                    # Show success confirmation dialog
                    QMessageBox.information(
                        self,
                        "Import Successful",
                        f"Successfully imported {len(result.successful_files)} diary file(s) with {result.total_entries_imported} entries.",
                    )

                    # Clear selections after successful import
                    self.selected_diary_files = []
                    self.diary_import_files_label.setText("No files selected")
                    self.diary_import_files_label.setStyleSheet("color: #666;")

                    # Refresh file list via signal (connector handles dispatch)
                    self.refreshFilesRequested.emit()
                else:
                    self._show_diary_status("Import failed - no files processed successfully", error=True)

                if result.failed_files:
                    # Format error messages more clearly
                    error_messages = []
                    for file_path, error_msg in result.failed_files[:3]:  # Show first 3 errors
                        file_name = Path(file_path).name
                        error_messages.append(f"{file_name}: {error_msg}")

                    error_details = "; ".join(error_messages)
                    if len(result.failed_files) > 3:
                        error_details += f" (and {len(result.failed_files) - 3} more)"

                    self._show_diary_status(f"Some files failed: {error_details}", error=True)
            elif not self.services.data_service:
                self._show_diary_status("Main data service not initialized", error=True)
                logger.error("Services data_service is None")
            else:
                self._show_diary_status("Diary service not initialized in data service", error=True)
                logger.error("data_service.diary_service is None")

        except Exception as e:
            logger.exception("Diary import failed with exception: %s", e)
            self._show_diary_status(f"Import error: {e!s}", error=True)

        finally:
            self.diary_import_btn.setEnabled(bool(self.selected_diary_files))
            self.diary_import_btn.setText("Import")
            self.diary_progress_label.setText("Import completed")
            QTimer.singleShot(3000, self._hide_diary_progress_components)

    def _on_diary_import_progress(self, message: str, current: int, total: int) -> None:
        """Handle diary import progress updates."""
        self.diary_progress_label.setText(message)
        if total > 0:
            self.diary_progress.setRange(0, total)
            self.diary_progress.setValue(current)

    def _hide_diary_progress_components(self) -> None:
        """Hide diary progress components after import completion."""
        try:
            self.diary_progress_label.setVisible(False)
            self.diary_progress.setVisible(False)
        except RuntimeError:
            pass  # Widget may have been deleted

    def _show_activity_status(self, message: str, error: bool = False) -> None:
        """Show status message for activity data import."""
        # activity_status_label is always created in _create_activity_data_section()
        self.activity_status_label.setText(message)
        if error:
            self.activity_status_label.setStyleSheet("color: #d32f2f; font-size: 10px;")
        else:
            self.activity_status_label.setStyleSheet("color: #666; font-size: 10px;")

    def _show_nwt_status(self, message: str, error: bool = False) -> None:
        """Show status message for NWT sensor data import."""
        # nwt_status_label is always created in _create_nwt_data_section()
        self.nwt_status_label.setText(message)
        if error:
            self.nwt_status_label.setStyleSheet("color: #d32f2f; font-size: 10px;")
        else:
            self.nwt_status_label.setStyleSheet("color: #666; font-size: 10px;")

    def _show_diary_status(self, message: str, error: bool = False) -> None:
        """Show status message for diary import."""
        self.diary_status_label.setText(message)
        if error:
            self.diary_status_label.setStyleSheet("color: #d32f2f; font-size: 10px;")
        else:
            self.diary_status_label.setStyleSheet("color: #666; font-size: 10px;")

    # Clear data methods
    def _clear_activity_data(self) -> None:
        """
        Clear all activity data from the database.

        Architecture: Widget dispatches action → Effect handler performs side effect.
        """
        from PyQt6.QtWidgets import QMessageBox

        # Confirmation dialog (consistent with other clear buttons)
        reply = QMessageBox.question(
            self,
            "Clear Activity Data",
            "Are you sure you want to clear ALL activity data?\n\n"
            "This will remove all imported data, sleep markers, and metrics.\n"
            "This action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        # Emit signal - connector dispatches the action to the store
        self.clearActivityDataRequested.emit()

    def _clear_nwt_data(self) -> None:
        """Clear all imported NWT sensor data from database."""
        reply = QMessageBox.question(
            self,
            "Clear NWT Data",
            "Are you sure you want to clear all NWT sensor data?\n\nThis action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            # Emit signal - connector handles the actual clearing
            self.clearNwtDataRequested.emit()

    def _clear_diary_data(self) -> None:
        """Clear all imported diary data from database."""
        reply = QMessageBox.question(
            self,
            "Clear Diary Data",
            "Are you sure you want to clear all imported diary data?\n\n"
            "This will remove:\n"
            "- All diary entries\n"
            "- All raw diary import data\n"
            "- This action cannot be undone!",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.clearDiaryDataRequested.emit()
