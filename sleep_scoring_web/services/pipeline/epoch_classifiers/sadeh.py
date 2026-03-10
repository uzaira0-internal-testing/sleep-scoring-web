"""Sadeh 1994 epoch classifiers — wraps existing SadehAlgorithm."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import ClassifiedEpochs, EpochSeries
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import EpochClassifierParams


class _SadehBase:
    """Base for Sadeh classifiers, parameterized by variant."""

    _variant: str = "actilife"

    @property
    def id(self) -> str:
        return f"sadeh_1994_{self._variant}"

    def classify(
        self,
        epochs: EpochSeries,
        *,
        params: EpochClassifierParams | None = None,
    ) -> ClassifiedEpochs:
        from sleep_scoring_web.services.algorithms.sadeh import SadehAlgorithm

        algo = SadehAlgorithm(variant=self._variant)
        # Apply threshold override if provided via params
        if params and params.threshold is not None:
            algo._threshold = params.threshold
        scores = algo.score(epochs.activity_counts)
        return ClassifiedEpochs(scores=scores, classifier_id=self.id)


@register("epoch_classifier", "sadeh_1994_actilife")
class SadehEpochClassifier(_SadehBase):
    """Sadeh 1994 with ActiLife scaling (threshold=-4.0)."""

    _variant = "actilife"


@register("epoch_classifier", "sadeh_1994_original")
class SadehOriginalEpochClassifier(_SadehBase):
    """Sadeh 1994 with original scaling (threshold=0.0)."""

    _variant = "original"
