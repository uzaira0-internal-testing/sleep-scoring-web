"""
Unit tests for marker_placement.py — automated sleep/nap/nonwear placement.

These are pure unit tests using synthetic epoch arrays and dataclass configs.
No HTTP client or database fixtures are needed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from sleep_scoring_web.schemas.enums import MarkerType
from sleep_scoring_web.services.marker_placement import (
    DiaryDay,
    DiaryPeriod,
    EpochData,
    PlacementConfig,
    PlacementResult,
    _find_valid_offset_near,
    _find_valid_onset_at_or_after,
    _find_valid_onset_near,
    _nearest_epoch_index,
    _parse_time_to_24h,
    place_main_sleep,
    place_naps,
    place_nonwear_markers,
    place_without_diary,
    run_auto_scoring,
)


# =============================================================================
# Helpers
# =============================================================================

BASE_TS = datetime(2024, 1, 1, 22, 0, 0, tzinfo=UTC)  # 22:00 UTC


def _make_epochs(
    scores: list[int],
    start: datetime = BASE_TS,
    epoch_sec: int = 60,
    activity: float | list[float] | None = None,
    choi_nonwear: list[bool] | None = None,
) -> list[EpochData]:
    """Build a list of EpochData from a compact sleep-score list.

    scores: 0=wake, 1=sleep for each epoch.
    activity: constant float or per-epoch list (defaults to 0 for sleep, 100 for wake).
    """
    epochs: list[EpochData] = []
    for i, s in enumerate(scores):
        if isinstance(activity, list):
            act = activity[i]
        elif activity is not None:
            act = activity
        else:
            act = 0.0 if s == 1 else 100.0
        nw = choi_nonwear[i] if choi_nonwear else False
        epochs.append(
            EpochData(
                index=i,
                timestamp=start + timedelta(seconds=epoch_sec * i),
                sleep_score=s,
                activity=act,
                is_choi_nonwear=nw,
            )
        )
    return epochs


def _make_timestamps(n: int, start: datetime = BASE_TS, epoch_sec: int = 60) -> list[float]:
    """Generate n timestamps starting at `start` spaced `epoch_sec` apart."""
    return [(start + timedelta(seconds=epoch_sec * i)).timestamp() for i in range(n)]


CFG = PlacementConfig()  # defaults: 3-epoch onset, 5-min offset, 60s epochs


# =============================================================================
# Tests
# =============================================================================


class TestOnsetRule:
    """Onset: first epoch of 3+ consecutive sleep epochs."""

    def test_basic_3_consecutive_sleep(self) -> None:
        """3 consecutive sleep epochs right at target => onset at first epoch."""
        # W W W S S S W W
        scores = [0, 0, 0, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        target = epochs[3].timestamp  # exactly where sleep starts
        result = _find_valid_onset_near(epochs, target, min_consecutive=3)
        assert result == 3

    def test_two_consecutive_not_valid(self) -> None:
        """Only 2 consecutive sleep epochs do NOT qualify as onset."""
        # W S S W W
        scores = [0, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        target = epochs[1].timestamp
        result = _find_valid_onset_near(epochs, target, min_consecutive=3)
        assert result is None

    def test_onset_nearest_before_target(self) -> None:
        """When target is past onset, prefer onset that is AT or BEFORE target."""
        # S S S S W W W S S S
        scores = [1, 1, 1, 1, 0, 0, 0, 1, 1, 1]
        epochs = _make_epochs(scores)
        # Target at epoch 2 (inside the first run) — onset at 0 is before target
        target = epochs[2].timestamp
        result = _find_valid_onset_near(epochs, target, min_consecutive=3)
        assert result == 0

    def test_onset_falls_back_to_after_if_none_before(self) -> None:
        """If no valid onset exists before target, fall back to one after."""
        # W W W W S S S S
        scores = [0, 0, 0, 0, 1, 1, 1, 1]
        epochs = _make_epochs(scores)
        target = epochs[1].timestamp  # before any sleep
        result = _find_valid_onset_near(epochs, target, min_consecutive=3)
        assert result == 4


class TestOffsetRule:
    """Offset: ends with 5+ consecutive minutes (epochs) of sleep."""

    def test_basic_5_consecutive_offset(self) -> None:
        """5 consecutive sleep epochs ending at target => valid offset."""
        # S S S S S W W
        scores = [1, 1, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        target = epochs[4].timestamp
        result = _find_valid_offset_near(
            epochs, target, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        assert result == 4

    def test_4_consecutive_not_valid_offset(self) -> None:
        """Only 4 consecutive sleep epochs do NOT satisfy the 5-minute rule."""
        # S S S S W W
        scores = [1, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        target = epochs[3].timestamp
        result = _find_valid_offset_near(
            epochs, target, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        assert result is None

    def test_offset_prefers_at_or_after_target(self) -> None:
        """Offset should be AT or AFTER diary wake (more inclusive)."""
        # S S S S S S S S W W
        scores = [1, 1, 1, 1, 1, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        # Target at epoch 5 — the run ends at epoch 7, which is after target
        target = epochs[5].timestamp
        result = _find_valid_offset_near(
            epochs, target, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        assert result == 7  # end of the run (at or after target)


class TestActivityInMiddle:
    """Rule 1: include wake activity in the middle of a sleep period.

    When onset -> offset is determined, the full span is the sleep period,
    even if there are wake epochs in between.
    """

    def test_wake_gap_included_in_period(self) -> None:
        """Wake epochs between onset and offset are included (full span)."""
        # S S S S W W S S S S S
        scores = [1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1]
        epochs = _make_epochs(scores)
        diary = DiaryDay(
            in_bed_time=epochs[0].timestamp,
            sleep_onset=epochs[0].timestamp,
            wake_time=epochs[10].timestamp,
        )
        result = place_main_sleep(epochs, diary, CFG)
        assert result is not None
        onset_idx, offset_idx = result
        assert onset_idx == 0
        assert offset_idx == 10
        # The gap at epochs 4-5 (wake) is inside the period — included by Rule 1


class TestSmallPeriodsNearOnset:
    """Rule: small periods need at least 3 sleep epochs to qualify."""

    def test_tiny_sleep_run_rejected(self) -> None:
        """A 2-epoch sleep run should NOT be chosen as onset."""
        # W S S W W W S S S S S W
        scores = [0, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 0]
        epochs = _make_epochs(scores)
        target = epochs[1].timestamp  # near the 2-epoch run
        result = _find_valid_onset_near(epochs, target, min_consecutive=3)
        # Should skip 2-epoch run (idx 1-2) and find the 5-epoch run (idx 6)
        assert result == 6


class TestExtendedSleepBeforeDiaryMarker:
    """Rule 3/5: extended sleep before diary marker.

    If there's a long sleep run that starts before the diary onset, the onset
    should be placed at the start of that run (nearest valid onset before target).
    """

    def test_onset_extends_before_diary(self) -> None:
        """Sleep starting before diary onset is picked up (onset < diary)."""
        # S S S S S S S S W W
        scores = [1, 1, 1, 1, 1, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        # Diary onset at epoch 3, but sleep actually starts at epoch 0
        diary = DiaryDay(
            in_bed_time=epochs[0].timestamp,
            sleep_onset=epochs[3].timestamp,
            wake_time=epochs[7].timestamp,
        )
        result = place_main_sleep(epochs, diary, CFG)
        assert result is not None
        onset_idx, offset_idx = result
        # Onset should be at 0 (the closest valid onset AT or BEFORE diary onset)
        assert onset_idx == 0
        assert offset_idx == 7


class TestNapPlacement:
    """Rule 6: nap detection — continuous >=10 sleep epoch periods as nap."""

    def test_nap_placed_from_diary(self) -> None:
        """A diary nap period matching 10+ sleep epochs produces a nap marker."""
        # 30 wake epochs, then 12 sleep epochs, then 8 wake epochs = 50 total
        scores = [0] * 30 + [1] * 12 + [0] * 8
        epochs = _make_epochs(scores, start=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC))
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(
                    start_time=epochs[29].timestamp,  # near start of sleep
                    end_time=epochs[42].timestamp,     # near end of sleep
                    period_type="nap",
                )
            ]
        )
        naps = place_naps(epochs, diary, main_onset=None, main_offset=None, config=CFG)
        assert len(naps) == 1
        onset_idx, offset_idx = naps[0]
        assert onset_idx == 30  # start of the 12-epoch sleep run
        assert offset_idx == 41  # end of the 12-epoch sleep run

    def test_nap_too_short_rejected(self) -> None:
        """A sleep run shorter than nap_min_consecutive_epochs (10) is rejected."""
        # 5 wake, 8 sleep, 5 wake = 18 total
        scores = [0] * 5 + [1] * 8 + [0] * 5
        epochs = _make_epochs(scores, start=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC))
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(
                    start_time=epochs[4].timestamp,
                    end_time=epochs[13].timestamp,
                    period_type="nap",
                )
            ]
        )
        naps = place_naps(epochs, diary, main_onset=None, main_offset=None, config=CFG)
        assert len(naps) == 0  # 8 epochs < 10 minimum

    def test_nap_overlapping_main_sleep_rejected(self) -> None:
        """Nap overlapping main sleep period should be rejected."""
        scores = [1] * 15 + [0] * 5 + [1] * 12 + [0] * 8
        epochs = _make_epochs(scores, start=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC))
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(
                    start_time=epochs[19].timestamp,
                    end_time=epochs[32].timestamp,
                    period_type="nap",
                )
            ]
        )
        # Main sleep covers epochs 0-14
        naps = place_naps(epochs, diary, main_onset=0, main_offset=14, config=CFG)
        # The nap (20-31) does NOT overlap main (0-14), so it should be accepted
        assert len(naps) == 1

        # Now test actual overlap — nap period overlaps main sleep
        naps2 = place_naps(epochs, diary, main_onset=0, main_offset=25, config=CFG)
        assert len(naps2) == 0  # rejected due to overlap


class TestRule8InBedClamping:
    """Rule 8: if onset is BEFORE in-bed time, use in-bed time instead."""

    def test_onset_clamped_to_in_bed(self) -> None:
        """When onset < in-bed, onset should be clamped forward to in-bed time."""
        # S S S S S W W S S S S S S W W
        scores = [1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        diary = DiaryDay(
            in_bed_time=epochs[7].timestamp,   # in-bed at epoch 7
            sleep_onset=epochs[0].timestamp,   # diary onset at epoch 0
            wake_time=epochs[12].timestamp,
        )
        result = place_main_sleep(epochs, diary, CFG)
        assert result is not None
        onset_idx, offset_idx = result
        # Onset at epoch 0 is before in-bed at epoch 7
        # Should be clamped to the next valid onset at or after epoch 7
        assert onset_idx == 7
        assert offset_idx == 12

    def test_clamping_disabled(self) -> None:
        """When enable_rule_8_clamping=False, onset stays before in-bed."""
        scores = [1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        diary = DiaryDay(
            in_bed_time=epochs[7].timestamp,
            sleep_onset=epochs[0].timestamp,
            wake_time=epochs[12].timestamp,
        )
        no_clamp_cfg = PlacementConfig(enable_rule_8_clamping=False)
        result = place_main_sleep(epochs, diary, no_clamp_cfg)
        assert result is not None
        onset_idx, offset_idx = result
        assert onset_idx == 0  # not clamped


class TestPlaceWithoutDiary:
    """Fallback placement without diary — find the longest sleep period."""

    def test_longest_period_selected(self) -> None:
        """Without diary, the longest qualifying sleep block is chosen."""
        # Run1: 4 sleep, gap, Run2: 10 sleep
        scores = [1, 1, 1, 1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        result = place_without_diary(epochs, CFG)
        assert result is not None
        onset_idx, offset_idx = result
        # Both Run1 (start=0) and Run2 (start=6) meet onset criteria (3+).
        # Both meet offset criteria (5+ epochs).
        # The longest inclusive period is onset=0 to offset=15 (Run1 start to Run2 end)
        assert onset_idx == 0
        assert offset_idx == 15

    def test_no_qualifying_runs(self) -> None:
        """All-wake data returns None."""
        scores = [0, 0, 0, 0, 0]
        epochs = _make_epochs(scores)
        result = place_without_diary(epochs, CFG)
        assert result is None


class TestRunAutoScoring:
    """Integration test for the run_auto_scoring entry point."""

    def test_full_pipeline_with_diary(self) -> None:
        """run_auto_scoring with diary onset/wake produces a main sleep marker."""
        n = 120
        start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        # Activity: high (wake), then low (sleep from epoch 30 to 100), then high
        activity = [200.0] * 30 + [5.0] * 70 + [200.0] * 20
        # Sleep scores matching the activity pattern
        sleep_scores = [0] * 30 + [1] * 70 + [0] * 20

        # Diary onset at epoch ~32, wake at epoch ~98
        onset_dt = start + timedelta(minutes=32)
        wake_dt = start + timedelta(minutes=98)

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_onset_time=onset_dt.strftime("%H:%M"),
            diary_wake_time=wake_dt.strftime("%H:%M"),
            analysis_date="2024-01-01",
        )

        assert len(result["sleep_markers"]) == 1
        marker = result["sleep_markers"][0]
        assert marker["marker_type"] == MarkerType.MAIN_SLEEP
        # Onset should be at epoch 30 (start of sleep run, before diary onset)
        assert marker["onset_timestamp"] == timestamps[30]
        # Offset should be at end of the sleep run
        assert marker["offset_timestamp"] == timestamps[99]

    def test_no_diary_returns_no_markers(self) -> None:
        """Without diary data, run_auto_scoring does not auto-score."""
        n = 60
        start = datetime(2024, 1, 1, 22, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [10.0] * n
        sleep_scores = [1] * n

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
        )
        assert len(result["sleep_markers"]) == 0
        assert any("No diary" in note or "auto-score requires diary" in note for note in result["notes"])

    def test_nap_via_diary(self) -> None:
        """run_auto_scoring places nap markers from diary nap periods.

        Uses an overnight data window (22:00 -> next morning) to match the
        diary time parser's overnight logic: onset is_evening=True (h<12 => +1d),
        wake is_evening=False (h<18 => +1d).  Nap times use _parse_nap_time
        (no shifting), so they land on analysis_date as-is.
        """
        # Data from 2024-01-01 12:00 to ~17:20 (320 minutes)
        # Nap runs from epoch 30 to epoch 50 (12:30-12:50)
        # Main sleep: not relevant for this test, but give a valid one
        # so the function doesn't skip naps.
        n = 320
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)

        # Construct overnight-style data to satisfy diary parsing.
        # analysis_date = 2024-01-01:
        #   diary onset "22:00" => 2024-01-01 22:00 (is_evening, h>=12 no shift)
        #   diary wake  "7:00"  => 2024-01-02 07:00 (not evening, h<18 => +1d)
        # But data starts at 12:00 on 2024-01-01, so we need data spanning
        # to 2024-01-02 ~07:00 = 1140 epochs from start.
        # That's too many — instead, use direct place_naps with pre-built epochs.

        # Simplify: test place_naps directly with proper EpochData and DiaryDay
        # (the integration test already covers run_auto_scoring pipeline).
        epoch_start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        # 20 wake, 15 sleep (nap), 15 wake = 50 epochs
        scores = [0] * 20 + [1] * 15 + [0] * 15
        epochs = _make_epochs(scores, start=epoch_start)

        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(
                    start_time=epochs[19].timestamp,  # near nap start
                    end_time=epochs[35].timestamp,     # near nap end
                    period_type="nap",
                )
            ]
        )
        naps = place_naps(epochs, diary, main_onset=None, main_offset=None, config=CFG)
        assert len(naps) == 1
        onset_idx, offset_idx = naps[0]
        assert onset_idx == 20
        assert offset_idx == 34


class TestNonwearPlacement:
    """Tests for place_nonwear_markers."""

    def test_diary_nonwear_with_zero_activity(self) -> None:
        """Diary nonwear period matching zero-activity epochs places a marker.

        _parse_diary_time for nonwear uses default is_evening=True, so times
        with h<12 get shifted to next day. We use analysis_date='2024-01-01'
        so diary time "10:10" => 2024-01-02 10:10 UTC. Data starts at that
        same shifted date to match.
        """
        n = 60
        # Data on 2024-01-02 10:00 UTC (matching the +1 day shift)
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        # Activity: 100 for first 10, then 0 for 20, then 100 for rest
        activity = [100.0] * 10 + [0.0] * 20 + [100.0] * 30

        result = place_nonwear_markers(
            timestamps=timestamps,
            activity_counts=activity,
            diary_nonwear=[("10:10", "10:29")],  # => 2024-01-02 10:10-10:29
            choi_nonwear=None,
            sensor_nonwear_periods=[],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",  # +1 day shift makes times land on 01-02
        )

        assert len(result.nonwear_markers) == 1

    def test_nonwear_overlapping_sleep_rejected(self) -> None:
        """Nonwear period overlapping with existing sleep marker is rejected.

        Use analysis_date='2024-01-01' so diary times with h<12 shift to
        2024-01-02, matching the data window.
        """
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n  # all zero activity

        # Sleep marker covering the full data range
        sleep_start = timestamps[0]
        sleep_end = timestamps[59]

        result = place_nonwear_markers(
            timestamps=timestamps,
            activity_counts=activity,
            diary_nonwear=[("10:10", "10:20")],  # => 2024-01-02 10:10-10:20
            choi_nonwear=None,
            sensor_nonwear_periods=[],
            existing_sleep_markers=[(sleep_start, sleep_end)],
            analysis_date="2024-01-01",  # +1 day shift makes times land on 01-02
        )

        assert len(result.nonwear_markers) == 0
        assert any("overlaps" in note for note in result.notes)

    def test_nonwear_too_much_activity_rejected(self) -> None:
        """Nonwear period with too much activity (>20% epochs) is rejected."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        # All high activity
        activity = [500.0] * n

        result = place_nonwear_markers(
            timestamps=timestamps,
            activity_counts=activity,
            diary_nonwear=[("10:10", "10:29")],  # => 2024-01-02 10:10-10:29
            choi_nonwear=None,
            sensor_nonwear_periods=[],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",  # +1 day shift makes times land on 01-02
        )

        assert len(result.nonwear_markers) == 0
        assert any("activity" in note.lower() for note in result.notes)


class TestParseTimeTo24h:
    """Unit tests for _parse_time_to_24h helper."""

    def test_24h_format(self) -> None:
        assert _parse_time_to_24h("23:30") == (23, 30)
        assert _parse_time_to_24h("00:00") == (0, 0)

    def test_12h_am_pm(self) -> None:
        assert _parse_time_to_24h("11:30 PM") == (23, 30)
        assert _parse_time_to_24h("9:27 AM") == (9, 27)
        assert _parse_time_to_24h("12:45 AM") == (0, 45)
        assert _parse_time_to_24h("12:00 PM") == (12, 0)

    def test_invalid_time(self) -> None:
        assert _parse_time_to_24h("not a time") is None
        assert _parse_time_to_24h("25:00") is None


class TestNearestEpochIndex:
    """Unit tests for _nearest_epoch_index binary search."""

    def test_exact_match(self) -> None:
        epochs = _make_epochs([0, 0, 0, 0, 0])
        result = _nearest_epoch_index(epochs, epochs[2].timestamp)
        assert result == 2

    def test_between_epochs(self) -> None:
        epochs = _make_epochs([0, 0, 0, 0, 0])
        # Target between epoch 1 and epoch 2 (closer to 2)
        target = epochs[1].timestamp + timedelta(seconds=40)
        result = _nearest_epoch_index(epochs, target)
        assert result == 2  # 40s past epoch 1 is closer to epoch 2 (20s away)

    def test_empty_epochs(self) -> None:
        result = _nearest_epoch_index([], BASE_TS)
        assert result is None
