#!/usr/bin/env python3
"""
Custom Exception Classes for Sleep Scoring Application
Provides structured error handling with specific exception types.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any


class SleepScoringError(Exception):
    """Base exception for all sleep scoring application errors."""

    def __init__(self, message: str, error_code: str | None = None, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.context = context or {}

    def __str__(self) -> str:
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message


class ValidationError(SleepScoringError):
    """Raised when input validation fails."""


class DatabaseError(SleepScoringError):
    """Raised when database operations fail."""


class DataIntegrityError(SleepScoringError):
    """Raised when data integrity is compromised."""


class FileOperationError(SleepScoringError):
    """Raised when file operations fail."""


class DataLoadingError(SleepScoringError):
    """Raised when data loading fails."""


class InvalidFileFormatError(DataLoadingError):
    """Raised when file format is invalid."""


class AlgorithmError(SleepScoringError):
    """Raised when algorithm execution fails."""


class ResourceError(SleepScoringError):
    """Raised when resource allocation or cleanup fails."""


class SecurityError(SleepScoringError):
    """Raised when security violations are detected."""


class ConfigurationError(SleepScoringError):
    """Raised when configuration is invalid."""


class SleepScoringMemoryError(SleepScoringError):
    """Raised when memory limits are exceeded."""


class SleepScoringImportError(SleepScoringError):
    """Raised when import fails."""


# Error codes for specific error types
class ErrorCodes(StrEnum):
    """Standardized error codes."""

    # Validation errors
    INVALID_INPUT = "INVALID_INPUT"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    INVALID_FORMAT = "INVALID_FORMAT"
    MISSING_REQUIRED = "MISSING_REQUIRED"

    # Database errors
    DB_CONNECTION_FAILED = "DB_CONNECTION_FAILED"
    DB_QUERY_FAILED = "DB_QUERY_FAILED"
    DB_INTEGRITY_VIOLATION = "DB_INTEGRITY_VIOLATION"
    DB_INSERT_FAILED = "DB_INSERT_FAILED"
    DB_DELETE_FAILED = "DB_DELETE_FAILED"

    # File operation errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_PERMISSION_DENIED = "FILE_PERMISSION_DENIED"
    FILE_CORRUPTED = "FILE_CORRUPTED"
    FILE_OPERATION_FAILED = "FILE_OPERATION_FAILED"
    DISK_FULL = "DISK_FULL"

    # Security errors
    PATH_TRAVERSAL = "PATH_TRAVERSAL"
    INJECTION_ATTEMPT = "INJECTION_ATTEMPT"
    ACCESS_DENIED = "ACCESS_DENIED"

    # Resource errors
    MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED"
    RESOURCE_EXHAUSTED = "RESOURCE_EXHAUSTED"
    TIMEOUT = "TIMEOUT"

    # Algorithm errors
    ALGORITHM_FAILED = "ALGORITHM_FAILED"
    INVALID_ALGORITHM_INPUT = "INVALID_ALGORITHM_INPUT"

    # Configuration errors
    CONFIG_INVALID = "CONFIG_INVALID"
    CONFIG_MISSING = "CONFIG_MISSING"

    # Import errors
    IMPORT_FAILED = "IMPORT_FAILED"

    # Data format errors
    VALIDATION_FAILED = "VALIDATION_FAILED"
    FILE_READ_ERROR = "FILE_READ_ERROR"
    UNSUPPORTED_FILE_FORMAT = "UNSUPPORTED_FILE_FORMAT"
