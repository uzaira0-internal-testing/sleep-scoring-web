#!/usr/bin/env python3
"""
Analysis Tab Component
Contains the main analysis interface with plots and controls.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from sleep_scoring_app.ui.utils.thread_safety import ensure_main_thread
from sleep_scoring_app.ui.widgets.file_selection_table import FileSelectionTable
from sleep_scoring_app.ui.widgets.no_scroll_widgets import NoScrollComboBox
from sleep_scoring_app.ui.widgets.popout_table_window import PopOutTableWindow

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import (
        AppStateInterface,
        MarkerOperationsInterface,
        NavigationInterface,
        ServiceContainer,
    )
    from sleep_scoring_app.ui.store import UIStore

from sleep_scoring_app.core.algorithms.nonwear.protocol import NonwearDetectionAlgorithm
from sleep_scoring_app.core.algorithms.sleep_period.protocol import SleepPeriodDetector
from sleep_scoring_app.core.algorithms.sleep_wake.protocol import SleepScoringAlgorithm
from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    ButtonStyle,
    ButtonText,
    DiaryTableColumn,
    MarkerCategory,
    MarkerType,
    TooltipText,
    UIColors,
)
from sleep_scoring_app.core.dataclasses import AppConfig, SleepPeriod
from sleep_scoring_app.ui.coordinators import DiaryTableConnector, SeamlessSourceSwitcher, TimeFieldCoordinator
from sleep_scoring_app.ui.coordinators.analysis_dialog_coordinator import AnalysisDialogCoordinator
from sleep_scoring_app.ui.utils.table_helpers import create_marker_data_table
from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

logger = logging.getLogger(__name__)


@dataclass
class DiaryColumnDefinition:
    """Definition for a diary table column."""

    id: DiaryTableColumn
    header: str
    width_mode: QHeaderView.ResizeMode
    width_hint: int | None = None
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignCenter


class AnalysisTab(QWidget):
    """Analysis Tab containing the main analysis interface."""

    # Navigation request signals - emitted when user clicks navigation buttons
    # NavigationGuardConnector intercepts these to check for unsaved markers
    prevDateRequested = pyqtSignal()
    nextDateRequested = pyqtSignal()
    dateSelectRequested = pyqtSignal(int)

    # Control change signals - AnalysisTabConnector dispatches to store
    activitySourceChanged = pyqtSignal(object)  # ActivityDataPreference enum
    viewModeChanged = pyqtSignal(int)  # hours (24 or 48)
    adjacentMarkersToggled = pyqtSignal(bool)
    autoSaveToggled = pyqtSignal(bool)
    markerModeChanged = pyqtSignal(object)  # MarkerCategory enum
    consensusFlagToggled = pyqtSignal(bool)  # Needs consensus review flag

    # Marker operation signals - AnalysisTabConnector delegates to marker_ops
    saveMarkersRequested = pyqtSignal()
    noSleepRequested = pyqtSignal()
    clearMarkersRequested = pyqtSignal()

    def __init__(
        self,
        store: "UIStore",
        navigation: "NavigationInterface",
        marker_ops: "MarkerOperationsInterface",
        app_state: "AppStateInterface",
        services: "ServiceContainer",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.store = store
        self.navigation = navigation
        self.marker_ops = marker_ops
        self.app_state = app_state
        self.services = services

        # Pop-out table windows
        self.onset_popout_window: PopOutTableWindow | None = None
        self.offset_popout_window: PopOutTableWindow | None = None

        # Dialog manager for shortcuts and color settings
        self.dialog_manager = AnalysisDialogCoordinator(
            store=self.store,
            navigation=self.navigation,
            marker_ops=self.marker_ops,
            app_state=self.app_state,
            services=self.services,
            parent_tab=self,
        )

        # Managers (initialized after setup_ui creates widgets they depend on)
        self.seamless_source_switcher: SeamlessSourceSwitcher | None = None
        self.diary_table_connector: DiaryTableConnector | None = None
        self.time_field_coordinator: TimeFieldCoordinator | None = None

        self.setup_ui()

    def setup_ui(self) -> None:
        """Create the analysis tab UI."""
        logger.debug("=== AnalysisTab.setup_ui() START ===")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create scroll area for the entire content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Remove frame for cleaner look

        # Create content widget that will be scrollable
        content_widget = QWidget()
        content_widget.setMinimumHeight(1000)  # Force minimum height to ensure scrollbar appears
        content_layout = QVBoxLayout(content_widget)

        # Activity plot (create first so control panel can reference it)
        self.plot_widget = ActivityPlotWidget(
            main_window=self.app_state,
            parent=self,
            get_axis_y_data_for_sadeh=self.app_state._get_axis_y_data_for_sadeh,
            get_selected_file=lambda: self.app_state.selected_file,
            create_nonwear_algorithm=self._create_nonwear_algorithm,
            create_sleep_algorithm=self._create_sleep_algorithm,
            create_sleep_period_detector=self._create_sleep_period_detector,
            get_default_sleep_algorithm_id=self._get_default_sleep_algorithm_id,
            get_default_sleep_period_detector_id=self._get_default_sleep_period_detector_id,
            get_choi_activity_column=self._get_choi_activity_column,
            get_algorithm_config=self._get_algorithm_config,
        )

        # Create top-level vertical splitter to separate file selection from plot area
        # Store as instance variable for layout persistence
        self.top_level_splitter = QSplitter(Qt.Orientation.Vertical)
        top_level_splitter = self.top_level_splitter

        # File selection bar
        file_bar = self._create_file_selection_bar()
        top_level_splitter.addWidget(file_bar)

        # Create widget for navigation, controls, and plot area
        plot_area_widget = QWidget()
        plot_area_layout = QVBoxLayout(plot_area_widget)
        plot_area_layout.setContentsMargins(0, 0, 0, 0)

        # Date navigation bar (centered)
        date_bar = self._create_date_navigation_bar()
        plot_area_layout.addWidget(date_bar)

        # Control bar (view mode and manual times)
        control_bar = self._create_control_bar()
        plot_area_layout.addWidget(control_bar)

        # Create vertical splitter for plot area and diary table
        # Store as instance variable for layout persistence
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter = self.main_splitter

        # Create horizontal splitter for plot and data tables (top section)
        # This allows users to resize the side tables by dragging
        # Store as instance variable for layout persistence
        self.plot_and_tables_splitter = QSplitter(Qt.Orientation.Horizontal)
        plot_and_tables_splitter = self.plot_and_tables_splitter
        plot_and_tables_splitter.setChildrenCollapsible(False)
        plot_and_tables_splitter.setHandleWidth(6)

        # Style the horizontal splitter handles
        plot_and_tables_splitter.setStyleSheet("""
            QSplitter::handle:horizontal {
                background-color: #c0c0c0;
                border: 1px solid #a0a0a0;
                width: 6px;
            }
            QSplitter::handle:horizontal:hover {
                background-color: #a0a0ff;
                border: 1px solid #7070ff;
            }
            QSplitter::handle:horizontal:pressed {
                background-color: #7070ff;
                border: 1px solid #4040ff;
            }
        """)

        # Left data table (onset/first marker) - resizable via splitter
        # Create wrapper to place button outside table container
        onset_wrapper = QWidget()
        onset_wrapper_layout = QVBoxLayout(onset_wrapper)
        onset_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        onset_wrapper_layout.setSpacing(2)

        # Add pop-out button above the table (center-aligned)
        onset_button_layout = QHBoxLayout()
        onset_button_layout.setContentsMargins(5, 0, 5, 2)
        self.onset_popout_button = QPushButton("⬈ Pop Out")
        self.onset_popout_button.setMaximumWidth(80)
        self.onset_popout_button.setFixedHeight(22)
        self.onset_popout_button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2868a8;
            }
        """)
        onset_button_layout.addStretch()
        onset_button_layout.addWidget(self.onset_popout_button)
        onset_button_layout.addStretch()
        onset_wrapper_layout.addLayout(onset_button_layout)

        # Add the table to the wrapper
        # Get the algorithm name from config for dynamic column header
        sleep_algorithm_name = self._get_sleep_algorithm_display_name()
        self.onset_table = create_marker_data_table("Sleep Onset Data", sleep_algorithm_name)
        onset_wrapper_layout.addWidget(self.onset_table)

        # Set minimum and preferred width for onset wrapper
        onset_wrapper.setMinimumWidth(280)
        plot_and_tables_splitter.addWidget(onset_wrapper)

        # Connect onset pop-out button
        self.onset_popout_button.clicked.connect(self._on_onset_popout_clicked)

        # Center widget containing filename label and plot
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(2)

        # Create filename label above the plot
        self.filename_label = QLabel("")
        self.filename_label.setStyleSheet("""
            QLabel {
                font-size: 11pt;
                font-weight: bold;
                color: #333;
                padding: 2px 5px;
                background-color: #f0f0f0;
                border: 1px solid #ddd;
                border-radius: 3px;
            }
        """)
        self.filename_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(self.filename_label)

        # Add plot widget below the label
        center_layout.addWidget(self.plot_widget, stretch=1)

        # Pass the filename label reference to the plot widget
        self.plot_widget.external_filename_label = self.filename_label

        # Add center widget to the splitter - takes remaining space
        center_widget.setMinimumWidth(400)
        plot_and_tables_splitter.addWidget(center_widget)

        # Right data table (offset/last marker) - resizable via splitter
        # Create wrapper to place button outside table container
        offset_wrapper = QWidget()
        offset_wrapper_layout = QVBoxLayout(offset_wrapper)
        offset_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        offset_wrapper_layout.setSpacing(2)

        # Add pop-out button above the table (center-aligned)
        offset_button_layout = QHBoxLayout()
        offset_button_layout.setContentsMargins(5, 0, 5, 2)
        self.offset_popout_button = QPushButton("⬈ Pop Out")
        self.offset_popout_button.setMaximumWidth(80)
        self.offset_popout_button.setFixedHeight(22)
        self.offset_popout_button.setStyleSheet("""
            QPushButton {
                background-color: #4a90e2;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 3px 8px;
                font-size: 9pt;
            }
            QPushButton:hover {
                background-color: #357abd;
            }
            QPushButton:pressed {
                background-color: #2868a8;
            }
        """)
        offset_button_layout.addStretch()
        offset_button_layout.addWidget(self.offset_popout_button)
        offset_button_layout.addStretch()
        offset_wrapper_layout.addLayout(offset_button_layout)

        # Add the table to the wrapper
        self.offset_table = create_marker_data_table("Sleep Offset Data", sleep_algorithm_name)
        offset_wrapper_layout.addWidget(self.offset_table)

        # Set minimum and preferred width for offset wrapper
        offset_wrapper.setMinimumWidth(280)
        plot_and_tables_splitter.addWidget(offset_wrapper)

        # Connect offset pop-out button
        self.offset_popout_button.clicked.connect(self._on_offset_popout_clicked)

        # Set initial sizes for horizontal splitter (side tables expanded to show all columns)
        # Left table: 380px, Plot: stretch, Right table: 380px (wider to show all columns)
        plot_and_tables_splitter.setSizes([380, 600, 380])
        plot_and_tables_splitter.setStretchFactor(0, 0)  # Left table fixed
        plot_and_tables_splitter.setStretchFactor(1, 1)  # Plot stretches
        plot_and_tables_splitter.setStretchFactor(2, 0)  # Right table fixed

        # Create diary table (bottom section)
        self.diary_table_widget = self._create_diary_table()

        # Add both sections to the vertical splitter
        main_splitter.addWidget(plot_and_tables_splitter)
        main_splitter.addWidget(self.diary_table_widget)

        # Configure splitter behavior
        main_splitter.setChildrenCollapsible(False)  # Prevent complete collapse, respect minimum sizes
        main_splitter.setHandleWidth(8)  # Make the splitter handle more visible

        # Add custom styling to make splitter handle more visible
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #b0b0ff;
                border: 1px solid #7070ff;
            }
            QSplitter::handle:hover {
                background-color: #9090ff;
                border: 1px solid #5050ff;
            }
            QSplitter::handle:pressed {
                background-color: #7070ff;
                border: 1px solid #4040ff;
            }
        """)

        # Set minimum sizes for both sections
        plot_and_tables_splitter.setMinimumHeight(200)  # Plot area minimum
        self.diary_table_widget.setMinimumHeight(100)  # Diary table minimum

        # Set initial splitter sizes (plot area gets more space initially)
        main_splitter.setSizes([500, 150])  # Plot area: 500px, Diary: 150px (reduced)
        main_splitter.setStretchFactor(0, 1)  # Plot area is stretchable
        main_splitter.setStretchFactor(1, 0)  # Diary table maintains proportional size

        # Add the main splitter to the plot area widget
        plot_area_layout.addWidget(main_splitter, stretch=1)

        # Add the plot area widget to the top-level splitter
        top_level_splitter.addWidget(plot_area_widget)

        # Configure top-level splitter behavior
        top_level_splitter.setChildrenCollapsible(False)  # Prevent complete collapse
        top_level_splitter.setHandleWidth(8)  # Make the splitter handle more visible

        # Add custom styling to make splitter handle more visible
        top_level_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #b0b0ff;
                border: 1px solid #7070ff;
            }
            QSplitter::handle:hover {
                background-color: #9090ff;
                border: 1px solid #5050ff;
            }
            QSplitter::handle:pressed {
                background-color: #7070ff;
                border: 1px solid #4040ff;
            }
        """)

        # Set minimum sizes for both sections of top-level splitter
        file_bar.setMinimumHeight(150)  # File selection minimum
        plot_area_widget.setMinimumHeight(300)  # Plot area minimum

        # Set initial top-level splitter sizes (file selection smaller, plot area larger)
        top_level_splitter.setSizes([250, 600])  # File selection: 250px, Plot area: 600px
        top_level_splitter.setStretchFactor(0, 0)  # File selection maintains fixed proportion
        top_level_splitter.setStretchFactor(1, 1)  # Plot area is stretchable

        # Add the top-level splitter to content layout
        content_layout.addWidget(top_level_splitter, stretch=1)

        # Set the content widget in the scroll area
        scroll_area.setWidget(content_widget)

        # Add scroll area to main layout
        layout.addWidget(scroll_area)

        # Hide diary section by default until we know participant has diary data
        self.diary_table_widget.setVisible(False)
        logger.debug("Diary table widget hidden by default")

        # Initialize managers now that widgets exist
        logger.debug("Initializing analysis tab managers...")
        self.seamless_source_switcher = SeamlessSourceSwitcher(
            store=self.store,
            data_service=self.services.data_service,
            config_manager=self.services.config_manager,
            plot_widget=self.plot_widget,
            available_dates=self.navigation.available_dates,
            set_pref_callback=self.app_state.set_activity_data_preferences,
            auto_save_callback=self.marker_ops.auto_save_current_markers,
            load_markers_callback=self.marker_ops.load_saved_markers,
            get_tab_dropdown_fn=lambda: self.activity_source_dropdown,
        )
        self.diary_table_connector = DiaryTableConnector(
            store=self.store,
            data_service=self.services.data_service,
            diary_coordinator=self.services.diary_coordinator,
            diary_table_widget=self.diary_table_widget,
        )
        self.time_field_coordinator = TimeFieldCoordinator(
            store=self.store,
            onset_time_input=self.onset_time_input,
            offset_time_input=self.offset_time_input,
            total_duration_label=self.total_duration_label,
            update_callback=self.marker_ops.set_manual_sleep_times,
        )
        logger.debug("Analysis tab managers initialized")

        # Initialize the activity source dropdown with current preferences
        # Use QTimer.singleShot to ensure parent window is fully initialized
        QTimer.singleShot(0, self.update_activity_source_dropdown)

        # Apply saved colors from settings (must be done after plot_widget is created)
        # Defer to ensure analysis_tab is fully initialized and parent can access plot_widget property
        QTimer.singleShot(0, self._apply_colors)
        logger.debug("=== AnalysisTab.setup_ui() COMPLETE ===")

    def _create_file_selection_bar(self) -> QFrame:
        """Create file selection bar with table widget."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)

        # File selection label with file count info
        self.file_selection_label = QLabel("File Selection")
        self.file_selection_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.file_selection_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.file_selection_label)

        # Store folder info label reference but don't display it
        # Keep it for compatibility with main_window.py update_folder_info_label
        self.folder_info_label = QLabel("")
        self.folder_info_label.setVisible(False)  # Hide it

        # File selection table
        self.file_selector = FileSelectionTable()
        self.file_selector.setMinimumHeight(200)
        self.file_selector.setMaximumHeight(300)

        layout.addWidget(self.file_selector)

        return panel

    def _create_date_navigation_bar(self) -> QFrame:
        """Create centered date navigation bar."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)
        panel.setMaximumHeight(60)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)

        # Add stretch to center content
        layout.addStretch()

        # Date navigation - buttons emit signals, NavigationGuardConnector handles dispatch
        self.prev_date_btn = QPushButton("◀ Previous")
        self.prev_date_btn.clicked.connect(self.prevDateRequested.emit)
        self.prev_date_btn.setEnabled(False)
        self.prev_date_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 16px;
                padding: 8px 16px;
            }}
            {ButtonStyle.FOCUS_STYLE}
        """)
        layout.addWidget(self.prev_date_btn)

        self.date_dropdown = NoScrollComboBox()
        # CSS text-align doesn't work for QListView items; centering uses AlignCenter via setItemData
        self.date_dropdown.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 20px 8px 20px;
                font-size: 16px;
                font-weight: bold;
                min-width: 120px;
            }}
            QComboBox:focus {{
                border: 2px solid {UIColors.FOCUS_BORDER};
                background-color: {UIColors.FOCUS_BACKGROUND};
            }}
            QComboBox QAbstractItemView::item {{
                padding: 8px;
            }}
        """)
        self.date_dropdown.setMaxVisibleItems(10)
        # Using a slot helper for dropdown to avoid direct parent dependency
        self.date_dropdown.currentIndexChanged.connect(self._on_date_selected)
        self.date_dropdown.setEnabled(False)

        # Center the text - make dropdown editable to access line edit for centering
        self.date_dropdown.setEditable(True)
        line_edit = self.date_dropdown.lineEdit()
        if line_edit:
            line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line_edit.setReadOnly(True)
            line_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            # Override the mouse press event to show popup
            original_mouse_press = line_edit.mousePressEvent

            def mouse_press_override(event) -> None:
                if event.button() == Qt.MouseButton.LeftButton:
                    self.date_dropdown.showPopup()
                else:
                    original_mouse_press(event)

            line_edit.mousePressEvent = mouse_press_override

        layout.addWidget(self.date_dropdown)

        self.next_date_btn = QPushButton("Next ▶")
        self.next_date_btn.clicked.connect(self.nextDateRequested.emit)
        self.next_date_btn.setEnabled(False)
        self.next_date_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 16px;
                padding: 8px 16px;
            }}
            {ButtonStyle.FOCUS_STYLE}
        """)
        layout.addWidget(self.next_date_btn)

        # Add stretch to center content
        layout.addStretch()

        return panel

    def _create_control_bar(self) -> QFrame:
        """Create control bar with two rows for better fit on smaller screens."""
        panel = QFrame()
        panel.setFrameStyle(QFrame.Shape.StyledPanel)

        # Use vertical layout for two rows
        main_layout = QVBoxLayout(panel)
        main_layout.setContentsMargins(10, 5, 10, 5)
        main_layout.setSpacing(5)

        row1 = QHBoxLayout()
        row1.setSpacing(15)
        row1.addStretch()

        # Shortcuts button
        shortcuts_btn = QPushButton("Shortcuts")
        shortcuts_btn.setMaximumWidth(85)
        shortcuts_btn.clicked.connect(self._show_shortcuts_dialog)
        shortcuts_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 11px;
                padding: 5px 10px;
                background-color: #e9ecef;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #dee2e6;
            }}
            QPushButton:focus {{
                border: 2px solid {UIColors.FOCUS_BORDER};
                background-color: {UIColors.FOCUS_BACKGROUND};
            }}
        """)
        row1.addWidget(shortcuts_btn)

        # Color Legend button
        legend_btn = QPushButton("Colors")
        legend_btn.setMaximumWidth(70)
        legend_btn.clicked.connect(self._show_color_legend_dialog)
        legend_btn.setStyleSheet(f"""
            QPushButton {{
                font-size: 11px;
                padding: 5px 10px;
                background-color: #e9ecef;
                border: 1px solid #ced4da;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background-color: #dee2e6;
            }}
            QPushButton:focus {{
                border: 2px solid {UIColors.FOCUS_BORDER};
                background-color: {UIColors.FOCUS_BACKGROUND};
            }}
        """)
        row1.addWidget(legend_btn)

        row1.addSpacing(10)

        # Activity data source selection
        row1.addWidget(QLabel("Source:"))

        self.activity_source_dropdown = NoScrollComboBox()
        self.activity_source_dropdown.addItem("Y-Axis (Vertical)", ActivityDataPreference.AXIS_Y)
        self.activity_source_dropdown.addItem("X-Axis (Lateral)", ActivityDataPreference.AXIS_X)
        self.activity_source_dropdown.addItem("Z-Axis (Forward)", ActivityDataPreference.AXIS_Z)
        self.activity_source_dropdown.addItem("Vector Magnitude", ActivityDataPreference.VECTOR_MAGNITUDE)
        self.activity_source_dropdown.setCurrentIndex(0)
        self.activity_source_dropdown.setToolTip(TooltipText.ACTIVITY_SOURCE_DROPDOWN)
        self.activity_source_dropdown.currentIndexChanged.connect(self._on_activity_source_changed)
        self.activity_source_dropdown.setEnabled(False)
        self.activity_source_dropdown.setStyleSheet(f"""
            QComboBox {{
                padding: 4px 8px;
                font-size: 12px;
                border: 1px solid #ced4da;
                border-radius: 4px;
                background-color: white;
            }}
            QComboBox:focus {{
                border: 2px solid {UIColors.FOCUS_BORDER};
                background-color: {UIColors.FOCUS_BACKGROUND};
            }}
            QComboBox::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 18px;
                border-left: 1px solid #ced4da;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid #666;
            }}
        """)
        row1.addWidget(self.activity_source_dropdown)

        row1.addSpacing(15)

        # Adjacent day markers checkbox
        self.show_adjacent_day_markers_checkbox = QCheckBox("Adjacent Markers")
        self.show_adjacent_day_markers_checkbox.setToolTip("Display sleep markers from adjacent days as faded, dashed lines")
        self.show_adjacent_day_markers_checkbox.setChecked(True)
        self.show_adjacent_day_markers_checkbox.toggled.connect(self._on_adjacent_day_markers_toggled)
        row1.addWidget(self.show_adjacent_day_markers_checkbox)

        row1.addSpacing(15)

        # View mode selection
        row1.addWidget(QLabel("View:"))

        self.view_24h_btn = QRadioButton("24h")
        self.view_24h_btn.setChecked(False)
        self.view_24h_btn.toggled.connect(lambda checked: self._on_view_mode_changed(24) if checked else None)
        row1.addWidget(self.view_24h_btn)

        self.view_48h_btn = QRadioButton("48h")
        self.view_48h_btn.setChecked(True)
        self.view_48h_btn.toggled.connect(lambda checked: self._on_view_mode_changed(48) if checked else None)
        row1.addWidget(self.view_48h_btn)

        self.view_mode_group = QButtonGroup()
        self.view_mode_group.addButton(self.view_24h_btn, 24)
        self.view_mode_group.addButton(self.view_48h_btn, 48)

        row1.addSpacing(15)

        # Day of Week display
        self.weekday_label = QLabel("Day: ")
        self.weekday_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        row1.addWidget(self.weekday_label)

        row1.addSpacing(15)

        # Needs consensus review checkbox
        self.needs_consensus_checkbox = QCheckBox("Needs Consensus")
        self.needs_consensus_checkbox.setToolTip("Flag this date as needing consensus review by a second scorer")
        self.needs_consensus_checkbox.setChecked(False)
        self.needs_consensus_checkbox.setEnabled(False)  # Disabled until data is loaded
        self.needs_consensus_checkbox.setMinimumWidth(140)  # Prevent text clipping on focus
        self.needs_consensus_checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 11px;
                padding: 2px 4px;
            }}
            QCheckBox:focus {{
                border: 2px solid {UIColors.FOCUS_BORDER};
                background-color: {UIColors.FOCUS_BACKGROUND};
            }}
        """)
        self.needs_consensus_checkbox.toggled.connect(self._on_consensus_flag_toggled)
        row1.addWidget(self.needs_consensus_checkbox)

        row1.addStretch()

        main_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(15)
        row2.addStretch()

        # Manual time entry
        row2.addWidget(QLabel("Sleep Times:"))

        self.onset_time_input = QLineEdit()
        self.onset_time_input.setPlaceholderText("HH:MM")
        self.onset_time_input.setMaximumWidth(55)
        self.onset_time_input.setToolTip(TooltipText.ONSET_TIME_INPUT)
        # Signal connections handled by TimeFieldCoordinator
        self.onset_time_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 4px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 2px solid {UIColors.FOCUS_BORDER};
                background-color: {UIColors.FOCUS_BACKGROUND};
            }}
        """)
        row2.addWidget(self.onset_time_input)

        row2.addWidget(QLabel("to"))

        self.offset_time_input = QLineEdit()
        self.offset_time_input.setPlaceholderText("HH:MM")
        self.offset_time_input.setMaximumWidth(55)
        self.offset_time_input.setToolTip(TooltipText.OFFSET_TIME_INPUT)
        # Signal connections handled by TimeFieldCoordinator
        self.offset_time_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 4px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border: 2px solid {UIColors.FOCUS_BORDER};
                background-color: {UIColors.FOCUS_BACKGROUND};
            }}
        """)
        row2.addWidget(self.offset_time_input)

        # Total duration label
        self.total_duration_label = QLabel("")
        self.total_duration_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #333; padding-left: 5px;")
        self.total_duration_label.setMinimumWidth(120)
        row2.addWidget(self.total_duration_label)

        row2.addSpacing(30)

        # Auto-save checkbox
        config = self.services.config_manager.config
        auto_save = config.auto_save_markers if config else False
        self.auto_save_checkbox = QCheckBox("Auto-save")
        self.auto_save_checkbox.setToolTip("Automatically save markers when navigating away")
        self.auto_save_checkbox.setChecked(auto_save)
        self.auto_save_checkbox.toggled.connect(self._on_auto_save_toggled)
        row2.addWidget(self.auto_save_checkbox)

        # Autosave status label (shows when last autosave occurred)
        self.autosave_status_label = QLabel("Saved at N/A")
        self.autosave_status_label.setStyleSheet("color: #333; font-size: 11px;")
        self.autosave_status_label.setVisible(auto_save)
        row2.addWidget(self.autosave_status_label)

        # Save markers button (hidden when autosave is enabled)
        self.save_markers_btn = QPushButton(ButtonText.SAVE_MARKERS)
        self.save_markers_btn.clicked.connect(self.saveMarkersRequested.emit)
        self.save_markers_btn.setToolTip(TooltipText.SAVE_MARKERS)
        self.save_markers_btn.setStyleSheet(ButtonStyle.SAVE_MARKERS)
        self.save_markers_btn.setVisible(not auto_save)
        row2.addWidget(self.save_markers_btn)

        # No Sleep button
        self.no_sleep_btn = QPushButton(ButtonText.MARK_NO_SLEEP)
        self.no_sleep_btn.clicked.connect(self.noSleepRequested.emit)
        self.no_sleep_btn.setToolTip(TooltipText.MARK_NO_SLEEP)
        self.no_sleep_btn.setStyleSheet(ButtonStyle.MARK_NO_SLEEP)
        row2.addWidget(self.no_sleep_btn)

        # Clear markers button
        self.clear_markers_btn = QPushButton(ButtonText.CLEAR_MARKERS)
        self.clear_markers_btn.clicked.connect(self.clearMarkersRequested.emit)
        self.clear_markers_btn.setToolTip(TooltipText.CLEAR_MARKERS)
        self.clear_markers_btn.setStyleSheet(ButtonStyle.CLEAR_MARKERS_RED)
        row2.addWidget(self.clear_markers_btn)

        row2.addSpacing(20)

        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.VLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        row2.addWidget(separator)

        row2.addSpacing(10)

        # Marker Mode selection (Sleep vs Nonwear)
        row2.addWidget(QLabel("Mode:"))

        self.sleep_mode_btn = QRadioButton("Sleep")
        self.sleep_mode_btn.setChecked(True)
        self.sleep_mode_btn.setToolTip("Click to place sleep onset/offset markers")
        self.sleep_mode_btn.toggled.connect(self._on_marker_mode_changed)
        row2.addWidget(self.sleep_mode_btn)

        self.nonwear_mode_btn = QRadioButton("Nonwear")
        self.nonwear_mode_btn.setChecked(False)
        self.nonwear_mode_btn.setToolTip("Click to place manual nonwear start/end markers")
        self.nonwear_mode_btn.toggled.connect(self._on_marker_mode_changed)
        row2.addWidget(self.nonwear_mode_btn)

        self.marker_mode_group = QButtonGroup()
        self.marker_mode_group.addButton(self.sleep_mode_btn, 0)  # 0 = SLEEP
        self.marker_mode_group.addButton(self.nonwear_mode_btn, 1)  # 1 = NONWEAR

        row2.addSpacing(10)

        # Show manual nonwear markers checkbox
        self.show_manual_nonwear_checkbox = QCheckBox("Show NW Markers")
        self.show_manual_nonwear_checkbox.setToolTip("Show/hide manual nonwear markers on the plot")
        self.show_manual_nonwear_checkbox.setChecked(True)
        self.show_manual_nonwear_checkbox.toggled.connect(self._on_manual_nonwear_visibility_changed)
        row2.addWidget(self.show_manual_nonwear_checkbox)

        row2.addStretch()

        main_layout.addLayout(row2)

        return panel

    def _show_shortcuts_dialog(self) -> None:
        """Show keyboard shortcuts dialog."""
        self.dialog_manager.show_shortcuts_dialog()

    def _show_color_legend_dialog(self) -> None:
        """Show color legend dialog with color picker functionality."""
        self.dialog_manager.show_color_legend_dialog()

    def _apply_colors(self) -> None:
        """Apply the selected colors to the plot in real-time."""
        self.dialog_manager.apply_colors()

    # Delegate to seamless source switcher manager
    @pyqtSlot(int)
    def _on_activity_source_changed(self, index: int) -> None:
        """Handle activity data source dropdown change (delegates to seamless switcher)."""
        logger.info("=== ACTIVITY SOURCE CHANGE START ===")
        selected_data = self.activity_source_dropdown.itemData(index)

        # Emit signal - AnalysisTabConnector dispatches to store
        self.activitySourceChanged.emit(selected_data)

        # Delegate to switcher for the heavy lifting (seamless reload)
        if self.seamless_source_switcher:
            try:
                # Use callbacks or services instead of direct parent
                cfg = self.services.config_manager.config
                choi_column = cfg.choi_axis if cfg else "axis1"
                self.app_state.set_activity_data_preferences(selected_data, choi_column)

                self.seamless_source_switcher.switch_activity_source(index)
                logger.info("=== ACTIVITY SOURCE CHANGE COMPLETE ===")
            except Exception as e:
                logger.exception(f"Error switching activity source: {e}")
                self.app_state.update_status_bar(f"Error switching source: {e}")

    @ensure_main_thread
    def update_activity_source_dropdown(self) -> None:
        """Update the activity source dropdown to reflect current preferences and available columns."""
        logger.debug("=== UPDATE ACTIVITY SOURCE DROPDOWN START ===")
        try:
            # Get current preferences
            preferred_column, _choi_column = self.app_state.get_activity_data_preferences()
            logger.debug(f"Preferred column: {preferred_column}, Choi column: {_choi_column}")

            # Get available columns for current file
            available_columns = self._get_available_activity_columns()

            # Update each item's enabled state based on available columns
            model = self.activity_source_dropdown.model()
            if model is not None:
                for i in range(self.activity_source_dropdown.count()):
                    item_data = self.activity_source_dropdown.itemData(i)
                    is_available = item_data in available_columns
                    # Enable/disable item in the model
                    item = model.item(i)
                    if item:
                        item.setEnabled(is_available)

            # Find the index for the preferred column
            for i in range(self.activity_source_dropdown.count()):
                if self.activity_source_dropdown.itemData(i) == preferred_column:
                    # Temporarily disconnect to avoid triggering change handler
                    try:
                        self.activity_source_dropdown.currentIndexChanged.disconnect()
                        self.activity_source_dropdown.setCurrentIndex(i)
                        self.activity_source_dropdown.currentIndexChanged.connect(self._on_activity_source_changed)
                    except (TypeError, RuntimeError):
                        # Handle case where signal is already disconnected or widget is being destroyed
                        self.activity_source_dropdown.setCurrentIndex(i)
                        self.activity_source_dropdown.currentIndexChanged.connect(self._on_activity_source_changed)
                    break

            # Enable the dropdown if data is available
            # Use store state as single source of truth
            # current_date_index is -1 when no date selected, so check >= 0
            has_data = bool(self.store.state.available_dates and self.store.state.current_date_index >= 0)
            self.activity_source_dropdown.setEnabled(has_data)
            logger.debug(
                f"Activity source dropdown enabled={has_data} (dates={len(self.store.state.available_dates)}, index={self.store.state.current_date_index})"
            )

        except Exception as e:
            logger.exception(f"Error updating activity source dropdown: {e}")

    def _get_available_activity_columns(self) -> list:
        """Get list of activity columns that have data for the current file."""
        try:
            # Get current filename from store or navigation interface
            filename = self.navigation.selected_file
            if filename and not filename.endswith((".csv", ".gt3x")):
                # It's likely a full path, get just the name
                filename = Path(filename).name

            if not filename:
                # No file loaded, return all as available
                return [
                    ActivityDataPreference.AXIS_Y,
                    ActivityDataPreference.AXIS_X,
                    ActivityDataPreference.AXIS_Z,
                    ActivityDataPreference.VECTOR_MAGNITUDE,
                ]

            # Query database for available columns via services container
            if self.services.data_service is not None:
                return self.services.data_service.get_available_activity_columns(filename)

            # Fallback to all available
            return [
                ActivityDataPreference.AXIS_Y,
                ActivityDataPreference.AXIS_X,
                ActivityDataPreference.AXIS_Z,
                ActivityDataPreference.VECTOR_MAGNITUDE,
            ]

        except Exception as e:
            logger.warning(f"Error getting available activity columns: {e}")
            return [ActivityDataPreference.AXIS_Y]

    @ensure_main_thread
    def set_activity_source_dropdown_enabled(self, enabled: bool) -> None:
        """Enable or disable the activity source dropdown."""
        self.activity_source_dropdown.setEnabled(enabled)

    def _create_diary_table(self) -> QWidget:
        """Create diary table that displays actual diary data."""
        container = QFrame()
        container.setFrameStyle(QFrame.Shape.StyledPanel)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(5, 5, 5, 5)

        # Title label
        title_label = QLabel("Sleep Diary")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px; margin-bottom: 5px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        # Define diary column structure with proper sizing
        diary_columns = [
            DiaryColumnDefinition(DiaryTableColumn.DATE, "Date", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.BEDTIME, "In Bed Time", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.SLEEP_ONSET, "Sleep Onset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.SLEEP_OFFSET, "Sleep Offset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NAP_OCCURRED, "# Naps", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NAP_1_START, "Nap 1 Onset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NAP_1_END, "Nap 1 Offset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NAP_2_START, "Nap 2 Onset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NAP_2_END, "Nap 2 Offset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NAP_3_START, "Nap 3 Onset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NAP_3_END, "Nap 3 Offset", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_OCCURRED, "Nonwear", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_1_START, "NWT 1 Start", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_1_END, "NWT 1 End", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_1_REASON, "NWT 1 Reason", QHeaderView.ResizeMode.Stretch),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_2_START, "NWT 2 Start", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_2_END, "NWT 2 End", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_2_REASON, "NWT 2 Reason", QHeaderView.ResizeMode.Stretch),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_3_START, "NWT 3 Start", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_3_END, "NWT 3 End", QHeaderView.ResizeMode.ResizeToContents),
            DiaryColumnDefinition(DiaryTableColumn.NONWEAR_3_REASON, "NWT 3 Reason", QHeaderView.ResizeMode.Stretch),
        ]

        # Create diary table with dynamic column count
        table = QTableWidget(0, len(diary_columns))

        # Set headers from column definitions
        headers = [col.header for col in diary_columns]
        table.setHorizontalHeaderLabels(headers)

        # Configure table appearance
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # Allow single row selection

        # Add hover styling and selection styling to indicate clickable rows
        from sleep_scoring_app.core.constants import UIColors

        table.setStyleSheet(f"""
            QTableWidget::item:hover {{
                background-color: {UIColors.DIARY_SELECTION_DARKER};
                color: white;
            }}
            QTableWidget::item:selected {{
                background-color: {UIColors.DIARY_SELECTION_DARKER} !important;
                color: white !important;
            }}
            QTableWidget:item:focus {{
                background-color: {UIColors.DIARY_SELECTION_DARKER} !important;
                color: white !important;
            }}
            QTableWidget {{
                selection-background-color: {UIColors.DIARY_SELECTION_DARKER};
                selection-color: white;
            }}
            QTableWidget::item {{
                padding: 2px;
            }}
        """)

        # Hide vertical header
        vertical_header = table.verticalHeader()
        if vertical_header:
            vertical_header.setVisible(False)

        # Configure column widths from definitions
        if (header := table.horizontalHeader()) is not None:
            header.setStretchLastSection(False)

            for idx, col_def in enumerate(diary_columns):
                header.setSectionResizeMode(idx, col_def.width_mode)
                if col_def.width_hint:
                    table.setColumnWidth(idx, col_def.width_hint)

        # Set font
        font = table.font()
        font.setPointSize(9)
        table.setFont(font)

        layout.addWidget(table)

        # Configure size policies
        table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Store reference for future use and column definitions
        container.diary_table = table
        container.diary_columns = diary_columns

        # Connect click handler for setting markers from diary
        table.itemClicked.connect(self._on_diary_row_clicked)

        return container

    def update_diary_display(self) -> None:
        """
        Update diary table with data for current participant.

        Delegates to DiaryTableConnector.
        """
        logger.info("=== UPDATE DIARY DISPLAY START ===")
        logger.info(f"diary_table_connector exists: {self.diary_table_connector is not None}")
        logger.info(f"diary_table_widget visible: {self.diary_table_widget.isVisible() if self.diary_table_widget else 'N/A'}")
        logger.info(f"Current participant ID: {self._get_current_participant_id()}")

        if self.diary_table_connector:
            try:
                self.diary_table_connector.update_diary_display()
                logger.info(f"After update - diary_table_widget visible: {self.diary_table_widget.isVisible()}")
                logger.info("=== UPDATE DIARY DISPLAY COMPLETE ===")
            except Exception as e:
                logger.exception(f"=== UPDATE DIARY DISPLAY FAILED: {e} ===")
        else:
            logger.warning("=== UPDATE DIARY DISPLAY SKIPPED: No diary_table_connector ===")

    def _on_diary_row_clicked(self, item) -> None:
        """Handle click on diary table row - delegates to DiaryTableConnector."""
        if self.diary_table_connector:
            self.diary_table_connector.on_diary_row_clicked(item)

    def save_splitter_states(self) -> tuple[bytes, bytes, bytes]:
        """Save splitter states for layout persistence."""
        return (
            bytes(self.top_level_splitter.saveState().data()),
            bytes(self.main_splitter.saveState().data()),
            bytes(self.plot_and_tables_splitter.saveState().data()),
        )

    def restore_splitter_states(
        self,
        top_level: bytes | None,
        main: bytes | None,
        plot_tables: bytes | None,
    ) -> None:
        """Restore splitter states from saved layout."""
        if top_level:
            self.top_level_splitter.restoreState(top_level)
        if main:
            self.main_splitter.restoreState(main)
        if plot_tables:
            self.plot_and_tables_splitter.restoreState(plot_tables)

    def _get_current_participant_id(self) -> str | None:
        """Get participant ID from current filename."""
        selected_file = self.navigation.selected_file
        if not selected_file:
            return None

        from pathlib import Path

        from sleep_scoring_app.utils.participant_extractor import extract_participant_info

        filename = Path(selected_file).name
        participant_info = extract_participant_info(filename)
        return participant_info.full_id if participant_info.numerical_id != "UNKNOWN" else None

    def _get_sleep_algorithm_display_name(self) -> str:
        """
        Get the display name of the currently configured sleep/wake algorithm.

        Returns:
            Display name of the algorithm (e.g., "Sadeh", "Cole-Kripke")

        """
        try:
            # AppStateInterface guarantees get_sleep_algorithm_display_name exists
            return self.app_state.get_sleep_algorithm_display_name()
        except Exception as e:
            logger.warning("Failed to get sleep algorithm name: %s", e)
            # Default fallback
            return "Sadeh"

    def _get_algorithm_config(self) -> AppConfig | None:
        """Provide algorithm config to plot components."""
        if self.services.config_manager:
            return self.services.config_manager.config
        return None

    @property
    def _algorithm_service(self):
        """Lazily resolve the algorithm service singleton."""
        from sleep_scoring_app.services.algorithm_service import get_algorithm_service

        return get_algorithm_service()

    def _create_sleep_algorithm(self, algorithm_id: str, config: AppConfig | None) -> SleepScoringAlgorithm:
        """Create sleep algorithm via algorithm service."""
        return self._algorithm_service.create_sleep_algorithm(algorithm_id, config)

    def _create_sleep_period_detector(self, detector_id: str) -> SleepPeriodDetector:
        """Create sleep period detector via algorithm service."""
        return self._algorithm_service.create_sleep_period_detector(detector_id)

    def _create_nonwear_algorithm(self, algorithm_id: str) -> NonwearDetectionAlgorithm:
        """Create nonwear algorithm via algorithm service."""
        return self._algorithm_service.create_nonwear_algorithm(algorithm_id)

    def _get_default_sleep_algorithm_id(self) -> str:
        """Provide default sleep algorithm id."""
        return self._algorithm_service.get_default_sleep_algorithm_id()

    def _get_default_sleep_period_detector_id(self) -> str:
        """Provide default sleep period detector id."""
        return self._algorithm_service.get_default_sleep_period_detector_id()

    def _get_choi_activity_column(self) -> str:
        """Provide Choi activity column from config or fallback."""
        config = self._get_algorithm_config()
        if config and getattr(config, "choi_axis", None):
            return config.choi_axis
        return ActivityDataPreference.VECTOR_MAGNITUDE

    @pyqtSlot(int)
    def _on_date_selected(self, index: int) -> None:
        """Handle date selection from dropdown - emits signal for NavigationGuardConnector."""
        logger.info(f"ANALYSIS TAB: _on_date_selected called with index={index}")
        if index < 0:
            logger.info("ANALYSIS TAB: index < 0, returning early")
            return

        current = self.store.state.current_date_index
        logger.info(f"ANALYSIS TAB: current_date_index in store = {current}")
        if index == current:
            logger.info("ANALYSIS TAB: index == current, returning early (no change)")
            return

        # Emit signal - NavigationGuardConnector will check for unsaved markers before dispatch
        logger.info(f"ANALYSIS TAB: Emitting dateSelectRequested({index})")
        self.dateSelectRequested.emit(index)

    @pyqtSlot(int)
    def _on_view_mode_changed(self, hours: int) -> None:
        """Handle view mode radio button change."""
        if hours == self.store.state.view_mode_hours:
            return

        logger.info(f"View mode requested: {hours} hours")

        # Emit signal - AnalysisTabConnector dispatches to store
        self.viewModeChanged.emit(hours)

    @pyqtSlot(bool)
    def _on_adjacent_day_markers_toggled(self, checked: bool) -> None:
        """Handle adjacent day markers checkbox toggle."""
        logger.info(f"Adjacent day markers toggled: {checked}")

        # Emit signal - AnalysisTabConnector dispatches to store
        self.adjacentMarkersToggled.emit(checked)

    def _on_auto_save_toggled(self, checked: bool) -> None:
        """Handle auto-save checkbox toggle."""
        logger.info(f"Auto-save toggled: {checked}")

        # Emit signal - AnalysisTabConnector dispatches to store
        # ConfigPersistenceConnector watches auto_save_enabled and persists to config
        self.autoSaveToggled.emit(checked)

    def update_autosave_status(self, message: str = "") -> None:
        """Update the autosave status label with timestamp or custom message."""
        # Initialized in setup_ui, always exists
        from datetime import datetime

        timestamp = datetime.now().strftime("%H:%M:%S")
        if message:
            # Custom message (e.g., "NWT saved") - add timestamp
            self.autosave_status_label.setText(f"{message} at {timestamp}")
        else:
            # Default sleep marker save
            self.autosave_status_label.setText(f"Saved at {timestamp}")
        self.autosave_status_label.setStyleSheet("color: #28a745; font-size: 11px;")  # Green when saved

    @pyqtSlot(bool)
    def _on_marker_mode_changed(self, checked: bool) -> None:
        """Handle marker mode radio button change (Sleep vs Nonwear)."""
        # Only process when a button is checked (not when unchecked)
        if not checked:
            return

        category = MarkerCategory.SLEEP
        if self.nonwear_mode_btn.isChecked():
            category = MarkerCategory.NONWEAR

        logger.debug(f"Marker mode changed to {category}")

        # Emit signal - AnalysisTabConnector dispatches to store
        self.markerModeChanged.emit(category)

    @pyqtSlot(bool)
    def _on_manual_nonwear_visibility_changed(self, visible: bool) -> None:
        """Handle manual nonwear markers visibility checkbox toggle."""
        logger.debug(f"Manual nonwear markers visibility: {visible}")

        # Update plot widget's nonwear marker visibility
        if self.plot_widget is not None:
            self.plot_widget.set_nonwear_markers_visibility(visible)

    @pyqtSlot(bool)
    def _on_consensus_flag_toggled(self, checked: bool) -> None:
        """Handle consensus flag checkbox toggle."""
        logger.info(f"Consensus flag toggled: {checked}")

        # Emit signal - ConsensusCheckboxConnector dispatches to store and persists to DB
        self.consensusFlagToggled.emit(checked)

    def _serialize_sleep_period(self, period) -> dict | None:
        """Serialize a sleep period for state capture."""
        if period is None:
            return None

        return {
            "onset_timestamp": period.onset_timestamp,
            "offset_timestamp": period.offset_timestamp,
            "marker_index": period.marker_index,
            "marker_type": period.marker_type.value if period.marker_type else None,
        }

    def _deserialize_sleep_period(self, period_data: dict | None) -> SleepPeriod | None:
        """Deserialize a sleep period for state restore."""
        if period_data is None:
            return None

        from sleep_scoring_app.core.dataclasses import SleepPeriod

        marker_type = MarkerType.MAIN_SLEEP  # Default
        if period_data.get("marker_type"):
            try:
                marker_type = MarkerType(period_data["marker_type"])
            except ValueError:
                marker_type = MarkerType.MAIN_SLEEP

        return SleepPeriod(
            onset_timestamp=period_data.get("onset_timestamp"),
            offset_timestamp=period_data.get("offset_timestamp"),
            marker_index=period_data.get("marker_index", 1),
            marker_type=marker_type,
        )

    @pyqtSlot()
    def _on_onset_popout_clicked(self) -> None:
        """Handle onset table pop-out button click."""
        if self.onset_popout_window is None:
            # Create new pop-out window
            parent_widget = self.parentWidget()
            self.onset_popout_window = PopOutTableWindow(parent=parent_widget, title="Sleep Onset Data - Pop Out", table_type="onset")
            # Connect right-click handler to main window for marker movement
            self.onset_popout_window.table.customContextMenuRequested.connect(lambda pos: self._on_popout_table_right_clicked("onset", pos))
            logger.info("Created onset pop-out window")

        # Show the window and bring to front
        self.onset_popout_window.show()
        self.onset_popout_window.raise_()
        self.onset_popout_window.activateWindow()

        # Immediately populate with data so user doesn't see an empty window
        self.refresh_onset_popout()

    @pyqtSlot()
    def _on_offset_popout_clicked(self) -> None:
        """Handle offset table pop-out button click."""
        if self.offset_popout_window is None:
            # Create new pop-out window
            parent_widget = self.parentWidget()
            self.offset_popout_window = PopOutTableWindow(parent=parent_widget, title="Sleep Offset Data - Pop Out", table_type="offset")
            # Connect right-click handler to main window for marker movement
            self.offset_popout_window.table.customContextMenuRequested.connect(lambda pos: self._on_popout_table_right_clicked("offset", pos))
            logger.info("Created offset pop-out window")

        # Show the window and bring to front
        self.offset_popout_window.show()
        self.offset_popout_window.raise_()
        self.offset_popout_window.activateWindow()

        # Immediately populate with data so user doesn't see an empty window
        self.refresh_offset_popout()

    def refresh_onset_popout(self) -> None:
        """Refresh data in the onset/start pop-out window (works for both sleep and nonwear modes)."""
        if not self.onset_popout_window or not self.onset_popout_window.isVisible():
            return

        onset_timestamp = None
        active_category = self.plot_widget.get_active_marker_category()

        if active_category == MarkerCategory.NONWEAR:
            selected_period = self.plot_widget.get_selected_nonwear_period()
            if selected_period and selected_period.start_timestamp:
                onset_timestamp = selected_period.start_timestamp
        else:
            selected_period = self.plot_widget.get_selected_marker_period()
            if selected_period and selected_period.onset_timestamp:
                onset_timestamp = selected_period.onset_timestamp

        full_data = self.app_state._get_full_48h_data_for_popout(marker_timestamp=onset_timestamp)
        # Always update - even with empty data - to clear stale data on date switch
        self.onset_popout_window.update_table_data(full_data)
        if full_data and onset_timestamp is not None:
            for row_idx, row_data in enumerate(full_data):
                if row_data.get("is_marker", False):
                    self.onset_popout_window.scroll_to_row(row_idx)
                    break

    def refresh_offset_popout(self) -> None:
        """Refresh data in the offset/end pop-out window (works for both sleep and nonwear modes)."""
        if not self.offset_popout_window or not self.offset_popout_window.isVisible():
            return

        offset_timestamp = None
        active_category = self.plot_widget.get_active_marker_category()

        if active_category == MarkerCategory.NONWEAR:
            selected_period = self.plot_widget.get_selected_nonwear_period()
            if selected_period and selected_period.end_timestamp:
                offset_timestamp = selected_period.end_timestamp
        else:
            selected_period = self.plot_widget.get_selected_marker_period()
            if selected_period and selected_period.offset_timestamp:
                offset_timestamp = selected_period.offset_timestamp

        full_data = self.app_state._get_full_48h_data_for_popout(marker_timestamp=offset_timestamp)
        # Always update - even with empty data - to clear stale data on date switch
        self.offset_popout_window.update_table_data(full_data)
        if full_data and offset_timestamp is not None:
            for row_idx, row_data in enumerate(full_data):
                if row_data.get("is_marker", False):
                    self.offset_popout_window.scroll_to_row(row_idx)
                    break

    def _on_popout_table_right_clicked(self, table_type: str, pos: QPoint) -> None:
        """Handle right-click on pop-out table cell - move marker to clicked row."""
        # Get the appropriate window
        window = self.onset_popout_window if table_type == "onset" else self.offset_popout_window
        if window is None:
            logger.warning(f"Pop-out window for {table_type} is None")
            return

        # Get the item at the clicked position
        item = window.table.itemAt(pos)
        if item is None:
            logger.warning(f"No item at position {pos}")
            return

        row = item.row()
        logger.info(f"Pop-out {table_type} table: Right-clicked on row {row}, moving marker")

        # Clear selection to prevent highlighting on right-click
        window.table.clearSelection()

        # Get the timestamp from the row data
        timestamp = window.get_timestamp_for_row(row)
        if timestamp is None:
            logger.warning(f"No timestamp available for row {row}")
            return

        # Move the marker using the marker operations interface
        self.marker_ops.move_marker_to_timestamp(table_type, timestamp)
        logger.debug(f"Moved {table_type} marker to timestamp {timestamp}")

    def cleanup_tab(self) -> None:
        """Clean up tab resources to prevent memory leaks."""
        try:
            # Close pop-out windows if they exist
            if self.onset_popout_window is not None:
                self.onset_popout_window.close()
                self.onset_popout_window = None

            if self.offset_popout_window is not None:
                self.offset_popout_window.close()
                self.offset_popout_window = None

            # Disconnect signals to prevent reference cycles
            # All initialized in setup_ui, always exist
            try:
                if self.file_selector:
                    self.file_selector.fileSelected.disconnect()
            except (TypeError, RuntimeError):
                # Signal already disconnected or object deleted
                pass

            try:
                if self.activity_source_dropdown:
                    self.activity_source_dropdown.currentIndexChanged.disconnect()
            except (TypeError, RuntimeError):
                # Signal already disconnected or object deleted
                pass

            try:
                if self.date_dropdown:
                    self.date_dropdown.currentIndexChanged.disconnect()
            except (TypeError, RuntimeError):
                # Signal already disconnected or object deleted
                pass

            # Clean up plot widget if it exists
            # PlotWidgetProtocol guarantees cleanup_widget() exists
            if self.plot_widget:
                self.plot_widget.cleanup_widget()

            logger.debug("AnalysisTab cleanup completed")

        except Exception as e:
            logger.warning(f"Error during AnalysisTab cleanup: {e}")
