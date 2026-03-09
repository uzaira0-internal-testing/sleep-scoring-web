#!/usr/bin/env python3
"""
Import Service for Sleep Scoring Application
Handles bulk CSV import functionality with progress tracking and file change detection.
"""

from __future__ import annotations

import hashlib
import logging
import math
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

import pandas as pd

from sleep_scoring_app.core.constants import DatabaseColumn, DatabaseTable, ImportStatus
from sleep_scoring_app.core.exceptions import (
    DatabaseError,
    ErrorCodes,
    SleepScoringImportError,
    ValidationError,
)
from sleep_scoring_app.core.validation import InputValidator
from sleep_scoring_app.data.database import DatabaseManager
from sleep_scoring_app.services.csv_data_transformer import CSVDataTransformer
from sleep_scoring_app.services.file_format_detector import FileFormatDetector
from sleep_scoring_app.services.import_progress_tracker import ImportProgress
from sleep_scoring_app.services.nonwear_service import NonwearDataService

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from sleep_scoring_app.core.dataclasses import ParticipantInfo

# Configure logging
logger = logging.getLogger(__name__)


class ImportService:
    """
    Service for importing CSV files into database with progress tracking.

    NOTE: This is a headless service. For Qt signal-based progress tracking,
    wrap this service with a Qt adapter in the ui/ layer or use the
    progress_callback parameter in import methods.
    """

    def __init__(self, database_manager: DatabaseManager | None = None) -> None:
        self.db_manager = database_manager or DatabaseManager()
        self.nonwear_service = NonwearDataService(self.db_manager)
        self.batch_size = 1000  # Records per batch for large files
        self.max_file_size = 100 * 1024 * 1024  # 100MB limit

        # Initialize delegate services
        self.file_format_detector = FileFormatDetector()
        self.csv_transformer = CSVDataTransformer(max_file_size=self.max_file_size)

    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file for change detection."""
        try:
            hash_sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            msg = f"Failed to calculate hash for {file_path}: {e}"
            raise SleepScoringImportError(
                msg,
                ErrorCodes.FILE_CORRUPTED,
            ) from e

    def extract_participant_info(self, file_path: Path) -> ParticipantInfo:
        """Extract participant information using centralized extractor - fail fast if configuration incomplete."""
        from sleep_scoring_app.utils.participant_extractor import extract_participant_info

        try:
            return extract_participant_info(file_path)  # type: ignore[arg-type]
        except Exception as e:
            # Convert extraction errors to import errors for proper error handling
            msg = f"Failed to extract participant information from {file_path.name}: {e}"
            raise SleepScoringImportError(
                msg,
                ErrorCodes.CONFIG_INVALID,
            ) from e

    def check_file_needs_import(self, file_path: Path) -> tuple[bool, str | None]:
        """Check if file needs to be imported based on PARTICIPANT_KEY and hash comparison."""
        try:
            # Extract participant info to get PARTICIPANT_KEY
            participant_info = self.extract_participant_info(file_path)
            participant_key = participant_info.participant_key
            current_hash = self.calculate_file_hash(file_path)

            # Check if file exists in registry using PARTICIPANT_KEY via repository
            exists, stored_hash, status, existing_filename = self.db_manager.file_registry.check_file_exists_by_participant_key(participant_key)

            if not exists:
                return True, "New participant data"

            # If it's a different file for same participant, check if it's newer
            if existing_filename != file_path.name:
                logger.info("Found different file for participant %s: %s vs %s", participant_key, existing_filename, file_path.name)
                return True, "Different file for participant"

            if stored_hash != current_hash:
                return True, "File changed"

            from sleep_scoring_app.core.constants import ImportStatus

            if status == ImportStatus.ERROR:
                return True, "Previous import failed"

            return False, "Already imported"

        except (DatabaseError, OSError, ValidationError, Exception) as e:
            logger.warning("Error checking import status for %s: %s", file_path, e)
            return True, "Import check failed"

    def import_csv_file(
        self,
        file_path: Path,
        progress: ImportProgress | None = None,
        skip_rows: int = 10,
        force_reimport: bool = False,
        custom_columns: dict[str, str] | None = None,
    ) -> bool:
        """Import a single CSV file into the database."""
        try:
            # Validate file
            validated_path = InputValidator.validate_file_path(file_path, must_exist=True, allowed_extensions={".csv"})

            filename = validated_path.name

            # Check if import is needed
            if not force_reimport:
                needs_import, reason = self.check_file_needs_import(validated_path)
                if not needs_import:
                    if progress:
                        progress.skipped_files.append(f"{filename}: {reason}")
                    logger.info("Skipping %s: %s", filename, reason)
                    return True

            # Check file size
            file_size = validated_path.stat().st_size
            if file_size > self.max_file_size:
                size_mb = file_size / 1024 / 1024
                limit_mb = self.max_file_size / 1024 / 1024
                error_msg = (
                    f"File {filename} exceeds size limit: {size_mb:.1f}MB > {limit_mb:.1f}MB. Please split the file or increase the size limit."
                )
                logger.error(error_msg)
                if progress:
                    progress.add_error(error_msg)
                return False

            if progress:
                progress.current_file = filename

            # Extract participant info
            participant_info = self.extract_participant_info(validated_path)

            # Calculate file hash
            file_hash = self.calculate_file_hash(validated_path)

            # Load and validate CSV using transformer
            df = self.csv_transformer.load_csv(validated_path, skip_rows)
            if df is None or df.empty:
                error_msg = f"File {filename} is empty or contains no valid data rows. Please check that the file has data after row {skip_rows}."
                logger.error(error_msg)
                if progress:
                    progress.add_error(error_msg)
                return False

            # Find required columns using transformer
            column_mapping = self.csv_transformer.identify_columns(df, custom_columns)
            if not column_mapping.is_valid:
                # Build detailed error message about missing columns
                missing_cols = []
                if not column_mapping.date_col:
                    missing_cols.append("date/datetime column")
                if not column_mapping.activity_col:
                    missing_cols.append("activity count column")

                available_cols = ", ".join(list(df.columns)[:10])  # Show first 10 columns
                if len(df.columns) > 10:
                    available_cols += f"... ({len(df.columns)} total)"

                error_msg = (
                    f"File {filename}: Required columns not found. "
                    f"Missing: {', '.join(missing_cols)}. "
                    f"Available columns: {available_cols}. "
                    f"Please check column mappings in Study Settings or use 'Generic CSV' preset to configure custom columns."
                )
                logger.error("Column identification failed for %s:", filename)
                logger.error("  Available columns: %s", list(df.columns))
                logger.error("  Found date_col: %s", column_mapping.date_col)
                logger.error("  Found time_col: %s", column_mapping.time_col)
                logger.error("  Found activity_col: %s", column_mapping.activity_col)
                if progress:
                    progress.add_error(error_msg)
                return False

            # Type guard: ensure required columns are not None after validation
            # Note: time_col can be None if datetime is combined in date_col
            assert column_mapping.date_col is not None
            assert column_mapping.activity_col is not None

            # Process timestamps using transformer
            timestamps, detected_epoch_seconds = self.csv_transformer.process_timestamps(df, column_mapping.date_col, column_mapping.time_col)
            if timestamps is None:
                error_msg = (
                    f"File {filename}: Failed to parse timestamps. "
                    f"Date column '{column_mapping.date_col}' "
                    f"{'and time column ' + repr(column_mapping.time_col) if column_mapping.time_col else ''} "
                    f"may have invalid date/time format. "
                    f"Please check that dates are in a standard format (e.g., YYYY-MM-DD, MM/DD/YYYY)."
                )
                logger.error(error_msg)
                if progress:
                    progress.add_error(error_msg)
                return False

            # Warn if epoch length is not 60 seconds (standard for sleep scoring algorithms)
            if detected_epoch_seconds is not None and detected_epoch_seconds != 60:
                warning_msg = (
                    f"File {filename}: Detected {detected_epoch_seconds}-second epochs. "
                    f"Sleep scoring algorithms (Sadeh, Cole-Kripke) require 60-second epochs for accurate results."
                )
                logger.warning(warning_msg)
                if progress:
                    progress.add_warning(warning_msg)

            # Import data using transaction
            success = self._import_data_transaction(
                filename,
                participant_info,
                file_hash,
                validated_path,
                df,
                timestamps,
                column_mapping.activity_col,
                column_mapping.extra_cols,
                progress,
            )

            if success:
                if progress:
                    progress.imported_files.append(filename)
                    progress.processed_files += 1
                logger.info("Successfully imported %s", filename)

            return success

        except Exception as e:
            error_msg = f"Failed to import {file_path}: {e}"
            if progress:
                progress.add_error(error_msg)
            logger.exception(error_msg)
            return False

    def _import_data_transaction(
        self,
        filename: str,
        participant_info: ParticipantInfo,
        file_hash: str,
        file_path: Path,
        df: pd.DataFrame,
        timestamps: list[str],
        activity_col: str,
        extra_cols: dict[str, str],
        progress: ImportProgress | None,
    ) -> bool:
        """Import data within a database transaction."""
        from sleep_scoring_app.data.repositories.base_repository import BaseRepository

        temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
        try:
            with temp_repo._get_connection() as conn:
                # Begin transaction
                conn.execute("BEGIN TRANSACTION")

                try:
                    # Register file first
                    # Extract just the date portion (YYYY-MM-DD) from timestamps for date_range fields
                    date_start = timestamps[0].split("T")[0] if timestamps else None
                    date_end = timestamps[-1].split("T")[0] if timestamps else None
                    self._register_file(
                        conn,
                        filename,
                        participant_info,
                        file_hash,
                        file_path,
                        len(df),
                        date_start,
                        date_end,
                    )

                    # Delete existing data if reimporting
                    conn.execute(
                        f"DELETE FROM {DatabaseTable.RAW_ACTIVITY_DATA} WHERE {DatabaseColumn.FILENAME} = ?",
                        (filename,),
                    )

                    # Import activity data in batches
                    success = self._import_activity_data_batched(
                        conn,
                        filename,
                        participant_info,  # Pass full participant info for composite key
                        file_hash,
                        df,
                        timestamps,
                        activity_col,
                        extra_cols,
                        progress,
                    )

                    if success:
                        # Update file status
                        conn.execute(
                            f"""
                            UPDATE {DatabaseTable.FILE_REGISTRY}
                            SET {DatabaseColumn.STATUS} = ?, {DatabaseColumn.IMPORT_DATE} = ?
                            WHERE {DatabaseColumn.FILENAME} = ?
                            """,
                            (
                                ImportStatus.IMPORTED,
                                datetime.now().isoformat(),
                                filename,
                            ),
                        )
                        conn.commit()
                        return True

                    # IMP-01 FIX: Update status to FAILED before rollback
                    # This ensures status is correct even if rollback fails
                    conn.rollback()
                    self._mark_file_as_failed(filename)
                    return False

                except Exception as e:
                    conn.rollback()
                    # IMP-01 FIX: Mark file as failed after rollback
                    self._mark_file_as_failed(filename)
                    error_msg = f"Database transaction failed for {filename}: {e}"
                    logger.exception(error_msg)
                    if progress:
                        progress.add_error(error_msg)
                    return False

        except Exception as e:
            # IMP-01 FIX: Mark file as failed even on connection error
            self._mark_file_as_failed(filename)
            error_msg = f"Database connection failed for {filename}: {e}"
            logger.exception(error_msg)
            if progress:
                progress.add_error(error_msg)
            return False

    def _mark_file_as_failed(self, filename: str) -> None:
        """
        Mark a file as FAILED in the registry after import failure.

        IMP-01 FIX: This ensures files don't get stuck in IMPORTING status
        even if rollback fails or connection is lost.
        """
        from sleep_scoring_app.data.repositories.base_repository import BaseRepository

        temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
        try:
            with temp_repo._get_connection() as conn:
                conn.execute(
                    f"""
                    UPDATE {DatabaseTable.FILE_REGISTRY}
                    SET {DatabaseColumn.STATUS} = ?
                    WHERE {DatabaseColumn.FILENAME} = ? AND {DatabaseColumn.STATUS} = ?
                    """,
                    (ImportStatus.FAILED, filename, ImportStatus.IMPORTING),
                )
                conn.commit()
                logger.info("Marked file '%s' as FAILED after import error", filename)
        except Exception as e:
            logger.warning("Could not update file status to FAILED for '%s': %s", filename, e)

    def _register_file(
        self,
        conn: Any,
        filename: str,
        participant_info: ParticipantInfo,
        file_hash: str,
        file_path: Path,
        total_records: int,
        date_start: str | None,
        date_end: str | None,
    ) -> None:
        """Register file in file registry."""
        file_stat = file_path.stat()

        conn.execute(
            f"""
            INSERT OR REPLACE INTO {DatabaseTable.FILE_REGISTRY} (
                {DatabaseColumn.FILENAME}, {DatabaseColumn.ORIGINAL_PATH},
                {DatabaseColumn.PARTICIPANT_KEY}, {DatabaseColumn.PARTICIPANT_ID},
                {DatabaseColumn.PARTICIPANT_GROUP}, {DatabaseColumn.PARTICIPANT_TIMEPOINT},
                {DatabaseColumn.FILE_SIZE}, {DatabaseColumn.FILE_HASH},
                {DatabaseColumn.DATE_RANGE_START}, {DatabaseColumn.DATE_RANGE_END},
                {DatabaseColumn.TOTAL_RECORDS}, {DatabaseColumn.LAST_MODIFIED},
                {DatabaseColumn.STATUS}
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                filename,
                str(file_path),
                participant_info.participant_key,  # Add composite key
                participant_info.numerical_id,
                participant_info.group_str,
                participant_info.timepoint_str,
                file_stat.st_size,
                file_hash,
                date_start,
                date_end,
                total_records,
                datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                ImportStatus.IMPORTING,
            ),
        )

    def _import_activity_data_batched(
        self,
        conn: Any,
        filename: str,
        participant_info: ParticipantInfo,
        file_hash: str,
        df: pd.DataFrame,
        timestamps: list[str],
        activity_col: str,
        extra_cols: dict[str, str],
        progress: ImportProgress | None,
    ) -> bool:
        """
        Import activity data in batches for memory efficiency.

        PERFORMANCE: Uses vectorized numpy arrays instead of row-by-row .iloc access.
        This provides ~100x speedup for large actigraphy files (600k+ rows).
        """
        import numpy as np

        try:
            total_rows = len(df)
            if total_rows == 0:
                return True

            # PERFORMANCE: Pre-extract columns as numpy arrays (vectorized, fast)
            # This avoids slow .iloc[i] access in the loop
            if DatabaseColumn.AXIS_Y in extra_cols and extra_cols[DatabaseColumn.AXIS_Y] in df.columns:
                axis_y_arr = np.asarray(df[extra_cols[DatabaseColumn.AXIS_Y]].fillna(0.0).astype(float))
            else:
                axis_y_arr = np.asarray(df[activity_col].fillna(0.0).astype(float))

            # Extract optional axis columns as numpy arrays (None if not available)
            axis_x_arr = None
            if DatabaseColumn.AXIS_X in extra_cols and extra_cols[DatabaseColumn.AXIS_X] in df.columns:
                axis_x_arr = np.asarray(df[extra_cols[DatabaseColumn.AXIS_X]])  # Keep NaN for None detection

            axis_z_arr = None
            if DatabaseColumn.AXIS_Z in extra_cols and extra_cols[DatabaseColumn.AXIS_Z] in df.columns:
                axis_z_arr = np.asarray(df[extra_cols[DatabaseColumn.AXIS_Z]])

            vm_arr = None
            if DatabaseColumn.VECTOR_MAGNITUDE in extra_cols and extra_cols[DatabaseColumn.VECTOR_MAGNITUDE] in df.columns:
                vm_arr = np.asarray(df[extra_cols[DatabaseColumn.VECTOR_MAGNITUDE]])

            # Check if we need to calculate VM from axes (do once, not per-row)
            need_vm_calculation = vm_arr is None and axis_x_arr is not None and axis_z_arr is not None
            if need_vm_calculation and progress:
                progress.add_warning(f"File {filename}: Vector Magnitude column missing, calculating from axis values (X, Y, Z)")

            # Static values for all rows
            static_values = (
                file_hash,
                filename,
                participant_info.participant_key,
                participant_info.numerical_id,
                participant_info.group_str,
                participant_info.timepoint_str,
            )

            # Process in batches
            for start_idx in range(0, total_rows, self.batch_size):
                end_idx = min(start_idx + self.batch_size, total_rows, len(timestamps))
                batch_size_actual = end_idx - start_idx

                if batch_size_actual <= 0:
                    break

                # Build batch data using list comprehension (much faster than append loop)
                batch_data = []
                for i in range(start_idx, end_idx):
                    axis_y = float(axis_y_arr[i])
                    axis_x = None if axis_x_arr is None or np.isnan(axis_x_arr[i]) else float(axis_x_arr[i])
                    axis_z = None if axis_z_arr is None or np.isnan(axis_z_arr[i]) else float(axis_z_arr[i])

                    # Get or calculate vector magnitude
                    if vm_arr is not None and not np.isnan(vm_arr[i]):
                        vm = float(vm_arr[i])
                    elif axis_x is not None and axis_z is not None:
                        vm = math.sqrt(axis_x**2 + axis_y**2 + axis_z**2)
                    else:
                        vm = None

                    batch_data.append((*static_values, timestamps[i], axis_y, axis_x, axis_z, vm))

                if batch_data:
                    conn.executemany(
                        f"""
                        INSERT INTO {DatabaseTable.RAW_ACTIVITY_DATA} (
                            {DatabaseColumn.FILE_HASH}, {DatabaseColumn.FILENAME},
                            {DatabaseColumn.PARTICIPANT_KEY}, {DatabaseColumn.PARTICIPANT_ID},
                            {DatabaseColumn.PARTICIPANT_GROUP}, {DatabaseColumn.PARTICIPANT_TIMEPOINT},
                            {DatabaseColumn.TIMESTAMP}, {DatabaseColumn.AXIS_Y},
                            {DatabaseColumn.AXIS_X}, {DatabaseColumn.AXIS_Z},
                            {DatabaseColumn.VECTOR_MAGNITUDE}
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch_data,
                    )

                    if progress:
                        progress.processed_records += len(batch_data)

            return True

        except Exception:
            logger.exception("Failed to import activity data for %s", filename)
            return False

    def import_directory(
        self,
        directory_path: Path,
        skip_rows: int = 10,
        force_reimport: bool = False,
        progress_callback: Callable[[ImportProgress], None] | None = None,
        include_nonwear: bool = False,
        custom_columns: dict[str, str] | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> ImportProgress:
        """Import all CSV files from a directory."""
        try:
            # Validate directory
            validated_dir = InputValidator.validate_directory_path(directory_path, must_exist=True, create_if_missing=False)

            # Find CSV files
            csv_files = list(validated_dir.rglob("*.csv"))
            logger.info("Found %s CSV files in %s", len(csv_files), validated_dir)

            # Estimate total records for progress tracking
            total_records = 0
            valid_files = []

            for csv_file in csv_files:
                try:
                    # Quick row count estimation
                    with open(csv_file) as f:
                        # Skip header rows and count remaining
                        for _ in range(skip_rows):
                            next(f, None)
                        row_count = sum(1 for _ in f)

                    total_records += max(0, row_count)
                    valid_files.append(csv_file)

                except (OSError, PermissionError, ValueError) as e:
                    logger.warning("Skipping %s: %s", csv_file, e)

            # Initialize progress
            progress = ImportProgress(total_files=len(valid_files), total_records=total_records)

            # Import files
            for csv_file in valid_files:
                # Check for cancellation before processing each file
                if cancellation_check and cancellation_check():
                    logger.info("Import cancelled by user after %d files", progress.processed_files)
                    progress.add_warning("Import cancelled by user")
                    break

                try:
                    self.import_csv_file(csv_file, progress, skip_rows, force_reimport, custom_columns)

                    if progress_callback:
                        progress_callback(progress)

                except (DatabaseError, OSError, ValidationError, ValueError) as e:
                    progress.add_error(f"Failed to import {csv_file}: {e}")

            # Import nonwear sensor and Choi algorithm data (only if requested)
            if include_nonwear:
                try:
                    self.import_nonwear_data(validated_dir, progress)
                except (DatabaseError, OSError, ValidationError) as e:
                    progress.add_error(f"Failed to import nonwear data: {e}")

            # Complete
            progress.processed_files = len(valid_files)

            logger.info(
                "Import completed: %s files imported, %s skipped, %s errors",
                len(progress.imported_files),
                len(progress.skipped_files),
                len(progress.errors),
            )

            return progress

        except (OSError, DatabaseError, ValidationError) as e:
            error_progress = ImportProgress()
            error_progress.add_error(f"Failed to import directory {directory_path}: {e}")
            return error_progress

    def import_files(
        self,
        file_paths: list[Path],
        skip_rows: int = 10,
        force_reimport: bool = False,
        progress_callback: Callable[[ImportProgress], None] | None = None,
        custom_columns: dict[str, str] | None = None,
        cancellation_check: Callable[[], bool] | None = None,
    ) -> ImportProgress:
        """Import a list of CSV files directly."""
        try:
            # Validate and filter files
            valid_files = []
            total_records = 0

            for file_path in file_paths:
                try:
                    validated_file = InputValidator.validate_file_path(file_path, must_exist=True)
                    # Quick row count estimation
                    with open(validated_file) as f:
                        for _ in range(skip_rows):
                            next(f, None)
                        row_count = sum(1 for _ in f)

                    total_records += max(0, row_count)
                    valid_files.append(validated_file)

                except (OSError, PermissionError, ValueError, ValidationError) as e:
                    logger.warning("Skipping %s: %s", file_path, e)

            logger.info("Importing %s CSV files (%s total records)", len(valid_files), total_records)

            # Initialize progress
            progress = ImportProgress(total_files=len(valid_files), total_records=total_records)

            # Import files
            for csv_file in valid_files:
                # Check for cancellation before processing each file
                if cancellation_check and cancellation_check():
                    logger.info("Import cancelled by user after %d files", progress.processed_files)
                    progress.add_warning("Import cancelled by user")
                    break

                try:
                    self.import_csv_file(csv_file, progress, skip_rows, force_reimport, custom_columns)

                    if progress_callback:
                        progress_callback(progress)

                except (DatabaseError, OSError, ValidationError, ValueError) as e:
                    progress.add_error(f"Failed to import {csv_file}: {e}")

            # Complete
            progress.processed_files = len(valid_files)

            logger.info(
                "Import completed: %s files imported, %s skipped, %s errors",
                len(progress.imported_files),
                len(progress.skipped_files),
                len(progress.errors),
            )

            return progress

        except (OSError, DatabaseError, ValidationError) as e:
            error_progress = ImportProgress()
            error_progress.add_error(f"Failed to import files: {e}")
            return error_progress

    def get_import_summary(self) -> dict[str, Any]:
        """Get summary of imported files."""
        try:
            return self.db_manager.file_registry.get_import_summary()
        except Exception:
            logger.exception("Failed to get import summary")
            return {
                "total_files": 0,
                "total_records": 0,
                "imported_files": 0,
                "error_files": 0,
            }

    def import_nonwear_data(
        self,
        data_directory: Path,
        progress: ImportProgress | None = None,
        progress_callback: Callable[[ImportProgress], None] | None = None,
    ) -> None:
        """Import nonwear sensor data (Choi algorithm results are generated on-demand)."""
        try:
            # Import nonwear sensor data only
            nonwear_files = self.nonwear_service.find_nonwear_sensor_files(data_directory)

            # Setup separate nonwear progress tracking
            if progress:
                progress.total_nonwear_files = len(nonwear_files)
                progress.processed_nonwear_files = 0

            for nonwear_file in nonwear_files:
                try:
                    if progress:
                        progress.current_nonwear_file = nonwear_file.name

                    periods = self.nonwear_service.load_nonwear_sensor_periods(nonwear_file)
                    filename = nonwear_file.name
                    self.nonwear_service.save_nonwear_periods(periods, filename)

                    if progress:
                        progress.imported_nonwear_files.append(nonwear_file.name)
                        progress.processed_nonwear_files += 1
                        progress.add_info(f"Imported {len(periods)} nonwear sensor periods from {nonwear_file.name}")
                        if progress_callback:
                            progress_callback(progress)

                except (OSError, PermissionError, pd.errors.ParserError, ValueError) as e:
                    if progress:
                        progress.processed_nonwear_files += 1
                        progress.add_error(f"Failed to import nonwear sensor file {nonwear_file.name}: {e}")
                        if progress_callback:
                            progress_callback(progress)

            logger.info("Nonwear sensor data import completed: %s sensor files", len(nonwear_files))

        except Exception:
            logger.exception("Failed to import nonwear sensor data")
            raise

    def import_nonwear_files(
        self,
        file_paths: list[Path],
        progress: ImportProgress | None = None,
        progress_callback: Callable[[ImportProgress], None] | None = None,
    ) -> None:
        """Import specific nonwear sensor files."""
        try:
            # Setup separate nonwear progress tracking
            if progress:
                progress.total_nonwear_files = len(file_paths)
                progress.processed_nonwear_files = 0

            for nonwear_file in file_paths:
                try:
                    if progress:
                        progress.current_nonwear_file = nonwear_file.name

                    periods = self.nonwear_service.load_nonwear_sensor_periods(nonwear_file)
                    filename = nonwear_file.name
                    self.nonwear_service.save_nonwear_periods(periods, filename)

                    if progress:
                        progress.imported_nonwear_files.append(nonwear_file.name)
                        progress.processed_nonwear_files += 1
                        progress.add_info(f"Imported {len(periods)} nonwear sensor periods from {nonwear_file.name}")
                        if progress_callback:
                            progress_callback(progress)

                except (OSError, PermissionError, pd.errors.ParserError, ValueError) as e:
                    if progress:
                        progress.processed_nonwear_files += 1
                        progress.add_error(f"Failed to import nonwear sensor file {nonwear_file.name}: {e}")
                        if progress_callback:
                            progress_callback(progress)

            logger.info("Nonwear sensor file import completed: %s files", len(file_paths))

        except Exception:
            logger.exception("Failed to import nonwear sensor files")
            raise
