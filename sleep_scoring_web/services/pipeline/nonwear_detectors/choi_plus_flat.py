"""
Choi + flat-activity composite nonwear detector.

Runs Choi 2011 and FlatActivityNonwearDetector, merges overlapping
results, and renumbers marker indices. Catches both the ≥90-min periods
that Choi handles and the shorter flat-zero periods that Choi misses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import DiaryInput, EpochSeries, NonwearPeriodResult, SleepPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import NonwearDetectorParams


@register("nonwear_detector", "choi_plus_flat")
class ChoiPlusFlatNonwearDetector:
    """Runs Choi 2011 and flat-activity detector, merges overlapping results."""

    @property
    def id(self) -> str:
        return "choi_plus_flat"

    def detect(
        self,
        epochs: EpochSeries,
        *,
        params: NonwearDetectorParams | None = None,
        diary_data: DiaryInput | None = None,
        existing_sleep: list[SleepPeriodResult] | None = None,
    ) -> list[NonwearPeriodResult]:
        from sleep_scoring_web.services.pipeline.nonwear_detectors.choi import ChoiNonwearDetector
        from sleep_scoring_web.services.pipeline.nonwear_detectors.flat_activity import FlatActivityNonwearDetector

        choi = ChoiNonwearDetector().detect(epochs, params=params, diary_data=diary_data, existing_sleep=existing_sleep)
        flat = FlatActivityNonwearDetector().detect(epochs, params=params, diary_data=diary_data, existing_sleep=existing_sleep)

        # Sort by start index, merge overlapping/adjacent periods
        combined = sorted(choi + flat, key=lambda r: r.start_index)
        merged: list[NonwearPeriodResult] = []
        for r in combined:
            if merged and r.start_index <= merged[-1].end_index + 1:
                prev = merged[-1]
                merged[-1] = NonwearPeriodResult(
                    start_index=prev.start_index,
                    end_index=max(prev.end_index, r.end_index),
                    start_timestamp=prev.start_timestamp,
                    end_timestamp=max(prev.end_timestamp, r.end_timestamp),
                    marker_index=prev.marker_index,
                )
            else:
                merged.append(r)

        return [
            NonwearPeriodResult(
                start_index=r.start_index,
                end_index=r.end_index,
                start_timestamp=r.start_timestamp,
                end_timestamp=r.end_timestamp,
                marker_index=i + 1,
            )
            for i, r in enumerate(merged)
        ]
