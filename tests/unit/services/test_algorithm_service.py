#!/usr/bin/env python3
"""
Unit tests for AlgorithmService.

Tests the service layer that provides access to sleep scoring algorithms,
nonwear algorithms, and sleep period detectors via factory pattern.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.services.algorithm_service import AlgorithmService, get_algorithm_service


class TestAlgorithmService:
    """Tests for AlgorithmService class."""

    @pytest.fixture
    def service(self):
        """Create AlgorithmService instance."""
        return AlgorithmService()

    @pytest.fixture
    def mock_sleep_factory(self):
        """Create mock sleep/wake algorithm factory."""
        factory = MagicMock()
        factory.get_available_algorithms.return_value = {
            "sadeh_1994_actilife": "Sadeh 1994 (ActiLife)",
            "cole_kripke_1992": "Cole-Kripke 1992",
        }
        factory.get_default_algorithm_id.return_value = "sadeh_1994_actilife"
        mock_algo = MagicMock()
        mock_algo.name = "Sadeh 1994"
        mock_algo.identifier = "sadeh_1994_actilife"
        mock_algo.description = "Sadeh algorithm"
        mock_algo.epoch_length = 60
        mock_algo.requires_raw_data = False
        factory.create.return_value = mock_algo
        return factory

    @pytest.fixture
    def mock_nonwear_factory(self):
        """Create mock nonwear algorithm factory."""
        factory = MagicMock()
        factory.get_available_algorithms.return_value = {
            "choi_2011": "Choi 2011",
            "van_hees_2023": "van Hees 2023",
        }
        factory.get_algorithms_for_paradigm.return_value = {"choi_2011": "Choi 2011"}
        factory.get_default_algorithm_id.return_value = "choi_2011"
        mock_algo = MagicMock()
        mock_algo.name = "Choi 2011"
        mock_algo.identifier = "choi_2011"
        factory.create.return_value = mock_algo
        return factory

    @pytest.fixture
    def mock_sleep_period_factory(self):
        """Create mock sleep period detector factory."""
        factory = MagicMock()
        factory.get_available_detectors.return_value = {
            "consecutive_onset3s_offset5s": "Consecutive (3S/5S)",
            "hdcza": "HDCZA",
        }
        factory.get_detectors_for_paradigm.return_value = {"consecutive_onset3s_offset5s": "Consecutive (3S/5S)"}
        factory.get_default_detector_id.return_value = "consecutive_onset3s_offset5s"
        mock_detector = MagicMock()
        mock_detector.name = "Consecutive (3S/5S)"
        mock_detector.identifier = "consecutive_onset3s_offset5s"
        factory.create.return_value = mock_detector
        return factory

    # === Lazy Loading Tests ===

    def test_lazy_load_sleep_wake_factory(self, service):
        """Test lazy loading of sleep/wake factory."""
        assert service._sleep_wake_factory is None

        # Call the actual method - lazy loading imports the real factory
        factory = service._get_sleep_wake_factory()
        from sleep_scoring_app.core.algorithms.sleep_wake.factory import AlgorithmFactory

        assert factory is AlgorithmFactory
        assert service._sleep_wake_factory is AlgorithmFactory

    def test_lazy_load_nonwear_factory(self, service):
        """Test lazy loading of nonwear factory."""
        assert service._nonwear_factory is None

        # Call the actual method - lazy loading imports the real factory
        factory = service._get_nonwear_factory()
        from sleep_scoring_app.core.algorithms.nonwear.factory import NonwearAlgorithmFactory

        assert factory is NonwearAlgorithmFactory
        assert service._nonwear_factory is NonwearAlgorithmFactory

    def test_lazy_load_sleep_period_factory(self, service):
        """Test lazy loading of sleep period factory."""
        assert service._sleep_period_factory is None

        # Call the actual method - lazy loading imports the real factory
        factory = service._get_sleep_period_factory()
        from sleep_scoring_app.core.algorithms.sleep_period.factory import SleepPeriodDetectorFactory

        assert factory is SleepPeriodDetectorFactory
        assert service._sleep_period_factory is SleepPeriodDetectorFactory

    def test_lazy_load_caching(self, service):
        """Test that factory instances are cached after first load."""
        # First call loads the factory
        factory1 = service._get_sleep_wake_factory()
        factory2 = service._get_sleep_wake_factory()
        assert factory1 is factory2
        # Factory should only be loaded once
        assert service._sleep_wake_factory is factory1

    # === Sleep/Wake Algorithm Tests ===

    def test_get_available_sleep_algorithms(self, service, mock_sleep_factory):
        """Test getting available sleep algorithms."""
        service._sleep_wake_factory = mock_sleep_factory
        algorithms = service.get_available_sleep_algorithms()

        assert algorithms == {
            "sadeh_1994_actilife": "Sadeh 1994 (ActiLife)",
            "cole_kripke_1992": "Cole-Kripke 1992",
        }
        mock_sleep_factory.get_available_algorithms.assert_called_once()

    def test_create_sleep_algorithm(self, service, mock_sleep_factory):
        """Test creating sleep algorithm instance."""
        service._sleep_wake_factory = mock_sleep_factory
        algorithm = service.create_sleep_algorithm("sadeh_1994_actilife")

        assert algorithm.name == "Sadeh 1994"
        mock_sleep_factory.create.assert_called_once_with("sadeh_1994_actilife", None)

    def test_create_sleep_algorithm_with_config(self, service, mock_sleep_factory):
        """Test creating sleep algorithm with config."""
        service._sleep_wake_factory = mock_sleep_factory
        mock_config = MagicMock()

        service.create_sleep_algorithm("sadeh_1994_actilife", config=mock_config)

        mock_sleep_factory.create.assert_called_once_with("sadeh_1994_actilife", mock_config)

    def test_get_default_sleep_algorithm_id(self, service, mock_sleep_factory):
        """Test getting default sleep algorithm ID."""
        service._sleep_wake_factory = mock_sleep_factory
        algorithm_id = service.get_default_sleep_algorithm_id()

        assert algorithm_id == "sadeh_1994_actilife"
        mock_sleep_factory.get_default_algorithm_id.assert_called_once()

    # === Nonwear Algorithm Tests ===

    def test_get_available_nonwear_algorithms(self, service, mock_nonwear_factory):
        """Test getting available nonwear algorithms."""
        service._nonwear_factory = mock_nonwear_factory
        algorithms = service.get_available_nonwear_algorithms()

        assert algorithms == {
            "choi_2011": "Choi 2011",
            "van_hees_2023": "van Hees 2023",
        }
        mock_nonwear_factory.get_available_algorithms.assert_called_once()

    def test_get_nonwear_algorithms_for_paradigm_epoch(self, service, mock_nonwear_factory):
        """Test getting nonwear algorithms for epoch-based data."""
        service._nonwear_factory = mock_nonwear_factory
        algorithms = service.get_nonwear_algorithms_for_paradigm("epoch_based")

        assert algorithms == {"choi_2011": "Choi 2011"}
        mock_nonwear_factory.get_algorithms_for_paradigm.assert_called_once_with("epoch_based")

    def test_get_nonwear_algorithms_for_paradigm_raw(self, service, mock_nonwear_factory):
        """Test getting nonwear algorithms for raw data."""
        service._nonwear_factory = mock_nonwear_factory
        mock_nonwear_factory.get_algorithms_for_paradigm.return_value = {"van_hees_2023": "van Hees 2023"}

        algorithms = service.get_nonwear_algorithms_for_paradigm("raw_accelerometer")

        assert algorithms == {"van_hees_2023": "van Hees 2023"}
        mock_nonwear_factory.get_algorithms_for_paradigm.assert_called_once_with("raw_accelerometer")

    def test_create_nonwear_algorithm(self, service, mock_nonwear_factory):
        """Test creating nonwear algorithm instance."""
        service._nonwear_factory = mock_nonwear_factory
        algorithm = service.create_nonwear_algorithm("choi_2011")

        assert algorithm.identifier == "choi_2011"
        mock_nonwear_factory.create.assert_called_once_with("choi_2011", None)

    def test_create_nonwear_algorithm_with_config(self, service, mock_nonwear_factory):
        """Test creating nonwear algorithm with config."""
        service._nonwear_factory = mock_nonwear_factory
        mock_config = MagicMock()

        service.create_nonwear_algorithm("choi_2011", config=mock_config)

        mock_nonwear_factory.create.assert_called_once_with("choi_2011", mock_config)

    def test_get_default_nonwear_algorithm_id(self, service, mock_nonwear_factory):
        """Test getting default nonwear algorithm ID."""
        service._nonwear_factory = mock_nonwear_factory
        algorithm_id = service.get_default_nonwear_algorithm_id()

        assert algorithm_id == "choi_2011"
        mock_nonwear_factory.get_default_algorithm_id.assert_called_once()

    # === Sleep Period Detector Tests ===

    def test_get_available_sleep_period_detectors(self, service, mock_sleep_period_factory):
        """Test getting available sleep period detectors."""
        service._sleep_period_factory = mock_sleep_period_factory
        detectors = service.get_available_sleep_period_detectors()

        assert detectors == {
            "consecutive_onset3s_offset5s": "Consecutive (3S/5S)",
            "hdcza": "HDCZA",
        }
        mock_sleep_period_factory.get_available_detectors.assert_called_once()

    def test_get_sleep_period_detectors_for_paradigm(self, service, mock_sleep_period_factory):
        """Test getting sleep period detectors for specific paradigm."""
        service._sleep_period_factory = mock_sleep_period_factory
        detectors = service.get_sleep_period_detectors_for_paradigm("epoch_based")

        assert detectors == {"consecutive_onset3s_offset5s": "Consecutive (3S/5S)"}
        mock_sleep_period_factory.get_detectors_for_paradigm.assert_called_once_with("epoch_based")

    def test_create_sleep_period_detector(self, service, mock_sleep_period_factory):
        """Test creating sleep period detector instance."""
        service._sleep_period_factory = mock_sleep_period_factory
        detector = service.create_sleep_period_detector("consecutive_onset3s_offset5s")

        assert detector.identifier == "consecutive_onset3s_offset5s"
        mock_sleep_period_factory.create.assert_called_once_with("consecutive_onset3s_offset5s")

    def test_get_default_sleep_period_detector_id(self, service, mock_sleep_period_factory):
        """Test getting default sleep period detector ID."""
        service._sleep_period_factory = mock_sleep_period_factory
        detector_id = service.get_default_sleep_period_detector_id()

        assert detector_id == "consecutive_onset3s_offset5s"
        mock_sleep_period_factory.get_default_detector_id.assert_called_once()

    # === Algorithm Information Tests ===

    def test_get_algorithm_description(self, service, mock_sleep_factory):
        """Test getting algorithm description."""
        service._sleep_wake_factory = mock_sleep_factory
        description = service.get_algorithm_description("sadeh_1994_actilife")

        assert description == "Sadeh algorithm"
        mock_sleep_factory.create.assert_called_once()

    def test_get_algorithm_description_no_description_attribute(self, service, mock_sleep_factory):
        """Test getting description when algorithm has no description attribute."""
        service._sleep_wake_factory = mock_sleep_factory
        mock_algorithm = MagicMock(spec=[])  # No description attribute
        mock_sleep_factory.create.return_value = mock_algorithm

        description = service.get_algorithm_description("test_algorithm")

        assert description == "test_algorithm"  # Falls back to ID

    def test_get_algorithm_description_exception(self, service, mock_sleep_factory):
        """Test getting description when creation fails."""
        service._sleep_wake_factory = mock_sleep_factory
        mock_sleep_factory.create.side_effect = Exception("Creation failed")

        description = service.get_algorithm_description("invalid_algorithm")

        assert description == "invalid_algorithm"  # Falls back to ID

    def test_get_algorithm_requirements(self, service, mock_sleep_factory):
        """Test getting algorithm requirements."""
        service._sleep_wake_factory = mock_sleep_factory
        requirements = service.get_algorithm_requirements("sadeh_1994_actilife")

        assert requirements == {"epoch_length": 60, "requires_raw_data": False}
        mock_sleep_factory.create.assert_called_once()

    def test_get_algorithm_requirements_missing_attributes(self, service, mock_sleep_factory):
        """Test getting requirements when algorithm has no attributes."""
        service._sleep_wake_factory = mock_sleep_factory
        mock_algorithm = MagicMock(spec=[])
        mock_sleep_factory.create.return_value = mock_algorithm

        requirements = service.get_algorithm_requirements("test_algorithm")

        # Should return defaults
        assert requirements == {"epoch_length": 60, "requires_raw_data": False}

    def test_get_algorithm_requirements_exception(self, service, mock_sleep_factory):
        """Test getting requirements when creation fails."""
        service._sleep_wake_factory = mock_sleep_factory
        mock_sleep_factory.create.side_effect = Exception("Creation failed")

        requirements = service.get_algorithm_requirements("invalid_algorithm")

        # Should return defaults
        assert requirements == {"epoch_length": 60, "requires_raw_data": False}

    def test_is_algorithm_available_true(self, service, mock_sleep_factory):
        """Test checking if algorithm is available (exists)."""
        service._sleep_wake_factory = mock_sleep_factory
        is_available = service.is_algorithm_available("sadeh_1994_actilife")

        assert is_available is True

    def test_is_algorithm_available_false(self, service, mock_sleep_factory):
        """Test checking if algorithm is available (does not exist)."""
        service._sleep_wake_factory = mock_sleep_factory
        is_available = service.is_algorithm_available("nonexistent_algorithm")

        assert is_available is False


class TestAlgorithmServiceSingleton:
    """Tests for AlgorithmService singleton pattern."""

    def test_get_algorithm_service_creates_instance(self):
        """Test that get_algorithm_service creates instance on first call."""
        # Reset singleton
        import sleep_scoring_app.services.algorithm_service as service_module

        service_module._algorithm_service_instance = None

        service = get_algorithm_service()
        assert isinstance(service, AlgorithmService)

    def test_get_algorithm_service_returns_same_instance(self):
        """Test that get_algorithm_service returns same instance on subsequent calls."""
        service1 = get_algorithm_service()
        service2 = get_algorithm_service()

        assert service1 is service2

    def test_get_algorithm_service_singleton_independence(self):
        """Test that singleton and direct instantiation are independent."""
        singleton = get_algorithm_service()
        direct = AlgorithmService()

        assert singleton is not direct
