"""
Scoring pipeline package.

Provides a pluggable, protocol-based pipeline for sleep scoring that supports
multiple algorithm frameworks (Sadeh/Cole-Kripke, GGIR, etc.) and ML
hyperparameter optimization.

Public API:
    ScoringPipeline  - orchestrator
    PipelineParams   - top-level configuration
    PipelineResult   - output container
    PipelineRole     - registry role enum
    describe_pipeline - registry discovery
    register         - component registration decorator
    run_via_pipeline - backward-compat bridge
"""

# Import all implementations to trigger registration
from . import bout_detectors as _bout_detectors
from . import diary_preprocessors as _diary_preprocessors
from . import epoch_classifiers as _epoch_classifiers
from . import nonwear_detectors as _nonwear_detectors
from . import period_constructors as _period_constructors
from . import period_guiders as _period_guiders
from .compat import run_via_pipeline
from .orchestrator import ScoringPipeline
from .params import (
    BoutDetectorParams,
    DiaryPreprocessorParams,
    EpochClassifierParams,
    NonwearDetectorParams,
    PeriodConstructorParams,
    PeriodGuiderParams,
    PipelineParams,
)
from .protocols import (
    Bout,
    ClassifiedEpochs,
    DiaryInput,
    EpochSeries,
    GuideWindow,
    NapGuideWindow,
    NonwearPeriodResult,
    PipelineResult,
    RawDiaryInput,
    SleepPeriodResult,
)
from .registry import PipelineRole, describe_pipeline, register

__all__ = [
    "Bout",
    "BoutDetectorParams",
    "ClassifiedEpochs",
    "DiaryInput",
    "DiaryPreprocessorParams",
    "EpochClassifierParams",
    "EpochSeries",
    "GuideWindow",
    "NapGuideWindow",
    "NonwearDetectorParams",
    "NonwearPeriodResult",
    "PeriodConstructorParams",
    "PeriodGuiderParams",
    "PipelineParams",
    "PipelineResult",
    "PipelineRole",
    "RawDiaryInput",
    "ScoringPipeline",
    "SleepPeriodResult",
    "describe_pipeline",
    "register",
    "run_via_pipeline",
]
