#!/usr/bin/env python3
"""
Test Choi axis selection affects algorithm output.

This test verifies that selecting different axes for Choi nonwear detection
produces different results when the data differs between axes.

CRITICAL: The Choi algorithm should use the CONFIGURED axis, not the display axis.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest

from sleep_scoring_app.core.algorithms import choi_detect_nonwear
from sleep_scoring_app.core.algorithms.types import ActivityColumn


class TestChoiAxisSelection:
    """Test that Choi axis selection actually affects the output."""

    @pytest.fixture
    def activity_data_with_differing_axes(self) -> pd.DataFrame:
        """
        Create test data where Vector Magnitude and Axis Y have different values.

        Scenario:
        - 180 minutes of data (3 hours)
        - Vector Magnitude: First 120 minutes are zeros (will trigger nonwear)
        - Axis Y: First 120 minutes have small activity (won't trigger nonwear)

        This ensures we can detect if the axis selection is working.
        """
        n_minutes = 180  # 3 hours
        start_time = datetime(2024, 1, 1, 0, 0, 0)

        # Create timestamps
        timestamps = [start_time + timedelta(minutes=i) for i in range(n_minutes)]

        # Vector Magnitude: zeros for first 120 minutes (triggers 90+ min nonwear)
        vector_magnitude = [0.0] * 120 + [100.0] * 60

        # Axis Y: small but non-zero values for first 120 minutes (no nonwear)
        axis_y = [5.0] * 120 + [100.0] * 60

        return pd.DataFrame(
            {
                "datetime": timestamps,
                "Vector Magnitude": vector_magnitude,
                "axis_y": axis_y,
            }
        )

    def test_vector_magnitude_detects_nonwear(self, activity_data_with_differing_axes: pd.DataFrame) -> None:
        """When using Vector Magnitude (zeros), Choi should detect nonwear."""
        result = choi_detect_nonwear(
            activity_data_with_differing_axes,
            activity_column=ActivityColumn.VECTOR_MAGNITUDE,
        )

        # Count nonwear epochs
        nonwear_count = result["Nonwear Score"].sum()

        # Should detect at least 90 minutes of nonwear (the minimum period)
        assert nonwear_count >= 90, f"Expected >= 90 nonwear minutes with VM zeros, got {nonwear_count}"

    def test_axis_y_no_nonwear(self, activity_data_with_differing_axes: pd.DataFrame) -> None:
        """When using Axis Y (non-zero), Choi should NOT detect nonwear."""
        result = choi_detect_nonwear(
            activity_data_with_differing_axes,
            activity_column=ActivityColumn.AXIS_Y,
        )

        # Count nonwear epochs
        nonwear_count = result["Nonwear Score"].sum()

        # Should detect NO nonwear since axis_y has values
        assert nonwear_count == 0, f"Expected 0 nonwear minutes with axis_y activity, got {nonwear_count}"

    def test_axis_selection_produces_different_results(self, activity_data_with_differing_axes: pd.DataFrame) -> None:
        """Verify different axis selections produce different nonwear results."""
        # Run with Vector Magnitude
        result_vm = choi_detect_nonwear(
            activity_data_with_differing_axes.copy(),
            activity_column=ActivityColumn.VECTOR_MAGNITUDE,
        )

        # Run with Axis Y
        result_y = choi_detect_nonwear(
            activity_data_with_differing_axes.copy(),
            activity_column=ActivityColumn.AXIS_Y,
        )

        vm_nonwear = result_vm["Nonwear Score"].sum()
        y_nonwear = result_y["Nonwear Score"].sum()

        # Results MUST be different - this proves axis selection works
        assert vm_nonwear != y_nonwear, f"Axis selection should affect results! VM nonwear: {vm_nonwear}, Y nonwear: {y_nonwear}"

        # Specifically: VM should have more nonwear (since it's all zeros)
        assert vm_nonwear > y_nonwear, (
            f"Vector Magnitude (zeros) should have MORE nonwear than Axis Y (with values). VM: {vm_nonwear}, Y: {y_nonwear}"
        )


class TestChoiAlgorithmClassAPI:
    """Test the class-based ChoiAlgorithm API uses activity_column correctly.

    NOTE: This test documents that the class-based API does NOT currently use
    the activity_column parameter - it expects the caller to pass the correct data.
    """

    @pytest.fixture
    def timestamps_and_data(self) -> tuple[list[datetime], list[float], list[float]]:
        """Create timestamps with zeros (nonwear) and non-zeros (wear)."""
        n_minutes = 180
        start_time = datetime(2024, 1, 1, 0, 0, 0)
        timestamps = [start_time + timedelta(minutes=i) for i in range(n_minutes)]

        # Data with zeros (would trigger nonwear)
        zeros_data = [0.0] * 120 + [100.0] * 60

        # Data with activity (no nonwear)
        activity_data = [5.0] * 120 + [100.0] * 60

        return timestamps, zeros_data, activity_data

    def test_class_api_uses_passed_data_not_column(self, timestamps_and_data) -> None:
        """
        Document that ChoiAlgorithm.detect() uses the passed data, not the column.

        The activity_column parameter is for reference/metadata only.
        The caller MUST pass the correct data for the desired axis.
        """
        from sleep_scoring_app.core.algorithms import ChoiAlgorithm

        timestamps, zeros_data, activity_data = timestamps_and_data
        algo = ChoiAlgorithm()

        # Calling detect with zeros_data but saying "axis_y" - still uses zeros!
        periods_with_zeros = algo.detect(
            activity_data=zeros_data,
            timestamps=timestamps,
            activity_column="axis_y",  # This is IGNORED
        )

        # Calling detect with activity_data but saying "vector_magnitude"
        periods_with_activity = algo.detect(
            activity_data=activity_data,
            timestamps=timestamps,
            activity_column="vector_magnitude",  # This is also IGNORED
        )

        # The results depend on DATA passed, not column name
        assert len(periods_with_zeros) > 0, "Zeros data should produce nonwear periods"
        assert len(periods_with_activity) == 0, "Activity data should produce no nonwear"
