"""
I/O related constants for Sleep Scoring Application.

Contains enums and constants for data import, export, file system operations,
and external integrations.
"""

from enum import StrEnum


class ImportStatus(StrEnum):
    """File import status values."""

    PENDING = "pending"
    IMPORTING = "importing"
    IMPORTED = "imported"
    PROCESSED = "processed"
    ERROR = "error"
    UPDATED = "updated"


class DeleteStatus(StrEnum):
    """File deletion status values."""

    SUCCESS = "success"
    FAILED = "failed"
    ERROR = "error"
    NOT_FOUND = "not_found"
    HAS_METRICS = "has_metrics"


class FileSourceType(StrEnum):
    """Source type for data files - where the file data is loaded from."""

    DATABASE = "database"  # Imported into SQLite database
    CSV = "csv"  # Direct CSV file on filesystem

    @classmethod
    def get_default(cls) -> "FileSourceType":
        """Get the default file source type."""
        return cls.DATABASE


class DiaryFileType(StrEnum):
    """Diary file type constants."""

    CSV = "csv"
    EXCEL = "excel"
    XLSX = "xlsx"
    XLS = "xls"


class ExportColumn(StrEnum):
    """Export CSV column names."""

    FULL_PARTICIPANT_ID = "Full Participant ID"
    NUMERICAL_PARTICIPANT_ID = "Numerical Participant ID"
    PARTICIPANT_GROUP = "Participant Group"
    PARTICIPANT_TIMEPOINT = "Participant Timepoint"
    SLEEP_ALGORITHM = "Sleep Algorithm"
    SLEEP_DATE = "Sleep Date"
    ONSET_DATE = "Onset Date"
    ONSET_TIME = "Onset Time"
    OFFSET_DATE = "Offset Date"
    OFFSET_TIME = "Offset Time"
    TOTAL_COUNTS = "Total Counts"
    EFFICIENCY = "Efficiency"
    TOTAL_MINUTES_IN_BED = "Total Minutes in Bed"
    TOTAL_SLEEP_TIME = "Total Sleep Time (TST)"
    WASO = "Wake After Sleep Onset (WASO)"
    NUMBER_OF_AWAKENINGS = "Number of Awakenings"
    AVERAGE_AWAKENING_LENGTH = "Average Awakening Length"
    MOVEMENT_INDEX = "Movement Index"
    FRAGMENTATION_INDEX = "Fragmentation Index"
    SLEEP_FRAGMENTATION_INDEX = "Sleep Fragmentation Index"
    # Overlapping nonwear minutes during sleep period
    OVERLAPPING_NONWEAR_MINUTES_ALGORITHM = "Overlapping Nonwear Minutes (Algorithm)"
    OVERLAPPING_NONWEAR_MINUTES_SENSOR = "Overlapping Nonwear Minutes (Sensor)"

    # Sleep algorithm results
    SLEEP_ALGORITHM_NAME = "Sleep Scoring Algorithm"
    SLEEP_ALGORITHM_ONSET = "Sleep Algorithm Value at Onset"
    SLEEP_ALGORITHM_OFFSET = "Sleep Algorithm Value at Offset"

    # Onset/offset rule (NEW - for DI pattern)
    ONSET_OFFSET_RULE = "Onset/Offset Rule"

    SAVED_AT = "Saved At"

    # Consensus review flag
    NEEDS_CONSENSUS = "Needs Consensus Review"

    # Multiple sleep period columns
    MARKER_TYPE = "Marker Type"
    MARKER_INDEX = "Marker Index"

    # Diary nap columns
    NAP_OCCURRED = "Nap Occurred"
    NAP_ONSET_TIME = "Nap Onset Time"
    NAP_OFFSET_TIME = "Nap Offset Time"
    NAP_ONSET_TIME_2 = "Nap 2 Onset Time"
    NAP_OFFSET_TIME_2 = "Nap 2 Offset Time"
    NAP_ONSET_TIME_3 = "Nap 3 Onset Time"
    NAP_OFFSET_TIME_3 = "Nap 3 Offset Time"

    # Diary nonwear time columns
    NONWEAR_OCCURRED = "Nonwear Occurred"
    NONWEAR_REASON = "Nonwear Reason"
    NONWEAR_START_TIME = "Nonwear Start Time"
    NONWEAR_END_TIME = "Nonwear End Time"
    NONWEAR_REASON_2 = "Nonwear 2 Reason"
    NONWEAR_START_TIME_2 = "Nonwear 2 Start Time"
    NONWEAR_END_TIME_2 = "Nonwear 2 End Time"
    NONWEAR_REASON_3 = "Nonwear 3 Reason"
    NONWEAR_START_TIME_3 = "Nonwear 3 Start Time"
    NONWEAR_END_TIME_3 = "Nonwear 3 End Time"

    # Manual nonwear marker columns (placed by user in analysis tab) - supports up to 10 markers
    MANUAL_NWT_COUNT = "Manual NWT Count"
    MANUAL_NWT_1_START = "Manual NWT 1 Start"
    MANUAL_NWT_1_END = "Manual NWT 1 End"
    MANUAL_NWT_1_DURATION = "Manual NWT 1 Duration (min)"
    MANUAL_NWT_2_START = "Manual NWT 2 Start"
    MANUAL_NWT_2_END = "Manual NWT 2 End"
    MANUAL_NWT_2_DURATION = "Manual NWT 2 Duration (min)"
    MANUAL_NWT_3_START = "Manual NWT 3 Start"
    MANUAL_NWT_3_END = "Manual NWT 3 End"
    MANUAL_NWT_3_DURATION = "Manual NWT 3 Duration (min)"
    MANUAL_NWT_4_START = "Manual NWT 4 Start"
    MANUAL_NWT_4_END = "Manual NWT 4 End"
    MANUAL_NWT_4_DURATION = "Manual NWT 4 Duration (min)"
    MANUAL_NWT_5_START = "Manual NWT 5 Start"
    MANUAL_NWT_5_END = "Manual NWT 5 End"
    MANUAL_NWT_5_DURATION = "Manual NWT 5 Duration (min)"
    MANUAL_NWT_6_START = "Manual NWT 6 Start"
    MANUAL_NWT_6_END = "Manual NWT 6 End"
    MANUAL_NWT_6_DURATION = "Manual NWT 6 Duration (min)"
    MANUAL_NWT_7_START = "Manual NWT 7 Start"
    MANUAL_NWT_7_END = "Manual NWT 7 End"
    MANUAL_NWT_7_DURATION = "Manual NWT 7 Duration (min)"
    MANUAL_NWT_8_START = "Manual NWT 8 Start"
    MANUAL_NWT_8_END = "Manual NWT 8 End"
    MANUAL_NWT_8_DURATION = "Manual NWT 8 Duration (min)"
    MANUAL_NWT_9_START = "Manual NWT 9 Start"
    MANUAL_NWT_9_END = "Manual NWT 9 End"
    MANUAL_NWT_9_DURATION = "Manual NWT 9 Duration (min)"
    MANUAL_NWT_10_START = "Manual NWT 10 Start"
    MANUAL_NWT_10_END = "Manual NWT 10 End"
    MANUAL_NWT_10_DURATION = "Manual NWT 10 Duration (min)"
    MANUAL_NWT_TOTAL_DURATION = "Manual NWT Total Duration (min)"

    # Nonwear period export columns (for StudyData.export_nonwear_rows())
    NONWEAR_START = "Nonwear Start"
    NONWEAR_END = "Nonwear End"
    NONWEAR_DURATION_MINUTES = "Nonwear Duration (min)"
    NONWEAR_SOURCE = "Nonwear Source"
    NONWEAR_PERIOD_INDEX = "Nonwear Period Index"
    NONWEAR_OVERLAP_MINUTES = "Nonwear Overlap Minutes"


class ActivityColumn(StrEnum):
    """Activity data column search keywords."""

    VECTOR = "vector"
    MAGNITUDE = "magnitude"
    VM = "vm"
    VECTORMAGNITUDE = "vectormagnitude"
    ACTIVITY = "activity"
    COUNT = "count"
    # Axis detection patterns (lowercase for matching)
    AXIS_Y = "axis_y"  # ActiGraph Axis1 = Y-axis (vertical)
    AXIS_X = "axis_x"  # ActiGraph Axis2 = X-axis (lateral)
    AXIS_Z = "axis_z"  # ActiGraph Axis3 = Z-axis (forward)
    DATETIME = "datetime"
    TIMESTAMP = "timestamp"


class ActivityDataPreference(StrEnum):
    """Activity data column preferences for algorithms and plotting."""

    AXIS_Y = "axis_y"  # Vertical axis (ActiGraph Axis1)
    AXIS_X = "axis_x"  # Lateral axis (ActiGraph Axis2)
    AXIS_Z = "axis_z"  # Forward axis (ActiGraph Axis3)
    VECTOR_MAGNITUDE = "vector_magnitude"


class DefaultColumn(StrEnum):
    """Default CSV column names for ActiGraph format."""

    DATE = "DATE"
    TIME = "TIME"
    ACTIVITY = "ACTIVITY"
    VECTOR_MAGNITUDE = "Vector Magnitude"
    AXIS_Y = "Axis1"  # ActiGraph CSV header name for Y-axis (vertical)


class ParticipantGroup(StrEnum):
    """Compatibility enum for participant groups used in tests and exports."""

    GROUP_1 = "G1"
    GROUP_2 = "G2"
    GROUP_3 = "G3"
    ISSUE = "ISSUE"


class ParticipantTimepoint(StrEnum):
    """Compatibility enum for participant timepoints used in tests and exports."""

    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class RegexPattern(StrEnum):
    """Regular expression patterns."""

    PARTICIPANT_GROUP = r"g(\d+)"
    FILENAME_PATTERN = r"^(\d+)\s+([A-Z0-9]+)\s+\((\d{4}-\d{2}-\d{2})\)60sec$"
    PARTICIPANT_ID = r".*(\d+).*"


class FileExtension(StrEnum):
    """Supported file extensions."""

    CSV = ".csv"
    JSON = ".json"
    DB = ".db"
    LOG = ".log"


class DirectoryName(StrEnum):
    """Directory names used by the application."""

    BACKUPS = "backups"
    DATA = "data"
    RESULTS = "results"
    AUTOSAVES = "autosaves"
    CONFIG = ".sleep-scoring-demo"
    SLEEP_DATA_EXPORTS = "sleep_data_exports"


class FileName(StrEnum):
    """File names used by the application."""

    SLEEP_SCORING_DB = "sleep_scoring.db"
    CONFIG_JSON = "config.json"


class DevicePreset(StrEnum):
    """Device/format preset options."""

    ACTIGRAPH = "actigraph"
    GENEACTIV = "geneactiv"
    AXIVITY = "axivity"
    ACTIWATCH = "actiwatch"
    MOTIONWATCH = "motionwatch"
    GENERIC_CSV = "generic_csv"


class DataSourceType(StrEnum):
    """Data source type options."""

    CSV = "csv"
    GT3X = "gt3x"

    @classmethod
    def get_default(cls) -> "DataSourceType":
        """Get the default data source type."""
        return cls.CSV


class MetadataKey(StrEnum):
    """Metadata dictionary keys for file and device information."""

    SAMPLE_RATE = "sample_rate"
    SERIAL_NUMBER = "serial_number"
    START_TIME = "start_time"
    END_TIME = "end_time"
    DEVICE_TYPE = "device_type"
    FIRMWARE_VERSION = "firmware_version"
    SUBJECT_NAME = "subject_name"
    ACCELERATION_SCALE = "acceleration_scale"
    ACCELERATION_MIN = "acceleration_min"
    ACCELERATION_MAX = "acceleration_max"
    BATTERY_VOLTAGE = "battery_voltage"
    DOWNLOAD_TIME = "download_time"
    BOARD_REVISION = "board_revision"


class DiaryPeriodKey(StrEnum):
    """Dictionary keys for diary nap and nonwear period data."""

    START_TIME = "start_time"
    END_TIME = "end_time"
    DURATION = "duration"
    QUALITY = "quality"
    NOTES = "notes"
    REASON = "reason"
    INDEX = "index"


def sanitize_filename_component(text: str) -> str:
    """Sanitize text for use in filenames."""
    return "".join(c for c in str(text) if c.isalnum() or c in ("-", "_")).strip()


def get_backup_filename(algorithm: str) -> str:
    """Generate backup filename for algorithm."""
    safe_algorithm = sanitize_filename_component(algorithm)
    return f"sleep_scoring_backup_{safe_algorithm}{FileExtension.CSV}"
