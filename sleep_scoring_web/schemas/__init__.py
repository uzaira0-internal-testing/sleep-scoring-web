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
    DateStatus,
    ExportColumnCategory,
    ExportColumnInfo,
    ExportColumnsResponse,
    ExportRequest,
    ExportResponse,
    FileInfo,
    FileUploadResponse,
    FullTableDataPoint,
    FullTableResponse,
    ManualNonwearPeriod,
    MarkerResponse,
    MarkerUpdateRequest,
    OnsetOffsetDataPoint,
    OnsetOffsetTableResponse,
    SleepMetrics,
    SleepPeriod,
)

__all__ = [
    # Models
    "ActivityDataColumnar",
    "ActivityDataResponse",
    # Enums
    "AlgorithmType",
    # Date status
    "DateStatus",
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
    # Table models
    "FullTableDataPoint",
    "FullTableResponse",
    # Markers
    "ManualNonwearPeriod",
    "MarkerCategory",
    "MarkerResponse",
    "MarkerType",
    "MarkerUpdateRequest",
    "NonwearAlgorithm",
    "OnsetOffsetDataPoint",
    "OnsetOffsetTableResponse",
    "SleepMetrics",
    "SleepPeriod",
    "SleepPeriodDetectorType",
    # Auth enums
    "UserRole",
    "VerificationStatus",
]
