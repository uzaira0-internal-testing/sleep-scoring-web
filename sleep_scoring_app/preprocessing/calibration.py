"""
Auto-calibration (sphere fitting) for accelerometer data.

Implements sphere calibration using Levenberg-Marquardt optimization
to correct sensor drift by fitting accelerometer data to the expected 1g sphere.

This module is ported from accelerometer-nonwear package and provides
validated calibration algorithms for sleep research applications.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import least_squares

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class CalibrationConfig:
    """
    Configuration for auto-calibration (sphere calibration).

    Attributes:
        epoch_size_sec: Size of calibration epochs in seconds.
        sphere_criterion: Criterion for sphere population check.
        sd_criterion: SD threshold for stationary point selection.
        min_stationary_points: Minimum number of stationary points needed.

    """

    epoch_size_sec: int = 10
    sphere_criterion: float = 0.3
    sd_criterion: float = 0.013
    min_stationary_points: int = 10


@dataclass(frozen=True)
class CalibrationResult:
    """
    Result from auto-calibration.

    Attributes:
        scale: Scale factors for x, y, z axes.
        offset: Offset values for x, y, z axes.
        error_before: Calibration error before optimization.
        error_after: Calibration error after optimization.
        n_points_used: Number of stationary points used.
        success: Whether calibration was successful.
        message: Status message.

    """

    scale: np.ndarray
    offset: np.ndarray
    error_before: float
    error_after: float
    n_points_used: int
    success: bool
    message: str

    def __post_init__(self) -> None:
        """Ensure arrays are immutable."""
        if isinstance(self.scale, np.ndarray):
            self.scale.flags.writeable = False
        if isinstance(self.offset, np.ndarray):
            self.offset.flags.writeable = False


def extract_calibration_features(
    data: np.ndarray,
    sample_rate: float,
    epoch_size_sec: int = 10,
) -> np.ndarray:
    """
    Extract features for calibration from accelerometer data.

    Calculates per-epoch features: EN (Euclidean norm), mean x/y/z, SD x/y/z.

    Args:
        data: Accelerometer data (n_samples, 3) for x, y, z.
        sample_rate: Sample frequency in Hz.
        epoch_size_sec: Epoch size in seconds.

    Returns:
        Feature array (n_epochs, 7): [EN, mean_x, mean_y, mean_z, sd_x, sd_y, sd_z]

    """
    window_len = int(sample_rate * epoch_size_sec)
    n_windows = len(data) // window_len

    if n_windows == 0:
        return np.array([]).reshape(0, 7)

    n_use = n_windows * window_len
    data_trimmed = data[:n_use]
    data_reshaped = data_trimmed.reshape((n_windows, window_len, 3))

    # EN per sample within each window
    en_per_sample = np.sqrt(np.sum(data_reshaped**2, axis=2))
    epoch_en = np.mean(en_per_sample, axis=1)

    # Means per axis
    epoch_mean = np.mean(data_reshaped, axis=1)

    # SDs per axis (ddof=1 for sample SD)
    epoch_sd = np.std(data_reshaped, axis=1, ddof=1)

    return np.column_stack([epoch_en, epoch_mean, epoch_sd])


def select_stationary_points(
    features: np.ndarray,
    sd_criterion: float = 0.013,
    sphere_criterion: float = 0.3,
) -> tuple[np.ndarray, str]:
    """
    Select stationary points for calibration.

    Filters features to find non-movement periods suitable for sphere calibration.

    Args:
        features: Feature array from extract_calibration_features.
        sd_criterion: SD threshold for stationary detection.
        sphere_criterion: Criterion for sphere population check.

    Returns:
        Tuple of (filtered features, status message).

    """
    # Filter valid data (remove 99999 or NaNs)
    valid_mask = (features[:, 0] != 99999) & ~np.isnan(features[:, 0]) & ~np.isnan(features[:, 3])
    features_temp = features[valid_mask]

    # Remove first row as R does
    if len(features_temp) > 1:
        features_temp = features_temp[1:]

    # Remove duplicate non-wear rows where means repeat
    if len(features_temp) > 1:
        comparison = features_temp[:-1, 1:7] == features_temp[1:, 1:7]
        matches_per_row = np.sum(comparison, axis=1)
        is_dup = matches_per_row == 3
        keep_mask = np.concatenate(([True], ~is_dup))
        features_temp = features_temp[keep_mask]

    # Select non-movement periods
    nomovement_mask = (
        (features_temp[:, 4] < sd_criterion)
        & (features_temp[:, 5] < sd_criterion)
        & (features_temp[:, 6] < sd_criterion)
        & (np.abs(features_temp[:, 1]) < 2)
        & (np.abs(features_temp[:, 2]) < 2)
        & (np.abs(features_temp[:, 3]) < 2)
    )
    features_temp = features_temp[nomovement_mask]

    if len(features_temp) < 10:
        return features_temp, "not enough stationary points"

    # Check sphere population (need points on all sides)
    tel = 0
    for axis in range(1, 4):
        if np.min(features_temp[:, axis]) < -sphere_criterion and np.max(features_temp[:, axis]) > sphere_criterion:
            tel += 1

    if tel < 3:
        return features_temp, "not enough points on all sides of sphere"

    return features_temp, "ok"


def calibrate(
    data: np.ndarray,
    sample_rate: float,
    config: CalibrationConfig | None = None,
) -> CalibrationResult:
    """
    Perform auto-calibration on accelerometer data.

    Args:
        data: Accelerometer data (n_samples, 3) for x, y, z axes.
        sample_rate: Sample frequency in Hz.
        config: Calibration configuration (uses defaults if None).

    Returns:
        CalibrationResult with scale, offset, and diagnostic information.

    """
    if config is None:
        config = CalibrationConfig()

    # Extract features
    features = extract_calibration_features(data, sample_rate, config.epoch_size_sec)

    # Select stationary points
    stationary_points, status = select_stationary_points(features, config.sd_criterion, config.sphere_criterion)

    # Check if we have enough data
    if len(stationary_points) < config.min_stationary_points:
        return CalibrationResult(
            scale=np.ones(3),
            offset=np.zeros(3),
            error_before=np.nan,
            error_after=np.nan,
            n_points_used=len(stationary_points),
            success=False,
            message=status,
        )

    # Run optimization or fallback if SciPy is unavailable
    input_data = stationary_points[:, 1:4]  # x, y, z means

    # Initial guess
    offset_init = np.zeros(3)
    scale_init = np.ones(3)
    x0 = np.concatenate([offset_init, scale_init])

    def residuals(params):
        offset = params[:3]
        scale = params[3:6]
        calibrated = (input_data + offset) * scale
        norms = np.sqrt(np.sum(calibrated**2, axis=1))
        return norms - 1.0

    result = least_squares(
        residuals,
        x0=x0,
        method="lm",
        ftol=1.49e-8,
        xtol=1.49e-8,
        gtol=np.finfo(float).eps,
    )

    offset = result.x[:3]
    scale = result.x[3:6]

    cal_error_start_vals = np.sqrt(np.sum(input_data**2, axis=1))
    cal_error_start = np.round(np.mean(np.abs(cal_error_start_vals - 1)), 5)

    calibrated_data = (input_data + offset) * scale
    cal_error_end_vals = np.sqrt(np.sum(calibrated_data**2, axis=1))
    cal_error_end = np.round(np.mean(np.abs(cal_error_end_vals - 1)), 5)

    return CalibrationResult(
        scale=scale,
        offset=offset,
        error_before=cal_error_start,
        error_after=cal_error_end,
        n_points_used=len(stationary_points),
        success=True,
        message="calibration successful",
    )


def apply_calibration(
    data: np.ndarray | pd.DataFrame,
    scale: np.ndarray,
    offset: np.ndarray,
) -> np.ndarray | pd.DataFrame:
    """
    Apply calibration parameters to accelerometer data.

    Args:
        data: Accelerometer data (n_samples, 3) as numpy array or DataFrame.
              If DataFrame, must have columns for x, y, z axes.
        scale: Scale factors for x, y, z axes.
        offset: Offset values for x, y, z axes.

    Returns:
        Calibrated data in the same format as input.

    """
    if isinstance(data, np.ndarray):
        # Numpy array - apply directly
        return (data + offset) * scale

    # DataFrame - need to identify axis columns
    import pandas as pd

    if not isinstance(data, pd.DataFrame):
        msg = f"Data must be numpy array or pandas DataFrame, got {type(data)}"
        raise TypeError(msg)

    # Make a copy to avoid modifying original
    calibrated = data.copy()

    # Try to find axis columns (common naming patterns)
    axis_cols = []
    for possible_names in [
        ["X", "Y", "Z"],
        ["x", "y", "z"],
        ["Axis1", "Axis2", "Axis3"],
        ["axis1", "axis2", "axis3"],
    ]:
        if all(col in calibrated.columns for col in possible_names):
            axis_cols = possible_names
            break

    if not axis_cols:
        msg = "Could not find x, y, z axis columns in DataFrame"
        raise ValueError(msg)

    # Apply calibration to each axis
    for i, col in enumerate(axis_cols):
        calibrated[col] = (calibrated[col] + offset[i]) * scale[i]

    return calibrated


__all__ = [
    "CalibrationConfig",
    "CalibrationResult",
    "apply_calibration",
    "calibrate",
    "extract_calibration_features",
    "select_stationary_points",
]
