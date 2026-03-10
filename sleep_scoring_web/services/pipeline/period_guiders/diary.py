"""
Diary-based period guider.

Uses preprocessed diary times to construct guide windows for main sleep and naps.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, DiaryInput, EpochSeries, GuideWindow, NapGuideWindow
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams


@register("period_guider", "diary")
class DiaryPeriodGuider:
    """Guides period construction using diary onset/wake/nap times."""

    @property
    def id(self) -> str:
        return "diary"

    def guide(
        self,
        epochs: EpochSeries,
        classified: ClassifiedEpochs,
        bouts: list[Bout],
        *,
        params: PeriodGuiderParams | None = None,
        diary_data: DiaryInput | None = None,
    ) -> tuple[GuideWindow | None, list[NapGuideWindow], list[str]]:
        notes: list[str] = []

        if diary_data is None:
            notes.append("No diary data for this date — auto-score requires diary")
            return None, [], notes

        # Main sleep guide window
        main_guide: GuideWindow | None = None
        if diary_data.sleep_onset and diary_data.wake_time:
            main_guide = GuideWindow(
                onset_target=diary_data.sleep_onset,
                offset_target=diary_data.wake_time,
                in_bed_time=diary_data.in_bed_time,
            )
        elif not diary_data.sleep_onset and not diary_data.wake_time:
            notes.append("Diary exists but no onset/wake times — auto-score requires diary times")
        else:
            notes.append("Diary incomplete (missing onset or wake) — auto-score requires both")

        # Nap guide windows
        nap_guides: list[NapGuideWindow] = []
        for nap_start, nap_end in diary_data.nap_periods:
            nap_guides.append(
                NapGuideWindow(
                    start_target=nap_start,
                    end_target=nap_end,
                )
            )

        return main_guide, nap_guides, notes
