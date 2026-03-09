"""Tests for loading activity data from demo files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tests.demo_data.conftest import DEVICE_FORMATS


@pytest.mark.demo_data
class TestActivityFilesExist:
    """Test that all activity files exist."""

    def test_activity_directory_exists(self, activity_dir: Path) -> None:
        """Activity directory should exist."""
        assert activity_dir.exists()
        assert activity_dir.is_dir()

    @pytest.mark.parametrize("device", ["actigraph", "actiwatch", "axivity", "geneactiv", "generic", "motionwatch"])
    def test_device_file_exists(self, activity_dir: Path, device: str) -> None:
        """Each device format file should exist."""
        pattern = f"*_{device}.csv"
        files = list(activity_dir.glob(pattern))
        assert len(files) >= 1, f"No {device} file found matching {pattern}"


@pytest.mark.demo_data
class TestActivityDataLoading:
    """Test loading activity data from each format."""

    @pytest.mark.parametrize("device,skip_rows,expected_cols", DEVICE_FORMATS)
    def test_load_activity_file(self, activity_dir: Path, device: str, skip_rows: int, expected_cols: list[str]) -> None:
        """Load activity file and verify structure."""
        files = list(activity_dir.glob(f"*_{device}.csv"))
        assert files, f"No {device} file found"

        file_path = files[0]
        df = pd.read_csv(file_path, skiprows=skip_rows)

        # Verify not empty
        assert len(df) > 0, f"{device} file is empty"

        # Verify expected columns present
        for col in expected_cols:
            assert col in df.columns, f"Missing column {col} in {device} file. Columns: {list(df.columns)}"

    @pytest.mark.parametrize("device,skip_rows", [(p.values[0], p.values[1]) for p in DEVICE_FORMATS])
    def test_activity_data_has_rows(self, activity_dir: Path, device: str, skip_rows: int) -> None:
        """Activity files should have substantial data (7+ days = 10080+ rows)."""
        files = list(activity_dir.glob(f"*_{device}.csv"))
        assert files, f"No {device} file found"
        file_path = files[0]
        df = pd.read_csv(file_path, skiprows=skip_rows)

        # 7 days * 24 hours * 60 minutes = 10080 epochs minimum
        assert len(df) >= 10000, f"{device} file has only {len(df)} rows, expected 10000+"

    @pytest.mark.parametrize("device,skip_rows", [(p.values[0], p.values[1]) for p in DEVICE_FORMATS])
    def test_activity_counts_reasonable(self, activity_dir: Path, device: str, skip_rows: int) -> None:
        """Activity counts should be within reasonable range."""
        files = list(activity_dir.glob(f"*_{device}.csv"))
        assert files, f"No {device} file found"
        file_path = files[0]
        df = pd.read_csv(file_path, skiprows=skip_rows)

        # Find activity column (varies by format)
        activity_cols = ["Axis1", "Activity", "activity_count", "y"]
        activity_col = None
        for col in activity_cols:
            if col in df.columns:
                activity_col = col
                break

        if activity_col:
            values = df[activity_col].dropna()
            assert values.min() >= 0, f"Negative activity values in {device}"
            assert values.max() <= 50000, f"Unreasonably high activity in {device}: {values.max()}"


@pytest.mark.demo_data
class TestActivityTimestamps:
    """Test timestamp parsing and continuity."""

    def test_actigraph_timestamps(self, activity_dir: Path) -> None:
        """Actigraph Date/Time columns should parse correctly."""
        files = list(activity_dir.glob("*_actigraph.csv"))
        df = pd.read_csv(files[0], skiprows=10)

        # Combine Date and Time columns
        df["datetime"] = pd.to_datetime(df["Date"] + " " + df["Time"])
        assert df["datetime"].notna().all(), "Failed to parse actigraph timestamps"

    def test_generic_timestamps(self, activity_dir: Path) -> None:
        """Generic datetime column should parse correctly."""
        files = list(activity_dir.glob("*_generic.csv"))
        df = pd.read_csv(files[0])

        df["datetime"] = pd.to_datetime(df["datetime"])
        assert df["datetime"].notna().all(), "Failed to parse generic timestamps"

    def test_axivity_timestamps(self, activity_dir: Path) -> None:
        """Axivity timestamp column should parse correctly."""
        files = list(activity_dir.glob("*_axivity.csv"))
        df = pd.read_csv(files[0], skiprows=6)

        df["datetime"] = pd.to_datetime(df["timestamp"])
        assert df["datetime"].notna().all(), "Failed to parse axivity timestamps"

    def test_timestamps_contiguous(self, activity_dir: Path) -> None:
        """Timestamps should be 60 seconds apart (no gaps)."""
        files = list(activity_dir.glob("*_generic.csv"))
        df = pd.read_csv(files[0])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df = df.sort_values("datetime")

        # Check time differences
        time_diffs = df["datetime"].diff().dropna()
        expected_diff = pd.Timedelta(seconds=60)

        # All diffs should be 60 seconds
        assert (time_diffs == expected_diff).all(), "Timestamps are not contiguous 60-second epochs"

    def test_no_duplicate_timestamps(self, activity_dir: Path) -> None:
        """No duplicate timestamps should exist."""
        files = list(activity_dir.glob("*_generic.csv"))
        df = pd.read_csv(files[0])
        df["datetime"] = pd.to_datetime(df["datetime"])

        duplicates = df["datetime"].duplicated().sum()
        assert duplicates == 0, f"Found {duplicates} duplicate timestamps"
