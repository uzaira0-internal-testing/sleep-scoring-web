"""Integration tests for demo data with application services."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest


@pytest.mark.demo_data
class TestDemoDataIntegration:
    """Test demo data works with application services."""

    def test_activity_data_covers_diary_period(self, activity_dir: Path, diary_dir: Path) -> None:
        """Activity data should cover the same period as diary."""
        # Load diary dates
        diary_files = list(diary_dir.glob("*.csv"))
        diary_df = pd.read_csv(diary_files[0])
        diary_dates = pd.to_datetime(diary_df["startdate"], format="mixed")

        # Load activity data (using generic format for simplicity)
        activity_files = list(activity_dir.glob("*_generic.csv"))
        activity_df = pd.read_csv(activity_files[0])
        activity_df["datetime"] = pd.to_datetime(activity_df["datetime"])

        activity_start = activity_df["datetime"].min().date()
        activity_end = activity_df["datetime"].max().date()

        diary_start = diary_dates.min().date()
        diary_end = diary_dates.max().date()

        # Activity should cover diary period
        assert activity_start <= diary_start, "Activity starts after diary"
        assert activity_end >= diary_end, "Activity ends before diary"

    def test_nonwear_periods_within_activity_range(self, activity_dir: Path, nonwear_dir: Path) -> None:
        """Nonwear periods should fall within activity data timeframe."""
        # Load activity data
        activity_files = list(activity_dir.glob("*_generic.csv"))
        activity_df = pd.read_csv(activity_files[0])
        activity_df["datetime"] = pd.to_datetime(activity_df["datetime"])

        activity_start = activity_df["datetime"].min()
        activity_end = activity_df["datetime"].max()

        # Load nonwear periods
        nonwear_files = list(nonwear_dir.glob("*.csv"))
        nonwear_df = pd.read_csv(nonwear_files[0])
        nonwear_df["start"] = pd.to_datetime(nonwear_df["start"])
        nonwear_df["end"] = pd.to_datetime(nonwear_df["end"])

        # All nonwear periods should be within activity range
        for _, row in nonwear_df.iterrows():
            assert row["start"] >= activity_start, f"Nonwear starts before activity data: {row['start']}"
            assert row["end"] <= activity_end, f"Nonwear ends after activity data: {row['end']}"

    def test_all_device_formats_same_duration(self, activity_dir: Path) -> None:
        """All device format files should cover the same duration."""
        durations = {}

        format_configs = [
            ("actigraph", 10, "Date", "Time"),
            ("actiwatch", 7, "Date", "Time"),
            ("axivity", 6, "timestamp", None),
            ("geneactiv", 7, "timestamp", None),
            ("generic", 0, "datetime", None),
            ("motionwatch", 4, "Date/Time", None),
        ]

        for device, skip_rows, date_col, time_col in format_configs:
            files = list(activity_dir.glob(f"*_{device}.csv"))
            if not files:
                continue

            df = pd.read_csv(files[0], skiprows=skip_rows)

            if time_col:
                df["datetime"] = pd.to_datetime(df[date_col] + " " + df[time_col])
            else:
                df["datetime"] = pd.to_datetime(df[date_col])

            duration = (df["datetime"].max() - df["datetime"].min()).total_seconds()
            durations[device] = duration

        # All durations should be similar (within 1 minute)
        duration_values = list(durations.values())
        if len(duration_values) > 1:
            max_diff = max(duration_values) - min(duration_values)
            assert max_diff < 60, f"Device formats have different durations: {durations}"

    def test_participant_id_consistent_across_files(self, diary_dir: Path, nonwear_dir: Path) -> None:
        """Participant ID should be consistent between diary and nonwear."""
        diary_files = list(diary_dir.glob("*.csv"))
        diary_df = pd.read_csv(diary_files[0])
        diary_id = diary_df["participant_id"].iloc[0]

        nonwear_files = list(nonwear_dir.glob("*.csv"))
        nonwear_df = pd.read_csv(nonwear_files[0])
        nonwear_id = nonwear_df["participant_id"].iloc[0]

        assert diary_id == nonwear_id, f"Participant ID mismatch: diary={diary_id}, nonwear={nonwear_id}"


@pytest.mark.demo_data
class TestDataQuality:
    """Test overall data quality of demo files."""

    def test_activity_no_all_zero_days(self, activity_dir: Path) -> None:
        """No day should have all-zero activity (unrealistic)."""
        files = list(activity_dir.glob("*_generic.csv"))
        df = pd.read_csv(files[0])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df["date"] = df["datetime"].dt.date

        daily_totals = df.groupby("date")["activity_count"].sum()

        # No day should have zero total activity
        zero_days = daily_totals[daily_totals == 0]
        assert len(zero_days) == 0, f"Days with zero activity: {list(zero_days.index)}"

    def test_activity_realistic_sleep_pattern(self, activity_dir: Path) -> None:
        """Activity should show lower values during typical sleep hours."""
        files = list(activity_dir.glob("*_generic.csv"))
        df = pd.read_csv(files[0])
        df["datetime"] = pd.to_datetime(df["datetime"])
        df["hour"] = df["datetime"].dt.hour

        # Average activity by hour
        hourly_avg = df.groupby("hour")["activity_count"].mean()

        # Night hours (0-5) should have lower average than day (10-17)
        night_avg = hourly_avg[(hourly_avg.index >= 0) & (hourly_avg.index <= 5)].mean()
        day_avg = hourly_avg[(hourly_avg.index >= 10) & (hourly_avg.index <= 17)].mean()

        assert night_avg < day_avg, f"Night activity ({night_avg:.1f}) not lower than day ({day_avg:.1f})"

    def test_demo_data_complete(self, demo_data_dir: Path) -> None:
        """Demo data directory should have all expected subdirectories."""
        expected_dirs = ["activity", "diary", "nonwear"]

        for subdir in expected_dirs:
            path = demo_data_dir / subdir
            assert path.exists(), f"Missing subdirectory: {subdir}"
            assert path.is_dir(), f"{subdir} is not a directory"

            # Each should have at least one CSV
            csvs = list(path.glob("*.csv"))
            assert len(csvs) >= 1, f"No CSV files in {subdir}"
