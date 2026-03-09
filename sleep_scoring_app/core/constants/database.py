"""
Database schema constants for Sleep Scoring Application.

Contains enums for database tables and column names.
"""

from enum import StrEnum


class DatabaseTable(StrEnum):
    """Database table names."""

    SLEEP_METRICS = "sleep_metrics"
    RAW_ACTIVITY_DATA = "raw_activity_data"
    FILE_REGISTRY = "file_registry"
    NONWEAR_SENSOR_PERIODS = "nonwear_sensor_periods"
    CHOI_ALGORITHM_PERIODS = "choi_algorithm_periods"
    DIARY_DATA = "diary_data"
    DIARY_FILE_REGISTRY = "diary_file_registry"
    DIARY_RAW_DATA = "diary_raw_data"
    DIARY_NAP_PERIODS = "diary_nap_periods"
    DIARY_NONWEAR_PERIODS = "diary_nonwear_periods"
    SLEEP_MARKERS_EXTENDED = "sleep_markers_extended"
    MANUAL_NWT_MARKERS = "manual_nwt_markers"


class DatabaseColumn(StrEnum):
    """Database column names."""

    # Primary keys and identifiers
    ID = "id"
    FILENAME = "filename"
    PARTICIPANT_KEY = "participant_key"  # Composite key: participant_id_group_timepoint
    PARTICIPANT_ID = "participant_id"
    PARTICIPANT_GROUP = "participant_group"
    PARTICIPANT_TIMEPOINT = "participant_timepoint"
    ANALYSIS_DATE = "analysis_date"

    # Timestamp data
    ONSET_TIMESTAMP = "onset_timestamp"
    OFFSET_TIMESTAMP = "offset_timestamp"
    ONSET_TIME = "onset_time"
    OFFSET_TIME = "offset_time"

    # Sleep metrics
    TOTAL_SLEEP_TIME = "total_sleep_time"
    SLEEP_EFFICIENCY = "sleep_efficiency"
    WASO = "waso"
    AWAKENINGS = "awakenings"
    TOTAL_MINUTES_IN_BED = "total_minutes_in_bed"
    AVERAGE_AWAKENING_LENGTH = "average_awakening_length"
    ALGORITHM_TYPE = "algorithm_type"

    # Sleep algorithm columns
    SLEEP_ALGORITHM_NAME = "sleep_algorithm_name"  # e.g., "sadeh_1994", "cole_kripke_1992"
    SLEEP_ALGORITHM_ONSET = "sleep_algorithm_onset"  # Algorithm value at onset marker
    SLEEP_ALGORITHM_OFFSET = "sleep_algorithm_offset"  # Algorithm value at offset marker

    # Onset/offset rule identifier (NEW - for DI pattern)
    ONSET_OFFSET_RULE = "onset_offset_rule"  # e.g., "consecutive_3_5", "tudor_locke_2014"

    # Overlapping nonwear minutes during sleep period
    OVERLAPPING_NONWEAR_MINUTES_ALGORITHM = "overlapping_nonwear_minutes_algorithm"
    OVERLAPPING_NONWEAR_MINUTES_SENSOR = "overlapping_nonwear_minutes_sensor"

    # Activity metrics
    TOTAL_ACTIVITY = "total_activity"
    MOVEMENT_INDEX = "movement_index"
    FRAGMENTATION_INDEX = "fragmentation_index"
    SLEEP_FRAGMENTATION_INDEX = "sleep_fragmentation_index"

    # Metadata and timestamps
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"
    METADATA = "metadata"
    SLEEP_DATA = "sleep_data"
    DAILY_SLEEP_MARKERS = "daily_sleep_markers"

    # Raw activity data columns
    FILE_HASH = "file_hash"
    TIMESTAMP = "timestamp"
    AXIS_Y = "AXIS_Y"  # ActiGraph Axis1 = Y-axis (vertical)
    AXIS_X = "AXIS_X"  # ActiGraph Axis2 = X-axis (lateral)
    AXIS_Z = "AXIS_Z"  # ActiGraph Axis3 = Z-axis (forward)
    VECTOR_MAGNITUDE = "VECTOR_MAGNITUDE"
    STEPS = "steps"
    LUX = "lux"
    IMPORT_DATE = "import_date"

    # File registry columns
    ORIGINAL_PATH = "original_path"
    FILE_SIZE = "file_size"
    DATE_RANGE_START = "date_range_start"
    DATE_RANGE_END = "date_range_end"
    TOTAL_RECORDS = "total_records"
    LAST_MODIFIED = "last_modified"
    STATUS = "status"

    # Nonwear sensor and Choi algorithm period columns
    START_TIME = "start_time"
    END_TIME = "end_time"
    DURATION_MINUTES = "duration_minutes"
    START_INDEX = "start_index"
    END_INDEX = "end_index"
    PERIOD_TYPE = "period_type"

    # Extended sleep marker columns
    MARKER_INDEX = "marker_index"
    MARKER_TYPE = "marker_type"
    IS_MAIN_SLEEP = "is_main_sleep"
    CREATED_BY = "created_by"
    PERIOD_METRICS_JSON = "period_metrics_json"  # JSON blob for period-specific calculated metrics

    # Diary-specific columns
    DIARY_DATE = "diary_date"
    BEDTIME = "bedtime"
    WAKE_TIME = "wake_time"
    SLEEP_QUALITY = "sleep_quality"
    SLEEP_ONSET_TIME = "sleep_onset_time"
    SLEEP_OFFSET_TIME = "sleep_offset_time"
    IN_BED_TIME = "in_bed_time"
    NAP_OCCURRED = "nap_occurred"
    NAP_ONSET_TIME = "nap_onset_time"
    NAP_OFFSET_TIME = "nap_offset_time"
    # Additional nap columns for second and third naps
    NAP_ONSET_TIME_2 = "nap_onset_time_2"
    NAP_OFFSET_TIME_2 = "nap_offset_time_2"
    NAP_ONSET_TIME_3 = "nap_onset_time_3"
    NAP_OFFSET_TIME_3 = "nap_offset_time_3"
    NONWEAR_OCCURRED = "nonwear_occurred"
    NONWEAR_REASON = "nonwear_reason"
    NONWEAR_START_TIME = "nonwear_start_time"
    NONWEAR_END_TIME = "nonwear_end_time"
    # Additional nonwear columns for multiple periods
    NONWEAR_REASON_2 = "nonwear_reason_2"
    NONWEAR_START_TIME_2 = "nonwear_start_time_2"
    NONWEAR_END_TIME_2 = "nonwear_end_time_2"
    NONWEAR_REASON_3 = "nonwear_reason_3"
    NONWEAR_START_TIME_3 = "nonwear_start_time_3"
    NONWEAR_END_TIME_3 = "nonwear_end_time_3"
    DIARY_NOTES = "diary_notes"
    NIGHT_NUMBER = "night_number"
    ORIGINAL_COLUMN_MAPPING = "original_column_mapping"

    # Auto-calculated column flags
    BEDTIME_AUTO_CALCULATED = "bedtime_auto_calculated"
    WAKE_TIME_AUTO_CALCULATED = "wake_time_auto_calculated"
    SLEEP_ONSET_AUTO_CALCULATED = "sleep_onset_auto_calculated"
    SLEEP_OFFSET_AUTO_CALCULATED = "sleep_offset_auto_calculated"
    IN_BED_TIME_AUTO_CALCULATED = "in_bed_time_auto_calculated"

    # Nap period table columns
    NAP_INDEX = "nap_index"
    NAP_START_TIME = "nap_start_time"
    NAP_END_TIME = "nap_end_time"
    NAP_DURATION_MINUTES = "nap_duration_minutes"
    NAP_QUALITY = "nap_quality"
    NAP_NOTES = "nap_notes"

    # Nonwear period table columns
    NONWEAR_INDEX = "nonwear_index"
    NONWEAR_DURATION_MINUTES = "nonwear_duration_minutes"
    NONWEAR_NOTES = "nonwear_notes"

    # Manual nonwear marker columns
    SLEEP_DATE = "sleep_date"  # The date the marker belongs to (for organization)
    START_TIMESTAMP = "start_timestamp"  # Unix timestamp for marker start
    END_TIMESTAMP = "end_timestamp"  # Unix timestamp for marker end

    # Consensus review flag
    NEEDS_CONSENSUS = "needs_consensus"  # Flag for dates needing consensus review
