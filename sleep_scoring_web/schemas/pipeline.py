"""Pydantic models for the pipeline v2 API."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import PipelineParams

from pydantic import BaseModel, Field

from sleep_scoring_web.services.pipeline.params import (
    DEFAULT_BOUT_DETECTOR,
    DEFAULT_DIARY_PREPROCESSOR,
    DEFAULT_EPOCH_CLASSIFIER,
    DEFAULT_NONWEAR_DETECTOR,
    DEFAULT_PERIOD_CONSTRUCTOR,
    DEFAULT_PERIOD_GUIDER,
)

# ---------------------------------------------------------------------------
# Pydantic equivalents of param dataclasses (for JSON Schema / discovery)
# ---------------------------------------------------------------------------


class EpochClassifierParamsSchema(BaseModel):
    """Parameters for epoch classification algorithms."""

    threshold: float | None = Field(default=None, description="Decision boundary override (e.g., Sadeh actilife=-4.0, original=0.0)")


class BoutDetectorParamsSchema(BaseModel):
    """Parameters for sustained-state bout detection (GGIR: HASPT)."""

    min_sleep_bout_epochs: int = Field(default=1, ge=1, description="Minimum consecutive sleep epochs to form a bout")


class PeriodGuiderParamsSchema(BaseModel):
    """Parameters for sleep period search anchoring (GGIR: guider)."""

    diary_tolerance_minutes: int = Field(default=15, ge=1, le=120, description="Tolerance window around diary times for candidate selection")
    l5_window_hours: int = Field(default=12, ge=6, le=24, description="Total search window (hours) centered on L5 midpoint")
    bout_merge_gap_minutes: int = Field(default=60, ge=5, le=180, description="Max wake gap (minutes) to merge adjacent sleep bouts")
    bout_padding_minutes: int = Field(default=30, ge=0, le=120, description="Padding (minutes) around longest bout each side")


class PeriodConstructorParamsSchema(BaseModel):
    """Parameters for sleep period construction (GGIR: SPT-window)."""

    onset_min_consecutive_sleep: int = Field(default=3, ge=1, le=30, description="Minimum consecutive sleep epochs for onset detection")
    offset_min_consecutive_minutes: int = Field(default=5, ge=1, le=60, description="Minimum consecutive sleep minutes for offset detection")
    max_forward_offset_epochs: int = Field(default=60, ge=1, le=240, description="Maximum epochs to search forward past diary wake for offset")
    nap_min_consecutive_epochs: int = Field(default=10, ge=1, le=120, description="Minimum consecutive sleep epochs for nap detection")
    nap_max_search_epochs: int = Field(default=60, ge=1, le=240, description="Maximum epoch search radius for nap onset/offset")
    enable_rule_8_clamping: bool = Field(default=True, description="Clamp onset to in-bed time when onset precedes it (Rule 8)")
    epoch_length_seconds: int = Field(default=60, ge=1, le=300, description="Epoch duration in seconds")


class NonwearDetectorParamsSchema(BaseModel):
    """Parameters for nonwear period detection."""

    activity_threshold: int = Field(default=0, ge=0, le=1000, description="Maximum activity count to consider as zero/near-zero")
    zero_activity_ratio: float = Field(
        default=0.65, ge=0.0, le=1.0, description="Minimum fraction of zero-activity epochs required in nonwear period"
    )
    min_duration_minutes: int = Field(default=10, ge=1, le=120, description="Minimum nonwear period duration in minutes")
    epoch_length_seconds: int = Field(default=60, ge=1, le=300, description="Epoch duration in seconds")


class DiaryPreprocessorParamsSchema(BaseModel):
    """Parameters for diary validation and correction."""

    enable_ampm_correction: bool = Field(default=True, description="Enable AM/PM flip correction for diary times")
    plausibility_min_hours: float = Field(default=2.0, ge=0.5, le=12.0, description="Minimum plausible sleep duration in hours")
    plausibility_max_hours: float = Field(default=18.0, ge=6.0, le=24.0, description="Maximum plausible sleep duration in hours")
    data_margin_hours: float = Field(default=2.0, ge=0.0, le=6.0, description="Allowed margin beyond data window for diary times")


PARAM_SCHEMAS: dict[str, type[BaseModel]] = {
    "epoch_classifier": EpochClassifierParamsSchema,
    "bout_detector": BoutDetectorParamsSchema,
    "period_guider": PeriodGuiderParamsSchema,
    "period_constructor": PeriodConstructorParamsSchema,
    "nonwear_detector": NonwearDetectorParamsSchema,
    "diary_preprocessor": DiaryPreprocessorParamsSchema,
}

# Pre-computed JSON Schemas — avoids calling model_json_schema() per request
PARAM_JSON_SCHEMAS: dict[str, dict[str, Any]] = {role: schema_cls.model_json_schema() for role, schema_cls in PARAM_SCHEMAS.items()}


# ---------------------------------------------------------------------------
# Request model for the v2 auto-score endpoint
# ---------------------------------------------------------------------------


class PipelineConfigRequest(BaseModel):
    """Request body for the v2 auto-score endpoint."""

    epoch_classifier: str = DEFAULT_EPOCH_CLASSIFIER
    bout_detector: str = DEFAULT_BOUT_DETECTOR
    period_guider: str = DEFAULT_PERIOD_GUIDER
    period_constructor: str = DEFAULT_PERIOD_CONSTRUCTOR
    nonwear_detector: str = DEFAULT_NONWEAR_DETECTOR
    diary_preprocessor: str = DEFAULT_DIARY_PREPROCESSOR

    epoch_classifier_params: dict[str, Any] = Field(default_factory=dict)
    bout_detector_params: dict[str, Any] = Field(default_factory=dict)
    period_guider_params: dict[str, Any] = Field(default_factory=dict)
    period_constructor_params: dict[str, Any] = Field(default_factory=dict)
    nonwear_detector_params: dict[str, Any] = Field(default_factory=dict)
    diary_preprocessor_params: dict[str, Any] = Field(default_factory=dict)

    def to_pipeline_params(self) -> PipelineParams:
        """Convert to internal PipelineParams with typed sub-param dataclasses."""
        from sleep_scoring_web.services.pipeline.params import (
            BoutDetectorParams,
            DiaryPreprocessorParams,
            EpochClassifierParams,
            NonwearDetectorParams,
            PeriodConstructorParams,
            PeriodGuiderParams,
            PipelineParams,
        )

        return PipelineParams(
            epoch_classifier=self.epoch_classifier,
            bout_detector=self.bout_detector,
            period_guider=self.period_guider,
            period_constructor=self.period_constructor,
            nonwear_detector=self.nonwear_detector,
            diary_preprocessor=self.diary_preprocessor,
            epoch_classifier_params=EpochClassifierParams(**self.epoch_classifier_params)
            if self.epoch_classifier_params
            else EpochClassifierParams(),
            bout_detector_params=BoutDetectorParams(**self.bout_detector_params) if self.bout_detector_params else BoutDetectorParams(),
            period_guider_params=PeriodGuiderParams(**self.period_guider_params) if self.period_guider_params else PeriodGuiderParams(),
            period_constructor_params=PeriodConstructorParams(**self.period_constructor_params)
            if self.period_constructor_params
            else PeriodConstructorParams(),
            nonwear_detector_params=NonwearDetectorParams(**self.nonwear_detector_params)
            if self.nonwear_detector_params
            else NonwearDetectorParams(),
            diary_preprocessor_params=DiaryPreprocessorParams(**self.diary_preprocessor_params)
            if self.diary_preprocessor_params
            else DiaryPreprocessorParams(),
        )
