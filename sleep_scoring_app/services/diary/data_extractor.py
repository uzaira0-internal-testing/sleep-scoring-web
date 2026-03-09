"""Data extraction utilities for diary import operations."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, ClassVar

import pandas as pd

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import DiaryColumnMapping

logger = logging.getLogger(__name__)


class DiaryDataExtractor:
    """Extracts and converts data fields from diary rows."""

    # Nonwear reason code mappings
    NONWEAR_REASON_CODES: ClassVar[dict[str, str]] = {
        "1": "Bath/Shower",
        "1.0": "Bath/Shower",
        "2": "Swimming",
        "2.0": "Swimming",
        "3": "Other",
        "3.0": "Other",
    }

    # Timepoint variation mappings for flexible matching
    TIMEPOINT_VARIATIONS: ClassVar[dict[str, list[str]]] = {
        "BO": ["BO", "B0", "BL", "Bo", "Bl", "bl", "b0", "bo"],
        "B0": ["B0", "BO", "BL", "b0", "bo", "bl"],
        "BL": ["BL", "BO", "B0", "Bl", "bl", "bo", "b0"],
        "Bo": ["Bo", "BO", "B0", "BL", "bo", "bl", "b0"],
        "Bl": ["Bl", "BL", "BO", "B0", "bl", "bo", "b0"],
        "bo": ["bo", "BO", "B0", "BL", "Bo", "Bl", "bl", "b0"],
        "bl": ["bl", "BL", "BO", "B0", "Bl", "Bo", "bo", "b0"],
        "b0": ["b0", "B0", "BO", "BL", "bo", "bl", "Bo", "Bl"],
        "P1": ["P1", "p1"],
        "p1": ["p1", "P1"],
        "P2": ["P2", "p2"],
        "p2": ["p2", "P2"],
        "P3": ["P3", "p3"],
        "p3": ["p3", "P3"],
    }

    def extract_participant_id(self, row: pd.Series, column_mapping: DiaryColumnMapping) -> str | None:
        """Extract participant ID from row data."""
        if not column_mapping.participant_id_column_name:
            logger.debug("No participant_id_column_name configured")
            return None

        try:
            value = row.get(column_mapping.participant_id_column_name)
            logger.debug(f"Extracted participant ID value: {value} from column {column_mapping.participant_id_column_name}")
            if pd.isna(value):
                logger.debug("Participant ID value is NaN")
                return None

            # Convert to string and clean
            participant_id = str(value).strip()
            logger.debug(f"Cleaned participant ID: {participant_id}")

            # If already a clean number, return as-is
            if participant_id.isdigit():
                return participant_id

            from sleep_scoring_app.utils.participant_extractor import (
                extract_participant_info,
            )

            extracted_info = extract_participant_info(participant_id)
            if extracted_info and extracted_info.numerical_id != "UNKNOWN":
                # Return full_id to preserve timepoint and group information
                return extracted_info.full_id

            return participant_id

        except Exception as e:
            logger.exception(f"Failed to extract participant ID: {e}")
            return None

    def extract_diary_date(self, row: pd.Series, column_mapping: DiaryColumnMapping) -> str | None:
        """Extract diary date from row data."""
        # Try different date columns in order of preference
        date_columns: list[str | None] = []

        # Add date_of_last_night if it exists in the configuration
        if column_mapping.date_of_last_night_column_name:
            date_columns.append(column_mapping.date_of_last_night_column_name)
            logger.debug(f"Looking for date in column: {column_mapping.date_of_last_night_column_name}")

        # Add standard date columns
        date_columns.extend(
            [
                column_mapping.todays_date_column_name,
                column_mapping.sleep_onset_date_column_name,
                column_mapping.sleep_offset_date_column_name,
            ]
        )

        for column_name in date_columns:
            if column_name:
                try:
                    value = row.get(column_name)
                    logger.debug(f"Checking date column '{column_name}': value = {value}")
                    if pd.isna(value):
                        logger.debug(f"Column '{column_name}' value is NaN")
                        continue

                    # Try to parse as date
                    if hasattr(value, "strftime"):
                        date_str = value.strftime("%Y-%m-%d")
                        logger.debug(f"Parsed date from datetime object: {date_str}")
                        return date_str
                    # Try to parse string date
                    parsed_date = pd.to_datetime(str(value))
                    date_str = parsed_date.strftime("%Y-%m-%d")
                    logger.debug(f"Parsed date from string: {date_str}")
                    return date_str

                except Exception as e:
                    logger.debug(f"Failed to parse date from column '{column_name}': {e}")
                    continue

        return None

    def extract_time_field(self, row: pd.Series, column_name: str | None) -> str | None:
        """Extract time field from row data, properly handling AM/PM format."""
        if not column_name:
            logger.debug("Time field extraction skipped: column_name is None")
            return None

        try:
            # Check if the column exists in the row
            if column_name not in row.index:
                logger.debug(f"Time column '{column_name}' not found in data")
                return None

            value = row.get(column_name)
            if pd.isna(value):
                logger.debug(f"Time column '{column_name}' value is NaN")
                return None

            # Convert to string and clean
            time_str = str(value).strip()
            logger.debug(f"Extracting time from column '{column_name}': raw value = {value}, cleaned = {time_str}")

            # Try to parse as datetime object first
            if hasattr(value, "strftime"):
                return value.strftime("%H:%M")

            # Try to parse using pandas to_datetime which handles AM/PM format
            try:
                parsed_time = pd.to_datetime(time_str, format="%I:%M %p")
                result = parsed_time.strftime("%H:%M")
                logger.debug(f"Successfully parsed AM/PM time '{time_str}' to '{result}'")
                return result
            except (ValueError, TypeError):
                logger.debug(f"Failed to parse '{time_str}' as AM/PM format")

            # Try alternative parsing with pandas (handles various formats automatically)
            try:
                parsed_time = pd.to_datetime(time_str)
                result = parsed_time.strftime("%H:%M")
                logger.debug(f"Successfully parsed time '{time_str}' to '{result}' using auto format")
                return result
            except (ValueError, TypeError):
                logger.debug(f"Failed to auto-parse time '{time_str}'")

            # Fallback to regex for simple HH:MM format (24-hour)
            time_match = re.search(r"(\d{1,2}):(\d{2})", time_str)
            if time_match:
                result = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
                logger.debug(f"Fallback regex parsed '{time_str}' to '{result}' (assuming 24-hour format)")
                return result

            logger.debug(f"Could not parse time '{time_str}', returning as-is")
            return time_str

        except Exception as e:
            logger.debug(f"Exception while parsing time from column '{column_name}': {e}")
            return None

    def extract_integer_field(self, row: pd.Series, column_name: str | None) -> int | None:
        """Extract integer field from row data."""
        if not column_name:
            return None

        try:
            # Check if the column exists in the row
            if column_name not in row.index:
                logger.debug(f"Integer column '{column_name}' not found in data")
                return None

            value = row.get(column_name)
            if pd.isna(value):
                return None

            # Handle numeric values (float/int)
            if isinstance(value, int | float):
                return int(value)

            # Try to parse string to integer
            str_value = str(value).strip()
            try:
                return int(float(str_value))  # Parse as float first to handle "1.0"
            except ValueError:
                return None

        except Exception:
            return None

    def extract_boolean_field(self, row: pd.Series, column_name: str | None) -> bool | None:
        """Extract boolean field from row data."""
        if not column_name:
            return None

        try:
            # Check if the column exists in the row
            if column_name not in row.index:
                logger.debug(f"Boolean column '{column_name}' not found in data")
                return None

            value = row.get(column_name)
            if pd.isna(value):
                return None

            if isinstance(value, bool):
                return value

            # Handle numeric values (float/int)
            if isinstance(value, int | float):
                return bool(value)

            # Try to parse string boolean
            str_value = str(value).strip().lower()
            if str_value in ["yes", "y", "true", "1", "1.0", "on"]:
                return True
            if str_value in ["no", "n", "false", "0", "0.0", "off"]:
                return False

            return None

        except Exception:
            return None

    def extract_multiple_time_fields(self, row: pd.Series, column_names_str: str | None) -> tuple[str | None, str | None, str | None]:
        """
        Extract multiple time fields from comma-separated column names.

        Returns the first 3 values found from the provided column names.
        """
        if not column_names_str:
            return None, None, None

        column_names = [name.strip() for name in column_names_str.split(",")]
        times: list[str | None] = []

        for i, column_name in enumerate(column_names):
            if column_name:
                # Check if the column exists before trying to extract
                if column_name in row.index:
                    time_value = self.extract_time_field(row, column_name)
                    times.append(time_value)
                    if time_value:
                        logger.debug(f"Found time value '{time_value}' in column '{column_name}' (position {i + 1})")
                else:
                    logger.debug(f"Column '{column_name}' not found in data (position {i + 1})")
                    times.append(None)
            else:
                times.append(None)

        # Pad with None to ensure we return exactly 3 values
        while len(times) < 3:
            times.append(None)

        return times[0], times[1], times[2]

    def extract_multiple_text_fields(self, row: pd.Series, column_names_str: str | None) -> tuple[str | None, str | None, str | None]:
        """
        Extract multiple text fields from comma-separated column names.

        Returns the first 3 values found from the provided column names.
        """
        if not column_names_str:
            return None, None, None

        column_names = [name.strip() for name in column_names_str.split(",")]
        texts: list[str | None] = []

        for i, column_name in enumerate(column_names):
            if column_name:
                try:
                    # Check if the column exists before trying to extract
                    if column_name in row.index:
                        value = row.get(column_name)
                        if pd.isna(value):
                            texts.append(None)
                        else:
                            text_value = str(value).strip()
                            texts.append(text_value)
                            logger.debug(f"Found text value '{text_value}' in column '{column_name}' (position {i + 1})")
                    else:
                        logger.debug(f"Text column '{column_name}' not found in data (position {i + 1})")
                        texts.append(None)
                except Exception:
                    texts.append(None)
            else:
                texts.append(None)

        # Pad with None to ensure we return exactly 3 values
        while len(texts) < 3:
            texts.append(None)

        return texts[0], texts[1], texts[2]

    def convert_nonwear_reason_code(self, reason: str | None) -> str | None:
        """Convert nonwear reason code to descriptive text."""
        if reason is None:
            return None

        reason_str = str(reason).strip()
        return self.NONWEAR_REASON_CODES.get(reason_str, reason_str)

    def extract_multiple_nap_fields(
        self, row: pd.Series, column_mapping: DiaryColumnMapping
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """
        Extract multiple nap fields (onset and offset times for naps 2 and 3).

        Returns:
            Tuple of (nap_onset_time_2, nap_onset_time_3, nap_offset_time_2, nap_offset_time_3)

        """
        nap_onset_2 = None
        nap_onset_3 = None
        nap_offset_2 = None
        nap_offset_3 = None

        # Extract nap onset times from the multiple nap columns
        if column_mapping.nap_onset_time_column_names:
            nap_onset_2, nap_onset_3, _ = self.extract_multiple_time_fields(row, column_mapping.nap_onset_time_column_names)
            if nap_onset_2:
                logger.debug(f"Found second nap onset time: {nap_onset_2}")
            if nap_onset_3:
                logger.debug(f"Found third nap onset time: {nap_onset_3}")

        # Extract nap offset times from the multiple nap columns
        if column_mapping.nap_offset_time_column_names:
            nap_offset_2, nap_offset_3, _ = self.extract_multiple_time_fields(row, column_mapping.nap_offset_time_column_names)
            if nap_offset_2:
                logger.debug(f"Found second nap offset time: {nap_offset_2}")
            if nap_offset_3:
                logger.debug(f"Found third nap offset time: {nap_offset_3}")

        # Warn about incomplete nap data
        if (nap_onset_2 and not nap_offset_2) or (nap_offset_2 and not nap_onset_2):
            logger.warning(f"Incomplete second nap data: onset={nap_onset_2}, offset={nap_offset_2}")
        if (nap_onset_3 and not nap_offset_3) or (nap_offset_3 and not nap_onset_3):
            logger.warning(f"Incomplete third nap data: onset={nap_onset_3}, offset={nap_offset_3}")

        return nap_onset_2, nap_onset_3, nap_offset_2, nap_offset_3

    def generate_timepoint_variations(self, participant_id: str) -> list[str]:
        """Generate timepoint variations for flexible matching."""
        if " " not in participant_id:
            return [participant_id]  # Not a full ID, return as-is

        parts = participant_id.split()
        if len(parts) < 3:
            return [participant_id]  # Not in expected format

        numerical_id = parts[0]
        timepoint = parts[1]
        group = parts[2]

        # Get variations for this timepoint
        variations = self.TIMEPOINT_VARIATIONS.get(timepoint, [timepoint])

        # Generate full participant IDs with each variation
        result = []
        for variation in variations:
            variation_id = f"{numerical_id} {variation} {group}"
            result.append(variation_id)

        logger.debug(f"Generated timepoint variations for '{participant_id}': {result[:5]}{'...' if len(result) > 5 else ''}")
        return result
