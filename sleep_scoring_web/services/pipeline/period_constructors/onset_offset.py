"""
Onset/offset period constructor.

Wraps the existing marker_placement.py onset/offset finding, Rule 8 clamping,
and nap placement logic. Delegates to the original functions to preserve exact
behavior during the transition.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.schemas.enums import MarkerType
from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, EpochSeries, GuideWindow, NapGuideWindow, SleepPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import PeriodConstructorParams


@register("period_constructor", "onset_offset")
class OnsetOffsetPeriodConstructor:
    """
    Constructs sleep periods using consecutive-run onset/offset rules.

    Delegates to the existing marker_placement.py functions for exact
    behavioral compatibility. Uses:
    - _find_valid_onset_near for main sleep onset
    - _find_valid_offset_near_bounded for main sleep offset
    - Rule 8: clamp onset to in-bed time
    - place_naps for diary nap periods
    """

    @property
    def id(self) -> str:
        return "onset_offset"

    def construct(
        self,
        epochs: EpochSeries,
        classified: ClassifiedEpochs,
        bouts: list[Bout],
        main_guide: GuideWindow | None,
        nap_guides: list[NapGuideWindow],
        *,
        params: PeriodConstructorParams | None = None,
    ) -> list[SleepPeriodResult]:
        from sleep_scoring_web.services.marker_placement import (
            DiaryDay,
            DiaryPeriod,
            EpochData,
            PlacementConfig,
            place_main_sleep,
            place_naps,
        )

        if params is None:
            from sleep_scoring_web.services.pipeline.params import PeriodConstructorParams as PCParams

            params = PCParams()

        config = PlacementConfig(
            onset_min_consecutive_sleep=params.onset_min_consecutive_sleep,
            offset_min_consecutive_minutes=params.offset_min_consecutive_minutes,
            nap_min_consecutive_epochs=params.nap_min_consecutive_epochs,
            max_forward_offset_epochs=params.max_forward_offset_epochs,
            nap_max_search_epochs=params.nap_max_search_epochs,
            enable_rule_8_clamping=params.enable_rule_8_clamping,
            epoch_length_seconds=params.epoch_length_seconds,
        )

        # Build EpochData list from pipeline data
        epoch_data_list = _build_epoch_data(epochs, classified)
        if not epoch_data_list:
            return []

        results: list[SleepPeriodResult] = []
        main_onset_idx: int | None = None
        main_offset_idx: int | None = None

        # Main sleep placement
        if main_guide is not None:
            diary = DiaryDay(
                in_bed_time=main_guide.in_bed_time,
                sleep_onset=main_guide.onset_target,
                wake_time=main_guide.offset_target,
            )
            main_result = place_main_sleep(epoch_data_list, diary, config)
            if main_result:
                main_onset_idx, main_offset_idx = main_result
                results.append(
                    SleepPeriodResult(
                        onset_index=main_onset_idx,
                        offset_index=main_offset_idx,
                        onset_timestamp=epochs.timestamps[main_onset_idx],
                        offset_timestamp=epochs.timestamps[main_offset_idx],
                        period_type=MarkerType.MAIN_SLEEP,
                        marker_index=1,
                    )
                )

        # Nap placement
        if nap_guides:
            nap_periods = [
                DiaryPeriod(
                    start_time=ng.start_target,
                    end_time=ng.end_target,
                    period_type="nap",
                )
                for ng in nap_guides
            ]
            diary_for_naps = DiaryDay(nap_periods=nap_periods)
            nap_results = place_naps(
                epoch_data_list,
                diary_for_naps,
                main_onset_idx,
                main_offset_idx,
                config,
            )
            for i, (nap_on, nap_off) in enumerate(nap_results):
                results.append(
                    SleepPeriodResult(
                        onset_index=nap_on,
                        offset_index=nap_off,
                        onset_timestamp=epochs.timestamps[nap_on],
                        offset_timestamp=epochs.timestamps[nap_off],
                        period_type=MarkerType.NAP,
                        marker_index=len(results) + 1,
                    )
                )

        return results


def _build_epoch_data(
    epochs: EpochSeries,
    classified: ClassifiedEpochs,
) -> list:
    """Build EpochData list from pipeline types for legacy function calls."""
    from sleep_scoring_web.services.marker_placement import EpochData

    result: list[EpochData] = []
    for i in range(epochs.length):
        result.append(
            EpochData(
                index=i,
                timestamp=epochs.epoch_times[i],
                sleep_score=classified.scores[i] if i < len(classified.scores) else 0,
                activity=epochs.activity_counts[i],
                is_choi_nonwear=False,  # Nonwear handled separately
            )
        )
    return result
