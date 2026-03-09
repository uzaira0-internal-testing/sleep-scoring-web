#!/usr/bin/env python3
"""
CSV Data Transformer for Sleep Scoring Application
Handles CSV loading, column identification, and data transformation.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

from sleep_scoring_app.core.constants import ActivityColumn, ActivityDataPreference, DatabaseColumn

if TYPE_CHECKING:
    from pathlib import Path

    pass

logger = logging.getLogger(__name__)


class ColumnMapping:
    """Represents identified column mappings in a CSV file."""

    def __init__(
        self,
        date_col: str | None = None,
        time_col: str | None = None,
        activity_col: str | None = None,
        datetime_combined: bool = False,
        extra_cols: dict[str, str] | None = None,
    ) -> None:
        self.date_col = date_col
        self.time_col = time_col
        self.activity_col = activity_col
        self.datetime_combined = datetime_combined
        self.extra_cols = extra_cols or {}

    @property
    def is_valid(self) -> bool:
        """Check if column mapping has minimum required columns."""
        return self.date_col is not None and self.activity_col is not None


class CSVDataTransformer:
    """Transforms CSV data by identifying columns and processing values."""

    def __init__(self, max_file_size: int = 100 * 1024 * 1024) -> None:
        self.max_file_size = max_file_size

    def load_csv(self, file_path: Path, skip_rows: int) -> pd.DataFrame | None:
        """
        Load and validate CSV file.

        Args:
            file_path: Path to CSV file
            skip_rows: Number of rows to skip (for ActiGraph metadata)

        Returns:
            Loaded DataFrame or None if loading fails

        """
        try:
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                logger.error("CSV file too large: %.1f MB > %.1f MB", file_size / 1024 / 1024, self.max_file_size / 1024 / 1024)
                return None

            df = pd.read_csv(file_path, skiprows=skip_rows)

            if df.empty:
                return None

            if len(df) > 100000:
                logger.warning("Large CSV file %s: %s rows", file_path.name, len(df))

            return df

        except pd.errors.EmptyDataError:
            logger.exception("CSV file %s is empty", file_path.name)
            return None
        except pd.errors.ParserError:
            logger.exception("CSV parsing error in %s", file_path.name)
            return None
        except Exception:
            logger.exception("Error loading CSV %s", file_path.name)
            return None

    def identify_columns(self, df: pd.DataFrame, custom_columns: dict[str, str] | None = None) -> ColumnMapping:
        """
        Identify required and optional columns in CSV.

        Args:
            df: DataFrame to identify columns in
            custom_columns: Optional dict with keys 'date', 'time', 'activity', 'datetime_combined'
                          If provided and datetime_combined is True, time will be None

        Returns:
            ColumnMapping with identified columns

        """
        columns = list(df.columns)

        logger.debug("Available columns (raw): %s", columns)
        logger.debug("Available columns (repr): %s", [repr(col) for col in columns])

        # Use custom columns if provided
        if custom_columns:
            return self._process_custom_columns(df, custom_columns, columns)

        # Auto-detect columns
        return self._auto_detect_columns(columns)

    def _process_custom_columns(self, df: pd.DataFrame, custom_columns: dict[str, str], columns: list[str]) -> ColumnMapping:
        """Process user-specified custom column mappings."""
        date_col = custom_columns.get("date")
        time_col = custom_columns.get("time")
        activity_col = custom_columns.get("activity")
        datetime_combined = bool(custom_columns.get("datetime_combined", False))

        # Validate custom columns exist in dataframe
        if date_col and date_col not in columns:
            logger.warning("Custom date column '%s' not found in CSV columns", date_col)
            date_col = None
        if time_col and time_col not in columns:
            logger.warning("Custom time column '%s' not found in CSV columns", time_col)
            time_col = None
        if activity_col and activity_col not in columns:
            logger.warning("Custom activity column '%s' not found in CSV columns", activity_col)
            activity_col = None

        # If datetime is combined, time_col should be None
        if datetime_combined:
            time_col = None

        logger.info("Using custom columns: date=%s, time=%s, activity=%s, combined=%s", date_col, time_col, activity_col, datetime_combined)

        # Process custom axis columns
        extra_cols = self._process_custom_axis_columns(custom_columns, columns)

        # If no custom axis columns provided, fall back to standard detection
        if not extra_cols:
            extra_cols = self._find_extra_columns(columns)

        return ColumnMapping(date_col, time_col, activity_col, datetime_combined, extra_cols)

    def _process_custom_axis_columns(self, custom_columns: dict[str, str], columns: list[str]) -> dict[str, str]:
        """Extract and validate custom axis column mappings."""
        extra_cols = {}

        # Get custom axis columns from the custom_columns dict
        custom_axis_y = custom_columns.get(ActivityDataPreference.AXIS_Y)
        custom_axis_x = custom_columns.get(ActivityDataPreference.AXIS_X)
        custom_axis_z = custom_columns.get(ActivityDataPreference.AXIS_Z)
        custom_vm = custom_columns.get(ActivityDataPreference.VECTOR_MAGNITUDE)

        # Validate and add custom axis columns
        if custom_axis_y and custom_axis_y in columns:
            extra_cols[DatabaseColumn.AXIS_Y] = custom_axis_y
            logger.info("Using custom Y-Axis (vertical) column: %s", custom_axis_y)
        if custom_axis_x and custom_axis_x in columns:
            extra_cols[DatabaseColumn.AXIS_X] = custom_axis_x
            logger.info("Using custom X-Axis (lateral) column: %s", custom_axis_x)
        if custom_axis_z and custom_axis_z in columns:
            extra_cols[DatabaseColumn.AXIS_Z] = custom_axis_z
            logger.info("Using custom Z-Axis (forward) column: %s", custom_axis_z)
        if custom_vm and custom_vm in columns:
            extra_cols[DatabaseColumn.VECTOR_MAGNITUDE] = custom_vm
            logger.info("Using custom Vector Magnitude column: %s", custom_vm)

        return extra_cols

    def _auto_detect_columns(self, columns: list[str]) -> ColumnMapping:
        """Auto-detect columns using standard naming patterns."""
        date_col = None
        time_col = None
        datetime_combined = False

        # First check for combined datetime column (exact match)
        for col in columns:
            col_lower = col.lower().strip()
            if col_lower in ("datetime", "timestamp"):
                date_col = col
                datetime_combined = True
                logger.debug("Found combined datetime column: '%s'", col)
                break

        # If no combined datetime, look for separate date column
        if date_col is None:
            date_patterns = ["date", "datum", "day"]
            for col in columns:
                col_lower = col.lower().strip()
                for pattern in date_patterns:
                    if pattern in col_lower:
                        date_col = col
                        logger.debug("Found date column: '%s' (repr: %r, matched pattern: '%s')", col, col, pattern)
                        break
                if date_col:
                    break

        # Find TIME column - only if not using combined datetime
        if not datetime_combined:
            time_patterns = ["time", "tijd", "hour"]
            for col in columns:
                col_lower = col.lower().strip()
                for pattern in time_patterns:
                    if pattern in col_lower:
                        time_col = col
                        logger.debug("Found time column: '%s' (repr: %r, matched pattern: '%s')", col, col, pattern)
                        break
                if time_col:
                    break

        # Find activity column (prioritize vector magnitude)
        activity_col = None
        for col in columns:
            col_lower = col.lower().strip()
            if any(
                keyword in col_lower
                for keyword in [
                    ActivityColumn.VECTOR,
                    ActivityColumn.MAGNITUDE,
                    ActivityColumn.VM,
                    ActivityColumn.VECTORMAGNITUDE,
                ]
            ):
                activity_col = col
                logger.debug("Found activity column: '%s' (repr: %r, vector magnitude)", col, col)
                break

        # Fallback to other activity columns (only generic patterns, not axis-specific)
        if activity_col is None:
            for col in columns:
                col_lower = col.lower().strip()
                if any(keyword in col_lower for keyword in [ActivityColumn.ACTIVITY, ActivityColumn.COUNT]):
                    activity_col = col
                    logger.debug("Found activity column: '%s' (repr: %r, fallback)", col, col)
                    break

        # Find extra columns (only vector magnitude - axis columns must be user-specified)
        extra_cols = self._find_extra_columns(columns)

        return ColumnMapping(date_col, time_col, activity_col, datetime_combined, extra_cols)

    def _find_extra_columns(self, columns: list[str]) -> dict[str, str]:
        """
        Find axis and vector magnitude columns with common naming patterns.

        Auto-detects columns with standard naming conventions:
        - Y-Axis (vertical): axis_y, axis1, y
        - X-Axis (lateral): axis_x, axis2, x
        - Z-Axis (forward): axis_z, axis3, z
        - Vector Magnitude: vector_magnitude, vm, vector magnitude
        """
        extra_cols = {}
        for col in columns:
            col_lower = col.lower().strip()

            # Auto-detect Y-Axis (vertical) - ActiGraph Axis1
            if DatabaseColumn.AXIS_Y not in extra_cols:
                if col_lower in ("axis_y", "axis1", "y") or col_lower == "axis 1":
                    extra_cols[DatabaseColumn.AXIS_Y] = col

            # Auto-detect X-Axis (lateral) - ActiGraph Axis2
            if DatabaseColumn.AXIS_X not in extra_cols:
                if col_lower in ("axis_x", "axis2", "x") or col_lower == "axis 2":
                    extra_cols[DatabaseColumn.AXIS_X] = col

            # Auto-detect Z-Axis (forward) - ActiGraph Axis3
            if DatabaseColumn.AXIS_Z not in extra_cols:
                if col_lower in ("axis_z", "axis3", "z") or col_lower == "axis 3":
                    extra_cols[DatabaseColumn.AXIS_Z] = col

            # Auto-detect Vector Magnitude
            if DatabaseColumn.VECTOR_MAGNITUDE not in extra_cols:
                if any(keyword in col_lower for keyword in [ActivityColumn.VECTOR, ActivityColumn.MAGNITUDE, "vm", "vectormagnitude"]):
                    extra_cols[DatabaseColumn.VECTOR_MAGNITUDE] = col

        return extra_cols

    def process_timestamps(self, df: pd.DataFrame, date_col: str, time_col: str | None) -> tuple[list[str] | None, int | None]:
        """
        Process date and time columns into ISO timestamps.

        Args:
            df: DataFrame containing the data
            date_col: Column name for date (or combined datetime if time_col is None)
            time_col: Column name for time, or None if datetime is combined in date_col

        Returns:
            Tuple of (List of ISO format timestamp strings, detected epoch length in seconds)
            Returns (None, None) if processing fails

        """
        try:
            # Verify date column exists
            if date_col not in df.columns:
                logger.error("Date column '%s' not found in DataFrame. Available columns: %s", date_col, list(df.columns))
                return None, None

            # Handle combined datetime vs separate date/time columns
            if time_col is None:
                # Combined datetime in single column
                datetime_strings = df[date_col].astype(str)
                logger.debug("Using combined datetime column: %s", date_col)
            else:
                # Separate date and time columns
                if time_col not in df.columns:
                    logger.error("Time column '%s' not found in DataFrame. Available columns: %s", time_col, list(df.columns))
                    return None, None
                datetime_strings = df[date_col].astype(str) + " " + df[time_col].astype(str)

            # Debug: show sample data
            logger.debug("Sample datetime strings: %s", datetime_strings.head(3).tolist())

            # Try different datetime parsing methods
            try:
                timestamps = pd.to_datetime(datetime_strings)
            except (ValueError, TypeError, pd.errors.ParserError) as parse_error:
                logger.warning("Standard datetime parsing failed: %s", parse_error)
                # Try with different format inference
                try:
                    timestamps = pd.to_datetime(datetime_strings, infer_datetime_format=True)
                except Exception as infer_error:
                    logger.exception("Inferred datetime parsing also failed: %s", infer_error)
                    return None, None

            # Convert to ISO format strings
            iso_timestamps = [ts.isoformat() for ts in timestamps]

            # Detect epoch length from data intervals
            detected_epoch_seconds: int | None = None
            if len(iso_timestamps) > 1:
                first_interval = timestamps.iloc[1] - timestamps.iloc[0]
                detected_epoch_seconds = round(first_interval.total_seconds())
                if detected_epoch_seconds != 60:
                    logger.warning(
                        "Data epoch length is %d seconds (expected 60s). Some algorithms require 60-second epochs.",
                        detected_epoch_seconds,
                    )

            logger.debug("Successfully processed %s timestamps (epoch length: %ss)", len(iso_timestamps), detected_epoch_seconds)
            return iso_timestamps, detected_epoch_seconds

        except Exception:
            logger.exception("Failed to process timestamps")
            return None, None

    def transform_activity_data(self, df: pd.DataFrame, activity_col: str) -> list[float]:
        """
        Transform activity data from DataFrame column to list of floats.

        Args:
            df: DataFrame containing activity data
            activity_col: Name of activity column

        Returns:
            List of float values with NaN replaced by 0.0

        """
        activity_data = df[activity_col].fillna(0).astype(float)
        return activity_data.tolist()
