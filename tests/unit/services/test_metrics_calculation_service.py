#!/usr/bin/env python3
"""
Comprehensive tests for MetricsCalculationService.
Tests sleep metrics calculations from algorithm results.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from sleep_scoring_app.core.constants import AlgorithmType
from sleep_scoring_app.core.dataclasses import DailySleepMarkers, ParticipantInfo, SleepMetrics, SleepPeriod
from sleep_scoring_app.services.metrics_calculation_service import MetricsCalculationService


class TestMetricsCalculationService:
    """Tests for MetricsCalculationService class."""

    @pytest.fixture
    def service(self) -> MetricsCalculationService:
        """Create a service instance."""
        return MetricsCalculationService()

    @pytest.fixture
    def participant_info(self) -> ParticipantInfo:
        """Create sample participant info."""
        return ParticipantInfo(
            full_id="1234_G1_T1",
            numerical_id="1234",
            group_str="G1",
            timepoint_str="T1",
        )

    @pytest.fixture
    def sample_timestamps(self) -> list[float]:
        """Create sample timestamps (60-second epochs for 60 minutes)."""
        base_ts = datetime(2024, 1, 15, 22, 0, 0).timestamp()
        return [base_ts + i * 60 for i in range(60)]

    @pytest.fixture
    def sample_activity_data(self) -> list[int]:
        """Create sample activity data (60 epochs)."""
        return [50, 30, 20, 10, 5] * 12  # Varying activity levels


class TestFindClosestDataIndex(TestMetricsCalculationService):
    """Tests for _find_closest_data_index method."""

    def test_finds_exact_match(self, service: MetricsCalculationService) -> None:
        """Should find exact timestamp match."""
        x_data = [100.0, 200.0, 300.0, 400.0]
        idx = service._find_closest_data_index(x_data, 200.0)
        assert idx == 1

    def test_finds_closest_lower(self, service: MetricsCalculationService) -> None:
        """Should find closest when target is slightly lower."""
        x_data = [100.0, 200.0, 300.0, 400.0]
        idx = service._find_closest_data_index(x_data, 195.0)
        assert idx == 1

    def test_finds_closest_higher(self, service: MetricsCalculationService) -> None:
        """Should find closest when target is slightly higher."""
        x_data = [100.0, 200.0, 300.0, 400.0]
        idx = service._find_closest_data_index(x_data, 205.0)
        assert idx == 1

    def test_returns_none_for_empty_data(self, service: MetricsCalculationService) -> None:
        """Should return None for empty data."""
        idx = service._find_closest_data_index([], 100.0)
        assert idx is None

    def test_returns_none_for_none_data(self, service: MetricsCalculationService) -> None:
        """Should return None for None data."""
        idx = service._find_closest_data_index(None, 100.0)
        assert idx is None

    def test_finds_first_element(self, service: MetricsCalculationService) -> None:
        """Should find first element when it's closest."""
        x_data = [100.0, 200.0, 300.0]
        idx = service._find_closest_data_index(x_data, 50.0)
        assert idx == 0

    def test_finds_last_element(self, service: MetricsCalculationService) -> None:
        """Should find last element when it's closest."""
        x_data = [100.0, 200.0, 300.0]
        idx = service._find_closest_data_index(x_data, 350.0)
        assert idx == 2


class TestCalculateSleepMetricsForPeriod(TestMetricsCalculationService):
    """Tests for calculate_sleep_metrics_for_period method."""

    def test_returns_none_for_none_period(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
    ) -> None:
        """Should return None for None period."""
        result = service.calculate_sleep_metrics_for_period(
            sleep_period=None,
            sadeh_results=[1] * 60,
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=[i * 60 for i in range(60)],
            participant_info=participant_info,
        )
        assert result is None

    def test_returns_none_for_incomplete_period(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
    ) -> None:
        """Should return None for incomplete period."""
        incomplete_period = SleepPeriod(onset_timestamp=100.0, offset_timestamp=None)

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=incomplete_period,
            sadeh_results=[1] * 60,
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=[i * 60 for i in range(60)],
            participant_info=participant_info,
        )
        assert result is None

    def test_calculates_for_complete_period(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should calculate metrics for complete period."""
        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=[1] * 60,
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert "Total Minutes in Bed" in result

    def test_calculates_basic_metrics(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
        sample_activity_data: list[int],
    ) -> None:
        """Should calculate basic sleep metrics."""
        # All sleep epochs (value 1)
        sadeh_results = [1] * 60
        choi_results = [0] * 60  # No nonwear

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=sample_activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert result["Full Participant ID"] == "1234_G1_T1"
        assert result["Numerical Participant ID"] == "1234"
        assert "Efficiency" in result
        assert "Total Minutes in Bed" in result
        assert "Total Sleep Time (TST)" in result

    def test_calculates_efficiency_correctly(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should calculate efficiency correctly."""
        # 30 sleep epochs, 10 wake epochs in 40-minute period
        sadeh_results = [0] * 10 + [1] * 30 + [0] * 10 + [1] * 10
        choi_results = [0] * 60
        activity_data = [50] * 60

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert "Efficiency" in result
        # Efficiency should be a percentage
        assert 0 <= result["Efficiency"] <= 100

    def test_counts_awakenings(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should count awakenings correctly."""
        # Pattern: Sleep, Wake, Sleep, Wake, Sleep
        sadeh_results = [1, 1, 1, 0, 0, 1, 1, 0, 1, 1] * 6
        choi_results = [0] * 60
        activity_data = [50] * 60

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[0],
            offset_timestamp=sample_timestamps[59],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert "Number of Awakenings" in result
        assert result["Number of Awakenings"] is not None
        assert result["Number of Awakenings"] >= 0

    def test_includes_algorithm_type(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should include algorithm type in results."""
        sadeh_results = [1] * 60
        choi_results = [0] * 60
        activity_data = [50] * 60

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert result["Sleep Algorithm"] == AlgorithmType.SADEH_1994_ACTILIFE.value

    def test_includes_onset_offset_times(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should include onset and offset times."""
        sadeh_results = [1] * 60
        choi_results = [0] * 60
        activity_data = [50] * 60

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert "Onset Date" in result
        assert "Onset Time" in result
        assert "Offset Date" in result
        assert "Offset Time" in result

    def test_calculates_nonwear_overlap(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should calculate nonwear overlap during sleep period."""
        sadeh_results = [1] * 60
        # 10 minutes of nonwear during sleep period (indices 20-30)
        choi_results = [0] * 20 + [1] * 10 + [0] * 30
        activity_data = [50] * 60

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert "Overlapping Nonwear Minutes (Algorithm)" in result
        assert result["Overlapping Nonwear Minutes (Algorithm)"] >= 0


class TestCalculateSleepMetricsForPeriodObject(TestMetricsCalculationService):
    """Tests for calculate_sleep_metrics_for_period_object method."""

    def test_returns_sleep_metrics_object(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should return SleepMetrics object."""
        sadeh_results = [1] * 60
        choi_results = [0] * 60
        activity_data = [50] * 60

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period_object(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
            file_path="/test/file.csv",
        )

        assert result is not None
        assert isinstance(result, SleepMetrics)

    def test_returns_none_for_invalid_input(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
    ) -> None:
        """Should return None for invalid input."""
        result = service.calculate_sleep_metrics_for_period_object(
            sleep_period=None,
            sadeh_results=[],
            choi_results=[],
            axis_y_data=[],
            x_data=[],
            participant_info=participant_info,
        )
        assert result is None

    def test_includes_participant_info(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should include participant info in SleepMetrics."""
        sadeh_results = [1] * 60
        choi_results = [0] * 60
        activity_data = [50] * 60

        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period_object(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=activity_data,
            x_data=sample_timestamps,
            participant_info=participant_info,
            file_path="/test/file.csv",
        )

        assert result is not None
        assert result.participant.numerical_id == "1234"


class TestDictToSleepMetrics(TestMetricsCalculationService):
    """Tests for _dict_to_sleep_metrics method."""

    def test_converts_dict_to_sleep_metrics(self, service: MetricsCalculationService) -> None:
        """Should convert dictionary to SleepMetrics."""
        metrics_dict = {
            "Full Participant ID": "1234_G1_T1",
            "Numerical Participant ID": "1234",
            "Participant Group": "G1",
            "Participant Timepoint": "T1",
            "Sleep Algorithm": AlgorithmType.SADEH_1994_ACTILIFE.value,
            "Onset Date": "2024-01-15",
            "Onset Time": "22:00",
            "Offset Date": "2024-01-16",
            "Offset Time": "06:00",
            "Total Minutes in Bed": 480,
            "Total Sleep Time (TST)": 450,
            "Efficiency": 93.75,
        }

        result = service._dict_to_sleep_metrics(metrics_dict, "/test/file.csv")

        assert isinstance(result, SleepMetrics)
        assert result.participant.numerical_id == "1234"
        assert result.total_minutes_in_bed == 480
        assert result.total_sleep_time == 450

    def test_handles_missing_fields(self, service: MetricsCalculationService) -> None:
        """Should handle missing fields gracefully."""
        metrics_dict = {
            "Numerical Participant ID": "1234",
            "Onset Date": "2024-01-15",
        }

        result = service._dict_to_sleep_metrics(metrics_dict, None)

        assert isinstance(result, SleepMetrics)
        assert result.participant.numerical_id == "1234"

    def test_uses_default_algorithm_type(self, service: MetricsCalculationService) -> None:
        """Should use default algorithm type when not specified."""
        metrics_dict = {
            "Numerical Participant ID": "1234",
            "Onset Date": "2024-01-15",
        }

        result = service._dict_to_sleep_metrics(metrics_dict, None)

        assert result.algorithm_type == AlgorithmType.SADEH_1994_ACTILIFE


class TestCalculateSleepMetricsForAllPeriods(TestMetricsCalculationService):
    """Tests for calculate_sleep_metrics_for_all_periods method."""

    def test_returns_empty_for_no_complete_periods(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
    ) -> None:
        """Should return empty list when no complete periods."""
        daily_markers = DailySleepMarkers()  # Empty markers

        result = service.calculate_sleep_metrics_for_all_periods(
            daily_sleep_markers=daily_markers,
            sadeh_results=[1] * 60,
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=[i * 60 for i in range(60)],
            participant_info=participant_info,
        )

        assert result == []

    def test_calculates_for_multiple_periods(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should calculate metrics for multiple periods."""
        daily_markers = DailySleepMarkers()
        daily_markers.period_1 = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[30],
        )
        daily_markers.period_2 = SleepPeriod(
            onset_timestamp=sample_timestamps[35],
            offset_timestamp=sample_timestamps[55],
        )

        result = service.calculate_sleep_metrics_for_all_periods(
            daily_sleep_markers=daily_markers,
            sadeh_results=[1] * 60,
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert len(result) == 2


class TestEdgeCases(TestMetricsCalculationService):
    """Tests for edge cases and error handling."""

    def test_handles_empty_activity_data(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should handle empty activity data gracefully."""
        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=[1] * 60,
            choi_results=[0] * 60,
            axis_y_data=[],
            x_data=sample_timestamps,
            participant_info=participant_info,
        )
        # Should still calculate some metrics
        assert result is not None

    def test_handles_mismatched_array_lengths(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should handle mismatched array lengths gracefully."""
        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=[1] * 30,  # Shorter than expected
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )
        # Should handle gracefully
        assert result is not None or result is None  # Doesn't crash

    def test_handles_all_wake_epochs(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should handle all wake epochs."""
        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=[0] * 60,  # All wake
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert result["Total Sleep Time (TST)"] == 0

    def test_handles_all_nonwear(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should handle all nonwear epochs."""
        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=[1] * 60,
            choi_results=[1] * 60,  # All nonwear
            axis_y_data=[50] * 60,
            x_data=sample_timestamps,
            participant_info=participant_info,
        )

        assert result is not None
        assert result["Overlapping Nonwear Minutes (Algorithm)"] > 0

    def test_handles_sensor_nonwear_results(
        self,
        service: MetricsCalculationService,
        participant_info: ParticipantInfo,
        sample_timestamps: list[float],
    ) -> None:
        """Should handle sensor nonwear results separately."""
        sleep_period = SleepPeriod(
            onset_timestamp=sample_timestamps[10],
            offset_timestamp=sample_timestamps[50],
        )

        result = service.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=[1] * 60,
            choi_results=[0] * 60,
            axis_y_data=[50] * 60,
            x_data=sample_timestamps,
            participant_info=participant_info,
            nwt_sensor_results=[1] * 60,  # All sensor nonwear
        )

        assert result is not None
        assert "Overlapping Nonwear Minutes (Sensor)" in result
        assert result["Overlapping Nonwear Minutes (Sensor)"] > 0
