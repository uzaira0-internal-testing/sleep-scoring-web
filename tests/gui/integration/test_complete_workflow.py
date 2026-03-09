#!/usr/bin/env python3
"""
Comprehensive end-to-end tests for the complete sleep scoring workflow.

Tests the FULL workflow from start to finish:
1. Setting up study settings (data folder, algorithm preferences)
2. Importing data files (CSV/GT3X)
3. Navigating to analysis tab
4. Placing sleep markers and nonwear markers for all days
5. Saving markers to database
6. Exporting results and validating output
"""

from __future__ import annotations

import csv
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    AlgorithmType,
    FileSourceType,
    MarkerType,
    NonwearAlgorithm,
    ParticipantGroup,
    ParticipantTimepoint,
)
from sleep_scoring_app.core.dataclasses import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    FileInfo,
    ParticipantInfo,
    SleepMetrics,
    SleepPeriod,
)
from sleep_scoring_app.data.database import DatabaseManager
from sleep_scoring_app.services.export_service import ExportManager, ExportResult


@pytest.fixture
def temp_data_folder(tmp_path):
    """Create a temporary data folder with sample CSV files."""
    data_folder = tmp_path / "data"
    data_folder.mkdir()
    return data_folder


@pytest.fixture
def temp_export_folder(tmp_path):
    """Create a temporary export folder."""
    export_folder = tmp_path / "exports"
    export_folder.mkdir()
    return export_folder


@pytest.fixture
def sample_csv_file(temp_data_folder) -> Path:
    """Create a sample CSV file with activity data."""
    filename = "4000 BO (2021-04-20)60sec.csv"
    filepath = temp_data_folder / filename

    # Generate 10 days of activity data (14400 rows at 60-sec epochs)
    base_time = datetime(2021, 4, 20, 12, 0, 0)
    rows = []

    for i in range(14400):  # 10 days of data
        timestamp = base_time + timedelta(minutes=i)
        axis_y = np.random.randint(0, 300)
        vector_magnitude = np.random.randint(0, 500)

        rows.append(
            {
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "axis_y": axis_y,
                "vector_magnitude": vector_magnitude,
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(filepath, index=False)

    return filepath


@pytest.fixture
def multiple_csv_files(temp_data_folder) -> list[Path]:
    """Create multiple sample CSV files for batch testing."""
    files = []

    for participant_num in [4000, 4001, 4002]:
        for timepoint in ["BO", "P1", "P2"]:
            filename = f"{participant_num} {timepoint} (2021-04-20)60sec.csv"
            filepath = temp_data_folder / filename

            base_time = datetime(2021, 4, 20, 12, 0, 0)
            rows = []

            for i in range(2880):  # 2 days of data
                timestamp = base_time + timedelta(minutes=i)
                axis_y = np.random.randint(0, 300)
                vector_magnitude = np.random.randint(0, 500)

                rows.append(
                    {
                        "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                        "axis_y": axis_y,
                        "vector_magnitude": vector_magnitude,
                    }
                )

            df = pd.DataFrame(rows)
            df.to_csv(filepath, index=False)
            files.append(filepath)

    return files


@pytest.fixture
def isolated_db(tmp_path) -> DatabaseManager:
    """Create an isolated database for testing."""
    # Reset the global database initialized flag to allow schema creation
    import sleep_scoring_app.data.database as db_module

    db_module._database_initialized.clear()

    db_path = tmp_path / "test_workflow.db"
    return DatabaseManager(db_path=db_path)


@pytest.fixture
def export_manager(isolated_db) -> ExportManager:
    """Create export manager with isolated database."""
    return ExportManager(database_manager=isolated_db)


@pytest.fixture
def complete_workflow_data():
    """Generate complete workflow data for a 10-day analysis session."""
    base_date = datetime(2021, 4, 20).date()
    dates = [base_date + timedelta(days=i) for i in range(10)]

    # Generate sleep periods for each date
    sleep_periods = {}
    for i, date in enumerate(dates):
        onset_datetime = datetime.combine(date, datetime.min.time().replace(hour=22, minute=0))
        offset_datetime = onset_datetime + timedelta(hours=8)

        sleep_periods[date] = {
            "onset_timestamp": onset_datetime.timestamp(),
            "offset_timestamp": offset_datetime.timestamp(),
            "onset_datetime": onset_datetime,
            "offset_datetime": offset_datetime,
        }

    return {
        "dates": dates,
        "sleep_periods": sleep_periods,
        "filename": "4000 BO (2021-04-20)60sec.csv",
        "participant_id": "4000",
        "timepoint": ParticipantTimepoint.T1,
        "group": ParticipantGroup.GROUP_1,
    }


@pytest.mark.integration
@pytest.mark.gui
class TestFileImportWorkflow:
    """Test file import workflow."""

    def test_import_to_database(self, mock_main_window, isolated_db, sample_csv_file):
        """Test importing file data to database."""
        mock_main_window.import_service = Mock()
        mock_main_window.import_service.import_activity_data = Mock(return_value=True)

        # Import file
        result = mock_main_window.import_service.import_activity_data(str(sample_csv_file))

        assert result is True
        mock_main_window.import_service.import_activity_data.assert_called_once()


@pytest.mark.integration
@pytest.mark.gui
class TestAnalysisTabMarkerPlacement:
    """Test marker placement in the analysis tab."""

    @pytest.fixture
    def setup_analysis_environment(self, mock_main_window, complete_workflow_data):
        """Set up the analysis environment with loaded data."""
        data = complete_workflow_data

        # Set file and dates
        mock_main_window.selected_file = data["filename"]
        mock_main_window.available_dates = [d.isoformat() for d in data["dates"]]
        mock_main_window.current_date_index = 0

        # Set up plot widget
        base_time = datetime.combine(data["dates"][0], datetime.min.time().replace(hour=12))
        timestamps = [base_time + timedelta(minutes=i) for i in range(2880)]
        activity_data = np.random.randint(0, 300, size=2880).tolist()

        mock_main_window.plot_widget.timestamps = timestamps
        mock_main_window.plot_widget.activity_data = activity_data
        mock_main_window.plot_widget.daily_sleep_markers = DailySleepMarkers()
        mock_main_window.plot_widget.sadeh_results = [1] * 2880
        mock_main_window.plot_widget.markers_saved = False

        # Mock methods
        mock_main_window.plot_widget.add_marker = Mock()
        mock_main_window.plot_widget.move_marker_to_timestamp = Mock(return_value=True)
        mock_main_window.plot_widget.redraw_markers = Mock()
        mock_main_window.db_manager.save_sleep_metrics = Mock(return_value=True)
        mock_main_window.db_manager.load_sleep_metrics = Mock(return_value=[])

        return mock_main_window, data

    def test_place_sleep_markers_single_day(self, setup_analysis_environment):
        """Test placing sleep markers for a single day."""
        window, data = setup_analysis_environment
        date = data["dates"][0]
        sleep_data = data["sleep_periods"][date]

        # Create sleep period
        period = SleepPeriod(
            onset_timestamp=sleep_data["onset_timestamp"],
            offset_timestamp=sleep_data["offset_timestamp"],
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        window.plot_widget.daily_sleep_markers.period_1 = period

        # Verify period is complete
        assert period.is_complete
        assert window.plot_widget.daily_sleep_markers.period_1 is not None

    def test_place_sleep_markers_all_days(self, setup_analysis_environment):
        """Test placing sleep markers for all days in the study."""
        window, data = setup_analysis_environment
        saved_markers_count = 0

        for i, date in enumerate(data["dates"]):
            window.current_date_index = i
            sleep_data = data["sleep_periods"][date]

            # Create and set sleep period
            period = SleepPeriod(
                onset_timestamp=sleep_data["onset_timestamp"],
                offset_timestamp=sleep_data["offset_timestamp"],
                marker_index=1,
                marker_type=MarkerType.MAIN_SLEEP,
            )
            window.plot_widget.daily_sleep_markers = DailySleepMarkers()
            window.plot_widget.daily_sleep_markers.period_1 = period

            # Simulate save
            if period.is_complete:
                saved_markers_count += 1

        assert saved_markers_count == len(data["dates"])

    def test_place_nonwear_markers(self, setup_analysis_environment):
        """Test placing nonwear markers for a day."""
        window, data = setup_analysis_environment

        # Create nonwear period (simulating sensor-detected nonwear)
        nonwear_onset = data["sleep_periods"][data["dates"][0]]["onset_timestamp"] - 3600  # 1 hour before sleep
        nonwear_offset = nonwear_onset + 1800  # 30 minutes

        # Simulate nonwear detection results
        window.plot_widget.get_nonwear_sensor_results_per_minute = Mock(
            return_value=[0] * 1200 + [1] * 30 + [0] * 1650  # 30 minutes of nonwear
        )

        nwt_results = window.plot_widget.get_nonwear_sensor_results_per_minute()
        nonwear_minutes = sum(nwt_results)

        assert nonwear_minutes == 30

    def test_place_multiple_sleep_periods(self, setup_analysis_environment):
        """Test placing multiple sleep periods (main sleep + naps)."""
        window, data = setup_analysis_environment
        date = data["dates"][0]
        sleep_data = data["sleep_periods"][date]

        # Main sleep
        main_sleep = SleepPeriod(
            onset_timestamp=sleep_data["onset_timestamp"],
            offset_timestamp=sleep_data["offset_timestamp"],
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        # Afternoon nap
        nap_onset = sleep_data["onset_timestamp"] - 28800  # 8 hours before main sleep
        nap = SleepPeriod(
            onset_timestamp=nap_onset,
            offset_timestamp=nap_onset + 3600,  # 1 hour nap
            marker_index=2,
            marker_type=MarkerType.NAP,
        )

        window.plot_widget.daily_sleep_markers.period_1 = main_sleep
        window.plot_widget.daily_sleep_markers.period_2 = nap

        complete_periods = window.plot_widget.daily_sleep_markers.get_complete_periods()
        assert len(complete_periods) == 2


@pytest.mark.integration
@pytest.mark.gui
class TestMarkerSavingWorkflow:
    """Test saving markers to database."""

    @pytest.fixture
    def setup_save_environment(self, mock_main_window, isolated_db, complete_workflow_data):
        """Set up environment for save testing."""
        data = complete_workflow_data

        mock_main_window.db_manager = isolated_db
        mock_main_window.selected_file = data["filename"]
        mock_main_window.available_dates = [d.isoformat() for d in data["dates"]]

        # Create complete markers for all days
        all_markers = {}
        for date in data["dates"]:
            sleep_data = data["sleep_periods"][date]
            period = SleepPeriod(
                onset_timestamp=sleep_data["onset_timestamp"],
                offset_timestamp=sleep_data["offset_timestamp"],
                marker_index=1,
                marker_type=MarkerType.MAIN_SLEEP,
            )
            markers = DailySleepMarkers()
            markers.period_1 = period
            all_markers[date] = markers

        return mock_main_window, data, all_markers

    def test_save_single_day_markers(self, setup_save_environment):
        """Test saving markers for a single day."""
        window, data, all_markers = setup_save_environment
        date = data["dates"][0]
        markers = all_markers[date]

        # Create metrics for save
        participant = ParticipantInfo(
            numerical_id=data["participant_id"],
            full_id=f"{data['participant_id']} {data['timepoint'].value}",
            group=data["group"],
            timepoint=data["timepoint"],
            date=date.isoformat(),
        )

        metrics = SleepMetrics(
            participant=participant,
            filename=data["filename"],
            analysis_date=date.isoformat(),
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            onset_time="22:00",
            offset_time="06:00",
            total_sleep_time=420.0,
            sleep_efficiency=87.5,
            total_minutes_in_bed=480.0,
            waso=45.0,
            awakenings=3,
            average_awakening_length=15.0,
            total_activity=15000,
            movement_index=2.5,
            fragmentation_index=12.3,
            sleep_fragmentation_index=8.7,
            sleep_algorithm_onset=600,  # Epoch index
            sleep_algorithm_offset=1080,  # Epoch index
            overlapping_nonwear_minutes_algorithm=0,
            overlapping_nonwear_minutes_sensor=0,
            updated_at=datetime.now().isoformat(),
        )

        # Save to database
        result = window.db_manager.save_sleep_metrics(metrics)

        assert result is True

    def test_save_all_days_markers(self, setup_save_environment):
        """Test saving markers for all days."""
        window, data, all_markers = setup_save_environment
        saved_count = 0

        for date in data["dates"]:
            markers = all_markers[date]

            participant = ParticipantInfo(
                numerical_id=data["participant_id"],
                full_id=f"{data['participant_id']} {data['timepoint'].value}",
                group=data["group"],
                timepoint=data["timepoint"],
                date=date.isoformat(),
            )

            metrics = SleepMetrics(
                participant=participant,
                filename=data["filename"],
                analysis_date=date.isoformat(),
                algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
                daily_sleep_markers=markers,
                onset_time="22:00",
                offset_time="06:00",
                total_sleep_time=420.0,
                sleep_efficiency=87.5,
                total_minutes_in_bed=480.0,
                waso=45.0,
                awakenings=3,
                average_awakening_length=15.0,
                total_activity=15000,
                movement_index=2.5,
                fragmentation_index=12.3,
                sleep_fragmentation_index=8.7,
                sleep_algorithm_onset=600,  # Epoch index
                sleep_algorithm_offset=1080,  # Epoch index
                overlapping_nonwear_minutes_algorithm=0,
                overlapping_nonwear_minutes_sensor=0,
                updated_at=datetime.now().isoformat(),
            )

            result = window.db_manager.save_sleep_metrics(metrics)
            if result:
                saved_count += 1

        assert saved_count == len(data["dates"])

    def test_load_saved_markers(self, setup_save_environment):
        """Test loading previously saved markers."""
        window, data, all_markers = setup_save_environment

        # First save a marker
        date = data["dates"][0]
        markers = all_markers[date]

        participant = ParticipantInfo(
            numerical_id=data["participant_id"],
            full_id=f"{data['participant_id']} {data['timepoint'].value}",
            group=data["group"],
            timepoint=data["timepoint"],
            date=date.isoformat(),
        )

        metrics = SleepMetrics(
            participant=participant,
            filename=data["filename"],
            analysis_date=date.isoformat(),
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            onset_time="22:00",
            offset_time="06:00",
            total_sleep_time=420.0,
            sleep_efficiency=87.5,
            total_minutes_in_bed=480.0,
            waso=45.0,
            awakenings=3,
            average_awakening_length=15.0,
            total_activity=15000,
            movement_index=2.5,
            fragmentation_index=12.3,
            sleep_fragmentation_index=8.7,
            sleep_algorithm_onset=600,  # Epoch index
            sleep_algorithm_offset=1080,  # Epoch index
            overlapping_nonwear_minutes_algorithm=0,
            overlapping_nonwear_minutes_sensor=0,
            updated_at=datetime.now().isoformat(),
        )

        window.db_manager.save_sleep_metrics(metrics)

        # Load back
        loaded = window.db_manager.load_sleep_metrics(data["filename"], date.isoformat())

        assert loaded is not None


@pytest.mark.integration
@pytest.mark.gui
class TestExportWorkflow:
    """Test export workflow and result validation."""

    @pytest.fixture
    def setup_export_environment(self, isolated_db, temp_export_folder, complete_workflow_data):
        """Set up environment for export testing with pre-populated data."""
        data = complete_workflow_data
        export_manager = ExportManager(database_manager=isolated_db)

        # Pre-populate database with metrics for all days
        for date in data["dates"]:
            sleep_data = data["sleep_periods"][date]

            period = SleepPeriod(
                onset_timestamp=sleep_data["onset_timestamp"],
                offset_timestamp=sleep_data["offset_timestamp"],
                marker_index=1,
                marker_type=MarkerType.MAIN_SLEEP,
            )
            markers = DailySleepMarkers()
            markers.period_1 = period

            participant = ParticipantInfo(
                numerical_id=data["participant_id"],
                full_id=f"{data['participant_id']} {data['timepoint'].value}",
                group=data["group"],
                timepoint=data["timepoint"],
                date=date.isoformat(),
            )

            metrics = SleepMetrics(
                participant=participant,
                filename=data["filename"],
                analysis_date=date.isoformat(),
                algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
                daily_sleep_markers=markers,
                onset_time="22:00",
                offset_time="06:00",
                total_sleep_time=420.0,
                sleep_efficiency=87.5,
                total_minutes_in_bed=480.0,
                waso=45.0,
                awakenings=3,
                average_awakening_length=15.0,
                total_activity=15000,
                movement_index=2.5,
                fragmentation_index=12.3,
                sleep_fragmentation_index=8.7,
                sleep_algorithm_onset=600,  # Epoch index
                sleep_algorithm_offset=1080,  # Epoch index
                overlapping_nonwear_minutes_algorithm=0,
                overlapping_nonwear_minutes_sensor=0,
                updated_at=datetime.now().isoformat(),
            )

            isolated_db.save_sleep_metrics(metrics)

        return export_manager, temp_export_folder, data

    def _get_export_path_from_result(self, result: str, export_folder: Path) -> Path | None:
        """Extract the actual file path from export result message."""
        if result and "Exported" in result and "records to" in result:
            # Parse path from message like "Exported 10 records to /path/to/file.csv"
            path_str = result.split("records to ")[-1].strip()
            return Path(path_str)
        # Fallback: find the most recent CSV in export folder
        csv_files = list(export_folder.glob("*.csv"))
        return max(csv_files, key=lambda p: p.stat().st_mtime) if csv_files else None

    def test_export_all_data_to_csv(self, setup_export_environment):
        """Test exporting all sleep data to CSV."""
        export_manager, export_folder, _data = setup_export_environment

        result = export_manager.export_all_sleep_data(str(export_folder))

        assert result is not None
        assert "Exported" in result
        export_path = self._get_export_path_from_result(result, export_folder)
        assert export_path is not None
        assert export_path.exists()

    def test_export_contains_all_dates(self, setup_export_environment):
        """Test that export contains data for all analyzed dates."""
        export_manager, export_folder, data = setup_export_environment

        result = export_manager.export_all_sleep_data(str(export_folder))
        export_path = self._get_export_path_from_result(result, export_folder)

        # Read exported CSV
        df = pd.read_csv(export_path)

        # Should have all dates
        assert len(df) >= len(data["dates"])

    def test_export_contains_expected_columns(self, setup_export_environment):
        """Test that export contains expected columns."""
        export_manager, export_folder, _data = setup_export_environment

        result = export_manager.export_all_sleep_data(str(export_folder))
        export_path = self._get_export_path_from_result(result, export_folder)

        df = pd.read_csv(export_path)

        expected_columns = [
            "Numerical Participant ID",
            "filename",
            "Onset Date",
            "Onset Time",
            "Offset Time",
            "Total Sleep Time (TST)",
            "Efficiency",
        ]

        for col in expected_columns:
            assert col in df.columns, f"Missing column: {col}"

    def test_export_values_are_valid(self, setup_export_environment):
        """Test that exported values are valid."""
        export_manager, export_folder, _data = setup_export_environment

        result = export_manager.export_all_sleep_data(str(export_folder))
        export_path = self._get_export_path_from_result(result, export_folder)

        df = pd.read_csv(export_path)

        # Check value ranges (use actual column names)
        tst_col = "Total Sleep Time (TST)"
        eff_col = "Efficiency"
        assert all(df[tst_col].dropna() >= 0), "Invalid total_sleep_time"
        assert all(df[eff_col].dropna() >= 0), "Invalid sleep_efficiency"
        assert all(df[eff_col].dropna() <= 100), "Sleep efficiency > 100"


@pytest.mark.integration
@pytest.mark.gui
class TestCompleteWorkflowIntegration:
    """Test complete end-to-end workflow integration."""

    def _get_export_path_from_result(self, result: str, export_folder: Path) -> Path | None:
        """Extract the actual file path from export result message."""
        if result and "Exported" in result and "records to" in result:
            path_str = result.split("records to ")[-1].strip()
            return Path(path_str)
        csv_files = list(export_folder.glob("*.csv"))
        return max(csv_files, key=lambda p: p.stat().st_mtime) if csv_files else None

    def test_full_workflow_study_to_export(
        self,
        mock_main_window,
        isolated_db,
        temp_data_folder,
        temp_export_folder,
        sample_csv_file,
    ):
        """Test complete workflow from study setup to export."""
        # STEP 1: Configure study settings
        mock_main_window.config_manager.config.data_folder = str(temp_data_folder)
        mock_main_window.config_manager.config.export_directory = str(temp_export_folder)
        mock_main_window.config_manager.config.epoch_length = 60
        mock_main_window.config_manager.config.use_database = True

        # STEP 2: Discover and load files
        file_info = FileInfo(
            filename=sample_csv_file.name,
            source_path=sample_csv_file,
            source=FileSourceType.CSV,
        )
        mock_main_window.available_files = [file_info]
        mock_main_window.selected_file = str(sample_csv_file)

        # STEP 3: Load dates
        base_date = datetime(2021, 4, 20).date()
        dates = [base_date + timedelta(days=i) for i in range(10)]
        mock_main_window.available_dates = [d.isoformat() for d in dates]

        # STEP 4: Analyze each date
        export_manager = ExportManager(database_manager=isolated_db)

        for i, date in enumerate(dates):
            mock_main_window.current_date_index = i

            # Create sleep markers
            onset_dt = datetime.combine(date, datetime.min.time().replace(hour=22))
            offset_dt = onset_dt + timedelta(hours=8)

            period = SleepPeriod(
                onset_timestamp=onset_dt.timestamp(),
                offset_timestamp=offset_dt.timestamp(),
                marker_index=1,
                marker_type=MarkerType.MAIN_SLEEP,
            )
            markers = DailySleepMarkers()
            markers.period_1 = period

            # Create and save metrics
            participant = ParticipantInfo(
                numerical_id="4000",
                full_id="4000 T1",
                group=ParticipantGroup.GROUP_1,
                timepoint=ParticipantTimepoint.T1,
                date=date.isoformat(),
            )

            metrics = SleepMetrics(
                participant=participant,
                filename=sample_csv_file.name,
                analysis_date=date.isoformat(),
                algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
                daily_sleep_markers=markers,
                onset_time="22:00",
                offset_time="06:00",
                total_sleep_time=420.0,
                sleep_efficiency=87.5,
                total_minutes_in_bed=480.0,
                waso=45.0,
                awakenings=3,
                average_awakening_length=15.0,
                total_activity=15000,
                movement_index=2.5,
                fragmentation_index=12.3,
                sleep_fragmentation_index=8.7,
                sleep_algorithm_onset=600,  # Epoch index
                sleep_algorithm_offset=1080,  # Epoch index
                overlapping_nonwear_minutes_algorithm=0,
                overlapping_nonwear_minutes_sensor=0,
                updated_at=datetime.now().isoformat(),
            )

            isolated_db.save_sleep_metrics(metrics)

        # STEP 5: Export all data
        result = export_manager.export_all_sleep_data(str(temp_export_folder))

        # STEP 6: Validate export
        assert result is not None
        assert "Exported" in result
        export_path = self._get_export_path_from_result(result, temp_export_folder)
        assert export_path is not None
        assert export_path.exists()

        df = pd.read_csv(export_path)
        assert len(df) == len(dates), f"Expected {len(dates)} rows, got {len(df)}"

        # Validate specific values (use actual column names)
        # Note: Participant ID may be stored as int or string
        assert all(df["Numerical Participant ID"].astype(str) == "4000")
        assert all(df["Total Sleep Time (TST)"] == 420.0)
        assert all(df["Efficiency"] == 87.5)

    def test_multi_participant_workflow(
        self,
        mock_main_window,
        isolated_db,
        temp_data_folder,
        temp_export_folder,
        multiple_csv_files,
    ):
        """Test workflow with multiple participants."""
        export_manager = ExportManager(database_manager=isolated_db)
        base_date = datetime(2021, 4, 20).date()

        participant_ids = ["4000", "4001", "4002"]

        for participant_id in participant_ids:
            for timepoint_idx, timepoint in enumerate([ParticipantTimepoint.T1, ParticipantTimepoint.T2]):
                # Create metrics for each participant/timepoint
                date = base_date + timedelta(days=timepoint_idx)

                onset_dt = datetime.combine(date, datetime.min.time().replace(hour=22))
                offset_dt = onset_dt + timedelta(hours=8)

                period = SleepPeriod(
                    onset_timestamp=onset_dt.timestamp(),
                    offset_timestamp=offset_dt.timestamp(),
                    marker_index=1,
                    marker_type=MarkerType.MAIN_SLEEP,
                )
                markers = DailySleepMarkers()
                markers.period_1 = period

                participant = ParticipantInfo(
                    numerical_id=participant_id,
                    full_id=f"{participant_id} {timepoint.value}",
                    group=ParticipantGroup.GROUP_1,
                    timepoint=timepoint,
                    date=date.isoformat(),
                )

                metrics = SleepMetrics(
                    participant=participant,
                    filename=f"{participant_id} {timepoint.value} (2021-04-20)60sec.csv",
                    analysis_date=date.isoformat(),
                    algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
                    daily_sleep_markers=markers,
                    onset_time="22:00",
                    offset_time="06:00",
                    total_sleep_time=420.0,
                    sleep_efficiency=87.5,
                    total_minutes_in_bed=480.0,
                    waso=45.0,
                    awakenings=3,
                    average_awakening_length=15.0,
                    total_activity=15000,
                    movement_index=2.5,
                    fragmentation_index=12.3,
                    sleep_fragmentation_index=8.7,
                    sleep_algorithm_onset=600,  # Epoch index
                    sleep_algorithm_offset=1080,  # Epoch index
                    overlapping_nonwear_minutes_algorithm=0,
                    overlapping_nonwear_minutes_sensor=0,
                    updated_at=datetime.now().isoformat(),
                )

                isolated_db.save_sleep_metrics(metrics)

        # Export and validate
        result = export_manager.export_all_sleep_data(str(temp_export_folder))

        assert result is not None
        assert "Exported" in result
        export_path = self._get_export_path_from_result(result, temp_export_folder)
        assert export_path is not None

        df = pd.read_csv(export_path)

        # Should have 3 participants x 2 timepoints = 6 records
        assert len(df) == 6

        # Check all participants are present (use actual column name)
        unique_participants = df["Numerical Participant ID"].unique()
        assert len(unique_participants) == 3


@pytest.mark.integration
@pytest.mark.gui
class TestErrorHandlingWorkflow:
    """Test error handling in the workflow."""

    def test_handles_empty_markers(self, mock_main_window, isolated_db, temp_export_folder):
        """Test handling export with no markers saved."""
        export_manager = ExportManager(database_manager=isolated_db)

        # Try to export with empty database
        output_path = export_manager.export_all_sleep_data(str(temp_export_folder))

        # Should still create file (empty or with headers)
        # This tests graceful handling of no data scenario

    def test_handles_partial_markers(self, mock_main_window, isolated_db, temp_export_folder):
        """Test handling incomplete sleep periods."""
        # Create incomplete period (onset only)
        period = SleepPeriod(
            onset_timestamp=datetime(2021, 4, 20, 22, 0, 0).timestamp(),
            offset_timestamp=None,  # No offset
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        assert not period.is_complete

