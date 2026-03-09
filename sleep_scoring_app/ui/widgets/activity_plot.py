#!/usr/bin/env python3
"""
Activity Plot Widget - Core plotting functionality extracted from RestrictedActivityPlot
Focuses on display and user interaction, with algorithms handled separately.
"""

import logging
import traceback
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QKeyEvent

from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    DatabaseColumn,
    MarkerCategory,
    MarkerEndpoint,
    MarkerLimits,
    NonwearAlgorithm,
    SleepMarkerEndpoint,
)
from sleep_scoring_app.core.dataclasses import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    ManualNonwearPeriod,
    NonwearPeriod,
    SleepPeriod,
)
from sleep_scoring_app.ui.widgets.marker_editor import MarkerEditor
from sleep_scoring_app.ui.widgets.plot_algorithm_manager import PlotAlgorithmManager
from sleep_scoring_app.ui.widgets.plot_marker_renderer import PlotMarkerRenderer
from sleep_scoring_app.ui.widgets.plot_overlay_renderer import PlotOverlayRenderer
from sleep_scoring_app.ui.widgets.plot_state_serializer import PlotStateSerializer
from sleep_scoring_app.utils.date_range import get_range_for_view_mode

# Configure logging
logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import AppStateInterface


class TimeAxisItem(pg.AxisItem):
    """Custom axis for displaying time labels."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def tickStrings(self, values, scale, spacing) -> list[str]:  # Qt naming convention
        """Convert timestamps to readable time strings."""
        strings = []
        for v in values:
            try:
                dt = datetime.fromtimestamp(v)
                strings.append(dt.strftime("%H"))
            except (ValueError, OSError):
                strings.append("")
        return strings


class ActivityPlotWidget(pg.PlotWidget):
    """Activity plot widget with restricted pan/zoom and sleep markers."""

    # Marker data change signals (for Redux dispatch via connector)
    sleep_markers_changed = pyqtSignal(DailySleepMarkers)  # Signal for daily sleep markers updates
    nonwear_markers_changed = pyqtSignal(DailyNonwearMarkers)  # Signal for nonwear markers updates

    # Selection change signals (for Redux dispatch via connector)
    sleep_period_selection_changed = pyqtSignal(int)  # Selected sleep period index changed
    nonwear_selection_changed = pyqtSignal(int)  # Selected nonwear marker index changed

    # UI feedback signals
    nonwear_marker_selected = pyqtSignal(object)  # Signal when a nonwear marker is selected (ManualNonwearPeriod or None)
    marker_limit_exceeded = pyqtSignal(str)  # Signal when marker limit exceeded
    error_occurred = pyqtSignal(str)  # Signal when an error occurs that should be shown to user

    # Plot interaction signals - connector decides what action to take based on Redux state
    plot_left_clicked = pyqtSignal(float)  # Emits clicked timestamp - connector decides sleep/nonwear
    plot_right_clicked = pyqtSignal()  # Emits when right-click to cancel incomplete marker

    def __init__(
        self,
        main_window: "AppStateInterface",
        parent=None,
        *,
        get_axis_y_data_for_sadeh: Callable[[], list[float] | None] | None = None,
        get_selected_file: Callable[[], str | None] | None = None,
        create_nonwear_algorithm: Callable[[str], Any] | None = None,
        create_sleep_algorithm: Callable[[str, Any], Any] | None = None,
        create_sleep_period_detector: Callable[[str], Any] | None = None,
        get_default_sleep_algorithm_id: Callable[[], str] | None = None,
        get_default_sleep_period_detector_id: Callable[[], str] | None = None,
        get_choi_activity_column: Callable[[], str] | None = None,
        get_algorithm_config: Callable[[], Any] | None = None,
    ) -> None:
        # Initialize basic attributes BEFORE super() so they exist for early signal/connector calls
        self._active_marker_category = MarkerCategory.SLEEP  # SLEEP or NONWEAR
        self.daily_sleep_markers = DailySleepMarkers()
        self.marker_lines = []
        self._daily_nonwear_markers = DailyNonwearMarkers()
        self._nonwear_marker_lines = []
        self.sleep_rule_markers = []
        self.adjacent_day_marker_lines = []
        self.adjacent_day_marker_labels = []
        self.current_marker_being_placed = None
        self._current_nonwear_marker_being_placed = None
        self._marker_click_in_progress = False
        self._marker_drag_in_progress = False

        # Algorithm/service callbacks (injected by container)
        self._get_axis_y_data_for_sadeh_cb = get_axis_y_data_for_sadeh
        self._get_selected_file = get_selected_file
        self._create_nonwear_algorithm = create_nonwear_algorithm
        self._create_sleep_algorithm = create_sleep_algorithm
        self._create_sleep_period_detector = create_sleep_period_detector
        self._get_default_sleep_algorithm_id = get_default_sleep_algorithm_id
        self._get_default_sleep_period_detector_id = get_default_sleep_period_detector_id
        self._get_choi_activity_column = get_choi_activity_column
        self._get_algorithm_config = get_algorithm_config

        # Initialize basic components needed by other methods early
        self.marker_renderer = PlotMarkerRenderer(self)
        self.overlay_renderer = PlotOverlayRenderer(self)
        self.algorithm_manager = PlotAlgorithmManager(self)
        self.state_serializer = PlotStateSerializer(self)

        # Create with custom time axis
        time_axis = TimeAxisItem(orientation="bottom")
        super().__init__(axisItems={"bottom": time_axis})
        self.app_state = main_window

        # Data boundaries
        self.data_start_time = None
        self.data_end_time = None
        self.data_min_y = 0
        self.data_max_y = 100
        self.max_vm_value = None  # Store the max vector magnitude value for consistent y-axis
        self.current_view_hours = 24

        # Selection state (local state, updated by PlotSelectionConnector from Redux)
        # Widgets are DUMB: they emit signals, connectors dispatch to store
        self._selected_marker_set_index = 1  # Currently selected sleep period (1-10)
        self._selected_nonwear_marker_index = 0  # Currently selected nonwear marker (0=none, 1-10)

        # Save state (local state, updated by PlotSelectionConnector from Redux)
        self._sleep_markers_saved = True  # Whether sleep markers are saved
        self._nonwear_markers_saved_state = True  # Whether nonwear markers are saved

        # Visibility
        self._nonwear_markers_visible = True  # Visibility of nonwear markers

        # Marker editor FSM
        self._marker_editor = MarkerEditor()

        # File info display
        self.file_info_label = None
        self.current_filename = None

        # Store main 48hr data and algorithm results
        self.main_48h_timestamps = None
        self.main_48h_activity = None
        self.main_48h_sadeh_results = None
        # CRITICAL: Sadeh timestamps MUST be stored alongside sadeh_results
        # This ensures apply_sleep_scoring_rules uses matching data
        self.main_48h_sadeh_timestamps: list[datetime] | None = None
        self.main_48h_axis_y_data = None
        # CRITICAL: axis_y timestamps must ONLY be set by _get_axis_y_data_for_sadeh()
        # which uses AlignedActivityData to guarantee alignment with axis_y_data
        self.main_48h_axis_y_timestamps: list[datetime] | None = None
        self._cached_48h_vm_data = None
        self.sadeh_results = None  # Current view Sadeh results

        # Data arrays (initialized to None/empty, populated by set_data_and_restrictions)
        self.x_data = None
        self.activity_data = None
        self.timestamps = None
        self.activity_plot_item = None
        self.nonwear_data = None
        self.nonwear_regions = []  # Visual region objects for nonwear
        self._algorithm_cache = {}

        # Setup plot appearance
        self._setup_plot_appearance()

        # Connect event handlers
        self._setup_event_handlers()

    def create_nonwear_algorithm(self, algorithm_id: str) -> Any:
        """Create a nonwear algorithm via injected factory."""
        if not self._create_nonwear_algorithm:
            msg = "Missing nonwear algorithm factory callback"
            raise RuntimeError(msg)
        return self._create_nonwear_algorithm(algorithm_id)

    def create_sleep_algorithm(self, algorithm_id: str, config: Any) -> Any:
        """Create a sleep scoring algorithm via injected factory."""
        if not self._create_sleep_algorithm:
            msg = "Missing sleep algorithm factory callback"
            raise RuntimeError(msg)
        return self._create_sleep_algorithm(algorithm_id, config)

    def create_sleep_period_detector(self, detector_id: str) -> Any:
        """Create a sleep period detector via injected factory."""
        if not self._create_sleep_period_detector:
            msg = "Missing sleep period detector factory callback"
            raise RuntimeError(msg)
        return self._create_sleep_period_detector(detector_id)

    def get_default_sleep_algorithm_id(self) -> str:
        """Get default sleep algorithm id via injected callback."""
        if not self._get_default_sleep_algorithm_id:
            msg = "Missing default sleep algorithm id callback"
            raise RuntimeError(msg)
        return self._get_default_sleep_algorithm_id()

    def get_default_sleep_period_detector_id(self) -> str:
        """Get default sleep period detector id via injected callback."""
        if not self._get_default_sleep_period_detector_id:
            msg = "Missing default sleep period detector id callback"
            raise RuntimeError(msg)
        return self._get_default_sleep_period_detector_id()

    @property
    def actual_data_bounds(self) -> tuple[float, float] | None:
        """Return (start, end) timestamps from actual loaded data, or None if no data."""
        if self.x_data is not None and len(self.x_data) > 0:
            return (float(self.x_data[0]), float(self.x_data[-1]))
        return None

    def get_choi_activity_column(self) -> str:
        """Get Choi activity column via injected callback."""
        if self._get_choi_activity_column:
            return self._get_choi_activity_column()
        return ActivityDataPreference.VECTOR_MAGNITUDE

    def get_algorithm_config(self) -> Any:
        """Get algorithm config via injected callback."""
        if self._get_algorithm_config:
            return self._get_algorithm_config()
        return None

    @property
    def selected_marker_set_index(self) -> int:
        """Get the currently selected sleep marker set index (local state)."""
        return self._selected_marker_set_index

    @selected_marker_set_index.setter
    def selected_marker_set_index(self, value: int) -> None:
        """Set selected sleep marker set index. Emits signal for connector to dispatch."""
        if self._selected_marker_set_index != value:
            self._selected_marker_set_index = value
            self.sleep_period_selection_changed.emit(value)

    def set_selected_marker_set_index_from_store(self, value: int) -> None:
        """Update local state from Redux store (called by connector only)."""
        self._selected_marker_set_index = value

    @property
    def selected_nonwear_marker_index(self) -> int:
        """Get the currently selected nonwear marker index (local state)."""
        return self._selected_nonwear_marker_index

    @selected_nonwear_marker_index.setter
    def selected_nonwear_marker_index(self, value: int) -> None:
        """Set selected nonwear marker index. Emits signal for connector to dispatch."""
        if self._selected_nonwear_marker_index != value:
            self._selected_nonwear_marker_index = value
            self.nonwear_selection_changed.emit(value)

    def set_selected_nonwear_marker_index_from_store(self, value: int) -> None:
        """Update local state from Redux store (called by connector only)."""
        self._selected_nonwear_marker_index = value

    @property
    def nonwear_markers_saved(self) -> bool:
        """Check if all nonwear markers are saved (local state)."""
        return self._nonwear_markers_saved_state

    def set_nonwear_markers_saved_from_store(self, saved: bool) -> None:
        """Update local state from Redux store (called by connector only)."""
        self._nonwear_markers_saved_state = saved

    def _setup_plot_appearance(self) -> None:
        """Configure plot appearance and styling with performance optimizations."""
        # Remove axis labels
        self.setLabel("bottom", "")  # Remove X-axis label
        self.getAxis("left").setLabel("")  # Remove Y-axis label but keep ticks
        self.showGrid(x=True, y=True, alpha=0.2)

        # Configure tick spacing for more uniform appearance
        self.getAxis("bottom").setTickSpacing(major=3600, minor=900)  # Major ticks every hour, minor every 15 min
        self.getAxis("left").enableAutoSIPrefix(False)  # Disable scientific notation
        self.getAxis("left").setTickSpacing(major=None, minor=None)  # Auto spacing for Y-axis

        # Improve plot styling
        self.getAxis("left").setPen(pg.mkPen(color="#333333", width=1))
        self.getAxis("bottom").setPen(pg.mkPen(color="#333333", width=1))
        self.getAxis("left").setTextPen(pg.mkPen(color="#444444"))
        self.getAxis("bottom").setTextPen(pg.mkPen(color="#444444"))

        # Set to panning mode instead of rectangle selection
        plot_item = self.plotItem
        if plot_item is not None:
            if (view_box := plot_item.getViewBox()) is not None:
                view_box.setMouseMode(pg.ViewBox.PanMode)
                view_box.setMenuEnabled(False)

            # Disable context menu to prevent unwanted interactions
            plot_item.setMenuEnabled(False)

            # Performance optimizations for pyqtgraph
            # Enable OpenGL for better rendering performance if available
            try:
                if hasattr(plot_item, "setUseOpenGL"):
                    plot_item.setUseOpenGL(True)
            except AttributeError:
                # OpenGL not available, continue with software rendering
                pass

            # Optimize rendering settings (check availability first)
            try:
                if hasattr(plot_item, "setDownsampling"):
                    plot_item.setDownsampling(mode="peak")  # Use peak downsampling for better performance
                if hasattr(plot_item, "setClipToView"):
                    plot_item.setClipToView(True)  # Only render visible data
                if hasattr(plot_item, "setAutoDownsample"):
                    plot_item.setAutoDownsample(True)  # Enable automatic downsampling
            except AttributeError:
                # These optimization methods not available in this pyqtgraph version
                pass

            # Reduce anti-aliasing for better performance (can be re-enabled if needed)
            try:
                if hasattr(plot_item, "setAntialiasing"):
                    plot_item.setAntialiasing(False)
            except AttributeError:
                pass

        # Add focus indicator for accessibility
        self.setStyleSheet("""
            ActivityPlotWidget:focus {
                border: 3px solid #0080FF;
                background-color: #fafbff;
            }
        """)

    # ========== Save State Properties (local state, updated by connector) ==========
    # Widgets are DUMB: local state is updated by PlotSelectionConnector from Redux.
    # mark_*_dirty() methods emit signals, connector dispatches to store.

    @property
    def markers_saved(self) -> bool:
        """Check if sleep markers are saved (local state)."""
        return self._sleep_markers_saved

    def set_sleep_markers_saved_from_store(self, saved: bool) -> None:
        """Update local state from Redux store (called by connector only)."""
        self._sleep_markers_saved = saved

    @property
    def _nonwear_markers_saved(self) -> bool:
        """Check if nonwear markers are saved (local state)."""
        return self._nonwear_markers_saved_state

    def mark_sleep_markers_dirty(self) -> None:
        """
        Mark sleep markers as dirty. Emits signal for connector to dispatch.

        NOTE: Local state is NOT set here. Redux is the single source of truth.
        The MarkersConnector will sync Redux state back to widget after dispatch.
        """
        self.sleep_markers_changed.emit(self.daily_sleep_markers)

    def mark_nonwear_markers_dirty(self) -> None:
        """
        Mark nonwear markers as dirty. Emits signal for connector to dispatch.

        NOTE: Local state is NOT set here. Redux is the single source of truth.
        The MarkersConnector will sync Redux state back to widget after dispatch.
        """
        self.nonwear_markers_changed.emit(self._daily_nonwear_markers)

    def update_cursor_from_editor_mode(self) -> None:
        """Update the cursor based on the current marker editor mode."""
        self.setCursor(self._marker_editor.cursor)

    def get_editor_status_text(self) -> str:
        """
        Get the status text from the marker editor FSM.

        Returns:
            Status message string describing the current editing mode

        """
        return self._marker_editor.status_text

    def _setup_event_handlers(self) -> None:
        """Setup event handlers for mouse and keyboard interaction."""
        # Get ViewBox for range control
        plot_item = self.plotItem
        if plot_item is None:
            logger.warning("Cannot setup event handlers - plotItem is None")
            return

        self.vb = plot_item.getViewBox()
        if self.vb:
            self.vb.sigRangeChanged.connect(self.enforce_range_limits)

        # Connect mouse clicks
        scene = plot_item.scene()
        if scene:
            scene.sigMouseClicked.connect(self.on_plot_clicked)

        # Connect mouse hover for tooltips with throttling
        self._mouse_move_timer = QTimer()
        self._mouse_move_timer.setSingleShot(True)
        self._mouse_move_timer.timeout.connect(self._process_mouse_move)
        self._last_mouse_pos = None

        if scene:
            scene.sigMouseMoved.connect(self._on_mouse_move_throttled)
        self.setMouseTracking(True)

        # Enable keyboard focus for key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def cleanup_widget(self) -> None:
        """Clean up widget resources to prevent memory leaks."""
        try:
            # Stop and cleanup mouse move timer
            if self._mouse_move_timer:
                self._mouse_move_timer.stop()
                self._mouse_move_timer.timeout.disconnect()
                self._mouse_move_timer.deleteLater()
                self._mouse_move_timer = None

            # Disconnect signals to prevent reference cycles
            try:
                if self.vb:
                    self.vb.sigRangeChanged.disconnect()
            except (TypeError, RuntimeError):
                # Signal already disconnected or object deleted
                pass

            try:
                if self.plotItem:
                    scene = self.plotItem.scene()
                    if scene:
                        scene.sigMouseClicked.disconnect()
                        scene.sigMouseMoved.disconnect()
            except (TypeError, RuntimeError):
                # Signal already disconnected or object deleted
                pass

            # Clear data references
            self.timestamps = None
            self.main_48h_timestamps = None
            self.main_48h_activity = None
            self.main_48h_sadeh_results = None
            self.main_48h_sadeh_timestamps = None  # CRITICAL: Clear alongside sadeh_results
            self.main_48h_axis_y_data = None
            self.main_48h_axis_y_timestamps = None
            self._cached_48h_vm_data = None
            self._last_mouse_pos = None

            # Clear marker lines and sleep rule markers
            for line in self.marker_lines:
                try:
                    if hasattr(line, "deleteLater"):
                        line.deleteLater()
                except (RuntimeError, AttributeError):
                    pass
            self.marker_lines.clear()

            if self.sleep_rule_markers:
                for marker in self.sleep_rule_markers:
                    try:
                        if hasattr(marker, "deleteLater"):
                            marker.deleteLater()
                    except (RuntimeError, AttributeError):
                        pass
                self.sleep_rule_markers.clear()

            logger.debug("ActivityPlotWidget cleanup completed")

        except Exception as e:
            logger.warning(f"Error during ActivityPlotWidget cleanup: {e}")

    def set_data_and_restrictions(
        self,
        timestamps: list[datetime] | None,
        activity_data: list[float] | None,
        view_hours: int = 24,
        skip_nonwear_plotting: bool = False,
        filename: str | None = None,
        activity_column_type: ActivityDataPreference | None = None,
        current_date: datetime | None = None,
    ) -> None:
        """Set data and establish pan/zoom restrictions."""
        import logging

        logger = logging.getLogger(__name__)

        logger.info(
            "PLOT WIDGET: set_data_and_restrictions called with %s timestamps, %s activity_data, view_hours=%s, filename=%s",
            len(timestamps) if timestamps else 0,
            len(activity_data) if activity_data else 0,
            view_hours,
            filename,
        )

        # Guard against None or empty data - clear the plot instead
        if activity_data is None or (timestamps is not None and len(timestamps) == 0):
            logger.warning("PLOT WIDGET: No activity data provided, clearing plot")
            self.clear_plot()
            return

        self.current_view_hours = view_hours
        self.current_filename = filename

        # Cached results are managed by NonwearData system

        # Convert timestamps to numeric values (optimized for performance)
        self.timestamps = timestamps
        # Use vectorized conversion for better performance with large datasets
        if timestamps:
            # Convert timestamps to numeric values directly (avoid numpy datetime corruption)
            self.x_data = np.array([ts.timestamp() for ts in timestamps])
        else:
            self.x_data = np.array([])

        logger.info("PLOT WIDGET: Converted %s timestamps to x_data array", len(self.x_data))

        # Calculate expected time boundaries based on view mode (not actual data bounds)
        # This ensures consistent display regardless of data availability

        # Use the provided current_date for plot bounds
        if current_date is not None:
            target_date = current_date
        elif len(self.x_data) > 0:
            # Fallback to first timestamp if no current_date provided
            target_date = datetime.fromtimestamp(self.x_data[0])
        else:
            # If no data and no current_date, use current date
            target_date = datetime.now()

        # Calculate date range using centralized utility
        date_range = get_range_for_view_mode(target_date, view_hours)
        expected_start = date_range.start
        expected_end = date_range.end

        # Set data boundaries to expected full range (not actual data range)
        self.data_start_time = expected_start.timestamp()
        self.data_end_time = expected_end.timestamp()

        # Set Y-axis boundaries based on actual data
        self.data_min_y = 0  # Always start at zero

        # Always calculate max based on the actual data
        current_max = max(activity_data) if activity_data else 200

        # Store max VM value if this is vector magnitude data
        if activity_column_type == DatabaseColumn.VECTOR_MAGNITUDE:
            self.max_vm_value = current_max
            # Use VM max for y-axis
            self.data_max_y = self.max_vm_value * 1.5
        # For axis_y, still use VM max if available, otherwise use current
        elif self.max_vm_value is not None:
            self.data_max_y = self.max_vm_value * 1.5
        else:
            # No VM data yet, temporarily use axis_y max
            self.data_max_y = current_max * 1.5

        # Clear existing plot
        self.clear()
        self.clear_sleep_markers()

        # Store raw data for potential future use (may be axis_y or vector_magnitude)
        self.activity_data = activity_data

        # ALWAYS store as main 48h data — the service layer loads 48h regardless of view mode.
        # View mode only affects the visual viewport, not the underlying data.
        self.main_48h_timestamps = timestamps
        self.main_48h_activity = activity_data
        # CRITICAL: Clear ALL algorithm-related data to force fresh reload
        self.main_48h_axis_y_data = None
        self.main_48h_axis_y_timestamps = None
        self.main_48h_sadeh_results = None
        self.main_48h_sadeh_timestamps = None  # Must clear alongside sadeh_results
        self._cached_48h_vm_data = None
        # Also clear algorithm manager's caches
        if self.algorithm_manager is not None:
            self.algorithm_manager._algorithm_cache.clear()
        logger.debug("Stored main 48h data: %d timestamps, cleared all algorithm caches", len(timestamps) if timestamps else 0)

        # Store column type for later reference
        self.activity_column_type = activity_column_type

        # axis_y_data will be loaded on demand via property using unified loader
        logger.debug("PLOT WIDGET: Activity column type: %s", activity_column_type)

        # Data loaded successfully
        logger.info("PLOT WIDGET: About to plot data - x_data: %s points, activity_data: %s points", len(self.x_data), len(activity_data))

        # Plot activity data with improved styling and store reference for seamless updates
        self.activity_plot_item = self.plot(
            self.x_data,
            activity_data,
            pen=pg.mkPen(color="#2E86AB", width=2),
            name="Activity Data",
        )

        logger.info("PLOT WIDGET: Plot data added successfully, plot_item: %s", self.activity_plot_item)

        # Run and plot algorithms (optimized)
        # Note: This will only plot Choi if no nonwear sensor data is available
        if not skip_nonwear_plotting:
            self.plot_algorithms()

        # Set view to actual data range (show where data actually exists)
        if len(self.x_data) > 0:
            actual_start = float(self.x_data[0])
            actual_end = float(self.x_data[-1])
            padding = (actual_end - actual_start) * 0.02  # 2% padding
            start_time = actual_start - padding
            end_time = actual_end + padding
        else:
            # Fallback to expected range if no data
            start_time = self.data_start_time
            end_time = self.data_end_time

        # Configure Y-axis range and ticks to match data
        self.getAxis("left").setRange(self.data_min_y, self.data_max_y)

        # Set view range with Y constrained to data range
        logger.info("PLOT WIDGET: Setting view range - x: [%s, %s], y: [%s, %s]", start_time, end_time, self.data_min_y, self.data_max_y)

        self.vb.setRange(
            xRange=[start_time, end_time],
            yRange=[self.data_min_y, self.data_max_y],
            padding=0,
        )

        logger.info("PLOT WIDGET: Plot setup completed successfully")

        # Update file info label
        self._update_file_info_label()

    def update_view_range_only(self, view_hours: int, current_date=None) -> None:
        """Update ONLY the visual range of the plot, not the underlying data."""
        self.current_view_hours = view_hours

        # Use the provided current_date for plot bounds
        if current_date is not None:
            target_date = current_date
        elif self.x_data is not None and len(self.x_data) > 0:
            # Fallback to first timestamp if no current_date provided
            target_date = datetime.fromtimestamp(self.x_data[0])
        else:
            # If no data and no current_date, use current date
            target_date = datetime.now()

        # Calculate date range using centralized utility
        date_range = get_range_for_view_mode(target_date, view_hours)
        expected_start = date_range.start
        expected_end = date_range.end

        # Just update the view range, not the data
        start_time = expected_start.timestamp()
        end_time = expected_end.timestamp()

        # Update data boundaries for marker validation
        self.data_start_time = start_time
        self.data_end_time = end_time

        # Keep Y-axis bounds unchanged when only switching view mode.
        # 24h/48h should differ by X-range restriction, not by recalculating Y-scale.
        if not self.activity_data:
            self.data_min_y = 0
            self.data_max_y = 200

        # Update the view box range
        self.vb.setRange(
            xRange=[start_time, end_time],
            yRange=[self.data_min_y, self.data_max_y],
            padding=0,
        )

        # Redraw sleep markers in the new range
        self.redraw_markers()

        # Also refresh sleep scoring rule arrows after view range change
        selected_period = self.marker_renderer.get_selected_marker_period()
        if selected_period and selected_period.is_complete:
            self.apply_sleep_scoring_rules(selected_period)

        # Update file info label
        self._update_file_info_label()

    def update_data_and_view_only(self, timestamps, activity_data, view_hours=24, current_date=None) -> None:
        """Update data and view without clearing sleep markers - for view mode switching."""
        self.current_view_hours = view_hours

        # ALWAYS update timestamps - different dates have different timestamp values
        # even if they have the same number of data points
        self.timestamps = timestamps
        if timestamps:
            self.x_data = np.array([ts.timestamp() for ts in timestamps])
        else:
            self.x_data = np.array([])

        # Calculate expected time boundaries based on view mode (not actual data bounds)
        # This ensures consistent display regardless of data availability

        # Use the provided current_date for plot bounds
        if current_date is not None:
            target_date = current_date
        elif len(self.x_data) > 0:
            # Fallback to first timestamp if no current_date provided
            target_date = datetime.fromtimestamp(self.x_data[0])
        else:
            # If no data and no current_date, use current date
            target_date = datetime.now()

        # Calculate date range using centralized utility
        date_range = get_range_for_view_mode(target_date, view_hours)
        expected_start = date_range.start
        expected_end = date_range.end

        # Set data boundaries to expected full range
        self.data_start_time = expected_start.timestamp()
        self.data_end_time = expected_end.timestamp()

        # Set Y-axis boundaries based on actual data
        self.data_min_y = 0  # Always start at zero

        # Update Y-axis max based on actual data if not already set or if data changed
        # This ensures the plot displays properly on first load
        if activity_data is not None and len(activity_data) > 0:
            current_max = max(activity_data) if hasattr(activity_data, "__iter__") else 100
            # Only update if we don't have a valid max or if this is significantly different
            if self.data_max_y <= 100 or current_max > self.data_max_y:
                self.data_max_y = current_max * 1.5
                logger.debug(f"Updated data_max_y to {self.data_max_y} based on data max {current_max}")

        # Always update the data (could be switching between VM and axis_y)
        self.activity_data = activity_data

        # ALWAYS store as main 48h data — the service layer loads 48h regardless of view mode.
        # View mode only affects the visual viewport, not the underlying data.
        self.main_48h_timestamps = timestamps
        self.main_48h_activity = activity_data
        # NOTE: Do NOT set axis_y timestamps here — main_48h_axis_y_timestamps must ONLY
        # be set by the unified axis_y loader which uses AlignedActivityData to guarantee
        # timestamps and data are aligned. Don't clear axis_y cache either.
        logger.debug("Stored main 48h reference data: %d timestamps", len(timestamps) if timestamps else 0)

        # Check if we have an existing plot item to update
        if self.activity_plot_item is not None:
            # Update existing plot item with new data
            self.activity_plot_item.setData(self.x_data, activity_data)
            logger.debug("Updated existing plot item with new activity data")
        else:
            # Create new plot item if none exists
            self.clear()
            self.activity_plot_item = self.plot(
                self.x_data,
                activity_data,
                pen=pg.mkPen(color="#2E86AB", width=2),
                name="Activity Data",
            )

            # Run algorithms if needed
            if self.nonwear_data is None:
                self.plot_algorithms()

        # Update the view range — get_range_for_view_mode already handles 24h vs 48h
        start_time = expected_start.timestamp()
        end_time = expected_end.timestamp()

        # Configure Y-axis range and ticks to match data
        self.getAxis("left").setRange(self.data_min_y, self.data_max_y)

        # Set view range with Y constrained to data range
        self.vb.setRange(
            xRange=[start_time, end_time],
            yRange=[self.data_min_y, self.data_max_y],
            padding=0,
        )

        # Restore sleep markers if they exist
        if self.daily_sleep_markers.get_all_periods():
            self.redraw_markers()

            # CRITICAL FIX: Also refresh sleep scoring rule arrows after view switch
            # This ensures arrows are visible after switching between 24h/48h views
            selected_period = self.marker_renderer.get_selected_marker_period()
            if selected_period and selected_period.is_complete:
                self.apply_sleep_scoring_rules(selected_period)

    def swap_activity_data(self, new_timestamps: list[datetime], new_activity_data: list[float], new_column_type: str) -> None:
        """
        Seamlessly swap activity data without triggering full plot recreation or state loss.

        This method preserves all plot widget state including:
        - Current zoom level and pan position
        - Sleep markers and their positions
        - Nonwear visualizations
        - All other plot elements and settings

        Args:
            new_timestamps: New timestamp data
            new_activity_data: New activity values
            new_column_type: Column type identifier for logging/debugging

        """
        logger.info("SEAMLESS SWAP: Starting data swap to %s column with %s data points", new_column_type, len(new_activity_data))

        try:
            # Store current view state to preserve after swap
            current_view_range = self.vb.viewRange()
            # Validate viewRange returned a valid structure
            if not current_view_range or len(current_view_range) < 2:
                logger.warning("viewRange returned invalid structure, using defaults")
                current_x_range = [0, 86400]  # Default 24h range
            else:
                current_x_range = current_view_range[0] if current_view_range[0] else [0, 86400]

            # Convert new timestamps to numeric values for plot compatibility
            if new_timestamps:
                # Convert timestamps to numeric values directly (avoid numpy datetime corruption)
                new_x_data = np.array([ts.timestamp() for ts in new_timestamps])
            else:
                new_x_data = np.array([])

            # Update internal data references
            self.timestamps = new_timestamps
            self.x_data = new_x_data
            self.activity_data = new_activity_data

            # Update column type for property access
            self.activity_column_type = new_column_type

            # axis_y_data will be loaded on demand via property
            logger.debug("SEAMLESS SWAP: Column type now %s", new_column_type)

            # Update Y-axis boundaries - keep consistent using VM max
            if new_column_type == DatabaseColumn.VECTOR_MAGNITUDE:
                # Update max VM value when we have vector magnitude data
                self.max_vm_value = max(new_activity_data) if new_activity_data else 200
                self.data_max_y = self.max_vm_value * 1.5
            # When switching to axis_y, DON'T change the y-axis range at all!
            # Just keep using whatever data_max_y was already set

            # Check if we have an existing activity plot item to update
            if self.activity_plot_item is not None:
                # Direct data update - this is the key to seamless swapping
                self.activity_plot_item.setData(new_x_data, new_activity_data)
                logger.debug("SEAMLESS SWAP: Updated existing plot item data directly")
            else:
                # Fallback: create new plot item if none exists
                logger.warning("SEAMLESS SWAP: No existing plot item found, creating new one")
                self.activity_plot_item = self.plot(
                    new_x_data,
                    new_activity_data,
                    pen=pg.mkPen(color="#2E86AB", width=2),
                    name="Activity Data",
                )

            # Update Y-axis range to fixed VM-based range
            self.getAxis("left").setRange(self.data_min_y, self.data_max_y)

            # Restore the X view but keep Y fixed to VM range
            preserved_x_range = current_x_range
            fixed_y_range = [self.data_min_y, self.data_max_y]

            self.vb.setRange(
                xRange=preserved_x_range,
                yRange=fixed_y_range,
                padding=0,
            )

            # Always clear algorithm cache when activity data changes
            # This ensures correct algorithm results for the new activity source
            self._algorithm_cache.clear()
            logger.debug("SEAMLESS SWAP: Cleared algorithm cache for new activity data")

            # Recalculate algorithms with new data
            # NonwearData system will handle its own updates if active
            if self.nonwear_data is not None:
                logger.debug("SEAMLESS SWAP: NonwearData system active, will update separately")
            self.plot_algorithms()

            # Update file info label to reflect new data source
            self._update_file_info_label()

            logger.info("SEAMLESS SWAP: Data swap completed successfully, preserved view state")

        except Exception as e:
            logger.exception("SEAMLESS SWAP: Failed to swap data: %s", e)
            logger.exception("SEAMLESS SWAP: Traceback: %s", traceback.format_exc())
            # Don't raise - let the application continue with existing data

    def enforce_range_limits(self) -> None:
        """Enforce strict pan/zoom boundaries."""
        if self.data_start_time is None or self.data_end_time is None:
            return

        current_range = self.vb.viewRange()
        # Validate viewRange returned a valid structure
        if not current_range or len(current_range) < 2:
            return  # Can't enforce limits without valid range
        x_range = current_range[0]  # [xmin, xmax]
        y_range = current_range[1]  # [ymin, ymax]
        if not x_range or len(x_range) < 2 or not y_range or len(y_range) < 2:
            return  # Invalid range structure

        # Calculate allowed boundaries based on display mode
        data_start = self.data_start_time
        data_end = self.data_end_time
        if self.current_view_hours == 24:
            # 24h mode: can only view within the 24h window
            max_start = data_start
            max_end = data_start + (24 * 3600)
            max_end = min(max_end, data_end)  # Don't exceed actual data
        else:
            # 48h mode: can view full dataset
            max_start = data_start
            max_end = data_end

        # Correct out-of-bounds X ranges
        x_min = max(x_range[0], max_start)  # Can't pan before start
        x_max = min(x_range[1], max_end)  # Can't pan after end

        # Prevent zooming out beyond allowed range
        current_width = x_max - x_min
        max_width = max_end - max_start

        if current_width > max_width:
            # Force back to full allowed range
            x_min = max_start
            x_max = max_end
        elif x_max - x_min < 1800:  # Minimum 30 minutes visible
            # Prevent over-zooming
            center = (x_range[0] + x_range[1]) / 2
            x_min = center - 900  # 15 minutes before center
            x_max = center + 900  # 15 minutes after center

            # Adjust if this pushes us out of bounds
            if x_min < max_start:
                x_min = max_start
                x_max = x_min + 1800
            elif x_max > max_end:
                x_max = max_end
                x_min = x_max - 1800

        # Force Y range to always be the full data range (no Y-axis zooming)
        y_min = self.data_min_y  # Always 0
        y_max = self.data_max_y  # Always 1.5x max value

        # Fix Y-axis range on the axis itself to prevent visual changes
        self.getAxis("left").setRange(y_min, y_max)

        # Also fix X-axis range to prevent visual axis number changes
        self.getAxis("bottom").setRange(x_min, x_max)

        # Apply corrected ranges if needed
        x_changed = abs(x_min - x_range[0]) > 0.1 or abs(x_max - x_range[1]) > 0.1
        y_changed = abs(y_min - y_range[0]) > 0.1 or abs(y_max - y_range[1]) > 0.1

        if x_changed or y_changed:
            self.vb.blockSignals(True)
            try:
                self.vb.setRange(xRange=[x_min, x_max], yRange=[y_min, y_max], padding=0)
            finally:
                self.vb.blockSignals(False)

    def keyPressEvent(self, ev: QKeyEvent) -> None:  # Qt naming convention
        """Handle keyboard events for marker adjustment and clearing."""
        key = ev.key()
        logger.debug(f"Key pressed: {key} (C={Qt.Key.Key_C}, Delete={Qt.Key.Key_Delete})")

        # Handle Escape key via FSM
        if self._marker_editor.on_key_press(key):
            logger.debug("Escape key handled by MarkerEditor FSM - cancelled current operation")
            # Cancel any incomplete markers
            if self._active_marker_category == MarkerCategory.SLEEP:
                self.cancel_incomplete_marker()
            elif self._active_marker_category == MarkerCategory.NONWEAR:
                self.cancel_incomplete_nonwear_marker()
            return

        # Handle clear marker shortcuts and incomplete marker cancellation (C and Delete)
        if key in (Qt.Key.Key_C, Qt.Key.Key_Delete):
            if self._active_marker_category == MarkerCategory.SLEEP:
                # First check if there's an incomplete marker to cancel
                if self.current_marker_being_placed is not None:
                    logger.debug("Delete/C key detected - cancelling incomplete sleep marker placement")
                    self.cancel_incomplete_marker()
                    return
                # Otherwise, clear selected marker set
                logger.debug("Clear sleep marker shortcut detected")
                self.clear_selected_marker_set()
            elif self._active_marker_category == MarkerCategory.NONWEAR:
                # First check if there's an incomplete nonwear marker to cancel
                if self._current_nonwear_marker_being_placed is not None:
                    logger.debug("Delete/C key detected - cancelling incomplete nonwear marker placement")
                    self.cancel_incomplete_nonwear_marker()
                    return
                # Otherwise, clear selected nonwear marker
                logger.debug("Clear nonwear marker shortcut detected")
                self.clear_selected_nonwear_marker()
            return

        # Handle marker adjustment based on active marker category
        if self._active_marker_category == MarkerCategory.SLEEP:
            # Handle marker adjustment for currently selected sleep marker set
            selected_period = self.get_selected_marker_period()
            if selected_period and selected_period.is_complete:
                if key == Qt.Key.Key_Q:  # Move onset left
                    self.adjust_selected_marker(SleepMarkerEndpoint.ONSET, -60)  # -1 minute
                elif key == Qt.Key.Key_E:  # Move onset right
                    self.adjust_selected_marker(SleepMarkerEndpoint.ONSET, 60)  # +1 minute
                elif key == Qt.Key.Key_A:  # Move offset left
                    self.adjust_selected_marker(SleepMarkerEndpoint.OFFSET, -60)  # -1 minute
                elif key == Qt.Key.Key_D:  # Move offset right
                    self.adjust_selected_marker(SleepMarkerEndpoint.OFFSET, 60)  # +1 minute
                else:
                    super().keyPressEvent(ev)
            else:
                super().keyPressEvent(ev)
        elif self._active_marker_category == MarkerCategory.NONWEAR:
            # Handle marker adjustment for currently selected nonwear marker
            selected_period = self.get_selected_nonwear_period()
            if selected_period and selected_period.is_complete:
                if key == Qt.Key.Key_Q:  # Move start left
                    self.adjust_selected_nonwear_marker(MarkerEndpoint.START, -60)  # -1 minute
                elif key == Qt.Key.Key_E:  # Move start right
                    self.adjust_selected_nonwear_marker(MarkerEndpoint.START, 60)  # +1 minute
                elif key == Qt.Key.Key_A:  # Move end left
                    self.adjust_selected_nonwear_marker(MarkerEndpoint.END, -60)  # -1 minute
                elif key == Qt.Key.Key_D:  # Move end right
                    self.adjust_selected_nonwear_marker(MarkerEndpoint.END, 60)  # +1 minute
                else:
                    super().keyPressEvent(ev)
            else:
                super().keyPressEvent(ev)
        else:
            super().keyPressEvent(ev)

    def adjust_main_sleep_marker(self, marker_type: str, seconds_delta: int) -> None:
        """Adjust main sleep marker by specified number of seconds."""
        main_sleep = self.daily_sleep_markers.get_main_sleep()
        if not main_sleep or not main_sleep.is_complete:
            return

        # Get current timestamp - is_complete guarantees both timestamps exist
        onset_ts = main_sleep.onset_timestamp
        offset_ts = main_sleep.offset_timestamp
        if onset_ts is None or offset_ts is None:
            return  # Should not happen due to is_complete check above

        if marker_type == SleepMarkerEndpoint.ONSET:
            current_timestamp = onset_ts
        elif marker_type == SleepMarkerEndpoint.OFFSET:
            current_timestamp = offset_ts
        else:
            return

        # Calculate new timestamp
        new_timestamp = current_timestamp + seconds_delta

        # Ensure timestamp is within actual data bounds (not view bounds)
        if self.x_data is None or len(self.x_data) == 0:
            return
        if not (self.x_data[0] <= new_timestamp <= self.x_data[-1]):
            return

        # Update the timestamp
        if marker_type == SleepMarkerEndpoint.ONSET:
            # Ensure onset is before offset
            if new_timestamp < offset_ts:
                main_sleep.onset_timestamp = new_timestamp
            else:
                return
        elif marker_type == SleepMarkerEndpoint.OFFSET:
            # Ensure offset is after onset
            if new_timestamp > onset_ts:
                main_sleep.offset_timestamp = new_timestamp
            else:
                return

        # Update classifications and redraw
        self.daily_sleep_markers.update_classifications()
        self.redraw_markers()
        self.mark_sleep_markers_dirty()  # Mark state as dirty via Redux

    def move_marker_to_timestamp(self, marker_type: str, target_timestamp: float, period_slot: int | None = None) -> bool:
        """
        Move a marker to a specific timestamp with validation.

        Args:
            marker_type: "onset" or "offset"
            target_timestamp: Unix timestamp to move the marker to
            period_slot: Optional period slot (1-4). If None, uses main sleep period.

        Returns:
            bool: True if marker was moved successfully, False otherwise

        """
        # Snap to nearest minute
        target_timestamp = round(target_timestamp / 60) * 60

        # Ensure timestamp is within actual data bounds (not view bounds)
        if self.x_data is None or len(self.x_data) == 0:
            logger.warning("Cannot move marker - no data loaded")
            return False
        if not (self.x_data[0] <= target_timestamp <= self.x_data[-1]):
            logger.warning(f"Target timestamp {target_timestamp} is outside data bounds [{self.x_data[0]}, {self.x_data[-1]}]")
            return False

        # Get the target period
        if period_slot is None:
            # Use main sleep period
            period = self.daily_sleep_markers.get_main_sleep()
            if not period:
                logger.warning("No main sleep period to move marker for")
                return False
        else:
            # Get period by slot
            period = self.daily_sleep_markers.get_period_by_slot(period_slot)
            if not period:
                logger.warning(f"No period found in slot {period_slot}")
                return False

        # Check if period is complete (has both markers)
        if not period.is_complete:
            logger.warning("Cannot move marker for incomplete period")
            return False

        # is_complete guarantees both timestamps are not None
        onset_ts = period.onset_timestamp
        offset_ts = period.offset_timestamp
        if onset_ts is None or offset_ts is None:
            return False  # Should not happen due to is_complete check

        # Validate the new position
        if marker_type == SleepMarkerEndpoint.ONSET:
            # Ensure onset would be before offset
            if target_timestamp >= offset_ts:
                logger.warning(f"Cannot move onset to {target_timestamp} - would be after offset at {offset_ts}")
                return False
            # Update onset timestamp
            period.onset_timestamp = target_timestamp
        elif marker_type == SleepMarkerEndpoint.OFFSET:
            # Ensure offset would be after onset
            if target_timestamp <= onset_ts:
                logger.warning(f"Cannot move offset to {target_timestamp} - would be before onset at {onset_ts}")
                return False
            # Update offset timestamp
            period.offset_timestamp = target_timestamp
        else:
            logger.warning(f"Invalid marker type: {marker_type}")
            return False

        # Update classifications and check for duration ties
        self.daily_sleep_markers.update_classifications()
        if self.daily_sleep_markers.check_duration_tie():
            # Duration tie detected - notify user but keep markers
            self.marker_limit_exceeded.emit("Warning: Multiple periods with identical duration detected")

        # Redraw markers and apply sleep scoring rules
        self.redraw_markers()

        # Apply sleep scoring rules if this is the selected period
        if period is self.get_selected_marker_period():
            self.apply_sleep_scoring_rules(period)

        # Emit change signal (redraw_markers doesn't always emit this)
        self.mark_sleep_markers_dirty()  # Mark state as dirty via Redux

        logger.info(f"Successfully moved {marker_type} marker to timestamp {target_timestamp}")
        return True

    def move_nonwear_marker_to_timestamp(self, marker_type: str, target_timestamp: float, period_slot: int | None = None) -> bool:
        """
        Move a nonwear marker to a specific timestamp with validation.

        Args:
            marker_type: "start" or "end"
            target_timestamp: Unix timestamp to move the marker to
            period_slot: Optional period slot (1-10). If None, uses selected nonwear period.

        Returns:
            bool: True if marker was moved successfully, False otherwise

        """
        # Snap to nearest minute
        target_timestamp = round(target_timestamp / 60) * 60

        # Ensure timestamp is within actual data bounds (not view bounds)
        if self.x_data is None or len(self.x_data) == 0:
            logger.warning("Cannot move nonwear marker - no data loaded")
            return False
        if not (self.x_data[0] <= target_timestamp <= self.x_data[-1]):
            logger.warning(f"Target timestamp {target_timestamp} is outside data bounds [{self.x_data[0]}, {self.x_data[-1]}]")
            return False

        # Get the target period
        if period_slot is None:
            # Use selected nonwear period
            period = self.marker_renderer.get_selected_nonwear_period()
            if not period:
                logger.warning("No nonwear period selected to move marker for")
                return False
        else:
            # Get period by slot
            period = self._daily_nonwear_markers.get_period_by_slot(period_slot)
            if not period:
                logger.warning(f"No nonwear period found in slot {period_slot}")
                return False

        # Check if period is complete (has both markers)
        if not period.is_complete:
            logger.warning("Cannot move marker for incomplete nonwear period")
            return False

        # Type narrowing: is_complete guarantees these are not None
        start_ts = period.start_timestamp
        end_ts = period.end_timestamp
        if start_ts is None or end_ts is None:
            return False

        # Validate the new position
        if marker_type == MarkerEndpoint.START:
            # Ensure start would be before end
            if target_timestamp >= end_ts:
                logger.warning(f"Cannot move start to {target_timestamp} - would be after end at {end_ts}")
                return False
            # Update start timestamp
            period.start_timestamp = target_timestamp
        elif marker_type == MarkerEndpoint.END:
            # Ensure end would be after start
            if target_timestamp <= start_ts:
                logger.warning(f"Cannot move end to {target_timestamp} - would be before start at {start_ts}")
                return False
            # Update end timestamp
            period.end_timestamp = target_timestamp
        else:
            logger.warning(f"Invalid nonwear marker type: {marker_type}")
            return False

        # Redraw nonwear markers
        self.marker_renderer.redraw_nonwear_markers()

        # Mark as unsaved via Redux store
        self.mark_nonwear_markers_dirty()

        logger.info(f"Successfully moved nonwear {marker_type} marker to timestamp {target_timestamp}")
        return True

    def add_sleep_marker(self, timestamp: float, force_nap: bool = False) -> None:
        """Add sleep marker using new extended marker system."""
        try:
            if self.current_marker_being_placed is None:
                # Start new sleep period
                if not self.daily_sleep_markers.has_space_for_new_period():
                    self.marker_limit_exceeded.emit(f"Maximum {MarkerLimits.MAX_SLEEP_PERIODS_PER_DAY} sleep periods per day allowed")
                    return

                # Determine what type this marker will be based on existing complete periods
                from sleep_scoring_app.core.dataclasses import MarkerType

                main_sleep = self.daily_sleep_markers.get_main_sleep()

                # force_nap=True on no-sleep days: always create NAP, never main sleep
                if force_nap:
                    marker_type = MarkerType.NAP
                elif main_sleep is None:
                    marker_type = MarkerType.MAIN_SLEEP
                else:
                    marker_type = MarkerType.NAP

                # Create new incomplete period (onset only) with the correct type
                self.current_marker_being_placed = SleepPeriod(onset_timestamp=timestamp, offset_timestamp=None, marker_type=marker_type)

            else:
                # Complete the current period (add offset)
                onset_ts = self.current_marker_being_placed.onset_timestamp
                if onset_ts is None or timestamp <= onset_ts:
                    # Invalid: offset before onset, reset
                    self.current_marker_being_placed = None
                    return

                self.current_marker_being_placed.offset_timestamp = timestamp

                # Find next available slot and add to daily markers
                slot = self._get_next_available_slot()
                if slot is not None:
                    self.current_marker_being_placed.marker_index = slot
                    self._assign_period_to_slot(self.current_marker_being_placed, slot)

                    # Set this as the currently selected marker set
                    self.selected_marker_set_index = slot

                    # Update classifications and emit signal
                    self.daily_sleep_markers.update_classifications()

                    # Check for duration ties
                    if self.daily_sleep_markers.check_duration_tie():
                        # Remove the just-added period
                        self._remove_period_from_slot(slot)
                        self.marker_limit_exceeded.emit("Cannot determine main sleep: multiple periods with identical duration")
                    else:
                        self.mark_sleep_markers_dirty()

                self.current_marker_being_placed = None

            self.redraw_markers()

        except Exception as e:
            logger.exception("Error adding sleep marker: %s", e)
            self.current_marker_being_placed = None
            self.error_occurred.emit(f"Failed to add sleep marker: {e}")

    def _get_next_available_slot(self) -> int | None:
        """Get the next available period slot (1, 2, 3, or 4)."""
        if self.daily_sleep_markers.period_1 is None:
            return 1
        if self.daily_sleep_markers.period_2 is None:
            return 2
        if self.daily_sleep_markers.period_3 is None:
            return 3
        if self.daily_sleep_markers.period_4 is None:
            return 4
        return None

    def _assign_period_to_slot(self, period: SleepPeriod, slot: int) -> None:
        """Assign a sleep period to a specific slot."""
        if slot == 1:
            self.daily_sleep_markers.period_1 = period
        elif slot == 2:
            self.daily_sleep_markers.period_2 = period
        elif slot == 3:
            self.daily_sleep_markers.period_3 = period
        elif slot == 4:
            self.daily_sleep_markers.period_4 = period

    def _remove_period_from_slot(self, slot: int) -> None:
        """Remove a sleep period from a specific slot."""
        if slot == 1:
            self.daily_sleep_markers.period_1 = None
        elif slot == 2:
            self.daily_sleep_markers.period_2 = None
        elif slot == 3:
            self.daily_sleep_markers.period_3 = None
        elif slot == 4:
            self.daily_sleep_markers.period_4 = None

    # ========== Marker Methods (delegated to PlotMarkerRenderer) ==========

    def _get_nap_number(self, period: SleepPeriod) -> int:
        """Get the sequential nap number for a given period."""
        return self.marker_renderer.get_nap_number(period)

    def _prepare_sleep_period_markers(self, period: SleepPeriod, is_main_sleep: bool) -> list[pg.InfiniteLine]:
        """Prepare onset and offset markers for a sleep period."""
        return self.marker_renderer.prepare_sleep_period_markers(period, is_main_sleep)

    def _draw_sleep_period(self, period: SleepPeriod, is_main_sleep: bool) -> None:
        """Draw onset and offset markers for a sleep period."""
        self.marker_renderer.draw_sleep_period(period, is_main_sleep)

    def _draw_incomplete_marker(self, period: SleepPeriod) -> None:
        """Draw a temporary marker for an incomplete sleep period."""
        self.marker_renderer.draw_incomplete_marker(period)

    def _create_marker_line(
        self, timestamp: float, color: str, label: str, period: SleepPeriod | None, marker_type: str, is_selected: bool = False
    ) -> pg.InfiniteLine:
        """Create a draggable marker line with proper styling and behavior."""
        return self.marker_renderer.create_marker_line(timestamp, color, label, period, marker_type, is_selected)

    def _create_marker_line_no_add(
        self, timestamp: float, color: str, label: str, period: SleepPeriod | None, marker_type: str, is_selected: bool = False
    ) -> pg.InfiniteLine:
        """Create a draggable marker line without adding to plot."""
        return self.marker_renderer.create_marker_line_no_add(timestamp, color, label, period, marker_type, is_selected)

    def load_daily_sleep_markers(self, daily_markers: DailySleepMarkers) -> None:
        """Load existing daily sleep markers into the plot widget."""
        self.marker_renderer.load_daily_sleep_markers(daily_markers)

    def load_daily_nonwear_markers(self, daily_markers: DailyNonwearMarkers) -> None:
        """Load existing daily nonwear markers into the plot widget."""
        self.marker_renderer.load_daily_nonwear_markers(daily_markers)

    def get_daily_sleep_markers(self) -> DailySleepMarkers:
        """Get the current daily sleep markers."""
        return self.marker_renderer.get_daily_sleep_markers()

    def remove_sleep_period(self, period_index: int) -> bool:
        """Remove a sleep period by its index (1, 2, 3, or 4)."""
        return self.marker_renderer.remove_sleep_period(period_index)

    def display_adjacent_day_markers(self, adjacent_day_markers_data: list) -> None:
        """Display adjacent day markers from adjacent days."""
        self.marker_renderer.display_adjacent_day_markers(adjacent_day_markers_data)

    def clear_adjacent_day_markers(self) -> None:
        """Clear all adjacent day markers from the plot."""
        self.marker_renderer.clear_adjacent_day_markers()

    def redraw_markers(self) -> None:
        """Redraw all sleep markers with proper colors for main sleep vs naps."""
        self.marker_renderer.redraw_markers()

    def _update_all_marker_labels(self) -> None:
        """Update labels and colors for all marker lines based on current classifications."""
        self.marker_renderer.update_marker_visual_state()

    def _update_marker_labels_text_only(self) -> None:
        """Update only the text of marker labels (safe for real-time updates during drag)."""
        self.marker_renderer.update_marker_labels_text_only()

    def get_marker_data(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Extract surrounding data for main sleep markers."""
        main_sleep = self.daily_sleep_markers.get_main_sleep()
        if not main_sleep or not main_sleep.is_complete:
            return [], []

        if self.timestamps is None or self.axis_y_data is None:
            return [], []

        first_marker_ts = main_sleep.onset_timestamp
        last_marker_ts = main_sleep.offset_timestamp
        if first_marker_ts is None or last_marker_ts is None:
            return [], []

        # Find indices for markers using optimized lookup
        first_marker_idx = self._find_closest_data_index(first_marker_ts)
        last_marker_idx = self._find_closest_data_index(last_marker_ts)

        onset_data = []
        offset_data = []

        # Get Sadeh, Choi, and Nonwear Sensor results if available
        sadeh_results = getattr(self, "sadeh_results", [])
        choi_results = self.get_choi_results_per_minute()
        nonwear_sensor_results = self.get_nonwear_sensor_results_per_minute()

        if first_marker_idx is not None:
            # Get 21 elements around first marker (10 before + marker + 10 after)
            start_idx = max(0, first_marker_idx - 10)
            end_idx = min(len(self.timestamps), first_marker_idx + 11)  # +11 to include 10 after

            for i in range(start_idx, end_idx):
                # Comprehensive bounds checking for all arrays
                if i < len(self.timestamps) and i < len(self.axis_y_data) and 0 <= i < len(self.timestamps):
                    is_marker = i == first_marker_idx
                    sadeh_value = sadeh_results[i] if i < len(sadeh_results) else 0
                    choi_value = choi_results[i] if i < len(choi_results) else 0
                    nwt_value = nonwear_sensor_results[i] if i < len(nonwear_sensor_results) else 0

                    onset_data.append(
                        {
                            "time": self.timestamps[i].strftime("%H:%M"),
                            "activity": int(self.axis_y_data[i]),
                            "sadeh": sadeh_value,
                            "choi": choi_value,
                            "nwt_sensor": nwt_value,
                            "is_marker": is_marker,
                        },
                    )

        if last_marker_idx is not None:
            # Get 21 elements around last marker (10 before + marker + 10 after)
            start_idx = max(0, last_marker_idx - 10)
            end_idx = min(len(self.timestamps), last_marker_idx + 11)  # +11 to include 10 after

            for i in range(start_idx, end_idx):
                if i < len(self.timestamps) and i < len(self.axis_y_data):
                    is_marker = i == last_marker_idx
                    sadeh_value = sadeh_results[i] if i < len(sadeh_results) else 0
                    choi_value = choi_results[i] if i < len(choi_results) else 0
                    nwt_value = nonwear_sensor_results[i] if i < len(nonwear_sensor_results) else 0
                    offset_data.append(
                        {
                            "time": self.timestamps[i].strftime("%H:%M"),
                            "activity": int(self.axis_y_data[i]),
                            "sadeh": sadeh_value,
                            "choi": choi_value,
                            "nwt_sensor": nwt_value,
                            "is_marker": is_marker,
                        },
                    )

        return onset_data, offset_data

    def _find_closest_data_index(self, target_timestamp: float) -> int | None:
        """
        Find the data index closest to the target timestamp using binary search.

        Uses self.x_data directly - no separate cache needed since x_data is already
        a numpy array of unix timestamps created when data is loaded.

        When the target is outside the data range (e.g. dragging a marker past the
        last data point in a 24h noon-to-noon view), clamps to the nearest boundary
        instead of returning None. This ensures marker drags at view edges still
        update period timestamps and trigger table/Redux updates.
        """
        if self.x_data is None or len(self.x_data) == 0:
            logger.warning("MARKER DRAG: No x_data available")
            return None

        # Clamp to data boundaries when target is outside the data range.
        # The view range (noon-to-noon) can extend beyond actual data, so
        # dragging a marker past the last data point should snap to the boundary.
        if target_timestamp <= self.x_data[0]:
            return 0
        if target_timestamp >= self.x_data[-1]:
            return int(len(self.x_data) - 1)

        # Use binary search on x_data (already a numpy array of unix timestamps)
        idx = np.searchsorted(self.x_data, target_timestamp)

        # Clip to bounds
        idx = max(0, min(idx, len(self.x_data) - 1))

        # Check if the neighbor is actually closer
        if idx > 0:
            diff_curr = abs(self.x_data[idx] - target_timestamp)
            diff_prev = abs(self.x_data[idx - 1] - target_timestamp)
            if diff_prev < diff_curr:
                idx -= 1

        return int(idx)

    def get_choi_results_per_minute(self) -> list[int]:
        """Get Choi nonwear periods as per-minute results (1=nonwear, 0=wear)."""
        # Use NonwearData system if available
        if self.nonwear_data is not None:
            return list(self.nonwear_data.choi_mask)

        # Fallback: compute on demand if NonwearData system not active
        if self.axis_y_data is None:
            return []

        try:
            choi_algorithm = self.create_nonwear_algorithm(NonwearAlgorithm.CHOI_2011)
            return choi_algorithm.detect_mask(self.axis_y_data)
        except Exception as e:
            logger.exception("Failed to compute Choi results: %s", e)
            return []

    def get_nonwear_sensor_results_per_minute(self) -> list[int]:
        """Get nonwear sensor periods as per-minute results (1=nonwear, 0=wear)."""
        # Use NonwearData system if available
        if self.nonwear_data is not None:
            return list(self.nonwear_data.sensor_mask)

        # Fallback processing if NonwearData system hasn't been used yet
        # This should rarely be used now that we have the unified NonwearData system
        logger.warning("Using fallback sensor data processing - NonwearData system not active")
        if self.activity_data is None:
            return []
        return [0] * len(self.activity_data)  # Return all wear periods as fallback

    @property
    def axis_y_data(self) -> list[float]:
        """Property that loads axis_y data on demand using unified loader."""
        # NEVER use display data for Sadeh - always load actual axis_y data
        # This ensures Sadeh algorithm always uses correct axis_y data regardless of display preference
        return self._get_axis_y_data_for_sadeh()

    def _get_axis_y_data_for_sadeh(self) -> list[float]:
        """Get axis_y data specifically for Sadeh algorithm using unified loader."""
        # PERFORMANCE: Return cached data if BOTH data and timestamps are available
        # We need both because arrows use timestamps that must align with sadeh_results
        axis_y_timestamps = getattr(self, "main_48h_axis_y_timestamps", None)
        if (
            self.main_48h_axis_y_data is not None
            and len(self.main_48h_axis_y_data) > 0
            and axis_y_timestamps is not None
            and len(axis_y_timestamps) == len(self.main_48h_axis_y_data)
        ):
            return self.main_48h_axis_y_data

        # Load from injected callback
        if self._get_axis_y_data_for_sadeh_cb is not None:
            return self._get_axis_y_data_for_sadeh_cb() or []
        return []

    def _extract_view_subset_from_main_results(self) -> None:
        """Extract the current view subset from main 48hr algorithm results."""
        self.algorithm_manager._extract_view_subset_from_main_results()

    def plot_algorithms(self) -> None:
        """Run and plot algorithms with performance optimization and caching."""
        self.algorithm_manager.plot_algorithms()

    def plot_choi_results(self, nonwear_periods) -> None:
        """Plot Choi nonwear periods as purple background regions (optimized)."""
        self.algorithm_manager.plot_choi_results(nonwear_periods)

    def extract_participant_info(self) -> dict[str, str]:
        """Extract participant information using centralized extractor."""
        from sleep_scoring_app.utils.participant_extractor import extract_participant_info

        try:
            # Get selected file from injected callback or self
            selected_file = None
            if self._get_selected_file is not None:
                selected_file = self._get_selected_file()
            elif getattr(self, "selected_file", None):
                selected_file = self.selected_file

            if not selected_file:
                # Fallback to timestamp-based naming if no file info
                return {
                    "participant_id": "Unknown",
                    "timepoint": "Unknown",
                }

            # Use centralized extractor
            participant_info = extract_participant_info(selected_file)

            return {
                "participant_id": participant_info.numerical_id,
                "timepoint": participant_info.timepoint_str,
            }

        except Exception as e:
            # Ultimate fallback
            logger.warning("Failed to extract participant info from filename: %s", e)
            return {
                "participant_id": "Unknown",
                "timepoint": "Unknown",
            }

    def apply_sleep_scoring_rules(self, main_sleep_period: SleepPeriod) -> None:
        """Apply 3 minute rule for onset and 5 minute rule for offset to selected marker set."""
        self.algorithm_manager.apply_sleep_scoring_rules(main_sleep_period)

    def create_sleep_onset_marker(self, timestamp) -> None:
        """Create sleep onset marker with arrow and axis label."""
        self.algorithm_manager.create_sleep_onset_marker(timestamp)

    def create_sleep_offset_marker(self, timestamp) -> None:
        """Create sleep offset marker with arrow and axis label."""
        self.algorithm_manager.create_sleep_offset_marker(timestamp)

    def clear_sleep_onset_offset_markers(self) -> None:
        """Clear sleep onset/offset markers from 3/5 rule."""
        self.algorithm_manager.clear_sleep_onset_offset_markers()

    def clear_sleep_markers(self) -> None:
        """Remove all sleep markers."""
        self.marker_renderer.clear_sleep_markers()
        self.clear_sleep_onset_offset_markers()

    def clear_nonwear_markers(self) -> None:
        """Remove all manual nonwear markers."""
        self.marker_renderer.clear_nonwear_markers()
        self._daily_nonwear_markers = DailyNonwearMarkers()

    def clear_plot(self) -> None:
        """Clear all plot data and markers."""
        # Clear the main plot
        plot_item = self.plotItem
        if plot_item:
            plot_item.clear()

        # Clear sleep markers (includes sleep onset/offset rule arrows)
        self.clear_sleep_markers()

        # Clear manual nonwear markers
        self.clear_nonwear_markers()

        # Clear adjacent day markers
        self.clear_adjacent_day_markers()

        # Clear nonwear visualizations (overlays)
        self.clear_nonwear_visualizations()

        # Reset plot state
        self.data_start_time = None
        self.data_end_time = None
        self.data_min_y = 0
        self.data_max_y = 100

    def get_sleep_duration(self) -> float | None:
        """Calculate duration of the currently selected marker period."""
        selected_period = self.get_selected_marker_period()
        if selected_period and selected_period.is_complete:
            return selected_period.duration_hours
        return None

    def get_selected_marker_period(self) -> SleepPeriod | None:
        """Get the currently selected marker period."""
        return self.marker_renderer.get_selected_marker_period()

    def clear_selected_marker_set(self) -> None:
        """Clear the currently selected marker set."""
        self.marker_renderer.clear_selected_marker_set()

    def cancel_incomplete_marker(self) -> None:
        """Cancel the current incomplete marker placement and remove its visual indicator."""
        self.marker_renderer.cancel_incomplete_marker()

    def adjust_selected_marker(self, marker_type: str, seconds_delta: int) -> None:
        """Adjust selected marker set by specified number of seconds."""
        self.marker_renderer.adjust_selected_marker(marker_type, seconds_delta)

    def _update_sleep_scoring_rules(self) -> None:
        """Update sleep scoring rules for the currently selected marker period."""
        selected_period = self.get_selected_marker_period()
        if selected_period and selected_period.is_complete:
            self.apply_sleep_scoring_rules(selected_period)

    def _select_marker_set_by_period(self, period: SleepPeriod) -> None:
        """Select the marker set that contains the given period."""
        self.marker_renderer.select_marker_set_by_period(period)

    def _auto_select_marker_set(self) -> None:
        """Automatically select an appropriate marker set when the current one is cleared."""
        self.marker_renderer.auto_select_marker_set()

    def _update_marker_visual_state(self) -> None:
        """Update the visual state of all markers to reflect current selection."""
        self.marker_renderer.update_marker_visual_state()

    # ========== Manual Nonwear Marker Methods ==========

    def add_nonwear_marker(self, timestamp: float) -> None:
        """Add a manual nonwear marker at the given timestamp."""
        try:
            if self._current_nonwear_marker_being_placed is None:
                # Start new nonwear period
                if not self._daily_nonwear_markers.has_space_for_new_period():
                    self.marker_limit_exceeded.emit(f"Maximum {MarkerLimits.MAX_NONWEAR_PERIODS_PER_DAY} nonwear periods per day allowed")
                    return

                # Get next available slot
                next_slot = self._daily_nonwear_markers.get_next_available_slot()
                if next_slot is None:
                    return

                # Create new incomplete period (start only)
                self._current_nonwear_marker_being_placed = ManualNonwearPeriod(
                    start_timestamp=timestamp,
                    end_timestamp=None,
                    marker_index=next_slot,
                )

            else:
                # Complete the current period (add end)
                start_ts = self._current_nonwear_marker_being_placed.start_timestamp
                if start_ts is None or timestamp <= start_ts:
                    # Invalid: end before start or no start, reset
                    self._current_nonwear_marker_being_placed = None
                    return

                self._current_nonwear_marker_being_placed.end_timestamp = timestamp
                end_ts = self._current_nonwear_marker_being_placed.end_timestamp

                # Check for overlap with existing periods
                slot = self._current_nonwear_marker_being_placed.marker_index
                if (
                    start_ts is not None
                    and end_ts is not None
                    and self._daily_nonwear_markers.check_overlap(
                        start_ts,
                        end_ts,
                        exclude_slot=slot,
                    )
                ):
                    self.marker_limit_exceeded.emit("Nonwear periods cannot overlap")
                    self._current_nonwear_marker_being_placed = None
                    return

                # Add to daily markers
                self._daily_nonwear_markers.set_period_by_slot(slot, self._current_nonwear_marker_being_placed)

                # Set this as the currently selected nonwear marker
                # Use property setter to emit nonwear_selection_changed signal
                self.selected_nonwear_marker_index = slot

                # Emit change signal for markers data
                self.mark_nonwear_markers_dirty()

                self._current_nonwear_marker_being_placed = None

            self.marker_renderer.redraw_nonwear_markers()

        except Exception as e:
            logger.exception("Error adding nonwear marker: %s", e)
            self._current_nonwear_marker_being_placed = None
            self.error_occurred.emit(f"Failed to add nonwear marker: {e}")

    def get_selected_nonwear_period(self) -> ManualNonwearPeriod | None:
        """Get the currently selected nonwear period."""
        return self.marker_renderer.get_selected_nonwear_period()

    def clear_selected_nonwear_marker(self) -> None:
        """Clear the currently selected nonwear marker."""
        self.marker_renderer.clear_selected_nonwear_marker()
        self.mark_nonwear_markers_dirty()

    def cancel_incomplete_nonwear_marker(self) -> None:
        """Cancel the current incomplete nonwear marker placement."""
        self.marker_renderer.cancel_incomplete_nonwear_marker()

    def adjust_selected_nonwear_marker(self, marker_type: str, seconds_delta: int) -> None:
        """Adjust selected nonwear marker by specified number of seconds."""
        self.marker_renderer.adjust_selected_nonwear_marker(marker_type, seconds_delta)
        self.mark_nonwear_markers_dirty()

    def get_daily_nonwear_markers(self) -> DailyNonwearMarkers:
        """Get the current daily nonwear markers."""
        return self.marker_renderer.get_daily_nonwear_markers()

    def set_nonwear_markers_visibility(self, visible: bool) -> None:
        """Set visibility of nonwear markers."""
        self.marker_renderer.set_nonwear_markers_visibility(visible)

    def set_active_marker_category(self, category: MarkerCategory) -> None:
        """
        Set the active marker category (SLEEP or NONWEAR).

        When switching modes, this also:
        - Clears the marker click-in-progress flag to prevent blocking
        - Cancels any incomplete markers from the previous mode
        """
        # Safety check for early calls during initialization
        previous_category = getattr(self, "_active_marker_category", None)
        self._active_marker_category = category

        # Always reset the click-in-progress flag when switching modes
        # This prevents clicks on markers from the other category from blocking new placements
        self._marker_click_in_progress = False

        # Cancel any incomplete markers from the previous mode
        if previous_category != category:
            if previous_category == MarkerCategory.SLEEP and self.current_marker_being_placed is not None:
                logger.debug("Cancelling incomplete sleep marker when switching to nonwear mode")
                self.cancel_incomplete_marker()
            elif previous_category == MarkerCategory.NONWEAR and self._current_nonwear_marker_being_placed is not None:
                logger.debug("Cancelling incomplete nonwear marker when switching to sleep mode")
                self.cancel_incomplete_nonwear_marker()

        logger.debug(f"Active marker category set to: {category}")

    def get_active_marker_category(self) -> MarkerCategory:
        """Get the currently active marker category."""
        return self._active_marker_category

    def add_background_region(
        self,
        start_time,
        end_time,
        color=(220, 53, 69, 40),
        border_color=(220, 53, 69, 120),
    ) -> pg.LinearRegionItem:
        """Add a background region (e.g., for nonwear periods)."""
        region = pg.LinearRegionItem(
            [start_time, end_time],
            brush=pg.mkBrush(*color),
            pen=pg.mkPen(*border_color[:3], width=1),
            movable=False,
        )
        region.setZValue(-10)  # Behind the activity plot
        plot_item = self.plotItem
        if plot_item:
            plot_item.addItem(region)
        return region

    # ========== Overlay Methods (delegated to PlotOverlayRenderer) ==========

    def set_nonwear_data(self, nonwear_data) -> None:
        """Set nonwear data using immutable NonwearData structure."""
        self.overlay_renderer.set_nonwear_data(nonwear_data)

    def clear_nonwear_visualizations(self) -> None:
        """Clear all nonwear period visualizations."""
        self.overlay_renderer.clear_nonwear_visualizations()

    def plot_nonwear_periods(self) -> None:
        """Plot nonwear periods using the same per-minute data as table/mouseover."""
        self.overlay_renderer.plot_nonwear_periods()

    def update_choi_overlay_only(self, new_activity_data: list[float]) -> None:
        """Recalculate Choi algorithm with new data while preserving Sadeh algorithm state."""
        self.overlay_renderer.update_choi_overlay_only(new_activity_data)

    def update_choi_overlay_async(self, new_activity_data: list[float]) -> None:
        """Asynchronously recalculate Choi algorithm with new data."""
        self.overlay_renderer.update_choi_overlay_async(new_activity_data)

    def _update_choi_cache_key(self, new_activity_data: list[float]) -> None:
        """Update cache key for Choi results while preserving Sadeh cache."""
        self.overlay_renderer._update_choi_cache_key(new_activity_data)

    def restore_choi_from_cache(self, activity_data: list[float]) -> bool:
        """Attempt to restore Choi results from cache for quick switching."""
        return self.overlay_renderer.restore_choi_from_cache(activity_data)

    def clear_choi_cache(self) -> None:
        """Clear the Choi algorithm results cache."""
        self.overlay_renderer.clear_choi_cache()

    def get_choi_cache_info(self) -> dict[str, int]:
        """Get information about the current Choi cache state."""
        return self.overlay_renderer.get_choi_cache_info()

    def validate_choi_overlay_state(self) -> bool:
        """Validate the current Choi overlay state for consistency."""
        return self.overlay_renderer.validate_choi_overlay_state()

    def _convert_choi_results_to_periods(self) -> list[NonwearPeriod]:
        """Convert dynamically generated Choi results to NonwearPeriod format."""
        return self.overlay_renderer.convert_choi_results_to_periods()

    def add_visual_marker(
        self, timestamp: float, text: str, color: str = "#0066CC", position_factor: float = 0.90
    ) -> tuple[pg.ArrowItem, pg.TextItem]:
        """Add a visual marker with arrow and text at specified timestamp."""
        # Create arrow pointing down to the timeline
        arrow = pg.ArrowItem(
            pos=(timestamp, self.data_max_y * 0.88),
            angle=-90,  # Point downward
            headLen=15,
            headWidth=12,
            tailLen=25,
            tailWidth=3,
            pen=pg.mkPen(color=color, width=2),
            brush=pg.mkBrush(color=color),
        )
        arrow.setZValue(10)  # Above everything else
        if (plot_item := self.plotItem) is not None:
            plot_item.addItem(arrow)

        # Create text label above the arrow
        time_str = datetime.fromtimestamp(timestamp).strftime("%H:%M")
        text_item = pg.TextItem(
            text=f"{text} at {time_str}",
            color=color,
            anchor=(0.5, 1.0),  # Center horizontally, bottom of text at point
        )
        text_item.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        text_item.setPos(timestamp, self.data_max_y * position_factor)
        text_item.setZValue(10)
        if (plot_item := self.plotItem) is not None:
            plot_item.addItem(text_item)

        return arrow, text_item

    def on_plot_clicked(self, event: Any) -> None:
        """Handle mouse clicks - emit signals for connector to decide action based on Redux state."""
        # Handle right-click cancellation - emit signal, connector decides which marker to cancel
        if event.button() == Qt.MouseButton.RightButton:
            logger.debug("Right-click detected - emitting plot_right_clicked signal")
            self.plot_right_clicked.emit()
            return

        # Only process left mouse button clicks for placement
        if event.button() != Qt.MouseButton.LeftButton:
            return

        # Ensure this widget has keyboard focus for keyboard shortcuts
        self.setFocus()

        # Don't create new markers if we just clicked on an existing marker
        if self._marker_click_in_progress:
            logger.debug("Skipping plot click - marker was clicked")
            return

        # Get mouse position in data coordinates
        mouse_pos = event.scenePos()
        plot_item = self.plotItem
        if plot_item is None:
            return
        view_box = plot_item.getViewBox()
        if view_box is None:
            return
        if plot_item.sceneBoundingRect().contains(mouse_pos):
            # Convert to data coordinates
            data_pos = view_box.mapSceneToView(mouse_pos)
            clicked_time = data_pos.x()

            # Check if click is within view boundaries (check for None first)
            if self.data_start_time is not None and self.data_end_time is not None and self.data_start_time <= clicked_time <= self.data_end_time:
                # Snap click to nearest actual data point so markers can't be
                # placed in empty edge regions of the view
                snap_idx = self._find_closest_data_index(clicked_time)
                if snap_idx is not None and self.x_data is not None:
                    snapped_time = float(self.x_data[snap_idx])
                    # Emit signal with snapped timestamp - connector decides sleep/nonwear based on Redux state
                    logger.debug(f"Plot left-clicked at timestamp {clicked_time}, snapped to {snapped_time} - emitting signal")
                    self.plot_left_clicked.emit(snapped_time)

        # Update marker visual state when clicking away from markers
        # This ensures selected markers stay emboldened/brightened even when clicked away
        self._update_marker_visual_state()

    def _on_mouse_move_throttled(self, pos) -> None:
        """Throttled mouse move handler to improve performance."""
        self._last_mouse_pos = pos

        # Throttle mouse move events to avoid excessive processing
        timer = self._mouse_move_timer
        if timer is not None and not timer.isActive():
            timer.start(50)  # Process at most every 50ms

    def _process_mouse_move(self) -> None:
        """Process the last mouse move position."""
        if self._last_mouse_pos is not None:
            self.on_mouse_move(self._last_mouse_pos)

    def on_mouse_move(self, pos) -> None:
        """Handle mouse movement for tooltips."""
        if self.axis_y_data is None or self.x_data is None:
            return

        # Check if mouse is over the plot area
        plot_item = self.plotItem
        if plot_item is None:
            return
        view_box = plot_item.getViewBox()
        if view_box is None:
            return
        if plot_item.sceneBoundingRect().contains(pos):
            # Convert to data coordinates
            data_pos = view_box.mapSceneToView(pos)
            hover_time = data_pos.x()

            # Check if hover is within data boundaries (check for None first)
            if self.data_start_time is not None and self.data_end_time is not None and self.data_start_time <= hover_time <= self.data_end_time:
                # Find closest data point
                closest_idx = self._find_closest_data_index(hover_time)
                if closest_idx is not None and closest_idx < len(self.axis_y_data) and self.timestamps is not None:
                    axis_y_value = self.axis_y_data[closest_idx]
                    timestamp = self.timestamps[closest_idx]

                    # Format tooltip text
                    time_str = timestamp.strftime("%H:%M")
                    tooltip_text = f"Time: {time_str}\nActivity: {axis_y_value}"

                    # Add sleep scoring info if available
                    if self.sadeh_results and closest_idx < len(self.sadeh_results):
                        sadeh_value = self.sadeh_results[closest_idx]
                        sadeh_state = "Sleep" if sadeh_value == 1 else "Wake"
                        tooltip_text += f"\nSadeh: {sadeh_state}"

                    # Add Choi algorithm info if available
                    choi_results = self.get_choi_results_per_minute()
                    if choi_results and closest_idx < len(choi_results):
                        choi_value = choi_results[closest_idx]
                        choi_state = "Nonwear" if choi_value == 1 else "Wear"
                        tooltip_text += f"\nChoi: {choi_state}"

                    # Add nonwear sensor info if available
                    nonwear_sensor_results = self.get_nonwear_sensor_results_per_minute()
                    if nonwear_sensor_results and closest_idx < len(nonwear_sensor_results):
                        nwt_value = nonwear_sensor_results[closest_idx]
                        nwt_state = "Nonwear" if nwt_value == 1 else "Wear"
                        tooltip_text += f"\nNWT Sensor: {nwt_state}"

                    # Set tooltip
                    self.setToolTip(tooltip_text)
                else:
                    self.setToolTip("")
            else:
                self.setToolTip("")
        else:
            self.setToolTip("")

    def capture_complete_state(self) -> dict[str, Any]:
        """Capture complete UI state for seamless data source switching."""
        return self.state_serializer.capture_complete_state()

    def restore_complete_state(self, state_dict: dict[str, Any]) -> bool:
        """Restore complete UI state for seamless data source switching."""
        return self.state_serializer.restore_complete_state(state_dict)

    def _serialize_sleep_period(self, period: SleepPeriod | None) -> dict[str, Any] | None:
        """Serialize a SleepPeriod to a dictionary for state storage."""
        return self.state_serializer._serialize_sleep_period(period)

    def _deserialize_sleep_period(self, data: dict[str, Any] | None) -> SleepPeriod | None:
        """Deserialize a dictionary back to a SleepPeriod."""
        return self.state_serializer._deserialize_sleep_period(data)

    def _update_file_info_label(self) -> None:
        """Update the file info label with the currently loaded file information."""
        # Check if we have an external label widget to use instead of plot TextItem
        external_label = getattr(self, "external_filename_label", None)

        if external_label:
            # Use external QLabel widget
            if self.current_filename:
                # Extract participant info directly from the filename
                from sleep_scoring_app.utils.participant_extractor import extract_participant_info

                info = extract_participant_info(self.current_filename)

                # Create display text showing the actual loaded data
                participant_id = info.numerical_id
                timepoint = info.timepoint_str
                group = info.group_str

                label_text = f"Loaded: {participant_id} {timepoint} {group} ({self.current_filename})"
                external_label.setText(label_text)
                external_label.setVisible(True)
            else:
                external_label.setText("")
                external_label.setVisible(False)

            # Clean up any existing plot TextItem if we're switching to external label
            if self.file_info_label and (plot_item := self.plotItem) is not None:
                plot_item.removeItem(self.file_info_label)
                self.file_info_label = None
        else:
            # Fallback to original TextItem behavior for backward compatibility
            # Remove existing label if it exists
            if self.file_info_label and (plot_item := self.plotItem) is not None:
                plot_item.removeItem(self.file_info_label)
                self.file_info_label = None

            # Create new label if we have filename
            if self.current_filename:
                # Extract participant info directly from the filename that was loaded from database/CSV
                # This is independent of the table selection, ensuring accuracy
                from sleep_scoring_app.utils.participant_extractor import extract_participant_info

                info = extract_participant_info(self.current_filename)

                # Create display text showing the actual loaded data
                participant_id = info.numerical_id
                timepoint = info.timepoint_str
                group = info.group_str

                label_text = f"Loaded: {participant_id} {timepoint} {group} ({self.current_filename})"

                # Create text item
                import pyqtgraph as pg
                from PyQt6.QtGui import QFont

                self.file_info_label = pg.TextItem(
                    text=label_text,
                    color=(0, 0, 0),  # Black text for maximum visibility
                    anchor=(0, 0),  # Bottom-left anchor to position lower
                )

                # Create bold font for better visibility
                self.file_info_label.setFont(QFont("Arial", 11, QFont.Weight.Bold))

                # Position in top-left corner of plot area
                view_range = self.vb.viewRange()
                # Validate viewRange before accessing
                if view_range and len(view_range) >= 2 and view_range[0] and view_range[1]:
                    x_min = view_range[0][0]
                    y_max = view_range[1][1]

                    # Offset slightly from the edges
                    x_offset = (view_range[0][1] - view_range[0][0]) * 0.02  # 2% from left edge
                    y_offset = (view_range[1][1] - view_range[1][0]) * 0.05  # 5% from top edge

                    self.file_info_label.setPos(x_min + x_offset, y_max - y_offset)
                else:
                    # Fallback position if viewRange is invalid
                    self.file_info_label.setPos(0, 0)
                self.file_info_label.setZValue(15)  # Above all other elements

                # Add to plot
                if (plot_item := self.plotItem) is not None:
                    plot_item.addItem(self.file_info_label)
