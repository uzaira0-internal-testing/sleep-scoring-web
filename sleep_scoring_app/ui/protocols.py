#!/usr/bin/env python3
"""
Protocol classes for UI component interfaces.
Reduces hasattr() checks by providing type-safe interfaces.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date, datetime

    from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton, QTableWidget

    from sleep_scoring_app.core.dataclasses import (
        DailyNonwearMarkers,
        DailySleepMarkers,
        FileInfo,
        ManualNonwearPeriod,
        SleepPeriod,
    )
    from sleep_scoring_app.data.database import DatabaseManager
    from sleep_scoring_app.services.unified_data_service import UnifiedDataService
    from sleep_scoring_app.ui.utils.config import ConfigManager


@runtime_checkable
class MarkerLineProtocol(Protocol):
    """
    Protocol for pyqtgraph InfiniteLine objects with marker attributes.

    When creating marker lines, these attributes are monkey-patched onto
    the pyqtgraph InfiniteLine. However, these are ONLY set for complete
    markers (not "incomplete" markers being drawn). Therefore, hasattr()
    checks are REQUIRED when handling lines from mixed sources.

    Attributes:
        period: The SleepPeriod/ManualNonwearPeriod this marker belongs to
        marker_type: MarkerType enum value (e.g., "onset", "offset")
        label: pyqtgraph TextItem for the marker label

    Usage:
        # For lines from unknown sources (e.g., mouse events), use hasattr:
        if hasattr(line, "period") and line.period:
            renderer.select_marker_set_by_period(line.period)

        # For lines from known marker collections, cast to protocol:
        marker: MarkerLineProtocol = line  # type: ignore[assignment]
        if marker.period:
            ...

    Note: The hasattr() pattern is correct here because incomplete markers
    do NOT have these attributes set. See marker_drawing_strategy.py:108-111.

    """

    period: SleepPeriod | None  # The sleep period this marker belongs to
    marker_type: str | None  # MarkerType enum value (e.g., "onset", "offset")
    label: Any | None  # pyqtgraph TextItem for the marker label


@runtime_checkable
class ConfigWithAlgorithmProtocol(Protocol):
    """Protocol for config objects with algorithm settings."""

    sleep_algorithm_id: str | None
    onset_offset_rule_id: str | None


class PlotWidgetProtocol(Protocol):
    """Protocol for ActivityPlotWidget interface."""

    # Core data attributes
    daily_sleep_markers: DailySleepMarkers
    daily_nonwear_markers: DailyNonwearMarkers
    timestamps: list[datetime]
    activity_data: list[float]
    axis_y_data: list[float]
    main_48h_axis_y_data: list[float] | None
    main_48h_timestamps: list[datetime] | None
    main_48h_activity: list[float] | None
    data_start_time: float | None  # Unix timestamp (NOT datetime)
    data_end_time: float | None  # Unix timestamp (NOT datetime)
    actual_data_bounds: tuple[float, float] | None  # Actual loaded data range (x_data[0], x_data[-1])
    current_marker_being_placed: SleepPeriod | None
    _current_nonwear_marker_being_placed: ManualNonwearPeriod | None

    # Manager components (optional - initialized after construction)
    algorithm_manager: Any | None
    plotItem: Any  # pyqtgraph PlotItem

    # Algorithm cache attributes
    _algorithm_cache: dict[str, Any] | None
    _cached_48h_vm_data: Any | None
    sadeh_results: list[int] | None

    # State tracking - READ-ONLY property delegating to Redux store
    # Use mark_nonwear_markers_dirty() to mark as dirty
    @property
    def _nonwear_markers_saved(self) -> bool: ...

    def get_selected_marker_period(self) -> SleepPeriod | None: ...
    def get_choi_results_per_minute(self) -> list[int]: ...
    def get_nonwear_sensor_results_per_minute(self) -> list[int]: ...
    def clear_markers(self) -> None: ...
    def clear_adjacent_day_markers(self) -> None: ...
    def display_adjacent_day_markers(self, markers: list[tuple[datetime, datetime, str]]) -> None: ...
    def load_daily_sleep_markers(self, periods: DailySleepMarkers) -> None: ...
    def load_daily_nonwear_markers(self, periods: DailyNonwearMarkers) -> None: ...
    def plot_algorithms(self) -> None: ...
    def cleanup_widget(self) -> None: ...
    def redraw_plot(self) -> None: ...
    def _update_sleep_scoring_rules(self) -> None: ...
    def clear_choi_cache(self) -> None: ...
    def update_choi_overlay_only(self, data: list[float]) -> None: ...


class AnalysisTabProtocol(Protocol):
    """Protocol for AnalysisTab interface."""

    # Navigation controls
    date_dropdown: QComboBox
    prev_date_btn: QPushButton
    next_date_btn: QPushButton

    # View mode controls
    view_24h_btn: Any  # QRadioButton
    view_48h_btn: Any  # QRadioButton

    # Autosave controls
    auto_save_checkbox: QCheckBox
    autosave_status_label: QLabel

    # Display options
    show_adjacent_day_markers_checkbox: QCheckBox
    activity_source_dropdown: QComboBox

    # Marker action buttons
    no_sleep_btn: QPushButton

    # Core widgets
    plot_widget: PlotWidgetProtocol
    diary_table_widget: QTableWidget | None
    file_selector: Any  # FileSelectionTable widget

    # Popout windows (optional - created on demand)
    onset_popout_window: Any | None
    offset_popout_window: Any | None

    def update_diary_display(self) -> None: ...
    def update_activity_source_dropdown(self) -> None: ...
    def cleanup_tab(self) -> None: ...
    def refresh_onset_popout(self) -> None: ...
    def refresh_offset_popout(self) -> None: ...


class DataSettingsTabProtocol(Protocol):
    """Protocol for DataSettingsTab interface."""

    activity_status_label: QLabel
    activity_import_files_label: QLabel
    nwt_import_files_label: QLabel
    nwt_progress_label: QLabel | None
    nwt_progress_bar: Any | None
    activity_progress_label: QLabel | None
    activity_progress_bar: Any | None
    # Note: auto_calibrate_check and impute_gaps_check are optional - use getattr()

    def update_loaders_for_paradigm(self, paradigm: Any) -> None: ...


class ExportTabProtocol(Protocol):
    """Protocol for ExportTab interface."""

    export_output_label: QLabel
    separate_nonwear_file_checkbox: Any


class StudySettingsTabProtocol(Protocol):
    """Protocol for StudySettingsTab interface."""

    test_id_input: Any

    def _load_settings_from_state(self, state: Any) -> None: ...


class MarkerTableProtocol(Protocol):
    """Protocol for MarkerTable interface."""

    table_widget: QTableWidget


class FileNavigationProtocol(Protocol):
    """Protocol for FileNavigation interface."""

    table: QTableWidget


class StateManagerProtocol(Protocol):
    """Protocol for WindowStateManager interface."""

    def save_current_markers(self) -> None: ...
    def clear_current_markers(self) -> None: ...
    def load_saved_markers(self) -> None: ...
    def mark_no_sleep_period(self) -> None: ...
    def handle_sleep_markers_changed(self, daily_sleep_markers: DailySleepMarkers) -> None: ...


class ServiceContainer(Protocol):
    """Protocol for objects that provide core application services."""

    data_service: UnifiedDataService
    config_manager: ConfigManager
    db_manager: DatabaseManager
    marker_service: Any  # MarkerService (headless)
    store: Any  # UIStore
    import_service: Any  # ImportService (headless)
    export_manager: Any | None  # ExportManager
    autosave_coordinator: Any | None
    compatibility_helper: Any | None
    table_manager: Any | None
    diary_coordinator: Any | None
    plot_widget: Any  # ActivityPlotWidget
    export_tab: Any | None  # ExportTab


class MarkerOperationsInterface(Protocol):
    """Protocol for marker placement and manipulation operations."""

    def save_current_markers(self) -> None: ...
    def auto_save_current_markers(self) -> None: ...
    def clear_current_markers(self) -> None: ...
    def load_saved_markers(self) -> None: ...
    def mark_no_sleep_period(self) -> None: ...
    def set_manual_sleep_times(self) -> None: ...
    def move_marker_to_timestamp(self, marker_type: str, timestamp: float) -> None: ...
    def handle_sleep_markers_changed(self, daily_sleep_markers: DailySleepMarkers) -> None: ...
    def handle_nonwear_markers_changed(self, daily_nonwear_markers: Any = None) -> None: ...
    def handle_nonwear_marker_selected(self, period: Any) -> None: ...
    def _autosave_sleep_markers_to_db(self, daily_sleep_markers: DailySleepMarkers) -> bool: ...
    def _autosave_nonwear_markers_to_db(self, daily_nonwear_markers: DailyNonwearMarkers) -> None: ...


class NavigationInterface(Protocol):
    """Protocol for navigation operations (dates, files)."""

    available_dates: list[date]
    current_date_index: int | None
    selected_file: str | None

    def load_current_date(self) -> None: ...
    def on_file_selected_from_table(self, file_info: FileInfo) -> None: ...
    def on_date_dropdown_changed(self, index: int) -> None: ...
    def prev_date(self) -> None: ...
    def next_date(self) -> None: ...
    def _parse_time_to_timestamp(self, time_str: str, base_date: datetime) -> float | None: ...
    def _find_timestamp_by_time_string(self, time_str: str) -> float | None: ...
    def _find_index_in_timestamps(self, timestamps: list[datetime], target: float) -> int | None: ...


class ImportInterface(Protocol):
    """Protocol for data import operations."""

    def browse_activity_files(self) -> None: ...
    def start_activity_import(self) -> None: ...
    def browse_nonwear_files(self) -> None: ...
    def start_nonwear_import(self) -> None: ...
    def browse_diary_files(self) -> None: ...
    def start_diary_import(self) -> None: ...
    def load_available_files(self, preserve_selection: bool = True, load_completion_counts: bool = False) -> None: ...


class AppStateInterface(Protocol):
    """Protocol for application-wide state and UI coordination."""

    store: Any  # UIStore
    available_dates: list[date]
    current_date_index: int | None
    tab_widget: Any  # QTabWidget

    def update_marker_tables(self, onset_data: list, offset_data: list) -> None: ...
    def set_activity_data_preferences(self, preferred: str, choi: str) -> None: ...
    def get_activity_data_preferences(self) -> tuple[str, str]: ...
    def _get_full_48h_data_for_popout(self, marker_timestamp: float | None = None) -> list[dict]: ...
    def update_status_bar(self, message: str = "") -> None: ...
    def clear_all_markers(self) -> None: ...
    def get_sleep_algorithm_display_name(self) -> str: ...


class MainWindowProtocol(ServiceContainer, MarkerOperationsInterface, NavigationInterface, AppStateInterface, ImportInterface, Protocol):
    """
    Protocol for SleepScoringMainWindow interface.

    Now purely composed of smaller, focused interfaces.
    """

    # UI components
    plot_widget: PlotWidgetProtocol
    analysis_tab: AnalysisTabProtocol
    data_settings_tab: DataSettingsTabProtocol
    export_tab: ExportTabProtocol
    study_settings_tab: StudySettingsTabProtocol

    # Marker tables
    onset_table: Any
    offset_table: Any

    # File navigation
    file_selector: Any

    # State manager
    state_manager: Any | None

    # Session manager
    session_service: Any | None

    # UI controls
    save_markers_btn: Any
    no_sleep_btn: Any
    clear_markers_btn: Any
    export_btn: Any
    onset_time_input: Any
    offset_time_input: Any
    total_duration_label: Any
    date_dropdown: Any
    prev_date_btn: Any
    next_date_btn: Any

    def populate_date_dropdown(self) -> None: ...
    def _refresh_file_dropdown_indicators(self) -> None: ...
    def _create_sleep_period_from_timestamps(self, onset: float | None, offset: float | None, is_main_sleep: bool = True) -> SleepPeriod | None: ...
    def _get_cached_metrics(self) -> list[Any]: ...
    def _get_axis_y_data_for_sadeh(self) -> list[float]: ...
    def _invalidate_metrics_cache(self) -> None: ...
    def _load_diary_data_for_file(self) -> None: ...
    def load_nonwear_data_for_plot(self) -> None: ...
    # Note: _update_time_fields_from_selection is optional - use getattr()
    def isVisible(self) -> bool: ...
    def isMaximized(self) -> bool: ...
    def geometry(self) -> Any: ...
    def statusBar(self) -> Any: ...
    def _check_unsaved_markers_before_navigation(self) -> bool: ...

    # Configuration change handlers
    def on_epoch_length_changed(self, value: int) -> None: ...
    def on_skip_rows_changed(self, value: int) -> None: ...

    # Export methods
    def browse_export_output_directory(self) -> None: ...
    def save_export_options(self) -> None: ...
    def perform_direct_export(self) -> None: ...

    # Status methods
    def update_data_source_status(self) -> None: ...
