"""
Sleep scoring algorithms package - Framework-agnostic implementations.

This package provides pure Python implementations of validated sleep research algorithms
that can be used from any interface (GUI, CLI, web, batch processing) without framework
dependencies.

Algorithms Included:
    - Sadeh (1994): Sleep/wake classification from actigraphy
    - Cole-Kripke (1992): Alternative sleep/wake classification algorithm
    - Choi (2011): Nonwear period detection
    - ConsecutiveEpochsSleepPeriodDetector: Configurable sleep period detection

Note:
    Raw data algorithms (Van Hees SIB, HDCZA, van Hees nonwear) are not included.
    For raw accelerometer analysis, use rpy2 to call GGIR.

Package Structure:
    sleep_wake/     - Sleep/wake classification (protocol, factory, Sadeh, Cole-Kripke)
    nonwear/        - Nonwear detection (protocol, factory, Choi)
    sleep_period/   - Sleep period detection (protocol, factory, ConsecutiveEpochs)
    protocols/      - Shared callback protocols
    types.py        - Common type definitions (ActivityColumn enum)

Example Usage (Protocol-based Dependency Injection):
    ```python
    from sleep_scoring_app.core.algorithms import (
        AlgorithmFactory,
        NonwearAlgorithmFactory,
        SleepPeriodDetectorFactory,
    )

    # Create algorithm instances via factory
    sleep_algo = AlgorithmFactory.create('sadeh_1994_actilife')
    nonwear_algo = NonwearAlgorithmFactory.create('choi_2011')
    period_detector = SleepPeriodDetectorFactory.create('consecutive_onset3s_offset5s')

    # Use algorithms
    df = sleep_algo.score(activity_df)
    periods = nonwear_algo.detect(activity_data, timestamps)
    onset, offset = period_detector.apply_rules(sleep_scores, start, end, timestamps)
    ```

Example Usage (Function-based API):
    ```python
    import pandas as pd
    from sleep_scoring_app.core.algorithms import sadeh_score, choi_detect_nonwear, ActivityColumn

    # Load activity data into DataFrame
    df = pd.read_csv('activity_data.csv')

    # Sadeh sleep scoring
    df = sadeh_score(df)

    # Choi nonwear detection
    df = choi_detect_nonwear(df, activity_column=ActivityColumn.VECTOR_MAGNITUDE)
    ```

"""

from __future__ import annotations

from sleep_scoring_app.io.sources import (
    CSVDataSourceLoader,
    DataSourceFactory,
    DataSourceLoader,
    GT3XDataSourceLoader,
)
from sleep_scoring_app.preprocessing import (
    CalibrationConfig,
    CalibrationResult,
    ImputationConfig,
    ImputationResult,
    apply_calibration,
    calibrate,
    extract_calibration_features,
    impute_timegaps,
    select_stationary_points,
)

from .nonwear import (
    ChoiAlgorithm,
    NonwearAlgorithmFactory,
    NonwearDetectionAlgorithm,
)
from .nonwear.choi import NonwearPeriod, choi_detect_nonwear
from .protocols import CancellationCheck, LogCallback, ProgressCallback
from .sleep_period import (
    CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG,
    CONSECUTIVE_ONSET5S_OFFSET10S_CONFIG,
    TUDOR_LOCKE_2014_CONFIG,
    AnchorPosition,
    ConsecutiveEpochsSleepPeriodDetector,
    ConsecutiveEpochsSleepPeriodDetectorConfig,
    EpochState,
    SleepPeriodDetector,
    SleepPeriodDetectorFactory,
    SleepPeriodMetrics,
    TudorLockeSleepMetricsCalculator,
    find_sleep_onset_offset,
)
from .sleep_wake import (
    AlgorithmFactory,
    ColeKripkeAlgorithm,
    SadehAlgorithm,
    SleepScoringAlgorithm,
    cole_kripke_score,
    find_datetime_column,
    sadeh_score,
    score_activity_cole_kripke,
    validate_and_collapse_epochs,
)
from .types import ActivityColumn

__all__ = [
    "CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG",
    "CONSECUTIVE_ONSET5S_OFFSET10S_CONFIG",
    "TUDOR_LOCKE_2014_CONFIG",
    # === Type Definitions ===
    "ActivityColumn",
    "AlgorithmFactory",
    "AnchorPosition",
    "CSVDataSourceLoader",
    # === Re-exports: Preprocessing ===
    "CalibrationConfig",
    "CalibrationResult",
    # === Callback Protocols ===
    "CancellationCheck",
    "ChoiAlgorithm",
    "ColeKripkeAlgorithm",
    "ConsecutiveEpochsSleepPeriodDetector",
    "ConsecutiveEpochsSleepPeriodDetectorConfig",
    "DataSourceFactory",
    # === Re-exports: Data Sources ===
    "DataSourceLoader",
    "EpochState",
    "GT3XDataSourceLoader",
    "ImputationConfig",
    "ImputationResult",
    "LogCallback",
    "NonwearAlgorithmFactory",
    # === Nonwear Detection ===
    "NonwearDetectionAlgorithm",
    "NonwearPeriod",
    "ProgressCallback",
    "SadehAlgorithm",
    # === Sleep Period Detection ===
    "SleepPeriodDetector",
    "SleepPeriodDetectorFactory",
    # === Sleep Period Metrics ===
    "SleepPeriodMetrics",
    # === Sleep/Wake Classification ===
    "SleepScoringAlgorithm",
    "TudorLockeSleepMetricsCalculator",
    "apply_calibration",
    "calibrate",
    "choi_detect_nonwear",
    "cole_kripke_score",
    "extract_calibration_features",
    "find_datetime_column",
    "find_sleep_onset_offset",
    "impute_timegaps",
    "sadeh_score",
    "score_activity_cole_kripke",
    "select_stationary_points",
    "validate_and_collapse_epochs",
]

__version__ = "5.0.0"  # Removed backward compatibility aliases
__author__ = "Sleep Scoring Team"
__description__ = "Framework-agnostic sleep scoring algorithms for research"
