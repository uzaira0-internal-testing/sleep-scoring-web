#!/usr/bin/env python3
"""
Nonwear Sensor Data Service for Sleep Scoring Application
Handles loading and processing of nonwear time (NWT) sensor data and Choi algorithm results.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from sleep_scoring_app.core.constants import NonwearDataSource
from sleep_scoring_app.core.dataclasses import NonwearPeriod
from sleep_scoring_app.core.exceptions import (
    DataLoadingError,
    ErrorCodes,
)
from sleep_scoring_app.core.validation import InputValidator
from sleep_scoring_app.data.database import DatabaseManager

# Configure logging
logger = logging.getLogger(__name__)


class NonwearDataService:
    """Service for loading and managing nonwear sensor data."""

    def __init__(self, database_manager: DatabaseManager | None = None) -> None:
        self.db_manager = database_manager or DatabaseManager()
        self.data_base_path = None  # Will be set when data folder is provided

    def find_nonwear_sensor_files(self, data_folder: Path) -> list[Path]:
        """Find all nonwear sensor files in the data folder."""
        try:
            # Look for nonwear files directly in the data folder
            # No hardcoded subdirectory - use the actual data folder provided
            if not data_folder.exists():
                logger.info("Data folder does not exist: %s", data_folder)
                return []

            # Find all nonwear period files in the data folder
            pattern = "*_nonwear_periods.csv"
            nonwear_files = list(data_folder.glob(pattern))

            logger.info("Found %d nonwear sensor files", len(nonwear_files))
            return nonwear_files

        except Exception:
            logger.exception("Error finding nonwear sensor files")
            return []

    def find_choi_algorithm_files(self, data_folder: Path) -> list[Path]:
        """Find all Choi algorithm result files in the data folder."""
        try:
            # Look for Choi result files directly in the data folder
            # No hardcoded subdirectory - use the actual data folder provided
            if not data_folder.exists():
                logger.info("Data folder does not exist: %s", data_folder)
                return []

            # Find all Choi result files in the data folder
            pattern = "*60sec_choi.csv"
            choi_files = list(data_folder.glob(pattern))

            logger.info("Found %d Choi algorithm files", len(choi_files))
            return choi_files

        except Exception:
            logger.exception("Error finding Choi algorithm files")
            return []

    def extract_participant_from_filename(self, file_path: Path) -> str:
        """Extract participant ID from filename using centralized extractor."""
        from sleep_scoring_app.utils.participant_extractor import extract_participant_info

        participant_info = extract_participant_info(str(file_path))
        return participant_info.numerical_id

    def _extract_participant_id_from_filename(self, file_path: Path) -> str:
        """Extract participant ID from filename - must match format used when saving."""
        # Use the same method as extract_participant_from_filename to ensure consistency
        # between saving and querying nonwear periods
        return self.extract_participant_from_filename(file_path)

    def load_nonwear_sensor_periods(self, file_path: Path) -> list[NonwearPeriod]:
        """Load nonwear periods from sensor data file."""
        try:
            # Validate file
            validated_path = InputValidator.validate_file_path(file_path, must_exist=True, allowed_extensions={".csv"})

            # Load CSV - handle small/corrupted files gracefully
            try:
                df = pd.read_csv(validated_path)
            except pd.errors.EmptyDataError:
                logger.info("Nonwear sensor file %s contains no data", file_path.name)
                return []
            except (OSError, PermissionError, pd.errors.ParserError, UnicodeDecodeError) as e:
                logger.warning("Error reading CSV file %s: %s", file_path.name, e)
                return []

            # Check if file is empty (only headers or completely empty)
            if df.empty or len(df) == 0:
                logger.info("Nonwear sensor file %s is empty - no nonwear periods to load", file_path.name)
                return []

            # Validate required columns
            required_columns = ["start", "end", "participant_id"]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                msg = f"Missing required columns in {file_path.name}: {missing_columns}"
                raise DataLoadingError(
                    msg,
                    ErrorCodes.INVALID_FORMAT,
                )

            # Extract participant ID from filename if not reliable in data
            filename_participant = self.extract_participant_from_filename(file_path)

            periods = []
            for _, row in df.iterrows():
                try:
                    # Use participant ID from filename as it's more reliable
                    participant_id = filename_participant

                    period = NonwearPeriod(
                        start_time=datetime.fromisoformat(str(row["start"])),
                        end_time=datetime.fromisoformat(str(row["end"])),
                        participant_id=participant_id,
                        source=NonwearDataSource.NONWEAR_SENSOR,
                    )
                    periods.append(period)

                except (ValueError, KeyError, TypeError) as e:
                    logger.warning("Error processing row in %s: %s", file_path.name, e)
                    continue

            logger.debug("Loaded %d nonwear sensor periods from %s", len(periods), file_path.name)
            return periods

        except Exception as e:
            logger.exception("Failed to load nonwear sensor periods from %s", file_path)
            msg = f"Failed to load nonwear sensor data: {e}"
            raise DataLoadingError(
                msg,
                ErrorCodes.FILE_OPERATION_FAILED,
            ) from e

    def load_choi_algorithm_periods(self, file_path: Path) -> list[NonwearPeriod]:
        """Load wear periods from Choi algorithm results file."""
        try:
            # Validate file
            validated_path = InputValidator.validate_file_path(file_path, must_exist=True, allowed_extensions={".csv"})

            # Load CSV - handle small/corrupted files gracefully
            try:
                df = pd.read_csv(validated_path)
            except pd.errors.EmptyDataError:
                logger.info("Choi algorithm file %s contains no data", file_path.name)
                return []
            except (OSError, PermissionError, pd.errors.ParserError, UnicodeDecodeError) as e:
                logger.warning("Error reading CSV file %s: %s", file_path.name, e)
                return []

            # Check if file is empty (only headers or completely empty)
            if df.empty or len(df) == 0:
                logger.info("Choi algorithm file %s is empty - no periods to load", file_path.name)
                return []

            # Validate required columns
            required_columns = [
                "start_time",
                "end_time",
                "duration_minutes",
                "start_index",
                "end_index",
            ]
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                msg = f"Missing required columns in {file_path.name}: {missing_columns}"
                raise DataLoadingError(
                    msg,
                    ErrorCodes.INVALID_FORMAT,
                )

            # Extract participant ID from filename
            participant_id = self.extract_participant_from_filename(file_path)

            periods = []
            for _, row in df.iterrows():
                try:
                    period = NonwearPeriod(
                        start_time=datetime.fromisoformat(str(row["start_time"])),
                        end_time=datetime.fromisoformat(str(row["end_time"])),
                        participant_id=participant_id,
                        source=NonwearDataSource.CHOI_ALGORITHM,
                        duration_minutes=int(row["duration_minutes"]) if pd.notna(row["duration_minutes"]) else None,
                        start_index=int(row["start_index"]) if pd.notna(row["start_index"]) else None,
                        end_index=int(row["end_index"]) if pd.notna(row["end_index"]) else None,
                    )
                    periods.append(period)

                except (ValueError, KeyError, TypeError) as e:
                    logger.warning("Error processing row in %s: %s", file_path.name, e)
                    continue

            logger.debug("Loaded %d Choi algorithm periods from %s", len(periods), file_path.name)
            return periods

        except Exception as e:
            logger.exception("Failed to load Choi algorithm periods from %s", file_path)
            msg = f"Failed to load Choi algorithm data: {e}"
            raise DataLoadingError(
                msg,
                ErrorCodes.FILE_OPERATION_FAILED,
            ) from e

    def get_nonwear_periods_for_file(
        self,
        filename: str,
        source: NonwearDataSource,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[NonwearPeriod]:
        """Get nonwear periods for a specific file from database, optionally filtered by date range."""
        try:
            logger.debug("Getting nonwear periods for file: %s, source: %s", filename, source)

            participant_id = self._extract_participant_id_from_filename(Path(filename))
            logger.info("Extracted participant ID '%s' from filename '%s'", participant_id, filename)

            periods = self.db_manager.nonwear.get_periods_for_file(
                filename=filename,
                participant_id=participant_id,
                source=source,
                start_time=start_time,
                end_time=end_time,
            )

            if start_time and end_time:
                logger.info("Filtering nonwear periods for %s between %s and %s", filename, start_time, end_time)
                logger.info("Found %d periods in date range", len(periods))

            logger.debug("Returning %d nonwear periods for file %s", len(periods), filename)
            return periods

        except Exception:
            logger.exception("Failed to get nonwear periods for %s", filename)
            return []

    def save_nonwear_periods(self, periods: list[NonwearPeriod], filename: str) -> bool:
        """Save nonwear periods to database."""
        try:
            return self.db_manager.nonwear.save_periods(periods, filename)
        except Exception:
            logger.exception("Failed to save nonwear periods for %s", filename)
            return False

    def align_nonwear_with_activity(self, nonwear_periods: list[NonwearPeriod], activity_timestamps: list[datetime]) -> list[bool]:
        """
        Align nonwear periods with activity data timestamps.

        Returns a list of boolean values indicating nonwear status for each timestamp
        """
        try:
            nonwear_status = [False] * len(activity_timestamps)

            for period in nonwear_periods:
                try:
                    # Parse period timestamps
                    start_dt = pd.to_datetime(period.start_time)
                    end_dt = pd.to_datetime(period.end_time)

                    # Find matching activity timestamps
                    for i, activity_dt in enumerate(activity_timestamps):
                        if start_dt <= activity_dt <= end_dt:
                            nonwear_status[i] = True

                except (ValueError, TypeError, pd.errors.OutOfBoundsDatetime) as e:
                    logger.warning("Error processing nonwear period: %s", e)
                    continue

            nonwear_count = sum(nonwear_status)
            logger.debug("Aligned nonwear periods: %d/%d minutes marked as nonwear", nonwear_count, len(activity_timestamps))

            return nonwear_status

        except Exception:
            logger.exception("Failed to align nonwear periods with activity data")
            # Return all wear periods as fallback
            return [False] * len(activity_timestamps)
