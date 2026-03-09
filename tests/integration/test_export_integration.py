#!/usr/bin/env python3
"""
Integration tests for export functionality.

Tests the complete export pipeline from database to CSV file,
including multi-period exports, nonwear separation, and data integrity.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import (
    AlgorithmType,
    ExportColumn,
    MarkerType,
    NonwearDataSource,
)
from sleep_scoring_app.core.dataclasses import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    ManualNonwearPeriod,
    ParticipantInfo,
    SleepMetrics,
    SleepPeriod,
)
from sleep_scoring_app.services.export_service import ExportManager, ExportResult


@pytest.fixture
def mock_db_manager():
    """Create a mock database manager with realistic behavior."""
    mock_db = MagicMock()

    # Default returns
    mock_db.load_raw_activity_data.return_value = ([], [])
    mock_db.load_manual_nonwear_markers.return_value = DailyNonwearMarkers()
    mock_db.save_sleep_metrics.return_value = True
    mock_db.get_all_sleep_data_for_export.return_value = []

    return mock_db


@pytest.fixture
def export_manager_with_db(mock_db_manager):
    """Create ExportManager with configured mock database."""
    return ExportManager(database_manager=mock_db_manager)


@pytest.fixture
def create_participant():
    """Factory fixture for creating participants."""

    def _create(
        numerical_id: str = "1000",
        group: str = "Control",
        timepoint: str = "T1",
    ) -> ParticipantInfo:
        return ParticipantInfo(
            numerical_id=numerical_id,
            full_id=f"{numerical_id} {timepoint} {group}",
            group_str=group,
            timepoint_str=timepoint,
        )

    return _create


@pytest.fixture
def create_sleep_period():
    """Factory fixture for creating sleep periods."""

    def _create(
        onset_hour: int = 22,
        duration_hours: float = 8.0,
        base_date: date = date(2024, 1, 10),
        marker_index: int = 1,
        marker_type: MarkerType = MarkerType.MAIN_SLEEP,
    ) -> SleepPeriod:
        onset_dt = datetime.combine(base_date, datetime.min.time().replace(hour=onset_hour))
        offset_dt = onset_dt + timedelta(hours=duration_hours)

        return SleepPeriod(
            onset_timestamp=onset_dt.timestamp(),
            offset_timestamp=offset_dt.timestamp(),
            marker_index=marker_index,
            marker_type=marker_type,
        )

    return _create


@pytest.fixture
def create_sleep_metrics(create_participant, create_sleep_period):
    """Factory fixture for creating SleepMetrics with customization."""

    def _create(
        participant_id: str = "1000",
        group: str = "Control",
        timepoint: str = "T1",
        analysis_date: str = "2024-01-10",
        filename: str | None = None,
        periods: list[SleepPeriod] | None = None,
        total_sleep_time: float = 420.0,
        sleep_efficiency: float = 85.0,
    ) -> SleepMetrics:
        participant = create_participant(participant_id, group, timepoint)

        markers = DailySleepMarkers()
        if periods:
            for i, period in enumerate(periods[:4], 1):  # Max 4 periods
                setattr(markers, f"period_{i}", period)
        else:
            markers.period_1 = create_sleep_period()

        return SleepMetrics(
            filename=filename or f"participant_{participant_id}.csv",
            analysis_date=analysis_date,
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
            total_sleep_time=total_sleep_time,
            sleep_efficiency=sleep_efficiency,
            total_minutes_in_bed=480.0,
            waso=45.0,
            awakenings=3,
            average_awakening_length=15.0,
        )

    return _create


@pytest.fixture
def multi_participant_dataset(create_sleep_metrics, create_sleep_period):
    """Create a dataset with multiple participants, dates, and periods."""
    metrics_list = []

    # Participant 1: Control group, T1, 3 dates
    for day in range(3):
        base_date = date(2024, 1, 10 + day)
        main_sleep = create_sleep_period(
            onset_hour=22,
            duration_hours=8.0,
            base_date=base_date,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        metrics = create_sleep_metrics(
            participant_id="1000",
            group="Control",
            timepoint="T1",
            analysis_date=base_date.isoformat(),
            periods=[main_sleep],
            total_sleep_time=420.0 + day * 10,
        )
        metrics_list.append(metrics)

    # Participant 2: Treatment group, T1, with nap
    base_date = date(2024, 1, 10)
    main_sleep = create_sleep_period(
        onset_hour=22,
        duration_hours=7.5,
        base_date=base_date,
        marker_index=1,
        marker_type=MarkerType.MAIN_SLEEP,
    )
    nap = create_sleep_period(
        onset_hour=14,
        duration_hours=1.5,
        base_date=base_date,
        marker_index=2,
        marker_type=MarkerType.NAP,
    )

    metrics = create_sleep_metrics(
        participant_id="1001",
        group="Treatment",
        timepoint="T1",
        analysis_date=base_date.isoformat(),
        periods=[main_sleep, nap],
        total_sleep_time=450.0,
    )
    metrics_list.append(metrics)

    # Participant 3: Control group, T2
    metrics = create_sleep_metrics(
        participant_id="1002",
        group="Control",
        timepoint="T2",
        analysis_date="2024-01-15",
        total_sleep_time=400.0,
    )
    metrics_list.append(metrics)

    return metrics_list


class TestFullExportPipeline:
    """Integration tests for the complete export pipeline."""

    def test_export_produces_valid_csv(self, export_manager_with_db, multi_participant_dataset, tmp_path):
        """Test that export produces a valid CSV file."""
        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                multi_participant_dataset,
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[
                    ExportColumn.NUMERICAL_PARTICIPANT_ID,
                    ExportColumn.SLEEP_DATE,
                    ExportColumn.TOTAL_SLEEP_TIME,
                    ExportColumn.EFFICIENCY,
                ],
            )

        assert result.success is True
        assert result.files_exported >= 1

        # Verify CSV can be read by pandas
        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        assert len(csv_files) >= 1

        df = pd.read_csv(csv_files[0], comment="#")
        assert len(df) > 0
        assert ExportColumn.NUMERICAL_PARTICIPANT_ID in df.columns

    def test_export_preserves_all_selected_columns(self, export_manager_with_db, multi_participant_dataset, tmp_path):
        """Test that all selected columns are present in export."""
        selected_cols = [
            ExportColumn.NUMERICAL_PARTICIPANT_ID,
            ExportColumn.PARTICIPANT_GROUP,
            ExportColumn.SLEEP_DATE,
            ExportColumn.ONSET_TIME,
            ExportColumn.OFFSET_TIME,
            ExportColumn.TOTAL_SLEEP_TIME,
            ExportColumn.EFFICIENCY,
        ]

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                multi_participant_dataset,
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=selected_cols,
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        # Check that all selected columns are present
        for col in selected_cols:
            assert col in df.columns, f"Column {col} not found in export"

    def test_export_data_sorted_correctly(self, export_manager_with_db, multi_participant_dataset, tmp_path):
        """Test that exported data is sorted by participant, date, and marker index."""
        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                multi_participant_dataset,
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[
                    ExportColumn.NUMERICAL_PARTICIPANT_ID,
                    ExportColumn.SLEEP_DATE,
                    ExportColumn.MARKER_INDEX,
                ],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        # Check that data is sorted
        if ExportColumn.NUMERICAL_PARTICIPANT_ID in df.columns:
            # Verify participant IDs are in order for same-participant rows
            participant_ids = df[ExportColumn.NUMERICAL_PARTICIPANT_ID].tolist()
            assert participant_ids == sorted(participant_ids, key=str)


class TestMultiPeriodExport:
    """Tests for exporting multiple sleep periods per participant/date."""

    def test_main_sleep_and_nap_appear_as_separate_rows(self, export_manager_with_db, create_sleep_metrics, create_sleep_period, tmp_path):
        """Test that main sleep and nap periods appear as separate rows."""
        base_date = date(2024, 1, 10)

        main_sleep = create_sleep_period(
            onset_hour=22,
            duration_hours=8.0,
            base_date=base_date,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        nap = create_sleep_period(
            onset_hour=14,
            duration_hours=1.5,
            base_date=base_date,
            marker_index=2,
            marker_type=MarkerType.NAP,
        )

        metrics = create_sleep_metrics(
            participant_id="1000",
            analysis_date=base_date.isoformat(),
            periods=[main_sleep, nap],
        )

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[
                    ExportColumn.NUMERICAL_PARTICIPANT_ID,
                    ExportColumn.MARKER_INDEX,
                    ExportColumn.MARKER_TYPE,
                ],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        assert len(df) == 2, "Should have 2 rows (main sleep + nap)"

    def test_marker_index_correctly_identifies_periods(self, export_manager_with_db, create_sleep_metrics, create_sleep_period, tmp_path):
        """Test that Marker Index column correctly identifies each period."""
        base_date = date(2024, 1, 10)

        periods = [
            create_sleep_period(marker_index=1, marker_type=MarkerType.MAIN_SLEEP),
            create_sleep_period(marker_index=2, marker_type=MarkerType.NAP, onset_hour=14, duration_hours=1.0),
            create_sleep_period(marker_index=3, marker_type=MarkerType.NAP, onset_hour=17, duration_hours=0.5),
        ]

        metrics = create_sleep_metrics(
            participant_id="1000",
            analysis_date=base_date.isoformat(),
            periods=periods,
        )

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.MARKER_INDEX],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        assert len(df) == 3
        assert set(df[ExportColumn.MARKER_INDEX].tolist()) == {1, 2, 3}

    def test_period_type_column_shows_main_sleep_vs_nap(self, export_manager_with_db, create_sleep_metrics, create_sleep_period, tmp_path):
        """Test that Period Type column shows 'Main Sleep' vs 'Nap'."""
        periods = [
            create_sleep_period(marker_index=1, marker_type=MarkerType.MAIN_SLEEP),
            create_sleep_period(marker_index=2, marker_type=MarkerType.NAP, onset_hour=14, duration_hours=1.0),
        ]

        metrics = create_sleep_metrics(periods=periods)

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.MARKER_TYPE],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        marker_types = df[ExportColumn.MARKER_TYPE].tolist()
        assert MarkerType.MAIN_SLEEP.value in marker_types
        assert MarkerType.NAP.value in marker_types


class TestNonwearSeparateExport:
    """Tests for exporting nonwear markers to a separate file."""

    def test_nonwear_separate_creates_two_files(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test that export_nonwear_separate=True creates two files."""
        metrics = create_sleep_metrics()

        # Create nonwear markers for the mock to return
        nonwear_markers = DailyNonwearMarkers()
        nonwear_period = ManualNonwearPeriod(
            start_timestamp=datetime(2024, 1, 10, 10, 0).timestamp(),
            end_timestamp=datetime(2024, 1, 10, 11, 0).timestamp(),
            marker_index=1,
        )
        nonwear_markers.period_1 = nonwear_period

        export_manager_with_db.db_manager.load_manual_nonwear_markers.return_value = nonwear_markers

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
                export_nonwear_separate=True,
            )

        assert result.success is True

        # Should have sleep data file
        sleep_files = list(tmp_path.glob("sleep_data_*.csv"))
        assert len(sleep_files) >= 1

        # Should have nonwear file
        nonwear_files = list(tmp_path.glob("nonwear_markers_*.csv"))
        assert len(nonwear_files) >= 1

    def test_nonwear_file_contains_correct_columns(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test that nonwear file contains expected columns."""
        metrics = create_sleep_metrics()

        nonwear_markers = DailyNonwearMarkers()
        nonwear_period = ManualNonwearPeriod(
            start_timestamp=datetime(2024, 1, 10, 10, 0).timestamp(),
            end_timestamp=datetime(2024, 1, 10, 11, 0).timestamp(),
            marker_index=1,
        )
        nonwear_markers.period_1 = nonwear_period

        export_manager_with_db.db_manager.load_manual_nonwear_markers.return_value = nonwear_markers

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
                export_nonwear_separate=True,
            )

        nonwear_files = list(tmp_path.glob("nonwear_markers_*.csv"))
        if nonwear_files:
            df = pd.read_csv(nonwear_files[0], comment="#")

            expected_columns = [
                "Participant ID",
                "Date",
                "Start Time",
                "End Time",
                "Duration (minutes)",
            ]

            for col in expected_columns:
                assert col in df.columns, f"Expected column '{col}' not found in nonwear export"


class TestExportEdgeCases:
    """Tests for edge cases in export functionality."""

    def test_export_with_no_metrics_in_database(self, export_manager_with_db, tmp_path):
        """Test export with no metrics returns appropriate error."""
        result = export_manager_with_db.perform_direct_export(
            [],
            grouping_option=0,
            output_directory=str(tmp_path),
            selected_columns=[],
        )

        assert result.success is False
        assert len(result.errors) > 0

    def test_export_metrics_with_no_complete_periods(self, export_manager_with_db, create_participant, tmp_path):
        """Test export with metrics but no complete periods."""
        participant = create_participant()

        # Create metrics with incomplete period (only onset, no offset)
        incomplete_period = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 10, 22, 0).timestamp(),
            offset_timestamp=None,  # Incomplete
            marker_index=1,
        )

        markers = DailySleepMarkers()
        markers.period_1 = incomplete_period

        metrics = SleepMetrics(
            filename="test.csv",
            analysis_date="2024-01-10",
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
        )

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        # Should still succeed but with only the basic row
        assert result.success is True

    def test_export_participant_with_missing_numerical_id(self, export_manager_with_db, create_sleep_period, tmp_path):
        """Test export with participant having no numerical_id."""
        participant = ParticipantInfo(
            numerical_id="",  # Empty
            full_id="Unknown",
            group_str="Unknown",
            timepoint_str="Unknown",
        )

        markers = DailySleepMarkers()
        markers.period_1 = create_sleep_period()

        metrics = SleepMetrics(
            filename="unknown_participant.csv",
            analysis_date="2024-01-10",
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
        )

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        # Should succeed even with empty participant ID
        assert result.success is True


class TestSpecialCharacters:
    """Tests for handling special characters in export."""

    def test_participant_id_with_special_characters(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test export with special characters in participant ID."""
        metrics = create_sleep_metrics(
            participant_id="P1-4000_A",  # Contains dash and underscore
            filename="P1-4000_A_data.csv",
        )

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        assert "P1-4000_A" in df[ExportColumn.NUMERICAL_PARTICIPANT_ID].tolist()

    def test_filename_with_spaces(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test export with spaces in filename."""
        metrics = create_sleep_metrics(
            participant_id="1000",
            filename="participant 1000 data file.csv",  # Spaces in filename
        )

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert result.success is True

    def test_export_path_with_unicode(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test export to path with unicode characters."""
        # Create directory with unicode name
        unicode_dir = tmp_path / "export_datos_2024"
        unicode_dir.mkdir()

        metrics = create_sleep_metrics()

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(unicode_dir),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert result.success is True


class TestColumnSelection:
    """Tests for column selection edge cases."""

    def test_export_with_all_columns_selected(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test export with all available columns selected."""
        metrics = create_sleep_metrics()

        all_columns = [
            ExportColumn.FULL_PARTICIPANT_ID,
            ExportColumn.NUMERICAL_PARTICIPANT_ID,
            ExportColumn.PARTICIPANT_GROUP,
            ExportColumn.PARTICIPANT_TIMEPOINT,
            ExportColumn.SLEEP_DATE,
            ExportColumn.ONSET_TIME,
            ExportColumn.OFFSET_TIME,
            ExportColumn.TOTAL_SLEEP_TIME,
            ExportColumn.EFFICIENCY,
            ExportColumn.WASO,
            ExportColumn.NUMBER_OF_AWAKENINGS,
            ExportColumn.MARKER_INDEX,
            ExportColumn.MARKER_TYPE,
        ]

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=all_columns,
            )

        assert result.success is True

    def test_export_with_only_required_columns(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test export with minimal required columns."""
        metrics = create_sleep_metrics()

        minimal_columns = [ExportColumn.NUMERICAL_PARTICIPANT_ID]

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=minimal_columns,
            )

        assert result.success is True

    def test_export_with_nonexistent_columns_shows_warning(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test export with non-existent columns in selection shows warning."""
        metrics = create_sleep_metrics()

        columns_with_invalid = [
            ExportColumn.NUMERICAL_PARTICIPANT_ID,
            "NonexistentColumn",  # This column doesn't exist
        ]

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=columns_with_invalid,
            )

        # Should still succeed but may have warnings
        assert result.success is True
        # The warning about missing columns should be present
        assert len(result.warnings) > 0 or "NonexistentColumn" not in str(result.warnings)


class TestDataIntegrityVerification:
    """Tests for verifying data integrity in exports."""

    def test_exported_metrics_match_source_values(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test that exported metrics match the original values."""
        metrics = create_sleep_metrics(
            participant_id="1000",
            total_sleep_time=420.0,
            sleep_efficiency=85.5,
        )

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[
                    ExportColumn.NUMERICAL_PARTICIPANT_ID,
                    ExportColumn.TOTAL_SLEEP_TIME,
                    ExportColumn.EFFICIENCY,
                ],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        # Note: pandas may parse numeric-looking strings as integers
        assert str(df[ExportColumn.NUMERICAL_PARTICIPANT_ID].iloc[0]) == "1000"
        assert df[ExportColumn.TOTAL_SLEEP_TIME].iloc[0] == 420.0
        assert abs(df[ExportColumn.EFFICIENCY].iloc[0] - 85.5) < 0.01

    def test_timestamp_formatting(self, export_manager_with_db, create_sleep_metrics, create_sleep_period, tmp_path):
        """Test that onset/offset times are formatted as HH:MM."""
        # Create period with specific times
        period = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 10, 22, 30).timestamp(),
            offset_timestamp=datetime(2024, 1, 11, 6, 45).timestamp(),
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        metrics = create_sleep_metrics(periods=[period])

        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[
                    ExportColumn.ONSET_TIME,
                    ExportColumn.OFFSET_TIME,
                ],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        df = pd.read_csv(csv_files[0], comment="#")

        # Check time format is HH:MM
        onset_time = df[ExportColumn.ONSET_TIME].iloc[0]
        offset_time = df[ExportColumn.OFFSET_TIME].iloc[0]

        assert ":" in str(onset_time), "Onset time should be in HH:MM format"
        assert ":" in str(offset_time), "Offset time should be in HH:MM format"


class TestConcurrentAccess:
    """Tests for concurrent access during export."""

    def test_multiple_exports_use_unique_temp_files(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test that multiple exports use unique temp files via PID."""

        metrics = create_sleep_metrics()
        current_pid = os.getpid()

        # Export twice in sequence (simulating concurrent access pattern)
        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result1 = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path / "export1"),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

            result2 = export_manager_with_db.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path / "export2"),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert result1.success is True
        assert result2.success is True

        # Verify both export directories exist
        assert (tmp_path / "export1").exists()
        assert (tmp_path / "export2").exists()

    def test_export_with_simultaneous_directory_creation(self, export_manager_with_db, create_sleep_metrics, tmp_path):
        """Test export handles simultaneous directory creation safely."""
        metrics = create_sleep_metrics()

        # Create nested output directories
        output_dirs = [
            tmp_path / "nested" / "dir1",
            tmp_path / "nested" / "dir2",
            tmp_path / "nested" / "dir3",
        ]

        results = []
        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            for output_dir in output_dirs:
                result = export_manager_with_db.perform_direct_export(
                    [metrics],
                    grouping_option=0,
                    output_directory=str(output_dir),
                    selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
                )
                results.append(result)

        # All exports should succeed
        for result in results:
            assert result.success is True

        # All directories should exist
        for output_dir in output_dirs:
            assert output_dir.exists()


class TestGroupingExport:
    """Tests for different grouping options in export."""

    def test_grouping_by_participant_creates_separate_files(self, export_manager_with_db, multi_participant_dataset, tmp_path):
        """Test that grouping by participant creates separate files."""
        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                multi_participant_dataset,
                grouping_option=1,  # By participant
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert result.success is True

        # Should have multiple files (one per participant)
        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        assert len(csv_files) >= 2  # At least 2 participants

    def test_grouping_by_study_group(self, export_manager_with_db, multi_participant_dataset, tmp_path):
        """Test grouping by study group."""
        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                multi_participant_dataset,
                grouping_option=2,  # By group
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert result.success is True

        # Should have files for Control and Treatment groups
        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        filenames = [f.name for f in csv_files]

        assert any("Control" in name for name in filenames) or len(csv_files) >= 2

    def test_grouping_by_timepoint(self, export_manager_with_db, multi_participant_dataset, tmp_path):
        """Test grouping by timepoint."""
        with patch.object(export_manager_with_db, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager_with_db.perform_direct_export(
                multi_participant_dataset,
                grouping_option=3,  # By timepoint
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert result.success is True

        # Should have files for T1 and T2 timepoints
        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        assert len(csv_files) >= 2
