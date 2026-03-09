#!/usr/bin/env python3
"""
Unit tests for Diary Mapping Helper Utilities.

Tests comprehensive functionality for:
- Comma-separated column name parsing
- Date and time string parsing and validation
- Auto-calculation flag checking
- Default value handling for missing columns
- Boolean field extraction with custom values
- Column name normalization and matching
- Diary mapping validation
"""

from __future__ import annotations

import pandas as pd
import pytest

from sleep_scoring_app.core.dataclasses import DiaryColumnMapping
from sleep_scoring_app.services.diary_mapper import DiaryMappingHelpers


@pytest.mark.unit
class TestDiaryMappingHelpers:
    """Test DiaryMappingHelpers utility functions."""

    def test_parse_comma_separated_columns_valid(self):
        """Test parsing valid comma-separated column names."""
        # Test normal case
        result = DiaryMappingHelpers.parse_comma_separated_columns("col1, col2, col3")
        assert result == ["col1", "col2", "col3"]

        # Test with extra spaces
        result = DiaryMappingHelpers.parse_comma_separated_columns("  col1  ,  col2  ,  col3  ")
        assert result == ["col1", "col2", "col3"]

        # Test single column
        result = DiaryMappingHelpers.parse_comma_separated_columns("single_col")
        assert result == ["single_col"]

        # Test empty strings filtered out
        result = DiaryMappingHelpers.parse_comma_separated_columns("col1, , col3, ")
        assert result == ["col1", "col3"]

    def test_parse_comma_separated_columns_invalid(self):
        """Test parsing invalid inputs."""
        # Test None input
        result = DiaryMappingHelpers.parse_comma_separated_columns(None)
        assert result == []

        # Test empty string
        result = DiaryMappingHelpers.parse_comma_separated_columns("")
        assert result == []

        # Test non-string input
        result = DiaryMappingHelpers.parse_comma_separated_columns(123)
        assert result == []

    def test_extract_multiple_values_from_columns(self):
        """Test extracting values from multiple columns."""
        # Create test row data
        row = pd.Series({"reason1": "shower", "reason2": "exercise", "reason3": "", "reason4": "work"})

        # Test normal case
        result = DiaryMappingHelpers.extract_multiple_values_from_columns(row, "reason1,reason2,reason4")
        assert result == "shower; exercise; work"

        # Test with empty values
        result = DiaryMappingHelpers.extract_multiple_values_from_columns(row, "reason1,reason3,reason2")
        assert result == "shower; exercise"

        # Test custom separator
        result = DiaryMappingHelpers.extract_multiple_values_from_columns(row, "reason1,reason2", separator=" | ")
        assert result == "shower | exercise"

        # Test no valid columns
        result = DiaryMappingHelpers.extract_multiple_values_from_columns(row, "invalid_col1,invalid_col2")
        assert result is None

        # Test None column names
        result = DiaryMappingHelpers.extract_multiple_values_from_columns(row, None)
        assert result is None

    def test_parse_time_string_valid_formats(self):
        """Test parsing various valid time formats."""
        # Test standard HH:MM format
        assert DiaryMappingHelpers.parse_time_string("23:30") == "23:30"
        assert DiaryMappingHelpers.parse_time_string("07:00") == "07:00"

        # Test single digit hours
        assert DiaryMappingHelpers.parse_time_string("7:30") == "07:30"

        # Test HHMM format
        assert DiaryMappingHelpers.parse_time_string("2330") == "23:30"
        assert DiaryMappingHelpers.parse_time_string("700") == "07:00"

        # Test 12-hour format with AM/PM
        assert DiaryMappingHelpers.parse_time_string("11:30 PM") == "23:30"
        assert DiaryMappingHelpers.parse_time_string("7:00 AM") == "07:00"
        assert DiaryMappingHelpers.parse_time_string("12:00 AM") == "00:00"
        assert DiaryMappingHelpers.parse_time_string("12:00 PM") == "12:00"

        # Test with seconds (should ignore)
        assert DiaryMappingHelpers.parse_time_string("23:30:45") == "23:30"

        # Test decimal format
        assert DiaryMappingHelpers.parse_time_string("23.30") == "23:30"

    def test_parse_time_string_invalid_formats(self):
        """Test parsing invalid time formats."""
        # Test invalid inputs
        assert DiaryMappingHelpers.parse_time_string(None) is None
        assert DiaryMappingHelpers.parse_time_string("") is None
        assert DiaryMappingHelpers.parse_time_string("invalid") is None

        # Test out of range values
        assert DiaryMappingHelpers.parse_time_string("25:30") is None
        assert DiaryMappingHelpers.parse_time_string("23:60") is None
        assert DiaryMappingHelpers.parse_time_string("2560") is None

    def test_parse_date_string_valid_formats(self):
        """Test parsing various valid date formats."""
        # Test YYYY-MM-DD format
        assert DiaryMappingHelpers.parse_date_string("2025-01-15") == "2025-01-15"

        # Test MM/DD/YYYY format
        assert DiaryMappingHelpers.parse_date_string("1/15/2025") == "2025-01-15"
        assert DiaryMappingHelpers.parse_date_string("01/15/2025") == "2025-01-15"

        # Test MM-DD-YYYY format
        assert DiaryMappingHelpers.parse_date_string("1-15-2025") == "2025-01-15"

        # Test YYYY/MM/DD format
        assert DiaryMappingHelpers.parse_date_string("2025/1/15") == "2025-01-15"

        # Test pandas datetime object
        import pandas as pd

        date_obj = pd.to_datetime("2025-01-15")
        assert DiaryMappingHelpers.parse_date_string(date_obj) == "2025-01-15"

    def test_parse_date_string_invalid_formats(self):
        """Test parsing invalid date formats."""
        # Test invalid inputs
        assert DiaryMappingHelpers.parse_date_string(None) is None
        assert DiaryMappingHelpers.parse_date_string("") is None
        assert DiaryMappingHelpers.parse_date_string("invalid") is None

        # Test out of range values
        assert DiaryMappingHelpers.parse_date_string("2025-13-01") is None
        assert DiaryMappingHelpers.parse_date_string("2025-01-32") is None
        assert DiaryMappingHelpers.parse_date_string("9999-99-99") is None  # Truly invalid date

    def test_extract_time_field_with_validation(self):
        """Test time field extraction with validation and defaults."""
        # Create test row
        row = pd.Series({"valid_time": "23:30", "invalid_time": "invalid", "empty_time": None})

        # Test valid time extraction
        result = DiaryMappingHelpers.extract_time_field_with_validation(row, "valid_time")
        assert result == "23:30"

        # Test invalid time with default
        result = DiaryMappingHelpers.extract_time_field_with_validation(row, "invalid_time", default_value="00:00")
        assert result == "00:00"

        # Test missing column with default
        result = DiaryMappingHelpers.extract_time_field_with_validation(row, "missing_col", default_value="12:00")
        assert result == "12:00"

        # Test None column name
        result = DiaryMappingHelpers.extract_time_field_with_validation(row, None, default_value="06:00")
        assert result == "06:00"

    def test_extract_date_field_with_validation(self):
        """Test date field extraction with validation and defaults."""
        # Create test row
        row = pd.Series({"valid_date": "2025-01-15", "invalid_date": "invalid", "empty_date": None})

        # Test valid date extraction
        result = DiaryMappingHelpers.extract_date_field_with_validation(row, "valid_date")
        assert result == "2025-01-15"

        # Test invalid date with default
        result = DiaryMappingHelpers.extract_date_field_with_validation(row, "invalid_date", default_value="2025-01-01")
        assert result == "2025-01-01"

        # Test missing column with default
        result = DiaryMappingHelpers.extract_date_field_with_validation(row, "missing_col", default_value="2025-01-01")
        assert result == "2025-01-01"

    def test_is_auto_calculated_column(self):
        """Test auto-calculated column checking."""
        # Create mapping with auto-calculated flags
        mapping = DiaryColumnMapping(
            auto_calculated_columns={"sleep_onset_time_column_name": True, "sleep_offset_time_column_name": False, "in_bed_time_column_name": True}
        )

        # Test true case
        assert DiaryMappingHelpers.is_auto_calculated_column(mapping, "sleep_onset_time_column_name") is True

        # Test false case
        assert DiaryMappingHelpers.is_auto_calculated_column(mapping, "sleep_offset_time_column_name") is False

        # Test missing field
        assert DiaryMappingHelpers.is_auto_calculated_column(mapping, "nonexistent_field") is False

        # Test None mapping
        assert DiaryMappingHelpers.is_auto_calculated_column(None, "any_field") is False

        # Test empty auto_calculated_columns
        empty_mapping = DiaryColumnMapping()
        assert DiaryMappingHelpers.is_auto_calculated_column(empty_mapping, "any_field") is False

    def test_extract_boolean_field_with_defaults(self):
        """Test boolean field extraction with custom values and defaults."""
        # Create test row
        row = pd.Series(
            {
                "yes_col": "yes",
                "no_col": "no",
                "true_col": True,
                "false_col": False,
                "numeric_1": 1,
                "numeric_0": 0,
                "custom_true": "occurred",
                "custom_false": "none",
                "invalid": "invalid_value",
                "empty": None,
            }
        )

        # Test standard true/false values
        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "yes_col") is True

        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "no_col") is False

        # Test boolean values
        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "true_col") is True

        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "false_col") is False

        # Test numeric values
        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "numeric_1") is True

        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "numeric_0") is False

        # Test custom true/false values
        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "custom_true", true_values=["occurred"]) is True

        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "custom_false", false_values=["none"]) is False

        # Test default values
        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "invalid", default_value=True) is True

        assert DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "missing_col", default_value=False) is False

    def test_normalize_column_name(self):
        """Test column name normalization."""
        # Test basic normalization
        assert DiaryMappingHelpers.normalize_column_name("Column Name") == "column_name"

        # Test with special characters
        assert DiaryMappingHelpers.normalize_column_name("Column-Name!@#") == "columnname"

        # Test with multiple spaces
        assert DiaryMappingHelpers.normalize_column_name("  Column   Name  ") == "column_name"

        # Test empty string
        assert DiaryMappingHelpers.normalize_column_name("") == ""

        # Test None (should not crash)
        assert DiaryMappingHelpers.normalize_column_name(None) == ""

    def test_find_best_column_match(self):
        """Test finding best column matches using patterns."""
        available_columns = [
            "Participant ID",
            "Sleep Onset Time",
            "Sleep Offset Time",
            "Nap Occurred",
            "Nonwear Start Time 1",
            "Nonwear Start Time 2",
        ]

        # Test exact match (case insensitive)
        result = DiaryMappingHelpers.find_best_column_match(["participant_id"], available_columns)
        assert result == "Participant ID"

        # Test substring match
        result = DiaryMappingHelpers.find_best_column_match(["sleep_onset"], available_columns)
        assert result == "Sleep Onset Time"

        # Test multiple patterns (should return first match)
        result = DiaryMappingHelpers.find_best_column_match(["invalid_pattern", "sleep_offset"], available_columns)
        assert result == "Sleep Offset Time"

        # Test no match
        result = DiaryMappingHelpers.find_best_column_match(["completely_invalid"], available_columns)
        assert result is None

        # Test empty inputs
        result = DiaryMappingHelpers.find_best_column_match([], available_columns)
        assert result is None

        result = DiaryMappingHelpers.find_best_column_match(["pattern"], [])
        assert result is None

    def test_validate_diary_mapping(self):
        """Test diary mapping validation."""
        available_columns = ["Participant ID", "Sleep Onset Time", "Sleep Offset Time", "Nap Occurred", "Nonwear Reason 1", "Nonwear Reason 2"]

        # Create mapping with valid, invalid, and missing fields
        mapping = DiaryColumnMapping(
            participant_id_column_name="Participant ID",  # Valid
            sleep_onset_time_column_name="Sleep Onset Time",  # Valid
            sleep_offset_time_column_name="Invalid Column",  # Invalid
            nonwear_reason_column_names="Nonwear Reason 1,Nonwear Reason 2",  # Valid (multiple)
            napped_column_name=None,  # Missing
        )

        result = DiaryMappingHelpers.validate_diary_mapping(mapping, available_columns)

        # Check that we have results for all categories
        assert "valid" in result
        assert "missing" in result
        assert "invalid" in result

        # Check specific validations
        valid_fields = [item for item in result["valid"] if "participant_id_column_name" in item]
        assert len(valid_fields) == 1

        invalid_fields = [item for item in result["invalid"] if "sleep_offset_time_column_name" in item]
        assert len(invalid_fields) == 1

        missing_fields = [item for item in result["missing"] if item == "napped_column_name"]
        assert len(missing_fields) == 1
