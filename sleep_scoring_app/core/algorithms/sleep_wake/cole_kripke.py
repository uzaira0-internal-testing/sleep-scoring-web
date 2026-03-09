"""
Cole-Kripke (1992) sleep scoring algorithm - Framework-agnostic implementation.

This module implements the Cole-Kripke algorithm for classifying minute-by-minute
activity data as sleep or wake. Two variants are supported:

    1. Original (1992): As published in Cole et al. (1992) paper
    2. ActiLife: As implemented in ActiGraph's ActiLife software

References:
    Cole, R. J., Kripke, D. F., Gruen, W., Mullaney, D. J., & Gillin, J. C. (1992).
    Automatic sleep/wake identification from wrist activity. Sleep, 15(5), 461-469.

    ActiGraph's Implementation:
    https://actigraphcorp.my.site.com/support/s/article/Where-can-I-find-documentation-for-the-Sadeh-and-Cole-Kripke-algorithms

Algorithm Details (ActiLife Implementation):
    - Uses y-axis epoch data
    - Divides count values by 100
    - Caps scaled values over 300 to 300
    - Uses a 7-minute sliding window (4 previous + current + 2 future epochs)
    - Missing epochs (at boundaries) are treated as zero
    - Formula: 0.001 * (106*A(t-4) + 54*A(t-3) + 58*A(t-2) + 76*A(t-1) + 230*A(t) + 74*A(t+1) + 67*A(t+2))
    - Classification: result < 1 = Sleep (1), otherwise Wake (0)
    - ALWAYS uses Axis1 column (hardcoded in the algorithm)

Coefficients (1-minute epochs):
    - P (scaling factor): 0.001
    - W-4 (lag 4): 106
    - W-3 (lag 3): 54
    - W-2 (lag 2): 58
    - W-1 (lag 1): 76
    - W0 (current): 230
    - W+1 (lead 1): 74
    - W+2 (lead 2): 67

Variants:
    - Original (1992): Uses activity data directly without pre-scaling (legacy behavior)
    - ActiLife: Pre-scales activity by /100 and caps at 300 before applying algorithm

"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from sleep_scoring_app.core.constants import ActivityDataPreference, AlgorithmOutputColumn, AlgorithmType, DefaultColumn
from sleep_scoring_app.core.pipeline.types import AlgorithmDataRequirement

from .utils import find_datetime_column, scale_counts, validate_and_collapse_epochs

if TYPE_CHECKING:
    import pandas as pd

logger = logging.getLogger(__name__)

# Cole-Kripke algorithm constants (1-minute epochs)
WINDOW_SIZE: int = 7  # 4 previous + current + 2 future
ACTIVITY_SCALE_ACTILIFE: float = 100.0  # Divide activity counts by this (ActiLife variant)
ACTIVITY_CAP_ACTILIFE: float = 300.0  # Maximum scaled activity value (ActiLife variant)
THRESHOLD: float = 1.0  # Sleep/wake classification threshold

# Scaling factor for the weighted sum
SCALING_FACTOR: float = 0.001

# Coefficients for the weighted sum (1-minute epochs)
# From Cole et al. (1992) and validated by actigraph.sleepr R package
COEF_LAG4: int = 106  # A(t-4)
COEF_LAG3: int = 54  # A(t-3)
COEF_LAG2: int = 58  # A(t-2)
COEF_LAG1: int = 76  # A(t-1)
COEF_CURRENT: int = 230  # A(t)
COEF_LEAD1: int = 74  # A(t+1)
COEF_LEAD2: int = 67  # A(t+2)


def cole_kripke_score(
    df: pd.DataFrame, use_actilife_scaling: bool = True, enable_count_scaling: bool = False, scale_factor: float = 100.0, count_cap: float = 300.0
) -> pd.DataFrame:
    """
    Apply Cole-Kripke (1992) sleep scoring algorithm to activity data.

    Three variants are supported:
    - ActiLife (default): Pre-scales activity by dividing by 100 and caps at 300
    - Original: Uses raw activity counts without pre-scaling
    - Count-Scaled: Custom scaling for modern accelerometers (enable_count_scaling=True)

    All variants use the same 7-minute sliding window with weighted coefficients.

    Note: use_actilife_scaling and enable_count_scaling are mutually exclusive.
    If enable_count_scaling=True, use_actilife_scaling is ignored.

    Args:
        df: DataFrame with datetime column and 'Axis1' activity column
        use_actilife_scaling: If True (default), use ActiLife's pre-scaling (/100, cap 300).
                              If False, use raw activity counts (original paper behavior).
                              Ignored if enable_count_scaling=True.
        enable_count_scaling: Apply custom count scaling for modern accelerometers (default: False)
        scale_factor: Division factor for count scaling (default: 100.0)
        count_cap: Maximum value after scaling (default: 300.0)

    Returns:
        Original DataFrame with new 'Sleep Score' column appended (1=sleep, 0=wake)

    Raises:
        ValueError: If epochs are larger than 1 minute or required columns missing

    Validation:
        - Finds datetime/date+time columns automatically
        - Verifies 1-minute epochs (+/-1 second tolerance)
        - Collapses to 1-minute if epochs < 1 minute
        - Raises error if epochs > 1 minute

    Example:
        >>> import pandas as pd
        >>> from sleep_scoring_app.core.algorithms import cole_kripke_score
        >>> df = pd.read_csv('activity.csv')
        >>> df.head()
           datetime             Axis1
        0  2024-01-01 00:00:00  45
        1  2024-01-01 00:01:00  32
        2  2024-01-01 00:02:00  0
        >>> df = cole_kripke_score(df)  # ActiLife variant (default)
        >>> df.head()
           datetime             Axis1  Sleep Score
        0  2024-01-01 00:00:00  45     1
        1  2024-01-01 00:01:00  32     1
        2  2024-01-01 00:02:00  0      1

    """
    if df is None or len(df) == 0:
        msg = "DataFrame cannot be None or empty"
        raise ValueError(msg)

    datetime_col = find_datetime_column(df)

    df = validate_and_collapse_epochs(df, datetime_col)

    if DefaultColumn.AXIS_Y not in df.columns:
        msg = f"DataFrame must contain '{DefaultColumn.AXIS_Y}' column. Cole-Kripke algorithm ALWAYS uses Axis1."
        raise ValueError(msg)

    activity_data = df[DefaultColumn.AXIS_Y].to_numpy(dtype=np.float64)

    if np.any(np.isnan(activity_data)):
        msg = "Axis1 column contains NaN (Not a Number) values"
        raise ValueError(msg)

    if np.any(np.isinf(activity_data)):
        msg = "Axis1 column contains infinite values"
        raise ValueError(msg)

    if np.any(activity_data < 0):
        negative_indices = np.where(activity_data < 0)[0]
        msg = f"Axis1 column contains negative values at indices: {negative_indices[:10].tolist()}"
        raise ValueError(msg)

    # Determine variant and apply appropriate scaling
    if enable_count_scaling:
        variant_name = "Count-Scaled"
        logger.debug(f"Running Cole-Kripke ({variant_name}) algorithm on {len(activity_data)} epochs")
        logger.info(f"Applying count scaling: scale_factor={scale_factor}, cap={count_cap}")
        scaled_activity = scale_counts(activity_data, scale_factor=scale_factor, cap=count_cap)
    elif use_actilife_scaling:
        variant_name = "ActiLife"
        logger.debug(f"Running Cole-Kripke ({variant_name}) algorithm on {len(activity_data)} epochs")
        # ActiLife variant: divide by 100 and cap at 300
        scaled_activity = np.minimum(activity_data / ACTIVITY_SCALE_ACTILIFE, ACTIVITY_CAP_ACTILIFE)
    else:
        variant_name = "Original"
        logger.debug(f"Running Cole-Kripke ({variant_name}) algorithm on {len(activity_data)} epochs")
        # Original variant: use raw activity counts
        scaled_activity = activity_data.copy()

    sleep_wake_scores = _calculate_cole_kripke_scores(scaled_activity)

    logger.debug(f"Cole-Kripke ({variant_name}) algorithm completed successfully for {len(activity_data)} epochs")

    result_df = df.copy()
    result_df[AlgorithmOutputColumn.SLEEP_SCORE] = sleep_wake_scores

    return result_df


def _calculate_cole_kripke_scores(activity: np.ndarray) -> np.ndarray:
    """
    Calculate Cole-Kripke sleep/wake scores for activity data.

    This is the core algorithm that applies the weighted sum formula.
    The input should already be pre-processed (scaled/capped for ActiLife variant,
    or raw counts for Original variant).

    Args:
        activity: Array of activity counts (pre-processed based on variant)

    Returns:
        Array of sleep/wake classifications (1=sleep, 0=wake)

    """
    n = len(activity)
    sleep_wake_scores = np.zeros(n, dtype=int)

    # Pad activity with zeros for boundary handling
    # 4 zeros at start (for lag), 2 zeros at end (for lead)
    padded_activity = np.pad(activity, pad_width=(4, 2), mode="constant", constant_values=0)

    # Coefficients array for vectorized multiplication
    coefficients = np.array([COEF_LAG4, COEF_LAG3, COEF_LAG2, COEF_LAG1, COEF_CURRENT, COEF_LEAD1, COEF_LEAD2])

    for i in range(n):
        # Extract 7-epoch window (4 lag + current + 2 lead)
        window_start = i  # Due to padding of 4, position i in padded = lag 4
        window = padded_activity[window_start : window_start + WINDOW_SIZE]

        # Calculate sleep index
        weighted_sum = np.dot(coefficients, window)
        sleep_index = SCALING_FACTOR * weighted_sum

        # Classify: SI < 1.0 = Sleep (1), SI >= 1.0 = Wake (0)
        sleep_wake_scores[i] = 1 if sleep_index < THRESHOLD else 0

    return sleep_wake_scores


def score_activity_cole_kripke(
    activity_data: list[float] | np.ndarray,
    use_actilife_scaling: bool = True,
    enable_count_scaling: bool = False,
    scale_factor: float = 100.0,
    count_cap: float = 300.0,
) -> list[int]:
    """
    Score activity data using Cole-Kripke algorithm (convenience function).

    Args:
        activity_data: List or array of Axis1 activity count values
        use_actilife_scaling: If True (default), use ActiLife's pre-scaling (/100, cap 300).
                              If False, use raw activity counts (original paper behavior).
                              Ignored if enable_count_scaling=True.
        enable_count_scaling: Apply custom count scaling for modern accelerometers (default: False)
        scale_factor: Division factor for count scaling (default: 100.0)
        count_cap: Maximum value after scaling (default: 300.0)

    Returns:
        List of sleep/wake classifications (1=sleep, 0=wake)

    Example:
        >>> from sleep_scoring_app.core.algorithms import score_activity_cole_kripke
        >>> activity_counts = [45, 32, 0, 12, 5, ...]
        >>> sleep_scores = score_activity_cole_kripke(activity_counts)  # ActiLife variant
        >>> sleep_scores
        [1, 1, 1, 1, 1, ...]

    """
    if activity_data is None:
        msg = "activity_data cannot be None"
        raise ValueError(msg)

    if len(activity_data) == 0:
        logger.debug("Empty activity_data provided to Cole-Kripke algorithm")
        return []

    try:
        activity_array = np.array(activity_data, dtype=np.float64)
    except (ValueError, TypeError) as e:
        msg = f"activity_data contains non-numeric values: {e}"
        raise ValueError(msg) from e

    if np.any(np.isnan(activity_array)):
        msg = "activity_data contains NaN (Not a Number) values"
        raise ValueError(msg)

    if np.any(np.isinf(activity_array)):
        msg = "activity_data contains infinite values"
        raise ValueError(msg)

    if np.any(activity_array < 0):
        negative_indices = np.where(activity_array < 0)[0]
        msg = f"activity_data contains negative values at indices: {negative_indices[:10].tolist()}"
        raise ValueError(msg)

    # Determine variant and apply appropriate scaling
    if enable_count_scaling:
        variant_name = "Count-Scaled"
        logger.debug(f"Running Cole-Kripke ({variant_name}) algorithm on {len(activity_array)} epochs")
        logger.info(f"Applying count scaling: scale_factor={scale_factor}, cap={count_cap}")
        scaled_activity = scale_counts(activity_array, scale_factor=scale_factor, cap=count_cap)
    elif use_actilife_scaling:
        variant_name = "ActiLife"
        logger.debug(f"Running Cole-Kripke ({variant_name}) algorithm on {len(activity_array)} epochs")
        # ActiLife variant: divide by 100 and cap at 300
        scaled_activity = np.minimum(activity_array / ACTIVITY_SCALE_ACTILIFE, ACTIVITY_CAP_ACTILIFE)
    else:
        variant_name = "Original"
        logger.debug(f"Running Cole-Kripke ({variant_name}) algorithm on {len(activity_array)} epochs")
        # Original variant: use raw activity counts
        scaled_activity = activity_array.copy()

    sleep_wake_scores = _calculate_cole_kripke_scores(scaled_activity)

    logger.debug(f"Cole-Kripke ({variant_name}) algorithm completed successfully for {len(activity_array)} epochs")

    return sleep_wake_scores.tolist()


class ColeKripkeAlgorithm:
    """
    Cole-Kripke (1992) sleep scoring algorithm - Protocol implementation.

    This class implements the SleepScoringAlgorithm protocol for dependency injection.
    The original function-based API (cole_kripke_score, score_activity_cole_kripke) is
    preserved for backward compatibility.

    The Cole-Kripke algorithm uses a 7-minute sliding window with weighted coefficients
    to classify each epoch as sleep or wake based on activity counts. It ALWAYS uses
    the vertical axis (Axis1/axis_y) regardless of configuration.

    Two variants are supported:
        - Original (1992): Uses raw activity counts as published in the paper
        - ActiLife: Pre-scales activity by /100 and caps at 300 (ActiGraph's implementation)

    Parameters
    ----------
        variant_name: Algorithm variant ("original" or "actilife")
            - "original": Use raw activity counts (as published in Cole et al. 1992)
            - "actilife": Pre-scale by /100 and cap at 300 (ActiGraph's implementation)

    Example:
        >>> from sleep_scoring_app.core.algorithms import ColeKripkeAlgorithm
        >>>
        >>> # Create ActiLife variant (default-like behavior via factory)
        >>> algorithm = ColeKripkeAlgorithm(variant_name="actilife")
        >>> algorithm.name
        'Cole-Kripke (1992) ActiLife'
        >>>
        >>> # Create Original variant
        >>> algorithm = ColeKripkeAlgorithm(variant_name="original")
        >>> algorithm.name
        'Cole-Kripke (1992) Original'
        >>>
        >>> # Score DataFrame
        >>> df = algorithm.score(activity_df)

    References
    ----------
        Cole, R. J., Kripke, D. F., Gruen, W., Mullaney, D. J., & Gillin, J. C. (1992).
        Automatic sleep/wake identification from wrist activity. Sleep, 15(5), 461-469.

        ActiGraph Cole-Kripke Implementation:
        https://actigraphcorp.my.site.com/support/s/article/Where-can-I-find-documentation-for-the-Sadeh-and-Cole-Kripke-algorithms

    """

    def __init__(
        self, variant_name: str = "actilife", enable_count_scaling: bool = False, scale_factor: float = 100.0, count_cap: float = 300.0
    ) -> None:
        """
        Initialize Cole-Kripke algorithm with specified variant.

        Args:
            variant_name: Algorithm variant ("original", "actilife", or "count_scaled")
                - "original": Use raw activity counts (as published)
                - "actilife": Pre-scale by /100 and cap at 300 (default)
                - "count_scaled": Custom scaling for modern accelerometers
            enable_count_scaling: Apply custom count scaling for modern accelerometers (default: False)
            scale_factor: Division factor for count scaling (default: 100.0)
            count_cap: Maximum value after scaling (default: 300.0)

        """
        self._variant_name = variant_name.lower()
        self._enable_count_scaling = enable_count_scaling or self._variant_name == "count_scaled"
        self._scale_factor = scale_factor
        self._count_cap = count_cap
        self._use_actilife_scaling = self._variant_name == "actilife" and not self._enable_count_scaling

        self._parameters = {
            "window_size": WINDOW_SIZE,
            "threshold": THRESHOLD,
            "scaling_factor": SCALING_FACTOR,
            "coef_lag4": COEF_LAG4,
            "coef_lag3": COEF_LAG3,
            "coef_lag2": COEF_LAG2,
            "coef_lag1": COEF_LAG1,
            "coef_current": COEF_CURRENT,
            "coef_lead1": COEF_LEAD1,
            "coef_lead2": COEF_LEAD2,
            "variant": self._variant_name,
            "enable_count_scaling": self._enable_count_scaling,
        }

        # Add scaling parameters based on variant
        if self._enable_count_scaling:
            self._parameters["scale_factor"] = scale_factor
            self._parameters["count_cap"] = count_cap
        elif self._use_actilife_scaling:
            self._parameters["activity_scale"] = ACTIVITY_SCALE_ACTILIFE
            self._parameters["activity_cap"] = ACTIVITY_CAP_ACTILIFE

    @property
    def name(self) -> str:
        """Algorithm name for display."""
        if self._variant_name == "count_scaled" or self._enable_count_scaling:
            return "Cole-Kripke (1992) Count-Scaled"
        if self._variant_name == "original":
            return "Cole-Kripke (1992) Original"
        return "Cole-Kripke (1992) ActiLife"

    @property
    def identifier(self) -> str:
        """Unique algorithm identifier."""
        if self._variant_name == "count_scaled" or self._enable_count_scaling:
            return "cole_kripke_1992_count_scaled"  # Disabled variant, no enum defined
        if self._variant_name == "original":
            return AlgorithmType.COLE_KRIPKE_1992_ORIGINAL
        return AlgorithmType.COLE_KRIPKE_1992_ACTILIFE

    @property
    def requires_axis(self) -> str:
        """Required accelerometer axis - always axis_y (vertical) for Cole-Kripke."""
        return ActivityDataPreference.AXIS_Y

    @property
    def data_requirement(self) -> AlgorithmDataRequirement:
        """Data requirement - Cole-Kripke requires 60-second epoch count data."""
        return AlgorithmDataRequirement.EPOCH_DATA

    def score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Score sleep/wake using Cole-Kripke algorithm.

        Args:
            df: DataFrame with datetime column and 'Axis1' activity column

        Returns:
            Original DataFrame with added 'Sleep Score' column (1=sleep, 0=wake)

        """
        return cole_kripke_score(
            df,
            use_actilife_scaling=self._use_actilife_scaling,
            enable_count_scaling=self._enable_count_scaling,
            scale_factor=self._scale_factor,
            count_cap=self._count_cap,
        )

    def get_parameters(self) -> dict[str, float | int | str]:
        """
        Get current algorithm parameters.

        Returns:
            Dictionary of parameter names and values (all read-only)

        """
        return self._parameters.copy()

    def set_parameters(self, **kwargs: float) -> None:
        """
        Update algorithm parameters.

        Cole-Kripke algorithm has NO configurable parameters. All values are
        fixed from the published paper and cannot be changed.

        Args:
            **kwargs: Parameter name-value pairs (all ignored with warning)

        """
        if kwargs:
            logger.warning(
                "Cole-Kripke algorithm has no configurable parameters. All values are fixed from the published paper. Ignoring parameters: %s",
                list(kwargs.keys()),
            )
