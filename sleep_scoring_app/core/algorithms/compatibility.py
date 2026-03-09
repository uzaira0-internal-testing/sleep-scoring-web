"""
Algorithm-data compatibility enforcement for dual-pipeline architecture.

This module provides UI-level compatibility checking to prevent users from
selecting invalid algorithm-data combinations. It builds on the pipeline
architecture (prompt 043) by adding user-facing validation and feedback.

Compatibility Rules:
    | Data Source | Sadeh/Cole-Kripke | Van Hees SIB/HDCZA |
    |-------------|-------------------|---------------------|
    | GT3X (raw)  | ✅ (after epoch)  | ✅ (direct)         |
    | Raw CSV     | ✅ (after epoch)  | ✅ (direct)         |
    | Epoch CSV   | ✅ (direct)       | ❌ BLOCKED          |

Example Usage:
    >>> from sleep_scoring_app.core.algorithms.compatibility import (
    ...     AlgorithmCompatibilityRegistry,
    ...     AlgorithmDataCompatibilityChecker,
    ... )
    >>> from sleep_scoring_app.core.pipeline import DataSourceType
    >>>
    >>> # Get algorithm info
    >>> algo_info = AlgorithmCompatibilityRegistry.get('sadeh_1994_actilife')
    >>> print(algo_info.data_requirement)  # AlgorithmDataRequirement.EPOCH_DATA
    >>>
    >>> # Check compatibility
    >>> checker = AlgorithmDataCompatibilityChecker()
    >>> result = checker.check(
    ...     DataSourceType.CSV_EPOCH,
    ...     'van_hees_2015_sib'
    ... )
    >>> if result.status == CompatibilityStatus.INCOMPATIBLE:
    ...     print(result.reason)  # "van Hees (2015) SIB requires raw data..."
    ...     print(result.suggested_alternatives)  # ("Sadeh...", "Cole-Kripke...")

References:
    - CLAUDE.md: Protocol-first design, StrEnum patterns
    - pipeline/types.py: AlgorithmDataRequirement, DataSourceType, PipelineType
    - pipeline/orchestrator.py: Core compatibility logic

"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sleep_scoring_app.core.pipeline.types import (
        AlgorithmDataRequirement,
        DataSourceType,
        PipelineType,
    )

# Import at runtime for implementation
import logging

from sleep_scoring_app.core.constants import AlgorithmType
from sleep_scoring_app.core.pipeline.types import (
    AlgorithmDataRequirement,
    DataSourceType,
    PipelineType,
)

logger = logging.getLogger(__name__)


class CompatibilityStatus(StrEnum):
    """
    Status of algorithm-data compatibility check.

    Attributes:
        COMPATIBLE: Combination is valid and can be executed
        INCOMPATIBLE: Combination is invalid and must be blocked
        REQUIRES_PREPROCESSING: Valid but requires additional processing step

    """

    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    REQUIRES_PREPROCESSING = "requires_preprocessing"


class AlgorithmCategory(StrEnum):
    """
    Algorithm category for UI grouping.

    Attributes:
        EPOCH_BASED: Algorithms that require 60-second epoch counts
        RAW_DATA: Algorithms that require raw tri-axial accelerometer data

    """

    EPOCH_BASED = "epoch_based"
    RAW_DATA = "raw_data"


@dataclass(frozen=True)
class AlgorithmCompatibilityInfo:
    """
    Compatibility information for a single algorithm.

    This immutable dataclass stores metadata about an algorithm's data
    requirements and compatibility constraints.

    Attributes:
        algorithm_id: Unique identifier (e.g., "sadeh_1994_actilife")
        display_name: Human-readable name for UI display
        data_requirement: Type of data required (EPOCH_DATA or RAW_DATA)
        category: Algorithm category for UI grouping
        incompatible_message: Message to show when incompatible with data source
        description: Optional detailed description

    """

    algorithm_id: str
    display_name: str
    data_requirement: AlgorithmDataRequirement
    category: AlgorithmCategory
    incompatible_message: str
    description: str = ""


@dataclass(frozen=True)
class CompatibilityResult:
    """
    Result of a compatibility check.

    This immutable dataclass contains the outcome of checking whether a
    data source and algorithm are compatible.

    Attributes:
        status: Compatibility status (COMPATIBLE, INCOMPATIBLE, etc.)
        pipeline_type: Pipeline configuration if compatible, None otherwise
        reason: Human-readable explanation of the result
        suggested_alternatives: Tuple of algorithm IDs that would be compatible
        data_source: Data source type that was checked
        algorithm_id: Algorithm ID that was checked

    """

    status: CompatibilityStatus
    pipeline_type: PipelineType | None
    reason: str
    suggested_alternatives: tuple[str, ...]
    data_source: DataSourceType | None = None
    algorithm_id: str | None = None


class AlgorithmCompatibilityRegistry:
    """
    Registry of algorithm compatibility information.

    This class maintains a ClassVar dictionary mapping algorithm IDs to
    their compatibility metadata. It provides methods to query algorithm
    requirements and find compatible algorithms for a given data source.

    Class Attributes:
        _registry: ClassVar mapping algorithm_id → AlgorithmCompatibilityInfo

    Methods:
        get: Get compatibility info for a specific algorithm
        get_compatible: Get all algorithms compatible with a data source
        is_compatible: Quick check if algorithm works with data source
        get_all: Get all registered algorithms
        register: Register a new algorithm (for extensibility)

    """

    _registry: ClassVar[dict[str, AlgorithmCompatibilityInfo]] = {
        # === EPOCH-BASED ALGORITHMS ===
        AlgorithmType.SADEH_1994_ORIGINAL: AlgorithmCompatibilityInfo(
            algorithm_id=AlgorithmType.SADEH_1994_ORIGINAL,
            display_name="Sadeh (1994) Original",
            data_requirement=AlgorithmDataRequirement.EPOCH_DATA,
            category=AlgorithmCategory.EPOCH_BASED,
            incompatible_message=(
                "Sadeh (1994) requires 60-second epoch count data. Pre-epoched CSV files are compatible, or raw data can be epoched first."
            ),
            description="Original Sadeh algorithm with threshold=0.0",
        ),
        AlgorithmType.SADEH_1994_ACTILIFE: AlgorithmCompatibilityInfo(
            algorithm_id=AlgorithmType.SADEH_1994_ACTILIFE,
            display_name="Sadeh (1994) ActiLife",
            data_requirement=AlgorithmDataRequirement.EPOCH_DATA,
            category=AlgorithmCategory.EPOCH_BASED,
            incompatible_message=(
                "Sadeh (1994) ActiLife requires 60-second epoch count data. Pre-epoched CSV files are compatible, or raw data can be epoched first."
            ),
            description="ActiLife variant with threshold=-4.0",
        ),
        # Note: sadeh_1994_count_scaled is disabled in factory, keep for reference
        "sadeh_1994_count_scaled": AlgorithmCompatibilityInfo(
            algorithm_id="sadeh_1994_count_scaled",
            display_name="Sadeh (1994) Count-Scaled",
            data_requirement=AlgorithmDataRequirement.EPOCH_DATA,
            category=AlgorithmCategory.EPOCH_BASED,
            incompatible_message=(
                "Sadeh (1994) Count-Scaled requires 60-second epoch count data. "
                "Pre-epoched CSV files are compatible, or raw data can be epoched first."
            ),
            description="Count-scaled variant for modern accelerometers",
        ),
        AlgorithmType.COLE_KRIPKE_1992_ORIGINAL: AlgorithmCompatibilityInfo(
            algorithm_id=AlgorithmType.COLE_KRIPKE_1992_ORIGINAL,
            display_name="Cole-Kripke (1992) Original",
            data_requirement=AlgorithmDataRequirement.EPOCH_DATA,
            category=AlgorithmCategory.EPOCH_BASED,
            incompatible_message=(
                "Cole-Kripke (1992) requires 60-second epoch count data. Pre-epoched CSV files are compatible, or raw data can be epoched first."
            ),
            description="Original Cole-Kripke algorithm",
        ),
        AlgorithmType.COLE_KRIPKE_1992_ACTILIFE: AlgorithmCompatibilityInfo(
            algorithm_id=AlgorithmType.COLE_KRIPKE_1992_ACTILIFE,
            display_name="Cole-Kripke (1992) ActiLife",
            data_requirement=AlgorithmDataRequirement.EPOCH_DATA,
            category=AlgorithmCategory.EPOCH_BASED,
            incompatible_message=(
                "Cole-Kripke (1992) ActiLife requires 60-second epoch count data. "
                "Pre-epoched CSV files are compatible, or raw data can be epoched first."
            ),
            description="ActiLife variant",
        ),
        # Note: cole_kripke_1992_count_scaled is disabled in factory, keep for reference
        "cole_kripke_1992_count_scaled": AlgorithmCompatibilityInfo(
            algorithm_id="cole_kripke_1992_count_scaled",
            display_name="Cole-Kripke (1992) Count-Scaled",
            data_requirement=AlgorithmDataRequirement.EPOCH_DATA,
            category=AlgorithmCategory.EPOCH_BASED,
            incompatible_message=(
                "Cole-Kripke (1992) Count-Scaled requires 60-second epoch count data. "
                "Pre-epoched CSV files are compatible, or raw data can be epoched first."
            ),
            description="Count-scaled variant for modern accelerometers",
        ),
    }

    @classmethod
    def get(cls, algorithm_id: str) -> AlgorithmCompatibilityInfo | None:
        """
        Get compatibility info for a specific algorithm.

        Args:
            algorithm_id: Algorithm identifier

        Returns:
            AlgorithmCompatibilityInfo if found, None otherwise

        Example:
            >>> info = AlgorithmCompatibilityRegistry.get('sadeh_1994_actilife')
            >>> print(info.data_requirement)  # AlgorithmDataRequirement.EPOCH_DATA

        """
        return cls._registry.get(algorithm_id)

    @classmethod
    def get_compatible(
        cls,
        data_source: DataSourceType,
    ) -> list[AlgorithmCompatibilityInfo]:
        """
        Get all algorithms compatible with a data source.

        This method returns algorithms that can be used with the given data
        source type, either directly or after preprocessing.

        Args:
            data_source: Data source type to check

        Returns:
            List of compatible algorithm info objects

        Example:
            >>> compatible = AlgorithmCompatibilityRegistry.get_compatible(
            ...     DataSourceType.CSV_EPOCH
            ... )
            >>> for algo in compatible:
            ...     print(algo.display_name)
            # Only epoch-based algorithms (Sadeh, Cole-Kripke variants)

        """
        compatible = []

        for info in cls._registry.values():
            # Raw data sources are compatible with ALL algorithms
            # (raw-data algorithms work directly, epoch-based need epoching)
            if data_source.is_raw():
                compatible.append(info)

            # Epoch data sources ONLY work with epoch-based algorithms
            elif data_source.is_epoched():
                if info.data_requirement == AlgorithmDataRequirement.EPOCH_DATA:
                    compatible.append(info)

        return compatible

    @classmethod
    def is_compatible(
        cls,
        data_source: DataSourceType,
        algorithm_id: str,
    ) -> bool:
        """
        Quick check if algorithm is compatible with data source.

        Args:
            data_source: Data source type
            algorithm_id: Algorithm identifier

        Returns:
            True if compatible, False otherwise

        Example:
            >>> is_ok = AlgorithmCompatibilityRegistry.is_compatible(
            ...     DataSourceType.CSV_EPOCH,
            ...     'van_hees_2015_sib'
            ... )
            >>> print(is_ok)  # False

        """
        compatible_algos = cls.get_compatible(data_source)
        return algorithm_id in {algo.algorithm_id for algo in compatible_algos}

    @classmethod
    def get_all(cls) -> list[AlgorithmCompatibilityInfo]:
        """
        Get all registered algorithms.

        Returns:
            List of all algorithm info objects

        Example:
            >>> all_algos = AlgorithmCompatibilityRegistry.get_all()
            >>> len(all_algos)  # 8 (6 epoch-based + 2 raw-data)

        """
        return list(cls._registry.values())

    @classmethod
    def get_by_category(
        cls,
        category: AlgorithmCategory,
    ) -> list[AlgorithmCompatibilityInfo]:
        """
        Get all algorithms in a category.

        Args:
            category: Algorithm category to filter by

        Returns:
            List of algorithms in the category

        Example:
            >>> epoch_algos = AlgorithmCompatibilityRegistry.get_by_category(
            ...     AlgorithmCategory.EPOCH_BASED
            ... )

        """
        return [info for info in cls._registry.values() if info.category == category]

    @classmethod
    def register(
        cls,
        info: AlgorithmCompatibilityInfo,
    ) -> None:
        """
        Register a new algorithm (for extensibility).

        Args:
            info: Algorithm compatibility information

        Raises:
            ValueError: If algorithm_id already registered

        Example:
            >>> new_algo = AlgorithmCompatibilityInfo(
            ...     algorithm_id='custom_algo',
            ...     display_name='Custom Algorithm',
            ...     data_requirement=AlgorithmDataRequirement.EPOCH_DATA,
            ...     category=AlgorithmCategory.EPOCH_BASED,
            ...     incompatible_message='Custom algorithm requires epoch data',
            ... )
            >>> AlgorithmCompatibilityRegistry.register(new_algo)

        """
        if info.algorithm_id in cls._registry:
            msg = f"Algorithm '{info.algorithm_id}' already registered"
            raise ValueError(msg)

        cls._registry[info.algorithm_id] = info
        logger.info(f"Registered algorithm compatibility: {info.algorithm_id}")


@runtime_checkable
class CompatibilityChecker(Protocol):
    """
    Protocol for checking algorithm-data compatibility.

    This protocol defines the interface for compatibility checking without
    specifying implementation details. Enables dependency injection and
    testing with mock implementations.

    Methods:
        check: Check compatibility and return detailed result
        get_incompatibility_reason: Get human-readable reason for incompatibility
        suggest_alternatives: Get suggested compatible algorithms

    """

    def check(
        self,
        data_source: DataSourceType,
        algorithm_id: str,
    ) -> CompatibilityResult:
        """
        Check compatibility between data source and algorithm.

        Args:
            data_source: Type of data source
            algorithm_id: Algorithm identifier

        Returns:
            CompatibilityResult with status, reason, and suggestions

        """
        ...

    def get_incompatibility_reason(
        self,
        data_source: DataSourceType,
        algorithm_id: str,
    ) -> str:
        """
        Get human-readable reason for incompatibility.

        Args:
            data_source: Type of data source
            algorithm_id: Algorithm identifier

        Returns:
            Reason string, or empty string if compatible

        """
        ...

    def suggest_alternatives(
        self,
        data_source: DataSourceType,
    ) -> tuple[str, ...]:
        """
        Suggest compatible algorithms for a data source.

        Args:
            data_source: Type of data source

        Returns:
            Tuple of algorithm IDs that are compatible

        """
        ...


class AlgorithmDataCompatibilityChecker:
    """
    Implementation of compatibility checking logic.

    This class implements the CompatibilityChecker protocol and uses the
    PipelineOrchestrator to determine compatibility based on pipeline types.

    Example:
        >>> checker = AlgorithmDataCompatibilityChecker()
        >>> result = checker.check(
        ...     DataSourceType.CSV_EPOCH,
        ...     'van_hees_2015_sib'
        ... )
        >>> if result.status == CompatibilityStatus.INCOMPATIBLE:
        ...     print(result.reason)
        ...     print("Try these instead:", result.suggested_alternatives)

    """

    def __init__(self) -> None:
        """Initialize compatibility checker."""
        from sleep_scoring_app.core.pipeline.orchestrator import PipelineOrchestrator

        self._orchestrator = PipelineOrchestrator()

    def check(
        self,
        data_source: DataSourceType,
        algorithm_id: str,
    ) -> CompatibilityResult:
        """
        Check compatibility between data source and algorithm.

        This method determines the pipeline type and returns a detailed
        result with status, reason, and suggested alternatives.

        Args:
            data_source: Type of data source
            algorithm_id: Algorithm identifier

        Returns:
            CompatibilityResult with complete information

        Example:
            >>> result = checker.check(
            ...     DataSourceType.CSV_EPOCH,
            ...     'sadeh_1994_actilife'
            ... )
            >>> print(result.status)  # CompatibilityStatus.COMPATIBLE
            >>> print(result.pipeline_type)  # PipelineType.EPOCH_DIRECT

        """
        # Get algorithm info
        algo_info = AlgorithmCompatibilityRegistry.get(algorithm_id)
        if not algo_info:
            return CompatibilityResult(
                status=CompatibilityStatus.INCOMPATIBLE,
                pipeline_type=None,
                reason=f"Unknown algorithm: {algorithm_id}",
                suggested_alternatives=(),
                data_source=data_source,
                algorithm_id=algorithm_id,
            )

        # Create a temporary algorithm instance to check compatibility
        # We need this because the orchestrator works with algorithm instances
        from sleep_scoring_app.core.algorithms import AlgorithmFactory
        from sleep_scoring_app.core.algorithms.sleep_period import SleepPeriodDetectorFactory

        sleep_algorithm = None
        try:
            sleep_algorithm = AlgorithmFactory.create(algorithm_id)
        except ValueError:
            # Try SleepPeriodDetectorFactory for SPT detectors like HDCZA
            # Note: Period detectors are always compatible with epoch data
            try:
                _period_detector = SleepPeriodDetectorFactory.create(algorithm_id)
                # Period detectors work on pre-classified epoch data, so they're always compatible
                return CompatibilityResult(
                    status=CompatibilityStatus.COMPATIBLE,
                    pipeline_type=PipelineType.EPOCH_DIRECT,
                    reason=f"{algo_info.display_name} is compatible with epoch data.",
                    suggested_alternatives=(),
                    data_source=data_source,
                    algorithm_id=algorithm_id,
                )
            except ValueError:
                pass

        if sleep_algorithm is None:
            return CompatibilityResult(
                status=CompatibilityStatus.INCOMPATIBLE,
                pipeline_type=None,
                reason=f"Failed to create algorithm: {algorithm_id}",
                suggested_alternatives=(),
                data_source=data_source,
                algorithm_id=algorithm_id,
            )

        # Determine pipeline type
        pipeline_type = self._orchestrator.determine_pipeline_type(
            data_source,
            sleep_algorithm,
        )

        # Get suggested alternatives
        alternatives = self.suggest_alternatives(data_source)

        # Build result based on pipeline type
        if pipeline_type == PipelineType.INCOMPATIBLE:
            return CompatibilityResult(
                status=CompatibilityStatus.INCOMPATIBLE,
                pipeline_type=None,
                reason=algo_info.incompatible_message,
                suggested_alternatives=alternatives,
                data_source=data_source,
                algorithm_id=algorithm_id,
            )

        if pipeline_type == PipelineType.RAW_TO_EPOCH:
            return CompatibilityResult(
                status=CompatibilityStatus.REQUIRES_PREPROCESSING,
                pipeline_type=pipeline_type,
                reason=(f"{algo_info.display_name} requires 60-second epoch data. Raw data will be automatically epoched before scoring."),
                suggested_alternatives=(),
                data_source=data_source,
                algorithm_id=algorithm_id,
            )

        # COMPATIBLE (RAW_TO_RAW or EPOCH_DIRECT)
        return CompatibilityResult(
            status=CompatibilityStatus.COMPATIBLE,
            pipeline_type=pipeline_type,
            reason=f"{algo_info.display_name} is compatible with this data source.",
            suggested_alternatives=(),
            data_source=data_source,
            algorithm_id=algorithm_id,
        )

    def get_incompatibility_reason(
        self,
        data_source: DataSourceType,
        algorithm_id: str,
    ) -> str:
        """
        Get human-readable reason for incompatibility.

        Args:
            data_source: Type of data source
            algorithm_id: Algorithm identifier

        Returns:
            Reason string, or empty string if compatible

        Example:
            >>> reason = checker.get_incompatibility_reason(
            ...     DataSourceType.CSV_EPOCH,
            ...     'van_hees_2015_sib'
            ... )
            >>> print(reason)  # "van Hees (2015) SIB requires raw..."

        """
        result = self.check(data_source, algorithm_id)
        if result.status == CompatibilityStatus.INCOMPATIBLE:
            return result.reason
        return ""

    def suggest_alternatives(
        self,
        data_source: DataSourceType,
    ) -> tuple[str, ...]:
        """
        Suggest compatible algorithms for a data source.

        Args:
            data_source: Type of data source

        Returns:
            Tuple of algorithm IDs that are compatible

        Example:
            >>> alternatives = checker.suggest_alternatives(
            ...     DataSourceType.CSV_EPOCH
            ... )
            >>> print(alternatives)
            # ('sadeh_1994_original', 'sadeh_1994_actilife', ...)

        """
        compatible_infos = AlgorithmCompatibilityRegistry.get_compatible(data_source)
        return tuple(info.algorithm_id for info in compatible_infos)
