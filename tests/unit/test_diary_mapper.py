#!/usr/bin/env python3
"""
Tests for Diary Data Mapper
Tests the mapping of raw diary data to standardized database schema.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from sleep_scoring_app.core.dataclasses import DiaryEntry, ParticipantInfo
from sleep_scoring_app.core.exceptions import ValidationError
from sleep_scoring_app.services.diary_mapper import DiaryDataMapper


class TestDiaryDataMapper:
    """Test cases for DiaryDataMapper."""

    @pytest.fixture
    def sample_mapping_config(self) -> dict:
        """Sample mapping configuration."""
        return {
            "participant_id_column_name": "participant_id",
            "sleep_onset_time_column_name": "asleep_time",
            "sleep_offset_time_column_name": "wake_time",
            "in_bed_time_column_name": "inbed_time",
            "out_of_bed_time_column_name": None,
            "napped_column_name": "nap",
            "nap_onset_time_column_name": "napstart_1_time",
            "nap_offset_time_column_name": "napend_1_time",
            "nap_onset_time_column_names": "napstart_1_time,napstart_2_time",
            "nap_offset_time_column_names": "napend_1_time,napend_2_time",
            "nonwear_occurred_column_name": "takeoff",
            "nonwear_reason_column_names": "why_timeoff_1,why_timeoff_2",
            "nonwear_start_time_column_names": "takeoffstart_1_time,takeoffstart_2_time",
            "nonwear_end_time_column_names": "takeoffend_1_time,takeoffend_2_time",
            "diary_completed_for_current_day_column_name": "sleep_diary_day_complete",
            "activity_columns": "activity_other1,activity_other2",
            "date_of_last_night_column_name": "date_lastnight",
            "auto_calculated_columns": {
                "sleep_onset_time_column_name": False,
                "sleep_offset_time_column_name": False,
                "nap_occurred": True,
                "nonwear_occurred": True,
            },
        }

    @pytest.fixture
    def sample_dataframe(self) -> pd.DataFrame:
        """Sample diary DataFrame."""
        return pd.DataFrame(
            [
                {
                    "participant_id": "P001",
                    "date_lastnight": "2024-01-15",
                    "asleep_time": "23:30",
                    "wake_time": "07:15",
                    "inbed_time": "23:00",
                    "nap": True,
                    "napstart_1_time": "14:00",
                    "napend_1_time": "14:30",
                    "napstart_2_time": "",
                    "napend_2_time": "",
                    "takeoff": False,
                    "why_timeoff_1": "",
                    "takeoffstart_1_time": "",
                    "takeoffend_1_time": "",
                    "why_timeoff_2": "",
                    "takeoffstart_2_time": "",
                    "takeoffend_2_time": "",
                    "sleep_diary_day_complete": "Yes",
                    "activity_other1": "Exercise",
                    "activity_other2": "",
                },
                {
                    "participant_id": "P002",
                    "date_lastnight": "2024-01-15",
                    "asleep_time": "22:45",
                    "wake_time": "06:30",
                    "inbed_time": "22:30",
                    "nap": False,
                    "napstart_1_time": "",
                    "napend_1_time": "",
                    "napstart_2_time": "",
                    "napend_2_time": "",
                    "takeoff": True,
                    "why_timeoff_1": "Shower",
                    "takeoffstart_1_time": "19:00",
                    "takeoffend_1_time": "19:15",
                    "why_timeoff_2": "Swimming",
                    "takeoffstart_2_time": "15:30",
                    "takeoffend_2_time": "16:00",
                    "sleep_diary_day_complete": "No",
                    "activity_other1": "",
                    "activity_other2": "Reading",
                },
            ]
        )

    @pytest.fixture
    def temp_config_file(self, sample_mapping_config: dict) -> Path:
        """Create temporary config file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(sample_mapping_config, f)
            return Path(f.name)

    def test_init_with_config(self, sample_mapping_config: dict) -> None:
        """Test mapper initialization with configuration."""
        mapper = DiaryDataMapper(sample_mapping_config)
        assert mapper.mapping_config == sample_mapping_config

    def test_init_without_config(self) -> None:
        """Test mapper initialization without configuration."""
        mapper = DiaryDataMapper()
        assert mapper.mapping_config == {}

    def test_from_config_file(self, temp_config_file: Path, sample_mapping_config: dict) -> None:
        """Test creating mapper from config file."""
        mapper = DiaryDataMapper.from_config_file(temp_config_file)
        assert mapper.mapping_config == sample_mapping_config

        # Clean up
        temp_config_file.unlink()

    def test_from_config_file_invalid_path(self) -> None:
        """Test creating mapper from invalid config file."""
        with pytest.raises(ValidationError):
            DiaryDataMapper.from_config_file(Path("nonexistent.json"))

    def test_from_config_file_invalid_json(self) -> None:
        """Test creating mapper from file with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("invalid json content")
            temp_path = Path(f.name)

        try:
            with pytest.raises(ValidationError):
                DiaryDataMapper.from_config_file(temp_path)
        finally:
            temp_path.unlink()

    def test_validate_config_invalid_type(self) -> None:
        """Test config validation with invalid type."""
        with pytest.raises(ValidationError):
            DiaryDataMapper("invalid config")

    def test_validate_config_missing_required(self) -> None:
        """Test config validation with missing required keys."""
        # Config with some content but missing required keys should raise error
        with pytest.raises(ValidationError):
            DiaryDataMapper({"some_other_key": "value"})

    def test_map_dataframe_to_entries_success(self, sample_mapping_config: dict, sample_dataframe: pd.DataFrame) -> None:
        """Test successful DataFrame mapping."""
        mapper = DiaryDataMapper(sample_mapping_config)
        entries = mapper.map_dataframe_to_entries(sample_dataframe, "test.csv")

        assert len(entries) == 2

        # Check first entry
        entry1 = entries[0]
        assert entry1.participant_id == "P001"
        assert entry1.diary_date == "2024-01-15"
        assert entry1.filename == "test.csv"
        assert entry1.sleep_onset_time == "23:30"
        assert entry1.sleep_offset_time == "07:15"
        assert entry1.in_bed_time == "23:00"
        assert entry1.nap_occurred is True
        assert entry1.nap_onset_time == "14:00"
        assert entry1.nap_offset_time == "14:30"
        assert entry1.nonwear_occurred is False
        assert "Diary completed: Yes" in entry1.diary_notes
        assert "Activities: activity_other1: Exercise" in entry1.diary_notes

        # Check second entry
        entry2 = entries[1]
        assert entry2.participant_id == "P002"
        assert entry2.nap_occurred is False
        assert entry2.nonwear_occurred is True
        assert entry2.nonwear_reason == "Shower"
        assert entry2.nonwear_start_time == "19:00"
        assert entry2.nonwear_end_time == "19:15"
        assert entry2.nonwear_reason_2 == "Swimming"
        assert entry2.nonwear_start_time_2 == "15:30"
        assert entry2.nonwear_end_time_2 == "16:00"

    def test_map_dataframe_empty(self, sample_mapping_config: dict) -> None:
        """Test mapping empty DataFrame."""
        mapper = DiaryDataMapper(sample_mapping_config)
        empty_df = pd.DataFrame()
        entries = mapper.map_dataframe_to_entries(empty_df, "test.csv")
        assert len(entries) == 0

    def test_map_dataframe_with_participant_info(self, sample_mapping_config: dict, sample_dataframe: pd.DataFrame) -> None:
        """Test mapping with pre-provided participant info."""
        mapper = DiaryDataMapper(sample_mapping_config)
        participant_info = ParticipantInfo(numerical_id="P999", full_id="P999 BO G1", group="G1", timepoint="BO", date="2024-01-15")

        entries = mapper.map_dataframe_to_entries(sample_dataframe, "test.csv", participant_info)

        # Should use participant_info for all entries
        assert all(entry.participant_id == "P999" for entry in entries)

    def test_extract_participant_id_from_various_sources(self, sample_mapping_config: dict) -> None:
        """Test participant ID extraction from various sources."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # Test with configured column
        row = pd.Series({"participant_id": "P123", "other_col": "value"})
        participant_id = mapper._extract_participant_id(row, None)
        assert participant_id == "P123"

        # Test with common fallback column
        row = pd.Series({"subject_id": "P456", "other_col": "value"})
        participant_id = mapper._extract_participant_id(row, None)
        assert participant_id == "P456"

        # Test with participant info
        participant_info = ParticipantInfo(numerical_id="P789", full_id="P789 BO G1", group="G1", timepoint="BO", date="")
        row = pd.Series({"other_col": "value"})
        participant_id = mapper._extract_participant_id(row, participant_info)
        assert participant_id == "P789"

    def test_extract_diary_date_various_formats(self, sample_mapping_config: dict) -> None:
        """Test date extraction from various formats."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # Test configured column
        row = pd.Series({"date_lastnight": "2024-01-15"})
        date = mapper._extract_diary_date(row)
        assert date == "2024-01-15"

        # Test datetime object
        row = pd.Series({"date": datetime(2024, 1, 15, 12, 0, 0)})
        date = mapper._extract_diary_date(row)
        assert date == "2024-01-15"

        # Test different date format
        row = pd.Series({"diary_date": "01/15/2024"})
        date = mapper._extract_diary_date(row)
        assert date == "2024-01-15"

    def test_extract_time_value_various_formats(self, sample_mapping_config: dict) -> None:
        """Test time extraction from various formats."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # Test HH:MM format
        assert mapper._extract_time_value("23:30") == "23:30"

        # Test HH:MM:SS format
        assert mapper._extract_time_value("23:30:45") == "23:30"

        # Test datetime object
        dt = datetime(2024, 1, 15, 23, 30, 0)
        assert mapper._extract_time_value(dt) == "23:30"

        # Test 12-hour format
        assert mapper._extract_time_value("11:30 PM") == "23:30"

        # Test invalid format
        assert mapper._extract_time_value("invalid") is None

        # Test empty/null
        assert mapper._extract_time_value("") is None
        assert mapper._extract_time_value(pd.NA) is None

    def test_extract_boolean_value_various_formats(self, sample_mapping_config: dict) -> None:
        """Test boolean extraction from various formats."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # Test boolean values
        assert mapper._extract_boolean_value(True) is True
        assert mapper._extract_boolean_value(False) is False

        # Test string values
        assert mapper._extract_boolean_value("true") is True
        assert mapper._extract_boolean_value("yes") is True
        assert mapper._extract_boolean_value("1") is True
        assert mapper._extract_boolean_value("false") is False
        assert mapper._extract_boolean_value("no") is False
        assert mapper._extract_boolean_value("0") is False

        # Test numeric values
        assert mapper._extract_boolean_value(1) is True
        assert mapper._extract_boolean_value(0) is False
        assert mapper._extract_boolean_value(5) is True

        # Test invalid values
        assert mapper._extract_boolean_value("maybe") is None
        assert mapper._extract_boolean_value(pd.NA) is None

    def test_auto_calculated_flags(self, sample_mapping_config: dict) -> None:
        """Test auto-calculated flag setting."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # Test nap_occurred auto-calculation
        entry = DiaryEntry(participant_id="P001", diary_date="2024-01-15", filename="test.csv", nap_occurred=None, nap_onset_time="14:00")
        mapper._set_auto_calculated_flags(entry)
        assert entry.nap_occurred is True

        # Test nonwear_occurred auto-calculation
        entry = DiaryEntry(participant_id="P001", diary_date="2024-01-15", filename="test.csv", nonwear_occurred=None, nonwear_reason="Shower")
        mapper._set_auto_calculated_flags(entry)
        assert entry.nonwear_occurred is True

    def test_validate_mapped_entries_success(self, sample_mapping_config: dict) -> None:
        """Test validation of mapped entries."""
        mapper = DiaryDataMapper(sample_mapping_config)

        valid_entry = DiaryEntry(participant_id="P001", diary_date="2024-01-15", filename="test.csv", sleep_onset_time="23:30")

        valid_entries, errors = mapper.validate_mapped_entries([valid_entry])
        assert len(valid_entries) == 1
        assert len(errors) == 0

    def test_validate_mapped_entries_with_errors(self, sample_mapping_config: dict) -> None:
        """Test validation of mapped entries with errors."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # Entry missing participant ID
        invalid_entry1 = DiaryEntry(participant_id="", diary_date="2024-01-15", filename="test.csv")

        # Entry with invalid date
        invalid_entry2 = DiaryEntry(participant_id="P001", diary_date="invalid-date", filename="test.csv")

        # Entry with invalid time
        invalid_entry3 = DiaryEntry(participant_id="P001", diary_date="2024-01-15", filename="test.csv", sleep_onset_time="invalid-time")

        valid_entries, errors = mapper.validate_mapped_entries([invalid_entry1, invalid_entry2, invalid_entry3])

        assert len(valid_entries) == 0
        assert len(errors) == 3
        assert "Missing participant ID" in errors[0]
        assert "Invalid date format" in errors[1]
        assert "Invalid time format" in errors[2]

    def test_get_mapping_summary(self, sample_mapping_config: dict) -> None:
        """Test mapping summary generation."""
        mapper = DiaryDataMapper(sample_mapping_config)
        summary = mapper.get_mapping_summary()

        assert summary["participant_id_source"] == "participant_id"
        assert summary["date_source"] == "date_lastnight"
        assert summary["sleep_timing_columns"]["onset"] == "asleep_time"
        assert summary["nap_columns"]["occurred"] == "nap"
        assert summary["nonwear_columns"]["occurred"] == "takeoff"
        assert "auto_calculated_flags" in summary

    def test_case_insensitive_column_mapping(self, sample_mapping_config: dict) -> None:
        """Test that column mapping is case-insensitive."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # Create DataFrame with mixed case columns
        df = pd.DataFrame([{"PARTICIPANT_ID": "P001", "Date_LastNight": "2024-01-15", "Asleep_Time": "23:30"}])

        entries = mapper.map_dataframe_to_entries(df, "test.csv")
        assert len(entries) == 1
        assert entries[0].participant_id == "P001"
        assert entries[0].diary_date == "2024-01-15"
        assert entries[0].sleep_onset_time == "23:30"

    def test_missing_optional_columns(self, sample_mapping_config: dict) -> None:
        """Test handling of missing optional columns."""
        mapper = DiaryDataMapper(sample_mapping_config)

        # DataFrame with only required columns
        df = pd.DataFrame([{"participant_id": "P001", "date_lastnight": "2024-01-15"}])

        entries = mapper.map_dataframe_to_entries(df, "test.csv")
        assert len(entries) == 1

        entry = entries[0]
        assert entry.participant_id == "P001"
        assert entry.diary_date == "2024-01-15"
        assert entry.sleep_onset_time is None
        assert entry.nap_occurred is False  # Auto-calculated as False
        assert entry.nonwear_occurred is False  # Auto-calculated as False

    def test_whitespace_handling(self, sample_mapping_config: dict) -> None:
        """Test handling of whitespace in data."""
        mapper = DiaryDataMapper(sample_mapping_config)

        df = pd.DataFrame([{" participant_id ": "  P001  ", " date_lastnight ": " 2024-01-15 ", " asleep_time ": " 23:30 "}])

        entries = mapper.map_dataframe_to_entries(df, "test.csv")
        assert len(entries) == 1

        entry = entries[0]
        assert entry.participant_id == "P001"
        assert entry.diary_date == "2024-01-15"
        assert entry.sleep_onset_time == "23:30"

    def test_null_value_handling(self, sample_mapping_config: dict) -> None:
        """Test handling of null/NaN values."""
        mapper = DiaryDataMapper(sample_mapping_config)

        df = pd.DataFrame([{"participant_id": "P001", "date_lastnight": "2024-01-15", "asleep_time": pd.NA, "nap": None, "takeoff": None}])

        entries = mapper.map_dataframe_to_entries(df, "test.csv")
        assert len(entries) == 1

        entry = entries[0]
        assert entry.participant_id == "P001"
        assert entry.diary_date == "2024-01-15"
        assert entry.sleep_onset_time is None
        assert entry.nap_occurred is False  # Auto-calculated
        assert entry.nonwear_occurred is False  # Auto-calculated
