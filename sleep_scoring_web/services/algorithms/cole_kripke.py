"""
Cole-Kripke (1992) sleep scoring algorithm — thin wrapper around the desktop core implementation.

The canonical algorithm lives in sleep_scoring_app.core.algorithms.sleep_wake.cole_kripke.
This module adapts its list-based API to the interface the web app expects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_app.core.algorithms.sleep_wake.cole_kripke import score_activity_cole_kripke

if TYPE_CHECKING:  # pragma: no cover
    from collections.abc import Sequence


class ColeKripkeAlgorithm:
    """
    Cole-Kripke 1992 sleep scoring algorithm (delegates to desktop core).

    Classifies each epoch as sleep (1) or wake (0) based on a 7-minute
    sliding window with weighted coefficients.
    """

    def __init__(self, variant: str = "actilife") -> None:
        self.variant = variant.lower()
        self._use_actilife_scaling = self.variant == "actilife"

    def score(self, activity_counts: Sequence[int | float]) -> list[int]:
        """Score epochs as sleep (1) or wake (0)."""
        if len(activity_counts) == 0:
            return []

        return score_activity_cole_kripke(
            list(activity_counts),
            use_actilife_scaling=self._use_actilife_scaling,
        )
