"""Cole-Kripke 1992 epoch classifiers — wraps existing ColeKripkeAlgorithm."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import ClassifiedEpochs, EpochSeries
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import EpochClassifierParams


class _ColeKripkeBase:
    """Base for Cole-Kripke classifiers, parameterized by variant."""

    _variant: str = "actilife"

    @property
    def id(self) -> str:
        return f"cole_kripke_1992_{self._variant}"

    def classify(
        self,
        epochs: EpochSeries,
        *,
        params: EpochClassifierParams | None = None,
    ) -> ClassifiedEpochs:
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant=self._variant)
        scores = algo.score(epochs.activity_counts)
        return ClassifiedEpochs(scores=scores, classifier_id=self.id)


@register("epoch_classifier", "cole_kripke_1992_actilife")
class ColeKripkeEpochClassifier(_ColeKripkeBase):
    """Cole-Kripke 1992 with ActiLife scaling."""

    _variant = "actilife"


@register("epoch_classifier", "cole_kripke_1992_original")
class ColeKripkeOriginalEpochClassifier(_ColeKripkeBase):
    """Cole-Kripke 1992 with original scaling."""

    _variant = "original"
