"""
Choi (2011) nonwear detection algorithm — optimized implementation.

Implements the Choi algorithm directly, bypassing the desktop core's
detect_mask() which creates 1440 dummy datetime objects per call.
The algorithm logic is identical: consecutive zero-count periods with
spike tolerance, minimum period length of 90 minutes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Sequence

# Published constants from Choi et al. (2011)
_MIN_PERIOD = 90
_SPIKE_TOL = 2
_SMALL_WINDOW = 30


@dataclass
class NonwearPeriod:
    """A detected nonwear period (web-facing shape)."""

    start_index: int
    end_index: int
    duration_minutes: int


def _choi_mask_fast(counts: np.ndarray) -> list[int]:
    """Compute Choi nonwear mask directly (no dummy timestamps)."""
    n = len(counts)
    mask = [0] * n
    i = 0

    while i < n:
        if counts[i] > 0:
            i += 1
            continue

        start_idx = i
        end_idx = i
        cont = i

        while cont < n:
            if counts[cont] == 0:
                end_idx = cont
                cont += 1
                continue

            w_start = max(0, cont - _SMALL_WINDOW)
            w_end = min(n, cont + _SMALL_WINDOW)
            nonzero = int(np.sum(counts[w_start:w_end] > 0))

            if nonzero > _SPIKE_TOL:
                break

            cont += 1

        if end_idx - start_idx + 1 >= _MIN_PERIOD:
            for j in range(start_idx, end_idx + 1):
                mask[j] = 1
            i = end_idx + 1
        else:
            i += 1

    return mask


class ChoiAlgorithm:
    """
    Choi (2011) nonwear detection — fast numpy-only path.

    Identifies consecutive zero-count periods as potential nonwear.
    Allows small spikes (<=2 minutes) within larger zero periods.
    Validates minimum period length (90 minutes).
    """

    def detect(self, activity_counts: Sequence[int | float]) -> list[NonwearPeriod]:
        """Detect nonwear periods from activity data."""
        n = len(activity_counts)
        if n == 0:
            return []

        mask = self.detect_mask(activity_counts)

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

        counts = np.asarray(activity_counts, dtype=np.float64)
        return _choi_mask_fast(counts)
