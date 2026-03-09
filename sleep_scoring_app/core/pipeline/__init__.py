"""
Pipeline orchestration for dual-pipeline architecture.

This package handles routing between different data processing paths:
- Raw data pipelines (GT3X, raw CSV)
- Pre-epoched data pipelines (60s CSV)

And ensures algorithm compatibility:
- Raw-data algorithms (Van Hees SIB, HDCZA)
- Epoch-based algorithms (Sadeh, Cole-Kripke)

Architecture:
    - types: Enums for data sources, algorithms, and pipeline types
    - detector: Automatic data source type detection
    - orchestrator: Pipeline routing and compatibility checking
    - exceptions: Pipeline-specific exceptions

Example Usage:
    >>> from sleep_scoring_app.core.pipeline import (
    ...     PipelineOrchestrator,
    ...     DataSourceDetector,
    ...     AlgorithmDataRequirement,
    ... )
    >>>
    >>> # Detect data source type
    >>> detector = DataSourceDetector()
    >>> source_type = detector.detect_from_file("data.csv")
    >>>
    >>> # Create orchestrator
    >>> orchestrator = PipelineOrchestrator()
    >>>
    >>> # Check compatibility
    >>> if orchestrator.is_compatible(source_type, algorithm):
    ...     result = orchestrator.process(source_type, file_path, algorithm)

References:
    - CLAUDE.md: Pipeline architecture patterns
    - Protocol-first design with StrEnum constants

"""

from __future__ import annotations

from .detector import DataSourceDetector
from .exceptions import IncompatiblePipelineError, PipelineError
from .orchestrator import PipelineOrchestrator
from .types import (
    AlgorithmDataRequirement,
    DataSourceType,
    PipelineType,
)

__all__ = [
    "AlgorithmDataRequirement",
    # Detector
    "DataSourceDetector",
    # Core types
    "DataSourceType",
    "IncompatiblePipelineError",
    # Exceptions
    "PipelineError",
    # Orchestrator
    "PipelineOrchestrator",
    "PipelineType",
]
