"""
Configuration dataclasses for sleep period detection algorithms.

This module provides immutable configuration objects for sleep period detection.
The main config is SleepPeriodDetectionConsecutiveEpochsConfig which supports
a 2x3 parameter matrix for onset and offset detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class EpochState(StrEnum):
    """State to look for in consecutive epoch detection."""

    SLEEP = "sleep"
    WAKE = "wake"


class AnchorPosition(StrEnum):
    """Which position of the detected run to return."""

    START = "start"  # First epoch of the consecutive run
    END = "end"  # Last epoch of the consecutive run


@dataclass(frozen=True)
class ConsecutiveEpochsSleepPeriodDetectorConfig:
    """
    Configuration for consecutive epochs sleep period detection.

    This config supports a full 2x3 parameter matrix for onset and offset:
    - onset_n: Number of consecutive epochs for onset detection
    - onset_state: What state to look for (SLEEP or WAKE)
    - onset_anchor: Return START or END of the detected run

    - offset_n: Number of consecutive epochs for offset detection
    - offset_state: What state to look for (SLEEP or WAKE)
    - offset_anchor: Return START or END of the detected run

    Common presets:
    - consecutive_onset3s_offset5s: onset=(3, SLEEP, START), offset=(5, SLEEP, END)
    - consecutive_onset5s_offset10w: onset=(5, SLEEP, START), offset=(10, WAKE, START) with preceding

    Attributes:
        onset_n: Consecutive epochs required for onset (default: 3)
        onset_state: State to detect for onset (default: SLEEP)
        onset_anchor: Position to return for onset (default: START)
        offset_n: Consecutive epochs required for offset (default: 5)
        offset_state: State to detect for offset (default: SLEEP)
        offset_anchor: Position to return for offset (default: END)
        offset_preceding_epoch: If True, return epoch before detected run (default: False)
        search_extension_minutes: Minutes to extend search beyond markers (default: 5)
        min_sleep_period_minutes: Minimum sleep period length in minutes (default: None = no minimum)
        max_sleep_period_minutes: Maximum sleep period length in minutes (default: 1440 = 24 hours)

    """

    # Onset parameters
    onset_n: int = 3
    onset_state: EpochState = EpochState.SLEEP
    onset_anchor: AnchorPosition = AnchorPosition.START

    # Offset parameters
    offset_n: int = 5
    offset_state: EpochState = EpochState.SLEEP
    offset_anchor: AnchorPosition = AnchorPosition.END
    offset_preceding_epoch: bool = False  # For Tudor-Locke style: return epoch before detected run

    # Search parameters
    search_extension_minutes: int = 5

    # Period length constraints (ActiLife Tudor-Locke Default uses 160 min / 1440 max)
    min_sleep_period_minutes: int | None = None  # None = no minimum
    max_sleep_period_minutes: int = 1440  # 24 hours


# Preset configs
CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG = ConsecutiveEpochsSleepPeriodDetectorConfig(
    onset_n=3,
    onset_state=EpochState.SLEEP,
    onset_anchor=AnchorPosition.START,
    offset_n=5,
    offset_state=EpochState.SLEEP,
    offset_anchor=AnchorPosition.END,
    offset_preceding_epoch=False,
    search_extension_minutes=5,
)

CONSECUTIVE_ONSET5S_OFFSET10S_CONFIG = ConsecutiveEpochsSleepPeriodDetectorConfig(
    onset_n=5,
    onset_state=EpochState.SLEEP,
    onset_anchor=AnchorPosition.START,
    offset_n=10,
    offset_state=EpochState.SLEEP,
    offset_anchor=AnchorPosition.END,
    offset_preceding_epoch=False,
    search_extension_minutes=5,
)

TUDOR_LOCKE_2014_CONFIG = ConsecutiveEpochsSleepPeriodDetectorConfig(
    onset_n=5,
    onset_state=EpochState.SLEEP,
    onset_anchor=AnchorPosition.START,
    offset_n=10,
    offset_state=EpochState.WAKE,
    offset_anchor=AnchorPosition.START,
    offset_preceding_epoch=True,  # Return last sleep epoch before wake run
    search_extension_minutes=5,
    min_sleep_period_minutes=160,  # ActiLife Tudor-Locke Default
    max_sleep_period_minutes=1440,  # 24 hours
)
