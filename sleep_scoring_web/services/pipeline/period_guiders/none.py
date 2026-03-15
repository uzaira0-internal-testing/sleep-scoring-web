"""Null period guider — pass-through for diary-free pipelines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:  # pragma: no cover
    from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams
    from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, DiaryInput, EpochSeries, GuideWindow, NapGuideWindow


@register("period_guider", "none")
class NullPeriodGuider:
    """No guiding — returns no guide windows."""

    @property
    def id(self) -> str:
        return "none"

    def guide(
        self,
        epochs: EpochSeries,
        classified: ClassifiedEpochs,
        bouts: list[Bout],
        *,
        params: PeriodGuiderParams | None = None,
        diary_data: DiaryInput | None = None,
    ) -> tuple[GuideWindow | None, list[NapGuideWindow], list[str]]:
        return None, [], ["No period guider active (diary-free mode)"]
