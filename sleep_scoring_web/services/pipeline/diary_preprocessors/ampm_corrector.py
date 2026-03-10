"""
AM/PM correcting diary preprocessor.

Wraps the existing _try_ampm_corrections, _parse_diary_time, and _parse_nap_time
functions from marker_placement.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sleep_scoring_web.services.pipeline.protocols import DiaryInput, RawDiaryInput
from sleep_scoring_web.services.pipeline.registry import register

if TYPE_CHECKING:
    from sleep_scoring_web.services.pipeline.params import DiaryPreprocessorParams


@register("diary_preprocessor", "ampm_corrector")
class AmPmDiaryPreprocessor:
    """Validates and corrects diary AM/PM errors, parses time strings."""

    @property
    def id(self) -> str:
        return "ampm_corrector"

    def preprocess(
        self,
        raw_diary: RawDiaryInput,
        data_window: tuple[float, float],
        *,
        params: DiaryPreprocessorParams | None = None,
    ) -> tuple[DiaryInput, list[str]]:
        from sleep_scoring_web.services.marker_placement import (
            _parse_diary_time,
            _parse_nap_time,
            _try_ampm_corrections,
        )

        notes: list[str] = []

        if not raw_diary.analysis_date:
            return DiaryInput(), notes

        from datetime import date as date_type

        d = date_type.fromisoformat(raw_diary.analysis_date)
        data_start = datetime.fromtimestamp(data_window[0], tz=UTC)
        data_end = datetime.fromtimestamp(data_window[1], tz=UTC)

        if params is None:
            from sleep_scoring_web.services.pipeline.params import DiaryPreprocessorParams as DPParams
            params = DPParams()

        # Main sleep times — with or without AM/PM correction
        onset_str = raw_diary.onset_time or raw_diary.bed_time
        if params.enable_ampm_correction:
            onset_dt, wake_dt, bed_dt, ampm_notes = _try_ampm_corrections(
                onset_str=onset_str,
                wake_str=raw_diary.wake_time,
                bed_str=raw_diary.bed_time,
                base_date=d,
                data_start=data_start,
                data_end=data_end,
            )
            notes.extend(ampm_notes)
        else:
            onset_dt = _parse_diary_time(onset_str, d, is_evening=True) if onset_str else None
            wake_dt = _parse_diary_time(raw_diary.wake_time, d, is_evening=False) if raw_diary.wake_time else None
            bed_dt = _parse_diary_time(raw_diary.bed_time, d, is_evening=True) if raw_diary.bed_time else None

        # Parse nap periods
        nap_periods: list[tuple[datetime, datetime]] = []
        for nap_start, nap_end in raw_diary.naps:
            if nap_start and nap_end:
                ns = _parse_nap_time(nap_start, d)
                ne = _parse_nap_time(nap_end, d)
                if ns and ne and ne <= ns:
                    ne += timedelta(days=1)
                if ns and ne:
                    nap_periods.append((ns, ne))

        # Parse nonwear periods
        nonwear_periods: list[tuple[datetime, datetime]] = []
        for nw_start, nw_end in raw_diary.nonwear:
            if nw_start and nw_end:
                ns = _parse_diary_time(nw_start, d, is_evening=False)
                ne = _parse_diary_time(nw_end, d, is_evening=False)
                if ns and ne:
                    nonwear_periods.append((ns, ne))

        diary = DiaryInput(
            sleep_onset=onset_dt,
            wake_time=wake_dt,
            in_bed_time=bed_dt or onset_dt,
            nap_periods=nap_periods,
            nonwear_periods=nonwear_periods,
        )
        return diary, notes
