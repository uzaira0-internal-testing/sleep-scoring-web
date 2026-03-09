"""
Algorithm factory for sleep scoring algorithms.

Provides a unified interface for creating and using different sleep
scoring algorithms (Sadeh, Cole-Kripke, etc.).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from .cole_kripke import ColeKripkeAlgorithm
from .sadeh import SadehAlgorithm

if TYPE_CHECKING:
    from collections.abc import Sequence


class SleepScoringAlgorithm(Protocol):
    """Protocol for sleep scoring algorithms."""

    def score(self, activity_counts: Sequence[int | float]) -> list[int]:
        """Score epochs as sleep (1) or wake (0)."""
        ...


class AlgorithmType:
    """Algorithm type identifiers matching frontend constants."""

    SADEH_1994_ACTILIFE = "sadeh_1994_actilife"
    SADEH_1994_ORIGINAL = "sadeh_1994_original"
    COLE_KRIPKE_1992_ACTILIFE = "cole_kripke_1992_actilife"
    COLE_KRIPKE_1992_ORIGINAL = "cole_kripke_1992_original"


# All available algorithm types
ALGORITHM_TYPES = [
    AlgorithmType.SADEH_1994_ACTILIFE,
    AlgorithmType.SADEH_1994_ORIGINAL,
    AlgorithmType.COLE_KRIPKE_1992_ACTILIFE,
    AlgorithmType.COLE_KRIPKE_1992_ORIGINAL,
]


def create_algorithm(algorithm_type: str) -> SleepScoringAlgorithm:
    """
    Create a sleep scoring algorithm instance.

    Args:
        algorithm_type: Algorithm identifier string (e.g., "sadeh_1994_actilife")

    Returns:
        Algorithm instance implementing SleepScoringAlgorithm protocol

    Raises:
        ValueError: If algorithm_type is not recognized

    """
    match algorithm_type:
        case AlgorithmType.SADEH_1994_ACTILIFE:
            return SadehAlgorithm(variant="actilife")
        case AlgorithmType.SADEH_1994_ORIGINAL:
            return SadehAlgorithm(variant="original")
        case AlgorithmType.COLE_KRIPKE_1992_ACTILIFE:
            return ColeKripkeAlgorithm(variant="actilife")
        case AlgorithmType.COLE_KRIPKE_1992_ORIGINAL:
            return ColeKripkeAlgorithm(variant="original")
        case _:
            msg = f"Unknown algorithm type: {algorithm_type}. Available: {ALGORITHM_TYPES}"
            raise ValueError(msg)


def get_default_algorithm() -> str:
    """Get the default algorithm type."""
    return AlgorithmType.SADEH_1994_ACTILIFE
