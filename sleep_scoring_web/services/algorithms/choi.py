"""
Choi (2011) nonwear detection algorithm — thin wrapper around the desktop core implementation.

The canonical algorithm lives in sleep_scoring_app.core.algorithms.nonwear.choi.
This module adapts its class-based API to the simpler interface the web app expects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sleep_scoring_app.core.algorithms.nonwear.choi import ChoiAlgorithm as CoreChoiAlgorithm

if TYPE_CHECKING:
    from collections.abc import Sequence


@dataclass
class NonwearPeriod:
    """A detected nonwear period (web-facing shape)."""

    start_index: int
    end_index: int
    duration_minutes: int


class ChoiAlgorithm:
    """
    Choi (2011) nonwear detection algorithm (delegates to desktop core).

    Identifies consecutive zero-count periods as potential nonwear.
    Allows small spikes (<=2 minutes) within larger zero periods.
    Validates minimum period length (90 minutes).
    """

    def __init__(self) -> None:
        self._core = CoreChoiAlgorithm()

    def detect(self, activity_counts: Sequence[int | float]) -> list[NonwearPeriod]:
        """Detect nonwear periods from activity data."""
        n = len(activity_counts)
        if n == 0:
            return []

        # Use core's detect_mask (which internally creates dummy timestamps)
        # then reconstruct periods from the mask for the web-facing shape
        mask = self._core.detect_mask(list(activity_counts))

        periods: list[NonwearPeriod] = []
        i = 0
        while i < n:
            if mask[i] == 0:
                i += 1
                continue
            start = i
            while i < n and mask[i] == 1:
                i += 1
            end = i - 1
            periods.append(
                NonwearPeriod(
                    start_index=start,
                    end_index=end,
                    duration_minutes=end - start + 1,
                )
            )

        return periods

    def detect_mask(self, activity_counts: Sequence[int | float]) -> list[int]:
        """Generate per-epoch nonwear mask (0=wearing, 1=not wearing)."""
        if len(activity_counts) == 0:
            return []

        return self._core.detect_mask(list(activity_counts))
