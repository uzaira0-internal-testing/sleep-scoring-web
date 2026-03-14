"""
Sadeh sleep scoring algorithm — thin wrapper around the desktop core implementation.

The canonical algorithm lives in sleep_scoring_app.core.algorithms.sleep_wake.sadeh.
This module adapts its pandas-based API to the list-based interface the web app expects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from sleep_scoring_app.core.algorithms.sleep_wake.sadeh import sadeh_score
from sleep_scoring_web.schemas.enums import AlgorithmOutputColumn

if TYPE_CHECKING:
    from collections.abc import Sequence


class SadehAlgorithm:
    """
    Sadeh 1994 sleep scoring algorithm (delegates to desktop core).

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

        # Build minimal DataFrame expected by the desktop core function
        df = pd.DataFrame(
            {
                "datetime": pd.date_range("2000-01-01", periods=n, freq="min"),
                "Axis1": np.array(activity_counts, dtype=np.float64),
            }
        )

        result_df = sadeh_score(df, threshold=self._threshold)
        return result_df[AlgorithmOutputColumn.SLEEP_SCORE].tolist()
