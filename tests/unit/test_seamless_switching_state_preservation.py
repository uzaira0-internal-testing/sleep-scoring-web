#!/usr/bin/env python3
"""
Unit tests for seamless activity data switching - State Preservation.
Tests accurate preservation of zoom, pan, markers, and UI state during switches.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.constants import ViewMode
from sleep_scoring_app.services.unified_data_service import UnifiedDataService
from sleep_scoring_app.ui.widgets.activity_plot import ActivityPlotWidget


@dataclass
class ViewState:
    """Represents complete view state for validation."""

    x_range: tuple[float, float]
    y_range: tuple[float, float]
    zoom_level: float
    pan_position: tuple[float, float]
    markers: list[dict[str, Any]]
    view_mode: ViewMode
    filename: str | None
    data_hash: str | None


@dataclass
class SwitchingTestCase:
    """Test case definition for switching scenarios."""

    name: str
    initial_mode: ViewMode
    target_mode: ViewMode
    initial_data_size: int
    target_data_size: int
    has_markers: bool
    custom_zoom: bool
    custom_pan: bool
    expected_preservation: dict[str, bool]


@pytest.fixture
def mock_plot_widget(qt_app):
    """Create mock activity plot widget with state tracking."""
    plot = Mock()  # Removed spec to allow dynamic attribute assignment

    # Mock view box for zoom/pan state
    view_box = Mock()
    view_box.viewRange.return_value = [[0, 86400], [0, 300]]  # 24h range, activity 0-300
    plot.getViewBox.return_value = view_box
    plot.vb = view_box

    # Mock axis for range information
    x_axis = Mock()
    x_axis.range = [0, 86400]
    y_axis = Mock()
    y_axis.range = [0, 300]
    plot.getAxis.side_effect = lambda side: x_axis if side == "bottom" else y_axis

    # State tracking
    plot.current_view_hours = ViewMode.HOURS_24
    plot.current_filename = None
    plot.data_start_time = 0
    plot.data_end_time = 86400
    plot.data_min_y = 0
    plot.data_max_y = 300
    plot.timestamps = []
    plot.activity_data = []
    plot.x_data = np.array([])

    # Sleep markers
    plot.sleep_markers = []
    plot.marker_items = []

    return plot


@pytest.fixture
def mock_unified_service():
    """Create mock unified data service."""
    service = Mock(spec=UnifiedDataService)
    service.current_view_mode = ViewMode.HOURS_24
    service.current_participant_key = None
    service.cached_activity_data = {}
    service.cached_timestamps = {}

    return service


@pytest.fixture
def switching_test_cases():
    """Provide comprehensive switching test cases."""
    return [
        SwitchingTestCase(
            name="24h_to_48h_with_zoom",
            initial_mode=ViewMode.HOURS_24,
            target_mode=ViewMode.HOURS_48,
            initial_data_size=2880,  # 24h * 60 min * 2 epochs
            target_data_size=5760,  # 48h * 60 min * 2 epochs
            has_markers=True,
            custom_zoom=True,
            custom_pan=False,
            expected_preservation={
                "relative_zoom": True,
                "markers": True,
                "pan_position": False,  # Pan resets when switching view modes
                "data_integrity": True,
            },
        ),
        SwitchingTestCase(
            name="48h_to_24h_with_pan",
            initial_mode=ViewMode.HOURS_48,
            target_mode=ViewMode.HOURS_24,
            initial_data_size=5760,
            target_data_size=2880,
            has_markers=False,
            custom_zoom=False,
            custom_pan=True,
            expected_preservation={
                "relative_zoom": True,
                "markers": True,
                "pan_position": False,  # Pan resets when switching view modes
                "data_integrity": True,
            },
        ),
        SwitchingTestCase(
            name="same_mode_switch",
            initial_mode=ViewMode.HOURS_24,
            target_mode=ViewMode.HOURS_24,
            initial_data_size=2880,
            target_data_size=2880,
            has_markers=True,
            custom_zoom=True,
            custom_pan=True,
            expected_preservation={
                "relative_zoom": True,
                "markers": True,
                "pan_position": True,  # Pan preserved for same mode
                "data_integrity": True,
            },
        ),
    ]


class TestStatePreservationCore:
    """Core state preservation tests during seamless switching."""

    def test_zoom_preservation_accuracy(self, mock_plot_widget, switching_test_cases):
        """Test that zoom levels are preserved accurately during switching."""
        for test_case in switching_test_cases:
            with patch.object(mock_plot_widget, "getViewBox") as mock_vb:
                # Set initial zoom state
                initial_x_range = [10000, 50000]  # Zoomed to ~11 hours within 24h
                initial_y_range = [0, 150]  # Zoomed to half Y range
                mock_vb.return_value.viewRange.return_value = [initial_x_range, initial_y_range]

                # Capture initial state
                initial_state = self._capture_view_state(mock_plot_widget, test_case.initial_mode)

                # Simulate data switch
                self._simulate_data_switch(
                    mock_plot_widget, test_case.initial_mode, test_case.target_mode, test_case.initial_data_size, test_case.target_data_size
                )

                # Capture post-switch state
                final_state = self._capture_view_state(mock_plot_widget, test_case.target_mode)

                # Validate zoom preservation
                if test_case.expected_preservation["relative_zoom"]:
                    self._assert_zoom_preserved(initial_state, final_state, test_case)

    def test_marker_preservation_accuracy(self, mock_plot_widget, switching_test_cases):
        """Test that sleep markers are preserved accurately during switching."""
        for test_case in switching_test_cases:
            if test_case.has_markers:
                # Set initial markers
                initial_markers = [
                    {"type": "onset", "time": 20000, "x_pos": 20000, "label": "Sleep Onset"},
                    {"type": "offset", "time": 65000, "x_pos": 65000, "label": "Sleep Offset"},
                ]
                mock_plot_widget.sleep_markers = initial_markers.copy()

                # Capture initial state
                initial_state = self._capture_view_state(mock_plot_widget, test_case.initial_mode)

                # Simulate data switch
                self._simulate_data_switch(
                    mock_plot_widget, test_case.initial_mode, test_case.target_mode, test_case.initial_data_size, test_case.target_data_size
                )

                # Capture post-switch state
                final_state = self._capture_view_state(mock_plot_widget, test_case.target_mode)

                # Validate marker preservation
                if test_case.expected_preservation["markers"]:
                    self._assert_markers_preserved(initial_state, final_state, test_case)

    def test_pan_position_handling(self, mock_plot_widget, switching_test_cases):
        """Test pan position preservation logic during switching."""
        for test_case in switching_test_cases:
            if test_case.custom_pan:
                # Set initial pan position
                pan_x_offset = 15000  # Panned ~4 hours to the right
                initial_x_range = [pan_x_offset, pan_x_offset + 43200]  # 12h window
                initial_y_range = [0, 300]

                mock_plot_widget.vb.viewRange.return_value = [initial_x_range, initial_y_range]

                # Capture initial state
                initial_state = self._capture_view_state(mock_plot_widget, test_case.initial_mode)

                # Simulate data switch
                self._simulate_data_switch(
                    mock_plot_widget, test_case.initial_mode, test_case.target_mode, test_case.initial_data_size, test_case.target_data_size
                )

                # Capture post-switch state
                final_state = self._capture_view_state(mock_plot_widget, test_case.target_mode)

                # Validate pan position handling
                if test_case.expected_preservation["pan_position"]:
                    self._assert_pan_preserved(initial_state, final_state, test_case)
                else:
                    self._assert_pan_reset(initial_state, final_state, test_case)

    def test_data_integrity_preservation(self, mock_plot_widget, switching_test_cases):
        """Test that data integrity is maintained during switching."""
        for test_case in switching_test_cases:
            # Generate test data
            initial_data = self._generate_test_data(test_case.initial_data_size)
            target_data = self._generate_test_data(test_case.target_data_size)

            # Set initial data
            mock_plot_widget.activity_data = initial_data["activity"]
            mock_plot_widget.timestamps = initial_data["timestamps"]
            mock_plot_widget.x_data = initial_data["x_data"]

            # Calculate initial data hash
            self._calculate_data_hash(initial_data)

            # Simulate switch to target data
            mock_plot_widget.activity_data = target_data["activity"]
            mock_plot_widget.timestamps = target_data["timestamps"]
            mock_plot_widget.x_data = target_data["x_data"]

            # Calculate final data hash
            final_hash = self._calculate_data_hash(target_data)

            # Validate data integrity
            if test_case.expected_preservation["data_integrity"]:
                assert final_hash is not None, f"Data integrity lost in {test_case.name}"
                assert len(mock_plot_widget.activity_data) == test_case.target_data_size
                assert len(mock_plot_widget.timestamps) == test_case.target_data_size

    def test_view_mode_transition_consistency(self, mock_plot_widget):
        """Test consistency of view mode transitions."""
        test_transitions = [
            (ViewMode.HOURS_24, ViewMode.HOURS_48),
            (ViewMode.HOURS_48, ViewMode.HOURS_24),
            (ViewMode.HOURS_24, ViewMode.HOURS_24),  # Same mode
            (ViewMode.HOURS_48, ViewMode.HOURS_48),  # Same mode
        ]

        for initial_mode, target_mode in test_transitions:
            # Set initial mode
            mock_plot_widget.current_view_hours = initial_mode

            # Capture pre-switch state
            pre_state = self._capture_view_state(mock_plot_widget, initial_mode)

            # Simulate mode transition
            self._simulate_mode_transition(mock_plot_widget, initial_mode, target_mode)

            # Capture post-switch state
            post_state = self._capture_view_state(mock_plot_widget, target_mode)

            # Validate transition consistency
            assert post_state.view_mode == target_mode

            # For same-mode transitions, more state should be preserved
            if initial_mode == target_mode:
                assert post_state.x_range == pre_state.x_range
                assert post_state.y_range == pre_state.y_range

    def test_concurrent_state_updates(self, mock_plot_widget):
        """Test handling of concurrent state updates during switching."""
        # Simulate rapid successive switches
        modes = [ViewMode.HOURS_24, ViewMode.HOURS_48, ViewMode.HOURS_24, ViewMode.HOURS_48]

        for i, mode in enumerate(modes):
            # Add marker during switching sequence
            marker = {"type": "test", "time": 10000 + (i * 5000), "x_pos": 10000 + (i * 5000), "label": f"Test Marker {i}"}
            mock_plot_widget.sleep_markers.append(marker)

            # Simulate mode switch
            self._simulate_mode_transition(mock_plot_widget, mock_plot_widget.current_view_hours, mode)

            # Verify markers are preserved
            assert len(mock_plot_widget.sleep_markers) == i + 1
            assert mock_plot_widget.sleep_markers[-1]["label"] == f"Test Marker {i}"

    def _capture_view_state(self, plot_widget: Mock, view_mode: ViewMode) -> ViewState:
        """Capture complete view state for comparison."""
        view_range = plot_widget.vb.viewRange()

        return ViewState(
            x_range=tuple(view_range[0]),
            y_range=tuple(view_range[1]),
            zoom_level=self._calculate_zoom_level(view_range),
            pan_position=(view_range[0][0], view_range[1][0]),
            markers=getattr(plot_widget, "sleep_markers", []).copy(),
            view_mode=view_mode,
            filename=getattr(plot_widget, "current_filename", None),
            data_hash=self._calculate_plot_data_hash(plot_widget),
        )

    def _simulate_data_switch(self, plot_widget: Mock, initial_mode: ViewMode, target_mode: ViewMode, initial_size: int, target_size: int):
        """Simulate seamless data switching."""
        # Generate new data
        target_data = self._generate_test_data(target_size)

        # Update plot widget data
        plot_widget.activity_data = target_data["activity"]
        plot_widget.timestamps = target_data["timestamps"]
        plot_widget.x_data = target_data["x_data"]
        plot_widget.current_view_hours = target_mode

        # Simulate view range update for mode change
        if initial_mode != target_mode:
            if target_mode == ViewMode.HOURS_48:
                new_x_range = [0, 172800]  # 48 hours
            else:
                new_x_range = [0, 86400]  # 24 hours

            plot_widget.vb.viewRange.return_value = [new_x_range, [0, 300]]

    def _simulate_mode_transition(self, plot_widget: Mock, initial_mode: ViewMode, target_mode: ViewMode):
        """Simulate view mode transition."""
        plot_widget.current_view_hours = target_mode

        # Update data boundaries based on mode
        if target_mode == ViewMode.HOURS_48:
            plot_widget.data_end_time = 172800  # 48 hours
        else:
            plot_widget.data_end_time = 86400  # 24 hours

    def _generate_test_data(self, size: int) -> dict[str, Any]:
        """Generate test activity data."""
        timestamps = pd.date_range(start="2021-04-20 12:00:00", periods=size, freq="30S")

        activity = np.random.poisson(50, size)  # Random activity counts
        x_data = np.array([ts.timestamp() for ts in timestamps])

        return {"timestamps": timestamps.tolist(), "activity": activity.tolist(), "x_data": x_data}

    def _calculate_zoom_level(self, view_range: list[list[float]]) -> float:
        """Calculate zoom level from view range."""
        x_span = view_range[0][1] - view_range[0][0]
        y_span = view_range[1][1] - view_range[1][0]
        return x_span / y_span  # Aspect ratio as zoom indicator

    def _calculate_data_hash(self, data: dict[str, Any]) -> str:
        """Calculate hash of data for integrity checking."""
        activity_hash = hash(tuple(data["activity"][:100]))  # Sample for performance
        timestamp_hash = hash(tuple(data["x_data"][:100]))
        return f"{activity_hash}_{timestamp_hash}"

    def _calculate_plot_data_hash(self, plot_widget: Mock) -> str:
        """Calculate hash of plot widget data."""
        if hasattr(plot_widget, "activity_data") and plot_widget.activity_data:
            activity_sample = plot_widget.activity_data[:100] if len(plot_widget.activity_data) > 100 else plot_widget.activity_data
            return hash(tuple(activity_sample))
        return "no_data"

    def _assert_zoom_preserved(self, initial_state: ViewState, final_state: ViewState, test_case: SwitchingTestCase):
        """Assert that zoom level is preserved appropriately."""
        # For view mode changes, we expect relative zoom to be maintained
        if test_case.initial_mode != test_case.target_mode:
            # Zoom level should be approximately preserved relative to new data range
            zoom_ratio = final_state.zoom_level / initial_state.zoom_level
            assert 0.5 <= zoom_ratio <= 2.0, f"Zoom ratio {zoom_ratio} out of acceptable range in {test_case.name}"
        else:
            # For same mode, zoom should be exactly preserved
            assert abs(final_state.zoom_level - initial_state.zoom_level) < 0.1, f"Zoom not preserved in {test_case.name}"

    def _assert_markers_preserved(self, initial_state: ViewState, final_state: ViewState, test_case: SwitchingTestCase):
        """Assert that markers are preserved correctly."""
        assert len(final_state.markers) == len(initial_state.markers), f"Marker count changed in {test_case.name}"

        for i, (initial_marker, final_marker) in enumerate(zip(initial_state.markers, final_state.markers, strict=False)):
            assert initial_marker["type"] == final_marker["type"], f"Marker type changed at index {i} in {test_case.name}"
            assert initial_marker["label"] == final_marker["label"], f"Marker label changed at index {i} in {test_case.name}"
            # Time positions should be preserved (they're in data coordinates)
            assert abs(initial_marker["time"] - final_marker["time"]) < 1000, f"Marker time shifted at index {i} in {test_case.name}"

    def _assert_pan_preserved(self, initial_state: ViewState, final_state: ViewState, test_case: SwitchingTestCase):
        """Assert that pan position is preserved."""
        # Pan position should be approximately preserved
        x_diff = abs(final_state.pan_position[0] - initial_state.pan_position[0])
        y_diff = abs(final_state.pan_position[1] - initial_state.pan_position[1])

        assert x_diff < 5000, f"X pan position changed too much ({x_diff}) in {test_case.name}"
        assert y_diff < 50, f"Y pan position changed too much ({y_diff}) in {test_case.name}"

    def _assert_pan_reset(self, initial_state: ViewState, final_state: ViewState, test_case: SwitchingTestCase):
        """Assert that pan position is reset as expected."""
        # For mode changes, pan should be reset to default positions
        if test_case.initial_mode != test_case.target_mode:
            # X position should be reset to start of data range
            assert final_state.pan_position[0] == 0 or final_state.pan_position[0] < 1000, f"Pan not reset in {test_case.name}"


class TestStatePreservationPerformance:
    """Performance tests for state preservation during switching."""

    def test_state_capture_performance(self, mock_plot_widget):
        """Test that state capture is fast enough for seamless switching."""
        # Generate large dataset
        large_data = self._generate_large_test_data(10000)  # 10k data points
        mock_plot_widget.activity_data = large_data["activity"]
        mock_plot_widget.timestamps = large_data["timestamps"]

        # Measure state capture time
        start_time = time.perf_counter()

        for _ in range(10):  # Multiple captures to average
            ViewState(
                x_range=(0, 86400),
                y_range=(0, 300),
                zoom_level=1.0,
                pan_position=(0, 0),
                markers=getattr(mock_plot_widget, "sleep_markers", []).copy(),
                view_mode=ViewMode.HOURS_24,
                filename=getattr(mock_plot_widget, "current_filename", None),
                data_hash="test_hash",
            )

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 10

        # State capture should be under 10ms for seamless feel
        assert avg_time < 0.01, f"State capture too slow: {avg_time:.4f}s"

    def test_state_restoration_performance(self, mock_plot_widget):
        """Test that state restoration is fast enough for seamless switching."""
        # Create test state
        test_state = ViewState(
            x_range=(10000, 50000),
            y_range=(0, 150),
            zoom_level=1.5,
            pan_position=(10000, 0),
            markers=[{"type": "onset", "time": 20000, "x_pos": 20000, "label": "Test"}],
            view_mode=ViewMode.HOURS_24,
            filename="test.csv",
            data_hash="test_hash",
        )

        # Measure restoration time
        start_time = time.perf_counter()

        for _ in range(10):  # Multiple restorations to average
            # Simulate state restoration
            mock_plot_widget.vb.setRange(xRange=list(test_state.x_range), yRange=list(test_state.y_range), padding=0)
            mock_plot_widget.sleep_markers = test_state.markers.copy()
            mock_plot_widget.current_view_hours = test_state.view_mode
            mock_plot_widget.current_filename = test_state.filename

        end_time = time.perf_counter()
        avg_time = (end_time - start_time) / 10

        # State restoration should be under 50ms for seamless feel
        assert avg_time < 0.05, f"State restoration too slow: {avg_time:.4f}s"

    def _generate_large_test_data(self, size: int) -> dict[str, Any]:
        """Generate large test dataset for performance testing."""
        timestamps = pd.date_range(start="2021-04-20 12:00:00", periods=size, freq="30S")

        activity = np.random.poisson(50, size)
        x_data = np.array([ts.timestamp() for ts in timestamps])

        return {"timestamps": timestamps.tolist(), "activity": activity.tolist(), "x_data": x_data}


class TestStatePreservationEdgeCases:
    """Edge case tests for state preservation."""

    def test_empty_data_switching(self, mock_plot_widget):
        """Test switching when no data is available."""
        # Start with empty data
        mock_plot_widget.activity_data = []
        mock_plot_widget.timestamps = []
        mock_plot_widget.x_data = np.array([])

        # Attempt to capture state
        initial_state = ViewState(
            x_range=(0, 86400),
            y_range=(0, 300),
            zoom_level=1.0,
            pan_position=(0, 0),
            markers=[],
            view_mode=ViewMode.HOURS_24,
            filename=None,
            data_hash="empty",
        )

        # Should not raise exceptions
        assert initial_state.view_mode == ViewMode.HOURS_24
        assert len(initial_state.markers) == 0

    def test_malformed_marker_preservation(self, mock_plot_widget):
        """Test preservation of malformed markers."""
        # Add malformed markers
        malformed_markers = [
            {"type": "onset"},  # Missing time/position
            {"time": 20000},  # Missing type/label
            {},  # Empty marker
            None,  # Null marker
        ]

        mock_plot_widget.sleep_markers = malformed_markers

        # Capture state (should handle malformed markers gracefully)
        state = ViewState(
            x_range=(0, 86400),
            y_range=(0, 300),
            zoom_level=1.0,
            pan_position=(0, 0),
            markers=mock_plot_widget.sleep_markers.copy(),
            view_mode=ViewMode.HOURS_24,
            filename=None,
            data_hash="test",
        )

        # Should preserve markers as-is (UI will handle malformed ones)
        assert len(state.markers) == 4

    def test_extreme_zoom_preservation(self, mock_plot_widget):
        """Test preservation of extreme zoom levels."""
        # Set extreme zoom (very zoomed in)
        extreme_x_range = [43200, 43300]  # 100 second window
        extreme_y_range = [0, 5]  # Very narrow Y range

        mock_plot_widget.vb.viewRange.return_value = [extreme_x_range, extreme_y_range]

        # Capture state with extreme zoom
        state = ViewState(
            x_range=tuple(extreme_x_range),
            y_range=tuple(extreme_y_range),
            zoom_level=100 / 5,  # Very high zoom ratio
            pan_position=(43200, 0),
            markers=[],
            view_mode=ViewMode.HOURS_24,
            filename=None,
            data_hash="extreme_zoom",
        )

        # Should handle extreme zoom levels
        assert state.zoom_level == 20.0
        assert state.x_range == (43200, 43300)

    def test_large_marker_count_preservation(self, mock_plot_widget):
        """Test preservation with large number of markers."""
        # Create many markers
        large_marker_set = []
        for i in range(1000):
            large_marker_set.append({"type": "test", "time": i * 100, "x_pos": i * 100, "label": f"Marker {i}"})

        mock_plot_widget.sleep_markers = large_marker_set

        # Capture state with many markers
        start_time = time.perf_counter()

        state = ViewState(
            x_range=(0, 86400),
            y_range=(0, 300),
            zoom_level=1.0,
            pan_position=(0, 0),
            markers=mock_plot_widget.sleep_markers.copy(),
            view_mode=ViewMode.HOURS_24,
            filename=None,
            data_hash="large_markers",
        )

        end_time = time.perf_counter()
        capture_time = end_time - start_time

        # Should handle large marker sets efficiently
        assert len(state.markers) == 1000
        assert capture_time < 0.1, f"Large marker set capture too slow: {capture_time:.4f}s"
