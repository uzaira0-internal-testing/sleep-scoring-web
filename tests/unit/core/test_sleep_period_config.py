"""
Tests for sleep period detection configuration dataclasses.

Tests EpochState, AnchorPosition, and ConsecutiveEpochsSleepPeriodDetectorConfig.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.core.algorithms.sleep_period.config import (
    AnchorPosition,
    ConsecutiveEpochsSleepPeriodDetectorConfig,
    EpochState,
)


class TestEpochState:
    """Tests for EpochState enum."""

    def test_sleep_value(self) -> None:
        """SLEEP has correct string value."""
        assert EpochState.SLEEP == "sleep"
        assert EpochState.SLEEP.value == "sleep"

    def test_wake_value(self) -> None:
        """WAKE has correct string value."""
        assert EpochState.WAKE == "wake"
        assert EpochState.WAKE.value == "wake"

    def test_is_str_enum(self) -> None:
        """Can use as string."""
        state = EpochState.SLEEP

        assert f"State is {state}" == "State is sleep"


class TestAnchorPosition:
    """Tests for AnchorPosition enum."""

    def test_start_value(self) -> None:
        """START has correct string value."""
        assert AnchorPosition.START == "start"
        assert AnchorPosition.START.value == "start"

    def test_end_value(self) -> None:
        """END has correct string value."""
        assert AnchorPosition.END == "end"
        assert AnchorPosition.END.value == "end"


class TestConsecutiveEpochsSleepPeriodDetectorConfig:
    """Tests for ConsecutiveEpochsSleepPeriodDetectorConfig dataclass."""

    def test_default_values(self) -> None:
        """Has correct default values."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig()

        assert config.onset_n == 3
        assert config.onset_state == EpochState.SLEEP
        assert config.onset_anchor == AnchorPosition.START
        assert config.offset_n == 5
        assert config.offset_state == EpochState.SLEEP
        assert config.offset_anchor == AnchorPosition.END
        assert config.offset_preceding_epoch is False
        assert config.search_extension_minutes == 5
        assert config.min_sleep_period_minutes is None
        assert config.max_sleep_period_minutes == 1440

    def test_custom_onset_values(self) -> None:
        """Accepts custom onset values."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            onset_n=7,
            onset_state=EpochState.WAKE,
            onset_anchor=AnchorPosition.END,
        )

        assert config.onset_n == 7
        assert config.onset_state == EpochState.WAKE
        assert config.onset_anchor == AnchorPosition.END

    def test_custom_offset_values(self) -> None:
        """Accepts custom offset values."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            offset_n=10,
            offset_state=EpochState.WAKE,
            offset_anchor=AnchorPosition.START,
            offset_preceding_epoch=True,
        )

        assert config.offset_n == 10
        assert config.offset_state == EpochState.WAKE
        assert config.offset_anchor == AnchorPosition.START
        assert config.offset_preceding_epoch is True

    def test_is_frozen(self) -> None:
        """Config is frozen (immutable)."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig()

        with pytest.raises(AttributeError):
            config.onset_n = 10  # type: ignore

    def test_custom_search_extension(self) -> None:
        """Accepts custom search extension."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(search_extension_minutes=15)

        assert config.search_extension_minutes == 15

    def test_custom_period_constraints(self) -> None:
        """Accepts custom period length constraints."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            min_sleep_period_minutes=120,
            max_sleep_period_minutes=720,
        )

        assert config.min_sleep_period_minutes == 120
        assert config.max_sleep_period_minutes == 720


class TestConfigEquality:
    """Tests for config equality comparison."""

    def test_equal_configs(self) -> None:
        """Equal configs compare equal."""
        config1 = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=5, offset_n=10)
        config2 = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=5, offset_n=10)

        assert config1 == config2

    def test_different_configs(self) -> None:
        """Different configs compare not equal."""
        config1 = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=3)
        config2 = ConsecutiveEpochsSleepPeriodDetectorConfig(onset_n=5)

        assert config1 != config2

    def test_hashable(self) -> None:
        """Config is hashable (can be dict key)."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig()

        config_dict = {config: "value"}

        assert config_dict[config] == "value"


class TestConfigUseCases:
    """Tests for common config use cases."""

    def test_traditional_35_config(self) -> None:
        """Creates traditional 3/5 rule config."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            onset_n=3,
            onset_state=EpochState.SLEEP,
            onset_anchor=AnchorPosition.START,
            offset_n=5,
            offset_state=EpochState.SLEEP,
            offset_anchor=AnchorPosition.END,
        )

        # Onset: First epoch of 3 consecutive sleep
        assert config.onset_n == 3
        assert config.onset_state == EpochState.SLEEP
        # Offset: Last epoch of 5 consecutive sleep
        assert config.offset_n == 5
        assert config.offset_state == EpochState.SLEEP

    def test_tudor_locke_style_config(self) -> None:
        """Creates Tudor-Locke style config."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            onset_n=5,
            onset_state=EpochState.SLEEP,
            onset_anchor=AnchorPosition.START,
            offset_n=10,
            offset_state=EpochState.WAKE,
            offset_anchor=AnchorPosition.START,
            offset_preceding_epoch=True,
            min_sleep_period_minutes=160,
        )

        # Onset: First epoch of 5 consecutive sleep
        assert config.onset_n == 5
        # Offset: Epoch BEFORE 10 consecutive wake
        assert config.offset_n == 10
        assert config.offset_state == EpochState.WAKE
        assert config.offset_preceding_epoch is True
        # Minimum period constraint
        assert config.min_sleep_period_minutes == 160

    def test_strict_detection_config(self) -> None:
        """Creates stricter detection config."""
        config = ConsecutiveEpochsSleepPeriodDetectorConfig(
            onset_n=10,
            offset_n=15,
            search_extension_minutes=0,  # No extension
        )

        assert config.onset_n == 10
        assert config.offset_n == 15
        assert config.search_extension_minutes == 0
