"""
Pydantic schemas for the Sleep Scoring Web API.

This package contains all Pydantic models that serve as the
single source of truth for both API validation and OpenAPI generation.
"""

from .enums import (
    AlgorithmType,
    FileStatus,
    MarkerCategory,
    MarkerType,
    NonwearAlgorithm,
    SleepPeriodDetectorType,
    UserRole,
    VerificationStatus,
)
from .models import (
    ActivityDataColumnar,
    ActivityDataResponse,
    ExportColumnCategory,
    ExportColumnInfo,
    ExportColumnsResponse,
    ExportRequest,
    ExportResponse,
    FileInfo,
    FileUploadResponse,
    ManualNonwearPeriod,
    MarkerResponse,
    MarkerUpdateRequest,
    SleepMetrics,
    SleepPeriod,
)

__all__ = [
    # Models
    "ActivityDataColumnar",
    "ActivityDataResponse",
    # Enums
    "AlgorithmType",
    # Export
    "ExportColumnCategory",
    "ExportColumnInfo",
    "ExportColumnsResponse",
    "ExportRequest",
    "ExportResponse",
    # Files
    "FileInfo",
    "FileStatus",
    "FileUploadResponse",
    # Markers
    "ManualNonwearPeriod",
    "MarkerCategory",
    "MarkerResponse",
    "MarkerType",
    "MarkerUpdateRequest",
    "NonwearAlgorithm",
    "SleepMetrics",
    "SleepPeriod",
    "SleepPeriodDetectorType",
    # Auth enums
    "UserRole",
    "VerificationStatus",
]
