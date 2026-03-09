"""
Shared callback protocols for algorithms.

This package contains callback protocol definitions shared across algorithm types.

Note: Domain-specific protocols (SleepScoringAlgorithm, NonwearDetectionAlgorithm,
SleepPeriodDetector) are now colocated with their implementations in their
respective subpackages (sleep_wake/, nonwear/, sleep_period/).

Exports:
    - ProgressCallback: Protocol for progress reporting
    - CancellationCheck: Protocol for cancellation checking
    - LogCallback: Protocol for logging

"""

from __future__ import annotations

from .callbacks import CancellationCheck, LogCallback, ProgressCallback

__all__ = [
    "CancellationCheck",
    "LogCallback",
    "ProgressCallback",
]
