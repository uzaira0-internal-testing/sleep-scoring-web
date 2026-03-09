"""
Unit tests for AlgorithmFactory dependency injection.

Tests the factory pattern implementation for sleep scoring algorithms.
"""

from __future__ import annotations

import pytest

from sleep_scoring_app.core.algorithms import AlgorithmFactory, SleepScoringAlgorithm


class TestAlgorithmFactoryCreation:
    """Tests for algorithm creation via factory."""

    def test_create_sadeh_original(self) -> None:
        """Test creating Sadeh 1994 original algorithm."""
        algorithm = AlgorithmFactory.create("sadeh_1994_original")
        assert algorithm is not None
        assert algorithm.name == "Sadeh (1994) Original"
        assert isinstance(algorithm, SleepScoringAlgorithm)

    def test_create_sadeh_actilife(self) -> None:
        """Test creating Sadeh 1994 ActiLife algorithm."""
        algorithm = AlgorithmFactory.create("sadeh_1994_actilife")
        assert algorithm is not None
        assert algorithm.name == "Sadeh (1994) ActiLife"
        assert isinstance(algorithm, SleepScoringAlgorithm)

    def test_create_cole_kripke_actilife(self) -> None:
        """Test creating Cole-Kripke 1992 ActiLife algorithm."""
        algorithm = AlgorithmFactory.create("cole_kripke_1992_actilife")
        assert algorithm is not None
        assert algorithm.name == "Cole-Kripke (1992) ActiLife"
        assert isinstance(algorithm, SleepScoringAlgorithm)

    def test_create_cole_kripke_original(self) -> None:
        """Test creating Cole-Kripke 1992 Original algorithm."""
        algorithm = AlgorithmFactory.create("cole_kripke_1992_original")
        assert algorithm is not None
        assert algorithm.name == "Cole-Kripke (1992) Original"
        assert isinstance(algorithm, SleepScoringAlgorithm)

    def test_create_unknown_algorithm_raises(self) -> None:
        """Test that creating unknown algorithm raises ValueError."""
        with pytest.raises(ValueError, match="Unknown algorithm"):
            AlgorithmFactory.create("nonexistent_algorithm")

    def test_create_returns_new_instance_each_time(self) -> None:
        """Test that each create call returns a new instance."""
        algo1 = AlgorithmFactory.create("sadeh_1994_actilife")
        algo2 = AlgorithmFactory.create("sadeh_1994_actilife")
        assert algo1 is not algo2


class TestAlgorithmFactoryRegistry:
    """Tests for factory registry operations."""

    def test_get_available_algorithms(self) -> None:
        """Test listing available algorithms."""
        available = AlgorithmFactory.get_available_algorithms()
        assert isinstance(available, dict)
        assert "sadeh_1994_original" in available
        assert "sadeh_1994_actilife" in available
        assert "cole_kripke_1992_actilife" in available
        assert "cole_kripke_1992_original" in available

    def test_get_available_algorithms_returns_display_names(self) -> None:
        """Test that available algorithms dict has display names as values."""
        available = AlgorithmFactory.get_available_algorithms()
        assert available["sadeh_1994_original"] == "Sadeh (1994) Original"
        assert available["sadeh_1994_actilife"] == "Sadeh (1994) ActiLife"
        assert available["cole_kripke_1992_actilife"] == "Cole-Kripke (1992) ActiLife"
        assert available["cole_kripke_1992_original"] == "Cole-Kripke (1992) Original"

    def test_is_registered_true(self) -> None:
        """Test is_registered returns True for registered algorithms."""
        assert AlgorithmFactory.is_registered("sadeh_1994_original") is True
        assert AlgorithmFactory.is_registered("sadeh_1994_actilife") is True
        assert AlgorithmFactory.is_registered("cole_kripke_1992_actilife") is True
        assert AlgorithmFactory.is_registered("cole_kripke_1992_original") is True

    def test_is_registered_false(self) -> None:
        """Test is_registered returns False for unregistered algorithms."""
        assert AlgorithmFactory.is_registered("nonexistent") is False
        assert AlgorithmFactory.is_registered("") is False

    def test_get_default_algorithm_id(self) -> None:
        """Test getting default algorithm ID."""
        default_id = AlgorithmFactory.get_default_algorithm_id()
        assert default_id == "sadeh_1994_actilife"
        assert AlgorithmFactory.is_registered(default_id)


class TestAlgorithmFactoryBehavior:
    """Tests for algorithm behavior from factory."""

    def test_sadeh_original_parameters(self) -> None:
        """Test Sadeh original uses threshold 0 in parameters."""
        algorithm = AlgorithmFactory.create("sadeh_1994_original")
        params = algorithm.get_parameters()
        assert params["threshold"] == 0.0

    def test_sadeh_actilife_parameters(self) -> None:
        """Test Sadeh ActiLife uses threshold -4 in parameters."""
        algorithm = AlgorithmFactory.create("sadeh_1994_actilife")
        params = algorithm.get_parameters()
        assert params["threshold"] == -4.0

    def test_all_algorithms_have_score_method(self) -> None:
        """Test all algorithms implement score method for DataFrames."""
        for algo_id in AlgorithmFactory.get_available_algorithms():
            algorithm = AlgorithmFactory.create(algo_id)
            assert hasattr(algorithm, "score")
            assert callable(algorithm.score)

    def test_all_algorithms_have_name_property(self) -> None:
        """Test all algorithms have name property."""
        for algo_id in AlgorithmFactory.get_available_algorithms():
            algorithm = AlgorithmFactory.create(algo_id)
            assert hasattr(algorithm, "name")
            assert isinstance(algorithm.name, str)
            assert len(algorithm.name) > 0

    def test_all_algorithms_have_identifier_property(self) -> None:
        """Test all algorithms have identifier property."""
        for algo_id in AlgorithmFactory.get_available_algorithms():
            algorithm = AlgorithmFactory.create(algo_id)
            assert hasattr(algorithm, "identifier")
            assert isinstance(algorithm.identifier, str)

    def test_all_algorithms_have_get_parameters(self) -> None:
        """Test all algorithms implement get_parameters."""
        for algo_id in AlgorithmFactory.get_available_algorithms():
            algorithm = AlgorithmFactory.create(algo_id)
            assert hasattr(algorithm, "get_parameters")
            params = algorithm.get_parameters()
            assert isinstance(params, dict)


class TestAlgorithmFactoryWithConfig:
    """Tests for factory with config parameter."""

    def test_create_with_none_config(self) -> None:
        """Test creating algorithm with None config."""
        algorithm = AlgorithmFactory.create("sadeh_1994_actilife", config=None)
        assert algorithm is not None

    def test_create_ignores_config_for_now(self) -> None:
        """Test that config parameter is reserved for future use."""
        # Currently config is not used, but should not cause errors
        algorithm = AlgorithmFactory.create("sadeh_1994_actilife", config=None)
        assert algorithm.name == "Sadeh (1994) ActiLife"
