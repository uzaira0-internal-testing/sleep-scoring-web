"""
Type definitions for dual-pipeline architecture.

This module defines the core enums that distinguish between:
1. Data source types (raw vs pre-epoched)
2. Algorithm data requirements (raw vs epoch data)
3. Pipeline configurations (the 4 distinct paths)

All types use StrEnum for type safety and explicit values.

Example Usage:
    >>> from sleep_scoring_app.core.pipeline import (
    ...     DataSourceType,
    ...     AlgorithmDataRequirement,
    ...     PipelineType,
    ... )
    >>>
    >>> # Data source classification
    >>> if data_source == DataSourceType.GT3X_RAW:
    ...     print("Raw GT3X file detected")
    >>>
    >>> # Algorithm classification
    >>> if algorithm.data_requirement == AlgorithmDataRequirement.EPOCH_DATA:
    ...     print("Requires 60-second epoch counts")
    >>>
    >>> # Pipeline routing
    >>> if pipeline_type == PipelineType.RAW_TO_EPOCH:
    ...     print("Will epoch raw data before scoring")

References:
    - CLAUDE.md: Use StrEnum for all categorical values
    - Protocol-first design patterns

"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    import pandas as pd


class DataSourceType(StrEnum):
    """
    Type of data source based on file format and content.

    This enum distinguishes between raw high-frequency accelerometer data
    and pre-aggregated epoch count data.

    Attributes:
        GT3X_RAW: GT3X binary file containing raw tri-axial data (~30-100 Hz)
        CSV_RAW: CSV file with raw tri-axial data (timestamp, X, Y, Z columns)
        CSV_EPOCH: CSV file with pre-aggregated epoch counts (60-second Axis1)

    Detection Logic:
        - GT3X files -> GT3X_RAW (always raw data)
        - CSV with AXIS_X, AXIS_Y, AXIS_Z columns -> CSV_RAW
        - CSV with Axis1/Activity column + ~60s intervals -> CSV_EPOCH

    """

    GT3X_RAW = "gt3x_raw"
    CSV_RAW = "csv_raw"
    CSV_EPOCH = "csv_epoch"

    def is_raw(self) -> bool:
        """Check if this data source contains raw high-frequency data."""
        return self in (DataSourceType.GT3X_RAW, DataSourceType.CSV_RAW)

    def is_epoched(self) -> bool:
        """Check if this data source contains pre-aggregated epoch data."""
        return self == DataSourceType.CSV_EPOCH


class AlgorithmDataRequirement(StrEnum):
    """
    Data type required by a sleep scoring algorithm.

    This enum specifies whether an algorithm operates on raw data or epoch data.
    Used to enforce compatibility between algorithms and data sources.

    Attributes:
        RAW_DATA: Algorithm requires raw tri-axial accelerometer data
                  Examples: Van Hees SIB (2015), HDCZA (2018)
        EPOCH_DATA: Algorithm requires pre-aggregated 60-second epoch counts
                    Examples: Sadeh (1994), Cole-Kripke (1992)

    Compatibility Rules:
        - RAW_DATA algorithms can ONLY process GT3X_RAW or CSV_RAW sources
        - EPOCH_DATA algorithms can process CSV_EPOCH directly OR epoched raw data
        - Mixing incompatible types raises IncompatiblePipelineError

    """

    RAW_DATA = "raw_data"
    EPOCH_DATA = "epoch_data"


class PipelineType(StrEnum):
    """
    Pipeline configuration for data processing.

    This enum represents the FOUR distinct data processing paths in the
    dual-pipeline architecture. Each path has specific requirements and
    processing steps.

    Pipeline Paths:
        RAW_TO_RAW: Raw data -> Raw-data algorithm (NO epoching)
            - Example: GT3X -> Van Hees SIB
            - Steps: Load -> Calibrate -> Score
            - Output: Sleep/wake at 60s resolution

        RAW_TO_EPOCH: Raw data -> Epoch -> Epoch-based algorithm (WITH epoching)
            - Example: GT3X -> 60s epochs -> Sadeh
            - Steps: Load -> Calibrate -> Epoch -> Score
            - Output: Sleep/wake at 60s resolution

        EPOCH_DIRECT: Pre-epoched data -> Epoch-based algorithm (DIRECT)
            - Example: 60s CSV -> Sadeh
            - Steps: Load -> Score
            - Output: Sleep/wake at 60s resolution

        INCOMPATIBLE: Blocked combination (RAISES ERROR)
            - Example: 60s CSV -> Van Hees SIB (INVALID)
            - Reason: Cannot recover raw data from epoch counts
            - Action: Raise IncompatiblePipelineError

    Usage:
        >>> orchestrator = PipelineOrchestrator()
        >>> pipeline = orchestrator.determine_pipeline_type(source, algorithm)
        >>> if pipeline == PipelineType.INCOMPATIBLE:
        ...     raise IncompatiblePipelineError(...)

    """

    RAW_TO_RAW = "raw_to_raw"  # Pipeline 1A
    RAW_TO_EPOCH = "raw_to_epoch"  # Pipeline 1B
    EPOCH_DIRECT = "epoch_direct"  # Pipeline 2A
    INCOMPATIBLE = "incompatible"  # Pipeline 2B (blocked)

    def is_valid(self) -> bool:
        """Check if this pipeline configuration is executable."""
        return self != PipelineType.INCOMPATIBLE

    def requires_epoching(self) -> bool:
        """Check if this pipeline requires epoching raw data."""
        return self == PipelineType.RAW_TO_EPOCH

    def is_raw_pipeline(self) -> bool:
        """Check if this pipeline starts with raw data."""
        return self in (PipelineType.RAW_TO_RAW, PipelineType.RAW_TO_EPOCH)

    def is_epoch_pipeline(self) -> bool:
        """Check if this pipeline starts with epoch data."""
        return self == PipelineType.EPOCH_DIRECT


@runtime_checkable
class EpochingService(Protocol):
    """
    Protocol for epoching raw accelerometer data.

    This protocol abstracts the epoching functionality needed by the
    pipeline orchestrator, avoiding direct service dependency.
    """

    def create_epochs(
        self,
        data: pd.DataFrame,
        epoch_seconds: int = 60,
    ) -> pd.DataFrame:
        """
        Create epochs from raw accelerometer data.

        Args:
            data: DataFrame with raw tri-axial data (AXIS_X, AXIS_Y, AXIS_Z)
            epoch_seconds: Epoch duration in seconds (default: 60)

        Returns:
            DataFrame with epoched data at specified resolution

        """
        ...
