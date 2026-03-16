"""
Sadeh sleep scoring algorithm — optimized numpy-only implementation.

Computes the Sadeh (1994) algorithm directly on arrays, bypassing the
desktop core's pandas-based API.  This eliminates DataFrame construction,
datetime column search, epoch validation, and an extra df.copy() that the
core wrapper requires — yielding a significant speedup for the web API
where input is already validated 1-minute epoch data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

# Published constants from Sadeh et al. (1994)
_WINDOW_SIZE = 11
_ACTIVITY_CAP = 300
_NATS_MIN = 50
_NATS_MAX = 100
_COEFF_A = 7.601
_COEFF_B = 0.065
_COEFF_C = 1.08
_COEFF_D = 0.056
_COEFF_E = 0.703


def _sadeh_score_fast(activity: np.ndarray, threshold: float) -> list[int]:
    """Compute Sadeh scores directly on a numpy array (no pandas)."""
    n = len(activity)
    capped = np.minimum(activity, _ACTIVITY_CAP)
    padded = np.pad(capped, pad_width=5, mode="constant", constant_values=0)

    # Vectorised rolling std (current + 5 preceding = 6-epoch backward window, ddof=1)
    # Build a (n, 6) matrix of sd windows, then compute std along axis=1
    sd_indices = np.arange(n)[:, None] + np.arange(6)[None, :]  # (n, 6) into padded
    sd_windows = padded[sd_indices]
    rolling_sds = np.std(sd_windows, axis=1, ddof=1)

    # Vectorised 11-epoch forward windows for AVG and NATS
    avg_indices = np.arange(n)[:, None] + np.arange(_WINDOW_SIZE)[None, :]
    windows = padded[avg_indices]  # (n, 11)
    avg = np.mean(windows, axis=1)
    nats = np.sum((windows >= _NATS_MIN) & (windows < _NATS_MAX), axis=1)

    lg = np.log(capped + 1)

    ps = _COEFF_A - (_COEFF_B * avg) - (_COEFF_C * nats) - (_COEFF_D * rolling_sds) - (_COEFF_E * lg)
    return (ps > threshold).astype(int).tolist()


class SadehAlgorithm:
    """
    Sadeh 1994 sleep scoring algorithm — fast numpy-only path.

    Classifies each epoch as sleep (1) or wake (0) based on activity counts
    from the surrounding 11-minute window.
    """

    def __init__(self, variant: str = "actilife") -> None:
        self.variant = variant
        self._threshold = -4.0 if variant == "actilife" else 0.0

    def score(self, activity_counts: Sequence[int | float]) -> list[int]:
        """Score epochs as sleep (1) or wake (0)."""
        n = len(activity_counts)
        if n == 0:
            return []
        activity = np.asarray(activity_counts, dtype=np.float64)
        return _sadeh_score_fast(activity, self._threshold)
