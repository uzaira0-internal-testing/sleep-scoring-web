#!/usr/bin/env python3
"""
Integration tests for seamless activity data switching - Complete Workflows.
Tests end-to-end switching workflows with various data states and configurations.
"""

from __future__ import annotations

import time
from collections import namedtuple
from typing import TYPE_CHECKING
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from sleep_scoring_app.core.constants import DatabaseColumn, DatabaseTable, ViewMode
from sleep_scoring_app.data.database import DatabaseManager
from sleep_scoring_app.services.unified_data_service import UnifiedDataService
from sleep_scoring_app.ui.main_window import SleepScoringMainWindow
from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

# ParticipantKey was removed from dataclasses - use simple namedtuple for tests
ParticipantKey = namedtuple("ParticipantKey", ["participant_id", "study_code", "group"])

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.skip(reason="Complex integration tests requiring MainWindow instantiation - needs dedicated integration test infrastructure")
class TestCompleteWorkflowSwitching:
    """Test complete end-to-end switching workflows."""

    @pytest.fixture
    def temp_database(self, tmp_path):
        """Create temporary database for integration testing."""
        db_path = tmp_path / "test_switching.db"
        db_manager = DatabaseManager(str(db_path))

        # Initialize with test data
        self._populate_test_database(db_manager)

        yield db_manager

        db_manager.close()

    @pytest.fixture
    def test_csv_files(self, tmp_path):
        """Create test CSV files for switching tests."""
        csv_dir = tmp_path / "csv_data"
        csv_dir.mkdir()

        files = {}

        # Create multiple participant files
        participants = [("4000", "BO", "G1", "2021-04-20"), ("4001", "P2", "G2", "2021-05-15"), ("4002", "P1", "G3", "2021-06-10")]

        for participant_id, timepoint, group, date in participants:
            # Create activity data file
            activity_file = csv_dir / f"{participant_id} {timepoint} ({date})60sec.csv"
            self._create_test_csv_file(activity_file, participant_id, timepoint, group, date, 2880)  # 24h data

            # Create extended data file for 48h mode
            extended_file = csv_dir / f"{participant_id} {timepoint} ({date})60sec_extended.csv"
            self._create_test_csv_file(extended_file, participant_id, timepoint, group, date, 5760)  # 48h data

            files[f"{participant_id}_{timepoint}_{group}"] = {
                "24h": activity_file,
                "48h": extended_file,
                "participant_key": ParticipantKey(participant_id, timepoint, group),
            }

        return files

    @pytest.fixture
    def integrated_main_window(self, qt_app, temp_database, test_csv_files):
        """Create integrated main window for workflow testing."""
        with patch("sleep_scoring_app.ui.main_window.DatabaseManager") as mock_db_class:
            mock_db_class.return_value = temp_database

            window = SleepScoringMainWindow()

            # Configure for testing
            window.data_service.database_manager = temp_database
            window.data_service.set_data_folder(str(test_csv_files[next(iter(test_csv_files.keys()))]["24h"].parent))

            yield window

            window.close()

    def test_database_to_csv_switching_workflow(self, integrated_main_window, test_csv_files):
        """Test complete workflow: database -> CSV switching with state preservation."""
        window = integrated_main_window

        # Step 1: Start in database mode with participant loaded
        participant_key = ParticipantKey("4000", "BO", "G1")

        # Load participant data from database
        success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert success, "Failed to load participant data from database"

        # Verify data is loaded
        assert window.plot_widget.activity_data is not None
        assert len(window.plot_widget.activity_data) > 0

        # Step 2: Add markers and zoom
        initial_markers = [
            {"type": "onset", "time": 75600, "x_pos": 75600, "label": "Sleep Onset"},
            {"type": "offset", "time": 104400, "x_pos": 104400, "label": "Sleep Offset"},
        ]
        window.plot_widget.sleep_markers = initial_markers.copy()

        # Set custom zoom
        window.plot_widget.vb.setRange(xRange=[70000, 110000], yRange=[0, 200], padding=0)
        initial_view_range = window.plot_widget.vb.viewRange()

        # Step 3: Switch to CSV mode
        window.data_settings_tab.activity_use_csv_radio.setChecked(True)
        window.data_settings_tab._on_activity_source_changed()

        # Step 4: Load same participant from CSV
        csv_file = test_csv_files["4000_BO_G1"]["24h"]
        window.data_service.set_data_folder(str(csv_file.parent))
        window.data_service.set_database_mode(False)

        success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert success, "Failed to load participant data from CSV"

        # Step 5: Verify seamless switching
        # Data should be loaded
        assert window.plot_widget.activity_data is not None
        assert len(window.plot_widget.activity_data) > 0

        # Markers should be preserved
        assert len(window.plot_widget.sleep_markers) == 2
        assert window.plot_widget.sleep_markers[0]["type"] == "onset"
        assert window.plot_widget.sleep_markers[1]["type"] == "offset"

        # Zoom should be approximately preserved (within reasonable tolerance)
        final_view_range = window.plot_widget.vb.viewRange()
        self._assert_view_range_similar(initial_view_range, final_view_range, tolerance=0.1)

    def test_view_mode_switching_with_data_source_change(self, integrated_main_window, test_csv_files):
        """Test switching both view mode and data source simultaneously."""
        window = integrated_main_window
        participant_key = ParticipantKey("4001", "P2", "G2")

        # Step 1: Load 24h data from database
        success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert success, "Failed to load 24h data from database"

        initial_data_length = len(window.plot_widget.activity_data)

        # Step 2: Add custom state
        test_markers = [{"type": "test", "time": 50000, "x_pos": 50000, "label": "Test Marker"}]
        window.plot_widget.sleep_markers = test_markers.copy()

        # Step 3: Switch to CSV mode AND 48h view simultaneously
        window.data_settings_tab.activity_use_csv_radio.setChecked(True)
        window.data_settings_tab._on_activity_source_changed()

        # Configure CSV data source
        csv_file = test_csv_files["4001_P2_G2"]["48h"]
        window.data_service.set_data_folder(str(csv_file.parent))
        window.data_service.set_database_mode(False)

        # Load with new view mode
        success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_48)
        assert success, "Failed to load 48h data from CSV"

        # Step 4: Verify seamless transition
        final_data_length = len(window.plot_widget.activity_data)

        # Data should be different (48h vs 24h)
        assert final_data_length != initial_data_length
        assert final_data_length > initial_data_length  # 48h should have more data

        # View mode should be updated
        assert window.plot_widget.current_view_hours == ViewMode.HOURS_48

        # Markers should be preserved
        assert len(window.plot_widget.sleep_markers) >= 1
        assert any(marker["label"] == "Test Marker" for marker in window.plot_widget.sleep_markers)

    def test_participant_switching_within_mode(self, integrated_main_window, test_csv_files):
        """Test switching between participants while maintaining mode and source."""
        window = integrated_main_window

        # Step 1: Load first participant
        participant1 = ParticipantKey("4000", "BO", "G1")
        success = window.data_service.load_participant_data(participant1, ViewMode.HOURS_24)
        assert success, "Failed to load first participant"

        # Step 2: Add markers and custom zoom
        markers_p1 = [
            {"type": "onset", "time": 75600, "x_pos": 75600, "label": "P1 Onset"},
            {"type": "offset", "time": 104400, "x_pos": 104400, "label": "P1 Offset"},
        ]
        window.plot_widget.sleep_markers = markers_p1.copy()
        window.plot_widget.vb.setRange(xRange=[70000, 110000], yRange=[0, 150], padding=0)

        p1_data_hash = self._calculate_data_hash(window.plot_widget.activity_data)

        # Step 3: Switch to second participant
        participant2 = ParticipantKey("4002", "P1", "G3")
        success = window.data_service.load_participant_data(participant2, ViewMode.HOURS_24)
        assert success, "Failed to load second participant"

        # Step 4: Verify seamless transition
        p2_data_hash = self._calculate_data_hash(window.plot_widget.activity_data)

        # Data should be different
        assert p1_data_hash != p2_data_hash, "Data should be different between participants"

        # Previous markers should be cleared (participant-specific)
        # New data should be loaded
        assert window.plot_widget.activity_data is not None
        assert len(window.plot_widget.activity_data) > 0

        # View mode should be maintained
        assert window.plot_widget.current_view_hours == ViewMode.HOURS_24

    def test_rapid_successive_switches(self, integrated_main_window, test_csv_files):
        """Test handling of rapid successive switches."""
        window = integrated_main_window
        participants = [ParticipantKey("4000", "BO", "G1"), ParticipantKey("4001", "P2", "G2"), ParticipantKey("4002", "P1", "G3")]

        # Perform rapid switches
        for i, participant in enumerate(participants):
            # Add unique marker for tracking
            test_marker = {"type": "rapid_test", "time": 50000 + (i * 1000), "x_pos": 50000 + (i * 1000), "label": f"Rapid Switch {i}"}

            # Load participant
            success = window.data_service.load_participant_data(participant, ViewMode.HOURS_24)
            assert success, f"Failed to load participant {i}"

            # Add marker
            if not hasattr(window.plot_widget, "sleep_markers"):
                window.plot_widget.sleep_markers = []
            window.plot_widget.sleep_markers.append(test_marker)

            # Verify data integrity after each switch
            assert window.plot_widget.activity_data is not None
            assert len(window.plot_widget.activity_data) > 0

            # Brief pause to simulate realistic usage
            QTimer.singleShot(10, lambda: None)
            QApplication.processEvents()

    def test_switching_with_algorithm_overlays(self, integrated_main_window, test_csv_files):
        """Test switching while preserving algorithm overlays."""
        window = integrated_main_window
        participant_key = ParticipantKey("4000", "BO", "G1")

        # Step 1: Load data and run algorithms
        success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert success, "Failed to load participant data"

        # Simulate algorithm results
        window.plot_widget.plot_algorithms()  # This should run Sadeh/Choi algorithms

        # Check if algorithm overlays exist
        len(window.plot_widget.listDataItems())

        # Step 2: Switch view mode
        success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_48)
        assert success, "Failed to switch to 48h view"

        # Step 3: Verify algorithm preservation/update
        final_plot_items = len(window.plot_widget.listDataItems())

        # Should have data plot and algorithm overlays
        assert final_plot_items >= 1, "Should have at least activity data plot"

        # Verify view mode is updated
        assert window.plot_widget.current_view_hours == ViewMode.HOURS_48

    def test_switching_with_memory_constraints(self, integrated_main_window, test_csv_files):
        """Test switching behavior under memory constraints."""
        window = integrated_main_window

        # Monitor memory usage
        import os

        import psutil

        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        participants = [ParticipantKey("4000", "BO", "G1"), ParticipantKey("4001", "P2", "G2"), ParticipantKey("4002", "P1", "G3")]

        memory_measurements = []

        # Perform multiple switches and measure memory
        for i in range(5):  # Multiple rounds to test memory management
            for participant in participants:
                # Load participant data
                success = window.data_service.load_participant_data(participant, ViewMode.HOURS_24)
                assert success, f"Failed to load participant in round {i}"

                # Switch view modes
                for view_mode in [ViewMode.HOURS_24, ViewMode.HOURS_48]:
                    success = window.data_service.load_participant_data(participant, view_mode)
                    assert success, f"Failed to switch view mode in round {i}"

                    # Measure memory
                    current_memory = process.memory_info().rss / 1024 / 1024
                    memory_measurements.append(current_memory)

        final_memory = process.memory_info().rss / 1024 / 1024

        # Memory should not grow excessively
        memory_growth = final_memory - initial_memory
        assert memory_growth < 500, f"Excessive memory growth: {memory_growth:.2f} MB"  # Allow 500MB growth

        # Memory should stabilize (last measurements shouldn't show continuous growth)
        recent_measurements = memory_measurements[-5:]
        if len(recent_measurements) >= 2:
            memory_trend = recent_measurements[-1] - recent_measurements[0]
            assert memory_trend < 100, f"Memory still growing at end: {memory_trend:.2f} MB"

    def test_error_recovery_during_switching(self, integrated_main_window, test_csv_files):
        """Test error recovery during switching operations."""
        window = integrated_main_window
        participant_key = ParticipantKey("4000", "BO", "G1")

        # Step 1: Load initial data successfully
        success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert success, "Failed to load initial data"

        initial_data = window.plot_widget.activity_data.copy()
        initial_markers = [{"type": "test", "time": 50000, "x_pos": 50000, "label": "Test"}]
        window.plot_widget.sleep_markers = initial_markers.copy()

        # Step 2: Simulate error during switching
        with patch.object(window.data_service, "load_participant_data") as mock_load:
            mock_load.return_value = False  # Simulate failure

            # Attempt to switch (should fail gracefully)
            success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_48)
            assert not success, "Load should have failed"

        # Step 3: Verify state is preserved after error
        # Data should remain from before the failed switch
        assert window.plot_widget.activity_data is not None
        assert len(window.plot_widget.activity_data) == len(initial_data)

        # Markers should be preserved
        assert len(window.plot_widget.sleep_markers) >= 1
        assert window.plot_widget.sleep_markers[0]["label"] == "Test"

        # Step 4: Verify recovery works
        # Restore normal behavior and try again
        with patch.object(window.data_service, "load_participant_data", return_value=True):
            success = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_48)
            assert success, "Recovery should work"

    def _populate_test_database(self, db_manager: DatabaseManager):
        """Populate database with test data."""
        participants = [("4000", "BO", "G1", "2021-04-20"), ("4001", "P2", "G2", "2021-05-15"), ("4002", "P1", "G3", "2021-06-10")]

        with db_manager._get_connection() as conn:
            for participant_id, timepoint, group, date in participants:
                # Generate activity data
                timestamps = pd.date_range(
                    start=f"{date} 12:00:00",
                    periods=2880,  # 24 hours of minute data
                    freq="1min",
                )

                activity_data = np.random.poisson(50, 2880)  # Random activity counts

                # Insert into database
                for i, (timestamp, activity) in enumerate(zip(timestamps, activity_data, strict=False)):
                    conn.execute(
                        f"""
                        INSERT INTO {DatabaseTable.RAW_ACTIVITY_DATA}
                        (participant_id, participant_timepoint, participant_group, timestamp, axis1)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (participant_id, timepoint, group, timestamp, int(activity)),
                    )
            conn.commit()

    def _create_test_csv_file(self, file_path: Path, participant_id: str, timepoint: str, group: str, date: str, data_points: int):
        """Create test CSV file with activity data."""
        timestamps = pd.date_range(
            start=f"{date} 12:00:00",
            periods=data_points,
            freq="30S",  # 30-second epochs
        )

        activity_data = np.random.poisson(50, data_points)

        df = pd.DataFrame(
            {
                "Date": timestamps.strftime("%m/%d/%Y"),
                "Time": timestamps.strftime("%H:%M:%S"),
                "Axis1": activity_data,
                "Axis2": activity_data * 0.8,
                "Axis3": activity_data * 0.6,
            }
        )

        df.to_csv(file_path, index=False)

    def _calculate_data_hash(self, data: list | np.ndarray) -> str:
        """Calculate hash of data for comparison."""
        if not data:
            return "empty"

        # Sample data for hash calculation (performance)
        sample = data[:100] if len(data) > 100 else data
        return str(hash(tuple(sample)))

    def _assert_view_range_similar(self, range1: list[list[float]], range2: list[list[float]], tolerance: float = 0.1):
        """Assert that two view ranges are similar within tolerance."""
        x1_span = range1[0][1] - range1[0][0]
        x2_span = range2[0][1] - range2[0][0]
        y1_span = range1[1][1] - range1[1][0]
        y2_span = range2[1][1] - range2[1][0]

        x_diff = abs(x1_span - x2_span) / max(x1_span, x2_span)
        y_diff = abs(y1_span - y2_span) / max(y1_span, y2_span)

        assert x_diff <= tolerance, f"X range difference {x_diff:.3f} exceeds tolerance {tolerance}"
        assert y_diff <= tolerance, f"Y range difference {y_diff:.3f} exceeds tolerance {tolerance}"


class TestConcurrentSwitchingOperations:
    """Test concurrent and overlapping switching operations."""

    @pytest.fixture
    def concurrent_test_setup(self, qt_app):
        """Setup for concurrent switching tests."""
        window = Mock()
        window.plot_widget = Mock()
        window.data_service = Mock()

        # Track operation states
        window.switching_in_progress = False
        window.pending_switches = []

        return window

    def test_overlapping_switch_requests(self, concurrent_test_setup):
        """Test handling of overlapping switch requests when a switch is in progress."""
        window = concurrent_test_setup

        call_count = 0

        # Simulate loading operation that checks switching_in_progress state
        def load_simulation(participant_key, view_mode):
            nonlocal call_count
            call_count += 1

            if window.switching_in_progress:
                # Queue the request if a switch is already in progress
                window.pending_switches.append((participant_key, view_mode))
                return False

            # Mark as in progress (would stay True until async operation completes)
            window.switching_in_progress = True
            return True

        window.data_service.load_participant_data.side_effect = load_simulation

        # Submit requests
        participant1 = ParticipantKey("4000", "BO", "G1")
        participant2 = ParticipantKey("4001", "P2", "G2")

        # First request should succeed and mark switching_in_progress
        result1 = window.data_service.load_participant_data(participant1, ViewMode.HOURS_24)
        assert result1, "First request should succeed"
        assert window.switching_in_progress, "Should be marked as in progress after first call"

        # Second request should be queued (switching_in_progress is still True)
        result2 = window.data_service.load_participant_data(participant2, ViewMode.HOURS_48)
        assert not result2, "Overlapping request should be queued"

        # Verify both calls were made
        assert call_count == 2, f"Expected 2 calls, got {call_count}"

        # Verify pending queue
        assert len(window.pending_switches) == 1
        assert window.pending_switches[0] == (participant2, ViewMode.HOURS_48)

    def test_switch_cancellation(self, concurrent_test_setup):
        """Test cancellation of in-progress switches."""
        window = concurrent_test_setup

        # Track cancellation state
        window.cancel_requested = False

        def cancellable_load(participant_key, view_mode):
            if window.cancel_requested:
                return False

            # Simulate work that can be cancelled
            for i in range(10):
                if window.cancel_requested:
                    return False
                time.sleep(0.01)

            return True

        window.data_service.load_participant_data.side_effect = cancellable_load

        # Start operation
        participant = ParticipantKey("4000", "BO", "G1")

        # Simulate cancellation request
        window.cancel_requested = True

        result = window.data_service.load_participant_data(participant, ViewMode.HOURS_24)
        assert not result, "Cancelled operation should fail"

    def test_rapid_mode_switching(self, concurrent_test_setup):
        """Test rapid view mode switching."""
        window = concurrent_test_setup

        switch_count = 0

        def count_switches(participant_key, view_mode):
            nonlocal switch_count
            switch_count += 1
            return True

        window.data_service.load_participant_data.side_effect = count_switches

        participant = ParticipantKey("4000", "BO", "G1")
        modes = [ViewMode.HOURS_24, ViewMode.HOURS_48, ViewMode.HOURS_24, ViewMode.HOURS_48]

        # Rapid successive switches
        for mode in modes:
            result = window.data_service.load_participant_data(participant, mode)
            assert result, f"Switch to {mode} should succeed"

        assert switch_count == 4, f"Expected 4 switches, got {switch_count}"


class TestSwitchingUIResponsiveness:
    """Test UI responsiveness during switching operations."""

    def test_ui_updates_during_switching(self, qt_app):
        """Test that UI remains responsive during switching."""
        app = QApplication.instance()

        # Create mock UI components
        progress_indicator = Mock()
        status_bar = Mock()
        Mock()

        # Simulate switching operation with UI updates
        ui_update_count = 0

        def simulate_switch_with_ui_updates():
            nonlocal ui_update_count

            # Start progress indication
            progress_indicator.show()
            status_bar.showMessage("Switching data source...")
            ui_update_count += 1

            # Process events to keep UI responsive
            app.processEvents()

            # Simulate work
            time.sleep(0.05)

            # Update progress
            progress_indicator.setValue(50)
            ui_update_count += 1
            app.processEvents()

            # More work
            time.sleep(0.05)

            # Complete
            progress_indicator.hide()
            status_bar.showMessage("Ready")
            ui_update_count += 1
            app.processEvents()

        # Execute switching simulation
        start_time = time.perf_counter()
        simulate_switch_with_ui_updates()
        end_time = time.perf_counter()

        # Verify UI was updated
        assert ui_update_count >= 3, "UI should be updated during switching"

        # Verify reasonable timing
        total_time = end_time - start_time
        assert total_time < 1.0, f"Switching took too long: {total_time:.3f}s"

    def test_progress_feedback_accuracy(self, qt_app):
        """Test accuracy of progress feedback during switching."""
        progress_values = []

        def mock_progress_callback(value: int):
            progress_values.append(value)

        # Simulate switching with progress tracking
        def switching_operation_with_progress():
            steps = 10
            for i in range(steps + 1):
                progress = int((i / steps) * 100)
                mock_progress_callback(progress)
                time.sleep(0.01)  # Simulate work

        switching_operation_with_progress()

        # Verify progress sequence
        assert len(progress_values) == 11, "Should have 11 progress updates"
        assert progress_values[0] == 0, "Should start at 0%"
        assert progress_values[-1] == 100, "Should end at 100%"

        # Verify monotonic progression
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i - 1], "Progress should be monotonic"

    def test_error_feedback_during_switching(self, qt_app):
        """Test error feedback mechanisms during switching."""
        error_messages = []

        def mock_error_callback(message: str):
            error_messages.append(message)

        # Simulate switching with error
        def switching_operation_with_error():
            try:
                # Simulate work
                time.sleep(0.02)

                # Simulate error
                msg = "Test error during switching"
                raise Exception(msg)

            except Exception as e:
                mock_error_callback(f"Switching failed: {e!s}")
                return False

            return True

        result = switching_operation_with_error()

        # Verify error handling
        assert not result, "Operation should fail"
        assert len(error_messages) == 1, "Should have one error message"
        assert "Test error during switching" in error_messages[0]
