"""
Tests for the marker API endpoints.
"""

from datetime import date

import pytest

from sleep_scoring_web.schemas.models import (
    FullTableDataPoint,
    FullTableResponse,
    OnsetOffsetDataPoint,
    OnsetOffsetTableResponse,
)


class TestOnsetOffsetDataPoint:
    """Tests for the OnsetOffsetDataPoint model."""

    def test_data_point_required_fields(self):
        """Data point should have all required fields."""
        point = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
        )
        assert point.timestamp == 1704067200.0
        assert point.datetime_str == "12:00:00"
        assert point.axis_y == 100
        assert point.vector_magnitude == 150
        assert point.algorithm_result is None
        assert point.choi_result is None
        assert point.is_nonwear is False

    def test_data_point_optional_fields(self):
        """Data point should accept optional algorithm results."""
        point = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
            algorithm_result=1,  # Sleep
            choi_result=0,  # Wear
            is_nonwear=True,
        )
        assert point.algorithm_result == 1
        assert point.choi_result == 0
        assert point.is_nonwear is True

    def test_data_point_algorithm_values(self):
        """Algorithm results should accept valid values."""
        # Sleep result
        point_sleep = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
            algorithm_result=1,
        )
        assert point_sleep.algorithm_result == 1

        # Wake result
        point_wake = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
            algorithm_result=0,
        )
        assert point_wake.algorithm_result == 0


class TestOnsetOffsetTableResponse:
    """Tests for the OnsetOffsetTableResponse model."""

    def test_response_empty_data(self):
        """Response should work with empty data lists."""
        response = OnsetOffsetTableResponse(
            onset_data=[],
            offset_data=[],
            period_index=1,
        )
        assert response.onset_data == []
        assert response.offset_data == []
        assert response.period_index == 1

    def test_response_with_data(self):
        """Response should contain onset and offset data."""
        onset_point = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
        )
        offset_point = OnsetOffsetDataPoint(
            timestamp=1704096000.0,
            datetime_str="20:00:00",
            axis_y=50,
            vector_magnitude=75,
        )

        response = OnsetOffsetTableResponse(
            onset_data=[onset_point],
            offset_data=[offset_point],
            period_index=1,
        )
        assert len(response.onset_data) == 1
        assert len(response.offset_data) == 1
        assert response.onset_data[0].axis_y == 100
        assert response.offset_data[0].axis_y == 50


class TestFullTableDataPoint:
    """Tests for the FullTableDataPoint model."""

    def test_full_data_point_fields(self):
        """Full table data point should have all fields."""
        point = FullTableDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
            algorithm_result=1,
            choi_result=0,
            is_nonwear=False,
        )
        assert point.timestamp == 1704067200.0
        assert point.algorithm_result == 1
        assert point.choi_result == 0
        assert point.is_nonwear is False


class TestFullTableResponse:
    """Tests for the FullTableResponse model."""

    def test_full_response_empty(self):
        """Full response should work when empty."""
        response = FullTableResponse(
            data=[],
            total_rows=0,
        )
        assert response.data == []
        assert response.total_rows == 0
        assert response.start_time is None
        assert response.end_time is None

    def test_full_response_with_data(self):
        """Full response should contain data and time range."""
        point = FullTableDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
        )
        response = FullTableResponse(
            data=[point],
            total_rows=1,
            start_time="2024-01-01 12:00:00",
            end_time="2024-01-01 12:00:00",
        )
        assert len(response.data) == 1
        assert response.total_rows == 1
        assert response.start_time == "2024-01-01 12:00:00"
        assert response.end_time == "2024-01-01 12:00:00"


## TestWindowMinutesParameter — REMOVED
# Superseded by tests/web/test_markers_tables.py::test_window_minutes_parameter
# which tests window_minutes via HTTP rather than introspecting a moved function.


class TestAlgorithmIntegration:
    """Tests for algorithm result integration in table data."""

    def test_sadeh_sleep_wake_values(self):
        """Sadeh algorithm should return 0 (wake) or 1 (sleep)."""
        # Sleep = 1
        sleep_point = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=0,  # Low activity typically = sleep
            vector_magnitude=0,
            algorithm_result=1,
        )
        assert sleep_point.algorithm_result == 1

        # Wake = 0
        wake_point = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=1000,  # High activity typically = wake
            vector_magnitude=1000,
            algorithm_result=0,
        )
        assert wake_point.algorithm_result == 0

    def test_choi_nonwear_values(self):
        """Choi algorithm should return 0 (wear) or 1 (nonwear)."""
        # Wear = 0
        wear_point = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
            choi_result=0,
        )
        assert wear_point.choi_result == 0

        # Nonwear = 1
        nonwear_point = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=0,
            vector_magnitude=0,
            choi_result=1,
        )
        assert nonwear_point.choi_result == 1


class TestManualNonwearIntegration:
    """Tests for manual nonwear marker integration."""

    def test_is_nonwear_flag(self):
        """is_nonwear flag should indicate manual marker overlap."""
        # Not in nonwear
        point_wear = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
            is_nonwear=False,
        )
        assert point_wear.is_nonwear is False

        # In nonwear marker
        point_nonwear = OnsetOffsetDataPoint(
            timestamp=1704067200.0,
            datetime_str="12:00:00",
            axis_y=100,
            vector_magnitude=150,
            is_nonwear=True,
        )
        assert point_nonwear.is_nonwear is True
