#!/usr/bin/env python3
"""
Algorithm Service for Sleep Scoring Application.

Provides a service layer abstraction over algorithm factories.
UI components should use this service instead of importing
algorithm factories directly.

This follows the Dependency Inversion Principle - UI depends on
the service abstraction, not concrete algorithm implementations.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sleep_scoring_app.core.algorithms.nonwear.protocol import NonwearDetectionAlgorithm
    from sleep_scoring_app.core.algorithms.sleep_period.protocol import SleepPeriodDetector
    from sleep_scoring_app.core.algorithms.sleep_wake.protocol import SleepScoringAlgorithm
    from sleep_scoring_app.core.dataclasses import AppConfig

logger = logging.getLogger(__name__)


class AlgorithmService:
    """
    Service for accessing sleep scoring algorithms.

    Wraps the algorithm factories to provide a clean interface
    for UI components without exposing implementation details.
    """

    def __init__(self) -> None:
        """Initialize the algorithm service."""
        # Lazy import factories to avoid circular dependencies
        self._sleep_wake_factory = None
        self._nonwear_factory = None
        self._sleep_period_factory = None

    def _get_sleep_wake_factory(self) -> type:
        """Lazy load the sleep/wake algorithm factory."""
        if self._sleep_wake_factory is None:
            from sleep_scoring_app.core.algorithms.sleep_wake.factory import AlgorithmFactory

            self._sleep_wake_factory = AlgorithmFactory
        return self._sleep_wake_factory

    def _get_nonwear_factory(self) -> type:
        """Lazy load the nonwear algorithm factory."""
        if self._nonwear_factory is None:
            from sleep_scoring_app.core.algorithms.nonwear.factory import NonwearAlgorithmFactory

            self._nonwear_factory = NonwearAlgorithmFactory
        return self._nonwear_factory

    def _get_sleep_period_factory(self) -> type:
        """Lazy load the sleep period detector factory."""
        if self._sleep_period_factory is None:
            from sleep_scoring_app.core.algorithms.sleep_period.factory import SleepPeriodDetectorFactory

            self._sleep_period_factory = SleepPeriodDetectorFactory
        return self._sleep_period_factory

    def get_available_sleep_algorithms(self) -> dict[str, str]:
        """
        Get available sleep/wake algorithms.

        Returns:
            Dictionary mapping algorithm_id to display name

        """
        factory = self._get_sleep_wake_factory()
        return factory.get_available_algorithms()

    def create_sleep_algorithm(
        self,
        algorithm_id: str,
        config: AppConfig | None = None,
    ) -> SleepScoringAlgorithm:
        """
        Create a sleep/wake algorithm instance.

        Args:
            algorithm_id: Algorithm identifier (e.g., "sadeh_1994_actilife")
            config: Optional application config

        Returns:
            Configured algorithm instance

        """
        factory = self._get_sleep_wake_factory()
        return factory.create(algorithm_id, config)

    def get_default_sleep_algorithm_id(self) -> str:
        """Get the default sleep/wake algorithm ID."""
        factory = self._get_sleep_wake_factory()
        return factory.get_default_algorithm_id()

    def get_available_nonwear_algorithms(self) -> dict[str, str]:
        """
        Get available nonwear detection algorithms.

        Returns:
            Dictionary mapping algorithm_id to display name

        """
        factory = self._get_nonwear_factory()
        return factory.get_available_algorithms()

    def get_nonwear_algorithms_for_paradigm(self, paradigm: str) -> dict[str, str]:
        """
        Get nonwear algorithms compatible with a specific data paradigm.

        Args:
            paradigm: Data paradigm ("epoch_based" or "raw_accelerometer")

        Returns:
            Dictionary mapping algorithm_id to display name

        """
        factory = self._get_nonwear_factory()
        return factory.get_algorithms_for_paradigm(paradigm)

    def create_nonwear_algorithm(
        self,
        algorithm_id: str,
        config: AppConfig | None = None,
    ) -> NonwearDetectionAlgorithm:
        """
        Create a nonwear detection algorithm instance.

        Args:
            algorithm_id: Algorithm identifier (e.g., "choi_2011")
            config: Optional application config

        Returns:
            Configured algorithm instance

        """
        factory = self._get_nonwear_factory()
        return factory.create(algorithm_id, config)

    def get_default_nonwear_algorithm_id(self) -> str:
        """Get the default nonwear algorithm ID."""
        factory = self._get_nonwear_factory()
        return factory.get_default_algorithm_id()

    def get_available_sleep_period_detectors(self) -> dict[str, str]:
        """
        Get available sleep period detectors.

        Returns:
            Dictionary mapping detector_id to display name

        """
        factory = self._get_sleep_period_factory()
        return factory.get_available_detectors()

    def get_sleep_period_detectors_for_paradigm(self, paradigm: str) -> dict[str, str]:
        """
        Get sleep period detectors compatible with a specific data paradigm.

        Args:
            paradigm: Data paradigm ("epoch_based" or "raw_accelerometer")

        Returns:
            Dictionary mapping detector_id to display name

        """
        factory = self._get_sleep_period_factory()
        return factory.get_detectors_for_paradigm(paradigm)

    def create_sleep_period_detector(self, detector_id: str) -> SleepPeriodDetector:
        """
        Create a sleep period detector instance.

        Args:
            detector_id: Detector identifier (e.g., "consecutive_onset3s_offset5s")

        Returns:
            Configured detector instance

        """
        factory = self._get_sleep_period_factory()
        return factory.create(detector_id)

    def get_default_sleep_period_detector_id(self) -> str:
        """Get the default sleep period detector ID."""
        factory = self._get_sleep_period_factory()
        return factory.get_default_detector_id()

    def get_algorithm_description(self, algorithm_id: str) -> str:
        """
        Get description for an algorithm.

        Args:
            algorithm_id: The algorithm identifier

        Returns:
            Human-readable description string

        """
        try:
            algorithm = self.create_sleep_algorithm(algorithm_id)
            return getattr(algorithm, "description", algorithm_id)
        except Exception as e:
            logger.debug("Failed to get description for algorithm %s: %s", algorithm_id, e)
            return algorithm_id

    def get_algorithm_requirements(self, algorithm_id: str) -> dict[str, Any]:
        """
        Get data requirements for an algorithm.

        Args:
            algorithm_id: The algorithm identifier

        Returns:
            Dictionary of algorithm requirements

        """
        try:
            algorithm = self.create_sleep_algorithm(algorithm_id)
            return {
                "epoch_length": getattr(algorithm, "epoch_length", 60),
                "requires_raw_data": getattr(algorithm, "requires_raw_data", False),
            }
        except Exception as e:
            logger.debug("Failed to get requirements for algorithm %s: %s", algorithm_id, e)
            return {"epoch_length": 60, "requires_raw_data": False}

    def is_algorithm_available(self, algorithm_id: str) -> bool:
        """
        Check if an algorithm is available.

        Args:
            algorithm_id: The algorithm identifier

        Returns:
            True if algorithm is available

        """
        available = self.get_available_sleep_algorithms()
        return algorithm_id in available


# Singleton instance for convenient access
_algorithm_service_instance: AlgorithmService | None = None


def get_algorithm_service() -> AlgorithmService:
    """
    Get the global algorithm service instance.

    This provides a convenient way to access the algorithm service
    without needing to pass it through constructors.

    Returns:
        The global AlgorithmService instance

    """
    global _algorithm_service_instance
    if _algorithm_service_instance is None:
        _algorithm_service_instance = AlgorithmService()
    return _algorithm_service_instance
