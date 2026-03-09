"""
Shared utility functions for sleep scoring algorithms.

This module provides common utility functions used across multiple algorithm
implementations (Sadeh, Choi, etc.) to eliminate code duplication.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def scale_counts(counts: np.ndarray, scale_factor: float = 100.0, cap: float = 300.0) -> np.ndarray:
    """
    Scale activity counts for modern accelerometer compatibility.

    Modern ActiGraph accelerometers (GT3X+, wGT3X-BT) are more sensitive than
    the older devices (AM7164, AW64) used when Sadeh and Cole-Kripke algorithms
    were developed. This causes systematic overestimation of activity counts,
    leading to underestimation of sleep.

    The count-scaled approach addresses this by:
    1. Scaling count values by a division factor (typically /100)
    2. Capping scaled values at a maximum (typically 300)

    This preprocessing step should be applied BEFORE the algorithm's sleep/wake
    classification to improve accuracy with modern accelerometers.

    Args:
        counts: Raw activity counts from modern accelerometer
        scale_factor: Division factor (default: 100.0)
        cap: Maximum value after scaling (default: 300.0)

    Returns:
        Scaled counts suitable for Sadeh/Cole-Kripke algorithms

    References:
        - GGIR R Package count scaling implementation
        - Meredith-Jones KA, et al. (2024). Validation of actigraphy sleep metrics
          in children aged 8 to 16 years. Int J Behav Nutr Phys Act.
        - Chen PW, et al. (2025). Performance of an Automated Sleep Scoring Approach
          for Actigraphy Data in Children and Adolescents. Sleep.

    Example:
        >>> import numpy as np
        >>> raw_counts = np.array([4500, 3200, 1000, 25000])
        >>> scaled = scale_counts(raw_counts, scale_factor=100.0, cap=300.0)
        >>> scaled
        array([45.0, 32.0, 10.0, 300.0])

    """
    scaled = counts / scale_factor
    return np.clip(scaled, 0, cap)


def find_datetime_column(df: pd.DataFrame) -> str:
    """
    Find the datetime column in a DataFrame.

    Searches for common datetime column names first, then falls back to
    checking column dtypes.

    Args:
        df: DataFrame to search

    Returns:
        Name of the datetime column

    Raises:
        ValueError: If no datetime column is found

    """
    for col in df.columns:
        col_lower = col.lower()
        if col_lower in {"datetime", "timestamp", "time"}:
            return col

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            return col

    msg = "No datetime column found. Expected 'datetime', 'timestamp', or a datetime-typed column."
    raise ValueError(msg)


def validate_and_collapse_epochs(df: pd.DataFrame, datetime_col: str) -> pd.DataFrame:
    """
    Validate that epochs are 1-minute intervals and collapse if needed.

    Args:
        df: DataFrame with datetime column
        datetime_col: Name of the datetime column

    Returns:
        DataFrame with validated 1-minute epochs

    Raises:
        ValueError: If epochs are larger than 1 minute

    """
    if len(df) <= 1:
        return df

    df = df.sort_values(by=datetime_col).reset_index(drop=True)

    time_diffs = df[datetime_col].diff().dt.total_seconds() / 60

    mean_interval = time_diffs[1:].mean()

    if abs(mean_interval - 1.0) < 0.02:
        return df

    if mean_interval > 1.0:
        msg = f"Epochs are larger than 1 minute (mean: {mean_interval:.2f} min). Cannot process data with epochs > 1 minute."
        raise ValueError(msg)

    logger.info(f"Epochs are {mean_interval:.2f} minutes. Collapsing to 1-minute epochs...")

    df[datetime_col] = pd.to_datetime(df[datetime_col])
    df = df.set_index(datetime_col)

    numeric_cols = df.select_dtypes(include=[np.number]).columns
    resampled = df[numeric_cols].resample("1min").sum()

    return resampled.reset_index()
