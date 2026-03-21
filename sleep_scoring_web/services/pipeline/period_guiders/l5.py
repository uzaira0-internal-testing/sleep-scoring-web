"""
L5 (Least Active 5 Hours) period guider.

Finds the 5-hour window with minimum total activity, then traces backward
through classified wake bouts to find where the person actually fell asleep.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.schemas.enums import PeriodGuiderType
from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, EpochSeries, GuideWindow, NapGuideWindow, NonwearPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams

L5_EPOCHS = 300  # 5 hours x 60 epochs/hour
MIDNIGHT_EPOCH = 720  # Epoch index for midnight in a noon-to-noon day (12h x 60)


def _find_lights_out(
    bouts: list[Bout],
    search_from: int,
    min_wake_epochs: int,
) -> int:
    """Walk backward through pre-computed wake bouts to find where
    sustained daytime activity ended.

    Uses the *bouts* list (already computed by the bout detector) instead of
    re-scanning raw scores.  If *search_from* lands inside a wake bout, that
    bout is skipped (contraction, same as nonwear handling).  Then earlier
    bouts are checked in reverse; the first wake bout >= *min_wake_epochs*
    marks the transition.

    Returns the first epoch after that sustained wake bout.
    Falls back to *search_from* if no qualifying wake bout is found.
    """
    for bout in reversed(bouts):
        if bout.state != 0:  # only wake bouts
            continue
        if bout.start_index >= search_from:  # entirely past search point
            continue
        # Bout contains or precedes search_from — check full length
        if bout.length >= min_wake_epochs:
            return bout.end_index + 1
    return search_from


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

        # Penalize nonwear epochs so the L5 window avoids them.
        raw_activity = epochs.activity_counts
        if excluded_nonwear:
            nonwear_set: set[int] = set()
            for nw in excluded_nonwear:
                nonwear_set.update(range(nw.start_index, nw.end_index + 1))
            penalty = (max(raw_activity) if raw_activity else 1) * n + 1
            activity = [penalty if i in nonwear_set else raw_activity[i] for i in range(n)]
        else:
            activity = raw_activity

        # ── Step 1: find the least-active 5-hour window ──
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

        # ── Step 2: trace backward to find lights-out ──
        # Walk backward from L5 start through classified wake bouts, skipping
        # any shorter than bout_merge_gap_minutes.  The first sustained wake
        # bout marks the end of daytime activity; onset_target is placed right
        # after it.
        from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams as DefaultParams

        resolved_params = params or DefaultParams()
        min_wake = resolved_params.bout_merge_gap_minutes // 2

        lights_out = _find_lights_out(bouts, best_start, min_wake)
        l5_end = best_start + L5_EPOCHS - 1

        onset_target = epochs.epoch_times[lights_out]
        offset_target = epochs.epoch_times[l5_end]

        guide = GuideWindow(onset_target=onset_target, offset_target=offset_target, guider=PeriodGuiderType.L5)

        notes.append(
            f"L5 guider: least-active 5h at epoch {best_start}-{l5_end}, "
            f"lights-out {onset_target.strftime('%H:%M')} (epoch {lights_out}), "
            f"offset {offset_target.strftime('%H:%M')} (epoch {l5_end})"
        )
        return guide, [], notes
