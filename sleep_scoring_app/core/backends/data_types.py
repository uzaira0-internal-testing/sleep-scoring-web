"""
Data structures for compute backend results.

This module defines immutable dataclasses for results returned by backend operations.
All structures are frozen to ensure data integrity and prevent accidental mutations.

Architecture:
    - Frozen dataclasses for immutability
    - Type-safe result objects
    - Standardized across all backends
    - Compatible with both gt3x-rs and Python implementations

Example Usage:
    >>> from sleep_scoring_app.core.backends import ComputeBackend, RawAccelerometerData
    >>>
    >>> backend = BackendFactory.create()
    >>> data = backend.parse_gt3x("file.gt3x")
    >>> isinstance(data, RawAccelerometerData)
    True

"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class RawAccelerometerData:
    """
    Raw tri-axial accelerometer data from device.

    Returned by parsing operations (GT3X, CSV, etc.).
    Contains high-frequency samples before any preprocessing.

    Attributes:
        x: X-axis acceleration values (lateral) in g
        y: Y-axis acceleration values (vertical) in g
        z: Z-axis acceleration values (forward/backward) in g
        timestamps: Timestamp for each sample (Unix seconds or datetime64)
        sample_rate: Sampling frequency in Hz
        metadata: Optional device and file metadata

    """

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    timestamps: np.ndarray
    sample_rate: float
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CalibrationResult:
    """
    Result of autocalibration operation.

    Contains calibration parameters and quality metrics.
    Compatible with GGIR calibration format.

    Attributes:
        success: Whether calibration succeeded
        scale: Scale factors for [X, Y, Z] axes
        offset: Offset values for [X, Y, Z] axes
        error_before: Calibration error before correction (deviation from 1g)
        error_after: Calibration error after correction
        n_points_used: Number of stationary points used
        message: Human-readable status message

    """

    success: bool
    scale: np.ndarray
    offset: np.ndarray
    error_before: float
    error_after: float
    n_points_used: int
    message: str


@dataclass(frozen=True)
class ImputationResult:
    """
    Result of time gap imputation operation.

    Contains gap-filled data and imputation statistics.
    Uses row replication method for GGIR compatibility.

    Attributes:
        x: Gap-filled X-axis data
        y: Gap-filled Y-axis data
        z: Gap-filled Z-axis data
        timestamps: Gap-filled timestamps
        n_gaps: Number of gaps detected
        n_samples_added: Total samples added via imputation
        total_gap_sec: Total duration of gaps in seconds
        gap_details: List of (start_idx, end_idx, duration_sec) for each gap

    """

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    timestamps: np.ndarray
    n_gaps: int
    n_samples_added: int
    total_gap_sec: float
    gap_details: list[tuple[int, int, float]] | None = None


@dataclass(frozen=True)
class EpochData:
    """
    Epoch-aggregated activity data.

    Result of epoching operation on raw samples.
    Typically 60-second windows for sleep analysis.

    Attributes:
        epoch_counts: Activity counts per epoch (sum of absolute values)
        epoch_timestamps: Timestamp for start of each epoch
        epoch_length_sec: Length of each epoch in seconds
        axis: Which axis was used ("x", "y", "z", or "vm" for vector magnitude)
        metadata: Optional epoch configuration metadata

    """

    epoch_counts: np.ndarray
    epoch_timestamps: np.ndarray
    epoch_length_sec: int
    axis: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class NonwearResult:
    """
    Nonwear detection result.

    Contains nonwear classifications and period information.

    Attributes:
        nonwear_vector: Boolean array (True = nonwear, False = wear)
        nonwear_periods: List of (start_idx, end_idx) tuples for nonwear periods
        algorithm: Algorithm used ("van_hees_2013", "van_hees_2023", "choi", "capsense")
        parameters: Algorithm parameters used
        metadata: Optional detection metadata

    """

    nonwear_vector: np.ndarray
    nonwear_periods: list[tuple[int, int]]
    algorithm: str
    parameters: dict[str, Any]
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SleepScoreResult:
    """
    Sleep/wake scoring result.

    Binary classification of each epoch as sleep or wake.

    Attributes:
        sleep_scores: Binary array (1 = sleep, 0 = wake)
        algorithm: Algorithm used ("sadeh", "cole_kripke", "van_hees_sib", "hdcza")
        confidence: Optional confidence scores per epoch
        parameters: Algorithm parameters used
        metadata: Optional scoring metadata

    """

    sleep_scores: np.ndarray
    algorithm: str
    confidence: np.ndarray | None = None
    parameters: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class SleepDetectionResult:
    """
    Sleep period detection result.

    Identifies sleep onset and offset times.

    Attributes:
        onset_idx: Index of sleep onset in data array
        offset_idx: Index of sleep offset (wake) in data array
        onset_time: Timestamp of sleep onset
        offset_time: Timestamp of sleep offset
        total_sleep_time_min: Total sleep time in minutes
        wake_after_sleep_onset_min: WASO in minutes
        sleep_efficiency_pct: Sleep efficiency percentage
        method: Detection method used
        metadata: Optional detection metadata

    """

    onset_idx: int
    offset_idx: int
    onset_time: Any  # datetime or timestamp
    offset_time: Any  # datetime or timestamp
    total_sleep_time_min: float
    wake_after_sleep_onset_min: float
    sleep_efficiency_pct: float
    method: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class MetricResult:
    """
    Generic metric calculation result.

    Used for ENMO, angles, and other continuous metrics.

    Attributes:
        values: Computed metric values
        metric_name: Name of metric ("enmo", "angle_z", "lfenmo", etc.)
        timestamps: Optional timestamps for each value
        parameters: Computation parameters
        metadata: Optional metric metadata

    """

    values: np.ndarray
    metric_name: str
    timestamps: np.ndarray | None = None
    parameters: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class CircadianResult:
    """
    Circadian rhythm metrics result.

    Contains M5/L5 or IS/IV metrics.

    Attributes:
        metric_name: Type of metric ("m5l5", "ivis", "sri")
        values: Dictionary of metric values
        timestamps: Optional timestamps for time-varying metrics
        metadata: Optional circadian metadata

    """

    metric_name: str
    values: dict[str, float]
    timestamps: np.ndarray | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ValidationResult:
    """
    Validation/agreement metric result.

    Used for Cohen's kappa, ICC, Bland-Altman.

    Attributes:
        metric_name: Validation metric ("kappa", "icc", "bland_altman")
        value: Primary metric value
        confidence_interval: Optional (lower, upper) CI bounds
        statistics: Additional statistics dictionary
        metadata: Optional validation metadata

    """

    metric_name: str
    value: float
    confidence_interval: tuple[float, float] | None = None
    statistics: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
