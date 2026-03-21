"""
Flat-activity nonwear detector.

Detects periods of sustained zero activity — the signature of a device
removed and placed on a surface (sudden drop to exactly 0, stays flat,
then sudden resumption). Catches shorter periods that Choi 2011 misses
(Choi requires ≥90 min; this defaults to ≥60 min).

A mid-recording run is only flagged as nonwear if activity RESUMES strongly
after the run ends — this distinguishes device-removal (activity comes back)
from actual sleep (activity stays low indefinitely).  A run that reaches the
END of the data is always flagged as nonwear (device removed and never put
back on).  A run followed only by near-zero values with no resumption and
not at the end of data is treated as sleep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import DiaryInput, EpochSeries, NonwearPeriodResult, SleepPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import NonwearDetectorParams


@register("nonwear_detector", "flat_activity")
class FlatActivityNonwearDetector:
    """
    Detects nonwear as sustained flat-zero runs that are followed by a
    strong resumption of activity.

    Two criteria must both be met:
    1. Run of zero (or near-zero) activity lasting ≥ flat_activity_min_minutes.
    2. Within flat_activity_resumption_window_epochs after the run ends,
       activity exceeds flat_activity_resumption_threshold — confirming the
       device was picked up, not that the person fell asleep.

    This correctly excludes overnight sleep periods (activity never strongly
    resumes) while catching midday device-removal periods (activity comes
    back quickly to normal levels).
    """

    @property
    def id(self) -> str:
        return "flat_activity"

    def detect(
        self,
        epochs: EpochSeries,
        *,
        params: NonwearDetectorParams | None = None,
        diary_data: DiaryInput | None = None,
        existing_sleep: list[SleepPeriodResult] | None = None,
    ) -> list[NonwearPeriodResult]:
        if params is None:
            from sleep_scoring_web.services.pipeline.params import NonwearDetectorParams as NWParams

            params = NWParams()

        activity = epochs.activity_counts
        threshold = params.flat_activity_threshold
        min_epochs = params.flat_activity_min_minutes * 60 // params.epoch_length_seconds
        resumption_window = params.flat_activity_resumption_window_epochs
        resumption_threshold = params.flat_activity_resumption_threshold

        results: list[NonwearPeriodResult] = []
        marker_index = 1
        i = 0
        while i < len(activity):
            if activity[i] <= threshold:
                run_start = i
                while i < len(activity) and activity[i] <= threshold:
                    i += 1
                run_end = i - 1
                run_length = run_end - run_start + 1

                if run_length < min_epochs:
                    continue

                # Require strong resumption after the run — confirms device was picked
                # up, not that the person fell asleep. Check the next
                # resumption_window epochs for activity above resumption_threshold.
                # Exception: a run that reaches the END of the data is always
                # nonwear — the device was removed and never put back on.
                at_end_of_data = i >= len(activity)
                if not at_end_of_data:
                    window_end = min(i + resumption_window, len(activity))
                    resumes = any(activity[j] >= resumption_threshold for j in range(i, window_end))
                    if not resumes:
                        continue

                results.append(
                    NonwearPeriodResult(
                        start_index=run_start,
                        end_index=run_end,
                        start_timestamp=epochs.timestamps[run_start],
                        end_timestamp=epochs.timestamps[run_end],
                        marker_index=marker_index,
                    )
                )
                marker_index += 1
            else:
                i += 1

        return results
