"""
Consecutive-run bout detector.

Single-pass scan of classified epochs to extract contiguous sleep/wake bouts.
Replaces the 6+ redundant scans in the current marker_placement.py code.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import BoutDetectorParams


@register("bout_detector", "consecutive_run")
class ConsecutiveRunBoutDetector:
    """Extracts contiguous same-state runs from classified epochs."""

    @property
    def id(self) -> str:
        return "consecutive_run"

    def detect_bouts(
        self,
        classified: ClassifiedEpochs,
        *,
        params: BoutDetectorParams | None = None,
    ) -> list[Bout]:
        scores = classified.scores
        if not scores:
            return []

        bouts: list[Bout] = []
        i = 0
        while i < len(scores):
            state = scores[i]
            run_start = i
            while i < len(scores) and scores[i] == state:
                i += 1
            bouts.append(
                Bout(
                    start_index=run_start,
                    end_index=i - 1,
                    state=state,
                    length=i - run_start,
                )
            )

        return bouts
