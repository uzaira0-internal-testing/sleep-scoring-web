"""
Tests for DiaryDataExtractor.

Tests field extraction and conversion from diary rows.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pandas as pd
import pytest

from sleep_scoring_app.services.diary.data_extractor import DiaryDataExtractor


@pytest.fixture
def extractor() -> DiaryDataExtractor:
    """Create a DiaryDataExtractor instance."""
    return DiaryDataExtractor()


@pytest.fixture
def mock_column_mapping() -> MagicMock:
    """Create a mock DiaryColumnMapping."""
    mapping = MagicMock()
    mapping.participant_id_column_name = "participant_id"
    mapping.date_of_last_night_column_name = "startdate"
    mapping.todays_date_column_name = "today"
    mapping.sleep_onset_date_column_name = None
    mapping.sleep_offset_date_column_name = None
    mapping.sleep_onset_time_column_name = "sleep_time"
    mapping.nap_onset_time_column_names = "nap1,nap2,nap3"
    mapping.nap_offset_time_column_names = "napend1,napend2,napend3"
    mapping.nonwear_start_time_column_names = "nw_start1,nw_start2"
    mapping.nonwear_end_time_column_names = "nw_end1,nw_end2"
    mapping.nonwear_reason_column_names = "nw_reason1,nw_reason2"
    mapping.nap_onset_time_column_name = "nap1"
    mapping.nap_offset_time_column_name = "napend1"
    return mapping


class TestExtractParticipantId:
    """Tests for extract_participant_id method."""

    def test_extracts_numeric_id(self, extractor: DiaryDataExtractor, mock_column_mapping: MagicMock) -> None:
        """Extracts numeric participant ID."""
        row = pd.Series({"participant_id": "1234"})

        result = extractor.extract_participant_id(row, mock_column_mapping)

        assert result == "1234"

    def test_extracts_from_float_value(self, extractor: DiaryDataExtractor, mock_column_mapping: MagicMock) -> None:
        """Extracts ID from float value (e.g., 1234.0)."""
        row = pd.Series({"participant_id": 1234.0})

        result = extractor.extract_participant_id(row, mock_column_mapping)

        assert result is not None
        assert "1234" in result

    def test_returns_none_for_nan(self, extractor: DiaryDataExtractor, mock_column_mapping: MagicMock) -> None:
        """Returns None for NaN value."""
        row = pd.Series({"participant_id": float("nan")})

        result = extractor.extract_participant_id(row, mock_column_mapping)

        assert result is None

    def test_returns_none_for_missing_column_config(self, extractor: DiaryDataExtractor) -> None:
        """Returns None when column not configured."""
        mapping = MagicMock()
        mapping.participant_id_column_name = None
        row = pd.Series({"participant_id": "1234"})

        result = extractor.extract_participant_id(row, mapping)

        assert result is None


class TestExtractDiaryDate:
    """Tests for extract_diary_date method."""

    def test_extracts_date_string(self, extractor: DiaryDataExtractor, mock_column_mapping: MagicMock) -> None:
        """Extracts date from string."""
        row = pd.Series({"startdate": "2024-01-15"})

        result = extractor.extract_diary_date(row, mock_column_mapping)

        assert result == "2024-01-15"

    def test_extracts_datetime_object(self, extractor: DiaryDataExtractor, mock_column_mapping: MagicMock) -> None:
        """Extracts date from datetime object."""
        row = pd.Series({"startdate": datetime(2024, 1, 15, 8, 0, 0)})

        result = extractor.extract_diary_date(row, mock_column_mapping)

        assert result == "2024-01-15"

    def test_returns_none_for_all_nan(self, extractor: DiaryDataExtractor, mock_column_mapping: MagicMock) -> None:
        """Returns None when all date columns are NaN."""
        row = pd.Series(
            {
                "startdate": float("nan"),
                "today": float("nan"),
            }
        )

        result = extractor.extract_diary_date(row, mock_column_mapping)

        assert result is None


class TestExtractTimeField:
    """Tests for extract_time_field method."""

    def test_extracts_24h_time(self, extractor: DiaryDataExtractor) -> None:
        """Extracts 24-hour time format."""
        row = pd.Series({"time_col": "14:30"})

        result = extractor.extract_time_field(row, "time_col")

        assert result == "14:30"

    def test_extracts_am_pm_time(self, extractor: DiaryDataExtractor) -> None:
        """Extracts AM/PM time format."""
        row = pd.Series({"time_col": "2:30 PM"})

        result = extractor.extract_time_field(row, "time_col")

        assert result == "14:30"

    def test_extracts_from_datetime_object(self, extractor: DiaryDataExtractor) -> None:
        """Extracts time from datetime object."""
        row = pd.Series({"time_col": datetime(2024, 1, 15, 22, 45)})

        result = extractor.extract_time_field(row, "time_col")

        assert result == "22:45"

    def test_returns_none_for_missing_column(self, extractor: DiaryDataExtractor) -> None:
        """Returns None for missing column."""
        row = pd.Series({"other_col": "value"})

        result = extractor.extract_time_field(row, "time_col")

        assert result is None

    def test_returns_none_for_none_column_name(self, extractor: DiaryDataExtractor) -> None:
        """Returns None when column_name is None."""
        row = pd.Series({"time_col": "14:30"})

        result = extractor.extract_time_field(row, None)

        assert result is None

    def test_returns_none_for_nan_value(self, extractor: DiaryDataExtractor) -> None:
        """Returns None for NaN value."""
        row = pd.Series({"time_col": float("nan")})

        result = extractor.extract_time_field(row, "time_col")

        assert result is None


class TestExtractIntegerField:
    """Tests for extract_integer_field method."""

    def test_extracts_integer(self, extractor: DiaryDataExtractor) -> None:
        """Extracts integer value."""
        row = pd.Series({"int_col": 42})

        result = extractor.extract_integer_field(row, "int_col")

        assert result == 42

    def test_extracts_from_float(self, extractor: DiaryDataExtractor) -> None:
        """Extracts integer from float value."""
        row = pd.Series({"int_col": 42.0})

        result = extractor.extract_integer_field(row, "int_col")

        assert result == 42

    def test_extracts_from_string(self, extractor: DiaryDataExtractor) -> None:
        """Extracts integer from string."""
        row = pd.Series({"int_col": "42"})

        result = extractor.extract_integer_field(row, "int_col")

        assert result == 42

    def test_returns_none_for_missing(self, extractor: DiaryDataExtractor) -> None:
        """Returns None for missing column."""
        row = pd.Series({"other_col": 42})

        result = extractor.extract_integer_field(row, "int_col")

        assert result is None


class TestExtractBooleanField:
    """Tests for extract_boolean_field method."""

    def test_extracts_true_from_yes(self, extractor: DiaryDataExtractor) -> None:
        """Extracts True from 'yes'."""
        row = pd.Series({"bool_col": "yes"})

        result = extractor.extract_boolean_field(row, "bool_col")

        assert result is True

    def test_extracts_false_from_no(self, extractor: DiaryDataExtractor) -> None:
        """Extracts False from 'no'."""
        row = pd.Series({"bool_col": "no"})

        result = extractor.extract_boolean_field(row, "bool_col")

        assert result is False

    def test_extracts_from_numeric_1(self, extractor: DiaryDataExtractor) -> None:
        """Extracts True from numeric 1."""
        row = pd.Series({"bool_col": 1})

        result = extractor.extract_boolean_field(row, "bool_col")

        assert result is True

    def test_extracts_from_numeric_0(self, extractor: DiaryDataExtractor) -> None:
        """Extracts False from numeric 0."""
        row = pd.Series({"bool_col": 0})

        result = extractor.extract_boolean_field(row, "bool_col")

        assert result is False

    def test_extracts_from_true_string(self, extractor: DiaryDataExtractor) -> None:
        """Extracts True from 'true' string."""
        row = pd.Series({"bool_col": "true"})

        result = extractor.extract_boolean_field(row, "bool_col")

        assert result is True


class TestExtractMultipleTimeFields:
    """Tests for extract_multiple_time_fields method."""

    def test_extracts_three_times(self, extractor: DiaryDataExtractor) -> None:
        """Extracts three time values."""
        row = pd.Series(
            {
                "time1": "08:00",
                "time2": "12:00",
                "time3": "18:00",
            }
        )

        t1, t2, t3 = extractor.extract_multiple_time_fields(row, "time1,time2,time3")

        assert t1 == "08:00"
        assert t2 == "12:00"
        assert t3 == "18:00"

    def test_pads_with_none(self, extractor: DiaryDataExtractor) -> None:
        """Pads result with None if fewer columns."""
        row = pd.Series({"time1": "08:00"})

        t1, t2, t3 = extractor.extract_multiple_time_fields(row, "time1")

        assert t1 == "08:00"
        assert t2 is None
        assert t3 is None

    def test_returns_none_tuple_for_empty(self, extractor: DiaryDataExtractor) -> None:
        """Returns None tuple for empty column string."""
        row = pd.Series({"time1": "08:00"})

        t1, t2, t3 = extractor.extract_multiple_time_fields(row, None)

        assert t1 is None
        assert t2 is None
        assert t3 is None


class TestConvertNonwearReasonCode:
    """Tests for convert_nonwear_reason_code method."""

    def test_converts_code_1_to_bath(self, extractor: DiaryDataExtractor) -> None:
        """Converts code 1 to Bath/Shower."""
        result = extractor.convert_nonwear_reason_code("1")

        assert result == "Bath/Shower"

    def test_converts_code_2_to_swimming(self, extractor: DiaryDataExtractor) -> None:
        """Converts code 2 to Swimming."""
        result = extractor.convert_nonwear_reason_code("2")

        assert result == "Swimming"

    def test_converts_code_3_to_other(self, extractor: DiaryDataExtractor) -> None:
        """Converts code 3 to Other."""
        result = extractor.convert_nonwear_reason_code("3")

        assert result == "Other"

    def test_handles_float_format(self, extractor: DiaryDataExtractor) -> None:
        """Handles float format (1.0)."""
        result = extractor.convert_nonwear_reason_code("1.0")

        assert result == "Bath/Shower"

    def test_returns_original_for_unknown(self, extractor: DiaryDataExtractor) -> None:
        """Returns original for unknown code."""
        result = extractor.convert_nonwear_reason_code("custom reason")

        assert result == "custom reason"

    def test_returns_none_for_none(self, extractor: DiaryDataExtractor) -> None:
        """Returns None for None input."""
        result = extractor.convert_nonwear_reason_code(None)

        assert result is None


class TestGenerateTimepointVariations:
    """Tests for generate_timepoint_variations method."""

    def test_generates_baseline_variations(self, extractor: DiaryDataExtractor) -> None:
        """Generates variations for baseline timepoint."""
        result = extractor.generate_timepoint_variations("1234 BL CTRL")

        assert len(result) > 1
        assert "1234 BL CTRL" in result
        assert "1234 BO CTRL" in result or "1234 B0 CTRL" in result

    def test_returns_original_for_simple_id(self, extractor: DiaryDataExtractor) -> None:
        """Returns original for simple ID without spaces."""
        result = extractor.generate_timepoint_variations("1234")

        assert result == ["1234"]

    def test_handles_p1_timepoint(self, extractor: DiaryDataExtractor) -> None:
        """Handles P1 timepoint."""
        result = extractor.generate_timepoint_variations("1234 P1 CTRL")

        assert len(result) >= 1
        assert "1234 P1 CTRL" in result
