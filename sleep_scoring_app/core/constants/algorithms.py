"""
Algorithm-related constants for Sleep Scoring Application.

Contains enums and constants for sleep scoring algorithms, nonwear detection,
and related algorithm parameters.
"""

from enum import StrEnum


class StudyDataParadigm(StrEnum):
    """
    Study-wide data paradigm that determines compatible file types and algorithms.

    This setting is configured once in Study Settings and controls:
    1. Which file types can be imported in Data Settings
    2. Which algorithms are available for selection
    3. The processing pipeline used

    Attributes:
        EPOCH_BASED: Pre-epoched data (ActiGraph/Actiwatch CSV exports)
            - Compatible files: CSV with 60-second epoch counts
            - Available algorithms: Sadeh, Cole-Kripke
            - Use case: Standard actigraphy workflow

        RAW_ACCELEROMETER: Raw tri-axial accelerometer data
            - Compatible files: GT3X, raw CSV with X/Y/Z columns
            - Available algorithms: All (Sadeh, Cole-Kripke via epoching, van Hees SIB, HDCZA)
            - Use case: Advanced analysis requiring z-angle or raw data algorithms

    """

    EPOCH_BASED = "epoch_based"
    RAW_ACCELEROMETER = "raw_accelerometer"

    @classmethod
    def get_default(cls) -> "StudyDataParadigm":
        """Get the default paradigm (epoch-based for backwards compatibility)."""
        return cls.EPOCH_BASED

    def get_display_name(self) -> str:
        """Get human-readable display name."""
        names = {
            StudyDataParadigm.EPOCH_BASED: "Epoch-Based (CSV with activity counts)",
            StudyDataParadigm.RAW_ACCELEROMETER: "Raw Accelerometer (GT3X / Raw CSV)",
        }
        return names.get(self, self.value)

    def get_description(self) -> str:
        """Get detailed description for tooltips."""
        descriptions = {
            StudyDataParadigm.EPOCH_BASED: (
                "Use pre-epoched CSV files with 60-second activity counts.\n"
                "• Compatible with: ActiGraph, Actiwatch, MotionWatch CSV exports\n"
                "• Available algorithms: Sadeh (1994), Cole-Kripke (1992)\n"
                "• Best for: Standard sleep scoring workflows"
            ),
            StudyDataParadigm.RAW_ACCELEROMETER: (
                "Use raw accelerometer data from GT3X files or raw CSV.\n"
                "• Compatible with: GT3X files, CSV with X/Y/Z acceleration columns\n"
                "• Available algorithms: All epoch-based + van Hees SIB, HDCZA\n"
                "• Best for: Research requiring z-angle analysis or GGIR-compatible methods"
            ),
        }
        return descriptions.get(self, "")

    def get_compatible_file_extensions(self) -> tuple[str, ...]:
        """Get file extensions compatible with this paradigm."""
        if self == StudyDataParadigm.EPOCH_BASED:
            return (".csv", ".xlsx", ".xls")
        # RAW_ACCELEROMETER
        return (".gt3x", ".csv", ".xlsx")

    def is_algorithm_compatible(self, algorithm_id: str) -> bool:
        """
        Check if an algorithm is compatible with this paradigm.

        Uses AlgorithmFactory.get_algorithm_data_requirement() to determine
        if the algorithm requires raw or epoch data.

        Paradigm compatibility:
        - EPOCH_BASED: Only epoch-based algorithms (Sadeh, Cole-Kripke with ActiLife counts)
        - RAW_ACCELEROMETER: Only raw-data algorithms (van Hees SIB, HDCZA)

        Note: Sadeh/Cole-Kripke are NOT compatible with raw GT3X data because they were
        designed for ActiLife activity counts, not zero-crossing counts from raw data.
        GGIR's implementation uses ZC counts calculated from raw data, which we don't
        yet support.

        Args:
            algorithm_id: Algorithm ID from AlgorithmFactory

        Returns:
            True if the algorithm can be used with this paradigm

        """
        # Import here to avoid circular imports
        from sleep_scoring_app.core.algorithms import AlgorithmFactory
        from sleep_scoring_app.core.pipeline import AlgorithmDataRequirement

        # Get the data requirement for this algorithm
        data_requirement = AlgorithmFactory.get_algorithm_data_requirement(algorithm_id)

        if data_requirement is None:
            # Unknown algorithm - allow it (fail later with better error)
            return True

        if self == StudyDataParadigm.EPOCH_BASED:
            # Epoch paradigm can only use epoch-based algorithms
            return data_requirement == AlgorithmDataRequirement.EPOCH_DATA
        # RAW_ACCELEROMETER - only supports raw-data algorithms
        # Sadeh/Cole-Kripke are NOT compatible because they need ActiLife counts,
        # not zero-crossing counts from raw data
        return data_requirement == AlgorithmDataRequirement.RAW_DATA


class AlgorithmType(StrEnum):
    """
    Sleep scoring algorithm identifiers.

    These values match the algorithm IDs registered in AlgorithmFactory.
    Use these for storing/retrieving algorithm type in database and exports.

    For creating algorithm instances, use AlgorithmFactory.create(algorithm_id).
    """

    # Sleep scoring algorithms (registered in AlgorithmFactory)
    SADEH_1994_ORIGINAL = "sadeh_1994_original"
    SADEH_1994_ACTILIFE = "sadeh_1994_actilife"
    COLE_KRIPKE_1992_ORIGINAL = "cole_kripke_1992_original"
    COLE_KRIPKE_1992_ACTILIFE = "cole_kripke_1992_actilife"
    VAN_HEES_2015_SIB = "van_hees_2015_sib"  # Implementation via rpy2/GGIR

    # Special values for UI/workflow states
    MANUAL = "manual"  # Manual scoring without algorithm
    CHOI = "choi"  # Nonwear detection (not sleep scoring)

    @classmethod
    def get_default(cls) -> "AlgorithmType":
        """Get the default algorithm type."""
        return cls.SADEH_1994_ACTILIFE

    @classmethod
    def from_value(cls, value: str) -> "AlgorithmType":
        """Parse algorithm type from string, defaulting to SADEH_1994_ACTILIFE if invalid."""
        try:
            return cls(value)
        except ValueError:
            return cls.SADEH_1994_ACTILIFE


class AlgorithmResult(StrEnum):
    """Algorithm result values."""

    SLEEP = "S"
    WAKE = "W"
    WEARING = "On"
    NOT_WEARING = "Off"


class NonwearAlgorithm(StrEnum):
    """
    Nonwear detection algorithm identifiers.

    These values match the algorithm IDs registered in NonwearAlgorithmFactory.
    Use these for storing/retrieving algorithm type in database and exports.

    For creating algorithm instances, use NonwearAlgorithmFactory.create(algorithm_id).
    """

    CHOI_2011 = "choi_2011"

    @classmethod
    def get_default(cls) -> "NonwearAlgorithm":
        """Get the default nonwear algorithm type."""
        return cls.CHOI_2011

    @classmethod
    def from_value(cls, value: str) -> "NonwearAlgorithm":
        """Parse nonwear algorithm from string, defaulting to CHOI_2011 if invalid."""
        try:
            return cls(value)
        except ValueError:
            return cls.CHOI_2011


class SleepPeriodDetectorType(StrEnum):
    """
    Sleep period detector identifiers.

    These values match the detector IDs registered in SleepPeriodDetectorFactory.
    Use these for storing/retrieving detector type in database and config.

    For creating detector instances, use SleepPeriodDetectorFactory.create(detector_id).
    """

    # Epoch-based detectors (work on pre-classified sleep/wake epochs)
    CONSECUTIVE_ONSET3S_OFFSET5S = "consecutive_onset3s_offset5s"
    CONSECUTIVE_ONSET5S_OFFSET10S = "consecutive_onset5s_offset10s"
    TUDOR_LOCKE_2014 = "tudor_locke_2014"

    @classmethod
    def get_default(cls) -> "SleepPeriodDetectorType":
        """Get the default sleep period detector type."""
        return cls.CONSECUTIVE_ONSET3S_OFFSET5S

    @classmethod
    def from_value(cls, value: str) -> "SleepPeriodDetectorType":
        """Parse detector type from string, defaulting to CONSECUTIVE_ONSET3S_OFFSET5S if invalid."""
        try:
            return cls(value)
        except ValueError:
            return cls.CONSECUTIVE_ONSET3S_OFFSET5S


class NonwearDataSource(StrEnum):
    """Nonwear data source types."""

    CHOI_ALGORITHM = "Choi Algorithm"  # Choi nonwear detection from accelerometer
    NONWEAR_SENSOR = "Nonwear Sensor"  # External nonwear sensor data
    NWT_SENSOR = "NWT Sensor"  # Alternative name for nonwear time sensor
    MANUAL_NWT = "Manual NWT"  # Manually marked non-wear time


class NonwearSourceFilter(StrEnum):
    """Filter options for nonwear data source selection."""

    CHOI = "choi"
    SENSOR = "sensor"
    COMBINED = "combined"


class SadehDataSource(StrEnum):
    """Sadeh data source types."""

    CALCULATED = "calculated"
    ACTILIFE = "actilife"


class MarkerType(StrEnum):
    """Sleep marker type classifications."""

    MAIN_SLEEP = "MAIN_SLEEP"
    NAP = "NAP"
    NWT = "nwt"


class SleepStatusValue(StrEnum):
    """Sleep status indicator values."""

    NO_SLEEP = "NO_SLEEP"


class AlgorithmParams:
    """Algorithm parameter constants."""

    # Choi algorithm
    CHOI_MIN_PERIOD_LENGTH = 90
    CHOI_SPIKE_TOLERANCE = 2
    CHOI_SMALL_WINDOW_LENGTH = 30

    # Sadeh algorithm
    SADEH_LOW_ACTIVITY_THRESHOLD = 30
    SADEH_NATS_MIN = 50
    SADEH_NATS_MAX = 100
    SADEH_ACTIVITY_CAP = 300  # Epoch counts over 300 are reduced to 300
    SADEH_COEFFICIENT_A = 7.601  # Intercept
    SADEH_COEFFICIENT_B = 0.065  # AVG coefficient
    SADEH_COEFFICIENT_C = 1.08  # NATS coefficient
    SADEH_COEFFICIENT_D = 0.056  # SD coefficient
    SADEH_COEFFICIENT_E = 0.703  # LG coefficient
    SADEH_THRESHOLD = -4  # If result > -4, epoch is asleep

    # Sleep rules
    SLEEP_ONSET_CONSECUTIVE_MINUTES = 3
    SLEEP_OFFSET_CONSECUTIVE_MINUTES = 5
    SLEEP_RULE_EXTENSION_MINUTES = 5


class MarkerLimits:
    """
    Marker validation limits.

    Note: MAX_SLEEP_PERIODS_PER_DAY is the default value.
    Actual runtime value is configurable via AppConfig.max_sleep_periods.
    """

    MAX_SLEEP_PERIODS_PER_DAY = 4  # 1 main sleep + up to 3 naps (default)
    MAX_NONWEAR_PERIODS_PER_DAY = 10  # User-placed manual nonwear markers


class MarkerCategory(StrEnum):
    """Category of marker for styling and routing purposes."""

    SLEEP = "sleep"
    NONWEAR = "nonwear"
    ADJACENT = "adjacent"


class MarkerEndpoint(StrEnum):
    """Which end of a marker period (generic, used for nonwear markers)."""

    START = "start"
    END = "end"


class SleepMarkerEndpoint(StrEnum):
    """Which end of a sleep marker period (onset/offset terminology)."""

    ONSET = "onset"
    OFFSET = "offset"


class MarkerPlacementState(StrEnum):
    """Marker placement state for rendering incomplete markers."""

    INCOMPLETE = "incomplete"
    COMPLETE = "complete"


class SelectionState(StrEnum):
    """Whether a marker is selected."""

    SELECTED = "selected"
    UNSELECTED = "unselected"


class AlgorithmOutputColumn(StrEnum):
    """
    Output column names added by algorithms to DataFrames.

    Use these constants instead of hardcoded strings when referencing
    algorithm output columns in DataFrames.
    """

    # Sleep scoring algorithm outputs
    SLEEP_SCORE = "Sleep Score"  # All sleep algorithms output (1=sleep, 0=wake)

    # Nonwear detection algorithm outputs
    NONWEAR_SCORE = "Nonwear Score"  # All nonwear algorithms output (1=nonwear, 0=wear)
