"""
CSV data loader service.

Ported from desktop app's io/sources/csv_loader.py for web use.
Loads activity data from CSV and Excel files with automatic column detection.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# GENEActiv CSV export columns.  Data starts at line 101 (no header row).
# Two formats exist depending on GeneaLibrary export settings:
#
# RAW (7 columns): timestamp, x(g), y(g), z(g), lux, button, temperature
#
# EPOCH COMPRESSED (12 columns): timestamp_end, mean_x, mean_y, mean_z,
#   mean_lux, sum_button, mean_temp, SVMgs, sd_x, sd_y, sd_z, peak_lux
#
# SVMgs = Σ|√(x²+y²+z²) - 1g|  (gravity-subtracted sum of vector magnitudes)
#
# We detect which format by column count and name accordingly.

GENEACTIV_RAW_COLUMNS = [
    "timestamp",  # A: datetime (may have colon-milliseconds)
    "x",  # B: accelerometer x-axis (g)
    "y",  # C: accelerometer y-axis (g)
    "z",  # D: accelerometer z-axis (g)
    "lux",  # E: light level (lux)
    "button",  # F: button press (0 or 1)
    "temperature",  # G: temperature (°C)
]

GENEACTIV_EPOCH_COLUMNS = [
    "timestamp",  # A: timestamp of epoch end
    "x",  # B: mean x-axis (g)
    "y",  # C: mean y-axis (g)
    "z",  # D: mean z-axis (g)
    "lux",  # E: mean lux
    "button",  # F: sum of button press time
    "temperature",  # G: mean temperature (°C)
    "svm",  # H: SVMgs — gravity-subtracted sum of vector magnitudes
    "sd_x",  # I: x-axis standard deviation
    "sd_y",  # J: y-axis standard deviation
    "sd_z",  # K: z-axis standard deviation
    "peak_lux",  # L: peak lux
]


@dataclass
class ColumnMapping:
    """CSV column mapping configuration."""

    date_column: str | None = None
    time_column: str | None = None
    datetime_column: str | None = None
    activity_column: str | None = None
    axis_x_column: str | None = None
    axis_z_column: str | None = None
    vector_magnitude_column: str | None = None


class CSVLoaderService:
    """
    CSV/XLSX data source loader.

    Loads activity data from CSV and Excel files with automatic column detection
    and format validation.
    """

    SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".csv", ".xlsx", ".xls"})

    def __init__(self, skip_rows: int = 10, device_preset: str | None = None) -> None:
        """
        Initialize CSV loader.

        Args:
            skip_rows: Number of header rows to skip (default 10 for ActiGraph)
            device_preset: Device preset hint (e.g. "geneactiv", "actigraph")

        """
        self.skip_rows = skip_rows
        self.device_preset = device_preset
        self.max_file_size = 5 * 1024 * 1024 * 1024  # 5GB limit (large raw GENEActiv files)

    @staticmethod
    def detect_geneactiv(file_path: Path) -> bool:
        """Check if file is a GENEActiv export by reading the first line."""
        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                first_line = f.readline().strip()
                # Real GENEActiv .bin exports start with "Device Type<sep>GENEActiv"
                return "geneactiv" in first_line.lower() and "device" in first_line.lower()
        except Exception:
            return False

    @staticmethod
    def _find_geneactiv_data_start(file_path: Path) -> tuple[int, bool]:
        """Find where data starts in a GENEActiv file.

        Returns:
            (data_start_line, has_header_row): line index where data begins,
            and whether there's a column header row immediately before it.
        """
        # Timestamp pattern: YYYY-MM-DD HH:MM:SS (with optional :MMM or .MMM)
        ts_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}")

        with open(file_path, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                stripped = line.strip()
                if not stripped:
                    continue
                # Check if this line looks like data (starts with a timestamp)
                if ts_pattern.match(stripped):
                    # Check the line before this — is it a header row?
                    # A header row would contain column name strings like "timestamp", "x", "y"
                    # If previous non-empty line has alpha words, it's a header
                    has_header = False
                    if i > 0:
                        # Re-read to check previous line
                        with open(file_path, encoding="utf-8", errors="ignore") as f2:
                            prev_line = ""
                            for j, check_line in enumerate(f2):
                                if j == i - 1:
                                    prev_line = check_line.strip().lower()
                                    break
                            if prev_line and any(kw in prev_line for kw in ("timestamp", "x", "y", "z", "time", "lux", "temp")):
                                has_header = True
                    return (i, has_header)

                if i > 120:
                    break
        return (100, False)  # Default fallback

    def _load_geneactiv_csv(self, file_path: Path) -> pd.DataFrame:
        """Load a GENEActiv CSV/bin-export file, handling the headerless format."""
        data_start, has_header = self._find_geneactiv_data_start(file_path)

        # Detect delimiter from the data region
        with open(file_path, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i == data_start:
                    sep = "\t" if "\t" in line else ","
                    num_cols = len(line.strip().split(sep))
                    break
            else:
                sep = ","
                num_cols = 7

        if has_header:
            # File has a column header row right before data — let pandas use it
            df = pd.read_csv(file_path, skiprows=data_start - 1, sep=sep, skipinitialspace=True)
        else:
            # No header row — assign column names based on column count.
            # 7 columns = raw data, 12 columns = epoch compressed.
            if num_cols <= len(GENEACTIV_RAW_COLUMNS):
                col_names = GENEACTIV_RAW_COLUMNS[:num_cols]
            elif num_cols <= len(GENEACTIV_EPOCH_COLUMNS):
                col_names = GENEACTIV_EPOCH_COLUMNS[:num_cols]
            else:
                col_names = GENEACTIV_EPOCH_COLUMNS + [
                    f"extra_{i}" for i in range(len(GENEACTIV_EPOCH_COLUMNS), num_cols)
                ]
            df = pd.read_csv(
                file_path,
                skiprows=data_start,
                sep=sep,
                header=None,
                names=col_names,
                skipinitialspace=True,
            )

        # Fix GENEActiv colon-millisecond timestamps: "2025-06-12 13:20:18:000" → "2025-06-12 13:20:18.000"
        ts_col = None
        for candidate in ("timestamp", df.columns[0]):
            if candidate in df.columns:
                ts_col = candidate
                break
        if ts_col is not None and df[ts_col].dtype == object:
            # Replace the LAST colon followed by 3 digits (milliseconds) with a period
            df[ts_col] = df[ts_col].str.replace(
                r":(\d{3})$", r".\1", regex=True
            )

        logger.info(
            "GENEActiv loader: data_start=%d, has_header=%s, sep=%r, cols=%d, rows=%d",
            data_start, has_header, sep, num_cols, len(df),
        )
        return df

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
            skip_rows: Number of header rows to skip
            custom_columns: Optional custom column mapping

        Returns:
            Dictionary containing:
                - activity_data: pd.DataFrame with standardized columns
                - metadata: dict with file metadata
                - column_mapping: ColumnMapping object

        Raises:
            FileNotFoundError: If file does not exist
            ValueError: If file format is invalid

        """
        file_path = Path(file_path)

        if not file_path.exists():
            msg = f"File not found: {file_path}"
            raise FileNotFoundError(msg)

        suffix = file_path.suffix.lower()
        if suffix not in self.SUPPORTED_EXTENSIONS:
            msg = f"Unsupported file extension: {suffix}"
            raise ValueError(msg)

        skip_rows = skip_rows if skip_rows is not None else self.skip_rows

        # Check file size
        file_size = file_path.stat().st_size
        if file_size > self.max_file_size:
            msg = f"File too large: {file_size / 1024 / 1024:.1f}MB > {self.max_file_size / 1024 / 1024:.1f}MB"
            raise ValueError(msg)

        # Detect GENEActiv format (by preset hint or auto-detection)
        is_geneactiv = self.device_preset == "geneactiv" or (
            suffix == ".csv" and self.detect_geneactiv(file_path)
        )

        # Load CSV/Excel file
        try:
            if is_geneactiv and suffix == ".csv":
                df = self._load_geneactiv_csv(file_path)
            elif suffix == ".csv":
                df = pd.read_csv(file_path, skiprows=skip_rows, skipinitialspace=True)
            else:
                df = pd.read_excel(file_path, skiprows=skip_rows)
        except pd.errors.EmptyDataError as e:
            msg = f"Empty data file: {file_path}"
            raise ValueError(msg) from e
        except pd.errors.ParserError as e:
            msg = f"Failed to parse file: {file_path}"
            raise ValueError(msg) from e

        if df.empty:
            msg = f"No data in file: {file_path}"
            raise ValueError(msg)

        # Strip whitespace from column names
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

        # Infer sample rate from timestamps
        sample_rate = None
        if len(standardized_df) >= 2:
            time_diff = (standardized_df["timestamp"].iloc[1] - standardized_df["timestamp"].iloc[0]).total_seconds()
            if time_diff > 0:
                sample_rate = 1.0 / time_diff

        metadata.update(
            {
                "loader": "csv",
                "total_epochs": len(standardized_df),
                "start_time": standardized_df["timestamp"].iloc[0],
                "end_time": standardized_df["timestamp"].iloc[-1],
                "sample_rate": sample_rate,
            }
        )

        return {
            "activity_data": standardized_df,
            "metadata": metadata,
            "column_mapping": column_mapping,
        }

    def detect_columns(self, df: pd.DataFrame) -> ColumnMapping:
        """Detect and map column names automatically."""
        columns = list(df.columns)
        detected: dict[str, str | None] = {}

        # Detect combined datetime column first
        for col in columns:
            col_lower = col.lower().strip()
            if col_lower in ("datetime", "timestamp"):
                detected["datetime_column"] = col
                break

        # If no combined datetime, look for separate date/time columns
        if "datetime_column" not in detected:
            for col in columns:
                col_lower = col.lower().strip()
                if "date" in col_lower and "date_column" not in detected:
                    detected["date_column"] = col
                if "time" in col_lower and "time_column" not in detected:
                    detected["time_column"] = col

        # Find Y-axis (activity) column first - this is the primary activity measure for Sadeh
        for col in columns:
            col_lower = col.lower().strip()
            if col_lower in ("axis_y", "axis1", "y", "axis 1", "y-axis"):
                detected["activity_column"] = col
                break

        # Detect other axis columns
        for col in columns:
            col_lower = col.lower().strip()
            if col_lower in ("axis_x", "axis2", "x", "axis 2"):
                detected["axis_x_column"] = col
            if col_lower in ("axis_z", "axis3", "z", "axis 3"):
                detected["axis_z_column"] = col

        # Find vector magnitude column (separate from activity column)
        for col in columns:
            col_lower = col.lower().strip()
            if any(kw in col_lower for kw in ["vector", "magnitude", "vm", "svm"]):
                detected["vector_magnitude_column"] = col
                # If no Y-axis found, use vector magnitude as fallback activity
                if "activity_column" not in detected:
                    detected["activity_column"] = col
                break

        return ColumnMapping(**detected)

    def _create_custom_mapping(self, df: pd.DataFrame, custom_columns: dict[str, str]) -> ColumnMapping:
        """Create column mapping from custom specification."""
        columns = list(df.columns)
        fields: dict[str, str] = {}

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

        activity_col = custom_columns.get("activity")
        if activity_col and activity_col in columns:
            fields["activity_column"] = activity_col

        axis_y = custom_columns.get("axis_y")
        if axis_y and axis_y in columns and "activity_column" not in fields:
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
        """Validate that required columns are present."""
        errors = []

        if not mapping.datetime_column and not mapping.date_column:
            errors.append("Missing timestamp column")

        if not mapping.activity_column:
            errors.append("Missing activity column")

        return len(errors) == 0, errors

    def _standardize_columns(self, df: pd.DataFrame, mapping: ColumnMapping) -> pd.DataFrame:
        """Standardize column names to database schema."""
        result = pd.DataFrame()

        # Process timestamp
        if mapping.datetime_column:
            result["timestamp"] = pd.to_datetime(df[mapping.datetime_column])
        elif mapping.date_column:
            if mapping.time_column:
                datetime_str = df[mapping.date_column].astype(str) + " " + df[mapping.time_column].astype(str)
            else:
                datetime_str = df[mapping.date_column].astype(str)
            result["timestamp"] = pd.to_datetime(datetime_str)

        # Map activity column to axis_y
        if mapping.activity_column:
            result["axis_y"] = df[mapping.activity_column].fillna(0).astype(float)

        # Map additional axis columns
        if mapping.axis_x_column:
            result["axis_x"] = df[mapping.axis_x_column].fillna(0).astype(float)

        if mapping.axis_z_column:
            result["axis_z"] = df[mapping.axis_z_column].fillna(0).astype(float)

        # Handle vector magnitude
        if mapping.vector_magnitude_column:
            result["vector_magnitude"] = df[mapping.vector_magnitude_column].fillna(0).astype(float)
        elif "axis_x" in result and "axis_y" in result and "axis_z" in result:
            result["vector_magnitude"] = result.apply(
                lambda row: math.sqrt(row["axis_x"] ** 2 + row["axis_y"] ** 2 + row["axis_z"] ** 2),
                axis=1,
            )

        return result

    def validate_data(self, df: pd.DataFrame) -> tuple[bool, list[str]]:
        """Validate data structure and content."""
        errors = []

        if "timestamp" not in df.columns:
            errors.append("Missing timestamp column")

        if "axis_y" not in df.columns:
            errors.append("Missing axis_y column")

        if len(df) == 0:
            errors.append("DataFrame is empty")

        return len(errors) == 0, errors

    def get_file_metadata(self, file_path: str | Path) -> dict[str, Any]:
        """Extract file metadata."""
        file_path = Path(file_path)
        device_type = self.device_preset or "actigraph"
        return {
            "file_size": file_path.stat().st_size,
            "device_type": device_type,
            "epoch_length_seconds": 60,
        }
