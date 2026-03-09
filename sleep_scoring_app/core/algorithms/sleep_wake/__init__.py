"""
Sleep scoring algorithm implementations.

This package contains implementations of sleep/wake classification algorithms.
All algorithms implement the SleepScoringAlgorithm protocol.

Algorithms:
    - SadehAlgorithm: Sadeh et al. (1994) - 11-minute window algorithm
    - ColeKripkeAlgorithm: Cole-Kripke (1992) - 7-minute weighted window algorithm

Exports:
    - SadehAlgorithm: Class implementing Sadeh algorithm
    - ColeKripkeAlgorithm: Class implementing Cole-Kripke algorithm
    - sadeh_score: Function-based Sadeh algorithm
    - cole_kripke_score: Function-based Cole-Kripke algorithm
    - score_activity_cole_kripke: Legacy Cole-Kripke function (list-based API)
    - find_datetime_column: Utility to find datetime column in DataFrame
    - validate_and_collapse_epochs: Utility to validate and resample epochs

Note:
    Raw data algorithms (Van Hees SIB, HDCZA) are not included in this package.
    For raw accelerometer analysis, use rpy2 to call GGIR.

"""

from __future__ import annotations

from .cole_kripke import ColeKripkeAlgorithm, cole_kripke_score, score_activity_cole_kripke
from .factory import AlgorithmFactory
from .protocol import SleepScoringAlgorithm
from .sadeh import SadehAlgorithm, sadeh_score
from .utils import find_datetime_column, validate_and_collapse_epochs

__all__ = [
    # Factory
    "AlgorithmFactory",
    "ColeKripkeAlgorithm",
    # Epoch-based algorithm classes
    "SadehAlgorithm",
    # Protocol
    "SleepScoringAlgorithm",
    # Cole-Kripke functions
    "cole_kripke_score",
    # General utilities
    "find_datetime_column",
    # Sadeh functions
    "sadeh_score",
    "score_activity_cole_kripke",
    "validate_and_collapse_epochs",
]
