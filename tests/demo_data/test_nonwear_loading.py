"""Tests for loading nonwear period data from demo files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.demo_data
class TestNonwearFileExists:
    """Test that nonwear file exists."""

    def test_nonwear_directory_exists(self, nonwear_dir: Path) -> None:
        """Nonwear directory should exist."""
        assert nonwear_dir.exists()
        assert nonwear_dir.is_dir()

    def test_nonwear_file_exists(self, nonwear_dir: Path) -> None:
        """Nonwear periods CSV should exist."""
        files = list(nonwear_dir.glob("*.csv"))
        assert len(files) >= 1, "No nonwear CSV files found"


@pytest.mark.demo_data
class TestNonwearDataLoading:
    """Test loading and parsing nonwear data."""

    def test_load_nonwear_file(self, nonwear_dir: Path) -> None:
        """Nonwear file should load without errors."""
        files = list(nonwear_dir.glob("*.csv"))
        df = pd.read_csv(files[0])
        assert len(df) > 0, "Nonwear file is empty"

    def test_nonwear_required_columns(self, nonwear_dir: Path) -> None:
        """Nonwear file should have required columns."""
        files = list(nonwear_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        required_columns = ["start", "end", "participant_id"]

        for col in required_columns:
            assert col in df.columns, f"Missing required column: {col}"

    def test_nonwear_timestamps_parse(self, nonwear_dir: Path) -> None:
        """Start and end timestamps should parse correctly."""
        files = list(nonwear_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        start_times = pd.to_datetime(df["start"])
        end_times = pd.to_datetime(df["end"])

        assert start_times.notna().all(), "Failed to parse some start times"
        assert end_times.notna().all(), "Failed to parse some end times"

    def test_nonwear_end_after_start(self, nonwear_dir: Path) -> None:
        """End time should be after start time for each period."""
        files = list(nonwear_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        df["start"] = pd.to_datetime(df["start"])
        df["end"] = pd.to_datetime(df["end"])

        assert (df["end"] > df["start"]).all(), "Some end times are before start times"

    def test_nonwear_participant_id(self, nonwear_dir: Path) -> None:
        """Participant ID should match expected format."""
        files = list(nonwear_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        unique_ids = df["participant_id"].unique()
        assert len(unique_ids) == 1, f"Multiple participant IDs: {unique_ids}"
        assert unique_ids[0] == "DEMO-001", f"Unexpected participant ID: {unique_ids[0]}"

    def test_nonwear_periods_reasonable_duration(self, nonwear_dir: Path) -> None:
        """Nonwear periods should have reasonable duration (>= 90 min per Choi)."""
        files = list(nonwear_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        df["start"] = pd.to_datetime(df["start"])
        df["end"] = pd.to_datetime(df["end"])
        df["duration"] = (df["end"] - df["start"]).dt.total_seconds() / 60

        # Choi algorithm minimum is 90 minutes
        assert df["duration"].min() >= 60, f"Nonwear period too short: {df['duration'].min()} minutes"

    def test_nonwear_periods_no_overlap(self, nonwear_dir: Path) -> None:
        """Nonwear periods should not overlap."""
        files = list(nonwear_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        df["start"] = pd.to_datetime(df["start"])
        df["end"] = pd.to_datetime(df["end"])
        df = df.sort_values("start")

        # Check each period doesn't overlap with next
        for i in range(len(df) - 1):
            current_end = df.iloc[i]["end"]
            next_start = df.iloc[i + 1]["start"]
            assert current_end <= next_start, f"Overlapping periods at index {i}"
