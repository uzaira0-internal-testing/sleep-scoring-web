"""
Unit tests for night complexity scoring.

Tests compute_pre_complexity and compute_post_complexity with synthetic data.
Pure computation — no DB, no HTTP, no async.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta

import pytest

from sleep_scoring_web.services.complexity import (
    compute_post_complexity,
    compute_pre_complexity,
)

# ---------------------------------------------------------------------------
# Helpers to build synthetic night data
# ---------------------------------------------------------------------------

ANALYSIS_DATE = "2025-06-15"  # arbitrary; night window = 2025-06-15 21:00 to 2025-06-16 09:00
_DATE_OBJ = datetime.strptime(ANALYSIS_DATE, "%Y-%m-%d").date()
_NIGHT_START_DT = datetime.combine(_DATE_OBJ, datetime.min.time()) + timedelta(hours=21)
_NIGHT_START_TS = float(calendar.timegm(_NIGHT_START_DT.timetuple()))
EPOCH_SEC = 60.0  # 1-minute epochs


def _make_timestamps(n: int, start_ts: float = _NIGHT_START_TS) -> list[float]:
    """Generate n timestamps at 60-second intervals starting at start_ts."""
    return [start_ts + i * EPOCH_SEC for i in range(n)]


def _make_clear_sleep_night(n: int = 480) -> tuple[list[float], list[float], list[int], list[int]]:
    """
    Build a textbook clear-sleep night (480 epochs = 8 hours starting at 21:00).

    Pattern: 30 min wake -> 7 hours sleep -> 30 min wake.
    Activity: high during wake, near-zero during sleep.
    Choi nonwear: all zeros (device worn the whole time).
    """
    timestamps = _make_timestamps(n)
    activity: list[float] = []
    sleep_scores: list[int] = []
    choi: list[int] = [0] * n

    for i in range(n):
        if i < 30 or i >= 450:
            # Wake periods at start and end
            activity.append(200.0)
            sleep_scores.append(0)
        else:
            # Solid sleep in the middle
            activity.append(0.0)
            sleep_scores.append(1)

    return timestamps, activity, sleep_scores, choi


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPreComplexityCompleteDiary:
    """Complete diary data should produce a score in the 0-100 range."""

    def test_complete_diary_returns_valid_score(self) -> None:
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="22:00",
            diary_wake_time="6:30 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        assert 0 <= score <= 100, f"Score {score} outside valid range"
        assert "total_penalty" in features
        assert features["total_penalty"] != "N/A"


class TestPreComplexityMissingDiary:
    """Missing onset or wake in the diary should return -1."""

    def test_missing_onset_returns_minus_one(self) -> None:
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time=None,
            diary_wake_time="7:00 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        assert score == -1
        assert features["missing_onset"] is True

    def test_missing_wake_returns_minus_one(self) -> None:
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="22:00",
            diary_wake_time=None,
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        assert score == -1
        assert features["missing_wake"] is True

    def test_both_missing_returns_minus_one(self) -> None:
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time=None,
            diary_wake_time=None,
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        assert score == -1
        assert features["no_diary"] is True


class TestPreComplexityNonwearOverlap:
    """Diary-reported nonwear overlapping diary-reported sleep should return -1."""

    def test_diary_nonwear_overlaps_sleep_returns_minus_one(self) -> None:
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        # Nonwear period 1:00 AM - 3:00 AM falls entirely within 22:00 - 06:30
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="22:00",
            diary_wake_time="6:30 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
            diary_nonwear_times=[("1:00 AM", "3:00 AM")],
        )
        assert score == -1
        assert features.get("diary_nonwear_overlaps_sleep") is True


class TestPreComplexityHighTransitions:
    """High activity transitions should drive a higher penalty (lower score)."""

    def test_fragmented_night_scores_lower_than_clear_night(self) -> None:
        n = 480
        timestamps = _make_timestamps(n)
        choi = [0] * n

        # Clear night: 30 wake -> 420 sleep -> 30 wake
        clear_activity: list[float] = []
        clear_sleep: list[int] = []
        for i in range(n):
            if i < 30 or i >= 450:
                clear_activity.append(200.0)
                clear_sleep.append(0)
            else:
                clear_activity.append(0.0)
                clear_sleep.append(1)

        clear_score, _ = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=clear_activity,
            sleep_scores=clear_sleep,
            choi_nonwear=choi,
            diary_onset_time="21:30",
            diary_wake_time="6:30 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )

        # Fragmented night: alternating 5-epoch runs of sleep/wake
        frag_activity: list[float] = []
        frag_sleep: list[int] = []
        for i in range(n):
            if i < 30 or i >= 450:
                frag_activity.append(200.0)
                frag_sleep.append(0)
            else:
                # Alternate every 5 epochs
                is_sleep = (i // 5) % 2 == 0
                frag_sleep.append(1 if is_sleep else 0)
                frag_activity.append(0.0 if is_sleep else 100.0)

        frag_score, _ = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=frag_activity,
            sleep_scores=frag_sleep,
            choi_nonwear=choi,
            diary_onset_time="21:30",
            diary_wake_time="6:30 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )

        assert frag_score < clear_score, (
            f"Fragmented score ({frag_score}) should be lower than clear score ({clear_score})"
        )


class TestPreComplexityClearSleepPattern:
    """A textbook clear sleep pattern should yield a high complexity score."""

    def test_clear_sleep_high_score(self) -> None:
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="21:30",
            diary_wake_time="6:30 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        # A textbook clear night with matching diary should score well
        assert score >= 50, f"Clear night scored only {score}, expected >= 50"


class TestPreComplexityEdgeCases:
    """Edge cases: all-zero activity, single epoch, empty data."""

    def test_all_zero_activity(self) -> None:
        """All-zero activity with all-sleep scores and no Choi nonwear."""
        n = 480
        timestamps = _make_timestamps(n)
        activity = [0.0] * n
        sleep_scores = [1] * n
        choi = [0] * n

        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="21:00",
            diary_wake_time="5:00 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        # Should return a valid score (not crash)
        assert isinstance(score, int)
        assert score == -1 or 0 <= score <= 100

    def test_single_epoch(self) -> None:
        """A single epoch should not crash, though the score may be low or -1."""
        timestamps = _make_timestamps(1)
        activity = [50.0]
        sleep_scores = [1]
        choi = [0]

        score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="22:00",
            diary_wake_time="6:00 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        assert isinstance(score, int)

    def test_empty_data_returns_zero(self) -> None:
        """Empty timestamps/scores returns score 0 with error."""
        score, features = compute_pre_complexity(
            timestamps=[],
            activity_counts=[],
            sleep_scores=[],
            choi_nonwear=[],
            diary_onset_time="22:00",
            diary_wake_time="6:00 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )
        assert score == 0
        assert features.get("error") == "insufficient_data"


class TestPostComplexityMarkerAlignment:
    """Post-complexity adjustments based on marker placement."""

    def test_close_marker_alignment_boosts_score(self) -> None:
        """Markers placed close to algorithm boundaries should boost the score."""
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        pre_score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="21:30",
            diary_wake_time="6:30 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )

        # Place a marker that aligns closely with the algorithm onset/offset.
        # Algorithm sleep runs from epoch 30 (onset) to epoch 449 (offset).
        onset_ts = timestamps[30]
        offset_ts = timestamps[449]
        sleep_markers = [(onset_ts, offset_ts)]

        post_score, post_features = compute_post_complexity(
            complexity_pre=pre_score,
            features=features,
            sleep_markers=sleep_markers,
            sleep_scores=sleep_scores,
            timestamps=timestamps,
        )
        assert post_features["marker_alignment"] == "close"
        assert post_score >= pre_score, (
            f"Close alignment should boost: post={post_score}, pre={pre_score}"
        )

    def test_far_marker_alignment_reduces_score(self) -> None:
        """Markers placed far from algorithm boundaries should reduce the score."""
        # Use a longer night (600 epochs) with sleep in the middle (100-500)
        # so we can place markers >30 epochs away from algorithm boundaries.
        n = 600
        timestamps = _make_timestamps(n)
        activity: list[float] = []
        sleep_scores: list[int] = []
        choi = [0] * n
        for i in range(n):
            if i < 100 or i >= 500:
                activity.append(200.0)
                sleep_scores.append(0)
            else:
                activity.append(0.0)
                sleep_scores.append(1)

        pre_score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="22:40",
            diary_wake_time="5:20 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )

        # Place a marker far from algorithm boundaries (epoch 100 and 499).
        # Marker at epoch 0 and epoch 599 → 100 epochs away from each boundary.
        far_onset_ts = timestamps[0]
        far_offset_ts = timestamps[-1]
        sleep_markers = [(far_onset_ts, far_offset_ts)]

        post_score, post_features = compute_post_complexity(
            complexity_pre=pre_score,
            features=features,
            sleep_markers=sleep_markers,
            sleep_scores=sleep_scores,
            timestamps=timestamps,
        )
        assert post_features["marker_alignment"] == "far"
        assert post_score <= pre_score, (
            f"Far alignment should reduce: post={post_score}, pre={pre_score}"
        )

    def test_no_markers_returns_pre_score_unchanged(self) -> None:
        """No sleep markers should leave the score unchanged."""
        timestamps, activity, sleep_scores, choi = _make_clear_sleep_night()
        pre_score, features = compute_pre_complexity(
            timestamps=timestamps,
            activity_counts=activity,
            sleep_scores=sleep_scores,
            choi_nonwear=choi,
            diary_onset_time="21:30",
            diary_wake_time="6:30 AM",
            diary_nap_count=0,
            analysis_date=ANALYSIS_DATE,
        )

        post_score, post_features = compute_post_complexity(
            complexity_pre=pre_score,
            features=features,
            sleep_markers=[],
            sleep_scores=sleep_scores,
            timestamps=timestamps,
        )
        assert post_score == max(0, min(100, pre_score))
        assert post_features["post_adjustment"] == 0
