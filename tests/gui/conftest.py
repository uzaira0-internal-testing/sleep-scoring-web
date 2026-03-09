#!/usr/bin/env python3
"""
GUI-specific test fixtures.
Provides fixtures for testing PyQt6 widgets and components.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from sleep_scoring_app.core.constants import FileSourceType, MarkerType, ParticipantGroup, ParticipantTimepoint
from sleep_scoring_app.core.dataclasses import DailySleepMarkers, FileInfo, ParticipantInfo, SleepMetrics, SleepPeriod


@pytest.fixture(autouse=True)
def mock_message_box(monkeypatch):
    """Mock QMessageBox to prevent blocking during tests.

    NOTE: autouse=True ensures ALL gui tests automatically get mocked dialogs,
    preventing any blocking dialog boxes during test runs.
    """
    mock_box = Mock()
    mock_box.exec.return_value = QMessageBox.StandardButton.Yes
    mock_box.information = Mock(return_value=QMessageBox.StandardButton.Ok)
    mock_box.warning = Mock(return_value=QMessageBox.StandardButton.Ok)
    mock_box.question = Mock(return_value=QMessageBox.StandardButton.Yes)
    mock_box.critical = Mock(return_value=QMessageBox.StandardButton.Ok)

    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.exec", lambda self: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.information", mock_box.information)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.warning", mock_box.warning)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.question", mock_box.question)
    monkeypatch.setattr("PyQt6.QtWidgets.QMessageBox.critical", mock_box.critical)

    return mock_box


@pytest.fixture(autouse=True)
def mock_file_dialog(monkeypatch):
    """Mock QFileDialog to prevent blocking during tests.

    NOTE: autouse=True ensures ALL gui tests automatically get mocked dialogs,
    preventing any blocking file dialogs during test runs.
    """
    mock_dialog = Mock()
    mock_dialog.getExistingDirectory = Mock(return_value="/test/directory")
    mock_dialog.getOpenFileName = Mock(return_value=("/test/file.csv", "CSV Files (*.csv)"))
    mock_dialog.getOpenFileNames = Mock(return_value=(["/test/file1.csv", "/test/file2.csv"], "CSV Files (*.csv)"))
    mock_dialog.getSaveFileName = Mock(return_value=("/test/output.csv", "CSV Files (*.csv)"))

    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getExistingDirectory", mock_dialog.getExistingDirectory)
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileName", mock_dialog.getOpenFileName)
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getOpenFileNames", mock_dialog.getOpenFileNames)
    monkeypatch.setattr("PyQt6.QtWidgets.QFileDialog.getSaveFileName", mock_dialog.getSaveFileName)

    return mock_dialog


@pytest.fixture
def sample_activity_data():
    """Generate sample activity data for testing."""
    base_time = datetime(2021, 4, 20, 12, 0, 0)
    timestamps = [base_time + timedelta(minutes=i) for i in range(2880)]  # 48 hours of minute data
    activity_counts = np.random.randint(0, 300, size=2880).tolist()

    return {
        "timestamps": timestamps,
        "activity": activity_counts,
        "axis_y": np.random.randint(0, 300, size=2880).tolist(),
        "vector_magnitude": np.random.randint(0, 500, size=2880).tolist(),
    }


@pytest.fixture
def sample_sleep_markers():
    """Generate sample sleep markers for testing."""
    base_time = datetime(2021, 4, 20, 22, 0, 0)  # 10 PM
    onset_timestamp = base_time.timestamp()
    offset_timestamp = (base_time + timedelta(hours=8)).timestamp()  # 6 AM next day

    return {
        "onset": onset_timestamp,
        "offset": offset_timestamp,
        "onset_datetime": base_time,
        "offset_datetime": base_time + timedelta(hours=8),
    }


@pytest.fixture
def sample_daily_sleep_markers(sample_sleep_markers):
    """Create DailySleepMarkers object for testing."""
    markers = DailySleepMarkers()

    main_sleep = SleepPeriod(
        onset_timestamp=sample_sleep_markers["onset"],
        offset_timestamp=sample_sleep_markers["offset"],
        marker_index=1,
        marker_type=MarkerType.MAIN_SLEEP,
    )

    markers.period_1 = main_sleep
    return markers


@pytest.fixture
def sample_participant():
    """Create sample participant info."""
    return ParticipantInfo(
        numerical_id="4000",
        full_id="4000 T1 G1",
        group=ParticipantGroup.GROUP_1,
        timepoint=ParticipantTimepoint.T1,
        date="2021-04-20",
    )


@pytest.fixture
def sample_sleep_metrics(sample_participant, sample_daily_sleep_markers):
    """Create sample SleepMetrics object."""
    from sleep_scoring_app.core.constants import AlgorithmType

    return SleepMetrics(
        participant=sample_participant,
        filename="4000 BO (2021-04-20)60sec.csv",
        analysis_date="2021-04-20",
        algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
        daily_sleep_markers=sample_daily_sleep_markers,
        onset_time="22:00",
        offset_time="06:00",
        total_sleep_time=420.0,  # 7 hours
        sleep_efficiency=87.5,
        total_minutes_in_bed=480.0,  # 8 hours
        waso=45.0,
        awakenings=3,
        average_awakening_length=15.0,
        total_activity=15000,
        movement_index=2.5,
        fragmentation_index=12.3,
        sleep_fragmentation_index=8.7,
        sleep_algorithm_onset="22:03",
        sleep_algorithm_offset="05:58",
        overlapping_nonwear_minutes_algorithm=100,
        overlapping_nonwear_minutes_sensor=50,
        updated_at=datetime.now().isoformat(),
    )


@pytest.fixture
def sample_file_list():
    """Generate sample file list for testing."""
    return [
        FileInfo(
            filename="4000 BO (2021-04-20)60sec.csv",
            source_path=Path("/test/data/4000 BO (2021-04-20)60sec.csv"),
            source=FileSourceType.DATABASE,
            completed_count=5,
            total_dates=10,
            start_date="2021-04-20",
            end_date="2021-04-29",
        ),
        FileInfo(
            filename="4001 P1 (2021-05-15)60sec.csv",
            source_path=Path("/test/data/4001 P1 (2021-05-15)60sec.csv"),
            source=FileSourceType.DATABASE,
            completed_count=8,
            total_dates=10,
            start_date="2021-05-15",
            end_date="2021-05-24",
        ),
        FileInfo(
            filename="4002 P2 (2021-06-10)60sec.csv",
            source_path=Path("/test/data/4002 P2 (2021-06-10)60sec.csv"),
            source=FileSourceType.CSV,
            completed_count=0,
            total_dates=10,
            start_date="2021-06-10",
            end_date="2021-06-19",
        ),
    ]


@pytest.fixture
def mock_plot_widget():
    """Create a mock activity plot widget."""
    mock_plot = Mock()
    mock_plot.timestamps = []
    mock_plot.activity_data = []
    mock_plot.sadeh_results = []
    mock_plot.daily_sleep_markers = DailySleepMarkers()
    mock_plot.get_selected_marker_period = Mock(return_value=None)
    mock_plot.get_choi_results_per_minute = Mock(return_value=[])
    mock_plot.get_nonwear_sensor_results_per_minute = Mock(return_value=[])
    mock_plot.clear_sleep_markers = Mock()
    mock_plot.load_daily_sleep_markers = Mock()
    mock_plot.redraw_markers = Mock()
    mock_plot.apply_sleep_scoring_rules = Mock()
    mock_plot.move_marker_to_timestamp = Mock(return_value=True)
    mock_plot.markers_saved = False

    return mock_plot


@pytest.fixture
def mock_database_with_data(mock_database_manager, sample_sleep_metrics):
    """Database manager with sample data."""
    mock_database_manager.load_sleep_metrics.return_value = [sample_sleep_metrics]
    mock_database_manager.save_sleep_metrics.return_value = True
    mock_database_manager.delete_sleep_metrics_for_date.return_value = True
    mock_database_manager.get_database_stats.return_value = {
        "unique_files": 3,
        "total_records": 15,
        "autosave_records": 5,
    }
    return mock_database_manager


@pytest.fixture
def mock_data_manager():
    """Create mock data manager for testing."""
    mock_manager = Mock()
    mock_manager.use_database = True
    mock_manager.data_folder = "/test/data"
    mock_manager.discover_files = Mock(return_value=[])
    mock_manager.load_real_data = Mock(return_value=([], []))
    mock_manager.extract_enhanced_participant_info = Mock(
        return_value={
            "numerical_participant_id": "4000",
            "full_participant_id": "4000 T1 G1",
            "participant_group": ParticipantGroup.GROUP_1,
            "participant_timepoint": ParticipantTimepoint.T1,
        }
    )
    mock_manager.calculate_sleep_metrics_object = Mock(return_value=None)

    return mock_manager


@pytest.fixture
def mock_export_manager():
    """Create mock export manager."""
    mock_export = Mock()
    mock_export.save_comprehensive_sleep_metrics = Mock(return_value=True)
    mock_export.export_to_csv = Mock(return_value=True)
    mock_export.export_to_excel = Mock(return_value=True)

    return mock_export


@pytest.fixture
def sample_marker_table_data():
    """Generate sample data for marker tables."""
    base_time = datetime(2021, 4, 20, 22, 0, 0)

    data = []
    for i in range(-10, 11):  # 21 rows: 10 before, marker, 10 after
        timestamp = base_time + timedelta(minutes=i)
        data.append(
            {
                "time": timestamp.strftime("%H:%M"),
                "timestamp": timestamp.timestamp(),
                "axis_y": 100 + i * 5,
                "vm": 150 + i * 10,
                "sadeh": 1 if abs(i) > 2 else 0,  # Sleep except near marker
                "choi": 0,  # No nonwear
                "nwt_sensor": 0,  # No nonwear
                "is_marker": i == 0,
            }
        )

    return data


@pytest.fixture
def sample_dates():
    """Generate sample date list."""
    base_date = datetime(2021, 4, 20).date()
    return [base_date + timedelta(days=i) for i in range(10)]


@pytest.fixture
def sample_algorithm_results():
    """Generate sample algorithm results (Sadeh, Choi)."""
    return {
        "sadeh": [1] * 480 + [0] * 1920 + [1] * 480,  # Sleep-Wake-Sleep pattern (2880 minutes)
        "choi": [0] * 2880,  # No nonwear
        "nonwear_sensor": [0] * 2880,  # No nonwear
    }


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton instances between tests."""
    # This fixture automatically runs before each test
    # Add any singleton reset logic here if needed
    yield
    # Cleanup after test
    import gc

    gc.collect()


def create_mock_window_with_tabs(qtbot, mock_database_manager, mock_config_manager):
    """Helper to create a mock main window with initialized tabs."""
    from sleep_scoring_app.ui.main_window import SleepScoringMainWindow

    # Mock initialization to avoid full window setup
    with patch.object(SleepScoringMainWindow, "__init__", lambda self: None):
        window = SleepScoringMainWindow()

        # Set up essential attributes
        window.db_manager = mock_database_manager
        window.config_manager = mock_config_manager

        # Add to qtbot for proper cleanup
        qtbot.addWidget(window)

        return window
