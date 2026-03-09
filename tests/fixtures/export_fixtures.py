#!/usr/bin/env python3
"""
Test fixtures for export functionality.

Provides reusable test data factories and fixtures for testing
the export system with various configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from sleep_scoring_app.core.constants import AlgorithmType, MarkerType
from sleep_scoring_app.core.dataclasses import (
    DailyNonwearMarkers,
    DailySleepMarkers,
    ManualNonwearPeriod,
    ParticipantInfo,
    SleepMetrics,
    SleepPeriod,
)

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass
class ParticipantConfig:
    """Configuration for generating participant data."""

    numerical_id: str
    group: str = "Control"
    timepoint: str = "T1"


@dataclass
class SleepPeriodConfig:
    """Configuration for generating sleep periods."""

    onset_hour: int = 22
    onset_minute: int = 0
    duration_hours: float = 8.0
    marker_index: int = 1
    marker_type: MarkerType = MarkerType.MAIN_SLEEP
    base_date: date = field(default_factory=lambda: date(2024, 1, 10))


@dataclass
class NonwearPeriodConfig:
    """Configuration for generating nonwear periods."""

    start_hour: int = 10
    start_minute: int = 0
    duration_minutes: float = 60.0
    marker_index: int = 1
    base_date: date = field(default_factory=lambda: date(2024, 1, 10))


@dataclass
class ExportTestData:
    """Container for a complete export test dataset."""

    metrics_list: list[SleepMetrics]
    participant_count: int
    total_periods: int
    has_naps: bool
    has_nonwear: bool
    groups: list[str]
    timepoints: list[str]


def create_participant(config: ParticipantConfig) -> ParticipantInfo:
    """Create a ParticipantInfo from configuration."""
    return ParticipantInfo(
        numerical_id=config.numerical_id,
        full_id=f"{config.numerical_id} {config.timepoint} {config.group}",
        group_str=config.group,
        timepoint_str=config.timepoint,
    )


def create_sleep_period(config: SleepPeriodConfig) -> SleepPeriod:
    """Create a SleepPeriod from configuration."""
    onset_dt = datetime.combine(
        config.base_date,
        datetime.min.time().replace(hour=config.onset_hour, minute=config.onset_minute),
    )
    offset_dt = onset_dt + timedelta(hours=config.duration_hours)

    return SleepPeriod(
        onset_timestamp=onset_dt.timestamp(),
        offset_timestamp=offset_dt.timestamp(),
        marker_index=config.marker_index,
        marker_type=config.marker_type,
    )


def create_nonwear_period(config: NonwearPeriodConfig) -> ManualNonwearPeriod:
    """Create a ManualNonwearPeriod from configuration."""
    start_dt = datetime.combine(
        config.base_date,
        datetime.min.time().replace(hour=config.start_hour, minute=config.start_minute),
    )
    end_dt = start_dt + timedelta(minutes=config.duration_minutes)

    return ManualNonwearPeriod(
        start_timestamp=start_dt.timestamp(),
        end_timestamp=end_dt.timestamp(),
        marker_index=config.marker_index,
    )


def create_sleep_metrics(
    participant_config: ParticipantConfig,
    analysis_date: str,
    filename: str | None = None,
    periods: list[SleepPeriod] | None = None,
    total_sleep_time: float = 420.0,
    sleep_efficiency: float = 85.0,
) -> SleepMetrics:
    """Create a SleepMetrics object with full configuration."""
    participant = create_participant(participant_config)

    markers = DailySleepMarkers()
    if periods:
        for i, period in enumerate(periods[:4], 1):
            setattr(markers, f"period_{i}", period)
    else:
        # Create default main sleep period
        default_config = SleepPeriodConfig(base_date=date.fromisoformat(analysis_date))
        markers.period_1 = create_sleep_period(default_config)

    return SleepMetrics(
        filename=filename or f"participant_{participant_config.numerical_id}.csv",
        analysis_date=analysis_date,
        algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
        daily_sleep_markers=markers,
        participant=participant,
        total_sleep_time=total_sleep_time,
        sleep_efficiency=sleep_efficiency,
        total_minutes_in_bed=480.0,
        waso=45.0,
        awakenings=3,
        average_awakening_length=15.0,
        movement_index=2.5,
        fragmentation_index=12.3,
        sleep_fragmentation_index=8.7,
    )


def generate_basic_export_dataset(participant_count: int = 3) -> ExportTestData:
    """
    Generate a basic export test dataset with simple configuration.

    Args:
        participant_count: Number of participants to generate

    Returns:
        ExportTestData containing the generated metrics

    """
    metrics_list = []
    groups = ["Control", "Treatment"]
    timepoints = ["T1", "T2"]

    for i in range(participant_count):
        config = ParticipantConfig(
            numerical_id=f"{1000 + i}",
            group=groups[i % len(groups)],
            timepoint=timepoints[i % len(timepoints)],
        )

        metrics = create_sleep_metrics(
            participant_config=config,
            analysis_date=f"2024-01-{10 + i:02d}",
            total_sleep_time=420.0 + i * 10,
            sleep_efficiency=85.0 + i,
        )
        metrics_list.append(metrics)

    return ExportTestData(
        metrics_list=metrics_list,
        participant_count=participant_count,
        total_periods=participant_count,  # One period per participant
        has_naps=False,
        has_nonwear=False,
        groups=list(set(groups)),
        timepoints=list(set(timepoints)),
    )


def generate_multi_period_dataset() -> ExportTestData:
    """
    Generate a dataset with multiple sleep periods (main sleep + naps).

    Returns:
        ExportTestData with main sleep and nap periods

    """
    metrics_list = []
    total_periods = 0

    # Participant 1: Main sleep + 1 nap
    base_date = date(2024, 1, 10)
    main_sleep_1 = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=22,
            duration_hours=8.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
            base_date=base_date,
        )
    )
    nap_1 = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=14,
            duration_hours=1.5,
            marker_index=2,
            marker_type=MarkerType.NAP,
            base_date=base_date,
        )
    )

    metrics_1 = create_sleep_metrics(
        participant_config=ParticipantConfig("1000", "Control", "T1"),
        analysis_date=base_date.isoformat(),
        periods=[main_sleep_1, nap_1],
    )
    metrics_list.append(metrics_1)
    total_periods += 2

    # Participant 2: Main sleep + 2 naps
    base_date = date(2024, 1, 11)
    main_sleep_2 = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=23,
            duration_hours=7.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
            base_date=base_date,
        )
    )
    nap_2a = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=13,
            duration_hours=1.0,
            marker_index=2,
            marker_type=MarkerType.NAP,
            base_date=base_date,
        )
    )
    nap_2b = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=17,
            duration_hours=0.5,
            marker_index=3,
            marker_type=MarkerType.NAP,
            base_date=base_date,
        )
    )

    metrics_2 = create_sleep_metrics(
        participant_config=ParticipantConfig("1001", "Treatment", "T1"),
        analysis_date=base_date.isoformat(),
        periods=[main_sleep_2, nap_2a, nap_2b],
    )
    metrics_list.append(metrics_2)
    total_periods += 3

    # Participant 3: Main sleep only
    base_date = date(2024, 1, 12)
    main_sleep_3 = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=21,
            duration_hours=9.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
            base_date=base_date,
        )
    )

    metrics_3 = create_sleep_metrics(
        participant_config=ParticipantConfig("1002", "Control", "T2"),
        analysis_date=base_date.isoformat(),
        periods=[main_sleep_3],
    )
    metrics_list.append(metrics_3)
    total_periods += 1

    return ExportTestData(
        metrics_list=metrics_list,
        participant_count=3,
        total_periods=total_periods,
        has_naps=True,
        has_nonwear=False,
        groups=["Control", "Treatment"],
        timepoints=["T1", "T2"],
    )


def generate_nonwear_dataset() -> tuple[list[SleepMetrics], dict[str, DailyNonwearMarkers]]:
    """
    Generate a dataset with both sleep and nonwear markers.

    Returns:
        Tuple of (metrics_list, nonwear_by_key) where nonwear_by_key
        maps filename_date keys to DailyNonwearMarkers

    """
    metrics_list = []
    nonwear_by_key = {}

    # Participant with overlapping nonwear
    base_date = date(2024, 1, 10)
    main_sleep = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=22,
            duration_hours=8.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
            base_date=base_date,
        )
    )

    metrics = create_sleep_metrics(
        participant_config=ParticipantConfig("1000", "Control", "T1"),
        analysis_date=base_date.isoformat(),
        periods=[main_sleep],
    )
    metrics_list.append(metrics)

    # Create nonwear that overlaps with sleep
    nonwear_markers = DailyNonwearMarkers()
    nonwear_period = create_nonwear_period(
        NonwearPeriodConfig(
            start_hour=23,  # During sleep
            duration_minutes=30.0,
            marker_index=1,
            base_date=base_date,
        )
    )
    nonwear_markers.period_1 = nonwear_period

    key = f"{metrics.filename}_{base_date.isoformat()}"
    nonwear_by_key[key] = nonwear_markers

    # Participant with non-overlapping nonwear
    base_date = date(2024, 1, 11)
    main_sleep = create_sleep_period(
        SleepPeriodConfig(
            onset_hour=22,
            duration_hours=8.0,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
            base_date=base_date,
        )
    )

    metrics = create_sleep_metrics(
        participant_config=ParticipantConfig("1001", "Treatment", "T1"),
        analysis_date=base_date.isoformat(),
        periods=[main_sleep],
    )
    metrics_list.append(metrics)

    # Create nonwear during daytime (not overlapping)
    nonwear_markers = DailyNonwearMarkers()
    nonwear_period = create_nonwear_period(
        NonwearPeriodConfig(
            start_hour=10,  # During day
            duration_minutes=60.0,
            marker_index=1,
            base_date=base_date,
        )
    )
    nonwear_markers.period_1 = nonwear_period

    key = f"{metrics.filename}_{base_date.isoformat()}"
    nonwear_by_key[key] = nonwear_markers

    return metrics_list, nonwear_by_key


def generate_longitudinal_dataset(
    participant_id: str = "1000",
    dates: int = 10,
    group: str = "Control",
    timepoint: str = "T1",
) -> list[SleepMetrics]:
    """
    Generate a longitudinal dataset for a single participant.

    Args:
        participant_id: The participant ID
        dates: Number of consecutive dates to generate
        group: Participant group
        timepoint: Participant timepoint

    Returns:
        List of SleepMetrics for consecutive dates

    """
    metrics_list = []
    start_date = date(2024, 1, 10)

    for i in range(dates):
        current_date = start_date + timedelta(days=i)

        # Vary sleep times slightly for realism
        onset_hour = 22 + (i % 2)  # Alternate between 22:00 and 23:00
        duration = 7.5 + (i % 3) * 0.5  # Vary between 7.5 and 8.5 hours

        sleep_period = create_sleep_period(
            SleepPeriodConfig(
                onset_hour=onset_hour,
                duration_hours=duration,
                marker_index=1,
                marker_type=MarkerType.MAIN_SLEEP,
                base_date=current_date,
            )
        )

        metrics = create_sleep_metrics(
            participant_config=ParticipantConfig(participant_id, group, timepoint),
            analysis_date=current_date.isoformat(),
            periods=[sleep_period],
            total_sleep_time=duration * 50,  # Rough estimate
            sleep_efficiency=80.0 + (i % 10),
        )
        metrics_list.append(metrics)

    return metrics_list


def generate_large_dataset(participant_count: int = 100) -> ExportTestData:
    """
    Generate a large dataset for performance testing.

    Args:
        participant_count: Number of participants (default 100)

    Returns:
        ExportTestData with many participants

    """
    metrics_list = []
    groups = ["Control", "Treatment", "Placebo"]
    timepoints = ["T1", "T2", "T3"]

    for i in range(participant_count):
        config = ParticipantConfig(
            numerical_id=f"{1000 + i}",
            group=groups[i % len(groups)],
            timepoint=timepoints[i % len(timepoints)],
        )

        # Add some variation in dates
        analysis_date = date(2024, 1, 10) + timedelta(days=i % 30)

        metrics = create_sleep_metrics(
            participant_config=config,
            analysis_date=analysis_date.isoformat(),
            total_sleep_time=360.0 + (i % 120),  # 6-8 hours
            sleep_efficiency=70.0 + (i % 25),  # 70-95%
        )
        metrics_list.append(metrics)

    return ExportTestData(
        metrics_list=metrics_list,
        participant_count=participant_count,
        total_periods=participant_count,
        has_naps=False,
        has_nonwear=False,
        groups=groups,
        timepoints=timepoints,
    )


@pytest.fixture
def basic_export_dataset() -> ExportTestData:
    """Provide a basic export test dataset."""
    return generate_basic_export_dataset()


@pytest.fixture
def multi_period_dataset() -> ExportTestData:
    """Provide a dataset with multiple sleep periods."""
    return generate_multi_period_dataset()


@pytest.fixture
def nonwear_dataset() -> tuple[list[SleepMetrics], dict[str, DailyNonwearMarkers]]:
    """Provide a dataset with nonwear markers."""
    return generate_nonwear_dataset()


@pytest.fixture
def longitudinal_dataset() -> list[SleepMetrics]:
    """Provide a longitudinal dataset for one participant."""
    return generate_longitudinal_dataset()


@pytest.fixture
def large_dataset() -> ExportTestData:
    """Provide a large dataset for performance testing."""
    return generate_large_dataset(participant_count=100)


@pytest.fixture
def participant_factory() -> Callable[[str, str, str], ParticipantInfo]:
    """Factory fixture for creating participants."""

    def _factory(
        numerical_id: str = "1000",
        group: str = "Control",
        timepoint: str = "T1",
    ) -> ParticipantInfo:
        return create_participant(ParticipantConfig(numerical_id, group, timepoint))

    return _factory


@pytest.fixture
def sleep_period_factory() -> Callable[..., SleepPeriod]:
    """Factory fixture for creating sleep periods."""

    def _factory(
        onset_hour: int = 22,
        duration_hours: float = 8.0,
        marker_index: int = 1,
        marker_type: MarkerType = MarkerType.MAIN_SLEEP,
        base_date: date = date(2024, 1, 10),
    ) -> SleepPeriod:
        return create_sleep_period(
            SleepPeriodConfig(
                onset_hour=onset_hour,
                duration_hours=duration_hours,
                marker_index=marker_index,
                marker_type=marker_type,
                base_date=base_date,
            )
        )

    return _factory


@pytest.fixture
def sleep_metrics_factory(
    participant_factory,
    sleep_period_factory,
) -> Callable[..., SleepMetrics]:
    """Factory fixture for creating SleepMetrics."""

    def _factory(
        participant_id: str = "1000",
        group: str = "Control",
        timepoint: str = "T1",
        analysis_date: str = "2024-01-10",
        periods: list[SleepPeriod] | None = None,
        **kwargs,
    ) -> SleepMetrics:
        return create_sleep_metrics(
            participant_config=ParticipantConfig(participant_id, group, timepoint),
            analysis_date=analysis_date,
            periods=periods,
            **kwargs,
        )

    return _factory
