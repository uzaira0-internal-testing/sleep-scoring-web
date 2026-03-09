"""
Tests for DiaryDataMapper and DiaryMappingHelpers.

Tests diary data mapping from CSV/Excel to database schema.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from sleep_scoring_app.services.diary_mapper import (
    DiaryDataMapper,
    DiaryMappingHelpers,
)


@pytest.fixture
def mapper() -> DiaryDataMapper:
    """Create a DiaryDataMapper instance with minimal config."""
    return DiaryDataMapper({"participant_id_column_name": "participant_id"})


@pytest.fixture
def sample_dataframe() -> pd.DataFrame:
    """Create a sample diary DataFrame."""
    return pd.DataFrame(
        {
            "participant_id": ["1234", "1234"],
            "date_lastnight": ["2024-01-15", "2024-01-16"],
            "sleep_onset_time": ["23:00", "22:30"],
            "sleep_offset_time": ["07:00", "07:30"],
            "napped": ["Yes", "No"],
        }
    )


class TestDiaryDataMapperInit:
    """Tests for DiaryDataMapper initialization."""

    def test_creates_with_config(self) -> None:
        """Creates mapper with configuration."""
        config = {"participant_id_column_name": "participant_id"}
        mapper = DiaryDataMapper(config)

        assert mapper.mapping_config == config

    def test_creates_with_empty_config(self) -> None:
        """Creates mapper with empty configuration."""
        mapper = DiaryDataMapper({})

        assert mapper.mapping_config == {}

    def test_creates_with_none_config(self) -> None:
        """Creates mapper with None configuration."""
        mapper = DiaryDataMapper(None)

        assert mapper.mapping_config == {}


class TestMapDataframeToEntries:
    """Tests for map_dataframe_to_entries method."""

    def test_maps_dataframe_to_entries(self, mapper: DiaryDataMapper, sample_dataframe: pd.DataFrame) -> None:
        """Maps DataFrame rows to DiaryEntry objects."""
        entries = mapper.map_dataframe_to_entries(sample_dataframe, "test.csv")

        assert len(entries) >= 1

    def test_returns_empty_for_empty_dataframe(self, mapper: DiaryDataMapper) -> None:
        """Returns empty list for empty DataFrame."""
        empty_df = pd.DataFrame()

        entries = mapper.map_dataframe_to_entries(empty_df, "test.csv")

        assert entries == []

    def test_sets_filename_on_entries(self, mapper: DiaryDataMapper, sample_dataframe: pd.DataFrame) -> None:
        """Sets filename on mapped entries."""
        entries = mapper.map_dataframe_to_entries(sample_dataframe, "diary.csv")

        if entries:
            assert entries[0].filename == "diary.csv"


class TestExtractParticipantId:
    """Tests for _extract_participant_id method."""

    def test_extracts_from_configured_column(self, mapper: DiaryDataMapper) -> None:
        """Extracts participant ID from configured column."""
        row = pd.Series({"participant_id": "1234", "other": "value"})

        result = mapper._extract_participant_id(row, None)

        assert result == "1234"

    def test_extracts_from_common_column_names(self) -> None:
        """Extracts from common column names as fallback."""
        mapper = DiaryDataMapper({})  # No explicit column config
        row = pd.Series({"subject_id": "5678", "other": "value"})

        result = mapper._extract_participant_id(row, None)

        assert result == "5678"

    def test_returns_none_when_not_found(self) -> None:
        """Returns None when participant ID not found."""
        mapper = DiaryDataMapper({})
        row = pd.Series({"other_column": "value"})

        result = mapper._extract_participant_id(row, None)

        assert result is None


class TestParseTimeString:
    """Tests for DiaryMappingHelpers.parse_time_string method."""

    def test_parses_24h_format(self) -> None:
        """Parses 24-hour time format."""
        result = DiaryMappingHelpers.parse_time_string("14:30")

        assert result == "14:30"

    def test_parses_12h_am_format(self) -> None:
        """Parses 12-hour AM time format."""
        result = DiaryMappingHelpers.parse_time_string("9:30 AM")

        assert result == "09:30"

    def test_parses_12h_pm_format(self) -> None:
        """Parses 12-hour PM time format."""
        result = DiaryMappingHelpers.parse_time_string("2:30 PM")

        assert result == "14:30"

    def test_parses_hhmm_format(self) -> None:
        """Parses HHMM format without colon."""
        result = DiaryMappingHelpers.parse_time_string("2330")

        assert result == "23:30"

    def test_returns_none_for_invalid(self) -> None:
        """Returns None for invalid time string."""
        result = DiaryMappingHelpers.parse_time_string("invalid")

        assert result is None

    def test_returns_none_for_none_input(self) -> None:
        """Returns None for None input."""
        result = DiaryMappingHelpers.parse_time_string(None)

        assert result is None

    def test_returns_none_for_empty_string(self) -> None:
        """Returns None for empty string."""
        result = DiaryMappingHelpers.parse_time_string("")

        assert result is None


class TestParseDateString:
    """Tests for DiaryMappingHelpers.parse_date_string method."""

    def test_parses_iso_format(self) -> None:
        """Parses ISO date format."""
        result = DiaryMappingHelpers.parse_date_string("2024-01-15")

        assert result == "2024-01-15"

    def test_parses_us_format(self) -> None:
        """Parses US date format (MM/DD/YYYY)."""
        result = DiaryMappingHelpers.parse_date_string("01/15/2024")

        assert result == "2024-01-15"

    def test_parses_datetime_object(self) -> None:
        """Parses datetime object."""
        dt = datetime(2024, 1, 15, 10, 30)
        result = DiaryMappingHelpers.parse_date_string(dt)

        assert result == "2024-01-15"

    def test_returns_none_for_invalid(self) -> None:
        """Returns None for invalid date string."""
        result = DiaryMappingHelpers.parse_date_string("invalid")

        assert result is None

    def test_returns_none_for_none_input(self) -> None:
        """Returns None for None input."""
        result = DiaryMappingHelpers.parse_date_string(None)

        assert result is None


class TestParseCommaSeparatedColumns:
    """Tests for DiaryMappingHelpers.parse_comma_separated_columns method."""

    def test_parses_comma_separated_string(self) -> None:
        """Parses comma-separated column names."""
        result = DiaryMappingHelpers.parse_comma_separated_columns("col1, col2, col3")

        assert result == ["col1", "col2", "col3"]

    def test_strips_whitespace(self) -> None:
        """Strips whitespace from column names."""
        result = DiaryMappingHelpers.parse_comma_separated_columns("  col1  ,  col2  ")

        assert result == ["col1", "col2"]

    def test_returns_empty_for_none(self) -> None:
        """Returns empty list for None input."""
        result = DiaryMappingHelpers.parse_comma_separated_columns(None)

        assert result == []

    def test_returns_empty_for_empty_string(self) -> None:
        """Returns empty list for empty string."""
        result = DiaryMappingHelpers.parse_comma_separated_columns("")

        assert result == []

    def test_filters_empty_strings(self) -> None:
        """Filters out empty strings from result."""
        result = DiaryMappingHelpers.parse_comma_separated_columns("col1,,col2")

        assert "" not in result


class TestNormalizeColumnName:
    """Tests for DiaryMappingHelpers.normalize_column_name method."""

    def test_converts_to_lowercase(self) -> None:
        """Converts column name to lowercase."""
        result = DiaryMappingHelpers.normalize_column_name("Column_Name")

        assert result == "column_name"

    def test_replaces_spaces_with_underscores(self) -> None:
        """Replaces spaces with underscores."""
        result = DiaryMappingHelpers.normalize_column_name("Column Name")

        assert result == "column_name"

    def test_removes_special_characters(self) -> None:
        """Removes special characters."""
        result = DiaryMappingHelpers.normalize_column_name("Column@Name#123")

        assert result == "columnname123"

    def test_handles_empty_string(self) -> None:
        """Handles empty string."""
        result = DiaryMappingHelpers.normalize_column_name("")

        assert result == ""


class TestExtractBooleanField:
    """Tests for DiaryMappingHelpers.extract_boolean_field_with_defaults method."""

    def test_extracts_true_values(self) -> None:
        """Extracts True from various true values."""
        row = pd.Series({"flag": "yes"})

        result = DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "flag")

        assert result is True

    def test_extracts_false_values(self) -> None:
        """Extracts False from various false values."""
        row = pd.Series({"flag": "no"})

        result = DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "flag")

        assert result is False

    def test_extracts_numeric_true(self) -> None:
        """Extracts True from numeric 1."""
        row = pd.Series({"flag": 1})

        result = DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "flag")

        assert result is True

    def test_extracts_numeric_false(self) -> None:
        """Extracts False from numeric 0."""
        row = pd.Series({"flag": 0})

        result = DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "flag")

        assert result is False

    def test_returns_default_for_missing_column(self) -> None:
        """Returns default value for missing column."""
        row = pd.Series({"other": "value"})

        result = DiaryMappingHelpers.extract_boolean_field_with_defaults(row, "flag", default_value=False)

        assert result is False


class TestGetMappingSummary:
    """Tests for get_mapping_summary method."""

    def test_returns_summary_dict(self, mapper: DiaryDataMapper) -> None:
        """Returns summary dictionary."""
        summary = mapper.get_mapping_summary()

        assert isinstance(summary, dict)
        assert "participant_id_source" in summary
        assert "sleep_timing_columns" in summary


class TestValidateMappedEntries:
    """Tests for validate_mapped_entries method."""

    def test_returns_valid_and_errors(self, mapper: DiaryDataMapper, sample_dataframe: pd.DataFrame) -> None:
        """Returns tuple of valid entries and error messages."""
        entries = mapper.map_dataframe_to_entries(sample_dataframe, "test.csv")

        valid, errors = mapper.validate_mapped_entries(entries)

        assert isinstance(valid, list)
        assert isinstance(errors, list)
