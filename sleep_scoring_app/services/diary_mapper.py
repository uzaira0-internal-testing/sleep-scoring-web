#!/usr/bin/env python3
"""
Diary Data Mapper for Sleep Scoring Application
Transforms raw CSV/Excel diary data using diary_mapping.json configuration to match database schema.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

import pandas as pd

from sleep_scoring_app.core.dataclasses import DiaryColumnMapping, DiaryEntry, ParticipantInfo
from sleep_scoring_app.core.exceptions import ErrorCodes, ValidationError
from sleep_scoring_app.core.validation import InputValidator

if TYPE_CHECKING:
    from pathlib import Path

# Configure logging
logger = logging.getLogger(__name__)


class DiaryDataMapper:
    """Maps raw diary data to standardized database schema using configuration."""

    def __init__(self, mapping_config: dict[str, Any] | None = None) -> None:
        """
        Initialize mapper with configuration.

        Args:
            mapping_config: Dictionary containing column mapping configuration

        """
        self.mapping_config = mapping_config or {}
        self._validate_config()

    @classmethod
    def from_config_file(cls, config_path: Path) -> DiaryDataMapper:
        """Create mapper from configuration file."""
        try:
            config_path = InputValidator.validate_file_path(config_path, must_exist=True, allowed_extensions={".json"})

            with open(config_path, encoding="utf-8") as f:
                mapping_config = json.load(f)

            return cls(mapping_config)

        except (json.JSONDecodeError, OSError) as e:
            msg = f"Failed to load mapping configuration from {config_path}: {e}"
            raise ValidationError(msg, ErrorCodes.INVALID_FORMAT) from e

    def _validate_config(self) -> None:
        """Validate mapping configuration structure."""
        if not isinstance(self.mapping_config, dict):
            msg = "Mapping configuration must be a dictionary"
            raise ValidationError(msg, ErrorCodes.INVALID_INPUT)

        # Only validate configuration if it's not empty
        if not self.mapping_config:
            return

        # Check for required configuration keys
        required_keys = ["participant_id_column_name"]
        missing_keys = [key for key in required_keys if key not in self.mapping_config]

        if missing_keys:
            msg = f"Missing required configuration keys: {missing_keys}"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

    def map_dataframe_to_entries(self, df: pd.DataFrame, filename: str, participant_info: ParticipantInfo | None = None) -> list[DiaryEntry]:
        """
        Map DataFrame to list of DiaryEntry objects.

        Args:
            df: Raw pandas DataFrame from CSV/Excel
            filename: Source filename for tracking
            participant_info: Pre-extracted participant info (optional)

        Returns:
            List of DiaryEntry objects mapped to database schema

        Raises:
            ValidationError: If mapping fails or data is invalid

        """
        # Validate inputs
        InputValidator.validate_string(filename, min_length=1, name="filename")

        if df.empty:
            logger.warning("Empty DataFrame provided for mapping")
            return []

        # Clean column names (remove whitespace, normalize case)
        df.columns = df.columns.str.strip().str.lower()

        entries = []
        mapping_errors = []

        for index, row in df.iterrows():
            try:
                entry = self._map_row_to_entry(row, filename, participant_info, index)
                if entry:  # Only add if mapping was successful
                    entries.append(entry)
            except Exception as e:
                error_msg = f"Row {index}: {e}"
                mapping_errors.append(error_msg)
                logger.warning("Failed to map row %s: %s", index, e)
                continue

        # Log mapping results
        logger.info("Mapped %s/%s rows successfully from %s", len(entries), len(df), filename)

        if mapping_errors:
            logger.warning("Mapping errors for %s: %s", filename, mapping_errors[:5])  # Limit to first 5 errors

        return entries

    def _map_row_to_entry(self, row: pd.Series, filename: str, participant_info: ParticipantInfo | None, row_index: int) -> DiaryEntry | None:
        """Map a single DataFrame row to DiaryEntry."""
        # Extract participant ID
        participant_id = self._extract_participant_id(row, participant_info)
        if not participant_id:
            logger.debug("No participant ID found for row %s", row_index)
            return None

        # Extract diary date (required)
        diary_date = self._extract_diary_date(row)
        if not diary_date:
            logger.debug("No diary date found for row %s", row_index)
            return None

        # Create base entry
        entry = DiaryEntry(
            participant_id=participant_id, diary_date=diary_date, filename=filename, original_column_mapping=json.dumps(self.mapping_config)
        )

        # Map all available columns
        self._map_sleep_timing_columns(row, entry)
        self._map_nap_columns(row, entry)
        self._map_nonwear_columns(row, entry)
        self._map_metadata_columns(row, entry)

        # Set auto-calculated flags
        self._set_auto_calculated_flags(entry)

        return entry

    def _extract_participant_id(self, row: pd.Series, participant_info: ParticipantInfo | None) -> str | None:
        """Extract participant ID from row or participant info."""
        # Try participant info first
        if participant_info and participant_info.numerical_id:
            return participant_info.numerical_id

        # Try mapping configuration
        participant_column = self.mapping_config.get("participant_id_column_name")
        if participant_column and participant_column.lower() in row.index:
            value = row[participant_column.lower()]
            if pd.notna(value) and str(value).strip():
                return str(value).strip()

        # Try common column names as fallback
        common_names = ["participant_id", "participant", "id", "subject_id", "subject"]
        for name in common_names:
            if name in row.index:
                value = row[name]
                if pd.notna(value) and str(value).strip():
                    return str(value).strip()

        return None

    def _extract_diary_date(self, row: pd.Series) -> str | None:
        """Extract diary date from row."""
        # Try configured date column
        date_column = self.mapping_config.get("date_of_last_night_column_name")
        if date_column and date_column.lower() in row.index:
            date_value = self._extract_date_value(row[date_column.lower()])
            if date_value:
                return date_value

        # Try common date column names
        common_date_names = ["date_lastnight", "date", "diary_date", "night_date", "sleep_date", "date_of_last_night"]

        for name in common_date_names:
            if name in row.index:
                date_value = self._extract_date_value(row[name])
                if date_value:
                    return date_value

        return None

    def _extract_date_value(self, value: Any) -> str | None:
        """Extract and validate date value."""
        if pd.isna(value):
            return None

        # Handle datetime objects
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")

        # Handle string dates
        value_str = str(value).strip()
        if not value_str:
            return None

        # Try to parse various date formats
        date_formats = ["%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d"]

        for fmt in date_formats:
            try:
                parsed_date = datetime.strptime(value_str, fmt)
                return parsed_date.strftime("%Y-%m-%d")
            except ValueError:
                continue

        logger.debug("Could not parse date value: %s", value_str)
        return None

    def _get_column_value(self, row: pd.Series, config_key: str) -> Any:
        """Safely get column value from row using config key."""
        column_name = self.mapping_config.get(config_key)
        if column_name and column_name.lower() in row.index:
            return row[column_name.lower()]
        return None

    def _map_sleep_timing_columns(self, row: pd.Series, entry: DiaryEntry) -> None:
        """Map sleep timing columns to entry."""
        # Core sleep timing mappings
        timing_mappings = {
            "sleep_onset_time_column_name": "sleep_onset_time",
            "sleep_offset_time_column_name": "sleep_offset_time",
            "in_bed_time_column_name": "in_bed_time",
            "out_of_bed_time_column_name": "wake_time",  # Map out_of_bed to wake_time
        }

        for config_key, entry_attr in timing_mappings.items():
            value = self._get_column_value(row, config_key)
            if value is not None:
                time_value = self._extract_time_value(value)
                if time_value:
                    setattr(entry, entry_attr, time_value)

    def _map_nap_columns(self, row: pd.Series, entry: DiaryEntry) -> None:
        """Map nap-related columns to entry."""
        # Single nap columns
        nap_mappings = {"nap_onset_time_column_name": "nap_onset_time", "nap_offset_time_column_name": "nap_offset_time"}

        for config_key, entry_attr in nap_mappings.items():
            value = self._get_column_value(row, config_key)
            if value is not None:
                time_value = self._extract_time_value(value)
                if time_value:
                    setattr(entry, entry_attr, time_value)

        # Multiple nap columns (comma-separated lists in config)
        self._map_multiple_columns(row, entry, "nap_onset_time_column_names", ["nap_onset_time", "nap_onset_time_2"])

        self._map_multiple_columns(row, entry, "nap_offset_time_column_names", ["nap_offset_time", "nap_offset_time_2"])

        # Nap occurred flag
        value = self._get_column_value(row, "napped_column_name")
        if value is not None:
            nap_value = self._extract_boolean_value(value)
            if nap_value is not None:
                entry.nap_occurred = nap_value

    def _map_nonwear_columns(self, row: pd.Series, entry: DiaryEntry) -> None:
        """Map nonwear-related columns to entry."""
        # Nonwear occurred flag
        value = self._get_column_value(row, "nonwear_occurred_column_name")
        if value is not None:
            nonwear_value = self._extract_boolean_value(value)
            if nonwear_value is not None:
                entry.nonwear_occurred = nonwear_value

        # Multiple nonwear reason columns
        self._map_multiple_columns(row, entry, "nonwear_reason_column_names", ["nonwear_reason", "nonwear_reason_2", "nonwear_reason_3"])

        # Multiple nonwear start time columns
        self._map_multiple_columns(
            row, entry, "nonwear_start_time_column_names", ["nonwear_start_time", "nonwear_start_time_2", "nonwear_start_time_3"], is_time=True
        )

        # Multiple nonwear end time columns
        self._map_multiple_columns(
            row, entry, "nonwear_end_time_column_names", ["nonwear_end_time", "nonwear_end_time_2", "nonwear_end_time_3"], is_time=True
        )

    def _map_metadata_columns(self, row: pd.Series, entry: DiaryEntry) -> None:
        """Map metadata columns to entry."""
        # Diary completion flag
        completion_value = self._get_column_value(row, "diary_completed_for_current_day_column_name")
        if completion_value is not None and pd.notna(completion_value):
            completion_text = f"Diary completed: {completion_value}"
            if entry.diary_notes:
                entry.diary_notes += f"; {completion_text}"
            else:
                entry.diary_notes = completion_text

        # Activity columns (store as notes)
        activity_columns = self.mapping_config.get("activity_columns", "")
        if activity_columns:
            activity_column_list = [col.strip().lower() for col in activity_columns.split(",")]
            activity_notes = []

            for activity_col in activity_column_list:
                if activity_col in row.index:
                    activity_value = row[activity_col]
                    if pd.notna(activity_value) and str(activity_value).strip():
                        activity_notes.append(f"{activity_col}: {activity_value}")

            if activity_notes:
                activity_text = "Activities: " + "; ".join(activity_notes)
                if entry.diary_notes:
                    entry.diary_notes += f"; {activity_text}"
                else:
                    entry.diary_notes = activity_text

    def _map_multiple_columns(self, row: pd.Series, entry: DiaryEntry, config_key: str, entry_attrs: list[str], is_time: bool = False) -> None:
        """Map multiple columns specified as comma-separated list in config."""
        column_names_str = self.mapping_config.get(config_key, "")
        if not column_names_str:
            return

        column_names = [col.strip().lower() for col in column_names_str.split(",")]

        for i, column_name in enumerate(column_names):
            if i >= len(entry_attrs):  # Don't exceed available entry attributes
                break

            if column_name and column_name in row.index:
                if is_time:
                    value = self._extract_time_value(row[column_name])
                else:
                    value = self._extract_string_value(row[column_name])

                if value:
                    setattr(entry, entry_attrs[i], value)

    def _extract_time_value(self, value: Any) -> str | None:
        """Extract and validate time value."""
        if pd.isna(value):
            return None

        # Handle datetime objects
        if isinstance(value, datetime):
            return value.strftime("%H:%M")

        # Handle string times
        value_str = str(value).strip()
        if not value_str:
            return None

        # Try to parse various time formats
        time_formats = ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"]

        for fmt in time_formats:
            try:
                parsed_time = datetime.strptime(value_str, fmt)
                return parsed_time.strftime("%H:%M")
            except ValueError:
                continue

        # If we can't parse it, return as-is if it looks like a time
        if ":" in value_str and len(value_str) <= 8:  # Basic time format check
            return value_str

        logger.debug("Could not parse time value: %s", value_str)
        return None

    def _extract_boolean_value(self, value: Any) -> bool | None:
        """Extract and validate boolean value."""
        if pd.isna(value):
            return None

        # Handle actual boolean
        if isinstance(value, bool):
            return value

        # Handle string representations
        value_str = str(value).strip().lower()
        if value_str in ("true", "yes", "1", "y"):
            return True
        if value_str in ("false", "no", "0", "n"):
            return False

        # Handle numeric values
        try:
            numeric_value = float(value)
            return numeric_value != 0
        except (ValueError, TypeError):
            pass

        logger.debug("Could not parse boolean value: %s", value)
        return None

    def _extract_string_value(self, value: Any) -> str | None:
        """Extract and validate string value."""
        if pd.isna(value):
            return None

        value_str = str(value).strip()
        return value_str if value_str else None

    def _set_auto_calculated_flags(self, entry: DiaryEntry) -> None:
        """Set auto-calculated flags based on mapping configuration."""
        auto_calc_config = self.mapping_config.get("auto_calculated_columns", {})

        # If nap times are present but nap_occurred is None, set it automatically
        if entry.nap_occurred is None and auto_calc_config.get("nap_occurred", True):  # Default to auto-calculate
            has_nap_data = any([entry.nap_onset_time, entry.nap_offset_time, entry.nap_onset_time_2, entry.nap_offset_time_2])
            entry.nap_occurred = has_nap_data

        # If nonwear times are present but nonwear_occurred is None, set it automatically
        if entry.nonwear_occurred is None and auto_calc_config.get("nonwear_occurred", True):  # Default to auto-calculate
            has_nonwear_data = any(
                [
                    entry.nonwear_start_time,
                    entry.nonwear_end_time,
                    entry.nonwear_start_time_2,
                    entry.nonwear_end_time_2,
                    entry.nonwear_start_time_3,
                    entry.nonwear_end_time_3,
                    entry.nonwear_reason,
                    entry.nonwear_reason_2,
                    entry.nonwear_reason_3,
                ]
            )
            entry.nonwear_occurred = has_nonwear_data

    def get_mapping_summary(self) -> dict[str, Any]:
        """Get summary of current mapping configuration."""
        return {
            "participant_id_source": self.mapping_config.get("participant_id_column_name"),
            "date_source": self.mapping_config.get("date_of_last_night_column_name"),
            "sleep_timing_columns": {
                "onset": self.mapping_config.get("sleep_onset_time_column_name"),
                "offset": self.mapping_config.get("sleep_offset_time_column_name"),
                "in_bed": self.mapping_config.get("in_bed_time_column_name"),
                "out_of_bed": self.mapping_config.get("out_of_bed_time_column_name"),
            },
            "nap_columns": {
                "occurred": self.mapping_config.get("napped_column_name"),
                "single_onset": self.mapping_config.get("nap_onset_time_column_name"),
                "single_offset": self.mapping_config.get("nap_offset_time_column_name"),
                "multiple_onsets": self.mapping_config.get("nap_onset_time_column_names"),
                "multiple_offsets": self.mapping_config.get("nap_offset_time_column_names"),
            },
            "nonwear_columns": {
                "occurred": self.mapping_config.get("nonwear_occurred_column_name"),
                "reasons": self.mapping_config.get("nonwear_reason_column_names"),
                "start_times": self.mapping_config.get("nonwear_start_time_column_names"),
                "end_times": self.mapping_config.get("nonwear_end_time_column_names"),
            },
            "auto_calculated_flags": self.mapping_config.get("auto_calculated_columns", {}),
            "metadata_columns": {
                "completion": self.mapping_config.get("diary_completed_for_current_day_column_name"),
                "activities": self.mapping_config.get("activity_columns"),
            },
        }

    def validate_mapped_entries(self, entries: list[DiaryEntry]) -> tuple[list[DiaryEntry], list[str]]:
        """
        Validate mapped entries and return valid entries plus error messages.

        Args:
            entries: List of DiaryEntry objects to validate

        Returns:
            Tuple of (valid_entries, error_messages)

        """
        valid_entries = []
        error_messages = []

        for i, entry in enumerate(entries):
            try:
                # Validate required fields
                if not entry.participant_id:
                    error_messages.append(f"Entry {i}: Missing participant ID")
                    continue

                if not entry.diary_date:
                    error_messages.append(f"Entry {i}: Missing diary date")
                    continue

                # Validate date format
                try:
                    datetime.strptime(entry.diary_date, "%Y-%m-%d")
                except ValueError:
                    error_messages.append(f"Entry {i}: Invalid date format: {entry.diary_date}")
                    continue

                # Validate time formats if present
                time_fields = [
                    "sleep_onset_time",
                    "sleep_offset_time",
                    "in_bed_time",
                    "wake_time",
                    "nap_onset_time",
                    "nap_offset_time",
                    "nap_onset_time_2",
                    "nap_offset_time_2",
                    "nonwear_start_time",
                    "nonwear_end_time",
                    "nonwear_start_time_2",
                    "nonwear_end_time_2",
                    "nonwear_start_time_3",
                    "nonwear_end_time_3",
                ]

                time_validation_failed = False
                for field in time_fields:
                    time_value = getattr(entry, field)
                    if time_value and not self._is_valid_time_format(time_value):
                        error_messages.append(f"Entry {i}: Invalid time format for {field}: {time_value}")
                        time_validation_failed = True

                if time_validation_failed:
                    continue

                valid_entries.append(entry)

            except Exception as e:
                error_messages.append(f"Entry {i}: Validation error: {e}")
                continue

        logger.info("Validated %s/%s entries successfully", len(valid_entries), len(entries))
        return valid_entries, error_messages

    def _is_valid_time_format(self, time_str: str) -> bool:
        """Check if time string is in valid format."""
        if not time_str:
            return True  # Empty is valid (None)

        # Try common time formats
        time_formats = ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M:%S %p"]

        for fmt in time_formats:
            try:
                datetime.strptime(time_str, fmt)
                return True
            except ValueError:
                continue

        # Check for basic HH:MM pattern
        return bool(re.match(r"^\d{1,2}:\d{2}$", time_str))


class DiaryMappingHelpers:
    """Helper utilities for diary data mapping operations (integrated from diary_mapping_helpers.py)."""

    # Common time formats for parsing
    TIME_PATTERNS: ClassVar[list[str]] = [
        r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$",  # HH:MM or HH:MM:SS
        r"^(\d{1,2})\.(\d{2})$",  # H.MM or HH.MM
        r"^(\d{1,2}):(\d{2})\s*(AM|PM)$",  # 12-hour format with AM/PM
        r"^(\d{3,4})$",  # HHMM format (e.g., 2330, 0700)
    ]

    # Common date formats for parsing
    DATE_PATTERNS: ClassVar[list[str]] = [
        r"^(\d{4})-(\d{1,2})-(\d{1,2})$",  # YYYY-MM-DD
        r"^(\d{1,2})/(\d{1,2})/(\d{4})$",  # MM/DD/YYYY
        r"^(\d{1,2})-(\d{1,2})-(\d{4})$",  # MM-DD-YYYY
        r"^(\d{4})/(\d{1,2})/(\d{1,2})$",  # YYYY/MM/DD
    ]

    @staticmethod
    def parse_comma_separated_columns(column_names: str | None) -> list[str]:
        """
        Parse comma-separated column names and return cleaned list.

        Args:
            column_names: Comma-separated string of column names, or None

        Returns:
            List of cleaned column names, empty list if input is None/empty

        """
        if not column_names:
            return []

        if not isinstance(column_names, str):
            logger.warning(f"Expected string for column names, got {type(column_names)}: {column_names}")
            return []

        # Split by comma and clean each name
        columns = [name.strip() for name in column_names.split(",")]

        # Filter out empty strings
        columns = [col for col in columns if col]

        # Validate each column name
        validated_columns = []
        for col in columns:
            try:
                # Use validate_string for basic validation
                InputValidator.validate_string(col, min_length=1, max_length=255, name="column_name")
                validated_columns.append(col)
            except ValidationError as e:
                logger.warning(f"Invalid column name '{col}': {e}")
                continue

        return validated_columns

    @staticmethod
    def extract_multiple_values_from_columns(row: pd.Series, column_names: str | None, separator: str = "; ") -> str | None:
        """
        Extract values from multiple comma-separated columns and combine them.

        Args:
            row: Pandas Series containing row data
            column_names: Comma-separated string of column names
            separator: String to use when joining multiple values

        Returns:
            Combined string of non-empty values, or None if no values found

        """
        columns = DiaryMappingHelpers.parse_comma_separated_columns(column_names)
        if not columns:
            return None

        values = []
        for column in columns:
            try:
                value = row.get(column)
                if not pd.isna(value) and str(value).strip():
                    values.append(str(value).strip())
            except Exception as e:
                logger.debug(f"Error extracting value from column '{column}': {e}")
                continue

        return separator.join(values) if values else None

    @staticmethod
    def parse_time_string(time_str: str | None) -> str | None:
        """
        Parse various time string formats into standardized HH:MM format.

        Args:
            time_str: Time string in various formats

        Returns:
            Standardized time string in HH:MM format, or None if invalid

        """
        if not time_str:
            return None

        # Clean input
        time_str = str(time_str).strip().upper()
        if not time_str:
            return None

        # Try each time pattern
        for pattern in DiaryMappingHelpers.TIME_PATTERNS:
            match = re.match(pattern, time_str)
            if match:
                try:
                    if "AM" in pattern or "PM" in pattern:
                        # 12-hour format
                        hour = int(match.group(1))
                        minute = int(match.group(2))
                        is_pm = "PM" in time_str

                        # Convert to 24-hour
                        if is_pm and hour != 12:
                            hour += 12
                        elif not is_pm and hour == 12:
                            hour = 0

                    elif pattern.endswith(r"(\d{3,4})$"):
                        # HHMM format
                        time_digits = match.group(1)
                        if len(time_digits) == 3:
                            hour = int(time_digits[0])
                            minute = int(time_digits[1:])
                        else:
                            hour = int(time_digits[:2])
                            minute = int(time_digits[2:])
                    else:
                        # Standard HH:MM format
                        hour = int(match.group(1))
                        minute = int(match.group(2))

                    # Validate ranges
                    if not (0 <= hour <= 23 and 0 <= minute <= 59):
                        logger.debug(f"Time values out of range: {hour}:{minute}")
                        continue

                    return f"{hour:02d}:{minute:02d}"

                except (ValueError, AttributeError) as e:
                    logger.debug(f"Error parsing time '{time_str}' with pattern {pattern}: {e}")
                    continue

        logger.debug(f"Could not parse time string: '{time_str}'")
        return None

    @staticmethod
    def parse_date_string(date_str: str | None) -> str | None:
        """
        Parse various date string formats into standardized YYYY-MM-DD format.

        Args:
            date_str: Date string in various formats

        Returns:
            Standardized date string in YYYY-MM-DD format, or None if invalid

        """
        if not date_str:
            return None

        # Handle pandas datetime objects
        if hasattr(date_str, "strftime"):
            try:
                return date_str.strftime("%Y-%m-%d")
            except Exception as e:
                logger.debug(f"Error formatting datetime object: {e}")
                return None

        # Clean input
        date_str = str(date_str).strip()
        if not date_str:
            return None

        # Try pandas datetime parsing first (most robust)
        try:
            parsed_date = pd.to_datetime(date_str, errors="coerce")
            if not pd.isna(parsed_date):
                return parsed_date.strftime("%Y-%m-%d")
        except Exception as e:
            logger.debug(f"Pandas datetime parsing failed for '{date_str}': {e}")

        # Try each date pattern
        for pattern in DiaryMappingHelpers.DATE_PATTERNS:
            match = re.match(pattern, date_str)
            if match:
                try:
                    if pattern.startswith(r"^(\d{4})"):
                        # YYYY-MM-DD or YYYY/MM/DD
                        year = int(match.group(1))
                        month = int(match.group(2))
                        day = int(match.group(3))
                    else:
                        # MM/DD/YYYY or MM-DD-YYYY
                        month = int(match.group(1))
                        day = int(match.group(2))
                        year = int(match.group(3))

                    # Validate ranges
                    if not (1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100):
                        logger.debug(f"Date values out of range: {year}-{month}-{day}")
                        continue

                    # Try to create date object to validate
                    test_date = datetime(year, month, day)
                    return test_date.strftime("%Y-%m-%d")

                except (ValueError, AttributeError) as e:
                    logger.debug(f"Error parsing date '{date_str}' with pattern {pattern}: {e}")
                    continue

        logger.debug(f"Could not parse date string: '{date_str}'")
        return None

    @staticmethod
    def extract_time_field_with_validation(row: pd.Series, column_name: str | None, default_value: str | None = None) -> str | None:
        """Extract and validate time field from row data with default handling."""
        if not column_name:
            return default_value

        try:
            value = row.get(column_name)
            if pd.isna(value):
                return default_value

            # Parse and validate time
            parsed_time = DiaryMappingHelpers.parse_time_string(str(value))
            return parsed_time if parsed_time else default_value

        except Exception as e:
            logger.debug(f"Error extracting time field from column '{column_name}': {e}")
            return default_value

    @staticmethod
    def extract_date_field_with_validation(row: pd.Series, column_name: str | None, default_value: str | None = None) -> str | None:
        """Extract and validate date field from row data with default handling."""
        if not column_name:
            return default_value

        try:
            value = row.get(column_name)
            if pd.isna(value):
                return default_value

            # Parse and validate date
            parsed_date = DiaryMappingHelpers.parse_date_string(str(value))
            return parsed_date if parsed_date else default_value

        except Exception as e:
            logger.debug(f"Error extracting date field from column '{column_name}': {e}")
            return default_value

    @staticmethod
    def is_auto_calculated_column(mapping: DiaryColumnMapping, column_field_name: str) -> bool:
        """Check if a column is marked as auto-calculated in the mapping."""
        if not mapping or not mapping.auto_calculated_columns:
            return False

        return mapping.auto_calculated_columns.get(column_field_name, False)

    @staticmethod
    def extract_boolean_field_with_defaults(
        row: pd.Series,
        column_name: str | None,
        default_value: bool | None = None,
        true_values: list[str] | None = None,
        false_values: list[str] | None = None,
    ) -> bool | None:
        """Extract boolean field from row data with customizable true/false values and defaults."""
        if not column_name:
            return default_value

        # Set default value lists
        if true_values is None:
            true_values = ["yes", "y", "true", "1", "on", "nap", "occurred"]
        if false_values is None:
            false_values = ["no", "n", "false", "0", "off", "none", ""]

        try:
            value = row.get(column_name)
            if pd.isna(value):
                return default_value

            if isinstance(value, bool):
                return value

            # Convert to lowercase string for comparison
            str_value = str(value).strip().lower()

            if str_value in true_values:
                return True
            if str_value in false_values:
                return False
            # Try numeric conversion
            try:
                numeric_value = float(str_value)
                return numeric_value != 0
            except (ValueError, TypeError):
                pass

            logger.debug(f"Could not interpret boolean value '{value}' from column '{column_name}'")
            return default_value

        except Exception as e:
            logger.debug(f"Error extracting boolean field from column '{column_name}': {e}")
            return default_value

    @staticmethod
    def normalize_column_name(column_name: str) -> str:
        """Normalize column name for consistent comparison and matching."""
        if not column_name:
            return ""

        # Convert to lowercase, strip whitespace, replace spaces with underscores
        normalized = str(column_name).lower().strip()
        normalized = re.sub(r"\s+", "_", normalized)

        # Remove special characters except underscores and alphanumeric
        return re.sub(r"[^a-z0-9_]", "", normalized)

    @staticmethod
    def find_best_column_match(target_patterns: list[str], available_columns: list[str]) -> str | None:
        """Find the best matching column name from available columns using pattern matching."""
        if not target_patterns or not available_columns:
            return None

        # Normalize available columns for comparison
        normalized_columns = {DiaryMappingHelpers.normalize_column_name(col): col for col in available_columns}

        # Try each pattern
        for pattern in target_patterns:
            pattern_lower = pattern.lower().strip()

            # First try exact match
            if pattern_lower in normalized_columns:
                return normalized_columns[pattern_lower]

            # Try substring matching
            for normalized, original in normalized_columns.items():
                if pattern_lower in normalized or normalized in pattern_lower:
                    return original

            # Try regex matching
            try:
                pattern_regex = re.compile(pattern_lower, re.IGNORECASE)
                for normalized, original in normalized_columns.items():
                    if pattern_regex.search(normalized) or pattern_regex.search(original):
                        return original
            except re.error:
                # Invalid regex pattern, skip
                continue

        return None

    @staticmethod
    def validate_diary_mapping(mapping: DiaryColumnMapping, available_columns: list[str]) -> dict[str, list[str]]:
        """Validate diary column mapping against available columns and return validation results."""
        results = {"valid": [], "missing": [], "invalid": []}

        # Get all mapping fields
        mapping_fields = [
            ("participant_id_column_name", mapping.participant_id_column_name),
            ("sleep_onset_time_column_name", mapping.sleep_onset_time_column_name),
            ("sleep_offset_time_column_name", mapping.sleep_offset_time_column_name),
            ("napped_column_name", mapping.napped_column_name),
            ("nap_onset_time_column_name", mapping.nap_onset_time_column_name),
            ("nap_offset_time_column_name", mapping.nap_offset_time_column_name),
            ("nonwear_occurred_column_name", mapping.nonwear_occurred_column_name),
            ("nonwear_reason_column_names", mapping.nonwear_reason_column_names),
            ("nonwear_start_time_column_names", mapping.nonwear_start_time_column_names),
            ("nonwear_end_time_column_names", mapping.nonwear_end_time_column_names),
            ("in_bed_time_column_name", mapping.in_bed_time_column_name),
            ("sleep_onset_date_column_name", mapping.sleep_onset_date_column_name),
            ("sleep_offset_date_column_name", mapping.sleep_offset_date_column_name),
            ("todays_date_column_name", mapping.todays_date_column_name),
            ("nap_onset_date_column_name", mapping.nap_onset_date_column_name),
            ("nap_offset_date_column_name", mapping.nap_offset_date_column_name),
        ]

        for field_name, column_names in mapping_fields:
            if not column_names:
                results["missing"].append(field_name)
                continue

            # Handle comma-separated column names
            column_list = DiaryMappingHelpers.parse_comma_separated_columns(column_names)

            valid_columns = []
            invalid_columns = []

            for column in column_list:
                if column in available_columns:
                    valid_columns.append(column)
                else:
                    invalid_columns.append(column)

            if valid_columns and not invalid_columns:
                results["valid"].append(f"{field_name}: {', '.join(valid_columns)}")
            elif invalid_columns:
                results["invalid"].append(f"{field_name}: invalid columns {invalid_columns}")
                if valid_columns:
                    results["valid"].append(f"{field_name}: partial match {valid_columns}")

        return results
