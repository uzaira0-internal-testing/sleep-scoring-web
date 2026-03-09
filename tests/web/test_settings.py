"""
Tests for the user settings API endpoints.
"""

import pytest

from sleep_scoring_web.api.settings import (
    UserSettingsResponse,
    UserSettingsUpdate,
    get_default_settings,
)
from sleep_scoring_web.schemas.enums import (
    ActivityDataPreference,
    AlgorithmType,
    SleepPeriodDetectorType,
)


class TestDefaultSettings:
    """Tests for default settings."""

    def test_get_default_settings(self):
        """Should return sensible defaults."""
        defaults = get_default_settings()

        assert defaults.sleep_detection_rule == SleepPeriodDetectorType.get_default()
        assert defaults.night_start_hour == "21:00"
        assert defaults.night_end_hour == "09:00"
        assert defaults.device_preset == "actigraph"
        assert defaults.epoch_length_seconds == 60
        assert defaults.skip_rows == 10
        assert defaults.preferred_display_column == ActivityDataPreference.AXIS_Y
        assert defaults.view_mode_hours == 24
        assert defaults.default_algorithm == AlgorithmType.get_default()
        assert defaults.extra_settings == {}

    def test_default_algorithm_is_sadeh(self):
        """Default algorithm should be Sadeh ActiLife."""
        defaults = get_default_settings()
        assert defaults.default_algorithm == AlgorithmType.SADEH_1994_ACTILIFE

    def test_default_epoch_is_60(self):
        """Default epoch length should be 60 seconds."""
        defaults = get_default_settings()
        assert defaults.epoch_length_seconds == 60


class TestUserSettingsResponse:
    """Tests for UserSettingsResponse model."""

    def test_response_all_none(self):
        """Response should work with all None values."""
        response = UserSettingsResponse()
        assert response.sleep_detection_rule is None
        assert response.night_start_hour is None
        assert response.device_preset is None
        assert response.extra_settings is None

    def test_response_with_values(self):
        """Response should accept all values."""
        response = UserSettingsResponse(
            sleep_detection_rule=SleepPeriodDetectorType.TUDOR_LOCKE_2014,
            night_start_hour="22:00",
            night_end_hour="08:00",
            device_preset="actiwatch",
            epoch_length_seconds=30,
            skip_rows=5,
            preferred_display_column=ActivityDataPreference.VECTOR_MAGNITUDE,
            view_mode_hours=48,
            default_algorithm=AlgorithmType.COLE_KRIPKE_1992_ACTILIFE,
            extra_settings={"custom_key": "custom_value"},
        )
        assert response.sleep_detection_rule == SleepPeriodDetectorType.TUDOR_LOCKE_2014
        assert response.night_start_hour == "22:00"
        assert response.device_preset == "actiwatch"
        assert response.epoch_length_seconds == 30
        assert response.view_mode_hours == 48
        assert response.extra_settings == {"custom_key": "custom_value"}


class TestUserSettingsUpdate:
    """Tests for UserSettingsUpdate model."""

    def test_update_partial(self):
        """Update should work with partial data."""
        update = UserSettingsUpdate(
            night_start_hour="23:00",
        )
        assert update.night_start_hour == "23:00"
        assert update.night_end_hour is None
        assert update.device_preset is None

    def test_update_full(self):
        """Update should accept all fields."""
        update = UserSettingsUpdate(
            sleep_detection_rule=SleepPeriodDetectorType.CONSECUTIVE_ONSET5S_OFFSET10S,
            night_start_hour="20:00",
            night_end_hour="10:00",
            device_preset="geneactiv",
            epoch_length_seconds=15,
            skip_rows=0,
            preferred_display_column=ActivityDataPreference.AXIS_Y,
            view_mode_hours=24,
            default_algorithm=AlgorithmType.SADEH_1994_ORIGINAL,
            extra_settings={"theme": "dark"},
        )
        assert update.sleep_detection_rule == SleepPeriodDetectorType.CONSECUTIVE_ONSET5S_OFFSET10S
        assert update.epoch_length_seconds == 15
        assert update.skip_rows == 0
        assert update.extra_settings == {"theme": "dark"}

    def test_update_extra_settings_json(self):
        """Extra settings should support complex JSON."""
        update = UserSettingsUpdate(
            extra_settings={
                "theme": "dark",
                "fontSize": 14,
                "features": {
                    "autoSave": True,
                    "showGrid": False,
                },
                "colors": ["#ff0000", "#00ff00"],
            }
        )
        assert update.extra_settings["theme"] == "dark"
        assert update.extra_settings["features"]["autoSave"] is True


class TestSettingsEnums:
    """Tests for settings enum values."""

    def test_sleep_detection_rules(self):
        """Should have valid sleep detection rules."""
        rules = [
            SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S,
            SleepPeriodDetectorType.CONSECUTIVE_ONSET5S_OFFSET10S,
            SleepPeriodDetectorType.TUDOR_LOCKE_2014,
        ]
        assert len(rules) == 3
        assert SleepPeriodDetectorType.get_default() in rules

    def test_algorithm_types(self):
        """Should have valid algorithm types."""
        algorithms = [
            AlgorithmType.SADEH_1994_ORIGINAL,
            AlgorithmType.SADEH_1994_ACTILIFE,
            AlgorithmType.COLE_KRIPKE_1992_ORIGINAL,
            AlgorithmType.COLE_KRIPKE_1992_ACTILIFE,
            AlgorithmType.MANUAL,
        ]
        assert len(algorithms) == 5
        assert AlgorithmType.get_default() in algorithms

    def test_activity_preferences(self):
        """Should have valid activity preferences."""
        prefs = [
            ActivityDataPreference.AXIS_Y,
            ActivityDataPreference.VECTOR_MAGNITUDE,
        ]
        assert len(prefs) == 2


class TestSettingsViewModes:
    """Tests for view mode settings."""

    def test_valid_view_modes(self):
        """Should accept 24 and 48 hour view modes."""
        response_24 = UserSettingsResponse(view_mode_hours=24)
        response_48 = UserSettingsResponse(view_mode_hours=48)

        assert response_24.view_mode_hours == 24
        assert response_48.view_mode_hours == 48

    def test_default_view_mode(self):
        """Default view mode should be 24 hours."""
        defaults = get_default_settings()
        assert defaults.view_mode_hours == 24
