"""
Tests for core dataclasses.

Tests SleepPeriod, DailySleepMarkers, ManualNonwearPeriod, DailyNonwearMarkers,
ParticipantInfo, FileInfo, and SleepMetrics.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sleep_scoring_app.core.constants import (
    AlgorithmType,
    FileSourceType,
    MarkerType,
    NonwearDataSource,
    ParticipantGroup,
    ParticipantTimepoint,
)
from sleep_scoring_app.core.dataclasses import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    DataSourceConfig,
    DeleteResult,
    DeleteStatus,
    FileInfo,
    ManualNonwearPeriod,
    NonwearPeriod,
    ParticipantInfo,
    SleepMetrics,
    SleepPeriod,
)


class TestSleepPeriod:
    """Tests for SleepPeriod dataclass."""

    def test_creates_instance(self) -> None:
        """Creates sleep period instance."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,  # 2024-01-10 22:00:00
            offset_timestamp=1704963600.0,  # 2024-01-11 07:00:00
        )

        assert period.onset_timestamp == 1704931200.0
        assert period.offset_timestamp == 1704963600.0

    def test_is_complete_when_both_set(self) -> None:
        """Returns True when both timestamps set."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
        )

        assert period.is_complete is True

    def test_is_complete_when_onset_missing(self) -> None:
        """Returns False when onset missing."""
        period = SleepPeriod(offset_timestamp=1704963600.0)

        assert period.is_complete is False

    def test_is_complete_when_offset_missing(self) -> None:
        """Returns False when offset missing."""
        period = SleepPeriod(onset_timestamp=1704931200.0)

        assert period.is_complete is False

    def test_duration_seconds(self) -> None:
        """Calculates duration in seconds."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
        )

        assert period.duration_seconds == 32400.0  # 9 hours

    def test_duration_minutes(self) -> None:
        """Calculates duration in minutes."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
        )

        assert period.duration_minutes == 540.0  # 9 hours

    def test_duration_hours(self) -> None:
        """Calculates duration in hours."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
        )

        assert period.duration_hours == 9.0

    def test_duration_none_when_incomplete(self) -> None:
        """Returns None for duration when incomplete."""
        period = SleepPeriod(onset_timestamp=1704931200.0)

        assert period.duration_seconds is None
        assert period.duration_minutes is None
        assert period.duration_hours is None

    def test_start_timestamp_alias(self) -> None:
        """start_timestamp is alias for onset_timestamp."""
        period = SleepPeriod(onset_timestamp=1704931200.0)

        assert period.start_timestamp == period.onset_timestamp

    def test_end_timestamp_alias(self) -> None:
        """end_timestamp is alias for offset_timestamp."""
        period = SleepPeriod(offset_timestamp=1704963600.0)

        assert period.end_timestamp == period.offset_timestamp

    def test_to_list_complete(self) -> None:
        """Converts complete period to list."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
        )

        result = period.to_list()

        assert result == [1704931200.0, 1704963600.0]

    def test_to_list_incomplete(self) -> None:
        """Returns empty list for incomplete period."""
        period = SleepPeriod(onset_timestamp=1704931200.0)

        assert period.to_list() == []

    def test_to_dict(self) -> None:
        """Converts to dictionary."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        result = period.to_dict()

        assert result["onset_timestamp"] == 1704931200.0
        assert result["offset_timestamp"] == 1704963600.0
        assert result["marker_index"] == 1
        assert result["marker_type"] == MarkerType.MAIN_SLEEP.value

    def test_from_dict(self) -> None:
        """Creates from dictionary."""
        data = {
            "onset_timestamp": 1704931200.0,
            "offset_timestamp": 1704963600.0,
            "marker_index": 2,
            "marker_type": "NAP",
        }

        period = SleepPeriod.from_dict(data)

        assert period.onset_timestamp == 1704931200.0
        assert period.offset_timestamp == 1704963600.0
        assert period.marker_index == 2
        assert period.marker_type == MarkerType.NAP

    def test_from_dict_invalid_marker_type(self) -> None:
        """Uses default marker type for invalid value."""
        data = {
            "onset_timestamp": 1704931200.0,
            "marker_type": "INVALID_TYPE",
        }

        period = SleepPeriod.from_dict(data)

        assert period.marker_type == MarkerType.MAIN_SLEEP


class TestDailySleepMarkers:
    """Tests for DailySleepMarkers dataclass."""

    def test_creates_empty_instance(self) -> None:
        """Creates empty markers instance."""
        markers = DailySleepMarkers()

        assert markers.period_1 is None
        assert markers.period_2 is None

    def test_get_all_periods_empty(self) -> None:
        """Returns empty list when no periods."""
        markers = DailySleepMarkers()

        assert markers.get_all_periods() == []

    def test_get_all_periods(self) -> None:
        """Returns all non-None periods."""
        period1 = SleepPeriod(onset_timestamp=1.0, offset_timestamp=2.0)
        period2 = SleepPeriod(onset_timestamp=3.0, offset_timestamp=4.0)
        markers = DailySleepMarkers(period_1=period1, period_2=period2)

        result = markers.get_all_periods()

        assert len(result) == 2
        assert period1 in result
        assert period2 in result

    def test_get_complete_periods(self) -> None:
        """Returns only complete periods."""
        complete = SleepPeriod(onset_timestamp=1.0, offset_timestamp=2.0)
        incomplete = SleepPeriod(onset_timestamp=3.0)  # No offset
        markers = DailySleepMarkers(period_1=complete, period_2=incomplete)

        result = markers.get_complete_periods()

        assert len(result) == 1
        assert complete in result

    def test_get_main_sleep(self) -> None:
        """Returns longest period as main sleep."""
        short = SleepPeriod(onset_timestamp=0.0, offset_timestamp=3600.0)  # 1 hour
        long = SleepPeriod(onset_timestamp=10000.0, offset_timestamp=40000.0)  # 8+ hours
        markers = DailySleepMarkers(period_1=short, period_2=long)

        main = markers.get_main_sleep()

        assert main is long

    def test_get_main_sleep_none_when_empty(self) -> None:
        """Returns None when no complete periods."""
        markers = DailySleepMarkers()

        assert markers.get_main_sleep() is None

    def test_get_naps(self) -> None:
        """Returns non-main sleep periods."""
        short = SleepPeriod(onset_timestamp=0.0, offset_timestamp=3600.0)
        long = SleepPeriod(onset_timestamp=10000.0, offset_timestamp=40000.0)
        markers = DailySleepMarkers(period_1=short, period_2=long)

        naps = markers.get_naps()

        assert len(naps) == 1
        assert short in naps
        assert long not in naps

    def test_update_classifications(self) -> None:
        """Updates marker types based on duration."""
        short = SleepPeriod(onset_timestamp=0.0, offset_timestamp=3600.0)
        long = SleepPeriod(onset_timestamp=10000.0, offset_timestamp=40000.0)
        markers = DailySleepMarkers(period_1=short, period_2=long)

        markers.update_classifications()

        assert long.marker_type == MarkerType.MAIN_SLEEP
        assert short.marker_type == MarkerType.NAP

    def test_check_duration_tie(self) -> None:
        """Detects identical durations."""
        period1 = SleepPeriod(onset_timestamp=0.0, offset_timestamp=3600.0)
        period2 = SleepPeriod(onset_timestamp=10000.0, offset_timestamp=13600.0)  # Same duration
        markers = DailySleepMarkers(period_1=period1, period_2=period2)

        assert markers.check_duration_tie() is True

    def test_check_duration_tie_false(self) -> None:
        """Returns False when no ties."""
        period1 = SleepPeriod(onset_timestamp=0.0, offset_timestamp=3600.0)
        period2 = SleepPeriod(onset_timestamp=10000.0, offset_timestamp=20000.0)
        markers = DailySleepMarkers(period_1=period1, period_2=period2)

        assert markers.check_duration_tie() is False

    def test_count_periods(self) -> None:
        """Counts defined periods."""
        markers = DailySleepMarkers(
            period_1=SleepPeriod(onset_timestamp=1.0),
            period_2=SleepPeriod(onset_timestamp=2.0),
        )

        assert markers.count_periods() == 2

    def test_has_space_for_new_period(self) -> None:
        """Checks if new period can be added."""
        markers = DailySleepMarkers()

        assert markers.has_space_for_new_period() is True

    def test_has_space_for_new_period_full(self) -> None:
        """Returns False when all slots filled."""
        markers = DailySleepMarkers(
            period_1=SleepPeriod(onset_timestamp=1.0),
            period_2=SleepPeriod(onset_timestamp=2.0),
            period_3=SleepPeriod(onset_timestamp=3.0),
            period_4=SleepPeriod(onset_timestamp=4.0),
        )

        assert markers.has_space_for_new_period() is False

    def test_get_period_by_slot(self) -> None:
        """Gets period by slot number."""
        period = SleepPeriod(onset_timestamp=1.0)
        markers = DailySleepMarkers(period_2=period)

        assert markers.get_period_by_slot(2) is period
        assert markers.get_period_by_slot(1) is None
        assert markers.get_period_by_slot(5) is None

    def test_set_period_by_slot(self) -> None:
        """Sets period by slot number."""
        markers = DailySleepMarkers()
        period = SleepPeriod(onset_timestamp=1.0)

        markers.set_period_by_slot(3, period)

        assert markers.period_3 is period

    def test_remove_period_by_slot(self) -> None:
        """Removes period by slot number."""
        period = SleepPeriod(onset_timestamp=1.0)
        markers = DailySleepMarkers(period_1=period)

        markers.remove_period_by_slot(1)

        assert markers.period_1 is None

    def test_to_dict(self) -> None:
        """Converts to dictionary."""
        period = SleepPeriod(onset_timestamp=1.0, offset_timestamp=2.0)
        markers = DailySleepMarkers(period_1=period)

        result = markers.to_dict()

        assert result["period_1"] is not None
        assert result["period_2"] is None

    def test_from_dict(self) -> None:
        """Creates from dictionary."""
        data = {
            "period_1": {"onset_timestamp": 1.0, "offset_timestamp": 2.0},
            "period_2": None,
        }

        markers = DailySleepMarkers.from_dict(data)

        assert markers.period_1 is not None
        assert markers.period_1.onset_timestamp == 1.0
        assert markers.period_2 is None


class TestManualNonwearPeriod:
    """Tests for ManualNonwearPeriod dataclass."""

    def test_creates_instance(self) -> None:
        """Creates nonwear period instance."""
        period = ManualNonwearPeriod(
            start_timestamp=1704931200.0,
            end_timestamp=1704963600.0,
        )

        assert period.start_timestamp == 1704931200.0
        assert period.end_timestamp == 1704963600.0

    def test_is_complete(self) -> None:
        """Checks if complete."""
        complete = ManualNonwearPeriod(start_timestamp=1.0, end_timestamp=2.0)
        incomplete = ManualNonwearPeriod(start_timestamp=1.0)

        assert complete.is_complete is True
        assert incomplete.is_complete is False

    def test_duration_seconds(self) -> None:
        """Calculates duration in seconds."""
        period = ManualNonwearPeriod(start_timestamp=0.0, end_timestamp=3600.0)

        assert period.duration_seconds == 3600.0

    def test_duration_minutes(self) -> None:
        """Calculates duration in minutes."""
        period = ManualNonwearPeriod(start_timestamp=0.0, end_timestamp=3600.0)

        assert period.duration_minutes == 60.0

    def test_to_list(self) -> None:
        """Converts to list."""
        period = ManualNonwearPeriod(start_timestamp=1.0, end_timestamp=2.0)

        assert period.to_list() == [1.0, 2.0]

    def test_to_dict(self) -> None:
        """Converts to dictionary."""
        period = ManualNonwearPeriod(
            start_timestamp=1.0,
            end_timestamp=2.0,
            marker_index=3,
        )

        result = period.to_dict()

        assert result["start_timestamp"] == 1.0
        assert result["end_timestamp"] == 2.0
        assert result["marker_index"] == 3

    def test_from_dict(self) -> None:
        """Creates from dictionary."""
        data = {
            "start_timestamp": 1.0,
            "end_timestamp": 2.0,
            "marker_index": 5,
        }

        period = ManualNonwearPeriod.from_dict(data)

        assert period.start_timestamp == 1.0
        assert period.end_timestamp == 2.0
        assert period.marker_index == 5


class TestDailyNonwearMarkers:
    """Tests for DailyNonwearMarkers dataclass."""

    def test_creates_empty_instance(self) -> None:
        """Creates empty markers instance."""
        markers = DailyNonwearMarkers()

        assert markers.period_1 is None
        assert len(markers) == 0

    def test_get_all_periods(self) -> None:
        """Returns all non-None periods."""
        period1 = ManualNonwearPeriod(start_timestamp=1.0, end_timestamp=2.0)
        period2 = ManualNonwearPeriod(start_timestamp=3.0, end_timestamp=4.0)
        markers = DailyNonwearMarkers(period_1=period1, period_5=period2)

        result = markers.get_all_periods()

        assert len(result) == 2

    def test_get_complete_periods(self) -> None:
        """Returns only complete periods."""
        complete = ManualNonwearPeriod(start_timestamp=1.0, end_timestamp=2.0)
        incomplete = ManualNonwearPeriod(start_timestamp=3.0)
        markers = DailyNonwearMarkers(period_1=complete, period_2=incomplete)

        result = markers.get_complete_periods()

        assert len(result) == 1

    def test_get_next_available_slot(self) -> None:
        """Gets next available slot."""
        markers = DailyNonwearMarkers(
            period_1=ManualNonwearPeriod(start_timestamp=1.0),
            period_2=ManualNonwearPeriod(start_timestamp=2.0),
        )

        assert markers.get_next_available_slot() == 3

    def test_get_next_available_slot_none_when_full(self) -> None:
        """Returns None when all slots filled."""
        markers = DailyNonwearMarkers(
            period_1=ManualNonwearPeriod(start_timestamp=1.0),
            period_2=ManualNonwearPeriod(start_timestamp=2.0),
            period_3=ManualNonwearPeriod(start_timestamp=3.0),
            period_4=ManualNonwearPeriod(start_timestamp=4.0),
            period_5=ManualNonwearPeriod(start_timestamp=5.0),
            period_6=ManualNonwearPeriod(start_timestamp=6.0),
            period_7=ManualNonwearPeriod(start_timestamp=7.0),
            period_8=ManualNonwearPeriod(start_timestamp=8.0),
            period_9=ManualNonwearPeriod(start_timestamp=9.0),
            period_10=ManualNonwearPeriod(start_timestamp=10.0),
        )

        assert markers.get_next_available_slot() is None

    def test_check_overlap_detects_overlap(self) -> None:
        """Detects overlapping periods."""
        existing = ManualNonwearPeriod(start_timestamp=100.0, end_timestamp=200.0)
        markers = DailyNonwearMarkers(period_1=existing)

        # New period overlaps with existing
        assert markers.check_overlap(150.0, 250.0) is True

    def test_check_overlap_no_overlap(self) -> None:
        """Returns False when no overlap."""
        existing = ManualNonwearPeriod(start_timestamp=100.0, end_timestamp=200.0)
        markers = DailyNonwearMarkers(period_1=existing)

        # New period does not overlap
        assert markers.check_overlap(300.0, 400.0) is False

    def test_check_overlap_excludes_slot(self) -> None:
        """Excludes specified slot from overlap check."""
        period = ManualNonwearPeriod(start_timestamp=100.0, end_timestamp=200.0)
        markers = DailyNonwearMarkers(period_1=period)

        # Would overlap but slot 1 is excluded
        assert markers.check_overlap(150.0, 250.0, exclude_slot=1) is False

    def test_len(self) -> None:
        """Returns count via len()."""
        markers = DailyNonwearMarkers(
            period_1=ManualNonwearPeriod(start_timestamp=1.0),
            period_2=ManualNonwearPeriod(start_timestamp=2.0),
        )

        assert len(markers) == 2


class TestParticipantInfo:
    """Tests for ParticipantInfo dataclass."""

    def test_creates_instance(self) -> None:
        """Creates participant info instance."""
        info = ParticipantInfo(
            numerical_id="1000",
            group_str="Control",
            timepoint_str="T1",
        )

        assert info.numerical_id == "1000"
        assert info.group_str == "Control"

    def test_participant_key(self) -> None:
        """Generates composite participant key."""
        info = ParticipantInfo(
            numerical_id="1000",
            group=ParticipantGroup.GROUP_1,
            timepoint=ParticipantTimepoint.T1,
        )

        assert info.participant_key == "1000_G1_T1"

    def test_from_dict(self) -> None:
        """Creates from dictionary."""
        data = {
            "numerical_participant_id": "2000",
            "full_participant_id": "2000 T2 G2",
            "participant_group": "G2",
            "participant_timepoint": "T2",
        }

        info = ParticipantInfo.from_dict(data)

        assert info.numerical_id == "2000"
        assert info.full_id == "2000 T2 G2"

    def test_from_participant_key(self) -> None:
        """Creates from participant key string."""
        info = ParticipantInfo.from_participant_key("1000_G1_T2")

        assert info.numerical_id == "1000"
        assert info.group == ParticipantGroup.GROUP_1
        assert info.timepoint == ParticipantTimepoint.T2

    def test_from_participant_key_invalid_format(self) -> None:
        """Raises error for invalid key format."""
        with pytest.raises(ValueError, match="Invalid participant key"):
            ParticipantInfo.from_participant_key("invalid_key")


class TestFileInfo:
    """Tests for FileInfo dataclass."""

    def test_creates_instance(self) -> None:
        """Creates file info instance."""
        info = FileInfo(
            filename="test.csv",
            source=FileSourceType.DATABASE,
            participant_id="1000",
        )

        assert info.filename == "test.csv"
        assert info.source == FileSourceType.DATABASE

    def test_display_name_database(self) -> None:
        """Shows (imported) suffix for database files."""
        info = FileInfo(filename="test.csv", source=FileSourceType.DATABASE)

        assert info.display_name == "test.csv (imported)"

    def test_display_name_csv(self) -> None:
        """Shows (CSV) suffix for CSV files."""
        info = FileInfo(filename="test.csv", source=FileSourceType.CSV)

        assert info.display_name == "test.csv (CSV)"

    def test_frozen(self) -> None:
        """FileInfo is immutable."""
        info = FileInfo(filename="test.csv")

        with pytest.raises(AttributeError):
            info.filename = "other.csv"


class TestDataSourceConfig:
    """Tests for DataSourceConfig dataclass."""

    def test_creates_instance(self) -> None:
        """Creates config instance."""
        config = DataSourceConfig(
            source_type="csv",
            file_path="/path/to/file.csv",
            skip_rows=5,
        )

        assert config.source_type == "csv"
        assert config.skip_rows == 5

    def test_to_dict(self) -> None:
        """Converts to dictionary."""
        config = DataSourceConfig(
            source_type="gt3x",
            file_path="/path/file.gt3x",
        )

        result = config.to_dict()

        assert result["source_type"] == "gt3x"
        assert result["file_path"] == "/path/file.gt3x"

    def test_from_dict(self) -> None:
        """Creates from dictionary."""
        data = {
            "source_type": "csv",
            "file_path": "/path/file.csv",
            "skip_rows": 15,
            "encoding": "latin-1",
        }

        config = DataSourceConfig.from_dict(data)

        assert config.source_type == "csv"
        assert config.skip_rows == 15
        assert config.encoding == "latin-1"

    def test_frozen(self) -> None:
        """Config is immutable."""
        config = DataSourceConfig()

        with pytest.raises(AttributeError):
            config.skip_rows = 20


class TestSleepMetrics:
    """Tests for SleepMetrics dataclass."""

    @pytest.fixture
    def sample_participant(self) -> ParticipantInfo:
        """Create sample participant."""
        return ParticipantInfo(
            numerical_id="1000",
            group_str="Control",
            timepoint_str="T1",
        )

    @pytest.fixture
    def sample_markers(self) -> DailySleepMarkers:
        """Create sample markers."""
        period = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        return DailySleepMarkers(period_1=period)

    def test_creates_instance(
        self,
        sample_participant: ParticipantInfo,
        sample_markers: DailySleepMarkers,
    ) -> None:
        """Creates metrics instance."""
        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=sample_markers,
            total_sleep_time=420,
        )

        assert metrics.filename == "test.csv"
        assert metrics.total_sleep_time == 420

    def test_set_dynamic_field(
        self,
        sample_participant: ParticipantInfo,
    ) -> None:
        """Sets dynamic field."""
        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
        )

        metrics.set_dynamic_field("custom_metric", 123)

        assert metrics.get_dynamic_field("custom_metric") == 123

    def test_get_dynamic_field_default(
        self,
        sample_participant: ParticipantInfo,
    ) -> None:
        """Returns default for missing dynamic field."""
        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
        )

        assert metrics.get_dynamic_field("missing", default="N/A") == "N/A"

    def test_to_dict(
        self,
        sample_participant: ParticipantInfo,
        sample_markers: DailySleepMarkers,
    ) -> None:
        """Converts to dictionary."""
        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=sample_markers,
            total_sleep_time=420,
        )

        result = metrics.to_dict()

        assert result["filename"] == "test.csv"
        assert result["total_sleep_time"] == 420
        assert result["participant"] == "1000"

    def test_to_export_dict(
        self,
        sample_participant: ParticipantInfo,
        sample_markers: DailySleepMarkers,
    ) -> None:
        """Converts to export dictionary."""
        from sleep_scoring_app.core.constants import ExportColumn

        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=sample_markers,
            total_sleep_time=420,
        )

        result = metrics.to_export_dict()

        assert ExportColumn.SLEEP_DATE in result
        assert result[ExportColumn.TOTAL_SLEEP_TIME] == 420

    def test_to_export_dict_list_with_periods(
        self,
        sample_participant: ParticipantInfo,
    ) -> None:
        """Creates list with one row per period."""
        # Create two periods
        main = SleepPeriod(
            onset_timestamp=1704931200.0,
            offset_timestamp=1704963600.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        nap = SleepPeriod(
            onset_timestamp=1704978000.0,  # Next day afternoon
            offset_timestamp=1704981600.0,
            marker_index=2,
            marker_type=MarkerType.NAP,
        )
        markers = DailySleepMarkers(period_1=main, period_2=nap)

        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=markers,
        )

        result = metrics.to_export_dict_list()

        assert len(result) == 2
        assert result[0]["Marker Index"] == 1
        assert result[1]["Marker Index"] == 2

    def test_to_export_dict_list_empty_periods(
        self,
        sample_participant: ParticipantInfo,
    ) -> None:
        """Returns single row when no complete periods."""
        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=DailySleepMarkers(),
        )

        result = metrics.to_export_dict_list()

        assert len(result) == 1

    def test_store_period_metrics(
        self,
        sample_participant: ParticipantInfo,
        sample_markers: DailySleepMarkers,
    ) -> None:
        """Stores metrics for specific period."""
        metrics = SleepMetrics(
            participant=sample_participant,
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=sample_markers,
        )

        period = sample_markers.period_1
        period_metrics = {"tst": 420, "efficiency": 85.0}

        metrics.store_period_metrics(period, period_metrics)

        assert metrics.get_dynamic_field("period_1_metrics") == period_metrics


class TestNonwearPeriod:
    """Tests for NonwearPeriod dataclass."""

    def test_creates_instance(self) -> None:
        """Creates nonwear period instance."""
        period = NonwearPeriod(
            start_time=datetime(2024, 1, 10, 10, 0),
            end_time=datetime(2024, 1, 10, 12, 0),
            participant_id="1000",
            source=NonwearDataSource.CHOI_ALGORITHM,
        )

        assert period.participant_id == "1000"
        assert period.source == NonwearDataSource.CHOI_ALGORITHM

    def test_parses_string_timestamps(self) -> None:
        """Parses string timestamps to datetime."""
        period = NonwearPeriod(
            start_time="2024-01-10T10:00:00",
            end_time="2024-01-10T12:00:00",
            participant_id="1000",
            source=NonwearDataSource.MANUAL_NWT,
        )

        assert isinstance(period.start_time, datetime)
        assert isinstance(period.end_time, datetime)

    def test_to_dict(self) -> None:
        """Converts to dictionary."""
        period = NonwearPeriod(
            start_time=datetime(2024, 1, 10, 10, 0),
            end_time=datetime(2024, 1, 10, 12, 0),
            participant_id="1000",
            source=NonwearDataSource.NWT_SENSOR,
            duration_minutes=120,
        )

        result = period.to_dict()

        assert "start_time" in result
        assert result["duration_minutes"] == 120

    def test_from_dict(self) -> None:
        """Creates from dictionary."""
        data = {
            "start_time": "2024-01-10T10:00:00",
            "end_time": "2024-01-10T12:00:00",
            "participant_id": "1000",
            "source": "Manual NWT",  # Must match NonwearDataSource.MANUAL_NWT value
        }

        period = NonwearPeriod.from_dict(data)

        assert period.participant_id == "1000"
        assert period.source == NonwearDataSource.MANUAL_NWT


class TestDeleteResult:
    """Tests for DeleteResult dataclass."""

    def test_creates_instance(self) -> None:
        """Creates delete result instance."""
        result = DeleteResult(
            status=DeleteStatus.SUCCESS,
            filename="test.csv",
            records_deleted=100,
        )

        assert result.status == DeleteStatus.SUCCESS
        assert result.records_deleted == 100

    def test_frozen(self) -> None:
        """Result is immutable."""
        result = DeleteResult(status=DeleteStatus.FAILED, filename="test.csv")

        with pytest.raises(AttributeError):
            result.status = DeleteStatus.SUCCESS
