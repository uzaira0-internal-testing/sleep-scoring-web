"""
Tests for ConsecutiveEpochsSleepPeriodDetector.

Tests sleep onset/offset detection using consecutive epoch rules.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from sleep_scoring_app.core.algorithms.sleep_period.config import (
    CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG,
    TUDOR_LOCKE_2014_CONFIG,
    AnchorPosition,
    ConsecutiveEpochsSleepPeriodDetectorConfig,
    EpochState,
)
from sleep_scoring_app.core.algorithms.sleep_period.consecutive_epochs import (
    ConsecutiveEpochsSleepPeriodDetector,
    find_sleep_onset_offset,
)


@pytest.fixture
def default_detector() -> ConsecutiveEpochsSleepPeriodDetector:
    """Create detector with default config."""
    return ConsecutiveEpochsSleepPeriodDetector()


@pytest.fixture
def sample_timestamps() -> list[datetime]:
    """Create 20 sample timestamps at 1-minute intervals."""
    base = datetime(2024, 1, 15, 22, 0, 0)
    return [base + timedelta(minutes=i) for i in range(20)]


@pytest.fixture
def sleep_pattern() -> list[int]:
    """Sample sleep pattern: wake, then sleep, then wake at end.

    Pattern: 0,0,0,1,1,1,1,1,1,1,1,1,1,1,0,0,0,0,0,0
             ^ onset should be index 3 (first of 3+ consecutive sleep)
                                       ^ offset should be index 13 or 14
    """
    return [0, 0, 0] + [1] * 11 + [0] * 6


class TestDetectorInit:
    """Tests for detector initialization."""

    def test_creates_with_default_config(self) -> None:
        """Creates with default configuration."""
        detector = ConsecutiveEpochsSleepPeriodDetector()

        assert detector.config.onset_n == 3
        assert detector.config.offset_n == 5

    def test_creates_with_custom_config(self) -> None:
        """Creates with custom configuration."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=5, offset_n=10)
        detector = ConsecutiveEpochsSleepPeriodDetector(config=config)

        assert detector.config.onset_n == 5
        assert detector.config.offset_n == 10

    def test_creates_with_preset_name(self) -> None:
        """Creates with preset name."""
        detector = ConsecutiveEpochsSleepPeriodDetector(preset_name="Tudor-Locke (2014)")

        assert detector.name == "Tudor-Locke (2014)"


class TestProtocolProperties:
    """Tests for protocol property implementations."""

    def test_name_generates_from_config(self) -> None:
        """Name generates from config when no preset name."""
        detector = ConsecutiveEpochsSleepPeriodDetector()

        # Format: "Consecutive {onset_n}{state}/{offset_n}{state}"
        assert "Consecutive" in detector.name
        assert "3" in detector.name

    def test_identifier_is_unique(self) -> None:
        """Identifier is unique per configuration."""
        detector1 = ConsecutiveEpochsSleepPeriodDetector(config=ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=3, offset_n=5))
        detector2 = ConsecutiveEpochsSleepPeriodDetector(config=ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=5, offset_n=10))

        assert detector1.identifier != detector2.identifier

    def test_description_contains_details(self) -> None:
        """Description contains onset/offset details."""
        detector = ConsecutiveEpochsSleepPeriodDetector()

        assert "Onset" in detector.description
        assert "Offset" in detector.description


class TestGetSetParameters:
    """Tests for get_parameters and set_parameters methods."""

    def test_get_parameters_returns_dict(self, default_detector: ConsecutiveEpochsSleepPeriodDetector) -> None:
        """get_parameters returns parameter dictionary."""
        params = default_detector.get_parameters()

        assert "onset_n" in params
        assert "offset_n" in params
        assert "onset_state" in params

    def test_set_parameters_updates_config(self, default_detector: ConsecutiveEpochsSleepPeriodDetector) -> None:
        """set_parameters updates configuration."""
        default_detector.set_parameters(onset_n=7, offset_n=12)

        assert default_detector.config.onset_n == 7
        assert default_detector.config.offset_n == 12

    def test_set_parameters_raises_for_invalid(self, default_detector: ConsecutiveEpochsSleepPeriodDetector) -> None:
        """set_parameters raises for invalid parameter names."""
        with pytest.raises(ValueError) as exc_info:
            default_detector.set_parameters(invalid_param=5)

        assert "Invalid parameters" in str(exc_info.value)


class TestApplyRules:
    """Tests for apply_rules method."""

    def test_finds_onset_and_offset(
        self,
        default_detector: ConsecutiveEpochsSleepPeriodDetector,
        sample_timestamps: list[datetime],
        sleep_pattern: list[int],
    ) -> None:
        """Finds both onset and offset."""
        onset_idx, offset_idx = default_detector.apply_rules(
            sleep_pattern,
            sample_timestamps[0],
            sample_timestamps[-1],
            sample_timestamps,
        )

        assert onset_idx is not None
        assert offset_idx is not None
        assert onset_idx < offset_idx

    def test_onset_at_first_consecutive_sleep(
        self,
        default_detector: ConsecutiveEpochsSleepPeriodDetector,
        sample_timestamps: list[datetime],
        sleep_pattern: list[int],
    ) -> None:
        """Onset is at first epoch of consecutive sleep run."""
        onset_idx, _ = default_detector.apply_rules(
            sleep_pattern,
            sample_timestamps[0],
            sample_timestamps[-1],
            sample_timestamps,
        )

        # First 3+ consecutive sleep starts at index 3
        assert onset_idx == 3

    def test_returns_none_for_empty_scores(self, default_detector: ConsecutiveEpochsSleepPeriodDetector) -> None:
        """Returns None for empty sleep scores."""
        onset_idx, offset_idx = default_detector.apply_rules(
            [],
            datetime.now(),
            datetime.now(),
            [],
        )

        assert onset_idx is None
        assert offset_idx is None

    def test_returns_none_for_all_wake(
        self,
        default_detector: ConsecutiveEpochsSleepPeriodDetector,
        sample_timestamps: list[datetime],
    ) -> None:
        """Returns None when all epochs are wake."""
        all_wake = [0] * 20

        onset_idx, _offset_idx = default_detector.apply_rules(
            all_wake,
            sample_timestamps[0],
            sample_timestamps[-1],
            sample_timestamps,
        )

        assert onset_idx is None


class TestFindOnset:
    """Tests for _find_onset method."""

    def test_finds_first_consecutive_run(self, default_detector: ConsecutiveEpochsSleepPeriodDetector) -> None:
        """Finds first consecutive sleep run."""
        # 3 consecutive sleep at indices 5,6,7
        scores = [0, 0, 0, 0, 0, 1, 1, 1, 0, 0]

        result = default_detector._find_onset(scores, start_idx=0, end_idx=9)

        assert result == 5

    def test_respects_start_anchor(self) -> None:
        """Returns start of run with START anchor."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=3, onset_anchor=AnchorPosition.START)
        detector = ConsecutiveEpochsSleepPeriodDetector(config)
        scores = [0, 0, 1, 1, 1, 0, 0]

        result = detector._find_onset(scores, start_idx=0, end_idx=6)

        assert result == 2  # Start of run

    def test_respects_end_anchor(self) -> None:
        """Returns end of run with END anchor."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=3, onset_anchor=AnchorPosition.END)
        detector = ConsecutiveEpochsSleepPeriodDetector(config)
        scores = [0, 0, 1, 1, 1, 0, 0]

        result = detector._find_onset(scores, start_idx=0, end_idx=6)

        assert result == 4  # End of run


class TestFindOffset:
    """Tests for _find_offset method."""

    def test_finds_last_valid_offset(self, default_detector: ConsecutiveEpochsSleepPeriodDetector) -> None:
        """Finds last valid offset in range."""
        # Sleep run, then wake
        scores = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1]  # All sleep

        result = default_detector._find_offset(scores, start_idx=0, end_idx=9, onset_idx=0)

        # With offset_n=5, should find last 5 consecutive sleep
        assert result is not None

    def test_finds_wake_offset_for_tudor_locke(self) -> None:
        """Finds wake-based offset for Tudor-Locke config."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            onset_n=5,
            onset_state=EpochState.SLEEP,
            offset_n=10,
            offset_state=EpochState.WAKE,
            offset_preceding_epoch=True,
        )
        detector = ConsecutiveEpochsSleepPeriodDetector(config)

        # Sleep then exactly 10 wake epochs (no overlap for multiple runs)
        scores = [1] * 10 + [0] * 10

        result = detector._find_offset(scores, start_idx=0, end_idx=19, onset_idx=0)

        # Should return preceding sleep epoch (9) - the last sleep before wake run
        assert result == 9


class TestPresetConfigs:
    """Tests for preset configuration objects."""

    def test_consecutive_3s_5s_config(self) -> None:
        """3S/5S config has correct values."""
        assert CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG.onset_n == 3
        assert CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG.offset_n == 5
        assert CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG.onset_state == EpochState.SLEEP
        assert CONSECUTIVE_ONSET3S_OFFSET5S_CONFIG.offset_state == EpochState.SLEEP

    def test_tudor_locke_config(self) -> None:
        """Tudor-Locke config has correct values."""
        assert TUDOR_LOCKE_2014_CONFIG.onset_n == 5
        assert TUDOR_LOCKE_2014_CONFIG.offset_n == 10
        assert TUDOR_LOCKE_2014_CONFIG.onset_state == EpochState.SLEEP
        assert TUDOR_LOCKE_2014_CONFIG.offset_state == EpochState.WAKE
        assert TUDOR_LOCKE_2014_CONFIG.offset_preceding_epoch is True
        assert TUDOR_LOCKE_2014_CONFIG.min_sleep_period_minutes == 160


class TestFindSleepOnsetOffset:
    """Tests for find_sleep_onset_offset convenience function."""

    def test_works_with_default_config(self, sample_timestamps: list[datetime], sleep_pattern: list[int]) -> None:
        """Works with default configuration."""
        onset, offset = find_sleep_onset_offset(
            sleep_pattern,
            sample_timestamps[0],
            sample_timestamps[-1],
            sample_timestamps,
        )

        assert onset is not None
        assert offset is not None

    def test_works_with_custom_config(self, sample_timestamps: list[datetime], sleep_pattern: list[int]) -> None:
        """Works with custom configuration."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=2, offset_n=3)

        onset, _offset = find_sleep_onset_offset(
            sleep_pattern,
            sample_timestamps[0],
            sample_timestamps[-1],
            sample_timestamps,
            config=config,
        )

        assert onset is not None


class TestGetMarkerLabels:
    """Tests for get_marker_labels method."""

    def test_returns_tuple_of_labels(self, default_detector: ConsecutiveEpochsSleepPeriodDetector) -> None:
        """Returns tuple of onset and offset labels."""
        onset_label, offset_label = default_detector.get_marker_labels("22:00", "07:00")

        assert "22:00" in onset_label
        assert "07:00" in offset_label
        assert "Sleep Onset" in onset_label
        assert "Sleep Offset" in offset_label
