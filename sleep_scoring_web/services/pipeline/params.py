"""
Parameter dataclasses for each pipeline role.

All hardcoded constants from marker_placement.py are surfaced here
with their original defaults preserved. Frozen for immutability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sleep_scoring_web.schemas.enums import AlgorithmType

# Default component IDs — shared between PipelineParams and PipelineConfigRequest
DEFAULT_EPOCH_CLASSIFIER = AlgorithmType.SADEH_1994_ACTILIFE
DEFAULT_BOUT_DETECTOR = "consecutive_run"
DEFAULT_PERIOD_GUIDER = "diary"
DEFAULT_PERIOD_CONSTRUCTOR = "onset_offset"
DEFAULT_NONWEAR_DETECTOR = "flat_activity"
DEFAULT_DIARY_PREPROCESSOR = "ampm_corrector"

# Sentinel IDs for null/passthrough components
GUIDER_NONE = "none"
DIARY_PREPROCESSOR_PASSTHROUGH = "passthrough"


@dataclass(frozen=True)
class EpochClassifierParams:
    """Parameters for epoch classification."""

    # Algorithm-specific threshold (e.g., Sadeh: -4.0 for actilife, 0.0 for original)
    threshold: float | None = None


@dataclass(frozen=True)
class BoutDetectorParams:
    """Parameters for bout detection."""

    min_sleep_bout_epochs: int = 1  # Minimum consecutive sleep epochs to form a bout


@dataclass(frozen=True)
class PeriodGuiderParams:
    """Parameters for period guiding."""

    diary_tolerance_minutes: int = 15
    bout_merge_gap_minutes: int = 60  # Max wake gap to merge adjacent sleep bouts
    bout_padding_minutes: int = 30  # Padding around longest bout each side


@dataclass(frozen=True)
class PeriodConstructorParams:
    """Parameters for period construction (onset/offset finding)."""

    onset_min_consecutive_sleep: int = 3
    offset_min_consecutive_minutes: int = 5
    max_forward_offset_epochs: int = 60
    nap_min_consecutive_epochs: int = 10
    nap_max_search_epochs: int = 60
    enable_rule_8_clamping: bool = True  # Clamp onset to in-bed time (Rule 8)
    epoch_length_seconds: int = 60


@dataclass(frozen=True)
class NonwearDetectorParams:
    """Parameters for nonwear detection."""

    activity_threshold: int = 0
    zero_activity_ratio: float = 0.65  # Minimum fraction of zero-activity epochs required
    min_duration_minutes: int = 10
    epoch_length_seconds: int = 60
    # FlatActivityNonwearDetector params
    flat_activity_threshold: int = 0    # Max activity count to be considered "flat zero"
    flat_activity_min_minutes: int = 60  # Minimum flat-zero run duration (< Choi's 90 min)
    flat_activity_resumption_window_epochs: int = 30  # How far past the run end to look for resumption
    flat_activity_resumption_threshold: int = 500     # Min activity to count as "resumed" (not sleep)


@dataclass(frozen=True)
class DiaryPreprocessorParams:
    """Parameters for diary preprocessing."""

    enable_ampm_correction: bool = True
    plausibility_min_hours: float = 2.0
    plausibility_max_hours: float = 18.0
    data_margin_hours: float = 2.0


@dataclass(frozen=True)
class PipelineParams:
    """
    Top-level pipeline configuration.

    Contains role selections (component IDs) and sub-params for each role.
    """

    epoch_classifier: str = DEFAULT_EPOCH_CLASSIFIER
    bout_detector: str = DEFAULT_BOUT_DETECTOR
    period_guider: str = DEFAULT_PERIOD_GUIDER
    period_constructor: str = DEFAULT_PERIOD_CONSTRUCTOR
    nonwear_detector: str = DEFAULT_NONWEAR_DETECTOR
    diary_preprocessor: str = DEFAULT_DIARY_PREPROCESSOR

    epoch_classifier_params: EpochClassifierParams = field(default_factory=EpochClassifierParams)
    bout_detector_params: BoutDetectorParams = field(default_factory=BoutDetectorParams)
    period_guider_params: PeriodGuiderParams = field(default_factory=PeriodGuiderParams)
    period_constructor_params: PeriodConstructorParams = field(default_factory=PeriodConstructorParams)
    nonwear_detector_params: NonwearDetectorParams = field(default_factory=NonwearDetectorParams)
    diary_preprocessor_params: DiaryPreprocessorParams = field(default_factory=DiaryPreprocessorParams)

    @classmethod
    def from_legacy(
        cls,
        algorithm: str = DEFAULT_EPOCH_CLASSIFIER,
        onset_epochs: int = 3,
        offset_minutes: int = 5,
        include_diary: bool = True,
    ) -> PipelineParams:
        """Map current API parameters to pipeline params for backward compat."""
        return cls(
            epoch_classifier=algorithm,
            period_guider=DEFAULT_PERIOD_GUIDER if include_diary else GUIDER_NONE,
            diary_preprocessor=DEFAULT_DIARY_PREPROCESSOR if include_diary else DIARY_PREPROCESSOR_PASSTHROUGH,
            period_constructor_params=PeriodConstructorParams(
                onset_min_consecutive_sleep=onset_epochs,
                offset_min_consecutive_minutes=offset_minutes,
            ),
        )
