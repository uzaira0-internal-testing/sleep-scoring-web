"""Choi 2011 nonwear detector — wraps existing ChoiAlgorithm."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import DiaryInput, EpochSeries, NonwearPeriodResult, SleepPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import NonwearDetectorParams


@register("nonwear_detector", "choi")
class ChoiNonwearDetector:
    """Choi 2011 nonwear detection (90-min zero-count periods)."""

    @property
    def id(self) -> str:
        return "choi"

    def detect(
        self,
        epochs: EpochSeries,
        *,
        params: NonwearDetectorParams | None = None,
        diary_data: DiaryInput | None = None,
        existing_sleep: list[SleepPeriodResult] | None = None,
    ) -> list[NonwearPeriodResult]:
        from sleep_scoring_web.services.algorithms.choi import ChoiAlgorithm

        if not epochs.activity_counts:
            return []

        choi = ChoiAlgorithm()
        periods = choi.detect(epochs.activity_counts)

        results: list[NonwearPeriodResult] = []
        for i, p in enumerate(periods):
            start_idx = min(p.start_index, epochs.length - 1)
            end_idx = min(p.end_index, epochs.length - 1)
            results.append(
                NonwearPeriodResult(
                    start_index=start_idx,
                    end_index=end_idx,
                    start_timestamp=epochs.timestamps[start_idx],
                    end_timestamp=epochs.timestamps[end_idx],
                    marker_index=i + 1,
                )
            )

        return results
