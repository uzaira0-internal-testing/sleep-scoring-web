"""
Time gap imputation for GGIR replication.

This module replicates R GGIR g.imputeTimegaps function. The KEY insight is that
R uses ROW REPLICATION (np.repeat), not insertion after gap positions.

This is critical for achieving kappa=1.0 agreement with R GGIR.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ImputationConfig:
    """
    Configuration for time gap imputation.

    Attributes:
        gap_threshold_sec: Minimum gap duration to impute (default 0.25s).
            Will be adjusted to at least 2 samples at the given frequency.
        max_gap_min: Maximum gap to fully impute (default 90 min).
            Gaps longer than this may be partially filled.

    """

    gap_threshold_sec: float = 0.25
    max_gap_min: float = 90.0


@dataclass(frozen=True)
class ImputationResult:
    """
    Result of time gap imputation.

    Attributes:
        data: Imputed accelerometer data (n_samples_new, 3) for x, y, z axes.
        timestamps: Imputed timestamps (n_samples_new,) in seconds.
        n_gaps: Number of gaps detected and imputed.
        total_gap_sec: Total duration of gaps in seconds.
        n_samples_added: Total number of samples added through replication.
        qc_log: Full quality control statistics including zero replacement info.

    """

    data: np.ndarray
    timestamps: np.ndarray
    n_gaps: int
    total_gap_sec: float
    n_samples_added: int
    qc_log: dict[str, int | float]


def impute_timegaps(
    data: np.ndarray,
    timestamps: np.ndarray,
    sample_freq: float,
    config: ImputationConfig | None = None,
) -> ImputationResult:
    """
    Impute time gaps and zero values in accelerometer data.

    This replicates R GGIR g.imputeTimegaps using ROW REPLICATION.

    CRITICAL: This uses np.repeat() to replicate rows IN PLACE, not insertion.
    R lapply(x, rep, x.gap) replicates each row according to gap duration.
    This keeps epoch boundaries aligned correctly with R output.

    Args:
        data: Accelerometer data (n_samples, 3) for x, y, z axes.
        timestamps: Unix timestamps (seconds) for each sample.
        sample_freq: Sample frequency in Hz.
        config: Configuration for imputation thresholds. If None, uses defaults.

    Returns:
        ImputationResult with imputed data, timestamps, and QC statistics.

    Example:
        >>> data = np.array([[0.1, 0.2, 0.9], [0.2, 0.1, 0.95]])
        >>> timestamps = np.array([0.0, 1.0])  # 1 second gap at 30Hz = missing ~30 samples
        >>> result = impute_timegaps(data, timestamps, sample_freq=30.0)
        >>> result.n_gaps
        1
        >>> result.n_samples_added
        28  # Gap was filled by replicating the first sample

    """
    if config is None:
        config = ImputationConfig()

    # Convert timestamps to float seconds if needed
    if np.issubdtype(timestamps.dtype, np.datetime64):
        timestamps = timestamps.astype("datetime64[ns]").astype(np.float64) / 1e9

    timestamps = np.asarray(timestamps, dtype=np.float64)
    data = np.asarray(data, dtype=np.float64).copy()

    # Ensure k is at least 2 samples
    k = config.gap_threshold_sec
    k = max(k, 2 / sample_freq)

    # Initialize QC log
    qc_log: dict[str, int | float] = {
        "n_zeros_replaced": 0,
        "n_gaps": 0,
        "total_gap_samples": 0,
        "total_gap_seconds": 0.0,
    }

    # Step 1: Handle zeros (0, 0, 0)
    previous_last_value = np.array([0.0, 0.0, 1.0])
    zeros_mask = (data[:, 0] == 0) & (data[:, 1] == 0) & (data[:, 2] == 0)
    zero_indices = np.where(zeros_mask)[0]

    if len(zero_indices) > 0:
        qc_log["n_zeros_replaced"] = len(zero_indices)

        # Handle zeros at the start
        if zero_indices[0] == 0:
            data[0, :] = previous_last_value
            zero_indices = zero_indices[1:]

        # Handle zeros at the end
        impute_last = False
        if len(zero_indices) > 0 and zero_indices[-1] == len(data) - 1:
            impute_last = True
            zero_indices = zero_indices[:-1]

        # Remove middle zeros
        if len(zero_indices) > 0:
            keep_mask = np.ones(len(data), dtype=bool)
            keep_mask[zero_indices] = False
            data = data[keep_mask]
            timestamps = timestamps[keep_mask]

        # Impute last value if needed
        if impute_last and len(data) > 1:
            data[-1, :] = data[-2, :]

    # Step 2: Detect time gaps
    deltatime = np.diff(timestamps)
    gap_indices = np.where(deltatime >= k)[0]

    if len(gap_indices) == 0:
        return ImputationResult(
            data=data,
            timestamps=timestamps,
            n_gaps=0,
            total_gap_sec=0.0,
            n_samples_added=0,
            qc_log=qc_log,
        )

    qc_log["n_gaps"] = len(gap_indices)

    # Step 3: Row replication (THE KEY FIX)
    # R: x.gap[gapsi] = round(deltatime[gapsi] * sf)
    # R: x <- as.data.frame(lapply(x, rep, x.gap))
    gap_counts = np.ones(len(data), dtype=int)
    gap_counts[gap_indices] = np.round(deltatime[gap_indices] * sample_freq).astype(int)

    qc_log["total_gap_samples"] = int(np.sum(gap_counts[gap_indices]))
    qc_log["total_gap_seconds"] = float(np.sum(deltatime[gap_indices]))

    # Handle very long gaps (>max_gap_min) specially
    gap_limit_seconds = config.max_gap_min * 60
    gap_limit_samples = int(gap_limit_seconds * sample_freq)

    for gap_idx in gap_indices:
        gap_counts[gap_idx] = min(gap_counts[gap_idx], gap_limit_samples)

    # Normalize values at gap positions to 1g magnitude
    for idx in gap_indices:
        magnitude = np.sqrt(np.sum(data[idx, :] ** 2))
        if abs(magnitude - 1.0) > 0.005 and magnitude > 0:
            data[idx, :] = data[idx, :] / magnitude

    # Replicate rows using np.repeat (equivalent to R lapply(x, rep, x.gap))
    imputed_data = np.repeat(data, gap_counts, axis=0)

    # Generate new timestamps
    start_time = timestamps[0]
    imputed_timestamps = start_time + np.arange(len(imputed_data)) / sample_freq

    # Calculate samples added
    n_samples_added = len(imputed_data) - len(data)

    return ImputationResult(
        data=imputed_data,
        timestamps=imputed_timestamps,
        n_gaps=len(gap_indices),
        total_gap_sec=float(qc_log["total_gap_seconds"]),
        n_samples_added=n_samples_added,
        qc_log=qc_log,
    )
