"""
Compute backend abstraction for sleep-scoring-demo.

This package provides a unified interface for computation backends,
allowing the GUI to use gt3x-rs (fast Rust implementation) with
pygt3x as fallback, without hardcoding dependencies.

The backend abstraction provides both low-level operations (parsing,
calibration, imputation) AND algorithm execution (Sadeh, Cole-Kripke,
Van Hees, etc.) through a single dependency injection interface.

Architecture:
    - Protocol-first design using @runtime_checkable Protocol
    - Factory pattern with ClassVar[dict] registry
    - Auto-registration of available backends
    - Priority-based backend selection
    - Constructor injection for loaders and services

Example Usage:
    >>> from sleep_scoring_app.core.backends import BackendFactory, BackendCapability
    >>>
    >>> # Auto-select best available backend
    >>> backend = BackendFactory.create()
    >>> print(backend.name)
    'gt3x-rs (Rust)'  # or 'PyGt3x (Python)' if gt3x-rs unavailable
    >>>
    >>> # Check capabilities
    >>> if backend.supports(BackendCapability.PARSE_GT3X):
    ...     data = backend.parse_gt3x("file.gt3x")
    >>>
    >>> # Use in dependency injection
    >>> from sleep_scoring_app.io.sources import GT3XDataSourceLoader
    >>> loader = GT3XDataSourceLoader(backend=backend)

Components:
    - ComputeBackend: Protocol defining backend interface
    - BackendCapability: StrEnum of all capability flags
    - BackendFactory: Factory for creating backend instances
    - Gt3xRsBackend: Rust implementation (preferred, priority=10)
    - PyGt3xBackend: Python fallback (priority=50)
    - Data types: Frozen dataclasses for results

Backends:
    Priority 10 (Preferred):
        - Gt3xRsBackend: gt3x-rs Rust library (52x faster)

    Priority 50 (Fallback):
        - PyGt3xBackend: Pure Python using pygt3x

References:
    - ARCHITECTURE-PATTERNS.md: Design patterns guide
    - DEVELOPER-PREFERENCES.md: Python conventions
    - COMPONENT_ALLOCATION.md: What belongs where

"""

from __future__ import annotations

# Capabilities
from .capabilities import BackendCapability

# Data types
from .data_types import (
    CalibrationResult,
    CircadianResult,
    EpochData,
    ImputationResult,
    MetricResult,
    NonwearResult,
    RawAccelerometerData,
    SleepDetectionResult,
    SleepScoreResult,
    ValidationResult,
)

# Factory (auto-registers backends on import)
from .factory import BackendFactory

# Backends (optional imports - may not be available)
from .gt3x_rs_backend import Gt3xRsBackend
from .protocol import ComputeBackend
from .pygt3x_backend import PyGt3xBackend

__all__ = [
    # Capabilities
    "BackendCapability",
    # Factory
    "BackendFactory",
    "CalibrationResult",
    "CircadianResult",
    # Protocol
    "ComputeBackend",
    "EpochData",
    # Backend implementations (may not be imported if dependencies missing)
    "Gt3xRsBackend",
    "ImputationResult",
    "MetricResult",
    "NonwearResult",
    "PyGt3xBackend",
    # Data types
    "RawAccelerometerData",
    "SleepDetectionResult",
    "SleepScoreResult",
    "ValidationResult",
]
