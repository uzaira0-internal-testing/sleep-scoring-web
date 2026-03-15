"""
Pipeline orchestrator — replaces the monolithic run_auto_scoring().

ScoringPipeline executes the six-step pipeline using pluggable components
resolved from the registry. PipelineResult.to_legacy_dict() bridges to
the existing dict format for backward compatibility.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sleep_scoring_web.schemas.enums import MarkerType

from .protocols import (
    DiaryInput,
    EpochSeries,
    NapGuideWindow,
    PipelineResult,
    RawDiaryInput,
    SleepPeriodResult,
)
from .registry import get_component

if TYPE_CHECKING:  # pragma: no cover
    from .params import PipelineParams


class ScoringPipeline:
    """Configurable scoring pipeline with pluggable components."""

    def __init__(self, params: PipelineParams) -> None:
        self._params = params
        self._diary_preprocessor = get_component("diary_preprocessor", params.diary_preprocessor)
        self._epoch_classifier = get_component("epoch_classifier", params.epoch_classifier)
        self._bout_detector = get_component("bout_detector", params.bout_detector)
        self._period_guider = get_component("period_guider", params.period_guider)
        self._period_constructor = get_component("period_constructor", params.period_constructor)
        self._nonwear_detector = get_component("nonwear_detector", params.nonwear_detector)

    def run(
        self,
        timestamps: list[float],
        activity_counts: list[float],
        *,
        raw_diary: RawDiaryInput | None = None,
    ) -> PipelineResult:
        if not timestamps or not activity_counts:
            return PipelineResult(notes=["No activity data"])

        epoch_times = [datetime.fromtimestamp(ts, tz=UTC) for ts in timestamps]
        epochs = EpochSeries(
            timestamps=timestamps,
            epoch_times=epoch_times,
            activity_counts=activity_counts,
            epoch_length_seconds=self._params.period_constructor_params.epoch_length_seconds,
        )

        notes: list[str] = []

        # Step 1: Diary preprocessing
        diary_data: DiaryInput | None = None
        if raw_diary is not None:
            data_window = (timestamps[0], timestamps[-1])
            diary_data, diary_notes = self._diary_preprocessor.preprocess(
                raw_diary,
                data_window,
                params=self._params.diary_preprocessor_params,
            )
            notes.extend(diary_notes)

        # Step 2: Epoch classification
        classified = self._epoch_classifier.classify(
            epochs,
            params=self._params.epoch_classifier_params,
        )

        # Step 3: Bout detection
        bouts = self._bout_detector.detect_bouts(
            classified,
            params=self._params.bout_detector_params,
        )

        # Step 4: Period guiding
        main_guide, nap_guides, guide_notes = self._period_guider.guide(
            epochs,
            classified,
            bouts,
            params=self._params.period_guider_params,
            diary_data=diary_data,
        )
        notes.extend(guide_notes)

        # Add detection rule note
        p = self._params.period_constructor_params
        if p.onset_min_consecutive_sleep != 3 or p.offset_min_consecutive_minutes != 5:
            notes.append(f"Detection rule: {p.onset_min_consecutive_sleep}S/{p.offset_min_consecutive_minutes}S")

        # Step 5: Period construction
        sleep_periods = self._period_constructor.construct(
            epochs,
            classified,
            bouts,
            main_guide,
            nap_guides,
            params=self._params.period_constructor_params,
        )

        # Step 6: Nonwear detection
        nonwear_periods = self._nonwear_detector.detect(
            epochs,
            params=self._params.nonwear_detector_params,
            diary_data=diary_data,
            existing_sleep=sleep_periods,
        )

        # Add placement notes
        _add_placement_notes(notes, sleep_periods, epochs, diary_data, main_guide, nap_guides)

        return PipelineResult(
            sleep_periods=sleep_periods,
            nonwear_periods=nonwear_periods,
            notes=notes,
        )


def _add_placement_notes(
    notes: list[str],
    sleep_periods: list[SleepPeriodResult],
    epochs: EpochSeries,
    diary_data: DiaryInput | None,
    main_guide: object | None,
    nap_guides: list[NapGuideWindow],
) -> None:
    """Add human-readable placement notes matching legacy output format."""
    main_found = False
    nap_count = 0

    for sp in sleep_periods:
        onset_time = epochs.epoch_times[sp.onset_index]
        offset_time = epochs.epoch_times[sp.offset_index]
        duration_epochs = sp.offset_index - sp.onset_index + 1
        duration_min = duration_epochs * epochs.epoch_length_seconds / 60

        if sp.period_type == MarkerType.MAIN_SLEEP:
            main_found = True
            if diary_data and diary_data.sleep_onset and diary_data.wake_time:
                notes.append(
                    f"Main sleep: {onset_time.strftime('%H:%M')} - "
                    f"{offset_time.strftime('%H:%M')} ({duration_min:.0f} min) — "
                    f"diary onset {diary_data.sleep_onset.strftime('%H:%M')}, "
                    f"diary wake {diary_data.wake_time.strftime('%H:%M')}"
                )
            else:
                notes.append(f"Main sleep: {onset_time.strftime('%H:%M')} - {offset_time.strftime('%H:%M')} ({duration_min:.0f} min)")
        elif sp.period_type == MarkerType.NAP:
            nap_count += 1
            notes.append(f"Nap {nap_count}: {onset_time.strftime('%H:%M')} - {offset_time.strftime('%H:%M')} ({duration_min:.0f} min)")

    if not main_found:
        if diary_data and diary_data.sleep_onset and diary_data.wake_time:
            notes.append(
                f"No valid sleep period found near diary times "
                f"(onset {diary_data.sleep_onset.strftime('%H:%M')}, "
                f"wake {diary_data.wake_time.strftime('%H:%M')})"
            )
        else:
            notes.append("No main sleep period detected")
