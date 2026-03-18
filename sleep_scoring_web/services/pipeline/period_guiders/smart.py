"""
Smart (composite) period guider.

Delegates to diary guider when diary data is available, otherwise falls back
to L5 guider. Transparent fallback — notes explain which sub-guider was used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams
    from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, DiaryInput, EpochSeries, GuideWindow, NapGuideWindow, NonwearPeriodResult


@register("period_guider", "smart")
class SmartPeriodGuider:
    """Delegates to diary guider if diary available, otherwise L5."""

    @property
    def id(self) -> str:
        return "smart"

    def guide(
        self,
        epochs: EpochSeries,
        classified: ClassifiedEpochs,
        bouts: list[Bout],
        *,
        params: PeriodGuiderParams | None = None,
        diary_data: DiaryInput | None = None,
        excluded_nonwear: list[NonwearPeriodResult] | None = None,
    ) -> tuple[GuideWindow | None, list[NapGuideWindow], list[str]]:
        if diary_data is not None and diary_data.sleep_onset and diary_data.wake_time:
            from sleep_scoring_web.services.pipeline.period_guiders.diary import DiaryPeriodGuider

            guide, naps, notes = DiaryPeriodGuider().guide(epochs, classified, bouts, params=params, diary_data=diary_data, excluded_nonwear=excluded_nonwear)
            notes.insert(0, "Smart guider: using diary")
            return guide, naps, notes

        from sleep_scoring_web.services.pipeline.period_guiders.l5 import L5PeriodGuider

        guide, naps, notes = L5PeriodGuider().guide(epochs, classified, bouts, params=params, excluded_nonwear=excluded_nonwear)
        notes.insert(0, "Smart guider: falling back to L5 (no diary)")
        return guide, naps, notes
