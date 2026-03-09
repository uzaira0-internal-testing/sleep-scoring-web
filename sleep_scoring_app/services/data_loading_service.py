"""
Data loading service for file discovery and activity data loading.
Handles CSV files, database queries, and activity data extraction.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from sleep_scoring_app.core.constants import ActivityDataPreference, FileSourceType
from sleep_scoring_app.core.dataclasses import FileInfo
from sleep_scoring_app.core.exceptions import DatabaseError, DataLoadingError, ErrorCodes, ValidationError
from sleep_scoring_app.core.validation import InputValidator
from sleep_scoring_app.utils.date_range import get_range_for_view_mode

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import AlignedActivityData
    from sleep_scoring_app.data.database import DatabaseManager

logger = logging.getLogger(__name__)


class DataLoadingService:
    """Handles file discovery and activity data loading operations."""

    def __init__(self, database_manager: DatabaseManager, data_folder: Path) -> None:
        self.db_manager = database_manager
        self.data_folder = data_folder
        self.use_database = True

        # Current CSV state (for fallback)
        self.current_data = None
        self.current_date_col = None
        self.current_time_col = None
        self.timestamps_combined = None
        self.current_activity_col = None

    def find_data_files(self) -> list[FileInfo]:
        """Find available data files - prioritize database imports, then local CSV files."""
        data_files: list[FileInfo] = []
        found_filenames: set[str] = set()

        # 1. Try to get imported files from database
        try:
            imported_files = self.db_manager.get_available_files()
            for db_file in imported_files:
                filename = db_file["filename"]
                original_path = db_file.get("original_path")
                data_files.append(
                    FileInfo(
                        filename=filename,
                        source=FileSourceType.DATABASE,
                        source_path=Path(original_path) if original_path else None,
                        participant_id=db_file.get("participant_id", "Unknown"),
                        participant_group=db_file.get("participant_group", ""),
                        total_records=db_file.get("total_records", 0),
                        import_date=db_file.get("import_date"),
                        start_date=db_file.get("date_range_start"),
                        end_date=db_file.get("date_range_end"),
                    )
                )
                found_filenames.add(filename)
            logger.debug(f"Found {len(data_files)} imported files in database")
        except Exception as e:
            logger.warning("Failed to load database files: %s", e)

        # 2. Look for CSV files in the data folder (TOP LEVEL ONLY)
        if self.data_folder and self.data_folder.exists():
            try:
                for csv_file in self.data_folder.glob("*.csv"):
                    try:
                        filename = csv_file.name
                        if filename in found_filenames:
                            continue  # Skip if already found in DB

                        data_files.append(
                            FileInfo(
                                filename=filename,
                                source=FileSourceType.CSV,
                                source_path=csv_file,
                            )
                        )
                    except (OSError, ValueError, PermissionError):
                        continue
            except Exception as e:
                logger.warning("Failed to scan CSV files: %s", e)

        # Sort by filename
        data_files.sort(key=lambda f: f.filename)
        logger.info(f"Total data files discovered: {len(data_files)}")
        return data_files

    def load_selected_file(self, file_info: FileInfo, skip_rows: int = 10) -> list[date | datetime]:
        """Load file and extract available dates - handles both database and CSV sources."""
        if not file_info:
            return []

        if file_info.source == FileSourceType.DATABASE:
            return self._load_database_file(file_info.filename)

        # CSV file - use source_path
        if file_info.source_path:
            return self._load_csv_file(file_info.source_path, skip_rows)

        return []

    def _load_database_file(self, filename: str) -> list[date | datetime]:
        """Load file dates from database."""
        try:
            # Database requires filename-only, not full paths
            if "/" in filename or "\\" in filename:
                logger.warning(
                    "FILENAME FORMAT ERROR: Expected filename-only but got path: '%s'. "
                    "Database queries require filename-only (e.g., 'DEMO-001.csv'). "
                    "This will likely cause 0 rows returned.",
                    filename,
                )
                # Extract just the filename as a recovery attempt
                from pathlib import Path

                extracted_filename = Path(filename).name
                logger.warning("Attempting recovery with extracted filename: '%s'", extracted_filename)
                filename = extracted_filename

            dates = self.db_manager.get_file_date_ranges(filename)
            if not dates:
                logger.warning("DATABASE QUERY RETURNED 0 DATES for '%s'. This file may not be imported or has no activity data.", filename)
                return []
            return dates
        except Exception:
            logger.exception(f"Failed to load dates from database for {filename}")
            return []

    def _load_csv_file(self, file_path: Path, skip_rows: int = 10) -> list[date | datetime]:
        """Load dates from CSV file."""
        if not file_path:
            return []

        try:
            # Validate inputs
            validated_path = InputValidator.validate_file_path(file_path, must_exist=True, allowed_extensions={".csv"})
            skip_rows = InputValidator.validate_integer(skip_rows, min_val=0, max_val=1000, name="skip_rows")

            logger.debug("Loading file: %s", validated_path)
            logger.debug("Skipping %s rows", skip_rows)

            # Read CSV file, skipping specified number of rows
            df = pd.read_csv(validated_path, skiprows=skip_rows)

            # Validate loaded data
            if df.empty:
                msg = "CSV file is empty"
                raise DataLoadingError(msg, ErrorCodes.INVALID_INPUT)

            if len(df) > 1000000:  # Limit to prevent memory issues
                msg = f"CSV file too large: {len(df)} rows. Maximum allowed: 1,000,000"
                raise DataLoadingError(msg, ErrorCodes.MEMORY_LIMIT_EXCEEDED)

            logger.debug("CSV columns: %s", list(df.columns))
            logger.debug("CSV shape: %s", df.shape)

            # Find separate DATE and TIME columns and combine them
            date_col = None
            time_col = None

            # Look for DATE column (handle whitespace)
            for col in df.columns:
                col_lower = col.strip().lower()
                if col_lower == "date":
                    date_col = col
                    logger.debug("✓ Found date column: '%s'", col)
                    break

            # Look for TIME column (handle whitespace)
            for col in df.columns:
                col_lower = col.strip().lower()
                if col_lower == "time":
                    time_col = col
                    logger.debug("✓ Found time column: '%s'", col)
                    break

            if date_col is None or time_col is None:
                logger.debug("❌ Could not find both DATE and TIME columns. Available columns: %s", list(df.columns))
                logger.debug("Found DATE column: %s", date_col)
                logger.debug("Found TIME column: %s", time_col)
                # Try fallback to single datetime column
                datetime_col = None
                for col in df.columns:
                    col_lower = col.lower()
                    if any(keyword in col_lower for keyword in ["datetime", "timestamp"]):
                        datetime_col = col
                        logger.debug("⚠ Using single datetime column as fallback: %s", datetime_col)
                        break

                if datetime_col is None:
                    datetime_col = df.columns[0]
                    logger.debug("⚠ Using first column as last resort: %s", datetime_col)

                # Parse single datetime column with robust error handling
                try:
                    timestamps = pd.to_datetime(df[datetime_col], infer_datetime_format=True)
                except (ValueError, TypeError, pd.errors.ParserError) as e:
                    logger.debug("Standard datetime parsing failed for column %s: %s", datetime_col, e)
                    # Fall back to automatic detection with errors='coerce'
                    timestamps = pd.to_datetime(df[datetime_col], errors="coerce")
                    if timestamps.isna().any():
                        logger.warning("Some timestamps in column %s could not be parsed", datetime_col)
                        # Drop rows with invalid timestamps
                        valid_mask = ~timestamps.isna()
                        timestamps = timestamps[valid_mask]
                        df = df[valid_mask]
                        logger.warning("Dropped %s rows with invalid timestamps", (~valid_mask).sum())
            else:
                # Combine DATE and TIME columns
                logger.debug("✓ Combining DATE column '%s' and TIME column '%s'", date_col, time_col)
                logger.debug("Sample date values: %s", df[date_col].head().tolist())
                logger.debug("Sample time values: %s", df[time_col].head().tolist())

                # Combine date and time columns
                datetime_strings = df[date_col].astype(str) + " " + df[time_col].astype(str)

                # Try different date formats that are common in ActiGraph data
                try:
                    # First try with infer_datetime_format=True
                    timestamps = pd.to_datetime(datetime_strings)
                except (ValueError, TypeError, pd.errors.ParserError) as e1:
                    logger.debug("Standard datetime parsing failed: %s", e1)
                    # Fall back to automatic detection with errors='coerce'
                    timestamps = pd.to_datetime(datetime_strings, errors="coerce")
                    if timestamps.isna().any():
                        logger.warning("Some timestamps could not be parsed and were set to NaT")
                        # Drop rows with invalid timestamps
                        valid_mask = ~timestamps.isna()
                        timestamps = timestamps[valid_mask]
                        df = df[valid_mask]
                        logger.warning("Dropped %s rows with invalid timestamps", (~valid_mask).sum())
                logger.debug("✓ Successfully combined date and time columns")
                logger.debug("Sample combined datetime: %s", timestamps.head().tolist())

            # Store the full dataset
            self.current_data = df
            self.current_date_col = date_col
            self.current_time_col = time_col
            self.timestamps_combined = timestamps  # Store the combined timestamps

            # Find vector magnitude column specifically
            activity_col = None

            # First priority: look for vector magnitude columns
            for col in df.columns:
                col_lower = col.lower()
                if any(keyword in col_lower for keyword in ["vector", "magnitude", "vm", "vectormagnitude"]):
                    activity_col = col
                    logger.debug("✓ Found vector magnitude column: %s", col)
                    break

            # Second priority: other activity-related columns (generic patterns only)
            if activity_col is None:
                for col in df.columns:
                    col_lower = col.lower()
                    if any(keyword in col_lower for keyword in ["activity", "count"]):
                        activity_col = col
                        logger.debug("⚠ Using activity column (no vector magnitude found): %s", col)
                        break

            # Fallback: last numeric column
            if activity_col is None:
                numeric_cols = df.select_dtypes(include=[np.number]).columns
                activity_col = numeric_cols[-1] if len(numeric_cols) > 0 else df.columns[-1]
                logger.debug("⚠ Using fallback numeric column: %s", activity_col)

            self.current_activity_col = activity_col
            logger.debug("Final activity column selection: %s", activity_col)

            # Extract unique dates
            dates = [ts.date() for ts in timestamps]
            unique_dates = sorted(set(dates))

            # Convert back to datetime objects (at noon for consistency)
            datetime_dates: list[date | datetime] = [datetime.combine(d, datetime.min.time().replace(hour=12)) for d in unique_dates]

            logger.debug("Found %s unique dates in file: %s to %s", len(datetime_dates), unique_dates[0], unique_dates[-1])
            return datetime_dates

        except pd.errors.EmptyDataError as e:
            msg = "CSV file is empty or corrupted"
            raise DataLoadingError(msg, ErrorCodes.FILE_CORRUPTED) from e
        except pd.errors.ParserError as e:
            msg = f"CSV parsing error: {e}"
            raise DataLoadingError(msg, ErrorCodes.INVALID_FORMAT) from e
        except FileNotFoundError as e:
            msg = f"File not found: {file_path}"
            raise DataLoadingError(msg, ErrorCodes.FILE_NOT_FOUND) from e
        except PermissionError as e:
            msg = f"Permission denied: {file_path}"
            raise DataLoadingError(msg, ErrorCodes.FILE_PERMISSION_DENIED) from e
        except Exception as e:
            logger.warning("Error loading file %s: %s", file_path, e)
            msg = f"Failed to load file: {e}"
            raise DataLoadingError(msg, ErrorCodes.INVALID_INPUT) from e

    def load_real_data(
        self, target_date, hours, filename: str | None = None, activity_column: ActivityDataPreference | None = None
    ) -> tuple[list[datetime], list[float]] | tuple[None, None]:
        """Load real activity data with configurable activity column - prioritize database, fallback to CSV."""
        # Try database first if filename is provided
        if filename and self.use_database:
            try:
                database_result = self._load_database_activity_data(filename, target_date, hours, activity_column)
                if database_result[0] is not None and database_result[1] is not None:
                    return database_result
                logger.warning("Database returned no activity data for %s; attempting CSV fallback", filename)
            except (DatabaseError, ValidationError, KeyError) as e:
                logger.warning("Failed to load from database, falling back to CSV: %s", e)

        # Fallback to CSV data if available
        if self.current_data is not None:
            return self._load_csv_activity_data(target_date, hours, activity_column)

        # Final fallback - this is a problem the user should know about
        logger.warning("No data source available for %s on %s. Check that the file was imported correctly.", filename, target_date)
        return None, None

    def load_unified_activity_data(self, filename: str, target_date: datetime | date, hours: int = 48) -> dict[str, list] | None:
        """
        Load ALL activity columns in ONE query with unified timestamps.

        This is the SINGLE SOURCE OF TRUTH for activity data loading.
        All columns share the SAME timestamps, preventing alignment bugs.

        Args:
            filename: Name of file to load (filename only, not full path)
            target_date: Target date for data loading
            hours: Number of hours to load (default 48)

        Returns:
            Dictionary with keys: 'timestamps', 'axis_y', 'axis_x', 'axis_z', 'vector_magnitude'
            All lists have the SAME length (guaranteed).
            Returns None if loading fails.

        """
        if not filename or not self.use_database:
            return None

        try:
            # Validate filename format
            if "/" in filename or "\\" in filename:
                logger.warning("Path detected in filename, extracting: %s", filename)
                from pathlib import Path

                filename = Path(filename).name

            # Convert date to datetime if needed
            if isinstance(target_date, date) and not isinstance(target_date, datetime):
                target_datetime = datetime.combine(target_date, datetime.min.time())
            else:
                target_datetime = target_date

            # Calculate time range
            date_range = get_range_for_view_mode(target_datetime, hours)
            start_time = date_range.start
            end_time = date_range.end

            # Load ALL columns in ONE query
            result = self.db_manager.load_all_activity_columns(filename, start_time, end_time)

            if not result or not result.get("timestamps"):
                logger.warning("No unified data found for %s in range %s to %s", filename, start_time, end_time)
                return None

            logger.info(
                "Loaded unified activity data: %d rows, all columns aligned",
                len(result["timestamps"]),
            )
            return result

        except Exception as e:
            logger.exception("Failed to load unified activity data: %s", e)
            return None

    def _load_database_activity_data(
        self, filename: str, target_date: datetime, hours: int, activity_column: ActivityDataPreference | None = None
    ) -> tuple[list[datetime], list[float]] | tuple[None, None]:
        """Load activity data from database with configurable activity column."""
        try:
            # Database requires filename-only, not full paths
            if "/" in filename or "\\" in filename:
                logger.warning(
                    "FILENAME FORMAT ERROR in activity load: Expected filename-only but got path: '%s'. Extracting filename for database query.",
                    filename,
                )
                from pathlib import Path

                filename = Path(filename).name

            # Convert date to datetime if needed
            if isinstance(target_date, date) and not isinstance(target_date, datetime):
                target_datetime = datetime.combine(target_date, datetime.min.time())
            else:
                target_datetime = target_date

            # Calculate time range using centralized utility
            date_range = get_range_for_view_mode(target_datetime, hours)
            start_time = date_range.start
            end_time = date_range.end

            # Load from database with specified activity column
            timestamps, activities = self.db_manager.load_raw_activity_data(
                filename,
                start_time,
                end_time,
                activity_column=activity_column or ActivityDataPreference.VECTOR_MAGNITUDE,
            )

            if not timestamps:
                logger.warning(
                    "DATABASE QUERY RETURNED 0 ROWS for '%s' in time range %s to %s. "
                    "This may indicate: (1) filename mismatch (expected filename-only, got full path?), "
                    "(2) no data exists for this date range, or (3) file was not imported correctly.",
                    filename,
                    start_time,
                    end_time,
                )
                return None, None

            logger.debug("Loaded %s data points from database for %s using %s column", len(timestamps), filename, activity_column)
            logger.debug("Activity data range: %.1f to %.1f", min(activities), max(activities))

            return timestamps, activities

        except Exception:
            logger.exception("Failed to load database activity data")
            raise

    def _load_csv_activity_data(
        self, target_date: datetime, hours: int, activity_column: ActivityDataPreference | None = None
    ) -> tuple[list[datetime], list[float]] | tuple[None, None]:
        """Load activity data from current CSV file with configurable activity column."""
        try:
            df = self.current_data
            if df is None:
                logger.warning("No CSV data loaded")
                return None, None

            # Use specified activity column or fall back to detected column
            activity_col = None
            if activity_column:
                # First try exact match
                if activity_column in df.columns:
                    activity_col = activity_column
                # If exact match fails and requested vector_magnitude, try variations
                elif activity_column.lower() == ActivityDataPreference.VECTOR_MAGNITUDE:
                    for col in df.columns:
                        col_lower = col.lower()
                        if any(keyword in col_lower for keyword in ["vector", "magnitude", "vm", "vectormagnitude"]):
                            activity_col = col
                            logger.debug("Found vector magnitude column variation: %s (requested %s)", col, activity_column)
                            break

            # Fall back to detected column if no match found
            if activity_col is None:
                activity_col = self.current_activity_col
                if activity_column:
                    logger.warning(
                        "COLUMN MATCH FAILED: Requested column '%s' not found. Available columns: %s. Using detected column: %s",
                        activity_column,
                        list(df.columns),
                        activity_col,
                    )

            # Use the pre-combined timestamps
            timestamps = self.timestamps_combined
            if timestamps is None:
                logger.warning("No combined timestamps available")
                return None, None
            timestamps_list = [ts.to_pydatetime() for ts in timestamps]

            # Get activity values
            activity_data = df[activity_col].fillna(0).astype(float).tolist()

            # Filter to requested time range
            # Convert date to datetime if needed
            if isinstance(target_date, date) and not isinstance(target_date, datetime):
                target_datetime = datetime.combine(target_date, datetime.min.time())
            else:
                target_datetime = target_date

            # Calculate time range using centralized utility
            date_range = get_range_for_view_mode(target_datetime, hours)
            start_time = date_range.start
            end_time = date_range.end

            # Filter data to time range
            filtered_timestamps = []
            filtered_activity = []

            for i, ts in enumerate(timestamps_list):
                if start_time <= ts <= end_time and i < len(activity_data):
                    filtered_timestamps.append(ts)
                    filtered_activity.append(max(0, activity_data[i]))  # Ensure non-negative

            if len(filtered_timestamps) == 0:
                logger.warning("No data found in time range %s to %s (check file import status)", start_time, end_time)
                return None, None

            logger.debug("Loaded %s data points from %s to %s", len(filtered_timestamps), filtered_timestamps[0], filtered_timestamps[-1])
            logger.debug("Activity data range: %.1f to %.1f", min(filtered_activity), max(filtered_activity))
            logger.debug("Sample activity values: %s", filtered_activity[:5] if len(filtered_activity) >= 5 else filtered_activity)
            return filtered_timestamps, filtered_activity

        except (ValueError, KeyError, IndexError, pd.errors.ParserError) as e:
            logger.warning("Error loading data: %s", e)
            return None, None

    def load_activity_data_only(
        self, filename: str, target_date: datetime, activity_column: ActivityDataPreference, hours: int = 24
    ) -> tuple[list[datetime], list[float]] | None:
        """
        Load only activity data for the specified column without triggering full reload cycle.

        Args:
            filename: Name of the file to load from
            target_date: Target date for data loading
            activity_column: Specific activity column to load
            hours: Number of hours to load (24 or 48)

        Returns:
            Tuple of (timestamps, activity_data) if successful, None if failed

        """
        date_str = target_date.date() if hasattr(target_date, "date") else target_date
        logger.info("TARGETED LOAD: Loading %s column from %s for %s (%sh)", activity_column, filename, date_str, hours)

        try:
            # Try database first
            if self.use_database:
                try:
                    database_result = self._load_database_activity_data(filename, target_date, hours, activity_column)
                    if database_result[0] is not None and database_result[1] is not None:
                        return database_result
                    logger.warning("TARGETED LOAD: Database returned no rows for %s", activity_column)
                except (DatabaseError, ValidationError, KeyError) as e:
                    logger.warning("TARGETED LOAD: Database load failed for %s: %s", activity_column, e)

            # Try CSV fallback if current data is available
            if self.current_data is not None:
                try:
                    csv_result = self._load_csv_activity_data(target_date, hours, activity_column)
                    if csv_result[0] is not None and csv_result[1] is not None:
                        return csv_result
                    logger.warning("TARGETED LOAD: CSV returned no rows for %s", activity_column)
                except Exception as e:
                    logger.warning("TARGETED LOAD: CSV load failed for %s: %s", activity_column, e)

            logger.warning("TARGETED LOAD: No data source available for %s column", activity_column)
            return None

        except Exception as e:
            logger.exception("TARGETED LOAD: Unexpected error loading %s: %s", activity_column, e)
            return None

    def load_axis_y_data_for_sadeh(self, filename: str, target_date: datetime, hours: int = 48) -> tuple[list[datetime], list[float]]:
        """
        Unified method to load axis_y (vertical) data specifically for Sadeh algorithm.
        This is the SINGLE SOURCE OF TRUTH for axis_y loading.

        Args:
            filename: Name of file to load from
            target_date: Target date for data loading
            hours: Number of hours to load (24 or 48, default 48)

        Returns:
            Tuple of (timestamps, axis_y_data) if successful, ([], []) if failed

        """
        aligned_data = self.load_axis_y_aligned(filename, target_date, hours)
        return list(aligned_data.timestamps), list(aligned_data.activity_values)

    def load_axis_y_aligned(self, filename: str, target_date: datetime, hours: int = 48) -> AlignedActivityData:
        """
        Load axis_y data as an aligned immutable container.

        This is the SINGLE SOURCE OF TRUTH for axis_y loading that guarantees
        timestamps and activity values are ALWAYS aligned and cannot get out of sync.

        Args:
            filename: Name of file to load from
            target_date: Target date for data loading
            hours: Number of hours to load (24 or 48, default 48)

        Returns:
            AlignedActivityData with timestamps and activity_values guaranteed to be aligned.
            Returns empty AlignedActivityData if loading fails.

        """
        from sleep_scoring_app.core.dataclasses import AlignedActivityData

        date_str = target_date.date() if hasattr(target_date, "date") else target_date
        logger.debug("AXIS_Y ALIGNED LOAD: Loading axis_y data for Sadeh from %s on %s (%sh)", filename, date_str, hours)

        # Convert date to datetime if needed
        if isinstance(target_date, date) and not isinstance(target_date, datetime):
            target_datetime = datetime.combine(target_date, datetime.min.time())
        else:
            target_datetime = target_date

        # Calculate time range using centralized utility
        date_range = get_range_for_view_mode(target_datetime, hours)
        start_time = date_range.start
        end_time = date_range.end

        # Always load axis_y data specifically
        try:
            # Try database first
            if self.use_database:
                try:
                    timestamps, activities = self.db_manager.load_raw_activity_data(
                        filename, start_time, end_time, activity_column=ActivityDataPreference.AXIS_Y
                    )
                    if timestamps:
                        logger.debug("AXIS_Y ALIGNED: Loaded %d points from database", len(timestamps))
                        # Create immutable aligned container - validates alignment at construction
                        return AlignedActivityData.from_lists(timestamps, activities, column_type="axis_y")
                except Exception as e:
                    logger.debug("AXIS_Y ALIGNED: Database load attempt failed: %s", e)

            # Try CSV fallback
            if self.current_data is not None:
                try:
                    timestamps, activities = self._load_csv_activity_data(target_date, hours, ActivityDataPreference.AXIS_Y)
                    if timestamps and activities:
                        logger.debug("AXIS_Y ALIGNED: Loaded %d points from CSV", len(timestamps))
                        return AlignedActivityData.from_lists(timestamps, activities, column_type="axis_y")
                except Exception as e:
                    logger.warning("AXIS_Y ALIGNED: CSV load failed: %s", e)

            # No data found - this is a user-visible problem
            logger.warning(
                "AXIS_Y ALIGNED: No axis_y data found for %s on %s. "
                "Sleep scoring algorithms require axis_y data. Check that the file was imported correctly.",
                filename,
                date_str,
            )
            return AlignedActivityData.empty(column_type="axis_y")

        except Exception as e:
            logger.warning("AXIS_Y ALIGNED: Unexpected error loading data for %s: %s", filename, e)
            return AlignedActivityData.empty(column_type="axis_y")

    def clear_current_data(self) -> None:
        """Clear current loaded CSV data."""
        self.current_data = None
        self.current_date_col = None
        self.current_time_col = None
        self.timestamps_combined = None
        self.current_activity_col = None
        logger.debug("Cleared current data")
