#!/usr/bin/env python3
"""Unit tests for DailySleepMarkers dataclass functionality."""

from __future__ import annotations

import pytest

from sleep_scoring_app.core.dataclasses import DailySleepMarkers, MarkerType, SleepPeriod


@pytest.mark.unit
@pytest.mark.gui
class TestDailySleepMarkers:
    """Test DailySleepMarkers dataclass functionality."""

    def test_daily_sleep_markers_empty_initialization(self):
        """Test initializing empty DailySleepMarkers."""
        markers = DailySleepMarkers()

        assert markers.period_1 is None
        assert markers.period_2 is None
        assert markers.period_3 is None
        assert markers.period_4 is None

    def test_daily_sleep_markers_get_complete_periods(self, sample_sleep_markers):
        """Test getting complete periods."""
        markers = DailySleepMarkers()

        # Add complete period
        complete_period = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"],
            offset_timestamp=sample_sleep_markers["offset"],
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        markers.period_1 = complete_period

        # Add incomplete period
        incomplete_period = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"] + 3600,
            offset_timestamp=None,
            marker_index=2,
            marker_type=MarkerType.NAP,
        )
        markers.period_2 = incomplete_period

        complete_periods = markers.get_complete_periods()

        assert len(complete_periods) == 1
        assert complete_periods[0].is_complete

    def test_daily_sleep_markers_get_main_sleep(self, sample_sleep_markers):
        """Test getting main sleep period (longest duration)."""
        markers = DailySleepMarkers()

        # Add shorter nap (2 hours)
        nap = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"],
            offset_timestamp=sample_sleep_markers["onset"] + 7200,  # 2 hours
            marker_index=1,
            marker_type=MarkerType.NAP,
        )
        markers.period_1 = nap

        # Add longer main sleep (8 hours) - this should be returned as main sleep
        main_sleep = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"] + 10000,
            offset_timestamp=sample_sleep_markers["onset"] + 10000 + 28800,  # 8 hours
            marker_index=2,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        markers.period_2 = main_sleep

        retrieved_main = markers.get_main_sleep()

        # get_main_sleep returns the LONGEST period, which is main_sleep
        assert retrieved_main == main_sleep

    def test_daily_sleep_markers_get_naps(self, sample_sleep_markers):
        """Test getting nap periods (all periods except the longest one)."""
        markers = DailySleepMarkers()

        # Add two shorter periods (naps) - 1 hour each
        nap1 = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"],
            offset_timestamp=sample_sleep_markers["onset"] + 3600,  # 1 hour
            marker_index=1,
            marker_type=MarkerType.NAP,
        )
        markers.period_1 = nap1

        nap2 = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"] + 5000,
            offset_timestamp=sample_sleep_markers["onset"] + 5000 + 3600,  # 1 hour
            marker_index=2,
            marker_type=MarkerType.NAP,
        )
        markers.period_2 = nap2

        # Add longest period (main sleep) - 8 hours
        main_sleep = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"] + 20000,
            offset_timestamp=sample_sleep_markers["onset"] + 20000 + 28800,  # 8 hours
            marker_index=3,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        markers.period_3 = main_sleep

        # get_naps returns all periods EXCEPT the longest (main sleep)
        naps = markers.get_naps()

        assert len(naps) == 2
        # Both naps should be the shorter periods
        assert nap1 in naps
        assert nap2 in naps
        assert main_sleep not in naps

    def test_sleep_period_is_complete_property(self, sample_sleep_markers):
        """Test SleepPeriod.is_complete property."""
        # Complete period
        complete = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"],
            offset_timestamp=sample_sleep_markers["offset"],
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        assert complete.is_complete is True

        # Incomplete period (no offset)
        incomplete = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"],
            offset_timestamp=None,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        assert incomplete.is_complete is False

    def test_sleep_period_duration_calculation(self, sample_sleep_markers):
        """Test SleepPeriod duration calculation."""
        period = SleepPeriod(
            onset_timestamp=sample_sleep_markers["onset"],
            offset_timestamp=sample_sleep_markers["offset"],
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        # Duration should be 8 hours = 28800 seconds
        expected_duration = 8 * 3600
        assert abs(period.offset_timestamp - period.onset_timestamp - expected_duration) < 1
