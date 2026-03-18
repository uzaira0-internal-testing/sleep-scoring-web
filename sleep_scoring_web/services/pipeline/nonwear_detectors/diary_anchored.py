"""Diary-anchored nonwear detector — wraps place_nonwear_markers()."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import DiaryInput, EpochSeries, NonwearPeriodResult, SleepPeriodResult
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import NonwearDetectorParams


@register("nonwear_detector", "diary_anchored")
class DiaryAnchoredNonwearDetector:
    """
    Diary-anchored nonwear detection with zero-activity extension.

    Wraps the existing place_nonwear_markers() logic. Uses diary nonwear
    anchors, extends via zero-activity, and validates with Choi/sensor signals.
    """

    @property
    def id(self) -> str:
        return "diary_anchored"

    def detect(
        self,
        epochs: EpochSeries,
        *,
        params: NonwearDetectorParams | None = None,
        diary_data: DiaryInput | None = None,
        existing_sleep: list[SleepPeriodResult] | None = None,
    ) -> list[NonwearPeriodResult]:
        if params is None:
            from sleep_scoring_web.services.pipeline.params import NonwearDetectorParams as NWParams

            params = NWParams()

        if not diary_data or not diary_data.nonwear_periods:
            return []

        # Convert diary nonwear to string pairs for legacy function
        diary_nonwear_strs: list[tuple[str | None, str | None]] = [
            (
                nw_start.strftime("%H:%M"),
                nw_end.strftime("%H:%M"),
            )
            for nw_start, nw_end in diary_data.nonwear_periods
        ]

        # Convert existing sleep to timestamp pairs
        sleep_marker_pairs: list[tuple[float, float]] = []
        if existing_sleep:
            sleep_marker_pairs = [(sp.onset_timestamp, sp.offset_timestamp) for sp in existing_sleep]

        from sleep_scoring_web.services.marker_placement import _find_nearest_epoch, place_nonwear_markers

        # Determine analysis_date from epoch times
        analysis_date_str = epochs.epoch_times[0].strftime("%Y-%m-%d")

        result = place_nonwear_markers(
            timestamps=epochs.timestamps,
            activity_counts=epochs.activity_counts,
            diary_nonwear=diary_nonwear_strs,
            choi_nonwear=None,
            sensor_nonwear_periods=[],
            existing_sleep_markers=sleep_marker_pairs,
            analysis_date=analysis_date_str,
            epoch_length_seconds=params.epoch_length_seconds,
            threshold=params.activity_threshold,
            min_duration_minutes=params.min_duration_minutes,
            zero_activity_ratio=params.zero_activity_ratio,
        )

        results: list[NonwearPeriodResult] = []
        for m in result.nonwear_markers:
            # Find epoch indices for the timestamps
            start_ts = m["start_timestamp"]
            end_ts = m["end_timestamp"]
            start_idx = _find_nearest_epoch(epochs.timestamps, start_ts) or 0
            end_idx = _find_nearest_epoch(epochs.timestamps, end_ts) or 0
            results.append(
                NonwearPeriodResult(
                    start_index=start_idx,
                    end_index=end_idx,
                    start_timestamp=start_ts,
                    end_timestamp=end_ts,
                    marker_index=m["marker_index"],
                )
            )

        return results
