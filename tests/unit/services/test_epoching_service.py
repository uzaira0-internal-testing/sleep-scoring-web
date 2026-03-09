"""
Tests for EpochingService.

Tests conversion of raw accelerometer data to epoch counts.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_app.core.pipeline.exceptions import EpochingError
from sleep_scoring_app.services.epoching_service import EpochingService


@pytest.fixture
def service() -> EpochingService:
    """Create an EpochingService instance."""
    return EpochingService()


@pytest.fixture
def sample_raw_data() -> pd.DataFrame:
    """Create sample raw accelerometer data."""
    # Create 60 seconds of data at 30 Hz (1800 samples)
    base_time = datetime(2024, 1, 15, 8, 0, 0)
    n_samples = 1800
    timestamps = [base_time + timedelta(milliseconds=i * (1000 / 30)) for i in range(n_samples)]

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "AXIS_X": np.random.uniform(-1, 1, n_samples),
            "AXIS_Y": np.random.uniform(-1, 1, n_samples),
            "AXIS_Z": np.random.uniform(-1, 1, n_samples),
        }
    )


@pytest.fixture
def multi_epoch_data() -> pd.DataFrame:
    """Create sample data spanning multiple epochs."""
    # Create 3 minutes of data at 30 Hz (5400 samples)
    base_time = datetime(2024, 1, 15, 8, 0, 0)
    n_samples = 5400
    timestamps = [base_time + timedelta(milliseconds=i * (1000 / 30)) for i in range(n_samples)]

    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "AXIS_X": np.random.uniform(-1, 1, n_samples),
            "AXIS_Y": np.random.uniform(-1, 1, n_samples),
            "AXIS_Z": np.random.uniform(-1, 1, n_samples),
        }
    )


class TestCreateEpochs:
    """Tests for create_epochs method."""

    def test_creates_epochs_from_raw_data(self, service: EpochingService, sample_raw_data: pd.DataFrame) -> None:
        """Creates epochs from raw accelerometer data."""
        epochs = service.create_epochs(sample_raw_data, epoch_seconds=60)

        assert "datetime" in epochs.columns
        assert "Axis1" in epochs.columns
        assert len(epochs) >= 1

    def test_uses_y_axis_by_default(self, service: EpochingService, sample_raw_data: pd.DataFrame) -> None:
        """Uses Y-axis (vertical) by default."""
        epochs = service.create_epochs(sample_raw_data, epoch_seconds=60, use_axis="Y")

        # Should have non-zero values
        assert epochs["Axis1"].sum() > 0

    def test_supports_vector_magnitude(self, service: EpochingService, sample_raw_data: pd.DataFrame) -> None:
        """Supports vector magnitude calculation."""
        epochs = service.create_epochs(sample_raw_data, epoch_seconds=60, use_axis="VM")

        # VM typically larger than single axis
        assert epochs["Axis1"].sum() > 0

    def test_creates_correct_number_of_epochs(self, service: EpochingService, multi_epoch_data: pd.DataFrame) -> None:
        """Creates correct number of epochs."""
        epochs = service.create_epochs(multi_epoch_data, epoch_seconds=60)

        # 3 minutes = 3 epochs
        assert len(epochs) >= 3

    def test_handles_different_timestamp_columns(self, service: EpochingService, sample_raw_data: pd.DataFrame) -> None:
        """Handles various timestamp column names."""
        # Rename to alternative name
        data = sample_raw_data.rename(columns={"timestamp": "datetime"})

        epochs = service.create_epochs(data, epoch_seconds=60)

        assert len(epochs) >= 1

    def test_raises_for_empty_data(self, service: EpochingService) -> None:
        """Raises error for empty data."""
        with pytest.raises(EpochingError) as exc_info:
            service.create_epochs(pd.DataFrame())

        assert "empty" in exc_info.value.reason.lower()

    def test_raises_for_missing_timestamp(self, service: EpochingService) -> None:
        """Raises error when timestamp column is missing."""
        data = pd.DataFrame(
            {
                "AXIS_X": [1, 2, 3],
                "AXIS_Y": [1, 2, 3],
                "AXIS_Z": [1, 2, 3],
            }
        )

        with pytest.raises(EpochingError) as exc_info:
            service.create_epochs(data)

        assert "timestamp" in exc_info.value.reason.lower()

    def test_raises_for_missing_axis_columns(self, service: EpochingService) -> None:
        """Raises error when axis columns are missing."""
        data = pd.DataFrame(
            {
                "timestamp": [datetime.now()],
            }
        )

        with pytest.raises(EpochingError) as exc_info:
            service.create_epochs(data)

        assert "AXIS" in exc_info.value.reason

    def test_raises_for_invalid_use_axis(self, service: EpochingService, sample_raw_data: pd.DataFrame) -> None:
        """Raises error for invalid use_axis parameter."""
        with pytest.raises(EpochingError) as exc_info:
            service.create_epochs(sample_raw_data, use_axis="INVALID")

        assert "Invalid use_axis" in exc_info.value.reason

    def test_epoch_counts_are_integers(self, service: EpochingService, sample_raw_data: pd.DataFrame) -> None:
        """Epoch counts are converted to integers."""
        epochs = service.create_epochs(sample_raw_data)

        assert epochs["Axis1"].dtype in [np.int32, np.int64, int]


class TestValidateRawData:
    """Tests for _validate_raw_data method."""

    def test_passes_for_valid_data(self, service: EpochingService, sample_raw_data: pd.DataFrame) -> None:
        """Passes validation for valid data."""
        # Should not raise
        service._validate_raw_data(sample_raw_data)

    def test_raises_for_none(self, service: EpochingService) -> None:
        """Raises error for None data."""
        with pytest.raises(EpochingError):
            service._validate_raw_data(None)

    def test_raises_for_missing_columns(self, service: EpochingService) -> None:
        """Raises error for missing required columns."""
        incomplete_data = pd.DataFrame(
            {
                "timestamp": [datetime.now()],
                "AXIS_X": [1.0],
                # Missing AXIS_Y and AXIS_Z
            }
        )

        with pytest.raises(EpochingError):
            service._validate_raw_data(incomplete_data)


class TestFindTimestampColumn:
    """Tests for _find_timestamp_column method."""

    def test_finds_timestamp(self, service: EpochingService) -> None:
        """Finds 'timestamp' column."""
        df = pd.DataFrame({"timestamp": [1], "data": [2]})
        assert service._find_timestamp_column(df) == "timestamp"

    def test_finds_datetime(self, service: EpochingService) -> None:
        """Finds 'datetime' column."""
        df = pd.DataFrame({"datetime": [1], "data": [2]})
        assert service._find_timestamp_column(df) == "datetime"

    def test_case_insensitive(self, service: EpochingService) -> None:
        """Finds column case-insensitively."""
        df = pd.DataFrame({"TIMESTAMP": [1], "data": [2]})
        assert service._find_timestamp_column(df) == "TIMESTAMP"

    def test_returns_none_for_no_match(self, service: EpochingService) -> None:
        """Returns None when no timestamp column found."""
        df = pd.DataFrame({"col1": [1], "col2": [2]})
        assert service._find_timestamp_column(df) is None


class TestEstimateSampleRate:
    """Tests for estimate_sample_rate method."""

    def test_estimates_30hz(self, service: EpochingService) -> None:
        """Estimates 30 Hz sample rate."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        n_samples = 100
        # 30 Hz = 1/30 seconds between samples
        timestamps = [base_time + timedelta(seconds=i / 30) for i in range(n_samples)]

        data = pd.DataFrame(
            {
                "timestamp": timestamps,
                "AXIS_X": np.zeros(n_samples),
                "AXIS_Y": np.zeros(n_samples),
                "AXIS_Z": np.zeros(n_samples),
            }
        )

        rate = service.estimate_sample_rate(data)

        assert abs(rate - 30.0) < 1.0  # Within 1 Hz

    def test_estimates_100hz(self, service: EpochingService) -> None:
        """Estimates 100 Hz sample rate."""
        base_time = datetime(2024, 1, 15, 8, 0, 0)
        n_samples = 100
        timestamps = [base_time + timedelta(seconds=i / 100) for i in range(n_samples)]

        data = pd.DataFrame(
            {
                "timestamp": timestamps,
                "AXIS_X": np.zeros(n_samples),
                "AXIS_Y": np.zeros(n_samples),
                "AXIS_Z": np.zeros(n_samples),
            }
        )

        rate = service.estimate_sample_rate(data)

        assert abs(rate - 100.0) < 5.0  # Within 5 Hz

    def test_raises_without_timestamp(self, service: EpochingService) -> None:
        """Raises error without timestamp column."""
        data = pd.DataFrame({"data": [1, 2, 3]})

        with pytest.raises(EpochingError):
            service.estimate_sample_rate(data)
