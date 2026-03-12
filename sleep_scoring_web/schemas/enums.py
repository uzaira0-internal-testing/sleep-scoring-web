"""
String enums for the Sleep Scoring Web API.

Ported from desktop app's core/constants/algorithms.py with web-specific additions.
These enums are the single source of truth for string constants.
"""

from enum import StrEnum


class UserRole(StrEnum):
    """User role for authorization."""

    ADMIN = "admin"
    ANNOTATOR = "annotator"
    REVIEWER = "reviewer"


class VerificationStatus(StrEnum):
    """Verification status for annotations."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    DISPUTED = "disputed"
    RESOLVED = "resolved"


class FileStatus(StrEnum):
    """File processing status."""

    PENDING = "pending"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AlgorithmType(StrEnum):
    """
    Sleep scoring algorithm identifiers.

    These values match the algorithm IDs registered in AlgorithmFactory.
    """

    SADEH_1994_ORIGINAL = "sadeh_1994_original"
    SADEH_1994_ACTILIFE = "sadeh_1994_actilife"
    COLE_KRIPKE_1992_ORIGINAL = "cole_kripke_1992_original"
    COLE_KRIPKE_1992_ACTILIFE = "cole_kripke_1992_actilife"
    MANUAL = "manual"

    @classmethod
    def get_default(cls) -> "AlgorithmType":
        """Get the default algorithm type."""
        return cls.SADEH_1994_ACTILIFE


class NonwearAlgorithm(StrEnum):
    """Nonwear detection algorithm identifiers."""

    CHOI_2011 = "choi_2011"

    @classmethod
    def get_default(cls) -> "NonwearAlgorithm":
        """Get the default nonwear algorithm."""
        return cls.CHOI_2011


class SleepPeriodDetectorType(StrEnum):
    """Sleep period detector identifiers."""

    CONSECUTIVE_ONSET3S_OFFSET5S = "consecutive_onset3s_offset5s"
    CONSECUTIVE_ONSET5S_OFFSET10S = "consecutive_onset5s_offset10s"
    TUDOR_LOCKE_2014 = "tudor_locke_2014"

    @classmethod
    def get_default(cls) -> "SleepPeriodDetectorType":
        """Get the default detector type."""
        return cls.CONSECUTIVE_ONSET3S_OFFSET5S


class MarkerType(StrEnum):
    """Sleep marker type classifications."""

    MAIN_SLEEP = "MAIN_SLEEP"
    NAP = "NAP"


class MarkerCategory(StrEnum):
    """Category of marker for styling and routing."""

    SLEEP = "sleep"
    NONWEAR = "nonwear"


class NonwearDataSource(StrEnum):
    """Nonwear data source types."""

    CHOI_ALGORITHM = "choi_algorithm"
    MANUAL = "manual"
    SENSOR = "sensor"


class ActivityDataPreference(StrEnum):
    """Preferred activity data column for display."""

    AXIS_Y = "axis_y"
    VECTOR_MAGNITUDE = "vector_magnitude"


class MarkerEndpoint(StrEnum):
    """Which end of a marker period (generic)."""

    START = "start"
    END = "end"


class SleepMarkerEndpoint(StrEnum):
    """Which end of a sleep marker period (onset/offset terminology)."""

    ONSET = "onset"
    OFFSET = "offset"


class MarkerPlacementState(StrEnum):
    """Marker placement state for two-click pattern."""

    IDLE = "idle"
    PLACING_ONSET = "placing_onset"
    PLACING_OFFSET = "placing_offset"
    COMPLETE = "complete"


class SelectionState(StrEnum):
    """Whether a marker is selected."""

    SELECTED = "selected"
    UNSELECTED = "unselected"


class AlgorithmOutputColumn(StrEnum):
    """Output column names from algorithms."""

    SLEEP_SCORE = "Sleep Score"  # 1=sleep, 0=wake
    NONWEAR_SCORE = "Nonwear Score"  # 1=nonwear, 0=wear


class AlgorithmParams:
    """Algorithm parameter constants (not an enum, a namespace class)."""

    # Choi algorithm
    CHOI_MIN_PERIOD_LENGTH = 90
    CHOI_SPIKE_TOLERANCE = 2
    CHOI_SMALL_WINDOW_LENGTH = 30

    # Sadeh algorithm
    SADEH_LOW_ACTIVITY_THRESHOLD = 30
    SADEH_NATS_MIN = 50
    SADEH_NATS_MAX = 100
    SADEH_ACTIVITY_CAP = 300
    SADEH_COEFFICIENT_A = 7.601
    SADEH_COEFFICIENT_B = 0.065
    SADEH_COEFFICIENT_C = 1.08
    SADEH_COEFFICIENT_D = 0.056
    SADEH_COEFFICIENT_E = 0.703
    SADEH_THRESHOLD = -4

    # Sleep rules
    SLEEP_ONSET_CONSECUTIVE_MINUTES = 3
    SLEEP_OFFSET_CONSECUTIVE_MINUTES = 5
    SLEEP_RULE_EXTENSION_MINUTES = 5


class MarkerLimits:
    """Marker validation limits (not an enum, a namespace class)."""

    MAX_SLEEP_PERIODS_PER_DAY = 4  # 1 main sleep + up to 3 naps
    MAX_NONWEAR_PERIODS_PER_DAY = 10  # User-placed manual nonwear markers
    EPOCH_DURATION_SECONDS = 60  # Standard epoch duration for snapping
