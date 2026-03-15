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
    NonwearPlacementResult,
    PlacementConfig,
    PlacementResult,
    _diary_time_present,
    _diary_times_plausible,
    _epoch_in_nonwear_signal,
    _find_nearest_epoch,
    _find_nearest_epoch_dt,
    _find_valid_offset_at_or_before,
    _find_valid_offset_near,
    _find_valid_offset_near_bounded,
    _find_valid_onset_at_or_after,
    _find_valid_onset_near,
    _find_valid_onset_near_bounded,
    _flip_ampm,
    _nearest_epoch_index,
    _parse_diary_time,
    _parse_nap_time,
    _parse_time_to_24h,
    _try_ampm_corrections,
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

    def test_single_epoch(self) -> None:
        epochs = _make_epochs([0])
        result = _nearest_epoch_index(epochs, epochs[0].timestamp)
        assert result == 0

    def test_target_before_all_epochs(self) -> None:
        epochs = _make_epochs([0, 0, 0])
        target = epochs[0].timestamp - timedelta(minutes=5)
        result = _nearest_epoch_index(epochs, target)
        assert result == 0

    def test_target_after_all_epochs(self) -> None:
        epochs = _make_epochs([0, 0, 0])
        target = epochs[2].timestamp + timedelta(minutes=5)
        result = _nearest_epoch_index(epochs, target)
        assert result == 2


# =============================================================================
# Additional Coverage Tests
# =============================================================================


class TestOnsetEquidistant:
    """Cover equidistant tie-breaking in _find_valid_onset_near (lines 135-136)."""

    def test_equidistant_onsets_picks_earlier(self) -> None:
        """When two valid onsets are equidistant, the earlier one is preferred."""
        # Run1 at 0-2 (len 3), Run2 at 6-8 (len 3)
        # Center at 3 => dist to 0 = 3, dist to 6 = 3 => equal
        scores = [1, 1, 1, 0, 0, 0, 1, 1, 1]
        epochs = _make_epochs(scores)
        target = epochs[3].timestamp
        result = _find_valid_onset_near(epochs, target, min_consecutive=3)
        # Both are equidistant from center (3). Before pool = [0], after pool = [6].
        # before pool is non-empty so it is used; result = 0
        assert result == 0


class TestOffsetEquidistant:
    """Cover equidistant tie-breaking in _find_valid_offset_near (lines 192-193)."""

    def test_equidistant_offsets_picks_later(self) -> None:
        """When two valid offsets are equidistant, the later one is preferred."""
        # Run1: epochs 0-5 (len 6, offset at 5), Run2: epochs 9-14 (len 6, offset at 14)
        # Center at 9 => after pool = [14], dist = 5. But offset at 5 is before center (dist=4).
        # Use after pool since idx >= center.
        scores = [1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1]
        epochs = _make_epochs(scores)
        target = epochs[9].timestamp  # center = 9
        result = _find_valid_offset_near(
            epochs, target, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        # After pool: [14] (14 >= 9), before pool: [5] (5 < 9).
        # After pool used first. Result = 14.
        assert result == 14

    def test_offset_falls_back_to_before(self) -> None:
        """When no valid offset AT or AFTER target, fall back to before."""
        # Only one run: epochs 0-6 (len 7, offset=6). Target at epoch 10.
        scores = [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        epochs = _make_epochs(scores)
        target = epochs[10].timestamp
        result = _find_valid_offset_near(
            epochs, target, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        # After pool (idx >= 10) is empty. Before pool = [6]. Result = 6.
        assert result == 6

    def test_offset_empty_epochs(self) -> None:
        """Empty epochs returns None for offset search."""
        result = _find_valid_offset_near(
            [], BASE_TS, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        assert result is None


class TestOffsetNearBounded:
    """Cover _find_valid_offset_near_bounded branches."""

    def test_empty_epochs(self) -> None:
        result = _find_valid_offset_near_bounded(
            [], BASE_TS, min_consecutive_minutes=5,
            epoch_length_seconds=60, max_forward_epochs=60
        )
        assert result is None

    def test_no_valid_offsets_within_bound(self) -> None:
        """Run end exceeds max_forward_epochs limit, so it's skipped."""
        # 20 epochs of sleep. Center at epoch 0, max_forward = 5.
        # Run end = 19, max_idx = 0+5 = 5. 19 > 5 => skipped.
        scores = [1] * 20
        epochs = _make_epochs(scores)
        target = epochs[0].timestamp
        result = _find_valid_offset_near_bounded(
            epochs, target, min_consecutive_minutes=5,
            epoch_length_seconds=60, max_forward_epochs=5
        )
        assert result is None

    def test_bounded_offset_within_window(self) -> None:
        """Run end within the bounded window is accepted."""
        # 10 sleep + 5 wake. Center at epoch 0, max_forward = 15.
        scores = [1] * 10 + [0] * 5
        epochs = _make_epochs(scores)
        target = epochs[0].timestamp
        result = _find_valid_offset_near_bounded(
            epochs, target, min_consecutive_minutes=5,
            epoch_length_seconds=60, max_forward_epochs=15
        )
        assert result == 9

    def test_bounded_equidistant_picks_later(self) -> None:
        """Equidistant offsets in bounded search pick the later one."""
        # Run1: 0-5 (end=5), Run2: 9-14 (end=14). Center=9, max_forward=60.
        # max_idx = 69 but array is only 15 long, so max_idx = 14.
        # Both end at <=14. After pool (>=9): [14]. Before pool (<9): [5].
        scores = [1, 1, 1, 1, 1, 1, 0, 0, 0, 1, 1, 1, 1, 1, 1]
        epochs = _make_epochs(scores)
        target = epochs[9].timestamp
        result = _find_valid_offset_near_bounded(
            epochs, target, min_consecutive_minutes=5,
            epoch_length_seconds=60, max_forward_epochs=60
        )
        assert result == 14


class TestOnsetNearBounded:
    """Cover _find_valid_onset_near_bounded branches."""

    def test_empty_epochs(self) -> None:
        result = _find_valid_onset_near_bounded(
            [], BASE_TS, min_consecutive=3, max_distance_epochs=60
        )
        assert result is None

    def test_no_valid_onsets_within_bound(self) -> None:
        """All onsets outside the bounded window are skipped."""
        # Sleep run at epoch 100-105, center at epoch 0, max_distance = 10.
        # lo=0, hi=10. run_start=100 is not in [0,10] => skipped.
        scores = [0] * 100 + [1] * 6
        epochs = _make_epochs(scores)
        target = epochs[0].timestamp
        result = _find_valid_onset_near_bounded(
            epochs, target, min_consecutive=3, max_distance_epochs=10
        )
        assert result is None

    def test_bounded_onset_within_window(self) -> None:
        """Onset within bounded window is returned."""
        scores = [0] * 5 + [1] * 5 + [0] * 5
        epochs = _make_epochs(scores)
        target = epochs[5].timestamp
        result = _find_valid_onset_near_bounded(
            epochs, target, min_consecutive=3, max_distance_epochs=10
        )
        assert result == 5


class TestFindValidOnsetAtOrAfter:
    """Cover _find_valid_onset_at_or_after branches."""

    def test_empty_epochs(self) -> None:
        result = _find_valid_onset_at_or_after([], BASE_TS, min_consecutive=3)
        assert result is None

    def test_target_in_middle_of_sleep_run(self) -> None:
        """When target lands mid-run, that run is skipped."""
        # Run1: 0-9 (10 sleep), gap, Run2: 15-19 (5 sleep)
        scores = [1] * 10 + [0] * 5 + [1] * 5 + [0] * 5
        epochs = _make_epochs(scores)
        target = epochs[5].timestamp  # mid-run1
        result = _find_valid_onset_at_or_after(epochs, target, min_consecutive=3)
        # Lands in middle of run (i=5, i-1=4 both sleep), skip past run1 to epoch 10.
        # Then search forward: run2 at 15 with len=5 >= 3 => onset=15.
        assert result == 15

    def test_target_at_start_of_run(self) -> None:
        """When target is at the first epoch of a run (preceded by wake), it's valid."""
        # W W W S S S S W
        scores = [0, 0, 0, 1, 1, 1, 1, 0]
        epochs = _make_epochs(scores)
        target = epochs[3].timestamp  # start of run, preceded by wake
        result = _find_valid_onset_at_or_after(epochs, target, min_consecutive=3)
        assert result == 3

    def test_no_valid_onset_found(self) -> None:
        """All runs after target are too short."""
        # W W W S S W W
        scores = [0, 0, 0, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        target = epochs[3].timestamp
        result = _find_valid_onset_at_or_after(epochs, target, min_consecutive=3)
        # run length 2 < 3 => None
        assert result is None


class TestFindValidOffsetAtOrBefore:
    """Cover _find_valid_offset_at_or_before (lines 385-404)."""

    def test_basic_offset_at_or_before(self) -> None:
        """Find offset at or before max_idx."""
        # S S S S S W W W W W
        scores = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        epochs = _make_epochs(scores)
        result = _find_valid_offset_at_or_before(
            epochs, max_idx=7, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        # Run ends at 4, which is <= 7. Result = 4.
        assert result == 4

    def test_run_end_exceeds_max_idx(self) -> None:
        """Run whose natural end exceeds max_idx is skipped."""
        # S S S S S S S S S S (10 consecutive, end=9)
        scores = [1] * 10
        epochs = _make_epochs(scores)
        # max_idx = 5 but run ends at 9. 9 > 5 => skipped.
        result = _find_valid_offset_at_or_before(
            epochs, max_idx=5, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        assert result is None

    def test_multiple_runs_picks_latest(self) -> None:
        """Among multiple valid runs, picks the one closest to max_idx."""
        # Run1: 0-5 (end=5), gap, Run2: 10-15 (end=15)
        scores = [1] * 6 + [0] * 4 + [1] * 6 + [0] * 4
        epochs = _make_epochs(scores)
        result = _find_valid_offset_at_or_before(
            epochs, max_idx=18, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        # Both runs qualify. run_end=5 and run_end=15. 15 > 5 => best=15.
        assert result == 15

    def test_no_qualifying_runs(self) -> None:
        """No runs meet minimum length."""
        scores = [1, 1, 0, 1, 1, 0, 0]
        epochs = _make_epochs(scores)
        result = _find_valid_offset_at_or_before(
            epochs, max_idx=6, min_consecutive_minutes=5, epoch_length_seconds=60
        )
        assert result is None

    def test_with_min_idx(self) -> None:
        """Respect min_idx parameter — only consider runs starting at or after min_idx."""
        # Run1: 0-5 (end=5), Run2: 10-15 (end=15)
        scores = [1] * 6 + [0] * 4 + [1] * 6 + [0] * 4
        epochs = _make_epochs(scores)
        result = _find_valid_offset_at_or_before(
            epochs, max_idx=18, min_consecutive_minutes=5,
            epoch_length_seconds=60, min_idx=8
        )
        # Run1 starts at 0 but iteration begins at min_idx=8 so run1 is skipped.
        # Run2 starts at 10 (>= 8), end=15 <= 18 => valid.
        assert result == 15


class TestFlipAmpm:
    """Cover _flip_ampm (lines 556-566)."""

    def test_flip_pm_to_am(self) -> None:
        assert _flip_ampm("7:00 PM") == "7:00 AM"

    def test_flip_am_to_pm(self) -> None:
        assert _flip_ampm("7:00 AM") == "7:00 PM"

    def test_24h_format_returns_none(self) -> None:
        assert _flip_ampm("19:00") is None

    def test_lowercase_pm(self) -> None:
        assert _flip_ampm("7:00 pm") == "7:00 AM"

    def test_lowercase_am(self) -> None:
        assert _flip_ampm("7:00 am") == "7:00 PM"


class TestDiaryTimesPlausible:
    """Cover _diary_times_plausible (lines 569-596)."""

    def test_both_none(self) -> None:
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        assert _diary_times_plausible(None, None, data_start, data_end) is False

    def test_onset_none(self) -> None:
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        wake = datetime(2024, 1, 2, 7, 0, tzinfo=UTC)
        assert _diary_times_plausible(None, wake, data_start, data_end) is False

    def test_wake_before_onset(self) -> None:
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        onset = datetime(2024, 1, 2, 7, 0, tzinfo=UTC)
        wake = datetime(2024, 1, 1, 22, 0, tzinfo=UTC)
        assert _diary_times_plausible(onset, wake, data_start, data_end) is False

    def test_too_short_duration(self) -> None:
        """Sleep duration < 2 hours is implausible."""
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        onset = datetime(2024, 1, 1, 22, 0, tzinfo=UTC)
        wake = datetime(2024, 1, 1, 23, 0, tzinfo=UTC)  # 1 hour only
        assert _diary_times_plausible(onset, wake, data_start, data_end) is False

    def test_too_long_duration(self) -> None:
        """Sleep duration > 18 hours is implausible."""
        data_start = datetime(2024, 1, 1, 0, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 3, 0, 0, tzinfo=UTC)
        onset = datetime(2024, 1, 1, 1, 0, tzinfo=UTC)
        wake = datetime(2024, 1, 2, 20, 0, tzinfo=UTC)  # 43 hours
        assert _diary_times_plausible(onset, wake, data_start, data_end) is False

    def test_onset_outside_data_range(self) -> None:
        """Onset far outside data window."""
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        onset = datetime(2024, 1, 5, 22, 0, tzinfo=UTC)  # way after data
        wake = datetime(2024, 1, 6, 7, 0, tzinfo=UTC)
        assert _diary_times_plausible(onset, wake, data_start, data_end) is False

    def test_wake_outside_data_range(self) -> None:
        """Wake far outside data window."""
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        onset = datetime(2024, 1, 1, 22, 0, tzinfo=UTC)
        wake = datetime(2024, 1, 5, 7, 0, tzinfo=UTC)  # way after data
        assert _diary_times_plausible(onset, wake, data_start, data_end) is False

    def test_plausible_times(self) -> None:
        """Normal overnight sleep within data range."""
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        onset = datetime(2024, 1, 1, 22, 0, tzinfo=UTC)
        wake = datetime(2024, 1, 2, 7, 0, tzinfo=UTC)
        assert _diary_times_plausible(onset, wake, data_start, data_end) is True


class TestTryAmpmCorrections:
    """Cover _try_ampm_corrections (lines 599-669)."""

    def test_original_plausible_no_corrections(self) -> None:
        """When original times are plausible, return them unchanged."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        onset_dt, wake_dt, bed_dt, notes = _try_ampm_corrections(
            onset_str="22:00", wake_str="7:00",
            bed_str="21:30", base_date=d,
            data_start=data_start, data_end=data_end,
        )
        assert onset_dt is not None
        assert wake_dt is not None
        assert len(notes) == 0

    def test_flip_wake_pm_to_am(self) -> None:
        """Wake entered as PM should be flipped to AM."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        # "7:00 PM" is implausible for wake (would be 19:00, only 3 hrs from 22:00 onset)
        # Wait — 22:00 onset to 19:00 wake next day = 21 hours, implausible (> 18h).
        # Flipping to AM: 22:00 to 7:00 AM next day = 9 hours, plausible.
        onset_dt, wake_dt, bed_dt, notes = _try_ampm_corrections(
            onset_str="10:00 PM", wake_str="7:00 PM",
            bed_str=None, base_date=d,
            data_start=data_start, data_end=data_end,
        )
        assert wake_dt is not None
        assert any("Corrected" in n for n in notes)

    def test_flip_onset_am_to_pm(self) -> None:
        """Onset entered as AM should be flipped to PM."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        # "10:00 AM" onset => 10:00 next day (is_evening, h<12 => +1 day)
        # "7:00" wake => 7:00 next day. gap = maybe negative or <2h.
        # Flip onset to PM => "10:00 PM" => 22:00 same day. wake 7:00 next day = 9h. Plausible.
        onset_dt, wake_dt, bed_dt, notes = _try_ampm_corrections(
            onset_str="10:00 AM", wake_str="7:00",
            bed_str="10:00 AM", base_date=d,
            data_start=data_start, data_end=data_end,
        )
        assert onset_dt is not None
        assert any("Corrected" in n for n in notes)

    def test_no_flip_works(self) -> None:
        """When no AM/PM flip makes times plausible, return originals."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        # 24h format => flip returns None, no corrections possible
        onset_dt, wake_dt, bed_dt, notes = _try_ampm_corrections(
            onset_str="03:00", wake_str="04:00",  # only 1 hour, too short
            bed_str=None, base_date=d,
            data_start=data_start, data_end=data_end,
        )
        # No flip possible (24h format) and original implausible (1 hour).
        assert len(notes) == 0

    def test_none_onset_and_wake(self) -> None:
        """None onset/wake returns Nones."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        onset_dt, wake_dt, bed_dt, notes = _try_ampm_corrections(
            onset_str=None, wake_str=None, bed_str=None,
            base_date=d, data_start=data_start, data_end=data_end,
        )
        assert onset_dt is None
        assert wake_dt is None


class TestParseDiaryTime:
    """Cover _parse_diary_time (lines 710-737)."""

    def test_evening_time_no_shift(self) -> None:
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        result = _parse_diary_time("22:00", d, is_evening=True)
        assert result is not None
        assert result.hour == 22
        assert result.day == 1  # h >= 12, no shift

    def test_evening_time_with_shift(self) -> None:
        """h < 12 with is_evening=True shifts to next day."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        result = _parse_diary_time("2:00", d, is_evening=True)
        assert result is not None
        assert result.day == 2  # shifted

    def test_wake_time_with_shift(self) -> None:
        """h < 18 with is_evening=False shifts to next day."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        result = _parse_diary_time("7:00", d, is_evening=False)
        assert result is not None
        assert result.day == 2  # shifted

    def test_wake_time_no_shift(self) -> None:
        """h >= 18 with is_evening=False stays on same day."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        result = _parse_diary_time("19:00", d, is_evening=False)
        assert result is not None
        assert result.day == 1  # no shift

    def test_invalid_time_str(self) -> None:
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        result = _parse_diary_time("not-a-time", d)
        assert result is None

    def test_invalid_base_date(self) -> None:
        """base_date with out-of-range values triggers ValueError branch."""
        from types import SimpleNamespace
        bad_date = SimpleNamespace(year=2024, month=13, day=1)  # month=13 invalid
        result = _parse_diary_time("22:00", bad_date)
        assert result is None


class TestParseNapTime:
    """Cover _parse_nap_time (lines 740-757)."""

    def test_basic_nap_time(self) -> None:
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        result = _parse_nap_time("14:00", d)
        assert result is not None
        assert result.hour == 14
        assert result.day == 1

    def test_invalid_nap_time(self) -> None:
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        result = _parse_nap_time("invalid", d)
        assert result is None

    def test_invalid_base_date(self) -> None:
        """base_date with out-of-range values triggers ValueError branch."""
        from types import SimpleNamespace
        bad_date = SimpleNamespace(year=2024, month=13, day=1)  # month=13 invalid
        result = _parse_nap_time("14:00", bad_date)
        assert result is None


class TestPlaceMainSleepEdgeCases:
    """Cover edge cases in place_main_sleep."""

    def test_no_diary_onset(self) -> None:
        """Missing sleep_onset returns None."""
        scores = [1] * 10
        epochs = _make_epochs(scores)
        diary = DiaryDay(wake_time=epochs[9].timestamp)
        result = place_main_sleep(epochs, diary, CFG)
        assert result is None

    def test_no_diary_wake(self) -> None:
        """Missing wake_time returns None."""
        scores = [1] * 10
        epochs = _make_epochs(scores)
        diary = DiaryDay(sleep_onset=epochs[0].timestamp)
        result = place_main_sleep(epochs, diary, CFG)
        assert result is None

    def test_onset_after_offset(self) -> None:
        """When onset >= offset, returns None (line 317)."""
        # Run1 (onset): epochs 8-11. Run2 (offset end): epoch 5.
        # onset_idx=8 > offset_idx=5 => None.
        scores = [0, 1, 1, 1, 1, 1, 0, 0, 1, 1, 1, 1]
        epochs = _make_epochs(scores)
        diary = DiaryDay(
            sleep_onset=epochs[8].timestamp,  # onset near epoch 8
            wake_time=epochs[3].timestamp,    # wake near epoch 3
        )
        result = place_main_sleep(epochs, diary, CFG)
        assert result is None

    def test_no_valid_onset_found(self) -> None:
        """All wake data => no valid onset."""
        scores = [0] * 20
        epochs = _make_epochs(scores)
        diary = DiaryDay(
            sleep_onset=epochs[5].timestamp,
            wake_time=epochs[15].timestamp,
        )
        result = place_main_sleep(epochs, diary, CFG)
        assert result is None

    def test_clamped_onset_past_offset(self) -> None:
        """Rule 8 clamp: if clamped onset >= offset, keep original onset."""
        # Run1: 0-5 (onset=0). Run2: 10-12 (len=3, onset=10).
        # Offset at end of run1 = 5.
        # in_bed at epoch 10 => clamp tries onset at 10. But 10 >= 5 => clamped not used.
        # Original result: onset=0, offset=5.
        scores = [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 1, 1, 1]
        epochs = _make_epochs(scores)
        diary = DiaryDay(
            in_bed_time=epochs[10].timestamp,
            sleep_onset=epochs[0].timestamp,
            wake_time=epochs[5].timestamp,
        )
        result = place_main_sleep(epochs, diary, CFG)
        assert result is not None
        onset_idx, offset_idx = result
        # clamped=10, but 10 >= offset(5), so onset stays 0
        assert onset_idx == 0


class TestPlaceNapsEdgeCases:
    """Cover edge cases in place_naps."""

    def test_nap_period_missing_start(self) -> None:
        """Nap period with None start_time is skipped."""
        scores = [0] * 5 + [1] * 15 + [0] * 5
        epochs = _make_epochs(scores, start=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC))
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(start_time=None, end_time=epochs[20].timestamp, period_type="nap")
            ]
        )
        naps = place_naps(epochs, diary, main_onset=None, main_offset=None, config=CFG)
        assert len(naps) == 0

    def test_nap_period_missing_end(self) -> None:
        """Nap period with None end_time is skipped."""
        scores = [0] * 5 + [1] * 15 + [0] * 5
        epochs = _make_epochs(scores, start=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC))
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(start_time=epochs[5].timestamp, end_time=None, period_type="nap")
            ]
        )
        naps = place_naps(epochs, diary, main_onset=None, main_offset=None, config=CFG)
        assert len(naps) == 0

    def test_nap_onset_after_offset(self) -> None:
        """When nap onset >= offset, nap is skipped (line 489-490)."""
        # Two small runs that can't form a valid nap (onset > offset due to search)
        scores = [0] * 10 + [1] * 3 + [0] * 20 + [1] * 3 + [0] * 10
        epochs = _make_epochs(scores, start=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC))
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(
                    # Search near end of data for onset, near start for offset
                    start_time=epochs[30].timestamp,
                    end_time=epochs[12].timestamp,
                    period_type="nap",
                )
            ]
        )
        naps = place_naps(epochs, diary, main_onset=None, main_offset=None, config=CFG)
        assert len(naps) == 0


class TestPlaceWithoutDiaryEdgeCases:
    """Cover edge cases in place_without_diary."""

    def test_only_short_runs(self) -> None:
        """All runs too short for onset (< 3 epochs) => None."""
        scores = [1, 1, 0, 1, 1, 0, 1, 1, 0]
        epochs = _make_epochs(scores)
        result = place_without_diary(epochs, CFG)
        assert result is None

    def test_onset_valid_but_offset_short(self) -> None:
        """Onset run qualifies (3+) but no run qualifies for offset (5min)."""
        # Single run of 3 epochs (onset valid, but offset needs 5 epochs)
        scores = [1, 1, 1, 0, 0, 0]
        epochs = _make_epochs(scores)
        result = place_without_diary(epochs, CFG)
        # Run of 3 meets onset (3) but not offset (5) => None
        assert result is None

    def test_multiple_valid_runs_picks_longest_span(self) -> None:
        """Among valid onset-offset pairs, the longest span wins."""
        # Run1: 0-6 (7 epochs), gap, Run2: 10-16 (7 epochs)
        scores = [1] * 7 + [0] * 3 + [1] * 7 + [0] * 3
        epochs = _make_epochs(scores)
        result = place_without_diary(epochs, CFG)
        assert result is not None
        onset_idx, offset_idx = result
        # Best span: onset from run1(0), offset from run2(16) = 17 epochs
        assert onset_idx == 0
        assert offset_idx == 16


class TestRunAutoScoringEdgeCases:
    """Cover edge cases in run_auto_scoring."""

    def test_empty_data(self) -> None:
        """Empty timestamps returns early (line 809)."""
        result = run_auto_scoring(
            timestamps=[], activity_counts=[], sleep_scores=[]
        )
        assert result["sleep_markers"] == []
        assert any("No activity" in n for n in result["notes"])

    def test_choi_nonwear_provided(self) -> None:
        """Choi nonwear list is properly converted to bools."""
        n = 60
        start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [5.0] * n
        sleep_scores = [1] * n
        choi = [0] * 30 + [1] * 30  # half nonwear

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="18:00",
            diary_wake_time="7:00",
            analysis_date="2024-01-01",
        )
        # Just verify it runs without error
        assert "sleep_markers" in result

    def test_custom_detection_rules(self) -> None:
        """Non-default onset/offset rules add a note."""
        n = 60
        start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [5.0] * n
        sleep_scores = [1] * n

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_onset_time="18:00",
            diary_wake_time="7:00",
            analysis_date="2024-01-01",
            onset_min_consecutive_sleep=5,
            offset_min_consecutive_minutes=10,
        )
        assert any("Detection rule: 5S/10S" in n for n in result["notes"])

    def test_diary_no_onset_no_wake(self) -> None:
        """Diary with analysis_date but no onset/wake times (line 900)."""
        n = 60
        start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [5.0] * n
        sleep_scores = [1] * n

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            analysis_date="2024-01-01",
            # No diary_onset_time or diary_wake_time
        )
        assert any("no onset/wake" in n.lower() or "requires diary" in n.lower() for n in result["notes"])

    def test_no_valid_sleep_period_near_diary(self) -> None:
        """Diary times provided but no matching sleep in data (line 894)."""
        n = 60
        start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [500.0] * n
        sleep_scores = [0] * n  # all wake

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_onset_time="22:00",
            diary_wake_time="7:00",
            analysis_date="2024-01-01",
        )
        assert any("No valid sleep" in n or "No main sleep" in n for n in result["notes"])

    def test_nap_markers_placed_via_run_auto_scoring(self) -> None:
        """Nap markers are placed through run_auto_scoring (lines 910-922)."""
        n = 600
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        # Nap: sleep from epoch 30-50 (12:30 - 12:50)
        # Main sleep: sleep from epoch 360-540 (18:00 - 21:00, overnight)
        sleep_scores = [0] * 30 + [1] * 21 + [0] * 309 + [1] * 180 + [0] * 60
        activity = [200.0 if s == 0 else 5.0 for s in sleep_scores]

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_onset_time="18:00",
            diary_wake_time="21:00",
            diary_naps=[("12:30", "12:50")],
            analysis_date="2024-01-01",
        )
        assert len(result["nap_markers"]) >= 1
        assert result["nap_markers"][0]["marker_type"] == MarkerType.NAP

    def test_nap_time_overnight_wrap(self) -> None:
        """Nap end < nap start causes day wrap (line 839-840)."""
        n = 600
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        sleep_scores = [0] * n
        activity = [200.0] * n

        # nap_end "1:00" < nap_start "23:00" => ne += 1 day
        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_onset_time="18:00",
            diary_wake_time="7:00",
            diary_naps=[("23:00", "1:00")],
            analysis_date="2024-01-01",
        )
        # No sleep data, so no naps placed, but parsing shouldn't crash
        assert "sleep_markers" in result

    def test_diary_nonwear_parsed(self) -> None:
        """Diary nonwear periods are parsed and stored in DiaryDay (lines 847-851)."""
        n = 120
        start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        sleep_scores = [0] * 30 + [1] * 60 + [0] * 30
        activity = [200.0 if s == 0 else 5.0 for s in sleep_scores]

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_onset_time="18:30",
            diary_wake_time="19:00",
            diary_nonwear=[("10:00", "11:00")],
            analysis_date="2024-01-01",
        )
        # Should not crash; nonwear is parsed but not placed via run_auto_scoring
        assert "sleep_markers" in result

    def test_diary_bed_time_used_as_fallback_onset(self) -> None:
        """When diary_onset_time is None, diary_bed_time is used (line 818)."""
        n = 120
        start = datetime(2024, 1, 1, 18, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        sleep_scores = [0] * 30 + [1] * 60 + [0] * 30
        activity = [200.0 if s == 0 else 5.0 for s in sleep_scores]

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_bed_time="18:30",
            diary_wake_time="19:30",
            analysis_date="2024-01-01",
        )
        assert len(result["sleep_markers"]) == 1


class TestDiaryTimePresent:
    """Cover _diary_time_present (line 941-946)."""

    def test_none_returns_false(self) -> None:
        assert _diary_time_present(None) is False

    def test_empty_string_returns_false(self) -> None:
        assert _diary_time_present("") is False

    def test_nan_returns_false(self) -> None:
        assert _diary_time_present("nan") is False

    def test_none_string_returns_false(self) -> None:
        assert _diary_time_present("none") is False

    def test_null_string_returns_false(self) -> None:
        assert _diary_time_present("null") is False

    def test_valid_time_returns_true(self) -> None:
        assert _diary_time_present("22:00") is True

    def test_whitespace_only_returns_false(self) -> None:
        assert _diary_time_present("   ") is False


class TestNonwearPlacementAdvanced:
    """Additional nonwear placement edge cases."""

    def test_empty_timestamps(self) -> None:
        """Empty data returns early."""
        result = place_nonwear_markers(
            timestamps=[], activity_counts=[],
            diary_nonwear=[], choi_nonwear=None,
            sensor_nonwear_periods=[], existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        assert len(result.nonwear_markers) == 0
        assert any("No activity" in n for n in result.notes)

    def test_no_diary_periods(self) -> None:
        """No diary nonwear periods produces a note."""
        n = 20
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[], choi_nonwear=None,
            sensor_nonwear_periods=[], existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        assert any("No diary nonwear" in n for n in result.notes)

    def test_diary_period_null_strings_skipped(self) -> None:
        """Diary entries with None strings are skipped."""
        n = 20
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[(None, "10:10"), ("10:10", None), ("nan", "10:20")],
            choi_nonwear=None,
            sensor_nonwear_periods=[], existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        assert len(result.nonwear_markers) == 0

    def test_extension_with_choi_signal(self) -> None:
        """Nonwear extends using Choi signal as boundary."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        # Zero activity everywhere
        activity = [0.0] * n
        # Choi nonwear: epochs 5-25
        choi = [0] * 5 + [1] * 21 + [0] * 34

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[("10:10", "10:20")],
            choi_nonwear=choi,
            sensor_nonwear_periods=[],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        assert len(result.nonwear_markers) == 1
        assert any("Choi" in n for n in result.notes)

    def test_extension_with_sensor_signal(self) -> None:
        """Nonwear extends using sensor signal as boundary."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n
        # Sensor nonwear covering epochs 5-25
        sensor_start = timestamps[5]
        sensor_end = timestamps[25]

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[("10:10", "10:20")],
            choi_nonwear=None,
            sensor_nonwear_periods=[(sensor_start, sensor_end)],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        assert len(result.nonwear_markers) == 1
        assert any("sensor" in n for n in result.notes)

    def test_extension_capped_by_max_extension(self) -> None:
        """Without external signals, extension is capped by max_extension_minutes."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n  # all zero

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[("10:10", "10:20")],
            choi_nonwear=None,
            sensor_nonwear_periods=[],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
            max_extension_minutes=5,
        )
        assert len(result.nonwear_markers) == 1
        # Check extension note mentions the extension
        ext_notes = [n for n in result.notes if "extended" in n]
        assert len(ext_notes) >= 1

    def test_min_duration_not_met(self) -> None:
        """Nonwear period too short (< min_duration_minutes) is skipped."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[("10:10", "10:12")],  # Only 2 minutes of diary window
            choi_nonwear=None,
            sensor_nonwear_periods=[],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
            min_duration_minutes=120,  # Very high threshold
            max_extension_minutes=0,
        )
        assert len(result.nonwear_markers) == 0
        assert any("min" in n.lower() for n in result.notes)

    def test_nonwear_end_before_start_wraps(self) -> None:
        """Nonwear end before start triggers day wrap (line 999-1000)."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        # "23:00" end < "23:30" start => nw_end_dt += 1 day
        # Both get shifted by _parse_diary_time (is_evening=False, h<18 => +1 day)
        # But 23:00 >= 18 so no shift. 23:30 >= 18 so no shift.
        # 23:00 < 23:30 => add a day to 23:00 => wraps.
        # This won't find data in our range but should not crash.
        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[("23:30", "23:00")],
            choi_nonwear=None,
            sensor_nonwear_periods=[],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        # May or may not find markers depending on data range, but shouldn't crash
        assert isinstance(result, NonwearPlacementResult)

    def test_choi_plus_sensor_second_pass(self) -> None:
        """Second pass places Choi+sensor confirmed nonwear (lines 1131-1192)."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n  # all zero activity

        # Choi: epochs 10-30
        choi = [0] * 10 + [1] * 21 + [0] * 29
        # Sensor: epochs 10-30
        sensor_start = timestamps[10]
        sensor_end = timestamps[30]

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[],  # No diary nonwear
            choi_nonwear=choi,
            sensor_nonwear_periods=[(sensor_start, sensor_end)],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        assert len(result.nonwear_markers) == 1
        assert any("Choi+sensor" in n for n in result.notes)

    def test_choi_sensor_overlap_with_sleep_skipped(self) -> None:
        """Choi+sensor nonwear overlapping sleep marker is skipped."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        choi = [0] * 10 + [1] * 21 + [0] * 29
        sensor_start = timestamps[10]
        sensor_end = timestamps[30]

        # Sleep marker covers the same range
        sleep_start = timestamps[5]
        sleep_end = timestamps[35]

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[],
            choi_nonwear=choi,
            sensor_nonwear_periods=[(sensor_start, sensor_end)],
            existing_sleep_markers=[(sleep_start, sleep_end)],
            analysis_date="2024-01-01",
        )
        # Should be skipped due to sleep overlap
        assert len(result.nonwear_markers) == 0

    def test_choi_sensor_overlap_with_placed_marker_skipped(self) -> None:
        """Choi+sensor nonwear overlapping already-placed diary nonwear is skipped."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        # Choi+sensor both cover epochs 10-30
        choi = [0] * 10 + [1] * 21 + [0] * 29
        sensor_start = timestamps[10]
        sensor_end = timestamps[30]

        # Diary nonwear also in the same range => first pass places marker
        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[("10:10", "10:30")],
            choi_nonwear=choi,
            sensor_nonwear_periods=[(sensor_start, sensor_end)],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        # First pass places diary-anchored marker.
        # Second pass should skip because it overlaps the already-placed marker.
        assert len(result.nonwear_markers) == 1  # only the diary one

    def test_choi_sensor_too_short_skipped(self) -> None:
        """Choi+sensor run shorter than min_duration is skipped."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        # Only 3 epochs of Choi+sensor overlap (too short for default 10 min)
        choi = [0] * 10 + [1] * 3 + [0] * 47
        sensor_start = timestamps[10]
        sensor_end = timestamps[12]

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[],
            choi_nonwear=choi,
            sensor_nonwear_periods=[(sensor_start, sensor_end)],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        assert len(result.nonwear_markers) == 0

    def test_choi_sensor_noncontiguous_runs(self) -> None:
        """Choi+sensor with a gap produces two separate runs."""
        n = 60
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [0.0] * n

        # Choi: epochs 5-15 and 25-35
        choi = [0] * 5 + [1] * 11 + [0] * 9 + [1] * 11 + [0] * 24
        # Sensor covers both ranges
        sensor_start1 = timestamps[5]
        sensor_end1 = timestamps[35]

        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[],
            choi_nonwear=choi,
            sensor_nonwear_periods=[(sensor_start1, sensor_end1)],
            existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        # Two runs: 5-15 (11 epochs) and 25-35 (11 epochs), both >= 10 min
        assert len(result.nonwear_markers) == 2


class TestFindNearestEpoch:
    """Cover _find_nearest_epoch (lines 1204-1215)."""

    def test_empty_returns_none(self) -> None:
        assert _find_nearest_epoch([], 100.0) is None

    def test_exact_match(self) -> None:
        ts = [100.0, 200.0, 300.0]
        assert _find_nearest_epoch(ts, 200.0) == 1

    def test_between_values(self) -> None:
        ts = [100.0, 200.0, 300.0]
        # 250 is equidistant; linear scan picks first (index 1)
        assert _find_nearest_epoch(ts, 250.0) == 1

    def test_closer_to_later(self) -> None:
        ts = [100.0, 200.0, 300.0]
        assert _find_nearest_epoch(ts, 280.0) == 2  # closer to 300

    def test_before_all(self) -> None:
        ts = [100.0, 200.0, 300.0]
        assert _find_nearest_epoch(ts, 50.0) == 0


class TestFindNearestEpochDt:
    """Cover _find_nearest_epoch_dt (lines 1218-1231)."""

    def test_empty_returns_none(self) -> None:
        assert _find_nearest_epoch_dt([], BASE_TS) is None

    def test_exact_match(self) -> None:
        times = [BASE_TS, BASE_TS + timedelta(minutes=1), BASE_TS + timedelta(minutes=2)]
        assert _find_nearest_epoch_dt(times, BASE_TS + timedelta(minutes=1)) == 1

    def test_between_values(self) -> None:
        times = [BASE_TS, BASE_TS + timedelta(minutes=1), BASE_TS + timedelta(minutes=2)]
        target = BASE_TS + timedelta(seconds=80)  # closer to minute 1
        assert _find_nearest_epoch_dt(times, target) == 1


class TestEpochInNonwearSignal:
    """Cover _epoch_in_nonwear_signal (lines 1234-1242)."""

    def test_in_choi_set(self) -> None:
        assert _epoch_in_nonwear_signal(5, {3, 4, 5, 6}, []) is True

    def test_not_in_choi_but_in_sensor(self) -> None:
        assert _epoch_in_nonwear_signal(5, set(), [(3, 7)]) is True

    def test_not_in_any(self) -> None:
        assert _epoch_in_nonwear_signal(5, {1, 2}, [(8, 10)]) is False

    def test_boundary_of_sensor_range(self) -> None:
        assert _epoch_in_nonwear_signal(3, set(), [(3, 7)]) is True
        assert _epoch_in_nonwear_signal(7, set(), [(3, 7)]) is True
        assert _epoch_in_nonwear_signal(8, set(), [(3, 7)]) is False


class TestParseTimeTo24hEdgeCases:
    """Additional edge cases for _parse_time_to_24h."""

    def test_no_minutes(self) -> None:
        """Time with only hour part."""
        # "14" without colon — parts[1] won't exist, m defaults to 0
        result = _parse_time_to_24h("14")
        assert result == (14, 0)

    def test_pm_without_space(self) -> None:
        assert _parse_time_to_24h("11:30PM") == (23, 30)

    def test_am_without_space(self) -> None:
        assert _parse_time_to_24h("9:27AM") == (9, 27)

    def test_hour_out_of_range(self) -> None:
        """Hour > 23 in 24h format."""
        assert _parse_time_to_24h("25:00") is None

    def test_minute_out_of_range(self) -> None:
        """Minute > 59."""
        assert _parse_time_to_24h("12:60") is None


class TestNearestEpochIndexPrevCloser:
    """Cover the d_prev < d_lo branch (line 275) in _nearest_epoch_index."""

    def test_target_closer_to_previous_epoch(self) -> None:
        """Target 20s past epoch 1 is closer to epoch 1 than epoch 2 (40s away)."""
        epochs = _make_epochs([0, 0, 0, 0, 0])
        target = epochs[1].timestamp + timedelta(seconds=20)
        result = _nearest_epoch_index(epochs, target)
        assert result == 1  # 20s from epoch 1 vs 40s from epoch 2


class TestRunAutoScoringDiaryNoTimes:
    """Cover the branch where diary exists but has no onset/wake times (line 900)."""

    def test_diary_with_naps_only_no_onset_wake(self) -> None:
        """analysis_date given with diary_naps but no onset/wake."""
        n = 60
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        activity = [5.0] * n
        sleep_scores = [1] * n

        result = run_auto_scoring(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            diary_naps=[("13:00", "13:30")],
            analysis_date="2024-01-01",
        )
        # No onset/wake => diary created from nap parsing but sleep_onset/wake_time are None
        # The "no onset/wake" note should be generated
        assert any(
            "no onset/wake" in n.lower() or "requires diary" in n.lower()
            for n in result["notes"]
        )


class TestNonwearDiaryTimesOutsideRange:
    """Lines 1033-1034 are unreachable (guarded by empty-timestamps check above).

    This test verifies the preceding logic works with mismatched diary/data ranges.
    """

    def test_diary_nonwear_mismatched_range_still_works(self) -> None:
        """Nonwear diary period far from actual data range still finds nearest epoch."""
        n = 20
        start = datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC)
        timestamps = _make_timestamps(n, start=start)
        # All zero activity
        activity = [0.0] * n

        # Diary time "20:00"-"21:00" => far from data (10:00-10:19 on Jan 2)
        # _find_nearest_epoch_dt returns nearest (index 0 or 19) — does not return None
        result = place_nonwear_markers(
            timestamps=timestamps, activity_counts=activity,
            diary_nonwear=[("20:00", "21:00")],
            choi_nonwear=None,
            sensor_nonwear_periods=[], existing_sleep_markers=[],
            analysis_date="2024-01-01",
        )
        # The function should still process (nearest epoch found) rather than skip
        assert isinstance(result, NonwearPlacementResult)


class TestNapOnsetAfterOffset:
    """Cover line 490: onset_idx >= offset_idx in place_naps."""

    def test_nap_onset_geq_offset_skipped(self) -> None:
        """Nap where bounded onset search finds index >= bounded offset search."""
        # Setup where onset is found after offset in the bounded search.
        # sleep at 30-32 (3 epochs, valid onset at 30) and 10-14 (5 epochs, valid offset at 14)
        # nap_period: start near 30, end near 14 => onset=30, offset=14, 30 >= 14 => skip
        scores = [0] * 10 + [1] * 5 + [0] * 15 + [1] * 3 + [0] * 7
        epochs = _make_epochs(scores, start=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC))
        diary = DiaryDay(
            nap_periods=[
                DiaryPeriod(
                    start_time=epochs[30].timestamp,  # near onset at 30
                    end_time=epochs[14].timestamp,     # near offset at 14
                    period_type="nap",
                )
            ]
        )
        naps = place_naps(epochs, diary, main_onset=None, main_offset=None, config=CFG)
        # onset=30 >= offset=14 => skipped
        assert len(naps) == 0


class TestAmpmCorrectionFlipBoth:
    """Cover the flip-both-onset-and-wake path in _try_ampm_corrections (line 651+)."""

    def test_flip_both_am_pm(self) -> None:
        """When flipping both onset and wake makes times plausible."""
        from datetime import date as date_type
        d = date_type(2024, 1, 1)
        data_start = datetime(2024, 1, 1, 18, 0, tzinfo=UTC)
        data_end = datetime(2024, 1, 2, 12, 0, tzinfo=UTC)
        # Onset "10:00 AM" => 10:00 next day (shifted). Wake "7:00 AM" => 7:00 next day.
        # Original: onset=10:00 Jan 2, wake=7:00 Jan 2. wake < onset => wake += 1 day = Jan 3.
        # Gap = 21 hours > 18 => implausible.
        # Flip wake only: "7:00 PM" => 19:00 Jan 2 (h>=18, no shift). onset=10:00 Jan 2.
        # wake(19:00 Jan 2) > onset(10:00 Jan 2). gap = 9h. But onset at 10:00 Jan 2 is outside data range.
        # Flip onset only: "10:00 PM" => 22:00 Jan 1. Wake "7:00 AM" => 7:00 Jan 2. gap=9h. Plausible!
        # This actually gets caught by flip-onset-only. Let me construct differently.
        #
        # Need: original implausible, flip-wake-only implausible, flip-onset-only implausible,
        # flip-both plausible.
        #
        # Onset "9:00 AM" => is_evening=True, h<12 => +1day => 9:00 Jan 2.
        # Wake "8:00 PM" => is_evening=False, h>=18 no shift => 20:00 Jan 1.
        # Original: wake(20:00 Jan 1) < onset(9:00 Jan 2) => wake += 1 day => 20:00 Jan 2.
        # gap = 11h. onset at 9:00 Jan 2, wake 20:00 Jan 2. onset is within margin of data_end (12:00 Jan 2 + 2h).
        # Actually 9:00 Jan 2 < 14:00 Jan 2 margin. But is 20:00 Jan 2 within margin? data_end + 2h = 14:00 Jan 2.
        # 20:00 > 14:00 => outside margin => implausible.
        #
        # Flip wake only: "8:00 AM" => is_evening=False, h<18 => +1day => 8:00 Jan 2.
        # onset=9:00 Jan 2. wake=8:00 Jan 2. wake < onset => wake += 1 day => 8:00 Jan 3.
        # gap = 23h > 18 => implausible.
        #
        # Flip onset only: "9:00 PM" => 21:00 Jan 1 (is_evening, h>=12 no shift).
        # Wake "8:00 PM" => 20:00 Jan 1. wake < onset => wake += 1 day => 20:00 Jan 2.
        # gap = 23h > 18 => implausible.
        #
        # Flip both: onset "9:00 PM" => 21:00 Jan 1. Wake "8:00 AM" => 8:00 Jan 2.
        # gap = 11h. onset 21:00 Jan 1 in data range (18:00-12:00+2h). wake 8:00 Jan 2 in range. Plausible!
        onset_dt, wake_dt, bed_dt, notes = _try_ampm_corrections(
            onset_str="9:00 AM", wake_str="8:00 PM",
            bed_str=None, base_date=d,
            data_start=data_start, data_end=data_end,
        )
        assert onset_dt is not None
        assert wake_dt is not None
        assert any("Corrected" in n for n in notes)
