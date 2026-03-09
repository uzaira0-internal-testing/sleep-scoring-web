"""
Nonwear detection algorithm implementations.

This package contains implementations of nonwear detection algorithms.
All algorithms implement the NonwearDetectionAlgorithm protocol.

Algorithms:
    - ChoiAlgorithm: Choi et al. (2011) - 90-minute window algorithm

Exports:
    - ChoiAlgorithm: Class implementing Choi algorithm
    - NonwearAlgorithmFactory: Factory for creating nonwear algorithms
    - NonwearDetectionAlgorithm: Protocol for nonwear algorithms

Note:
    Raw data nonwear algorithms (van Hees) are not included in this package.
    For raw accelerometer nonwear detection, use rpy2 to call GGIR.

"""

from __future__ import annotations

from .choi import ChoiAlgorithm
from .factory import NonwearAlgorithmFactory
from .protocol import NonwearDetectionAlgorithm

__all__ = [
    # Algorithm classes
    "ChoiAlgorithm",
    # Factory
    "NonwearAlgorithmFactory",
    # Protocol
    "NonwearDetectionAlgorithm",
]
