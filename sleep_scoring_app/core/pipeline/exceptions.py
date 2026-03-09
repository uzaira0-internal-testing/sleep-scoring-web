"""
Pipeline-specific exceptions.

This module defines exceptions for the dual-pipeline architecture,
enabling clear error handling for incompatible data/algorithm combinations.

Example Usage:
    >>> from sleep_scoring_app.core.pipeline import (
    ...     IncompatiblePipelineError,
    ...     PipelineOrchestrator,
    ... )
    >>>
    >>> orchestrator = PipelineOrchestrator()
    >>> try:
    ...     result = orchestrator.process(source, file_path, algorithm)
    ... except IncompatiblePipelineError as e:
    ...     print(f"Cannot process: {e.message}")
    ...     print(f"Reason: {e.reason}")
    ...     print(f"Suggestion: {e.suggestion}")

References:
    - core/exceptions.py: Base exception classes
    - CLAUDE.md: Error handling patterns

"""

from __future__ import annotations

from sleep_scoring_app.core.exceptions import AlgorithmError, SleepScoringError

# Import types at runtime for isinstance checks and comparisons
from .types import AlgorithmDataRequirement, DataSourceType


class PipelineError(SleepScoringError):
    """
    Base exception for pipeline-related errors.

    Raised when pipeline orchestration fails for any reason.
    """


class IncompatiblePipelineError(PipelineError):
    """
    Raised when algorithm and data source are incompatible.

    This exception is raised when attempting to use:
    - Raw-data algorithms (Van Hees SIB, HDCZA) with pre-epoched CSV data
    - Any blocked combination that cannot be recovered

    The error includes detailed information about why the combination
    is invalid and what alternatives are available.

    Attributes:
        message: Human-readable error message
        data_source: Data source type that was provided
        algorithm_requirement: What the algorithm requires
        reason: Technical explanation of incompatibility
        suggestion: Recommended action to resolve the issue

    Example:
        >>> raise IncompatiblePipelineError(
        ...     data_source=DataSourceType.CSV_EPOCH,
        ...     algorithm_requirement=AlgorithmDataRequirement.RAW_DATA,
        ...     algorithm_name="van Hees SIB (2015)",
        ... )

    """

    def __init__(
        self,
        data_source: DataSourceType,
        algorithm_requirement: AlgorithmDataRequirement,
        algorithm_name: str,
        message: str | None = None,
    ) -> None:
        """
        Initialize incompatible pipeline error.

        Args:
            data_source: Type of data source provided
            algorithm_requirement: Data type required by algorithm
            algorithm_name: Name of the algorithm for display
            message: Optional custom error message

        """
        self.data_source = data_source
        self.algorithm_requirement = algorithm_requirement
        self.algorithm_name = algorithm_name

        # Generate reason and suggestion
        self.reason = self._generate_reason()
        self.suggestion = self._generate_suggestion()

        # Generate full message
        if message is None:
            message = f"Cannot process {data_source.value} data with {algorithm_name}. {self.reason} {self.suggestion}"

        super().__init__(
            message=message,
            error_code="INCOMPATIBLE_PIPELINE",
            context={
                "data_source": data_source.value,
                "algorithm_requirement": algorithm_requirement.value,
                "algorithm_name": algorithm_name,
            },
        )

    def _generate_reason(self) -> str:
        """Generate technical explanation of incompatibility."""
        if self.algorithm_requirement == AlgorithmDataRequirement.RAW_DATA:
            return (
                f"The {self.algorithm_name} algorithm requires raw high-frequency "
                f"tri-axial accelerometer data, but {self.data_source.value} contains "
                f"pre-aggregated 60-second epoch counts."
            )
        # This case shouldn't normally happen (epoch algorithms can use any source)
        return f"The {self.algorithm_name} algorithm requires 60-second epoch data, but {self.data_source.value} format is incompatible."

    def _generate_suggestion(self) -> str:
        """Generate recommended action to resolve the issue."""
        if self.algorithm_requirement == AlgorithmDataRequirement.RAW_DATA:
            return (
                "To use this algorithm, please load a GT3X file or CSV with raw "
                "tri-axial data (AXIS_X, AXIS_Y, AXIS_Z columns at ~30-100 Hz). "
                "Alternatively, choose an epoch-based algorithm like Sadeh (1994) "
                "or Cole-Kripke (1992) which can process epoch count data."
            )
        return "To use this algorithm, please load a CSV file with pre-aggregated 60-second epoch counts (Axis1 column) or a GT3X file."


class DataDetectionError(PipelineError):
    """
    Raised when data source type cannot be automatically detected.

    This occurs when:
    - File format is ambiguous (CSV without clear column structure)
    - Required columns are missing
    - Data format is unrecognized

    Example:
        >>> raise DataDetectionError(
        ...     file_path="unknown.csv",
        ...     reason="Missing required columns: timestamp, Axis1",
        ... )

    """

    def __init__(
        self,
        file_path: str,
        reason: str,
        message: str | None = None,
    ) -> None:
        """
        Initialize data detection error.

        Args:
            file_path: Path to file that failed detection
            reason: Technical explanation of detection failure
            message: Optional custom error message

        """
        self.file_path = file_path
        self.reason = reason

        if message is None:
            message = f"Cannot detect data source type for '{file_path}'. {reason}"

        super().__init__(
            message=message,
            error_code="DATA_DETECTION_FAILED",
            context={
                "file_path": file_path,
                "reason": reason,
            },
        )


class EpochingError(AlgorithmError):
    """
    Raised when epoching raw data fails.

    This occurs when:
    - Raw data is malformed
    - Sample rate is invalid
    - Epoch length is incompatible with sample rate

    Example:
        >>> raise EpochingError(
        ...     reason="Sample rate 0 Hz is invalid",
        ...     epoch_length=60,
        ... )

    """

    def __init__(
        self,
        reason: str,
        epoch_length: int | None = None,
        message: str | None = None,
    ) -> None:
        """
        Initialize epoching error.

        Args:
            reason: Technical explanation of epoching failure
            epoch_length: Target epoch length in seconds (if applicable)
            message: Optional custom error message

        """
        self.reason = reason
        self.epoch_length = epoch_length

        if message is None:
            if epoch_length is not None:
                message = f"Failed to create {epoch_length}s epochs: {reason}"
            else:
                message = f"Epoching failed: {reason}"

        super().__init__(
            message=message,
            error_code="EPOCHING_FAILED",
            context={
                "reason": reason,
                "epoch_length": epoch_length,
            },
        )
