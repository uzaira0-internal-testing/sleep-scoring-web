"""Tests for loading sleep diary data from demo files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.demo_data
class TestDiaryFileExists:
    """Test that diary file exists."""

    def test_diary_directory_exists(self, diary_dir: Path) -> None:
        """Diary directory should exist."""
        assert diary_dir.exists()
        assert diary_dir.is_dir()

    def test_diary_file_exists(self, diary_dir: Path) -> None:
        """Sleep diary CSV should exist."""
        files = list(diary_dir.glob("*.csv"))
        assert len(files) >= 1, "No diary CSV files found"


@pytest.mark.demo_data
class TestDiaryDataLoading:
    """Test loading and parsing diary data."""

    def test_load_diary_file(self, diary_dir: Path) -> None:
        """Diary file should load without errors."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])
        assert len(df) > 0, "Diary file is empty"

    def test_diary_required_columns(self, diary_dir: Path) -> None:
        """Diary should have required columns."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        required_columns = [
            "participant_id",
            "startdate",
            "in_bed_time",
            "sleep_onset_time",
            "sleep_offset_time",
        ]

        for col in required_columns:
            assert col in df.columns, f"Missing required column: {col}"

    def test_diary_optional_columns(self, diary_dir: Path) -> None:
        """Diary may have optional nap columns."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        optional_columns = ["napped", "napstart_1_time", "napend_1_time", "nonwear_occurred"]

        found_optional = [col for col in optional_columns if col in df.columns]
        assert len(found_optional) > 0, "No optional columns found"

    def test_diary_participant_id(self, diary_dir: Path) -> None:
        """Participant ID should be consistent."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        unique_ids = df["participant_id"].unique()
        assert len(unique_ids) == 1, f"Multiple participant IDs found: {unique_ids}"
        assert unique_ids[0] == "DEMO-001", f"Unexpected participant ID: {unique_ids[0]}"

    def test_diary_has_multiple_days(self, diary_dir: Path) -> None:
        """Diary should cover multiple days."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        assert len(df) >= 7, f"Diary has only {len(df)} days, expected 7+"

    def test_diary_dates_parse(self, diary_dir: Path) -> None:
        """Date column should parse correctly."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        dates = pd.to_datetime(df["startdate"], format="mixed")
        assert dates.notna().all(), "Failed to parse some dates"

    def test_diary_times_present(self, diary_dir: Path) -> None:
        """Time columns should have values."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        # Check bed time and wake time are present
        assert df["in_bed_time"].notna().all(), "Missing in_bed_time values"
        assert df["sleep_offset_time"].notna().all(), "Missing sleep_offset_time values"

    def test_diary_nap_data(self, diary_dir: Path) -> None:
        """Nap data should be consistent."""
        files = list(diary_dir.glob("*.csv"))
        df = pd.read_csv(files[0])

        if "napped" in df.columns:
            # If napped=Yes, nap times should be present
            napped_rows = df[df["napped"] == "Yes"]
            if len(napped_rows) > 0:
                assert napped_rows["napstart_1_time"].notna().any(), "Napped=Yes but no nap start times"
