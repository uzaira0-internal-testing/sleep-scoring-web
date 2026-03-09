"""
Unit tests for NonwearAlgorithmFactory dependency injection.

Tests the factory pattern implementation for nonwear detection algorithms.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.core.algorithms import NonwearAlgorithmFactory, NonwearDetectionAlgorithm


class TestNonwearAlgorithmFactoryCreation:
    """Tests for algorithm creation via factory."""

    def test_create_choi_2011(self) -> None:
        """Test creating Choi 2011 algorithm."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        assert algorithm is not None
        assert algorithm.name == "Choi (2011)"
        assert isinstance(algorithm, NonwearDetectionAlgorithm)

    def test_create_unknown_algorithm_raises(self) -> None:
        """Test that creating unknown algorithm raises ValueError."""
        with pytest.raises(ValueError, match="Unknown nonwear algorithm"):
            NonwearAlgorithmFactory.create("nonexistent_algorithm")

    def test_create_returns_new_instance_each_time(self) -> None:
        """Test that each create call returns a new instance."""
        algo1 = NonwearAlgorithmFactory.create("choi_2011")
        algo2 = NonwearAlgorithmFactory.create("choi_2011")
        assert algo1 is not algo2


class TestNonwearAlgorithmFactoryRegistry:
    """Tests for factory registry operations."""

    def test_get_available_algorithms(self) -> None:
        """Test listing available algorithms."""
        available = NonwearAlgorithmFactory.get_available_algorithms()
        assert isinstance(available, dict)
        assert "choi_2011" in available

    def test_get_available_algorithms_returns_display_names(self) -> None:
        """Test that available algorithms dict has display names as values."""
        available = NonwearAlgorithmFactory.get_available_algorithms()
        assert available["choi_2011"] == "Choi (2011)"

    def test_is_registered_true(self) -> None:
        """Test is_registered returns True for registered algorithms."""
        assert NonwearAlgorithmFactory.is_registered("choi_2011") is True

    def test_is_registered_false(self) -> None:
        """Test is_registered returns False for unregistered algorithms."""
        assert NonwearAlgorithmFactory.is_registered("nonexistent") is False
        assert NonwearAlgorithmFactory.is_registered("") is False
        assert NonwearAlgorithmFactory.is_registered("vanhees_2013") is False

    def test_get_default_algorithm_id(self) -> None:
        """Test getting default algorithm ID."""
        default_id = NonwearAlgorithmFactory.get_default_algorithm_id()
        assert default_id == "choi_2011"
        assert NonwearAlgorithmFactory.is_registered(default_id)


class TestNonwearAlgorithmBehavior:
    """Tests for algorithm behavior from factory."""

    def test_choi_parameters(self) -> None:
        """Test Choi algorithm has correct default parameters."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        params = algorithm.get_parameters()
        assert params["min_period_length"] == 90
        assert params["spike_tolerance"] == 2
        assert params["small_window_length"] == 30
        assert params["use_vector_magnitude"] is True

    def test_algorithm_has_detect_method(self) -> None:
        """Test algorithm implements detect method."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        assert hasattr(algorithm, "detect")
        assert callable(algorithm.detect)

    def test_algorithm_has_detect_mask_method(self) -> None:
        """Test algorithm implements detect_mask method."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        assert hasattr(algorithm, "detect_mask")
        assert callable(algorithm.detect_mask)

    def test_algorithm_has_name_property(self) -> None:
        """Test algorithm has name property."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        assert hasattr(algorithm, "name")
        assert isinstance(algorithm.name, str)
        assert len(algorithm.name) > 0

    def test_algorithm_has_identifier_property(self) -> None:
        """Test algorithm has identifier property."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        assert hasattr(algorithm, "identifier")
        assert algorithm.identifier == "choi_2011"

    def test_algorithm_has_get_parameters(self) -> None:
        """Test algorithm implements get_parameters."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011")
        assert hasattr(algorithm, "get_parameters")
        params = algorithm.get_parameters()
        assert isinstance(params, dict)


class TestNonwearAlgorithmFactoryWithConfig:
    """Tests for factory with config parameter."""

    def test_create_with_none_config(self) -> None:
        """Test creating algorithm with None config."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011", config=None)
        assert algorithm is not None

    def test_create_ignores_config_for_now(self) -> None:
        """Test that config parameter is reserved for future use."""
        algorithm = NonwearAlgorithmFactory.create("choi_2011", config=None)
        assert algorithm.name == "Choi (2011)"


class TestNonwearAlgorithmProtocol:
    """Tests for NonwearDetectionAlgorithm protocol compliance."""

    def test_choi_implements_protocol(self) -> None:
        """Test that Choi algorithm implements NonwearDetectionAlgorithm protocol."""
        from sleep_scoring_app.core.algorithms import ChoiAlgorithm

        # Check protocol methods exist
        assert hasattr(ChoiAlgorithm, "detect")
        assert hasattr(ChoiAlgorithm, "name")

        # Create instance and verify
        algo = ChoiAlgorithm()
        assert isinstance(algo, NonwearDetectionAlgorithm)

    def test_choi_detect_mask_returns_list(self) -> None:
        """Test that detect_mask method returns a list."""
        import numpy as np

        algorithm = NonwearAlgorithmFactory.create("choi_2011")

        # Create minimal test data (empty should return empty list)
        activity = np.array([])

        result = algorithm.detect_mask(activity)
        assert isinstance(result, list)
