"""
Pipeline orchestration for dual-pipeline architecture.

This module routes data processing through the correct pipeline path based on
data source type and algorithm requirements. It enforces compatibility rules
and blocks invalid combinations.

Example Usage:
    >>> from sleep_scoring_app.core.pipeline import (
    ...     PipelineOrchestrator,
    ...     DataSourceType,
    ... )
    >>> from sleep_scoring_app.core.algorithms import SadehAlgorithm
    >>>
    >>> orchestrator = PipelineOrchestrator()
    >>> algorithm = SadehAlgorithm()
    >>>
    >>> # Check compatibility
    >>> is_ok = orchestrator.is_compatible(
    ...     DataSourceType.CSV_EPOCH,
    ...     algorithm
    ... )
    >>>
    >>> # Determine pipeline type
    >>> pipeline = orchestrator.determine_pipeline_type(
    ...     DataSourceType.GT3X_RAW,
    ...     algorithm
    ... )

References:
    - CLAUDE.md: Pipeline architecture patterns
    - types.py: Pipeline type definitions

"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd

    from sleep_scoring_app.core.algorithms.sleep_wake.protocol import SleepScoringAlgorithm

from sleep_scoring_app.core.constants import AlgorithmOutputColumn

from .exceptions import IncompatiblePipelineError
from .types import AlgorithmDataRequirement, DataSourceType, EpochingService, PipelineType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PipelineResult:
    """
    Result of pipeline processing.

    This immutable dataclass contains the output from pipeline execution,
    including the scored data and metadata about the pipeline path taken.

    Attributes:
        scored_data: DataFrame with sleep/wake scores
        pipeline_type: Type of pipeline that was executed
        data_source: Original data source type
        algorithm_name: Name of algorithm used
        metadata: Optional processing metadata

    """

    scored_data: pd.DataFrame
    pipeline_type: PipelineType
    data_source: DataSourceType
    algorithm_name: str
    metadata: dict[str, str | int | float] | None = None


class PipelineOrchestrator:
    """
    Orchestrator for dual-pipeline architecture.

    This class determines the correct processing path based on data source
    and algorithm requirements, enforces compatibility rules, and routes
    data through the appropriate pipeline.

    Pipeline Paths:
        1. RAW_TO_RAW: GT3X/CSV_RAW → Raw-data algorithm (Van Hees SIB, HDCZA)
        2. RAW_TO_EPOCH: GT3X/CSV_RAW → Epoch → Epoch-based algorithm (Sadeh, Cole-Kripke)
        3. EPOCH_DIRECT: CSV_EPOCH → Epoch-based algorithm (Sadeh, Cole-Kripke)
        4. INCOMPATIBLE: CSV_EPOCH → Raw-data algorithm (BLOCKED)

    Example:
        >>> from services.epoching_service import EpochingService
        >>> epoching_service = EpochingService()
        >>> orchestrator = PipelineOrchestrator(epoching_service)
        >>> result = orchestrator.process(
        ...     data_source=DataSourceType.GT3X_RAW,
        ...     file_path="data.gt3x",
        ...     algorithm=algorithm,
        ... )

    """

    def __init__(self, epoching_service: EpochingService | None = None) -> None:
        """
        Initialize pipeline orchestrator.

        Args:
            epoching_service: Service for epoching raw data. If None, RAW_TO_EPOCH
                             pipeline will fail. Optional for backwards compatibility.

        """
        self._epoching_service = epoching_service

    def determine_pipeline_type(
        self,
        data_source: DataSourceType,
        algorithm: SleepScoringAlgorithm,
    ) -> PipelineType:
        """
        Determine which pipeline type to use for this combination.

        This method implements the compatibility matrix:
        - Raw data sources can use ANY algorithm (with epoching if needed)
        - Epoch data sources can ONLY use epoch-based algorithms
        - Raw-data algorithms with epoch sources are INCOMPATIBLE

        Args:
            data_source: Type of data source
            algorithm: Sleep scoring algorithm instance

        Returns:
            PipelineType indicating which pipeline path to use

        Example:
            >>> pipeline = orchestrator.determine_pipeline_type(
            ...     DataSourceType.GT3X_RAW,
            ...     sadeh_algorithm,
            ... )
            >>> print(pipeline)  # PipelineType.RAW_TO_EPOCH

        """
        # Get algorithm's data requirement
        algo_requirement = algorithm.data_requirement

        logger.debug(f"Determining pipeline: data_source={data_source.value}, algorithm={algorithm.name}, requirement={algo_requirement.value}")

        # Case 1: Raw data source + Raw-data algorithm → RAW_TO_RAW
        if data_source.is_raw() and algo_requirement == AlgorithmDataRequirement.RAW_DATA:
            logger.debug("Pipeline: RAW_TO_RAW (no epoching needed)")
            return PipelineType.RAW_TO_RAW

        # Case 2: Raw data source + Epoch-based algorithm → RAW_TO_EPOCH
        if data_source.is_raw() and algo_requirement == AlgorithmDataRequirement.EPOCH_DATA:
            logger.debug("Pipeline: RAW_TO_EPOCH (will epoch raw data)")
            return PipelineType.RAW_TO_EPOCH

        # Case 3: Epoch data source + Epoch-based algorithm → EPOCH_DIRECT
        if data_source.is_epoched() and algo_requirement == AlgorithmDataRequirement.EPOCH_DATA:
            logger.debug("Pipeline: EPOCH_DIRECT (direct processing)")
            return PipelineType.EPOCH_DIRECT

        # Case 4: Epoch data source + Raw-data algorithm → INCOMPATIBLE
        if data_source.is_epoched() and algo_requirement == AlgorithmDataRequirement.RAW_DATA:
            logger.warning(f"INCOMPATIBLE: Cannot use {algorithm.name} (requires raw data) with {data_source.value} (pre-epoched)")
            return PipelineType.INCOMPATIBLE

        # Fallback (shouldn't reach here)
        logger.error(f"Unexpected combination: {data_source.value} + {algo_requirement.value}")
        return PipelineType.INCOMPATIBLE

    def is_compatible(
        self,
        data_source: DataSourceType,
        algorithm: SleepScoringAlgorithm,
    ) -> bool:
        """
        Check if data source and algorithm are compatible.

        This is a convenience method that wraps determine_pipeline_type()
        and returns a simple boolean.

        Args:
            data_source: Type of data source
            algorithm: Sleep scoring algorithm instance

        Returns:
            True if compatible, False if incompatible

        Example:
            >>> if orchestrator.is_compatible(source, algorithm):
            ...     result = orchestrator.process(source, file_path, algorithm)
            ... else:
            ...     print("Incompatible combination")

        """
        pipeline_type = self.determine_pipeline_type(data_source, algorithm)
        return pipeline_type.is_valid()

    def validate_compatibility(
        self,
        data_source: DataSourceType,
        algorithm: SleepScoringAlgorithm,
    ) -> None:
        """
        Validate compatibility and raise exception if incompatible.

        This method enforces the compatibility rules and raises a detailed
        exception if the combination is invalid.

        Args:
            data_source: Type of data source
            algorithm: Sleep scoring algorithm instance

        Raises:
            IncompatiblePipelineError: If data source and algorithm are incompatible

        Example:
            >>> try:
            ...     orchestrator.validate_compatibility(source, algorithm)
            ... except IncompatiblePipelineError as e:
            ...     print(f"Error: {e.message}")
            ...     print(f"Suggestion: {e.suggestion}")

        """
        pipeline_type = self.determine_pipeline_type(data_source, algorithm)

        if not pipeline_type.is_valid():
            raise IncompatiblePipelineError(
                data_source=data_source,
                algorithm_requirement=algorithm.data_requirement,
                algorithm_name=algorithm.name,
            )

    def process(
        self,
        data_source: DataSourceType,
        data: pd.DataFrame,
        algorithm: SleepScoringAlgorithm,
    ) -> PipelineResult:
        """
        Process data through the appropriate pipeline.

        This method is the main entry point for pipeline execution. It:
        1. Validates compatibility
        2. Determines pipeline type
        3. Routes to appropriate processing function
        4. Returns wrapped result

        Args:
            data_source: Type of data source
            data: Loaded DataFrame (raw or epoch data)
            algorithm: Sleep scoring algorithm instance

        Returns:
            PipelineResult with scored data and metadata

        Raises:
            IncompatiblePipelineError: If data source and algorithm are incompatible

        Example:
            >>> df = pd.read_csv("data.csv")
            >>> result = orchestrator.process(
            ...     DataSourceType.CSV_EPOCH,
            ...     df,
            ...     algorithm,
            ... )
            >>> print(result.scored_data['Sleep Score'])

        """
        # Validate compatibility first
        self.validate_compatibility(data_source, algorithm)

        # Determine pipeline type
        pipeline_type = self.determine_pipeline_type(data_source, algorithm)

        logger.info(f"Processing via {pipeline_type.value} pipeline: source={data_source.value}, algorithm={algorithm.name}")

        # Route to appropriate pipeline function
        if pipeline_type == PipelineType.RAW_TO_RAW:
            scored_data = self._process_raw_to_raw(data, algorithm)
        elif pipeline_type == PipelineType.RAW_TO_EPOCH:
            scored_data = self._process_raw_to_epoch(data, algorithm)
        elif pipeline_type == PipelineType.EPOCH_DIRECT:
            scored_data = self._process_epoch_direct(data, algorithm)
        else:
            # Should never reach here due to validation
            raise IncompatiblePipelineError(
                data_source=data_source,
                algorithm_requirement=algorithm.data_requirement,
                algorithm_name=algorithm.name,
            )

        # Find the score column (all algorithms output "Sleep Score")
        score_column = self._find_score_column(scored_data)

        # Wrap result
        result = PipelineResult(
            scored_data=scored_data,
            pipeline_type=pipeline_type,
            data_source=data_source,
            algorithm_name=algorithm.name,
            metadata={
                "num_epochs": len(scored_data),
                "sleep_epochs": int(scored_data[score_column].sum()),
                "sleep_percentage": float(scored_data[score_column].mean() * 100),
                "score_column": score_column,
            },
        )

        if result.metadata:
            logger.info(f"Pipeline completed: {result.metadata['num_epochs']} epochs, {result.metadata['sleep_percentage']:.1f}% sleep")

        return result

    def _process_raw_to_raw(
        self,
        data: pd.DataFrame,
        algorithm: SleepScoringAlgorithm,
    ) -> pd.DataFrame:
        """
        Pipeline 1A: Raw data → Raw-data algorithm (NO epoching).

        This pipeline processes raw tri-axial accelerometer data directly
        with algorithms that operate on raw data (Van Hees SIB, HDCZA).

        Args:
            data: DataFrame with raw tri-axial data (AXIS_X, AXIS_Y, AXIS_Z)
            algorithm: Raw-data algorithm (Van Hees SIB, HDCZA)

        Returns:
            DataFrame with Sleep Score column at 60s resolution

        """
        logger.debug("Executing RAW_TO_RAW pipeline")

        # Raw-data algorithms handle everything internally
        # (calibration, z-angle calculation, scoring, resampling to 60s)
        return algorithm.score(data)

    def _process_raw_to_epoch(
        self,
        data: pd.DataFrame,
        algorithm: SleepScoringAlgorithm,
    ) -> pd.DataFrame:
        """
        Pipeline 1B: Raw data → Epoch → Epoch-based algorithm (WITH epoching).

        This pipeline epochs raw tri-axial data to 60-second counts, then
        applies epoch-based algorithms (Sadeh, Cole-Kripke).

        Args:
            data: DataFrame with raw tri-axial data (AXIS_X, AXIS_Y, AXIS_Z)
            algorithm: Epoch-based algorithm (Sadeh, Cole-Kripke)

        Returns:
            DataFrame with Sleep Score column at 60s resolution

        Raises:
            RuntimeError: If epoching service was not provided during initialization

        """
        logger.debug("Executing RAW_TO_EPOCH pipeline")

        if self._epoching_service is None:
            msg = "RAW_TO_EPOCH pipeline requires an epoching service. Pass it to PipelineOrchestrator.__init__()"
            raise RuntimeError(msg)

        # Epoch raw data to 60-second counts
        epoch_data = self._epoching_service.create_epochs(data, epoch_seconds=60)

        logger.debug(f"Epoched raw data: {len(epoch_data)} 60-second epochs")

        # Apply epoch-based algorithm
        return algorithm.score(epoch_data)

    def _process_epoch_direct(
        self,
        data: pd.DataFrame,
        algorithm: SleepScoringAlgorithm,
    ) -> pd.DataFrame:
        """
        Pipeline 2A: Pre-epoched data → Epoch-based algorithm (DIRECT).

        This pipeline directly applies epoch-based algorithms to pre-epoched
        CSV data without any preprocessing.

        Args:
            data: DataFrame with pre-epoched data (Axis1 column, 60s intervals)
            algorithm: Epoch-based algorithm (Sadeh, Cole-Kripke)

        Returns:
            DataFrame with Sleep Score column

        """
        logger.debug("Executing EPOCH_DIRECT pipeline")

        # Direct scoring (no preprocessing needed)
        return algorithm.score(data)

    def _find_score_column(self, df: pd.DataFrame) -> str:
        """
        Find the score column in the result DataFrame.

        All algorithms output to a generic "Sleep Score" column defined by
        AlgorithmOutputColumn.SLEEP_SCORE.

        Args:
            df: DataFrame with scoring results

        Returns:
            Name of the score column

        Raises:
            ValueError: If no score column is found

        """
        # Common score column patterns (all algorithms now output generic "Sleep Score")
        score_columns = [AlgorithmOutputColumn.SLEEP_SCORE, "score"]

        for col in score_columns:
            if col in df.columns:
                return col

        # Fallback: look for any column with "score" in the name (case-insensitive)
        for col in df.columns:
            if "score" in col.lower():
                return col

        # If still not found, raise error
        msg = f"No score column found in DataFrame. Available columns: {list(df.columns)}"
        raise ValueError(msg)
