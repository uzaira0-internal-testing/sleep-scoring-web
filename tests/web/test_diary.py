"""
Tests for the diary API endpoints.
"""

from datetime import date

import pytest

from sleep_scoring_web.api.diary import (
    DiaryEntryCreate,
    DiaryEntryResponse,
    DiaryUploadResponse,
    _get_int_field,
    _get_str_field,
    _get_time_field,
)


class TestDiaryEntryModels:
    """Tests for diary entry Pydantic models."""

    def test_diary_entry_response_required_fields(self):
        """Response should have required fields."""
        entry = DiaryEntryResponse(
            id=1,
            file_id=1,
            analysis_date=date(2024, 1, 15),
        )
        assert entry.id == 1
        assert entry.file_id == 1
        assert entry.analysis_date == date(2024, 1, 15)
        assert entry.bed_time is None
        assert entry.wake_time is None

    def test_diary_entry_response_all_fields(self):
        """Response should accept all optional fields."""
        entry = DiaryEntryResponse(
            id=1,
            file_id=1,
            analysis_date=date(2024, 1, 15),
            bed_time="22:30",
            wake_time="07:15",
            lights_out="22:45",
            got_up="07:30",
            sleep_quality=4,
            time_to_fall_asleep_minutes=15,
            number_of_awakenings=2,
            notes="Slept well",
        )
        assert entry.bed_time == "22:30"
        assert entry.wake_time == "07:15"
        assert entry.sleep_quality == 4
        assert entry.notes == "Slept well"

    def test_diary_entry_create(self):
        """Create model should work with partial data."""
        entry = DiaryEntryCreate(
            bed_time="23:00",
            wake_time="06:30",
        )
        assert entry.bed_time == "23:00"
        assert entry.wake_time == "06:30"
        assert entry.sleep_quality is None

    def test_diary_upload_response(self):
        """Upload response should contain counts."""
        response = DiaryUploadResponse(
            entries_imported=10,
            entries_skipped=2,
            errors=["Error 1", "Error 2"],
        )
        assert response.entries_imported == 10
        assert response.entries_skipped == 2
        assert len(response.errors) == 2


class TestHelperFunctions:
    """Tests for diary import helper functions."""

    def test_get_time_field_valid(self):
        """Should extract valid time values."""
        row = {"bed_time": "22:30"}
        assert _get_time_field(row, ["bed_time"]) == "22:30"

    def test_get_time_field_normalizes(self):
        """Should normalize time format."""
        row = {"bedtime": "9:5"}
        assert _get_time_field(row, ["bedtime"]) == "09:05"

    def test_get_time_field_multiple_names(self):
        """Should try multiple field names."""
        row = {"time_to_bed": "21:00"}
        result = _get_time_field(row, ["bed_time", "bedtime", "time_to_bed"])
        assert result == "21:00"

    def test_get_time_field_none(self):
        """Should return None for missing field."""
        row = {"other": "value"}
        assert _get_time_field(row, ["bed_time"]) is None

    def test_get_time_field_null_values(self):
        """Should treat null-like values as None."""
        for null_val in [None, "", "nan", "NaN", "none", "null"]:
            row = {"bed_time": null_val}
            assert _get_time_field(row, ["bed_time"]) is None

    def test_get_int_field_valid(self):
        """Should extract integer values."""
        row = {"sleep_quality": 4}
        assert _get_int_field(row, ["sleep_quality"]) == 4

    def test_get_int_field_from_float(self):
        """Should convert float to int."""
        row = {"quality": 3.7}
        assert _get_int_field(row, ["quality"]) == 3

    def test_get_int_field_from_string(self):
        """Should convert string to int."""
        row = {"awakenings": "2"}
        assert _get_int_field(row, ["awakenings"]) == 2

    def test_get_int_field_none(self):
        """Should return None for missing/invalid field."""
        assert _get_int_field({}, ["quality"]) is None
        assert _get_int_field({"quality": "abc"}, ["quality"]) is None

    def test_get_str_field_valid(self):
        """Should extract string values."""
        row = {"notes": "Slept well"}
        assert _get_str_field(row, ["notes"]) == "Slept well"

    def test_get_str_field_strips(self):
        """Should strip whitespace."""
        row = {"notes": "  Some notes  "}
        assert _get_str_field(row, ["notes"]) == "Some notes"

    def test_get_str_field_null_values(self):
        """Should treat null-like values as None."""
        for null_val in ["nan", "NaN", "none", "null"]:
            row = {"notes": null_val}
            assert _get_str_field(row, ["notes"]) is None


class TestDiaryEntryValidation:
    """Tests for diary entry field validation."""

    def test_time_format_hhmm(self):
        """Should accept HH:MM time format."""
        entry = DiaryEntryCreate(bed_time="22:30")
        assert entry.bed_time == "22:30"

    def test_sleep_quality_range(self):
        """Should accept quality values."""
        entry = DiaryEntryCreate(sleep_quality=5)
        assert entry.sleep_quality == 5

    def test_minutes_field(self):
        """Should accept minute values."""
        entry = DiaryEntryCreate(time_to_fall_asleep_minutes=20)
        assert entry.time_to_fall_asleep_minutes == 20

    def test_awakenings_count(self):
        """Should accept awakening counts."""
        entry = DiaryEntryCreate(number_of_awakenings=3)
        assert entry.number_of_awakenings == 3
