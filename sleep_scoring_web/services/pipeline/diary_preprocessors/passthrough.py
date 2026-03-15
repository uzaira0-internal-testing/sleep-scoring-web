"""Passthrough diary preprocessor — no-op for diary-free pipelines."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import DiaryInput, RawDiaryInput
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:  # pragma: no cover
    from sleep_scoring_web.services.pipeline.params import DiaryPreprocessorParams


@register("diary_preprocessor", "passthrough")
class PassthroughDiaryPreprocessor:
    """Returns empty diary data — used when no diary is available."""

    @property
    def id(self) -> str:
        return "passthrough"

    def preprocess(
        self,
        raw_diary: RawDiaryInput,
        data_window: tuple[float, float],
        *,
        params: DiaryPreprocessorParams | None = None,
    ) -> tuple[DiaryInput, list[str]]:
        return DiaryInput(), []
