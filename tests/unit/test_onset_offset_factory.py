"""
Unit tests for SleepPeriodDetectorFactory dependency injection.

Tests the factory pattern implementation for sleep period detection.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.core.algorithms import SleepPeriodDetector, SleepPeriodDetectorFactory


class TestSleepPeriodDetectorFactoryCreation:
    """Tests for detector creation via factory."""

    def test_create_consecutive_onset3s_offset5s(self) -> None:
        """Test creating consecutive 3s/5s detector."""
        detector = SleepPeriodDetectorFactory.create("consecutive_onset3s_offset5s")
        assert detector is not None
        assert detector.name == "Consecutive 3S/5S"
        assert isinstance(detector, SleepPeriodDetector)

    def test_create_consecutive_onset5s_offset10s(self) -> None:
        """Test creating consecutive 5s/10s detector."""
        detector = SleepPeriodDetectorFactory.create("consecutive_onset5s_offset10s")
        assert detector is not None
        assert detector.name == "Consecutive 5S/10S"
        assert isinstance(detector, SleepPeriodDetector)

    def test_create_tudor_locke_2014(self) -> None:
        """Test creating Tudor-Locke 2014 detector."""
        detector = SleepPeriodDetectorFactory.create("tudor_locke_2014")
        assert detector is not None
        assert detector.name == "Tudor-Locke (2014)"
        assert isinstance(detector, SleepPeriodDetector)

    def test_create_unknown_detector_raises(self) -> None:
        """Test that creating unknown detector raises ValueError."""
        with pytest.raises(ValueError, match="Unknown sleep period detector"):
            SleepPeriodDetectorFactory.create("nonexistent_detector")

    def test_create_returns_new_instance_each_time(self) -> None:
        """Test that each create call returns a new instance."""
        detector1 = SleepPeriodDetectorFactory.create("consecutive_onset3s_offset5s")
        detector2 = SleepPeriodDetectorFactory.create("consecutive_onset3s_offset5s")
        assert detector1 is not detector2


class TestSleepPeriodDetectorFactoryRegistry:
    """Tests for factory registry operations."""

    def test_get_available_detectors(self) -> None:
        """Test listing available detectors."""
        available = SleepPeriodDetectorFactory.get_available_detectors()
        assert isinstance(available, dict)
        assert "consecutive_onset3s_offset5s" in available
        assert "consecutive_onset5s_offset10s" in available
        assert "tudor_locke_2014" in available

    def test_get_available_detectors_returns_display_names(self) -> None:
        """Test that available detectors dict has display names as values."""
        available = SleepPeriodDetectorFactory.get_available_detectors()
        assert available["consecutive_onset3s_offset5s"] == "Consecutive 3S/5S"
        assert available["consecutive_onset5s_offset10s"] == "Consecutive 5S/10S"
        assert available["tudor_locke_2014"] == "Tudor-Locke (2014)"

    def test_get_default_detector_id(self) -> None:
        """Test getting default detector ID."""
        default_id = SleepPeriodDetectorFactory.get_default_detector_id()
        assert default_id == "consecutive_onset3s_offset5s"

    def test_backward_compat_get_available_rules(self) -> None:
        """Test backward compatibility alias."""
        available = SleepPeriodDetectorFactory.get_available_rules()
        assert "consecutive_onset3s_offset5s" in available

    def test_backward_compat_get_default_rule_id(self) -> None:
        """Test backward compatibility alias."""
        default_id = SleepPeriodDetectorFactory.get_default_rule_id()
        assert default_id == "consecutive_onset3s_offset5s"


class TestSleepPeriodDetectorBehavior:
    """Tests for detector behavior from factory."""

    def test_consecutive_onset3s_offset5s_parameters(self) -> None:
        """Test consecutive 3s/5s detector has correct parameters."""
        detector = SleepPeriodDetectorFactory.create("consecutive_onset3s_offset5s")
        params = detector.get_parameters()
        assert params["onset_n"] == 3
        assert params["onset_state"] == "sleep"
        assert params["offset_n"] == 5
        assert params["offset_state"] == "sleep"

    def test_consecutive_onset5s_offset10s_parameters(self) -> None:
        """Test consecutive 5s/10s detector has correct parameters."""
        detector = SleepPeriodDetectorFactory.create("consecutive_onset5s_offset10s")
        params = detector.get_parameters()
        assert params["onset_n"] == 5
        assert params["onset_state"] == "sleep"
        assert params["offset_n"] == 10
        assert params["offset_state"] == "sleep"

    def test_tudor_locke_parameters(self) -> None:
        """Test Tudor-Locke detector has correct parameters."""
        detector = SleepPeriodDetectorFactory.create("tudor_locke_2014")
        params = detector.get_parameters()
        assert params["onset_n"] == 5
        assert params["onset_state"] == "sleep"
        assert params["offset_n"] == 10
        assert params["offset_state"] == "wake"
        assert params["offset_preceding_epoch"] is True

    def test_all_detectors_have_apply_rules_method(self) -> None:
        """Test all detectors implement apply_rules method."""
        for detector_id in SleepPeriodDetectorFactory.get_available_detectors():
            detector = SleepPeriodDetectorFactory.create(detector_id)
            assert hasattr(detector, "apply_rules")
            assert callable(detector.apply_rules)

    def test_all_detectors_have_name_property(self) -> None:
        """Test all detectors have name property."""
        for detector_id in SleepPeriodDetectorFactory.get_available_detectors():
            detector = SleepPeriodDetectorFactory.create(detector_id)
            assert hasattr(detector, "name")
            assert isinstance(detector.name, str)
            assert len(detector.name) > 0

    def test_all_detectors_have_identifier_property(self) -> None:
        """Test all detectors have identifier property."""
        for detector_id in SleepPeriodDetectorFactory.get_available_detectors():
            detector = SleepPeriodDetectorFactory.create(detector_id)
            assert hasattr(detector, "identifier")
            assert isinstance(detector.identifier, str)

    def test_all_detectors_have_description_property(self) -> None:
        """Test all detectors have description property."""
        for detector_id in SleepPeriodDetectorFactory.get_available_detectors():
            detector = SleepPeriodDetectorFactory.create(detector_id)
            assert hasattr(detector, "description")
            assert isinstance(detector.description, str)

    def test_all_detectors_have_get_parameters(self) -> None:
        """Test all detectors implement get_parameters."""
        for detector_id in SleepPeriodDetectorFactory.get_available_detectors():
            detector = SleepPeriodDetectorFactory.create(detector_id)
            assert hasattr(detector, "get_parameters")
            params = detector.get_parameters()
            assert isinstance(params, dict)


class TestSleepPeriodDetectorFactoryWithConfig:
    """Tests for factory with config parameter."""

    def test_create_with_none_config(self) -> None:
        """Test creating detector with None config."""
        detector = SleepPeriodDetectorFactory.create("consecutive_onset3s_offset5s", config=None)
        assert detector is not None

    def test_create_tudor_locke_with_none_config(self) -> None:
        """Test creating Tudor-Locke with None config."""
        detector = SleepPeriodDetectorFactory.create("tudor_locke_2014", config=None)
        assert detector.name == "Tudor-Locke (2014)"
