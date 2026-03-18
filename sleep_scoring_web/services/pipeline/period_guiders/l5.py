"""
L5 (Least Active 5 Hours) period guider.

Finds the 5-hour window with minimum total activity and centers a wide
search window around it. Always succeeds — there's always a least-active period.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sleep_scoring_web.schemas.enums import PeriodGuiderType
from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, EpochSeries, GuideWindow, NapGuideWindow, NonwearPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams

L5_EPOCHS = 300  # 5 hours x 60 epochs/hour
MIDNIGHT_EPOCH = 720  # Epoch index for midnight in a noon-to-noon day (12h x 60)


@register("period_guider", "l5")
class L5PeriodGuider:
    """Guides period construction using the least-active 5-hour window."""

    @property
    def id(self) -> str:
        return "l5"

    def guide(
        self,
        epochs: EpochSeries,
        classified: ClassifiedEpochs,
        bouts: list[Bout],
        *,
        params: PeriodGuiderParams | None = None,
        diary_data: None = None,
        excluded_nonwear: list[NonwearPeriodResult] | None = None,
    ) -> tuple[GuideWindow | None, list[NapGuideWindow], list[str]]:
        notes: list[str] = []
        n = epochs.length

        if n < L5_EPOCHS:
            notes.append(f"L5 guider: only {n} epochs available (need {L5_EPOCHS}) — using full window")
            return (
                GuideWindow(onset_target=epochs.epoch_times[0], offset_target=epochs.epoch_times[-1], guider=PeriodGuiderType.L5),
                [],
                notes,
            )

        # Build activity array — penalize nonwear epochs so the L5 window avoids them.
        # Any window containing a nonwear epoch gets a very high sum, making it
        # uncompetitive with windows of actual low-activity (e.g., real sleep).
        raw_activity = epochs.activity_counts
        if excluded_nonwear:
            nonwear_set: set[int] = set()
            for nw in excluded_nonwear:
                nonwear_set.update(range(nw.start_index, nw.end_index + 1))
            penalty = (max(raw_activity) if raw_activity else 1) * n + 1
            activity = [penalty if i in nonwear_set else raw_activity[i] for i in range(n)]
        else:
            activity = raw_activity
        window_sum = sum(activity[:L5_EPOCHS])
        best_sum = window_sum
        best_starts: list[int] = [0]

        for i in range(1, n - L5_EPOCHS + 1):
            window_sum += activity[i + L5_EPOCHS - 1] - activity[i - 1]
            if window_sum < best_sum:
                best_sum = window_sum
                best_starts = [i]
            elif window_sum == best_sum:
                best_starts.append(i)

        # Tiebreak: prefer window whose midpoint is closest to midnight
        if len(best_starts) > 1:
            best_start = min(best_starts, key=lambda s: abs((s + L5_EPOCHS // 2) - MIDNIGHT_EPOCH))
        else:
            best_start = best_starts[0]

        l5_midpoint = best_start + L5_EPOCHS // 2

        # Determine window size from params
        from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams as DefaultParams

        window_hours = (params or DefaultParams()).l5_window_hours
        half_window = timedelta(hours=window_hours / 2)

        # onset_target = start of the L5 window (where the least-active period begins),
        # NOT midpoint - half_window.  Using the far left edge of the search window as
        # the onset target biases _find_valid_onset_near toward any sleep run that happens
        # to fall partway through the search window (e.g. a brief zero burst 2 h before
        # actual sleep) rather than the actual sleep onset at the L5 window start.
        #
        # offset_target = midpoint + half_window so the offset search covers the full
        # second half of the night.  For L5 the offset is placed at max(valid_offsets)
        # regardless, so offset_target just needs to be comfortably past wake-up.
        midpoint_dt = epochs.epoch_times[l5_midpoint]
        onset_target = epochs.epoch_times[best_start]
        offset_target = midpoint_dt + half_window

        guide = GuideWindow(onset_target=onset_target, offset_target=offset_target, guider=PeriodGuiderType.L5)

        notes.append(
            f"L5 guider: least-active 5h at epoch {best_start}-{best_start + L5_EPOCHS - 1}, midpoint {midpoint_dt.strftime('%H:%M')}, window +/-{window_hours / 2:.0f}h"
        )
        return guide, [], notes
