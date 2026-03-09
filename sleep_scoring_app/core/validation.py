#!/usr/bin/env python3
"""
Input Validation Module for Sleep Scoring Application
Provides comprehensive validation for all inputs and data.
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from sleep_scoring_app.core.exceptions import ErrorCodes, SecurityError, ValidationError


class InputValidator:
    """Comprehensive input validation for the sleep scoring application."""

    PATH_TRAVERSAL_PATTERN = re.compile(r"\.\.[\\/]")
    INJECTION_PATTERNS: ClassVar[list[re.Pattern[str]]] = [
        re.compile(r'[<>"\']'),
        re.compile(r"[\x00-\x1f\x7f-\x9f]"),
        re.compile(r"\\x[0-9a-fA-F]{2}"),
    ]

    TIME_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]?\d)$")
    DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    ALLOWED_EXTENSIONS: ClassVar[set[str]] = {".csv", ".json", ".db", ".log"}
    MAX_FILENAME_LENGTH = 255
    MAX_PATH_LENGTH = 4096

    @staticmethod
    def validate_file_path(
        file_path: str | Path,
        must_exist: bool = True,
        allowed_extensions: set[str] | frozenset[str] | None = None,
    ) -> Path:
        """
        Validate file path for security and existence.

        Args:
            file_path: Path to validate
            must_exist: Whether file must exist
            allowed_extensions: Set of allowed file extensions

        Returns:
            Validated Path object

        Raises:
            ValidationError: If path is invalid
            SecurityError: If path poses security risk

        """
        if not file_path:
            msg = "File path cannot be empty"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        path = Path(file_path)

        if len(str(path)) > InputValidator.MAX_PATH_LENGTH:
            msg = f"Path too long: {len(str(path))} > {InputValidator.MAX_PATH_LENGTH}"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_INPUT,
            )

        if InputValidator.PATH_TRAVERSAL_PATTERN.search(str(path)):
            msg = f"Path traversal attempt detected: {path}"
            raise SecurityError(msg, ErrorCodes.PATH_TRAVERSAL)

        if len(path.name) > InputValidator.MAX_FILENAME_LENGTH:
            msg = f"Filename too long: {len(path.name)} > {InputValidator.MAX_FILENAME_LENGTH}"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_INPUT,
            )

        if allowed_extensions and path.suffix.lower() not in allowed_extensions:
            msg = f"Invalid file extension: {path.suffix}. Allowed: {allowed_extensions}"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_FORMAT,
            )

        if must_exist and not path.exists():
            msg = f"File does not exist: {path}"
            raise ValidationError(msg, ErrorCodes.FILE_NOT_FOUND)

        if must_exist and path.exists() and not path.is_file():
            msg = f"Path is not a file: {path}"
            raise ValidationError(msg, ErrorCodes.INVALID_INPUT)

        return path

    @staticmethod
    def validate_directory_path(dir_path: str | Path, must_exist: bool = True, create_if_missing: bool = False) -> Path:
        """
        Validate directory path for security and existence.

        Args:
            dir_path: Directory path to validate
            must_exist: Whether directory must exist
            create_if_missing: Whether to create if missing

        Returns:
            Validated Path object

        Raises:
            ValidationError: If path is invalid
            SecurityError: If path poses security risk

        """
        if not dir_path:
            msg = "Directory path cannot be empty"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        path = Path(dir_path)

        if len(str(path)) > InputValidator.MAX_PATH_LENGTH:
            msg = f"Path too long: {len(str(path))} > {InputValidator.MAX_PATH_LENGTH}"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_INPUT,
            )

        if InputValidator.PATH_TRAVERSAL_PATTERN.search(str(path)):
            msg = f"Path traversal attempt detected: {path}"
            raise SecurityError(msg, ErrorCodes.PATH_TRAVERSAL)

        if must_exist and not path.exists():
            if create_if_missing:
                try:
                    path.mkdir(parents=True, exist_ok=True, mode=0o755)
                except OSError as e:
                    msg = f"Cannot create directory: {path}. Error: {e}"
                    raise ValidationError(
                        msg,
                        ErrorCodes.FILE_PERMISSION_DENIED,
                    ) from e
            else:
                msg = f"Directory does not exist: {path}"
                raise ValidationError(msg, ErrorCodes.FILE_NOT_FOUND)

        if path.exists() and not path.is_dir():
            msg = f"Path is not a directory: {path}"
            raise ValidationError(msg, ErrorCodes.INVALID_INPUT)

        return path

    @staticmethod
    def validate_time_string(time_str: str) -> tuple[int, int]:
        """
        Validate time string in HH:MM format.

        Args:
            time_str: Time string to validate

        Returns:
            Tuple of (hour, minute)

        Raises:
            ValidationError: If time format is invalid

        """
        if not time_str:
            msg = "Time string cannot be empty"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        for pattern in InputValidator.INJECTION_PATTERNS:
            if pattern.search(time_str):
                msg = f"Potential injection attempt in time string: {time_str}"
                raise SecurityError(
                    msg,
                    ErrorCodes.INJECTION_ATTEMPT,
                )

        match = InputValidator.TIME_PATTERN.match(time_str.strip())
        if not match:
            msg = f"Invalid time format: {time_str}. Expected HH:MM"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_FORMAT,
            )

        hour, minute = int(match.group(1)), int(match.group(2))

        if not (0 <= hour <= 23):
            msg = f"Invalid hour: {hour}. Must be 0-23"
            raise ValidationError(msg, ErrorCodes.OUT_OF_RANGE)

        if not (0 <= minute <= 59):
            msg = f"Invalid minute: {minute}. Must be 0-59"
            raise ValidationError(msg, ErrorCodes.OUT_OF_RANGE)

        return hour, minute

    @staticmethod
    def validate_timestamp(timestamp: float) -> float:
        """
        Validate timestamp value.

        Args:
            timestamp: Timestamp to validate

        Returns:
            Validated timestamp as float

        Raises:
            ValidationError: If timestamp is invalid

        """
        if timestamp is None:
            msg = "Timestamp cannot be None"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        if not isinstance(timestamp, int | float):
            msg = f"Timestamp must be numeric, got {type(timestamp)}"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_INPUT,
            )

        if timestamp < 0:
            msg = f"Timestamp cannot be negative: {timestamp}"
            raise ValidationError(msg, ErrorCodes.OUT_OF_RANGE)

        if not (0 <= timestamp <= 4102444800):  # Year 2100
            msg = f"Timestamp out of reasonable range: {timestamp}"
            raise ValidationError(
                msg,
                ErrorCodes.OUT_OF_RANGE,
            )

        try:
            datetime.fromtimestamp(timestamp)
        except (ValueError, OSError) as e:
            msg = f"Invalid timestamp: {timestamp}. Error: {e}"
            raise ValidationError(msg, ErrorCodes.INVALID_INPUT) from e

        return float(timestamp)

    @staticmethod
    def validate_integer(
        value: Any,
        min_val: int | None = None,
        max_val: int | None = None,
        name: str = "value",
    ) -> int:
        """
        Validate integer value with optional range checking.

        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            name: Name for error messages

        Returns:
            Validated integer

        Raises:
            ValidationError: If value is invalid

        """
        if value is None:
            msg = f"{name} cannot be None"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        if not isinstance(value, int):
            try:
                value = int(value)
            except (ValueError, TypeError) as e:
                msg = f"{name} must be an integer, got {type(value)}"
                raise ValidationError(
                    msg,
                    ErrorCodes.INVALID_INPUT,
                ) from e

        if min_val is not None and value < min_val:
            msg = f"{name} must be >= {min_val}, got {value}"
            raise ValidationError(msg, ErrorCodes.OUT_OF_RANGE)

        if max_val is not None and value > max_val:
            msg = f"{name} must be <= {max_val}, got {value}"
            raise ValidationError(msg, ErrorCodes.OUT_OF_RANGE)

        return value

    @staticmethod
    def validate_float(
        value: Any,
        min_val: float | None = None,
        max_val: float | None = None,
        name: str = "value",
    ) -> float:
        """
        Validate float value with optional range checking.

        Args:
            value: Value to validate
            min_val: Minimum allowed value
            max_val: Maximum allowed value
            name: Name for error messages

        Returns:
            Validated float

        Raises:
            ValidationError: If value is invalid

        """
        if value is None:
            msg = f"{name} cannot be None"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        if not isinstance(value, int | float):
            try:
                value = float(value)
            except (ValueError, TypeError) as e:
                msg = f"{name} must be numeric, got {type(value)}"
                raise ValidationError(
                    msg,
                    ErrorCodes.INVALID_INPUT,
                ) from e

        if min_val is not None and value < min_val:
            msg = f"{name} must be >= {min_val}, got {value}"
            raise ValidationError(msg, ErrorCodes.OUT_OF_RANGE)

        if max_val is not None and value > max_val:
            msg = f"{name} must be <= {max_val}, got {value}"
            raise ValidationError(msg, ErrorCodes.OUT_OF_RANGE)

        return float(value)

    @staticmethod
    def validate_string(value: Any, min_length: int = 0, max_length: int = 10000, name: str = "value") -> str:
        """
        Validate string value with length and content checking.

        Args:
            value: Value to validate
            min_length: Minimum string length
            max_length: Maximum string length
            name: Name for error messages

        Returns:
            Validated string

        Raises:
            ValidationError: If value is invalid
            SecurityError: If value poses security risk

        """
        if value is None:
            msg = f"{name} cannot be None"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        if not isinstance(value, str):
            value = str(value)

        if len(value) < min_length:
            msg = f"{name} must be at least {min_length} characters, got {len(value)}"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_INPUT,
            )

        if len(value) > max_length:
            msg = f"{name} must be at most {max_length} characters, got {len(value)}"
            raise ValidationError(
                msg,
                ErrorCodes.INVALID_INPUT,
            )

        for pattern in InputValidator.INJECTION_PATTERNS:
            if pattern.search(value):
                msg = f"Potential injection attempt in {name}: {value}"
                raise SecurityError(
                    msg,
                    ErrorCodes.INJECTION_ATTEMPT,
                )

        return value

    @staticmethod
    def validate_array_bounds(array: list[Any], index: int, name: str = "array") -> None:
        """
        Validate array index bounds.

        Args:
            array: Array to check
            index: Index to validate
            name: Name for error messages

        Raises:
            ValidationError: If index is out of bounds

        """
        if not array:
            msg = f"{name} cannot be empty"
            raise ValidationError(msg, ErrorCodes.INVALID_INPUT)

        if not isinstance(index, int):
            msg = f"Index must be integer, got {type(index)}"
            raise ValidationError(msg, ErrorCodes.INVALID_INPUT)

        if index < 0 or index >= len(array):
            msg = f"Index {index} out of bounds for {name} of length {len(array)}"
            raise ValidationError(
                msg,
                ErrorCodes.OUT_OF_RANGE,
            )

    @staticmethod
    def validate_disk_space(file_path: str | Path, required_bytes: int) -> None:
        """
        Validate available disk space.

        Args:
            file_path: Path to check disk space for
            required_bytes: Required bytes

        Raises:
            ValidationError: If insufficient disk space

        """
        path = Path(file_path)

        try:
            free_bytes = shutil.disk_usage(path.parent).free

            if free_bytes < required_bytes:
                msg = f"Insufficient disk space. Required: {required_bytes} bytes, Available: {free_bytes} bytes"
                raise ValidationError(
                    msg,
                    ErrorCodes.DISK_FULL,
                )
        except OSError as e:
            msg = f"Cannot check disk space for {path}: {e}"
            raise ValidationError(
                msg,
                ErrorCodes.FILE_PERMISSION_DENIED,
            ) from e

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename for safe usage.

        Args:
            filename: Filename to sanitize

        Returns:
            Sanitized filename

        """
        if not filename:
            return "unnamed"

        filename = Path(filename).name
        sanitized = re.sub(r'[<>:"/\\|?*]', "_", filename)
        sanitized = "".join(c for c in sanitized if ord(c) >= 32)

        if len(sanitized) > InputValidator.MAX_FILENAME_LENGTH:
            name, ext = os.path.splitext(sanitized)
            max_name_length = InputValidator.MAX_FILENAME_LENGTH - len(ext)
            sanitized = name[:max_name_length] + ext

        if not sanitized:
            sanitized = "unnamed"

        return sanitized
