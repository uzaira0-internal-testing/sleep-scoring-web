"""
CSV/XLSX data source loader implementation.

This module provides loading capabilities for CSV and Excel format activity data files.
Refactored from ImportService to implement DataSourceLoader protocol for DI pattern.

Architecture:
    - Implements DataSourceLoader protocol
    - Handles CSV, XLSX, and XLS file formats
    - Detects ActiGraph CSV format automatically
    - Validates data structure and content

Example Usage:
    >>> from sleep_scoring_app.io.sources.csv_loader import CSVDataSourceLoader
    >>>
    >>> loader = CSVDataSourceLoader()
    >>> result = loader.load_file("/path/to/data.csv")
    >>> activity_df = result["activity_data"]
    >>> metadata = result["metadata"]

References:
    - ActiGraph CSV export format specification

"""

from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING, Any

import pandas as pd

from sleep_scoring_app.core.constants import ActivityColumn, DatabaseColumn
from sleep_scoring_app.core.dataclasses import ColumnMapping
from sleep_scoring_app.core.validation import InputValidator

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class CSVDataSourceLoader:
    """
    CSV/XLSX data source loader.

    Loads activity data from CSV and Excel files with automatic column detection
    and format validation. Implements DataSourceLoader protocol for DI compatibility.
    """

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xlsx", ".xls"})

    def __init__(self, skip_rows: int = 10) -> None:
        """
        Initialize CSV loader.

        Args:
            skip_rows: Number of header rows to skip (default 10 for ActiGraph)

        """
        self.skip_rows = skip_rows
        self.max_file_size = 100 * 1024 * 1024  # 100MB limit

    @property
    def name(self) -> str:
        """
        Loader name for display.

        Returns:
            Human-readable loader name

        """
        return "CSV/XLSX File Loader"

    @property
    def identifier(self) -> str:
        """
        Unique loader identifier.

        Returns:
            Snake_case identifier for configuration storage

        """
        return "csv"

    @property
    def supported_extensions(self) -> frozenset[str]:
        """
        Supported file extensions.

        Returns:
            Set of file extensions this loader can handle

        """
        return self.SUPPORTED_EXTENSIONS

    def load_file(
        self,
        file_path: str | Path,
        skip_rows: int | None = None,
        custom_columns: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Load activity data from CSV/XLSX file.

        Args:
            file_path: Path to the data file
            skip_rows: Number of header rows to skip (uses instance default if None)
            custom_columns: Optional custom column mapping

        Returns:
            Dictionary containing:
                - activity_data: pd.DataFrame with standardized columns
                - metadata: dict with file metadata
                - column_mapping: ColumnMapping object

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file format is invalid
            IOError: If file cannot be read

        """
        file_path = InputValidator.validate_file_path(
            file_path,
            must_exist=True,
            allowed_extensions=self.supported_extensions,
        )

        # Use provided skip_rows or fall back to instance default
        skip_rows = skip_rows if skip_rows is not None else self.skip_rows

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > self.max_file_size:
            msg = f"File too large: {file_size / 1024 / 1024:.1f}MB > {self.max_file_size / 1024 / 1024:.1f}MB"
            raise ValueError(msg)

        # Load CSV/Excel file
        try:
            if file_path.suffix.lower() == ".csv":
                # Use skipinitialspace to handle CSVs with spaces after commas
                df = pd.read_csv(file_path, skiprows=skip_rows, skipinitialspace=True)
            elif file_path.suffix.lower() in {".xlsx", ".xls"}:
                df = pd.read_excel(file_path, skiprows=skip_rows)
            else:
                msg = f"Unsupported file extension: {file_path.suffix}"
                raise ValueError(msg)
        except pd.errors.EmptyDataError as e:
            msg = f"Empty data file: {file_path}"
            raise ValueError(msg) from e
        except pd.errors.ParserError as e:
            msg = f"Failed to parse file: {file_path}"
            raise ValueError(msg) from e

        if df.empty:
            msg = f"No data in file: {file_path}"
            raise ValueError(msg)

        # Strip whitespace from column names (handles trailing spaces and any missed leading spaces)
        df.columns = df.columns.str.strip()

        # Detect or use custom column mapping
        if custom_columns:
            column_mapping = self._create_custom_mapping(df, custom_columns)
        else:
            column_mapping = self.detect_columns(df)

        # Validate column mapping
        is_valid, errors = self._validate_column_mapping(column_mapping)
        if not is_valid:
            msg = f"Invalid column mapping: {', '.join(errors)}"
            raise ValueError(msg)

        # Standardize columns
        standardized_df = self._standardize_columns(df, column_mapping)

        # Validate standardized data
        is_valid, errors = self.validate_data(standardized_df)
        if not is_valid:
            msg = f"Data validation failed: {', '.join(errors)}"
            raise ValueError(msg)

        # Extract metadata
        metadata = self.get_file_metadata(file_path)

        # Infer sample rate from timestamps (if sufficient data)
        sample_rate = None
        if len(standardized_df) >= 2:
            time_diff = (standardized_df[DatabaseColumn.TIMESTAMP].iloc[1] - standardized_df[DatabaseColumn.TIMESTAMP].iloc[0]).total_seconds()
            if time_diff > 0:
                sample_rate = 1.0 / time_diff

        metadata.update(
            {
                "loader": "csv",
                "total_epochs": len(standardized_df),
                "total_samples": len(standardized_df),  # Same as epochs for pre-aggregated CSV
                "start_time": standardized_df[DatabaseColumn.TIMESTAMP].iloc[0],
                "end_time": standardized_df[DatabaseColumn.TIMESTAMP].iloc[-1],
                "sample_rate": sample_rate,
                "timezone_offset": None,  # Not available from CSV, could be added to config
                "serial_number": None,
                "firmware": None,
                "autocalibrated": False,
                "calibration_error_before": None,
                "calibration_error_after": None,
                "imputation_applied": False,
                "imputation_n_gaps": 0,
                "imputation_samples_added": 0,
                "imputation_total_gap_sec": 0.0,
            },
        )

        return {
            "activity_data": standardized_df,
            "metadata": metadata,
            "column_mapping": column_mapping,
        }

    def detect_columns(self, df: pd.DataFrame) -> ColumnMapping:
        """
        Detect and map column names.

        Args:
            df: DataFrame to analyze

        Returns:
            ColumnMapping object with detected columns

        Raises:
            ValueError: If required columns cannot be detected

        """
        columns = list(df.columns)
        detected: dict[str, str | None] = {}

        # Detect combined datetime column first
        for col in columns:
            col_lower = col.lower().strip()
            if col_lower in ("datetime", "timestamp"):
                detected["datetime_column"] = col
                logger.debug("Found combined datetime column: '%s'", col)
                break

        # If no combined datetime, look for separate date/time columns
        if "datetime_column" not in detected:
            # Find date column
            date_patterns = ["date", "datum", "day"]
            for col in columns:
                col_lower = col.lower().strip()
                for pattern in date_patterns:
                    if pattern in col_lower:
                        detected["date_column"] = col
                        logger.debug("Found date column: '%s'", col)
                        break
                if "date_column" in detected:
                    break

            # Find time column
            time_patterns = ["time", "tijd", "hour"]
            for col in columns:
                col_lower = col.lower().strip()
                for pattern in time_patterns:
                    if pattern in col_lower:
                        detected["time_column"] = col
                        logger.debug("Found time column: '%s'", col)
                        break
                if "time_column" in detected:
                    break

        # Find activity column (prioritize vector magnitude)
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
                detected["activity_column"] = col
                logger.debug("Found activity column (VM): '%s'", col)
                break

        # Fallback to Y-axis for activity if no VM found
        if "activity_column" not in detected:
            for col in columns:
                col_lower = col.lower().strip()
                if col_lower in ("axis_y", "axis1", "y", "axis 1", "y-axis"):
                    detected["activity_column"] = col
                    logger.debug("Found activity column (Y-axis): '%s'", col)
                    break

        # Detect axis columns
        for col in columns:
            col_lower = col.lower().strip()

            # X-Axis (lateral) - ActiGraph Axis2
            if col_lower in ("axis_x", "axis2", "x", "axis 2", "x-axis"):
                detected["axis_x_column"] = col

            # Z-Axis (forward) - ActiGraph Axis3
            if col_lower in ("axis_z", "axis3", "z", "axis 3", "z-axis"):
                detected["axis_z_column"] = col

            # Vector Magnitude
            if any(keyword in col_lower for keyword in [ActivityColumn.VECTOR, ActivityColumn.MAGNITUDE, "vm", "vectormagnitude"]):
                detected["vector_magnitude_column"] = col

        return ColumnMapping(**detected)

    def _create_custom_mapping(self, df: pd.DataFrame, custom_columns: dict[str, str]) -> ColumnMapping:
        """
        Create column mapping from custom column specification.

        Args:
            df: DataFrame to validate against
            custom_columns: Custom column names

        Returns:
            ColumnMapping object

        """
        columns = list(df.columns)
        fields: dict[str, str] = {}

        # Handle datetime columns
        if custom_columns.get("datetime_combined"):
            date_col = custom_columns.get("date")
            if date_col and date_col in columns:
                fields["datetime_column"] = date_col
        else:
            date_col = custom_columns.get("date")
            time_col = custom_columns.get("time")
            if date_col and date_col in columns:
                fields["date_column"] = date_col
            if time_col and time_col in columns:
                fields["time_column"] = time_col

        # Handle activity column
        activity_col = custom_columns.get("activity")
        if activity_col and activity_col in columns:
            fields["activity_column"] = activity_col

        # Handle axis columns
        axis_y = custom_columns.get("axis_y")
        if axis_y and axis_y in columns:
            # If activity column not set, use axis_y as activity
            if "activity_column" not in fields:
                fields["activity_column"] = axis_y

        axis_x = custom_columns.get("axis_x")
        if axis_x and axis_x in columns:
            fields["axis_x_column"] = axis_x

        axis_z = custom_columns.get("axis_z")
        if axis_z and axis_z in columns:
            fields["axis_z_column"] = axis_z

        vm = custom_columns.get("vector_magnitude")
        if vm and vm in columns:
            fields["vector_magnitude_column"] = vm

        return ColumnMapping(**fields)

    def _validate_column_mapping(self, mapping: ColumnMapping) -> tuple[bool, list[str]]:
        """
        Validate that required columns are present in mapping.

        Args:
            mapping: ColumnMapping to validate

        Returns:
            Tuple of (is_valid, error_messages)

        """
        errors = []

        # Need either datetime_column or date_column
        if not mapping.datetime_column and not mapping.date_column:
            errors.append("Missing timestamp column (need datetime or date column)")

        # Need activity column
        if not mapping.activity_column:
            errors.append("Missing activity column")

        return len(errors) == 0, errors

    def _standardize_columns(self, df: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
        """
        Standardize column names to database schema.

        Creates a new DataFrame with standardized column names:
        - TIMESTAMP (datetime)
        - AXIS_Y (primary activity - vertical)
        - AXIS_X (lateral, optional)
        - AXIS_Z (forward, optional)
        - VECTOR_MAGNITUDE (calculated or mapped, optional)

        Args:
            df: Original DataFrame
            mapping: Column mapping

        Returns:
            DataFrame with standardized columns

        """
        result = pd.DataFrame()

        # Process timestamp
        if mapping.datetime_column:
            result[DatabaseColumn.TIMESTAMP] = pd.to_datetime(df[mapping.datetime_column])
        elif mapping.date_column:
            if mapping.time_column:
                datetime_str = df[mapping.date_column].astype(str) + " " + df[mapping.time_column].astype(str)
            else:
                datetime_str = df[mapping.date_column].astype(str)
            result[DatabaseColumn.TIMESTAMP] = pd.to_datetime(datetime_str)

        # Map activity column to AXIS_Y (primary activity for sleep scoring)
        if mapping.activity_column:
            result[DatabaseColumn.AXIS_Y] = df[mapping.activity_column].fillna(0).astype(float)

        # Map additional axis columns
        if mapping.axis_x_column:
            result[DatabaseColumn.AXIS_X] = df[mapping.axis_x_column].fillna(0).astype(float)

        if mapping.axis_z_column:
            result[DatabaseColumn.AXIS_Z] = df[mapping.axis_z_column].fillna(0).astype(float)

        # Handle vector magnitude
        if mapping.vector_magnitude_column:
            result[DatabaseColumn.VECTOR_MAGNITUDE] = df[mapping.vector_magnitude_column].fillna(0).astype(float)
        elif DatabaseColumn.AXIS_X in result and DatabaseColumn.AXIS_Y in result and DatabaseColumn.AXIS_Z in result:
            # Calculate vector magnitude from X, Y, Z
            result[DatabaseColumn.VECTOR_MAGNITUDE] = result.apply(
                lambda row: math.sqrt(row[DatabaseColumn.AXIS_X] ** 2 + row[DatabaseColumn.AXIS_Y] ** 2 + row[DatabaseColumn.AXIS_Z] ** 2),
                axis=1,
            )

        return result

    def validate_data(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        """
        Validate data structure and content.

        Args:
            df: DataFrame to validate

        Returns:
            Tuple of (is_valid, error_messages)

        Raises:
            ValueError: If validation fails with specific error details

        """
        errors = []

        # Check required columns exist
        if DatabaseColumn.TIMESTAMP not in df.columns:
            errors.append(f"Missing required column: {DatabaseColumn.TIMESTAMP}")

        if DatabaseColumn.AXIS_Y not in df.columns:
            errors.append(f"Missing required column: {DatabaseColumn.AXIS_Y}")

        # Validate data types
        if DatabaseColumn.TIMESTAMP in df.columns:
            try:
                if not pd.api.types.is_datetime64_any_dtype(df[DatabaseColumn.TIMESTAMP]):
                    errors.append(f"{DatabaseColumn.TIMESTAMP} must be datetime type")
            except Exception as e:
                errors.append(f"Error checking {DatabaseColumn.TIMESTAMP} type: {e}")

        if DatabaseColumn.AXIS_Y in df.columns:
            try:
                if not pd.api.types.is_numeric_dtype(df[DatabaseColumn.AXIS_Y]):
                    errors.append(f"{DatabaseColumn.AXIS_Y} must be numeric type")
            except Exception as e:
                errors.append(f"Error checking {DatabaseColumn.AXIS_Y} type: {e}")

        # Check for empty data
        if len(df) == 0:
            errors.append("DataFrame is empty")

        return len(errors) == 0, errors

    def get_file_metadata(self, file_path: str | Path) -> dict[str, Any]:
        """
        Extract file metadata.

        Args:
            file_path: Path to the data file

        Returns:
            Metadata dictionary containing:
                - file_size: File size in bytes
                - device_type: Device type (if detectable)
                - epoch_length_seconds: Estimated epoch length

        Raises:
            FileNotFoundError: If file does not exist

        """
        file_path = InputValidator.validate_file_path(
            file_path,
            must_exist=True,
            allowed_extensions=self.supported_extensions,
        )

        return {
            "loader": "csv",
            "file_size": file_path.stat().st_size,
            "device_type": "actigraph",  # Assume ActiGraph for CSV files
            "epoch_length_seconds": 60,  # Standard 60-second epochs
            "sample_rate": None,  # Will be inferred from data if available
            "timezone_offset": None,
        }
