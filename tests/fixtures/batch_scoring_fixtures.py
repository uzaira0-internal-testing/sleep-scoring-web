#!/usr/bin/env python3
"""
Test fixtures for batch scoring service.

Provides reusable activity data files and diary data for testing
the batch scoring pipeline with real data processing.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd
import pytest


def create_activity_csv_content(
    start_datetime: datetime,
    minutes: int = 1440,
    activity_pattern: list[int] | None = None,
) -> str:
    """
    Create activity CSV content with known patterns.

    Args:
        start_datetime: Start timestamp for the data
        minutes: Number of minute epochs to generate (default: 1440 = 24 hours)
        activity_pattern: Optional list of activity values. If shorter than minutes,
                         it will be repeated. If None, generates low activity (sleep-like).

    Returns:
        CSV string with datetime and Axis1 columns

    """
    if activity_pattern is None:
        # Default: low activity (likely to score as sleep)
        activity_pattern = [5, 0, 10, 0, 5, 0, 8, 0, 3, 0]

    rows = []
    rows.append("datetime,Axis1,Vector Magnitude")

    for i in range(minutes):
        ts = start_datetime + timedelta(minutes=i)
        activity = activity_pattern[i % len(activity_pattern)]
        # Vector magnitude slightly higher than Axis1
        vm = activity + 5 if activity > 0 else 0
        rows.append(f"{ts.strftime('%Y-%m-%d %H:%M:%S')},{activity},{vm}")

    return "\n".join(rows)


def create_diary_csv_content(entries: list[dict]) -> str:
    """
    Create diary CSV content.

    Args:
        entries: List of dicts with keys:
            - participant_id: str
            - date: str (YYYY-MM-DD)
            - sleep_onset_time: str (HH:MM)
            - sleep_offset_time: str (HH:MM)

    Returns:
        CSV string with diary columns

    """
    rows = []
    rows.append("participant_id,date,sleep_onset_time,sleep_offset_time")

    for entry in entries:
        rows.append(f"{entry['participant_id']},{entry['date']},{entry['sleep_onset_time']},{entry['sleep_offset_time']}")

    return "\n".join(rows)


# Pattern 1: Continuous low activity (should score as sleep)
# Sadeh algorithm: PS = 7.601 - 0.065*AVG - 1.08*NATS - 0.056*SD - 0.703*LG
# For very low activity (all zeros): PS = 7.601 - 0 - 0 - 0 - 0.703*log(1) = 7.601
# Since 7.601 > -4.0, all epochs should score as sleep (1)
CONTINUOUS_SLEEP_PATTERN = [0] * 20

# Pattern 2: Continuous high activity (should score as wake)
# For high activity (e.g., 300): PS = 7.601 - 0.065*300 - 0 - high_SD - 0.703*log(301)
# PS = 7.601 - 19.5 - 0 - SD - 4.02 = -15.9 - SD
# Since -15.9 < -4.0, all epochs should score as wake (0)
CONTINUOUS_WAKE_PATTERN = [300] * 20

# Pattern 3: Mixed pattern - alternating sleep/wake
# Low activity periods followed by high activity
MIXED_PATTERN = [0, 0, 5, 0, 0, 5, 0, 0, 0, 0] + [250, 300, 280, 290, 300] * 2

# Pattern 4: Realistic night pattern
# Low activity during night (22:00-06:00), high during day
# 8 hours of low activity = 480 minutes, then 16 hours high = 960 minutes
REALISTIC_NIGHT_PATTERN_LOW = [0, 5, 0, 10, 0, 5, 0, 0, 8, 0]  # Sleep-like
REALISTIC_NIGHT_PATTERN_HIGH = [150, 200, 180, 250, 300, 280, 200, 150, 180, 220]  # Wake-like


@pytest.fixture
def activity_folder_with_files(tmp_path: Path) -> tuple[Path, list[Path]]:
    """
    Create a temporary folder with real activity CSV files.

    Returns:
        Tuple of (folder_path, list_of_created_files)

    """
    folder = tmp_path / "activity_data"
    folder.mkdir()

    files = []

    # File 1: Participant 1000, date 2024-01-10
    # Uses low activity pattern (should score mostly sleep)
    file1 = folder / "P1-1000-A-D1-P1_2024-01-10.csv"
    start_dt = datetime(2024, 1, 10, 0, 0, 0)
    content = create_activity_csv_content(
        start_datetime=start_dt,
        minutes=1440,  # Full 24 hours
        activity_pattern=CONTINUOUS_SLEEP_PATTERN,
    )
    file1.write_text(content)
    files.append(file1)

    # File 2: Participant 1001, date 2024-01-11
    # Uses high activity pattern (should score mostly wake)
    file2 = folder / "P1-1001-A-D1-P1_2024-01-11.csv"
    start_dt = datetime(2024, 1, 11, 0, 0, 0)
    content = create_activity_csv_content(
        start_datetime=start_dt,
        minutes=1440,
        activity_pattern=CONTINUOUS_WAKE_PATTERN,
    )
    file2.write_text(content)
    files.append(file2)

    # File 3: Participant 1002, date 2024-01-12
    # Uses realistic night pattern
    file3 = folder / "P1-1002-A-D1-P1_2024-01-12.csv"
    start_dt = datetime(2024, 1, 12, 0, 0, 0)
    # Create realistic pattern: 6 hours wake, 8 hours sleep, 10 hours wake
    wake_morning = REALISTIC_NIGHT_PATTERN_HIGH * 36  # 360 minutes
    sleep_period = REALISTIC_NIGHT_PATTERN_LOW * 48  # 480 minutes
    wake_evening = REALISTIC_NIGHT_PATTERN_HIGH * 60  # 600 minutes
    full_pattern = wake_morning + sleep_period + wake_evening
    content = create_activity_csv_content(
        start_datetime=start_dt,
        minutes=1440,
        activity_pattern=full_pattern,
    )
    file3.write_text(content)
    files.append(file3)

    return folder, files


@pytest.fixture
def diary_file(tmp_path: Path) -> Path:
    """
    Create a diary file matching the activity files.

    Returns:
        Path to the created diary CSV file

    """
    diary_path = tmp_path / "diary.csv"

    entries = [
        {
            "participant_id": "1000",
            "date": "2024-01-10",
            "sleep_onset_time": "22:00",
            "sleep_offset_time": "07:00",
        },
        {
            "participant_id": "1001",
            "date": "2024-01-11",
            "sleep_onset_time": "23:00",
            "sleep_offset_time": "06:30",
        },
        {
            "participant_id": "1002",
            "date": "2024-01-12",
            "sleep_onset_time": "22:30",
            "sleep_offset_time": "06:00",
        },
    ]

    content = create_diary_csv_content(entries)
    diary_path.write_text(content)

    return diary_path


@pytest.fixture
def single_activity_file_low_activity(tmp_path: Path) -> Path:
    """
    Create a single activity file with low activity (should score as sleep).

    Returns:
        Path to the created CSV file

    """
    file_path = tmp_path / "low_activity_2024-01-15.csv"
    start_dt = datetime(2024, 1, 15, 0, 0, 0)
    content = create_activity_csv_content(
        start_datetime=start_dt,
        minutes=1440,
        activity_pattern=CONTINUOUS_SLEEP_PATTERN,
    )
    file_path.write_text(content)
    return file_path


@pytest.fixture
def single_activity_file_high_activity(tmp_path: Path) -> Path:
    """
    Create a single activity file with high activity (should score as wake).

    Returns:
        Path to the created CSV file

    """
    file_path = tmp_path / "high_activity_2024-01-15.csv"
    start_dt = datetime(2024, 1, 15, 0, 0, 0)
    content = create_activity_csv_content(
        start_datetime=start_dt,
        minutes=1440,
        activity_pattern=CONTINUOUS_WAKE_PATTERN,
    )
    file_path.write_text(content)
    return file_path


@pytest.fixture
def activity_df_low_activity() -> pd.DataFrame:
    """
    Create a DataFrame with low activity data.

    The Sadeh algorithm should score most epochs as sleep (1).

    Returns:
        DataFrame with datetime and Axis1 columns

    """
    start_dt = datetime(2024, 1, 15, 0, 0, 0)
    timestamps = [start_dt + timedelta(minutes=i) for i in range(60)]
    activity = [5, 0, 10, 0, 5, 0, 8, 0, 3, 0] * 6  # Repeat low activity pattern

    return pd.DataFrame({"datetime": timestamps, "Axis1": activity})


@pytest.fixture
def activity_df_high_activity() -> pd.DataFrame:
    """
    Create a DataFrame with high activity data.

    The Sadeh algorithm should score most epochs as wake (0).

    Returns:
        DataFrame with datetime and Axis1 columns

    """
    start_dt = datetime(2024, 1, 15, 0, 0, 0)
    timestamps = [start_dt + timedelta(minutes=i) for i in range(60)]
    activity = [300] * 60  # All high activity

    return pd.DataFrame({"datetime": timestamps, "Axis1": activity})


# For validation: These are the expected scoring behaviors based on the Sadeh algorithm
#
# Sadeh (1994) formula:
# PS = 7.601 - 0.065*AVG - 1.08*NATS - 0.056*SD - 0.703*LG
#
# Where:
# - AVG: Mean activity in 11-minute window (capped at 300)
# - NATS: Count of epochs with activity in [50, 100)
# - SD: Standard deviation of 6-epoch forward window
# - LG: log(activity + 1)
#
# Classification: PS > -4.0 (ActiLife threshold) -> Sleep (1)
#
# Expected behaviors:
# 1. All zeros: PS = 7.601 - 0 - 0 - 0 - 0 = 7.601 > -4.0 -> Sleep
# 2. All 300s: PS = 7.601 - 19.5 - 0 - 0 - 4.02 = -15.9 < -4.0 -> Wake
# 3. Mixed: Varies based on surrounding context
