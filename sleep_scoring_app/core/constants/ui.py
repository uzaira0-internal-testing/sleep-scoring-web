"""
UI-related constants for Sleep Scoring Application.

Contains enums and constants for user interface elements, styling,
messages, and display formatting.
"""

from enum import StrEnum

from .io import ActivityDataPreference


class FeatureFlags:
    """Feature flags for enabling/disabling functionality."""

    ENABLE_AUTOSAVE = False  # Set to False to disable autosave functionality


class TimeConstants:
    """Time-related constants."""

    SECONDS_PER_MINUTE = 60
    SECONDS_PER_HOUR = 3600
    MINUTES_PER_HOUR = 60
    HOURS_PER_DAY = 24
    FIVE_MINUTES = 5
    TEN_MINUTES = 10
    FIFTEEN_MINUTES = 15
    THIRTY_MINUTES = 30
    SADEH_NIGHT_START_HOUR = 22
    SADEH_NIGHT_END_HOUR = 7


class TimeFormat(StrEnum):
    """Time format strings."""

    HOUR_MINUTE = "%H:%M"
    DATE_ONLY = "%Y-%m-%d"
    ISO_DATETIME = "%Y-%m-%dT%H:%M:%S"
    PLACEHOLDER = "HH:MM"
    EMPTY_TIME = "--:--"
    EMPTY_VALUE = "--"


class ViewMode(StrEnum):
    """Plot view modes."""

    HOURS_24 = "24h"
    HOURS_48 = "48h"


class ConfigDefaults:
    """Configuration default values."""

    MAX_RECENT_FILES = 10
    WINDOW_WIDTH = 1200
    WINDOW_HEIGHT = 800
    EPOCH_LENGTH = 60
    SKIP_ROWS = 10
    # Activity column preferences - Y-axis (vertical) is default for Sadeh algorithm
    DEFAULT_ACTIVITY_COLUMN = ActivityDataPreference.AXIS_Y
    DEFAULT_CHOI_ACTIVITY_COLUMN = ActivityDataPreference.VECTOR_MAGNITUDE
    DEFAULT_PLOT_ACTIVITY_COLUMN = ActivityDataPreference.AXIS_Y
    # View mode preferences
    DEFAULT_VIEW_MODE = ViewMode.HOURS_48
    # UI element visibility
    SEPARATOR_VISIBLE_DEFAULT = True


class MemoryConstants:
    """Memory management constants."""

    # BoundedCache limits
    CACHE_MAX_SIZE = 500
    CACHE_MAX_MEMORY_MB = 500

    # Memory monitoring thresholds
    MEMORY_WARNING_THRESHOLD_MB = 1000
    MEMORY_CRITICAL_THRESHOLD_MB = 2000

    # Cache cleanup
    DEFAULT_MAX_AGE_HOURS = 24
    MEMORY_UTILIZATION_THRESHOLD = 0.7


class ConfigKey(StrEnum):
    """Configuration file keys."""

    DATA_FOLDER = "data_folder"
    EPOCH_LENGTH = "epoch_length"
    ACTIVITY_EPOCH_DATA_SKIP_ROWS = "activity_epoch_data_skip_rows"
    DATE_COLUMN = "date_column"
    TIME_COLUMN = "time_column"
    DATETIME_COLUMN = "datetime_column"
    ACTIVITY_COLUMN = "activity_column"
    AXIS_X_COLUMN = "axis_x_column"
    AXIS_Z_COLUMN = "axis_z_column"
    VECTOR_MAGNITUDE_COLUMN = "vector_magnitude_column"
    WINDOW_WIDTH = "window_width"
    WINDOW_HEIGHT = "window_height"
    RECENT_FILES = "recent_files"


class ArrowColorKey(StrEnum):
    """Keys for custom arrow color dictionaries."""

    ONSET = "onset"
    OFFSET = "offset"


class ExportUIGroup(StrEnum):
    """UI group names for export column grouping."""

    NONWEAR_MARKERS = "Nonwear Markers"


class DiaryTableColumn(StrEnum):
    """Diary table column identifiers."""

    DATE = "date"
    BEDTIME = "bedtime"
    WAKE_TIME = "wake_time"
    SLEEP_ONSET = "sleep_onset"
    SLEEP_OFFSET = "sleep_offset"
    NAP_OCCURRED = "nap_occurred"
    NAP_1_START = "nap_1_start"
    NAP_1_END = "nap_1_end"
    NAP_2_START = "nap_2_start"
    NAP_2_END = "nap_2_end"
    NAP_3_START = "nap_3_start"
    NAP_3_END = "nap_3_end"
    NONWEAR_OCCURRED = "nonwear_occurred"
    NONWEAR_1_START = "nonwear_1_start"
    NONWEAR_1_END = "nonwear_1_end"
    NONWEAR_1_REASON = "nonwear_1_reason"
    NONWEAR_2_START = "nonwear_2_start"
    NONWEAR_2_END = "nonwear_2_end"
    NONWEAR_2_REASON = "nonwear_2_reason"
    NONWEAR_3_START = "nonwear_3_start"
    NONWEAR_3_END = "nonwear_3_end"
    NONWEAR_3_REASON = "nonwear_3_reason"


class EditMode(StrEnum):
    """Marker editing modes for activity plot."""

    IDLE = "idle"
    PLACING_ONSET = "placing_onset"
    PLACING_OFFSET = "placing_offset"
    DRAGGING = "dragging"


class ViewHours:
    """View mode hour constants."""

    HOURS_24 = 24
    HOURS_48 = 48


class MessageType(StrEnum):
    """Message dialog types."""

    INFORMATION = "Information"
    WARNING = "Warning"
    ERROR = "Error"
    QUESTION = "Question"


# --- Window and Dialog Text ---


class WindowTitle(StrEnum):
    """Window and dialog titles."""

    MAIN_WINDOW = "Sleep Scoring App - Activity Data Visualization"
    EXPORT_DIALOG = "Export Sleep Scoring Data"
    FOLDER_LOADED = "Folder Loaded"
    NO_FILES_FOUND = "No Files Found"
    NO_FOLDER_SELECTED = "No Folder Selected"
    NO_MARKERS = "No Markers"
    NO_FILE_SELECTED = "No File Selected"
    MARKERS_SAVED = "Markers Saved"
    EXPORT_READY = "Export Ready"
    EXPORT_ERROR = "Export Error"
    NO_DATA = "No Data"
    CLEAR_ALL_MARKERS = "Clear All Markers"
    MARK_NO_SLEEP = "Mark No Sleep"
    SELECT_STUDY_DAYS_FILE = "Select Study Days File"
    SELECT_NWT_DATA_FOLDER = "Select NWT Data Folder"
    SELECT_FOLDER = "Select Folder"
    SELECT_CSV_FILE = "Select CSV File"
    SELECT_DIARY_FOLDER = "Select Diary Data Folder"
    SELECT_DIARY_FILES = "Select Diary Files"


class ButtonText(StrEnum):
    """Button text constants."""

    SAVE_MARKERS = "Save Markers"
    MARKERS_SAVED = "Markers Saved ✓"
    NO_SLEEP_MARKED = "No Sleep Marked ✓"
    LOAD_DATA_FOLDER = "Load Data Folder"
    ANALYZE_COLUMNS = "Analyze Columns"
    EXPORT = "Export"
    CANCEL = "Cancel"
    BROWSE = "Browse..."
    CLEAR_MARKERS = "Clear Markers"
    CLEAR_ACTIVITY_DATA = "Clear Activity Data"
    CLEAR_STUDY_DAYS = "Clear Study Days"
    CLEAR_NWT_DATA = "Clear NWT Data"
    CLEAR_ACTILIFE_DATA = "Clear ActiLife Data"
    CLEAR_DIARY_DATA = "Clear Diary Data"
    MARK_NO_SLEEP = "Mark No Sleep"
    START_IMPORT = "Start Import"
    IMPORT_DIARIES = "Import Diaries"
    MAP_COLUMNS = "Map Columns"
    MAPPING_IN_PROGRESS = "Mapping..."
    MAPPING_COMPLETE = "Mapping Complete ✓"


class TabName(StrEnum):
    """Tab names."""

    DATA_SETTINGS = "Data Settings"
    STUDY_SETTINGS = "Study Settings"
    ANALYSIS = "Analysis"
    EXPORT_TAB = "Export"
    IMPORT_TAB = "Import"


class LabelText(StrEnum):
    """Label text constants."""

    DATA_FOLDER = "Data Folder:"
    EPOCH_LENGTH = "Epoch Length (seconds):"
    SKIP_ROWS = "Skip Rows:"
    DATE_COLUMN = "Date Column:"
    TIME_COLUMN = "Time Column:"
    ACTIVITY_COLUMN = "Activity Column:"


class MenuText(StrEnum):
    """Menu item text."""

    FILE_MENU = "File"
    CHANGE_DATA_FOLDER = "Change Data Folder..."
    EXIT = "Exit"


class GroupBoxTitle(StrEnum):
    """Group box titles."""

    ACTIVITY_DATA = "Activity Data"
    NONWEAR_SENSOR_DATA = "Nonwear Time (NWT) Sensor Data"
    ACTILIFE_NONWEAR_DATA = "ActiLife Nonwear Export Data"
    CHOI_ALGORITHM_DATA = "Choi Algorithm Results"
    DIARY_DATA = "Diary Data"


# --- Status and Messages ---


class StatusMessage(StrEnum):
    """Status bar messages."""

    NO_MARKERS = "Sleep Period Markers: No markers placed. Click on the activity plot to mark sleep start and end times."
    USAGE_INSTRUCTIONS = "Usage: Click to place sleep markers • Mouse wheel to zoom • Drag to pan horizontally"
    SLEEP_START_ONLY = "Sleep Start Time: {} | Click on the plot again to set the sleep end time"
    SLEEP_PERIOD_DEFINED = "Sleep Period Defined: {} to {} | Total Duration: {:.1f} hours | Use Q/E (left) A/D (right) to adjust"


class InfoMessage(StrEnum):
    """Information messages."""

    NO_FOLDER_SELECTED = "No folder selected"
    NO_FILE_SELECTED = "Select CSV file..."
    NO_CSV_FILES_FOUND = "No CSV files found"
    SELECT_FOLDER_FIRST = "Please select a data folder first."
    NO_MARKERS_TO_SAVE = "No sleep markers to save. Please place markers first."
    NO_MARKERS_FOUND = "No sleep markers or metrics found in the database."
    IMPORTED_RAW_DATA_PRESERVED = "Imported raw data will be preserved."
    NO_DIRECTORY_SELECTED = "No directory selected"
    NO_FILE_SELECTED_DEFAULT = "No file selected"
    READY_TO_IMPORT = "Ready to import"
    NOT_IMPLEMENTED = "Not implemented"


class ConfirmationMessage(StrEnum):
    """Confirmation dialog messages."""

    CLEAR_ALL_MARKERS = "Are you sure you want to clear all sleep markers and metrics from the database?"
    MARK_NO_SLEEP_CONFIRM = "Mark {} as having no sleep period?\n\nThis will delete existing SLEEP markers for this date and save a record indicating no sleep occurred.\n\nNWT (nonwear) markers will be preserved."
    ACTION_CANNOT_BE_UNDONE = "This action cannot be undone."


class SuccessMessage(StrEnum):
    """Success messages."""

    MARKERS_SAVED_TO_DATABASE = "Sleep markers saved to database successfully!"
    NO_SLEEP_MARKED_SUCCESS = "Date {} marked as having no sleep period.\n\nThis record has been saved to the database."
    IMPORT_COMPLETED = "Import completed successfully!"
    EXPORT_COMPLETED = "Export completed successfully!"


class ErrorMessage(StrEnum):
    """Error messages."""

    FAILED_TO_DELETE_MARKERS = "Failed to delete existing markers: {}"
    FAILED_TO_SAVE_MARKERS = "Error saving markers: {}"
    NO_DATA_AVAILABLE = "No data available for export."
    EXPORT_FAILED = "Export failed: {}"
    IMPORT_FAILED = "Import failed: {}"


class TooltipText(StrEnum):
    """Tooltip messages."""

    ONSET_TIME_INPUT = "Sleep onset time (HH:MM format) - Auto-updates on Enter"
    OFFSET_TIME_INPUT = "Sleep offset time (HH:MM format) - Auto-updates on Enter"
    SAVE_MARKERS = "Save current markers permanently"
    CLEAR_MARKERS = "Clear all sleep markers"
    MARK_NO_SLEEP = "Mark this date as having no sleep period"
    EXPORT_BUTTON = "Export sleep markers and metrics to CSV"
    TIME_COLUMN = "Time in HH:MM format"
    ACTIVITY_COLUMN = "Raw activity counts"
    VM_COLUMN = "Vector Magnitude activity counts"
    SLEEP_SCORE_COLUMN = "Sleep/Wake Algorithm: S=Sleep, W=Wake"
    CHOI_COLUMN = "Choi Algorithm: On=Wearing, Off=Not wearing"
    NWT_SENSOR_COLUMN = "NWT Sensor: Off=Not wearing"
    ACTIVITY_SOURCE_DROPDOWN = "Select which activity data column to display and use for Choi algorithm analysis.\nNote: Sadeh algorithm always uses Axis 1 regardless of this setting."


class FileDialogText(StrEnum):
    """File dialog text."""

    SELECT_DATA_FOLDER = "Select folder containing CSV data files"
    EMPTY_PATH = ""


# --- Styling ---


class UIColors(StrEnum):
    """UI color constants."""

    # Plot styling
    AXIS_PEN = "#333333"
    AXIS_TEXT = "#444444"
    ACTIVITY_DATA = "#2E86AB"
    SLEEP_START = "green"
    SLEEP_END = "red"
    SLEEP_ONSET_MARKER = "#0066CC"
    SLEEP_OFFSET_MARKER = "#CC0000"
    BACKGROUND_WHITE = "w"
    FOREGROUND_BLACK = "k"

    # Extended marker colors (colorblind-friendly blue/orange scheme)
    SELECTED_MARKER_ONSET = "#0080FF"  # Bright blue for main sleep onset
    SELECTED_MARKER_OFFSET = "#FF8000"  # Bright orange for main sleep offset
    UNSELECTED_MARKER_ONSET = "#004080"  # Darker blue for nap onset
    UNSELECTED_MARKER_OFFSET = "#CC4000"  # Darker orange for nap offset
    INCOMPLETE_MARKER = "#808080"  # Gray for incomplete markers
    HOVERED_MARKER = "#606060"  # Gray for selected/hovered markers
    NWT_MARKER_FILL = "#FFE4B5"  # Light beige fill
    NWT_MARKER_BORDER = "#D2691E"  # Chocolate border

    # Nonwear visualization colors (colorblind-friendly scheme)
    NONWEAR_SENSOR_BRUSH = "255,215,0,60"  # Gold with transparency for NWT sensor
    NONWEAR_SENSOR_BORDER = "218,165,32,120"  # Darker gold border
    CHOI_ALGORITHM_BRUSH = "147,112,219,60"  # Medium purple with transparency for Choi
    CHOI_ALGORITHM_BORDER = "138,43,226,120"  # Blue violet border for Choi
    NONWEAR_OVERLAP_BRUSH = "65,105,225,60"  # Royal blue with transparency for overlap
    NONWEAR_OVERLAP_BORDER = "0,0,255,120"  # Pure blue border for overlap

    # Manual nonwear marker colors (dashed lines, red scheme)
    SELECTED_MANUAL_NWT_START = "#DC143C"  # Crimson red for selected start
    SELECTED_MANUAL_NWT_END = "#B22222"  # Firebrick red for selected end
    UNSELECTED_MANUAL_NWT_START = "#8B0000"  # Dark red for unselected start
    UNSELECTED_MANUAL_NWT_END = "#660000"  # Darker red for unselected end
    INCOMPLETE_MANUAL_NWT = "#808080"  # Gray for incomplete markers

    # Adjacent day sleep marker colors (solid black lines)
    ADJACENT_SLEEP_START = "#000000"  # Solid black for adjacent day sleep start
    ADJACENT_SLEEP_END = "#333333"  # Dark gray for adjacent day sleep end

    # Date status colors
    DATE_WITH_MARKERS = "#27ae60"  # Green for dates with markers
    DATE_NO_SLEEP = "#e74c3c"  # Red for no sleep dates
    DATE_PARTIAL_COMPLETION = "#ff8c00"  # Orange for partial completion

    # Focus and interaction colors
    FOCUS_BORDER = "#0080FF"  # Blue focus border
    FOCUS_BACKGROUND = "#f0f8ff"  # Light blue focus background

    # Diary selection colors
    DIARY_SELECTION_DARKER = "#1a5490"  # Darker blue for diary selection highlighting

    # Button colors - Primary (blue)
    BUTTON_PRIMARY = "#4a90e2"
    BUTTON_PRIMARY_HOVER = "#357abd"
    BUTTON_PRIMARY_PRESSED = "#2868a8"
    BUTTON_PRIMARY_ALT = "#3498db"
    BUTTON_PRIMARY_ALT_HOVER = "#2980b9"

    # Button colors - Success (green)
    BUTTON_SUCCESS = "#28a745"
    BUTTON_SUCCESS_HOVER = "#229954"
    BUTTON_SUCCESS_ALT = "#2ecc71"
    BUTTON_SUCCESS_ALT_HOVER = "#27ae60"

    # Button colors - Danger (red)
    BUTTON_DANGER = "#dc3545"
    BUTTON_DANGER_HOVER = "#c0392b"
    BUTTON_DANGER_ALT = "#e74c3c"
    BUTTON_DANGER_ALT_HOVER = "#ec7063"

    # Button colors - Warning (orange)
    BUTTON_WARNING = "#ffc107"
    BUTTON_WARNING_HOVER = "#e0a800"

    # Panel/Background colors
    PANEL_BACKGROUND = "#f0f0f0"
    PANEL_BACKGROUND_LIGHT = "#f8f8f8"
    PANEL_BACKGROUND_SUCCESS = "#f0fff0"
    PANEL_BACKGROUND_ERROR = "#fff0f0"
    PANEL_BORDER = "#ced4da"
    PANEL_BORDER_LIGHT = "#ddd"

    # Text colors
    TEXT_PRIMARY = "#333333"
    TEXT_SECONDARY = "#666666"
    TEXT_MUTED = "#999999"

    # Status colors
    STATUS_ERROR = "#e74c3c"
    STATUS_SUCCESS = "#27ae60"
    STATUS_WARNING = "#f39c12"
    STATUS_INFO = "#3498db"

    # Table colors
    TABLE_ONSET_BACKGROUND = "#87CEEB"
    TABLE_OFFSET_BACKGROUND = "#FFDAB9"
    TABLE_HEADER_BACKGROUND = "#e0e0e0"
    TABLE_ROW_ALT = "#f5f5f5"


class ButtonStyle(StrEnum):
    """Button CSS styles."""

    # Common focus style for all interactive elements
    FOCUS_STYLE = "QPushButton:focus { border: 2px solid #0080FF; background-color: #f0f8ff; }"

    SAVE_MARKERS = """
        QPushButton {
            font-weight: bold;
            background-color: #0066CC;
            color: white;
        }
        QPushButton:focus {
            border: 2px solid #0080FF;
        }
    """
    SAVE_MARKERS_SAVED = """
        QPushButton {
            font-weight: bold;
            background-color: #004080;
            color: white;
        }
        QPushButton:focus {
            border: 2px solid #0080FF;
        }
    """
    MARK_NO_SLEEP = """
        QPushButton {
            font-weight: bold;
            background-color: #FF8000;
            color: white;
        }
        QPushButton:focus {
            border: 2px solid #0080FF;
        }
    """
    NO_SLEEP_MARKED = """
        QPushButton {
            font-weight: bold;
            background-color: #CC4000;
            color: white;
        }
        QPushButton:focus {
            border: 2px solid #0080FF;
        }
    """
    NAVIGATION = "font-size: 16px; padding: 8px 16px;"
    BOLD_PADDED = "font-weight: bold; padding: 5px 10px;"
    EXPORT = "font-weight: bold; padding: 10px;"
    CLEAR_MARKERS_RED = """
        QPushButton {
            font-weight: bold;
            padding: 5px 10px;
            background-color: #dc3545;
            color: white;
            border: 1px solid #bd2130;
            border-radius: 3px;
        }
        QPushButton:hover {
            background-color: #c82333;
        }
        QPushButton:pressed {
            background-color: #bd2130;
        }
    """


class LabelStyle(StrEnum):
    """Label CSS styles."""

    FOLDER_INFO = "color: #666; margin-left: 10px;"
    DATE_LABEL = "font-weight: bold; font-size: 20px; min-width: 200px; margin: 0 20px;"


# --- Table and Plot Configuration ---


class TableColumn(StrEnum):
    """Table column identifiers."""

    TIME = "Time"
    ACTIVITY = "Activity"
    VM = "VM"  # Vector Magnitude
    SLEEP_SCORE = "Sleep"  # Generic sleep/wake algorithm column (dynamically named)
    CHOI = "Choi"
    NWT_SENSOR = "NWT Sensor"
    IS_MARKER = "is_marker"
    START_TIME = "start_time"
    END_TIME = "end_time"
    DURATION_MINUTES = "duration_minutes"
    TIMESTAMP = "timestamp"
    SLEEP_WAKE_SCORE = "sleep_wake_score"
    AXIS_Y = "Axis Y"  # Display name for Y-axis (vertical)


class TableDimensions:
    """Table layout dimensions."""

    ROW_HEIGHT = 18  # Actual rendered row height in pixels

    # Fixed table widths for side tables
    TABLE_MIN_WIDTH = 1
    TABLE_MAX_WIDTH = 500  # Increased to allow wider tables
    TABLE_MARGINS = 5
    TABLE_SPACING = 3
    TABLE_HEADER_HEIGHT = 22
    TABLE_FONT_SIZE = 9

    # Marker table colors (matching the actual markers)
    ONSET_MARKER_BACKGROUND = "#87CEEB"  # Light blue (135, 206, 235) - Sky blue
    ONSET_MARKER_FOREGROUND = "#000000"  # Black text for readability
    OFFSET_MARKER_BACKGROUND = "#FFDAB9"  # Light orange/peach (255, 218, 185)
    OFFSET_MARKER_FOREGROUND = "#000000"  # Black text for readability


class PlotConstants:
    """Plot widget constants."""

    TICK_MAJOR = 3600  # 1 hour
    TICK_MINOR = 900  # 15 minutes
    MARKER_ADJUSTMENT_SECONDS = 60
    MINUTE_SNAP_SECONDS = 60


class MarkerLabel(StrEnum):
    """Sleep marker labels."""

    SLEEP_START = "Sleep Start"
    SLEEP_END = "Sleep End"
    SLEEP_ONSET = "Sleep Onset at {}\n3-minute rule applied"
    SLEEP_OFFSET = "Sleep Offset at {}\n5-minute rule applied"

    # Extended marker labels
    MAIN_SLEEP_START = "Main Sleep Start"
    MAIN_SLEEP_END = "Main Sleep End"
    NAP_START = "Nap Start"
    NAP_END = "Nap End"
    NWT_START = "Non-wear Start"
    NWT_END = "Non-wear End"


class PeriodKey(StrEnum):
    """Sleep period dictionary keys."""

    START_INDEX = "start_index"
    END_INDEX = "end_index"
    DURATION_MINUTES = "duration_minutes"


class DebugMessage(StrEnum):
    """Debug/logging messages."""

    AUTO_SAVED_MARKERS = "Auto-saved markers on change for {}"
    LOADED_SAVED_MARKERS = "Loaded saved markers for {} on {} from database"
    LOADED_RECORDS_ON_STARTUP = "Loaded {} saved records on startup from database"
    FOUND_DATA_FOR_FILES = "Found data for {} files: {}"
    USING_VECTOR_MAGNITUDE = "Using vector magnitude for Choi algorithm"
    VECTOR_MAGNITUDE_UNAVAILABLE = "Vector magnitude requested but multi-axis data not available, using single axis"
    DATA_INTERVALS_WARNING = "Data intervals may not be exactly 1 minute - proceeding with algorithm"


class AppArgument(StrEnum):
    """Application arguments."""

    PLATFORM = "-platform"
    WINDOWS_DARKMODE = "windows:darkmode=1"
    STYLE_FUSION = "--style=Fusion"


class PyQtGraphConfig(StrEnum):
    """PyQtGraph configuration keys."""

    BACKGROUND = "background"
    FOREGROUND = "foreground"
    ANTIALIAS = "antialias"


class ParadigmLabel(StrEnum):
    """Labels for data paradigm UI elements."""

    SECTION_TITLE = "Data Paradigm"
    COMBO_LABEL = "Data Paradigm:"
    EPOCH_BASED_DISPLAY = "Epoch-Based (CSV with activity counts)"
    RAW_ACCELEROMETER_DISPLAY = "Raw Accelerometer (GT3X / Raw CSV)"


class ParadigmTooltip(StrEnum):
    """Tooltips for data paradigm UI elements."""

    EPOCH_BASED = (
        "Use pre-epoched CSV files with 60-second activity counts.\n"
        "• Compatible with: ActiGraph, Actiwatch, MotionWatch CSV exports\n"
        "• Available algorithms: Sadeh (1994), Cole-Kripke (1992)\n"
        "• Best for: Standard sleep scoring workflows"
    )
    RAW_ACCELEROMETER = (
        "Use raw accelerometer data from GT3X files or raw CSV.\n"
        "• Compatible with: GT3X files, CSV with X/Y/Z acceleration columns\n"
        "• Available algorithms: All epoch-based + van Hees SIB, HDCZA\n"
        "• Best for: Research requiring z-angle analysis or GGIR-compatible methods"
    )
    COMBO_BOX = "Select the type of data files you will use for this study."


class ParadigmInfoText(StrEnum):
    """Info text for paradigm selection."""

    EPOCH_BASED_INFO = (
        "📊 <b>Epoch-Based Mode:</b> Import CSV files with pre-calculated activity counts. Compatible algorithms: Sadeh (1994), Cole-Kripke (1992)."
    )
    RAW_ACCELEROMETER_INFO = (
        "📈 <b>Raw Accelerometer Mode:</b> Import GT3X files or raw CSV with X/Y/Z data. All algorithms available including van Hees SIB and HDCZA."
    )


class ParadigmStyle(StrEnum):
    """CSS styles for paradigm UI elements."""

    LABEL = "QLabel { color: #2c3e50; margin-bottom: 5px; }"
    INFO_LABEL = "QLabel { color: #2980b9; font-size: 11px; padding: 8px; background-color: #ecf0f1; border-radius: 4px; }"
    SECTION_TITLE = "QLabel { font-size: 14px; font-weight: bold; color: #2c3e50; margin-top: 10px; margin-bottom: 5px; }"
    WARNING_BOX = (
        "QLabel { color: #e67e22; font-size: 11px; padding: 8px; background-color: #fef5e7; border: 1px solid #f39c12; border-radius: 4px; }"
    )


class SettingsSection(StrEnum):
    """Settings section titles."""

    DATA_PARADIGM = "1. Data Paradigm"
    PARTICIPANT_IDENTIFICATION = "2. Participant Identification"
    IMPORT_EXPORT_CONFIG = "3. Import/Export Configuration"
    ALGORITHM_SETTINGS = "Algorithm Settings"
    SLEEP_SCORING = "Sleep Scoring"
    NONWEAR_DETECTION = "Nonwear Detection"
    TIME_SETTINGS = "Time Settings"
    LIVE_ID_TESTING = "Live ID Pattern Testing"
    STUDY_PARAMETERS = "Study Parameters"
    VALID_VALUES = "Valid Groups and Timepoints"
    DEFAULT_SELECTION = "Default Selection"


class ParadigmWarning(StrEnum):
    """Warning messages for paradigm changes."""

    DATA_EXISTS = "You have imported data that may be incompatible with the new paradigm.\n\nContinue anyway?"
    RESET_RECOMMENDED = "Switching paradigms will update available data loaders and algorithms to match the new paradigm.\n\nDo you want to continue?"
    TITLE = "Confirm Paradigm Change"
    INCOMPATIBLE_FILE_WARNING = (
        "The currently selected file may not be compatible with the new paradigm.\n\nData loader and algorithm selections will be updated."
    )


class AlgorithmTooltip(StrEnum):
    """Tooltips for algorithm selection UI elements."""

    SLEEP_ALGORITHM_COMBO = (
        "Select the sleep scoring algorithm to use.\n\n"
        "EPOCH-BASED ALGORITHMS (require 60-second epoch counts):\n"
        "• Sadeh (1994) Original: Original algorithm with -4.0 threshold\n"
        "• Sadeh (1994) ActiLife: ActiLife-compatible version\n"
        "• Sadeh (1994) Count-Scaled: For modern accelerometers (GT3X+, wGT3X-BT)\n"
        "• Cole-Kripke (1992) variants: Alternative scoring algorithm\n\n"
        "RAW-DATA ALGORITHMS (require raw tri-axial accelerometer data):\n"
        "• van Hees (2015) SIB: Sustained Inactivity Bout detection\n"
        "• HDCZA (2018): Heuristic algorithm using z-angle distribution\n\n"
        "COUNT-SCALED variants divide counts by 100 and cap at 300 to\n"
        "correct for higher sensitivity in modern accelerometers."
    )


class AlgorithmHelpText(StrEnum):
    """Help text for algorithm selection."""

    SLEEP_ALGORITHM = (
        "The sleep scoring algorithm determines how each epoch is classified as Sleep or Wake. "
        "Different algorithms may produce slightly different results. Sadeh (1994) ActiLife is the most commonly used."
    )
    SLEEP_ALGORITHM_WITH_COMPATIBILITY = (
        "The sleep scoring algorithm determines how each epoch is classified as Sleep or Wake. "
        "Different algorithms may produce slightly different results. Sadeh (1994) ActiLife is the most commonly used. "
        "<b>Algorithm compatibility will be enforced based on your data file type.</b>"
    )
    COUNT_SCALED_EXPLANATION = (
        "Count-Scaled variants address sensitivity differences in modern accelerometers. "
        "Newer ActiGraph devices (GT3X+, wGT3X-BT) produce higher activity counts than the older "
        "devices (AM7164, AW64) used when Sadeh and Cole-Kripke algorithms were developed. "
        "This causes systematic overestimation of activity, leading to underestimation of sleep. "
        "Count-Scaled variants apply preprocessing: counts are divided by 100 and capped at 300 "
        "to improve accuracy with modern accelerometers."
    )
