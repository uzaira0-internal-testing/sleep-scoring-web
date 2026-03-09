#!/usr/bin/env python3
"""
Comprehensive unit tests for InputValidator.

Tests all validation methods for inputs, paths, and data.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from sleep_scoring_app.core.exceptions import SecurityError, ValidationError
from sleep_scoring_app.core.validation import InputValidator


class TestValidateFilePath:
    """Tests for validate_file_path method."""

    def test_validates_existing_file(self, tmp_path: Path):
        """Returns Path for existing file."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")

        result = InputValidator.validate_file_path(test_file, must_exist=True)

        assert result == test_file

    def test_raises_for_empty_path(self):
        """ValidationError for empty path."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_file_path("")
        assert "empty" in str(exc_info.value).lower()

    def test_raises_for_none_path(self):
        """ValidationError for None path."""
        with pytest.raises(ValidationError):
            InputValidator.validate_file_path(None)

    def test_raises_for_nonexistent_file(self, tmp_path: Path):
        """ValidationError for nonexistent file when must_exist=True."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_file_path(tmp_path / "nonexistent.csv", must_exist=True)
        assert "does not exist" in str(exc_info.value)

    def test_allows_nonexistent_when_must_exist_false(self, tmp_path: Path):
        """Allows nonexistent file when must_exist=False."""
        path = tmp_path / "new_file.csv"
        result = InputValidator.validate_file_path(path, must_exist=False)
        assert result == path

    def test_raises_for_path_traversal(self, tmp_path: Path):
        """SecurityError for path traversal attempt."""
        with pytest.raises(SecurityError) as exc_info:
            InputValidator.validate_file_path(tmp_path / ".." / ".." / "etc" / "passwd")
        assert "traversal" in str(exc_info.value).lower()

    def test_validates_extension(self, tmp_path: Path):
        """Validates allowed extensions."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")

        result = InputValidator.validate_file_path(test_file, must_exist=True, allowed_extensions={".csv", ".json"})
        assert result == test_file

    def test_raises_for_invalid_extension(self, tmp_path: Path):
        """ValidationError for disallowed extension."""
        test_file = tmp_path / "test.exe"
        test_file.write_text("data")

        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_file_path(test_file, must_exist=True, allowed_extensions={".csv", ".json"})
        assert "extension" in str(exc_info.value).lower()

    def test_raises_for_path_too_long(self):
        """ValidationError for path exceeding max length."""
        long_path = "a" * 5000 + ".csv"
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_file_path(long_path, must_exist=False)
        assert "too long" in str(exc_info.value).lower()

    def test_raises_for_filename_too_long(self, tmp_path: Path):
        """ValidationError for filename exceeding max length."""
        long_filename = "a" * 300 + ".csv"
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_file_path(tmp_path / long_filename, must_exist=False)
        assert "too long" in str(exc_info.value).lower()

    def test_raises_for_directory_not_file(self, tmp_path: Path):
        """ValidationError when path is directory, not file."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_file_path(tmp_path, must_exist=True)
        assert "not a file" in str(exc_info.value).lower()

    def test_accepts_string_path(self, tmp_path: Path):
        """Accepts string path."""
        test_file = tmp_path / "test.csv"
        test_file.write_text("data")

        result = InputValidator.validate_file_path(str(test_file), must_exist=True)
        assert result == test_file


class TestValidateDirectoryPath:
    """Tests for validate_directory_path method."""

    def test_validates_existing_directory(self, tmp_path: Path):
        """Returns Path for existing directory."""
        result = InputValidator.validate_directory_path(tmp_path, must_exist=True)
        assert result == tmp_path

    def test_raises_for_empty_path(self):
        """ValidationError for empty path."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_directory_path("")
        assert "empty" in str(exc_info.value).lower()

    def test_raises_for_nonexistent_directory(self, tmp_path: Path):
        """ValidationError for nonexistent directory."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_directory_path(tmp_path / "nonexistent", must_exist=True)
        assert "does not exist" in str(exc_info.value)

    def test_creates_directory_if_missing(self, tmp_path: Path):
        """Creates directory when create_if_missing=True."""
        new_dir = tmp_path / "new_directory"

        result = InputValidator.validate_directory_path(new_dir, must_exist=True, create_if_missing=True)

        assert result == new_dir
        assert new_dir.exists()

    def test_raises_for_path_traversal(self, tmp_path: Path):
        """SecurityError for path traversal attempt."""
        with pytest.raises(SecurityError):
            InputValidator.validate_directory_path(tmp_path / ".." / ".." / "etc")

    def test_raises_for_file_not_directory(self, tmp_path: Path):
        """ValidationError when path is file, not directory."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("data")

        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_directory_path(test_file, must_exist=True)
        assert "not a directory" in str(exc_info.value).lower()


class TestValidateTimeString:
    """Tests for validate_time_string method."""

    def test_validates_valid_time(self):
        """Returns hour, minute for valid time."""
        hour, minute = InputValidator.validate_time_string("14:30")
        assert hour == 14
        assert minute == 30

    def test_validates_midnight(self):
        """Validates midnight (00:00)."""
        hour, minute = InputValidator.validate_time_string("00:00")
        assert hour == 0
        assert minute == 0

    def test_validates_end_of_day(self):
        """Validates end of day (23:59)."""
        hour, minute = InputValidator.validate_time_string("23:59")
        assert hour == 23
        assert minute == 59

    def test_validates_single_digit_hour(self):
        """Validates single digit hour."""
        hour, minute = InputValidator.validate_time_string("9:30")
        assert hour == 9
        assert minute == 30

    def test_raises_for_empty_string(self):
        """ValidationError for empty string."""
        with pytest.raises(ValidationError):
            InputValidator.validate_time_string("")

    def test_raises_for_invalid_format(self):
        """ValidationError for invalid format."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_time_string("14-30")
        assert "format" in str(exc_info.value).lower()

    def test_raises_for_invalid_hour(self):
        """ValidationError for hour > 23."""
        with pytest.raises(ValidationError):
            InputValidator.validate_time_string("25:30")

    def test_raises_for_invalid_minute(self):
        """ValidationError for minute > 59."""
        with pytest.raises(ValidationError):
            InputValidator.validate_time_string("14:60")

    def test_raises_for_injection_attempt(self):
        """SecurityError for injection attempt."""
        with pytest.raises(SecurityError):
            InputValidator.validate_time_string("14:30<script>")

    def test_strips_whitespace(self):
        """Strips whitespace from time string."""
        hour, minute = InputValidator.validate_time_string("  14:30  ")
        assert hour == 14
        assert minute == 30


class TestValidateTimestamp:
    """Tests for validate_timestamp method."""

    def test_validates_valid_timestamp(self):
        """Returns float for valid timestamp."""
        result = InputValidator.validate_timestamp(1704067200.0)  # 2024-01-01
        assert result == 1704067200.0

    def test_validates_integer_timestamp(self):
        """Accepts integer timestamp."""
        result = InputValidator.validate_timestamp(1704067200)
        assert result == 1704067200.0

    def test_raises_for_none(self):
        """ValidationError for None."""
        with pytest.raises(ValidationError):
            InputValidator.validate_timestamp(None)

    def test_raises_for_string(self):
        """ValidationError for string."""
        with pytest.raises(ValidationError):
            InputValidator.validate_timestamp("1704067200")

    def test_raises_for_negative(self):
        """ValidationError for negative timestamp."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_timestamp(-1000)
        assert "negative" in str(exc_info.value).lower()

    def test_raises_for_far_future(self):
        """ValidationError for timestamp beyond year 2100."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_timestamp(5000000000.0)
        assert "range" in str(exc_info.value).lower()


class TestValidateInteger:
    """Tests for validate_integer method."""

    def test_validates_valid_integer(self):
        """Returns int for valid integer."""
        result = InputValidator.validate_integer(42)
        assert result == 42

    def test_converts_string_to_int(self):
        """Converts valid string to int."""
        result = InputValidator.validate_integer("42")
        assert result == 42

    def test_validates_min_value(self):
        """Validates minimum value constraint."""
        result = InputValidator.validate_integer(10, min_val=5)
        assert result == 10

    def test_raises_for_below_min(self):
        """ValidationError when below minimum."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(3, min_val=5, name="count")
        assert ">=" in str(exc_info.value)

    def test_validates_max_value(self):
        """Validates maximum value constraint."""
        result = InputValidator.validate_integer(10, max_val=20)
        assert result == 10

    def test_raises_for_above_max(self):
        """ValidationError when above maximum."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(30, max_val=20, name="count")
        assert "<=" in str(exc_info.value)

    def test_raises_for_none(self):
        """ValidationError for None."""
        with pytest.raises(ValidationError):
            InputValidator.validate_integer(None)

    def test_raises_for_invalid_string(self):
        """ValidationError for non-numeric string."""
        with pytest.raises(ValidationError):
            InputValidator.validate_integer("abc")

    def test_uses_custom_name_in_error(self):
        """Uses custom name in error message."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_integer(None, name="epoch_count")
        assert "epoch_count" in str(exc_info.value)


class TestValidateFloat:
    """Tests for validate_float method."""

    def test_validates_valid_float(self):
        """Returns float for valid float."""
        result = InputValidator.validate_float(3.14)
        assert result == 3.14

    def test_converts_int_to_float(self):
        """Converts integer to float."""
        result = InputValidator.validate_float(42)
        assert result == 42.0
        assert isinstance(result, float)

    def test_converts_string_to_float(self):
        """Converts valid string to float."""
        result = InputValidator.validate_float("3.14")
        assert result == 3.14

    def test_validates_min_value(self):
        """Validates minimum value constraint."""
        result = InputValidator.validate_float(10.5, min_val=5.0)
        assert result == 10.5

    def test_raises_for_below_min(self):
        """ValidationError when below minimum."""
        with pytest.raises(ValidationError):
            InputValidator.validate_float(3.0, min_val=5.0)

    def test_validates_max_value(self):
        """Validates maximum value constraint."""
        result = InputValidator.validate_float(10.5, max_val=20.0)
        assert result == 10.5

    def test_raises_for_above_max(self):
        """ValidationError when above maximum."""
        with pytest.raises(ValidationError):
            InputValidator.validate_float(30.0, max_val=20.0)

    def test_raises_for_none(self):
        """ValidationError for None."""
        with pytest.raises(ValidationError):
            InputValidator.validate_float(None)


class TestValidateString:
    """Tests for validate_string method."""

    def test_validates_valid_string(self):
        """Returns string for valid input."""
        result = InputValidator.validate_string("hello")
        assert result == "hello"

    def test_converts_non_string_to_string(self):
        """Converts non-string to string."""
        result = InputValidator.validate_string(123)
        assert result == "123"

    def test_validates_min_length(self):
        """Validates minimum length constraint."""
        result = InputValidator.validate_string("hello", min_length=3)
        assert result == "hello"

    def test_raises_for_too_short(self):
        """ValidationError when too short."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_string("hi", min_length=5)
        assert "at least" in str(exc_info.value)

    def test_validates_max_length(self):
        """Validates maximum length constraint."""
        result = InputValidator.validate_string("hello", max_length=10)
        assert result == "hello"

    def test_raises_for_too_long(self):
        """ValidationError when too long."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_string("hello world", max_length=5)
        assert "at most" in str(exc_info.value)

    def test_raises_for_none(self):
        """ValidationError for None."""
        with pytest.raises(ValidationError):
            InputValidator.validate_string(None)

    def test_raises_for_injection_attempt(self):
        """SecurityError for injection attempt."""
        with pytest.raises(SecurityError):
            InputValidator.validate_string("hello<script>")

    def test_raises_for_special_characters(self):
        """SecurityError for control characters."""
        with pytest.raises(SecurityError):
            InputValidator.validate_string("hello\x00world")


class TestValidateArrayBounds:
    """Tests for validate_array_bounds method."""

    def test_validates_valid_index(self):
        """Passes for valid index."""
        InputValidator.validate_array_bounds([1, 2, 3], 1)
        # Should not raise

    def test_validates_first_index(self):
        """Validates index 0."""
        InputValidator.validate_array_bounds([1, 2, 3], 0)

    def test_validates_last_index(self):
        """Validates last index."""
        InputValidator.validate_array_bounds([1, 2, 3], 2)

    def test_raises_for_negative_index(self):
        """ValidationError for negative index."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_array_bounds([1, 2, 3], -1)
        assert "out of bounds" in str(exc_info.value).lower()

    def test_raises_for_index_too_large(self):
        """ValidationError for index >= length."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_array_bounds([1, 2, 3], 3)
        assert "out of bounds" in str(exc_info.value).lower()

    def test_raises_for_empty_array(self):
        """ValidationError for empty array."""
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_array_bounds([], 0)
        assert "empty" in str(exc_info.value).lower()

    def test_raises_for_non_integer_index(self):
        """ValidationError for non-integer index."""
        with pytest.raises(ValidationError):
            InputValidator.validate_array_bounds([1, 2, 3], "1")


class TestValidateDiskSpace:
    """Tests for validate_disk_space method."""

    def test_passes_when_enough_space(self, tmp_path: Path):
        """Passes when enough disk space available."""
        test_file = tmp_path / "test.txt"
        # Request 1KB, should have plenty of space
        InputValidator.validate_disk_space(test_file, 1024)

    def test_raises_when_insufficient_space(self, tmp_path: Path):
        """ValidationError when insufficient space."""
        test_file = tmp_path / "test.txt"
        # Request impossibly large amount
        with pytest.raises(ValidationError) as exc_info:
            InputValidator.validate_disk_space(test_file, 10**18)  # 1 exabyte
        assert "insufficient" in str(exc_info.value).lower()


class TestSanitizeFilename:
    """Tests for sanitize_filename method."""

    def test_returns_valid_filename_unchanged(self):
        """Returns valid filename unchanged."""
        result = InputValidator.sanitize_filename("valid_file.csv")
        assert result == "valid_file.csv"

    def test_replaces_invalid_characters(self):
        """Replaces invalid characters with underscore."""
        result = InputValidator.sanitize_filename('file<>:"/\\|?*.csv')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result
        assert "/" not in result
        assert "\\" not in result
        assert "|" not in result
        assert "?" not in result
        assert "*" not in result

    def test_removes_control_characters(self):
        """Removes control characters."""
        result = InputValidator.sanitize_filename("file\x00name.csv")
        assert "\x00" not in result

    def test_truncates_long_filename(self):
        """Truncates filename exceeding max length."""
        long_name = "a" * 300 + ".csv"
        result = InputValidator.sanitize_filename(long_name)
        assert len(result) <= InputValidator.MAX_FILENAME_LENGTH

    def test_preserves_extension_when_truncating(self):
        """Preserves extension when truncating."""
        long_name = "a" * 300 + ".csv"
        result = InputValidator.sanitize_filename(long_name)
        assert result.endswith(".csv")

    def test_returns_unnamed_for_empty(self):
        """Returns 'unnamed' for empty input."""
        result = InputValidator.sanitize_filename("")
        assert result == "unnamed"

    def test_returns_unnamed_for_all_invalid(self):
        """Returns 'unnamed' when all characters are invalid."""
        result = InputValidator.sanitize_filename("\x00\x01\x02")
        assert result == "unnamed"

    def test_extracts_basename_from_path(self):
        """Extracts basename from path."""
        result = InputValidator.sanitize_filename("/path/to/file.csv")
        assert result == "file.csv"
