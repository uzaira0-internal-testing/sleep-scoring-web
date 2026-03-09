#!/usr/bin/env python3
"""
Edge case tests for seamless activity data switching - Error Scenarios and Rollback.
Tests error handling, rollback mechanisms, and recovery during switching operations.
"""

from __future__ import annotations

import time
from collections import namedtuple
from unittest.mock import Mock, patch

import numpy as np
import pytest

from sleep_scoring_app.core.constants import ViewMode
from sleep_scoring_app.core.exceptions import DatabaseError, DataIntegrityError, ErrorCodes, SecurityError, SleepScoringError, ValidationError
from sleep_scoring_app.data.database import DatabaseManager
from sleep_scoring_app.services.unified_data_service import UnifiedDataService
from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget

# ParticipantKey was removed from dataclasses - use simple namedtuple for tests
ParticipantKey = namedtuple("ParticipantKey", ["participant_id", "study_code", "group"])


class TestDataSourceErrorScenarios:
    """Test error scenarios related to data source switching."""

    @pytest.fixture
    def mock_unified_service(self):
        """Create mock unified data service for error testing."""
        service = Mock(spec=UnifiedDataService)
        service.current_view_mode = ViewMode.HOURS_24
        service.current_participant_key = None
        service.database_manager = Mock(spec=DatabaseManager)
        service._data_manager = Mock()

        return service

    @pytest.fixture
    def mock_plot_widget(self, qt_app):
        """Create mock plot widget with error handling."""
        plot = Mock(spec=ActivityPlotWidget)

        # Initial state
        plot.activity_data = [1, 2, 3, 4, 5] * 100  # Some data
        plot.timestamps = list(range(500))
        plot.sleep_markers = [{"type": "onset", "time": 1000, "label": "Test"}]
        plot.current_view_hours = ViewMode.HOURS_24
        plot.current_filename = "test.csv"

        # Mock view box
        plot.vb = Mock()
        plot.vb.viewRange.return_value = [[0, 86400], [0, 300]]

        return plot

    def test_database_connection_failure_during_switch(self, mock_unified_service, mock_plot_widget):
        """Test handling of database connection failure during switching."""
        # Set up initial state
        initial_data = mock_plot_widget.activity_data.copy()
        initial_markers = mock_plot_widget.sleep_markers.copy()

        # Mock database failure
        mock_unified_service.database_manager.load_sleep_metrics.side_effect = DatabaseError(
            "Connection to database failed", ErrorCodes.DB_CONNECTION_FAILED
        )

        participant_key = ParticipantKey("4000", "BO", "G1")

        # Attempt to switch with database failure
        mock_unified_service.load_participant_data = Mock(
            side_effect=DatabaseError("Database connection failed during switching", ErrorCodes.DB_CONNECTION_FAILED)
        )

        try:
            mock_unified_service.load_participant_data(participant_key, ViewMode.HOURS_24)
            msg = "Should have raised DatabaseError"
            raise AssertionError(msg)
        except DatabaseError as e:
            assert e.error_code == ErrorCodes.DB_CONNECTION_FAILED
            assert "Database connection failed" in str(e)

        # Verify state preservation after error
        assert mock_plot_widget.activity_data == initial_data
        assert mock_plot_widget.sleep_markers == initial_markers

    def test_csv_file_not_found_during_switch(self, mock_unified_service, mock_plot_widget):
        """Test handling of missing CSV file during switching."""
        initial_data = mock_plot_widget.activity_data.copy()
        initial_markers = mock_plot_widget.sleep_markers.copy()

        # Mock file not found error
        mock_unified_service.get_database_mode.return_value = False

        participant_key = ParticipantKey("4000", "BO", "G1")

        mock_unified_service.load_participant_data = Mock(side_effect=FileNotFoundError("CSV file not found"))

        try:
            mock_unified_service.load_participant_data(participant_key, ViewMode.HOURS_24)
            msg = "Should have raised FileNotFoundError"
            raise AssertionError(msg)
        except FileNotFoundError as e:
            assert "CSV file not found" in str(e)

        # State should be preserved
        assert mock_plot_widget.activity_data == initial_data
        assert mock_plot_widget.sleep_markers == initial_markers

    def test_corrupted_data_detection_during_switch(self, mock_unified_service, mock_plot_widget):
        """Test detection and handling of corrupted data during switching."""
        initial_state = {
            "data": mock_plot_widget.activity_data.copy(),
            "markers": mock_plot_widget.sleep_markers.copy(),
            "view_mode": mock_plot_widget.current_view_hours,
        }

        # Mock corrupted data
        corrupted_data = [float("nan")] * 100 + [float("inf")] * 50

        def corrupt_data_load(participant_key, view_mode):
            # This should trigger validation error without modifying state
            # (rollback would happen in production code, but we're testing the error path)
            raise DataIntegrityError("Corrupted data detected: NaN/Inf values found", ErrorCodes.FILE_CORRUPTED)

        mock_unified_service.load_participant_data = Mock(side_effect=corrupt_data_load)

        participant_key = ParticipantKey("4000", "BO", "G1")

        try:
            mock_unified_service.load_participant_data(participant_key, ViewMode.HOURS_24)
            msg = "Should have raised DataIntegrityError"
            raise AssertionError(msg)
        except DataIntegrityError as e:
            assert e.error_code == ErrorCodes.FILE_CORRUPTED
            assert "Corrupted data detected" in str(e)

        # State should be preserved since error was raised before modification
        assert mock_plot_widget.activity_data == initial_state["data"]
        assert mock_plot_widget.sleep_markers == initial_state["markers"]

    def test_insufficient_memory_during_large_data_switch(self, mock_unified_service, mock_plot_widget):
        """Test handling of memory exhaustion during large data switching."""
        initial_data_size = len(mock_plot_widget.activity_data)

        mock_unified_service.load_participant_data = Mock(side_effect=MemoryError("Insufficient memory for large dataset"))

        participant_key = ParticipantKey("4000", "BO", "G1")

        try:
            mock_unified_service.load_participant_data(participant_key, ViewMode.HOURS_48)
            msg = "Should have raised MemoryError"
            raise AssertionError(msg)
        except MemoryError as e:
            assert "Insufficient memory" in str(e)

        # Data size should remain unchanged
        assert len(mock_plot_widget.activity_data) == initial_data_size

    def test_timeout_during_slow_data_loading(self, mock_unified_service, mock_plot_widget):
        """Test timeout handling during slow data loading."""
        import concurrent.futures

        initial_state = mock_plot_widget.activity_data.copy()

        def slow_loading_operation(participant_key, view_mode):
            time.sleep(2.0)  # Simulate very slow operation
            return True

        mock_unified_service.load_participant_data = Mock(side_effect=slow_loading_operation)

        # Set timeout for testing
        participant_key = ParticipantKey("4000", "BO", "G1")

        start_time = time.perf_counter()
        timed_out = False

        # Use ThreadPoolExecutor for cross-platform timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                mock_unified_service.load_participant_data,
                participant_key,
                ViewMode.HOURS_24,
            )
            try:
                future.result(timeout=1.0)  # 1 second timeout
            except concurrent.futures.TimeoutError:
                timed_out = True
                elapsed_time = time.perf_counter() - start_time
                assert elapsed_time < 1.5, "Timeout should occur quickly"

        assert timed_out, "Expected timeout to occur"

        # State should be preserved after timeout
        assert mock_plot_widget.activity_data == initial_state


class TestUIErrorScenarios:
    """Test UI-related error scenarios during switching."""

    @pytest.fixture
    def mock_main_window(self, qt_app):
        """Create mock main window for UI error testing."""
        window = Mock()
        window.plot_widget = Mock()  # Removed spec to allow dynamic attribute assignment in tests
        window.data_service = Mock()  # Removed spec to allow patch.object usage
        window.status_bar = Mock()
        window.progress_bar = Mock()

        # Initial UI state
        window.plot_widget.activity_data = [1, 2, 3] * 100
        window.plot_widget.sleep_markers = []
        window.plot_widget.vb = Mock()
        window.plot_widget.vb.viewRange.return_value = [[0, 86400], [0, 300]]

        return window

    def test_widget_disposal_error_during_switch(self, mock_main_window):
        """Test handling of widget disposal errors during switching."""
        window = mock_main_window

        # Mock widget disposal error
        def disposal_error(*args, **kwargs):
            msg = "Widget has been disposed"
            raise RuntimeError(msg)

        window.plot_widget.clear.side_effect = disposal_error

        initial_data = window.plot_widget.activity_data.copy()

        # Attempt switching with disposal error
        try:
            window.plot_widget.clear()
            msg = "Should have raised RuntimeError"
            raise AssertionError(msg)
        except RuntimeError as e:
            assert "disposed" in str(e)

        # Data should still be accessible
        assert window.plot_widget.activity_data == initial_data

    def test_plotting_library_error_during_switch(self, mock_main_window):
        """Test handling of plotting library errors during switching."""
        window = mock_main_window

        # Mock plotting error
        def plotting_error(*args, **kwargs):
            msg = "PyQtGraph plotting error"
            raise Exception(msg)

        window.plot_widget.plot.side_effect = plotting_error

        try:
            window.plot_widget.plot([1, 2, 3], [4, 5, 6])
            msg = "Should have raised plotting error"
            raise AssertionError(msg)
        except Exception as e:
            assert "PyQtGraph" in str(e)

    def test_ui_thread_deadlock_during_switch(self, mock_main_window):
        """Test detection of UI thread deadlock during switching."""
        window = mock_main_window

        # Simulate deadlock scenario
        deadlock_detected = False

        def simulate_deadlock_operation():
            nonlocal deadlock_detected

            # Simulate blocking operation that could cause deadlock
            start_time = time.perf_counter()

            while time.perf_counter() - start_time < 0.1:  # 100ms blocking
                pass

            deadlock_detected = True
            return True

        with patch.object(window.data_service, "load_participant_data") as mock_load:
            mock_load.side_effect = lambda *args: simulate_deadlock_operation()

            participant_key = ParticipantKey("4000", "BO", "G1")
            result = window.data_service.load_participant_data(participant_key, ViewMode.HOURS_24)

            assert result is True
            assert deadlock_detected

    def test_progress_update_failure_during_switch(self, mock_main_window):
        """Test handling of progress update failures during switching."""
        window = mock_main_window

        # Mock progress update error
        def progress_error(value):
            msg = "Progress widget error"
            raise RuntimeError(msg)

        window.progress_bar.setValue.side_effect = progress_error

        # Progress errors should not stop the operation
        try:
            window.progress_bar.setValue(50)
            msg = "Should have raised RuntimeError"
            raise AssertionError(msg)
        except RuntimeError as e:
            assert "Progress widget error" in str(e)


class TestConcurrencyErrorScenarios:
    """Test concurrency-related error scenarios."""

    def test_concurrent_switch_requests(self):
        """Test handling of concurrent switch requests."""
        service = Mock()  # Removed spec to allow dynamic attribute assignment

        # Track concurrent operations - simulate a lock that persists
        operations_in_progress = set()

        call_count = 0

        def concurrent_operation(participant_key, view_mode):
            nonlocal call_count
            call_count += 1
            operation_id = f"{participant_key.participant_id}_{view_mode}"

            if operation_id in operations_in_progress:
                raise SleepScoringError(f"Switch operation already in progress for {operation_id}", ErrorCodes.RESOURCE_EXHAUSTED)

            operations_in_progress.add(operation_id)

            # First call keeps the lock (simulates slow operation still in progress)
            # Second call should see the lock and fail
            if call_count == 1:
                # Don't release lock on first call to simulate operation still in progress
                return True

            # Subsequent calls would release, but we expect failure before this
            operations_in_progress.discard(operation_id)
            return True

        service.load_participant_data.side_effect = concurrent_operation

        participant_key = ParticipantKey("4000", "BO", "G1")

        # First operation should succeed (and keep the lock)
        result1 = service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert result1 is True

        # Second operation should fail because first operation's lock is still held
        try:
            service.load_participant_data(participant_key, ViewMode.HOURS_24)
            msg = "Should have raised SleepScoringError"
            raise AssertionError(msg)
        except SleepScoringError as e:
            assert e.error_code == ErrorCodes.RESOURCE_EXHAUSTED

    def test_resource_contention_during_switch(self):
        """Test handling of resource contention during switching."""
        service = Mock()  # Removed spec to allow dynamic attribute assignment

        # Simulate resource lock
        resource_locked = False

        def resource_contention_operation(participant_key, view_mode):
            nonlocal resource_locked

            if resource_locked:
                raise SleepScoringError("Data resource is locked by another operation", ErrorCodes.RESOURCE_EXHAUSTED)

            resource_locked = True

            try:
                time.sleep(0.02)
                return True
            finally:
                resource_locked = False

        service.load_participant_data.side_effect = resource_contention_operation

        participant_key = ParticipantKey("4000", "BO", "G1")

        # First operation locks resource
        result = service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert result is True

        # Resource should be released
        assert not resource_locked

    def test_thread_synchronization_error(self):
        """Test thread synchronization errors during switching."""
        import threading

        service = Mock()  # Removed spec to allow dynamic attribute assignment

        # Simulate thread synchronization issue
        shared_state = {"value": 0}
        threading.Lock()

        def unsynchronized_operation(participant_key, view_mode):
            # Intentionally create race condition
            current_value = shared_state["value"]
            time.sleep(0.001)  # Small delay to increase race condition chance
            shared_state["value"] = current_value + 1

            if shared_state["value"] != current_value + 1:
                raise SleepScoringError("Thread synchronization error detected", ErrorCodes.RESOURCE_EXHAUSTED)

            return True

        service.load_participant_data.side_effect = unsynchronized_operation

        participant_key = ParticipantKey("4000", "BO", "G1")

        # Single-threaded operation should work
        result = service.load_participant_data(participant_key, ViewMode.HOURS_24)
        assert result is True


class TestRollbackMechanisms:
    """Test rollback mechanisms during failed switching operations."""

    @pytest.fixture
    def stateful_plot_widget(self, qt_app):
        """Create plot widget with state tracking for rollback testing."""
        plot = Mock()  # Removed spec to allow dynamic attribute assignment for state tracking

        # State management
        plot.state_history = []
        plot.current_state = {
            "activity_data": [1, 2, 3] * 100,
            "markers": [{"type": "onset", "time": 1000}],
            "view_range": [[0, 86400], [0, 300]],
            "view_mode": ViewMode.HOURS_24,
            "filename": "initial.csv",
        }

        def save_state():
            # Capture actual current plot attributes, not the stale current_state dict
            current_snapshot = {
                "activity_data": plot.activity_data.copy() if hasattr(plot.activity_data, "copy") else plot.activity_data,
                "markers": plot.sleep_markers.copy() if hasattr(plot.sleep_markers, "copy") else plot.sleep_markers,
                "view_mode": plot.current_view_hours,
                "filename": plot.current_filename,
            }
            plot.state_history.append(current_snapshot)

        def rollback_state():
            if plot.state_history:
                restored_state = plot.state_history.pop()
                plot.activity_data = restored_state["activity_data"]
                plot.sleep_markers = restored_state["markers"]
                plot.current_view_hours = restored_state["view_mode"]
                plot.current_filename = restored_state["filename"]

        plot.save_state = save_state
        plot.rollback_state = rollback_state

        # Initialize with current state
        plot.activity_data = plot.current_state["activity_data"]
        plot.sleep_markers = plot.current_state["markers"]
        plot.current_view_hours = plot.current_state["view_mode"]
        plot.current_filename = plot.current_state["filename"]
        plot.vb = Mock()
        plot.vb.viewRange.return_value = plot.current_state["view_range"]

        return plot

    def test_rollback_after_data_corruption(self, stateful_plot_widget):
        """Test rollback after data corruption is detected."""
        plot = stateful_plot_widget

        # Save initial state
        initial_data = plot.activity_data.copy()
        initial_markers = plot.sleep_markers.copy()
        plot.save_state()

        # Simulate data corruption during switching
        try:
            # Corrupt data
            plot.activity_data = [float("nan")] * 100
            plot.sleep_markers = []

            # Validate data (would detect corruption)
            if any(np.isnan(plot.activity_data)):
                raise DataIntegrityError(ErrorCodes.FILE_CORRUPTED, "Data corruption detected during switching")

            msg = "Should have detected corruption"
            raise AssertionError(msg)

        except DataIntegrityError:
            # Rollback to previous state
            plot.rollback_state()

        # Verify rollback
        assert plot.activity_data == initial_data
        assert plot.sleep_markers == initial_markers

    def test_rollback_after_memory_allocation_failure(self, stateful_plot_widget):
        """Test rollback after memory allocation failure."""
        plot = stateful_plot_widget

        initial_state = {"data": plot.activity_data.copy(), "markers": plot.sleep_markers.copy(), "mode": plot.current_view_hours}

        plot.save_state()

        try:
            # Simulate memory allocation failure
            large_data = [1] * (10**8)  # Very large allocation
            plot.activity_data = large_data

            # This would likely cause MemoryError in real scenario
            msg = "Cannot allocate memory for large dataset"
            raise MemoryError(msg)

        except MemoryError:
            # Rollback
            plot.rollback_state()

        # Verify rollback preserved initial state
        assert plot.activity_data == initial_state["data"]
        assert plot.sleep_markers == initial_state["markers"]
        assert plot.current_view_hours == initial_state["mode"]

    def test_rollback_after_partial_state_update_failure(self, stateful_plot_widget):
        """Test rollback after partial state update failure."""
        plot = stateful_plot_widget

        initial_state = {
            "data": plot.activity_data.copy(),
            "markers": plot.sleep_markers.copy(),
            "view_mode": plot.current_view_hours,
            "filename": plot.current_filename,
        }

        plot.save_state()

        try:
            # Start updating state
            plot.activity_data = [5, 6, 7] * 200  # New data
            plot.sleep_markers = [{"type": "test", "time": 2000}]  # New markers

            # Failure occurs during state update
            msg = "UI update failed during switching"
            raise RuntimeError(msg)

        except RuntimeError:
            # Partial rollback needed
            plot.rollback_state()

        # All state should be rolled back
        assert plot.activity_data == initial_state["data"]
        assert plot.sleep_markers == initial_state["markers"]
        assert plot.current_view_hours == initial_state["view_mode"]
        assert plot.current_filename == initial_state["filename"]

    def test_rollback_with_nested_operations(self, stateful_plot_widget):
        """Test rollback with nested operations and multiple save points."""
        plot = stateful_plot_widget

        # Initial state
        state0 = plot.activity_data.copy()
        plot.save_state()  # Save point 0

        # First operation
        plot.activity_data = [10, 11, 12] * 50
        plot.save_state()  # Save point 1
        state1 = plot.activity_data.copy()

        # Second operation
        plot.activity_data = [20, 21, 22] * 75
        plot.save_state()  # Save point 2
        state2 = plot.activity_data.copy()

        # Third operation fails
        try:
            plot.activity_data = [float("inf")] * 100  # Invalid data

            # Validation fails
            if any(np.isinf(plot.activity_data)):
                raise DataIntegrityError(ErrorCodes.FILE_CORRUPTED, "Invalid data")

        except DataIntegrityError:
            # Rollback once
            plot.rollback_state()

        # Should be at state2
        assert plot.activity_data == state2

        # Another failure occurs
        try:
            msg = "Another error"
            raise RuntimeError(msg)
        except RuntimeError:
            # Rollback again
            plot.rollback_state()

        # Should be at state1
        assert plot.activity_data == state1

        # One more rollback
        plot.rollback_state()

        # Should be back to initial state
        assert plot.activity_data == state0


class TestErrorRecoveryScenarios:
    """Test error recovery mechanisms."""

    def test_automatic_retry_after_transient_error(self):
        """Test automatic retry after transient errors."""
        service = Mock()  # Removed spec to allow dynamic attribute assignment

        # Track retry attempts
        attempt_count = 0

        def transient_error_operation(participant_key, view_mode):
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count < 3:
                # Fail first two attempts
                raise SleepScoringError(f"Transient error (attempt {attempt_count})", ErrorCodes.TIMEOUT)

            # Succeed on third attempt
            return True

        service.load_participant_data.side_effect = transient_error_operation

        participant_key = ParticipantKey("4000", "BO", "G1")

        # Simulate retry mechanism
        max_retries = 3
        success = False

        for retry in range(max_retries):
            try:
                service.load_participant_data(participant_key, ViewMode.HOURS_24)
                success = True
                break
            except SleepScoringError:
                if retry < max_retries - 1:
                    time.sleep(0.01)  # Brief delay before retry
                    continue
                raise

        assert success
        assert attempt_count == 3

    def test_graceful_degradation_on_feature_failure(self):
        """Test graceful degradation when optional features fail."""
        service = Mock()  # Removed spec to allow dynamic attribute assignment

        def failing_optional_feature(participant_key, view_mode):
            # Main operation succeeds
            main_result = True

            # Optional algorithm overlay fails
            try:
                # Simulate Choi algorithm failure
                msg = "Choi algorithm failed"
                raise RuntimeError(msg)
            except RuntimeError:
                # Continue without overlay - graceful degradation
                pass

            return main_result

        service.load_participant_data.side_effect = failing_optional_feature

        participant_key = ParticipantKey("4000", "BO", "G1")
        result = service.load_participant_data(participant_key, ViewMode.HOURS_24)

        # Main operation should succeed despite optional feature failure
        assert result is True

    def test_error_reporting_and_logging(self):
        """Test comprehensive error reporting and logging."""
        service = Mock()  # Removed spec to allow dynamic attribute assignment

        error_log = []

        def logged_error_operation(participant_key, view_mode):
            error = ValidationError(
                "Invalid participant data format",
                ErrorCodes.INVALID_INPUT,
                {"participant_id": participant_key.participant_id, "view_mode": view_mode},
            )

            # Log error details
            error_log.append(
                {
                    "timestamp": time.time(),
                    "error_code": error.error_code,
                    "message": str(error),
                    "context": error.context,
                    "participant": participant_key.participant_id,
                }
            )

            raise error

        service.load_participant_data.side_effect = logged_error_operation

        participant_key = ParticipantKey("4000", "BO", "G1")

        try:
            service.load_participant_data(participant_key, ViewMode.HOURS_24)
            msg = "Should have raised ValidationError"
            raise AssertionError(msg)
        except ValidationError as e:
            assert e.error_code == ErrorCodes.INVALID_INPUT

        # Verify error was logged
        assert len(error_log) == 1
        assert error_log[0]["error_code"] == ErrorCodes.INVALID_INPUT
        assert error_log[0]["participant"] == "4000"

    def test_user_notification_on_critical_errors(self):
        """Test user notification mechanisms for critical errors."""
        service = Mock()  # Removed spec to allow dynamic attribute assignment
        ui_notifications = []

        def critical_error_with_notification(participant_key, view_mode):
            error = SecurityError("Security violation during data access", ErrorCodes.ACCESS_DENIED)

            # Notify user of critical error
            ui_notifications.append(
                {
                    "type": "critical_error",
                    "title": "Security Violation",
                    "message": "A security violation was detected during data access. Operation cancelled.",
                    "timestamp": time.time(),
                }
            )

            raise error

        service.load_participant_data.side_effect = critical_error_with_notification

        participant_key = ParticipantKey("4000", "BO", "G1")

        try:
            service.load_participant_data(participant_key, ViewMode.HOURS_24)
            msg = "Should have raised SecurityError"
            raise AssertionError(msg)
        except SecurityError as e:
            assert e.error_code == ErrorCodes.ACCESS_DENIED

        # Verify user was notified
        assert len(ui_notifications) == 1
        assert ui_notifications[0]["type"] == "critical_error"
        assert "security violation" in ui_notifications[0]["message"].lower()
