"""
Sleep period detection implementations.

This package contains implementations of sleep period detectors that find
sleep onset and offset times (Sleep Period Time / SPT boundaries).

Epoch-based detectors (require pre-classified sleep/wake data):
    - ConsecutiveEpochsSleepPeriodDetector: Configurable consecutive epochs detector

Presets:
    - consecutive_onset3s_offset5s: 3 sleep epochs for onset, 5 sleep epochs for offset
    - consecutive_onset5s_offset10s: 5 sleep epochs for onset, 10 sleep epochs for offset
    - tudor_locke_2014: Tudor-Locke algorithm (5 sleep onset, 10 wake offset)

Configuration:
    - ConsecutiveEpochsSleepPeriodDetectorConfig: Full 2x3 parameter matrix
    - EpochState: SLEEP or WAKE
    - AnchorPosition: START or END of detected run

Note:
    Raw-data detectors (HDCZA, etc.) are not included. For raw accelerometer
    analysis, use rpy2 to call GGIR.

"""

from __future__ import annotations

from .config import (
    CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG,
    CONSECUTIVE_ONSET5S_OFFSET10S_CONFIG,
    TUDOR_LOCKE_2014_CONFIG,
    AnchorPosition,
    ConsecutiveEpochsSleepPeriodDetectorConfig,
    EpochState,
)
from .consecutive_epochs import (
    ConsecutiveEpochsSleepPeriodDetector,
    find_sleep_onset_offset,
)
from .factory import SleepPeriodDetectorFactory
from .metrics import SleepPeriodMetrics, TudorLockeSleepMetricsCalculator
from .protocol import SleepPeriodDetector

__all__ = [
    # Preset configs
    "CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG",
    "CONSECUTIVE_ONSET5S_OFFSET10S_CONFIG",
    "TUDOR_LOCKE_2014_CONFIG",
    "AnchorPosition",
    # Main classes
    "ConsecutiveEpochsSleepPeriodDetector",
    "ConsecutiveEpochsSleepPeriodDetectorConfig",
    # Enums
    "EpochState",
    # Protocol
    "SleepPeriodDetector",
    # Factory
    "SleepPeriodDetectorFactory",
    # Metrics
    "SleepPeriodMetrics",
    "TudorLockeSleepMetricsCalculator",
    # Convenience function
    "find_sleep_onset_offset",
]
