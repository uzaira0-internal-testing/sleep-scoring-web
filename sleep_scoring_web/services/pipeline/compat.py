"""
Backward-compatibility bridge between legacy run_auto_scoring() and the pipeline.

Provides run_via_pipeline() which accepts the same inputs as the legacy
function but routes through the pipeline orchestrator.
"""

from __future__ import annotations

from typing import Any

from .params import PipelineParams
from .protocols import RawDiaryInput


def run_via_pipeline(
    timestamps: list[float],
    activity_counts: list[float],
    *,
    algorithm: str = "sadeh_1994_actilife",
    diary_bed_time: str | None = None,
    diary_onset_time: str | None = None,
    diary_wake_time: str | None = None,
    diary_naps: list[tuple[str | None, str | None]] | None = None,
    diary_nonwear: list[tuple[str | None, str | None]] | None = None,
    analysis_date: str | None = None,
    epoch_length_seconds: int = 60,
    onset_min_consecutive_sleep: int = 3,
    offset_min_consecutive_minutes: int = 5,
    include_diary: bool = True,
) -> dict[str, Any]:
    """
    Run the full pipeline and return legacy-format dict.

    Unlike run_auto_scoring(), this includes epoch classification
    (the caller does NOT need to pre-compute sleep_scores).
    """
    from .orchestrator import ScoringPipeline
    from .params import PeriodConstructorParams

    params = PipelineParams.from_legacy(
        algorithm=algorithm,
        onset_epochs=onset_min_consecutive_sleep,
        offset_minutes=offset_min_consecutive_minutes,
        include_diary=include_diary,
    )
    # Override epoch_length if non-default, preserving all other fields
    if epoch_length_seconds != 60:
        from dataclasses import replace

        params = replace(
            params,
            period_constructor_params=PeriodConstructorParams(
                onset_min_consecutive_sleep=onset_min_consecutive_sleep,
                offset_min_consecutive_minutes=offset_min_consecutive_minutes,
                epoch_length_seconds=epoch_length_seconds,
            ),
        )

    raw_diary: RawDiaryInput | None = None
    if include_diary and analysis_date:
        raw_diary = RawDiaryInput(
            bed_time=diary_bed_time,
            onset_time=diary_onset_time,
            wake_time=diary_wake_time,
            naps=list(diary_naps or []),
            nonwear=list(diary_nonwear or []),
            analysis_date=analysis_date,
        )

    pipeline = ScoringPipeline(params)
    result = pipeline.run(
        timestamps,
        activity_counts,
        raw_diary=raw_diary,
    )

    return result.to_legacy_dict()
