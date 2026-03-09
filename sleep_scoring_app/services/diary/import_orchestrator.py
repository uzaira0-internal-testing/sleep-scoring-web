"""Import orchestration for diary files."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from sleep_scoring_app.core.constants import DatabaseColumn, DatabaseTable
from sleep_scoring_app.core.dataclasses import (
    DiaryColumnMapping,
    DiaryEntry,
    DiaryFileInfo,
    DiaryImportResult,
    ParticipantInfo,
)
from sleep_scoring_app.core.exceptions import (
    DatabaseError,
    ErrorCodes,
    SleepScoringImportError,
    ValidationError,
)
from sleep_scoring_app.services.diary.data_extractor import DiaryDataExtractor
from sleep_scoring_app.services.diary.progress import DiaryImportProgress

if TYPE_CHECKING:
    from collections.abc import Callable

    from sleep_scoring_app.data.database import DatabaseManager

logger = logging.getLogger(__name__)


class DiaryImportOrchestrator:
    """Orchestrates diary file import operations."""

    def __init__(self, database_manager: DatabaseManager) -> None:
        self.db_manager = database_manager
        self._extractor = DiaryDataExtractor()
        self._progress = DiaryImportProgress()
        self._column_mapping: DiaryColumnMapping | None = None

    @property
    def progress(self) -> DiaryImportProgress:
        """Get current import progress."""
        return self._progress

    def import_diary_files(
        self,
        file_paths: list[Path],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> DiaryImportResult:
        """Import multiple diary files using configuration-based column mapping."""
        start_time = time.time()
        result = DiaryImportResult()

        try:
            # Load column mapping configuration
            self._column_mapping = self._load_column_mapping()

            # Validate inputs
            self._validate_import_inputs(file_paths)

            # Prepare file info
            file_infos = []
            total_sheets = 0

            for file_path in file_paths:
                try:
                    file_info = DiaryFileInfo.from_path(file_path)

                    # Get sheet names for Excel files
                    if file_info.file_type == "excel":
                        file_info.sheet_names = self._get_excel_sheet_names(file_path)
                        total_sheets += len(file_info.sheet_names)
                    else:
                        total_sheets += 1

                    file_infos.append(file_info)

                except Exception as e:
                    logger.exception(f"Failed to process file info for {file_path}: {e}")
                    result.failed_files.append((str(file_path), str(e)))

            # Initialize progress tracking
            self._progress = DiaryImportProgress(total_files=len(file_infos), total_sheets=total_sheets)

            # Process each file
            for file_info in file_infos:
                self._progress.current_file = file_info.file_path.name
                self._progress.current_operation = "processing"
                self._emit_progress(progress_callback)

                try:
                    self._process_diary_file(file_info, result, progress_callback)
                    result.successful_files.append(file_info.file_path.name)

                except Exception as e:
                    logger.exception(f"Failed to process file {file_info.file_path}: {e}")
                    result.failed_files.append((file_info.file_path.name, str(e)))

                finally:
                    self._progress.processed_files += 1
                    self._emit_progress(progress_callback)

            # Finalize results
            result.total_files_processed = len(file_infos)
            result.import_duration_seconds = time.time() - start_time

            logger.info(
                f"Diary import completed: {len(result.successful_files)}/{result.total_files_processed} files successful, "
                f"{result.total_entries_imported} entries imported"
            )

            return result

        except Exception as e:
            logger.exception(f"Diary import failed: {e}")
            result.import_duration_seconds = time.time() - start_time
            msg = f"Diary import failed: {e}"
            raise SleepScoringImportError(
                msg,
                error_code=ErrorCodes.IMPORT_FAILED,
                context={"file_count": len(file_paths)},
            ) from e

    def _load_column_mapping(self) -> DiaryColumnMapping:
        """Load embedded column mapping configuration."""
        try:
            logger.debug("Loading embedded diary mapping configuration")

            # Embedded mapping configuration based on TECH_diary_mapping.json
            config_data = {
                "participant_id_column_name": "participant_id",
                "sleep_onset_time_column_name": "sleep_onset_time",
                "sleep_offset_time_column_name": "sleep_offset_time",
                "in_bed_time_column_name": "in_bed_time",
                "out_of_bed_time_column_name": None,
                "napped_column_name": "napped",
                "nap_onset_time_column_name": "napstart_1_time",
                "nap_offset_time_column_name": "napend_1_time",
                "nap_onset_time_column_names": "nap_onset_time_2,nap_onset_time_3,nap_onset_time_4",
                "nap_offset_time_column_names": "nap_offset_time_2,nap_offset_time_3,nap_offset_time_4",
                "nonwear_occurred_column_name": "nonwear_occurred",
                "nonwear_reason_column_names": "nonwear_reason,nonwear_reason_2,nonwear_reason_3,nonwear_reason_4",
                "nonwear_start_time_column_names": "nonwear_start_time,nonwear_start_time_2,nonwear_start_time_3,nonwear_start_time_4",
                "nonwear_end_time_column_names": "nonwear_end_time,nonwear_end_time_2,nonwear_end_time_3,nonwear_end_time_4",
                "diary_completed_for_current_day_column_name": "sleep_diary_day_complete",
                "activity_columns": "activity_other1,activity_other2,activity_other3,activity_other4",
                "expected_diary_entry_date_column_name": None,
                "diary_submission_date_column_name": None,
                "date_of_last_night_column_name": "startdate",
                "sleep_onset_date_column_name": None,
                "sleep_offset_date_column_name": None,
                "todays_date_column_name": None,
                "nap_onset_date_column_name": None,
                "nap_offset_date_column_name": None,
                "participant_timepoint_column_name": None,
                "participant_group_column_name": None,
                "auto_calculated_columns": {
                    "sleep_onset_time_column_name": False,
                    "sleep_offset_time_column_name": False,
                    "in_bed_time_column_name": False,
                    "nap_onset_time_column_name": True,
                    "nap_offset_time_column_name": True,
                    "todays_date_column_name": False,
                    "sleep_onset_date_column_name": False,
                    "sleep_offset_date_column_name": False,
                    "nap_onset_date_column_name": False,
                    "nap_offset_date_column_name": False,
                },
                "alternative_column_names": {
                    "sleep_onset_time": [
                        "sleep_onset_time",
                        "sleep_onset_time_auto",
                        "asleep_time",
                    ],
                    "sleep_offset_time": [
                        "sleep_offset_time",
                        "sleep_offset_time_auto",
                        "wake_time",
                    ],
                    "in_bed_time": ["bedtime", "in_bed_time_auto", "inbed_time"],
                    "nap_onset_time": ["nap_onset_time_auto", "napstart_1_time"],
                    "nap_offset_time": ["nap_offset_time_auto", "napend_1_time"],
                },
            }

            mapping = DiaryColumnMapping.from_dict(config_data)
            logger.info("Successfully loaded embedded diary column mapping")
            return mapping

        except Exception as e:
            msg = f"Failed to load embedded diary mapping configuration: {e}"
            raise ValidationError(
                msg,
                error_code=ErrorCodes.VALIDATION_FAILED,
                context={"error": str(e)},
            ) from e

    def _validate_import_inputs(self, file_paths: list[Path]) -> None:
        """Validate import inputs."""
        if not file_paths:
            msg = "No files provided for import"
            raise ValidationError(
                msg,
                error_code=ErrorCodes.VALIDATION_FAILED,
            )

        # Validate file paths
        for file_path in file_paths:
            if not file_path.exists():
                msg = f"File does not exist: {file_path}"
                raise ValidationError(
                    msg,
                    error_code=ErrorCodes.FILE_NOT_FOUND,
                    context={"file_path": str(file_path)},
                )

            if file_path.suffix.lower() not in [".csv", ".xlsx", ".xls"]:
                msg = f"Unsupported file format: {file_path.suffix}"
                raise ValidationError(
                    msg,
                    error_code=ErrorCodes.UNSUPPORTED_FILE_FORMAT,
                    context={"file_path": str(file_path)},
                )

    def _get_excel_sheet_names(self, file_path: Path) -> list[str]:
        """Get sheet names from Excel file."""
        try:
            excel_file = pd.ExcelFile(file_path)
            return excel_file.sheet_names
        except Exception as e:
            logger.exception(f"Failed to get sheet names from {file_path}: {e}")
            return []

    def _process_diary_file(
        self,
        file_info: DiaryFileInfo,
        result: DiaryImportResult,
        progress_callback: Callable[[str, int, int], None] | None,
    ) -> None:
        """Process a single diary file."""
        if file_info.file_type == "excel":
            # Process each sheet in Excel file
            for sheet_name in file_info.sheet_names:
                self._progress.current_sheet = sheet_name
                self._process_sheet(file_info, sheet_name, result, progress_callback)
                self._progress.processed_sheets += 1
                self._emit_progress(progress_callback)
        else:
            # Process CSV file
            self._process_sheet(file_info, None, result, progress_callback)
            self._progress.processed_sheets += 1
            self._emit_progress(progress_callback)

    def _process_sheet(
        self,
        file_info: DiaryFileInfo,
        sheet_name: str | None,
        result: DiaryImportResult,
        progress_callback: Callable[[str, int, int], None] | None,
    ) -> None:
        """Process a single sheet/CSV file."""
        try:
            # Load data
            self._progress.current_operation = "loading"
            self._emit_progress(progress_callback)

            data = self._load_sheet_data(file_info.file_path, sheet_name)
            if data.empty:
                logger.warning(f"No data found in {file_info.file_path} sheet {sheet_name}")
                return

            # Store mapping result
            mapping_key = f"{file_info.file_path.name}:{sheet_name}" if sheet_name else file_info.file_path.name
            result.mapping_results[mapping_key] = self._column_mapping

            # Convert data to standard format
            self._progress.current_operation = "importing"
            self._emit_progress(progress_callback)

            diary_entries = self._convert_data_to_entries(
                data,
                self._column_mapping,
                file_info.file_path.name,
                sheet_name,
            )

            # Import to database
            self._import_entries_to_database(diary_entries, file_info.file_path)

            # Update statistics
            result.total_entries_imported += len(diary_entries)
            self._progress.entries_imported += len(diary_entries)

            # Collect participant IDs
            for entry in diary_entries:
                result.participants_found.add(entry.participant_id)

            logger.info(
                f"Successfully imported {len(diary_entries)} diary entries from {file_info.file_path.name}{':' + sheet_name if sheet_name else ''}"
            )

        except Exception as e:
            error_msg = f"Failed to process sheet {sheet_name or 'CSV'}: {e}"
            logger.exception(error_msg)
            sheet_key = f"{file_info.file_path.name}:{sheet_name}" if sheet_name else file_info.file_path.name
            result.failed_files.append((sheet_key, error_msg))

    def _load_sheet_data(self, file_path: Path, sheet_name: str | None) -> pd.DataFrame:
        """Load data from CSV or Excel sheet."""
        file_extension = file_path.suffix.lower()

        try:
            if file_extension == ".csv":
                # Try different encodings
                for encoding in ["utf-8", "latin-1", "cp1252"]:
                    try:
                        data = pd.read_csv(file_path, encoding=encoding)
                        logger.debug(f"Successfully read CSV with {encoding} encoding")
                        return data
                    except (UnicodeDecodeError, KeyError):
                        continue
                # Fallback to default
                return pd.read_csv(file_path)

            if file_extension in [".xlsx", ".xls"]:
                return pd.read_excel(file_path, sheet_name=sheet_name or 0)

            msg = f"Unsupported file format: {file_extension}"
            raise ValueError(msg)

        except Exception as e:
            msg = f"Failed to load data from {file_path}: {e}"
            raise SleepScoringImportError(
                msg,
                error_code=ErrorCodes.FILE_READ_ERROR,
                context={"file_path": str(file_path), "sheet_name": sheet_name},
            ) from e

    def _convert_data_to_entries(
        self,
        data: pd.DataFrame,
        column_mapping: DiaryColumnMapping | None,
        filename: str,
        sheet_name: str | None,
    ) -> list[DiaryEntry]:
        """Convert DataFrame to DiaryEntry objects using column mapping."""
        if column_mapping is None:
            return []

        # Auto-detect REDCap wide format and pivot to long before normal processing
        from sleep_scoring_web.services.redcap_diary_converter import (
            convert_redcap_wide_to_long,
            is_redcap_wide_format,
        )

        if is_redcap_wide_format(list(data.columns)):
            import polars as pl

            logger.info("Detected REDCap wide format in %s, converting to long format", filename)
            data = convert_redcap_wide_to_long(pl.from_pandas(data)).to_pandas()

        # Resolve column names against actual CSV columns using alternatives
        available_columns = list(data.columns)
        column_mapping.resolve_columns(available_columns)
        logger.debug("Resolved column mapping against %d available columns", len(available_columns))

        entries = []

        logger.debug(f"Converting {len(data)} rows from {filename} sheet {sheet_name or 'CSV'}")

        for _, row in data.iterrows():
            try:
                # Extract participant ID
                participant_id = self._extractor.extract_participant_id(row, column_mapping)
                if not participant_id:
                    logger.warning("No participant ID found in row, skipping")
                    continue

                # Extract diary date
                diary_date = self._extractor.extract_diary_date(row, column_mapping)
                if not diary_date:
                    logger.warning(f"No diary date found for participant {participant_id}, skipping")
                    continue

                # Extract nonwear fields
                (
                    nonwear_start_1,
                    nonwear_start_2,
                    nonwear_start_3,
                ) = self._extractor.extract_multiple_time_fields(row, column_mapping.nonwear_start_time_column_names)
                (
                    nonwear_end_1,
                    nonwear_end_2,
                    nonwear_end_3,
                ) = self._extractor.extract_multiple_time_fields(row, column_mapping.nonwear_end_time_column_names)
                (
                    nonwear_reason_raw_1,
                    nonwear_reason_raw_2,
                    nonwear_reason_raw_3,
                ) = self._extractor.extract_multiple_text_fields(row, column_mapping.nonwear_reason_column_names)

                # Convert reason codes
                nonwear_reason_1 = self._extractor.convert_nonwear_reason_code(nonwear_reason_raw_1)
                nonwear_reason_2 = self._extractor.convert_nonwear_reason_code(nonwear_reason_raw_2)
                nonwear_reason_3 = self._extractor.convert_nonwear_reason_code(nonwear_reason_raw_3)

                # Extract nap data
                nap_onset_1 = self._extractor.extract_time_field(row, column_mapping.nap_onset_time_column_name)
                nap_offset_1 = self._extractor.extract_time_field(row, column_mapping.nap_offset_time_column_name)

                # Try alternative columns if primary not found
                if nap_onset_1 is None:
                    for alt_col in [
                        "nap_onset_time_auto",
                        "nap_onset_time",
                        "napstart_time",
                    ]:
                        if alt_col != column_mapping.nap_onset_time_column_name:
                            nap_onset_1 = self._extractor.extract_time_field(row, alt_col)
                            if nap_onset_1:
                                break

                if nap_offset_1 is None:
                    for alt_col in [
                        "nap_offset_time_auto",
                        "nap_offset_time",
                        "napend_time",
                    ]:
                        if alt_col != column_mapping.nap_offset_time_column_name:
                            nap_offset_1 = self._extractor.extract_time_field(row, alt_col)
                            if nap_offset_1:
                                break

                # Extract additional naps
                (
                    nap_onset_2_temp,
                    nap_onset_3_temp,
                    nap_offset_2_temp,
                    nap_offset_3_temp,
                ) = self._extractor.extract_multiple_nap_fields(row, column_mapping)

                # Handle nap data positioning
                if nap_onset_1 is None and nap_offset_1 is None and nap_onset_2_temp is not None:
                    nap_onset_1 = nap_onset_2_temp
                    nap_offset_1 = nap_offset_2_temp
                    nap_onset_2 = nap_onset_3_temp
                    nap_offset_2 = nap_offset_3_temp
                    nap_onset_3 = None
                    nap_offset_3 = None
                else:
                    nap_onset_2 = nap_onset_2_temp
                    nap_offset_2 = nap_offset_2_temp
                    nap_onset_3 = nap_onset_3_temp
                    nap_offset_3 = nap_offset_3_temp

                # Create diary entry
                entry = DiaryEntry(
                    participant_id=participant_id,
                    diary_date=diary_date,
                    filename=filename,
                    sleep_onset_time=self._extractor.extract_time_field(row, column_mapping.sleep_onset_time_column_name),
                    sleep_offset_time=self._extractor.extract_time_field(row, column_mapping.sleep_offset_time_column_name),
                    in_bed_time=self._extractor.extract_time_field(row, column_mapping.in_bed_time_column_name),
                    nap_occurred=self._extractor.extract_integer_field(row, column_mapping.napped_column_name),
                    nap_onset_time=nap_onset_1,
                    nap_offset_time=nap_offset_1,
                    nap_onset_time_2=nap_onset_2,
                    nap_offset_time_2=nap_offset_2,
                    nap_onset_time_3=nap_onset_3,
                    nap_offset_time_3=nap_offset_3,
                    nonwear_occurred=self._extractor.extract_boolean_field(row, column_mapping.nonwear_occurred_column_name),
                    nonwear_start_time=nonwear_start_1,
                    nonwear_end_time=nonwear_end_1,
                    nonwear_reason=nonwear_reason_1,
                    nonwear_start_time_2=nonwear_start_2,
                    nonwear_end_time_2=nonwear_end_2,
                    nonwear_reason_2=nonwear_reason_2,
                    nonwear_start_time_3=nonwear_start_3,
                    nonwear_end_time_3=nonwear_end_3,
                    nonwear_reason_3=nonwear_reason_3,
                    original_column_mapping=json.dumps(column_mapping.to_dict()),
                )

                entries.append(entry)

            except Exception as e:
                logger.exception(f"Failed to convert row to diary entry: {e}")
                continue

        return entries

    def _import_entries_to_database(self, entries: list[DiaryEntry], file_path: Path | None = None) -> None:
        """Import diary entries to database with proper file registration."""
        if not entries:
            return

        from sleep_scoring_app.data.repositories.base_repository import BaseRepository

        temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
        try:
            with temp_repo._get_connection() as conn:
                cursor = conn.cursor()

                # Group entries by filename
                files_by_filename: dict[str, DiaryEntry] = {}
                for entry in entries:
                    if entry.filename not in files_by_filename:
                        files_by_filename[entry.filename] = entry

                # Register each unique file first
                for filename in files_by_filename:
                    try:
                        actual_file_path = file_path if file_path else Path(filename)

                        file_hash = "unknown"
                        if actual_file_path.exists():
                            file_hash = self._calculate_file_hash(actual_file_path)

                        participant_info = self._extract_participant_info_from_filename(filename)

                        self._register_diary_file(
                            conn,
                            filename,
                            actual_file_path,
                            file_hash,
                            participant_info,
                        )

                    except Exception as reg_error:
                        logger.warning(f"Failed to register file {filename}: {reg_error}")

                # Insert entries
                for entry in entries:
                    entry_dict = entry.to_database_dict()

                    columns = list(entry_dict.keys())
                    placeholders = ", ".join(["?" for _ in columns])
                    values = list(entry_dict.values())

                    query = f"""
                        INSERT OR REPLACE INTO {DatabaseTable.DIARY_DATA}
                        ({", ".join(columns)})
                        VALUES ({placeholders})
                    """

                    cursor.execute(query, values)

                conn.commit()
                logger.info(f"Successfully imported {len(entries)} diary entries to database")

        except Exception as e:
            msg = f"Failed to import diary entries: {e}"
            raise DatabaseError(
                msg,
                error_code=ErrorCodes.DB_QUERY_FAILED,
                context={"entry_count": len(entries)},
            ) from e

    def _register_diary_file(
        self,
        conn: Any,
        filename: str,
        file_path: Path,
        file_hash: str,
        participant_info: ParticipantInfo | None = None,
    ) -> None:
        """Register diary file in registry before importing entries."""
        try:
            file_stat = file_path.stat()

            if participant_info is None:
                participant_info = self._extract_participant_info_from_filename(filename)

            if participant_info is None:
                participant_info = ParticipantInfo(
                    numerical_id="UNKNOWN",
                    group_str="G1",  # Set string representation for export
                    timepoint_str="T1",  # Set string representation for export
                )

            conn.execute(
                f"""
                INSERT OR REPLACE INTO {DatabaseTable.DIARY_FILE_REGISTRY} (
                    {DatabaseColumn.FILENAME}, {DatabaseColumn.ORIGINAL_PATH},
                    {DatabaseColumn.PARTICIPANT_ID}, {DatabaseColumn.PARTICIPANT_GROUP},
                    {DatabaseColumn.PARTICIPANT_TIMEPOINT}, {DatabaseColumn.FILE_HASH},
                    {DatabaseColumn.FILE_SIZE}, {DatabaseColumn.LAST_MODIFIED}
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    filename,
                    str(file_path),
                    participant_info.numerical_id,
                    participant_info.group_str,
                    participant_info.timepoint_str,
                    file_hash,
                    file_stat.st_size,
                    datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                ),
            )

        except Exception as e:
            logger.exception(f"Failed to register diary file {filename}: {e}")
            raise

    def _extract_participant_info_from_filename(self, filename: str) -> ParticipantInfo | None:
        """Extract participant info from filename."""
        from sleep_scoring_app.utils.participant_extractor import (
            extract_participant_info,
        )

        try:
            return extract_participant_info(filename)
        except Exception as e:
            logger.exception(f"Failed to extract participant info from filename {filename}: {e}")
            return None

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file for change detection."""
        try:
            hash_sha256 = hashlib.sha256()
            with file_path.open("rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_sha256.update(chunk)
            return hash_sha256.hexdigest()
        except Exception as e:
            logger.exception(f"Failed to calculate hash for {file_path}: {e}")
            stat = file_path.stat()
            fallback_data = f"{file_path.name}_{stat.st_size}_{stat.st_mtime}".encode()
            return hashlib.sha256(fallback_data).hexdigest()

    def _emit_progress(self, progress_callback: Callable[[str, int, int], None] | None) -> None:
        """Emit progress update."""
        if progress_callback:
            progress_callback(
                self._progress.get_status_text(),
                self._progress.processed_sheets,
                self._progress.total_sheets,
            )
