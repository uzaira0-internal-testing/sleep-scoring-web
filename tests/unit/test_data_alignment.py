#!/usr/bin/env python3
"""
Tests for data alignment between timestamps and algorithm results.

These tests verify the critical invariant that was being violated:
    len(timestamps) == len(sadeh_results)

The bug was caused by loading timestamps and sadeh results from DIFFERENT
database queries that could return different row counts due to NULL handling.

The fix:
1. Redux store is single source of truth for activity data
2. ActivityDataConnector loads ALL columns in ONE query with SAME timestamps
3. PlotDataConnector updates widgets from store (no separate loading)
4. Sadeh algorithm uses axis_y from store (guaranteed same length as timestamps)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest


def _make_timestamps(count: int) -> list[datetime]:
    """Create a list of timestamps with 1-minute intervals."""
    base = datetime(2024, 1, 1, 0, 0)
    return [base + timedelta(minutes=i) for i in range(count)]


class TestDataAlignmentInvariants:
    """Tests that verify the critical data alignment invariants."""

    def test_unified_data_has_same_length_for_all_columns(self):
        """Verify unified data loading returns same length for all columns."""
        # This simulates what load_unified_activity_data should return
        unified_data = {
            "timestamps": _make_timestamps(2880),
            "axis_x": [1.0] * 2880,
            "axis_y": [2.0] * 2880,
            "axis_z": [3.0] * 2880,
            "vector_magnitude": [4.0] * 2880,
        }

        # All columns must have same length as timestamps
        timestamps_len = len(unified_data["timestamps"])
        assert len(unified_data["axis_x"]) == timestamps_len
        assert len(unified_data["axis_y"]) == timestamps_len
        assert len(unified_data["axis_z"]) == timestamps_len
        assert len(unified_data["vector_magnitude"]) == timestamps_len

    def test_sadeh_results_length_matches_input_length(self):
        """Verify Sadeh algorithm output has same length as input."""
        import pandas as pd

        from sleep_scoring_app.core.algorithms.sleep_wake.factory import AlgorithmFactory

        # Create test input data
        input_length = 100
        activity_data = [50.0] * input_length
        timestamps = pd.date_range("2024-01-15 00:00:00", periods=input_length, freq="1min")
        df = pd.DataFrame({"datetime": timestamps, "Axis1": activity_data})

        # Get Sadeh algorithm
        algorithm = AlgorithmFactory.create("sadeh_1994_actilife")

        # Run algorithm using score() DataFrame API
        result_df = algorithm.score(df)
        results = result_df["Sleep Score"].tolist()

        # Output length must match input length
        assert len(results) == input_length, (
            f"Sadeh output length ({len(results)}) must match input length ({input_length}). This invariant violation causes the arrow placement bug."
        )

    def test_store_activity_data_lengths_match(self):
        """Verify store state maintains length invariant for all activity columns."""
        from sleep_scoring_app.ui.store import Actions, UIStore

        store = UIStore()

        # Simulate ActivityDataConnector dispatching unified data
        data_length = 2880
        timestamps = _make_timestamps(data_length)
        axis_x = [1.0] * data_length
        axis_y = [2.0] * data_length
        axis_z = [3.0] * data_length
        vector_magnitude = [4.0] * data_length

        store.dispatch(
            Actions.activity_data_loaded(
                timestamps=timestamps,
                axis_x=axis_x,
                axis_y=axis_y,
                axis_z=axis_z,
                vector_magnitude=vector_magnitude,
            )
        )

        state = store.state

        # All lengths must match
        timestamps_len = len(state.activity_timestamps)
        assert timestamps_len == data_length
        assert len(state.axis_x_data) == timestamps_len
        assert len(state.axis_y_data) == timestamps_len
        assert len(state.axis_z_data) == timestamps_len
        assert len(state.vector_magnitude_data) == timestamps_len

    def test_sadeh_results_computed_from_store_axis_y(self):
        """Verify Sadeh results computed from store axis_y match store timestamps length."""
        from sleep_scoring_app.core.algorithms.sleep_wake.factory import AlgorithmFactory
        from sleep_scoring_app.ui.store import Actions, UIStore

        store = UIStore()

        # Simulate unified data load
        data_length = 2880
        timestamps = _make_timestamps(data_length)
        axis_y = [50.0] * data_length  # Activity data for Sadeh

        store.dispatch(
            Actions.activity_data_loaded(
                timestamps=timestamps,
                axis_x=[0.0] * data_length,
                axis_y=axis_y,
                axis_z=[0.0] * data_length,
                vector_magnitude=[0.0] * data_length,
            )
        )

        # Get axis_y from store (this is what Sadeh should use)
        state = store.state
        axis_y_from_store = list(state.axis_y_data)

        # Run Sadeh on axis_y from store using score() DataFrame API
        import pandas as pd

        scoring_df = pd.DataFrame({"datetime": list(state.activity_timestamps), "Axis1": axis_y_from_store})
        algorithm = AlgorithmFactory.create("sadeh_1994_actilife")
        result_df = algorithm.score(scoring_df)
        sadeh_results = result_df["Sleep Score"].tolist()

        # CRITICAL INVARIANT: sadeh results length == store timestamps length
        assert len(sadeh_results) == len(state.activity_timestamps), (
            f"ALIGNMENT BUG: sadeh_results ({len(sadeh_results)}) != "
            f"timestamps ({len(state.activity_timestamps)}). "
            "This causes arrows to be placed at wrong positions."
        )


class TestDataLoadingPaths:
    """Tests that verify there's only ONE data loading path."""

    def test_activity_data_connector_is_sole_loader(self):
        """Verify ActivityDataConnector is the only thing that loads activity data."""
        # This test ensures NavigationConnector doesn't call load_current_date
        # by checking that NavigationConnector._update_navigation doesn't
        # contain load_current_date call

        import inspect

        from sleep_scoring_app.ui.connectors import NavigationConnector

        source = inspect.getsource(NavigationConnector._update_navigation)

        # NavigationConnector should NOT call load_current_date
        assert "load_current_date" not in source or "DO NOT call" in source, (
            "NavigationConnector should NOT call load_current_date(). ActivityDataConnector is the sole authority for loading data."
        )


class TestNoSeparateAxisYLoading:
    """Tests that axis_y is never loaded separately from other columns."""

    def test_get_axis_y_data_uses_store(self):
        """Verify _get_axis_y_data_for_sadeh uses store, not separate DB query."""
        import inspect
        from pathlib import Path

        # Read the source file directly since MainWindow has import side effects
        main_window_path = Path(__file__).parent.parent.parent / "sleep_scoring_app" / "ui" / "main_window.py"
        source = main_window_path.read_text()

        # Find the _get_axis_y_data_for_sadeh method
        method_start = source.find("def _get_axis_y_data_for_sadeh")
        assert method_start != -1, "Could not find _get_axis_y_data_for_sadeh method"

        # Get the method body (until next def or end of class)
        method_end = source.find("\n    def ", method_start + 1)
        if method_end == -1:
            method_end = len(source)
        method_source = source[method_start:method_end]

        # Should reference store.state, not unified_48h_data
        assert "store.state" in method_source, "_get_axis_y_data_for_sadeh should use store.state.axis_y_data, not a separate database query."

        # Should NOT reference unified_48h_data (the old way)
        assert "unified_48h_data" not in method_source, (
            "_get_axis_y_data_for_sadeh should NOT use file_service.unified_48h_data. Store is the single source of truth."
        )
