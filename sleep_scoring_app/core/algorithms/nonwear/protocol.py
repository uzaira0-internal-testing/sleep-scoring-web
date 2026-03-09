"""
Nonwear detection algorithm protocol for dependency injection.

This protocol defines the interface that all nonwear detection algorithms must implement.
Enables swappable algorithms without changing core application logic.

Architecture:
    - Protocol defines the contract for nonwear detection algorithms
    - Implementations: ChoiAlgorithm (2011), van Hees (future), etc.
    - Factory creates instances based on configuration
    - Services accept protocol type, not concrete implementations

Example Usage:
    >>> from sleep_scoring_app.core.algorithms import NonwearAlgorithmFactory
    >>>
    >>> # Create algorithm from factory
    >>> algorithm = NonwearAlgorithmFactory.create('choi_2011')
    >>>
    >>> # Use protocol type for dependency injection
    >>> def process_data(algorithm: NonwearDetectionAlgorithm, data: list):
    ...     return algorithm.detect(data, timestamps)

References:
    - Choi, L., et al. (2011). Validation of accelerometer wear and nonwear time classification algorithm.
    - van Hees, V. T., et al. (2013). Separating movement and gravity components in an acceleration signal.

"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime

    import numpy as np

    from sleep_scoring_app.core.dataclasses import NonwearPeriod


@runtime_checkable
class NonwearDetectionAlgorithm(Protocol):
    """
    Protocol for nonwear detection algorithms.

    All nonwear detection algorithms (Choi, van Hees, etc.) must implement this interface.
    The protocol is runtime_checkable to allow isinstance() checks for validation.

    Properties:
        name: Human-readable algorithm name for display
        identifier: Unique identifier for storage and configuration

    Methods:
        detect: Detect nonwear periods from activity data
        detect_mask: Generate per-epoch nonwear mask (0=wear, 1=nonwear)
        get_parameters: Get current algorithm parameters
        set_parameters: Update algorithm parameters

    """

    @property
    def name(self) -> str:
        """
        Algorithm name for display and identification.

        Returns:
            Human-readable algorithm name (e.g., "Choi (2011)", "van Hees (2013)")

        """
        ...

    @property
    def identifier(self) -> str:
        """
        Unique algorithm identifier for storage and configuration.

        Returns:
            Snake_case identifier (e.g., "choi_2011", "vanhees_2013")

        """
        ...

    def detect(
        self,
        activity_data: list[float] | np.ndarray,
        timestamps: list[datetime],
        activity_column: str = "axis_y",
    ) -> list[NonwearPeriod]:
        """
        Detect nonwear periods from activity data.

        Args:
            activity_data: List or array of activity count values
            timestamps: List of datetime objects corresponding to activity data
            activity_column: Name of activity column for reference (e.g., "axis_y", "vector_magnitude")

        Returns:
            List of NonwearPeriod objects representing detected nonwear periods

        Raises:
            ValueError: If input data is invalid or mismatched lengths

        """
        ...

    def detect_mask(self, activity_data: list[float] | np.ndarray) -> list[int]:
        """
        Generate per-epoch nonwear mask from activity data.

        Args:
            activity_data: List or array of activity count values

        Returns:
            List of 0/1 values where 0=wearing, 1=not wearing

        Raises:
            ValueError: If input data is invalid

        """
        ...

    def get_parameters(self) -> dict[str, Any]:
        """
        Get current algorithm parameters.

        Returns:
            Dictionary of parameter names and values

        """
        ...

    def set_parameters(self, **kwargs: Any) -> None:
        """
        Update algorithm parameters.

        Args:
            **kwargs: Parameter name-value pairs

        Raises:
            ValueError: If parameter name is invalid or value is out of range

        """
        ...
