"""
Automated Marker Placement Module.

This module provides automated sleep and nap marker placement based on
configurable rules and feature extraction.

Main Components:
- Features: Dataclasses for epoch, run, spike, diary, and candidate features
- Extractors: Classes to extract features from raw data
- Rules: Rule implementations for marker placement decisions

Usage:
    from sleep_scoring_app.core.algorithms.marker_placement import (
        AutomatedMarkerPlacer,
        RuleConfig,
        DiaryDay,
    )

    # Create placer
    placer = AutomatedMarkerPlacer(
        timestamps=timestamps,
        activity_counts=activity,
        sleep_scores=scores,
        choi_nonwear=nonwear,
        diary=diary_day,
        all_diary_days=all_days,
        config=RuleConfig(onset_min_consecutive_sleep=3),
    )

    # Place markers
    main_sleep = placer.place_main_sleep()
    naps = placer.place_naps()

    # Debug info
    summary = placer.get_feature_summary()
"""

from sleep_scoring_app.core.algorithms.marker_placement.extractors import (
    CrossDayAggregator,
    EpochFeatureExtractor,
    RunLengthEncoder,
    SpikeDetector,
)
from sleep_scoring_app.core.algorithms.marker_placement.features import (
    ActivitySpike,
    CrossDayFeatures,
    DiaryDay,
    DiaryPeriod,
    EpochFeatures,
    NapCandidate,
    SleepPeriodCandidate,
    SleepRun,
)
from sleep_scoring_app.core.algorithms.marker_placement.rules import (
    AutomatedMarkerPlacer,
    MainSleepPeriodRule,
    NapPeriodRule,
    RuleConfig,
    SleepPeriodCandidateFinder,
)

__all__ = [
    # Features
    "ActivitySpike",
    # Rules
    "AutomatedMarkerPlacer",
    # Extractors
    "CrossDayAggregator",
    "CrossDayFeatures",
    "DiaryDay",
    "DiaryPeriod",
    "EpochFeatureExtractor",
    "EpochFeatures",
    "MainSleepPeriodRule",
    "NapCandidate",
    "NapPeriodRule",
    "RuleConfig",
    "RunLengthEncoder",
    "SleepPeriodCandidate",
    "SleepPeriodCandidateFinder",
    "SleepRun",
    "SpikeDetector",
]
