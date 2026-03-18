"""
Longest sleep bout period guider.

Merges adjacent sleep bouts separated by short wake gaps, picks the longest
merged block, and pads it to form a search window. Can fail if no sleep bouts
are found.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sleep_scoring_web.schemas.enums import PeriodGuiderType
from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, EpochSeries, GuideWindow, NapGuideWindow, NonwearPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams


@register("period_guider", "longest_bout")
class LongestBoutPeriodGuider:
    """Guides period construction using the longest merged sleep bout."""

    @property
    def id(self) -> str:
        return "longest_bout"

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

        # Filter to sleep bouts only
        sleep_bouts = sorted((b for b in bouts if b.state == 1), key=lambda b: b.start_index)
        if not sleep_bouts:
            notes.append("Longest bout guider: no sleep bouts found")
            return None, [], notes

        from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams as DefaultParams

        p = params or DefaultParams()
        merge_gap = p.bout_merge_gap_minutes  # gap in epochs (1-min epochs)

        # Merge adjacent sleep bouts with wake gaps < merge_gap
        merged: list[tuple[int, int]] = [(sleep_bouts[0].start_index, sleep_bouts[0].end_index)]
        for bout in sleep_bouts[1:]:
            prev_start, prev_end = merged[-1]
            gap = bout.start_index - prev_end - 1
            if gap < merge_gap:
                merged[-1] = (prev_start, bout.end_index)
            else:
                merged.append((bout.start_index, bout.end_index))

        # Pick longest merged block
        best_start, best_end = max(merged, key=lambda m: m[1] - m[0])
        block_length = best_end - best_start + 1

        # Pad using datetime arithmetic so guide window isn't clamped to data bounds
        padding_td = timedelta(minutes=p.bout_padding_minutes)
        onset_target = epochs.epoch_times[best_start] - padding_td
        offset_target = epochs.epoch_times[best_end] + padding_td

        guide = GuideWindow(onset_target=onset_target, offset_target=offset_target, guider=PeriodGuiderType.LONGEST_BOUT)

        notes.append(
            f"Longest bout guider: merged block epoch {best_start}-{best_end} ({block_length} epochs), padded +/-{p.bout_padding_minutes}min"
        )
        return guide, [], notes
