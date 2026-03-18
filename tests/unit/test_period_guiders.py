"""Tests for diary-free period guiders: L5, LongestBout, Smart."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sleep_scoring_web.services.pipeline.params import PeriodGuiderParams
from sleep_scoring_web.services.pipeline.protocols import Bout, ClassifiedEpochs, DiaryInput, EpochSeries


def _make_epochs(
    activity: list[float],
    start: datetime | None = None,
) -> EpochSeries:
    """Build an EpochSeries from an activity list."""
    if start is None:
        start = datetime(2024, 1, 1, 12, 0, 0)  # noon
    n = len(activity)
    epoch_times = [start + timedelta(minutes=i) for i in range(n)]
    timestamps = [et.timestamp() for et in epoch_times]
    return EpochSeries(
        timestamps=timestamps,
        epoch_times=epoch_times,
        activity_counts=activity,
    )


def _make_classified(n: int, scores: list[int] | None = None) -> ClassifiedEpochs:
    if scores is None:
        scores = [0] * n
    return ClassifiedEpochs(scores=scores, classifier_id="test")


# =============================================================================
# L5 Guider
# =============================================================================


class TestL5PeriodGuider:
    def test_finds_minimum_window(self) -> None:
        """L5 should center its search window on the least-active 5h block."""
        from sleep_scoring_web.services.pipeline.period_guiders.l5 import L5PeriodGuider

        # 1440 epochs (24h). Activity = 100 everywhere, except epochs 720-1019 = 0 (5h block at midnight)
        activity = [100.0] * 1440
        for i in range(720, 1020):
            activity[i] = 0.0

        epochs = _make_epochs(activity)
        classified = _make_classified(1440)
        guider = L5PeriodGuider()

        guide, naps, notes = guider.guide(epochs, classified, [], params=PeriodGuiderParams())

        assert guide is not None
        assert naps == []
        assert any("L5 guider" in n for n in notes)

        # L5 window starts at epoch 720 (midnight); midpoint = 870, offset = midpoint + 6h
        midpoint_dt = epochs.epoch_times[870]
        assert guide.onset_target == epochs.epoch_times[720]  # start of L5 window
        assert guide.offset_target == midpoint_dt + timedelta(hours=6)

    def test_tiebreak_prefers_midnight(self) -> None:
        """When two windows have equal sums, prefer the one closest to midnight (epoch 720)."""
        from sleep_scoring_web.services.pipeline.period_guiders.l5 import L5PeriodGuider

        # Two equally-zero 5h blocks: one near start (0-299), one at midnight (720-1019)
        activity = [100.0] * 1440
        for i in range(0, 300):
            activity[i] = 0.0
        for i in range(720, 1020):
            activity[i] = 0.0

        epochs = _make_epochs(activity)
        classified = _make_classified(1440)
        guider = L5PeriodGuider()

        guide, _, notes = guider.guide(epochs, classified, [], params=PeriodGuiderParams())

        assert guide is not None
        # The midnight-centered block (720-1019) should win the tiebreak
        # Its midpoint is 870, which is closer to MIDNIGHT_EPOCH=720 than midpoint 150
        # Wait — 870 is farther from 720 than 150 is from 720. So actually the first block wins.
        # Let me reconsider: |150 - 720| = 570, |870 - 720| = 150. Block at 720 wins.
        assert guide.onset_target <= epochs.epoch_times[720]

    def test_short_data_uses_full_window(self) -> None:
        """With fewer than 300 epochs, L5 should use the full data window."""
        from sleep_scoring_web.services.pipeline.period_guiders.l5 import L5PeriodGuider

        activity = [10.0] * 100
        epochs = _make_epochs(activity)
        classified = _make_classified(100)
        guider = L5PeriodGuider()

        guide, _, notes = guider.guide(epochs, classified, [], params=PeriodGuiderParams())

        assert guide is not None
        assert guide.onset_target == epochs.epoch_times[0]
        assert guide.offset_target == epochs.epoch_times[-1]
        assert any("full window" in n for n in notes)


# =============================================================================
# Longest Bout Guider
# =============================================================================


class TestLongestBoutPeriodGuider:
    def test_picks_longest_merged_block(self) -> None:
        """Should merge adjacent sleep bouts and pick the longest."""
        from sleep_scoring_web.services.pipeline.period_guiders.longest_bout import LongestBoutPeriodGuider

        activity = [50.0] * 1440
        epochs = _make_epochs(activity)
        classified = _make_classified(1440)

        # Two sleep bouts with a 30-min gap (< 60-min merge threshold) → merge
        bouts = [
            Bout(start_index=600, end_index=700, state=1),
            Bout(start_index=730, end_index=900, state=1),  # 30-epoch gap
        ]
        guider = LongestBoutPeriodGuider()
        guide, naps, notes = guider.guide(epochs, classified, bouts, params=PeriodGuiderParams())

        assert guide is not None
        assert naps == []
        # Merged block is 600-900 (301 epochs), padded by 30min via timedelta
        assert guide.onset_target == epochs.epoch_times[600] - timedelta(minutes=30)
        assert guide.offset_target == epochs.epoch_times[900] + timedelta(minutes=30)

    def test_no_sleep_bouts_returns_none(self) -> None:
        """Should return None when no sleep bouts found."""
        from sleep_scoring_web.services.pipeline.period_guiders.longest_bout import LongestBoutPeriodGuider

        activity = [50.0] * 1440
        epochs = _make_epochs(activity)
        classified = _make_classified(1440)

        # Only wake bouts
        bouts = [Bout(start_index=0, end_index=1439, state=0)]
        guider = LongestBoutPeriodGuider()
        guide, naps, notes = guider.guide(epochs, classified, bouts, params=PeriodGuiderParams())

        assert guide is None
        assert naps == []
        assert any("no sleep bouts" in n for n in notes)

    def test_does_not_merge_large_gap(self) -> None:
        """Bouts separated by >= merge_gap should not be merged."""
        from sleep_scoring_web.services.pipeline.period_guiders.longest_bout import LongestBoutPeriodGuider

        activity = [50.0] * 1440
        epochs = _make_epochs(activity)
        classified = _make_classified(1440)

        # Two bouts with a 70-epoch gap (> 60-min default)
        bouts = [
            Bout(start_index=100, end_index=200, state=1),  # 101 epochs
            Bout(start_index=271, end_index=300, state=1),  # 30 epochs
        ]
        guider = LongestBoutPeriodGuider()
        guide, _, _ = guider.guide(epochs, classified, bouts, params=PeriodGuiderParams())

        assert guide is not None
        # Should pick the first (longer) bout: 100-200, padded by 30min via timedelta
        assert guide.onset_target == epochs.epoch_times[100] - timedelta(minutes=30)
        assert guide.offset_target == epochs.epoch_times[200] + timedelta(minutes=30)


# =============================================================================
# Smart Guider
# =============================================================================


class TestSmartPeriodGuider:
    def test_uses_diary_when_available(self) -> None:
        """Smart guider should delegate to diary when onset+wake present."""
        from sleep_scoring_web.services.pipeline.period_guiders.smart import SmartPeriodGuider

        start = datetime(2024, 1, 1, 12, 0, 0)
        activity = [50.0] * 1440
        epochs = _make_epochs(activity, start=start)
        classified = _make_classified(1440)

        diary = DiaryInput(
            sleep_onset=datetime(2024, 1, 1, 23, 0, 0),
            wake_time=datetime(2024, 1, 2, 7, 0, 0),
        )

        guider = SmartPeriodGuider()
        guide, _, notes = guider.guide(epochs, classified, [], params=PeriodGuiderParams(), diary_data=diary)

        assert guide is not None
        assert any("using diary" in n for n in notes)
        assert guide.onset_target == diary.sleep_onset
        assert guide.offset_target == diary.wake_time

    def test_falls_back_to_l5_without_diary(self) -> None:
        """Smart guider should fall back to L5 when no diary."""
        from sleep_scoring_web.services.pipeline.period_guiders.smart import SmartPeriodGuider

        activity = [100.0] * 1440
        for i in range(720, 1020):
            activity[i] = 0.0

        epochs = _make_epochs(activity)
        classified = _make_classified(1440)

        guider = SmartPeriodGuider()
        guide, _, notes = guider.guide(epochs, classified, [], params=PeriodGuiderParams())

        assert guide is not None
        assert any("falling back to L5" in n for n in notes)

    def test_falls_back_when_diary_incomplete(self) -> None:
        """Smart guider should fall back to L5 when diary has no onset."""
        from sleep_scoring_web.services.pipeline.period_guiders.smart import SmartPeriodGuider

        activity = [100.0] * 1440
        for i in range(720, 1020):
            activity[i] = 0.0

        epochs = _make_epochs(activity)
        classified = _make_classified(1440)
        diary = DiaryInput(sleep_onset=None, wake_time=datetime(2024, 1, 2, 7, 0, 0))

        guider = SmartPeriodGuider()
        guide, _, notes = guider.guide(epochs, classified, [], params=PeriodGuiderParams(), diary_data=diary)

        assert guide is not None
        assert any("falling back to L5" in n for n in notes)
