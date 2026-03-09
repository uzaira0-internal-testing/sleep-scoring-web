"""
Export system for sleep scoring application
Handles data export, backup creation, and file operations.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd

from sleep_scoring_app.core.constants import (
    ActivityDataPreference,
    AlgorithmOutputColumn,
    AlgorithmType,
    DefaultColumn,
    DirectoryName,
    ExportColumn,
    NonwearAlgorithm,
    get_backup_filename,
    sanitize_filename_component,
)
from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes, ValidationError
from sleep_scoring_app.data.database import DatabaseManager

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import SleepMetrics

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ExportResult:
    """Result of export operation with accumulated warnings and errors."""

    success: bool
    files_exported: int = 0
    files_with_issues: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)
        logger.warning(message)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.errors.append(message)
        logger.error(message)

    def has_issues(self) -> bool:
        """Check if there are any warnings or errors."""
        return bool(self.warnings or self.errors)


class ExportManager:
    """Handles all export operations."""

    def __init__(self, database_manager: DatabaseManager | None = None) -> None:
        self.db_manager = database_manager or DatabaseManager()
        self.max_backups = 10

    def _atomic_csv_write(self, df: pd.DataFrame, csv_path: Path, **kwargs) -> None:
        """Write CSV atomically to prevent corruption."""
        temp_path = csv_path.with_suffix(f".tmp.{os.getpid()}")

        try:
            df.to_csv(temp_path, float_format="%.4f", **kwargs)

            if temp_path.stat().st_size == 0:
                msg = "CSV write produced empty file"
                raise OSError(msg)

            temp_path.replace(csv_path)

        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise

    def _sanitize_csv_cell(self, value: str | float | None) -> str | int | float | None:
        """Prevent CSV formula injection."""
        if not isinstance(value, str):
            return value

        if value and value[0] in ("=", "+", "@", "\t", "\r"):
            return "'" + value

        return value

    def _validate_export_path(self, output_directory: str) -> tuple[bool, str]:
        """
        Validate that the export path is writable.

        Returns:
            Tuple of (is_valid, error_message)

        """
        try:
            path = Path(output_directory)

            # Check for network paths on Windows
            path_str = str(path)
            if path_str.startswith("\\\\"):
                # UNC path - check if the server/share exists
                parts = path_str.split("\\")
                if len(parts) >= 4:
                    server_share = "\\\\".join(["", "", parts[2], parts[3]])
                    if not Path(server_share).exists():
                        return False, f"Network path not accessible: {server_share}"

            # Check for unmapped drive letters on Windows
            if len(path_str) >= 2 and path_str[1] == ":":
                drive_letter = path_str[0].upper()
                drive_root = f"{drive_letter}:\\"
                # Check if the drive root exists (more reliable than just drive letter)
                if not Path(drive_root).exists():
                    return False, f"Drive not accessible: {drive_letter}:"
                # Also verify we can actually access the drive
                try:
                    list(Path(drive_root).iterdir())
                except (PermissionError, OSError):
                    return False, f"Drive not accessible: {drive_letter}:"

            # Check if parent exists and is writable for new paths
            if not path.exists():
                parent = path.parent
                # Walk up to find existing ancestor
                while not parent.exists() and parent != parent.parent:
                    parent = parent.parent

                if not parent.exists():
                    return False, "Cannot create directory: parent path does not exist"

                # Try to check write permission on existing parent
                try:
                    test_file = parent / f".write_test_{os.getpid()}"
                    test_file.touch()
                    test_file.unlink()
                except (PermissionError, OSError):
                    return False, f"No write permission in {parent}"

            return True, ""

        except Exception as e:
            return False, f"Path validation error: {e}"

    def export_all_sleep_data(self, output_directory: str | None = None) -> str | None:
        """Export all sleep data to CSV with backup creation."""
        try:
            # Get all data from database
            export_data = self.db_manager.get_all_sleep_data_for_export()

            if not export_data:
                return "No data available for export"

            # Convert to DataFrame
            df = pd.DataFrame(export_data)

            # Sanitize string columns
            for col in df.select_dtypes(include=["object"]).columns:
                df[col] = df[col].apply(self._sanitize_csv_cell)

            # Set output directory
            if not output_directory:
                output_directory = str(Path.cwd() / DirectoryName.SLEEP_DATA_EXPORTS)

            # Validate the export path before attempting to create it
            is_valid, error_msg = self._validate_export_path(output_directory)
            if not is_valid:
                logger.warning("Export path validation failed: %s", error_msg)
                return f"Error: {error_msg}"

            # Ensure output directory exists
            os.makedirs(output_directory, mode=0o755, exist_ok=True)

            # Generate filename with timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_filename = f"sleep_scoring_export_{timestamp}.csv"
            csv_path = Path(output_directory) / csv_filename

            # Create backup of existing file BEFORE export
            if csv_path.exists():
                self._create_backup(csv_path)

            # Export to CSV atomically
            self._atomic_csv_write(df, csv_path, index=False)

            return f"Exported {len(df)} records to {csv_path}"

        except (DatabaseError, OSError, PermissionError, ValueError) as e:
            logger.warning("Error exporting data: %s", e)
            return None

    def create_export_csv_only(
        self,
        sleep_metrics_list: list[SleepMetrics],
        algorithm_name: AlgorithmType = AlgorithmType.SADEH_1994_ACTILIFE,
    ) -> str | None:
        """Create CSV file for export dialog WITHOUT saving to database (to avoid duplicates)."""
        if not sleep_metrics_list:
            return None

        # Sanitize algorithm name to prevent security issues
        safe_algorithm_name = sanitize_filename_component(algorithm_name)
        if not safe_algorithm_name:
            safe_algorithm_name = sanitize_filename_component(AlgorithmType.SADEH_1994_ACTILIFE)

        try:
            # CRITICAL: Ensure all metrics (including naps) are calculated before export
            self._ensure_metrics_calculated_for_export(sleep_metrics_list)

            # Create export file path
            export_dir = Path.cwd() / "sleep_data_exports"
            export_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_filepath = export_dir / f"export_temp_{safe_algorithm_name}_{timestamp}.csv"

            # Create new data DataFrame from SleepMetrics objects - multiple periods per participant
            new_data = []
            for metrics in sleep_metrics_list:
                # Get all sleep periods for this participant/date
                period_rows = metrics.to_export_dict_list()
                new_data.extend(period_rows)

            export_df = pd.DataFrame(new_data)

            # Sanitize string columns to prevent formula injection
            for col in export_df.select_dtypes(include=["object"]).columns:
                export_df[col] = export_df[col].apply(self._sanitize_csv_cell)

            # Sort by Participant ID, Sleep Date, and Marker Index for consistent ordering
            sort_columns = []
            if "Numerical Participant ID" in export_df.columns:
                sort_columns.append("Numerical Participant ID")
            if "Sleep Date" in export_df.columns:
                sort_columns.append("Sleep Date")
            if "Marker Index" in export_df.columns:
                sort_columns.append("Marker Index")

            if sort_columns:
                export_df = export_df.sort_values(by=sort_columns, ascending=True)

            # Count total sleep periods exported
            total_periods = len(new_data)
            total_participants = len(sleep_metrics_list)

            # Write CSV file with header comments atomically
            temp_path = export_filepath.with_suffix(f".tmp.{os.getpid()}")
            try:
                with open(temp_path, "w", newline="", encoding="utf-8") as f:
                    f.write("#\n")
                    f.write("# Sleep Scoring Export Data (Multiple Periods)\n")
                    f.write("# Algorithm: ")
                    f.write(safe_algorithm_name)
                    f.write("\n")
                    f.write("# Generated: ")
                    f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    f.write("\n")
                    f.write("# Participants: ")
                    f.write(str(total_participants))
                    f.write("\n")
                    f.write("# Sleep Periods: ")
                    f.write(str(total_periods))
                    f.write("\n")
                    f.write("# Note: Each row represents one sleep period (main sleep or nap)\n")
                    f.write("#\n")

                    export_df.to_csv(f, index=False, float_format="%.4f")

                    f.flush()
                    os.fsync(f.fileno())

                if temp_path.stat().st_size == 0:
                    msg = "CSV write produced empty file"
                    raise OSError(msg)

                temp_path.replace(export_filepath)

            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

            logger.debug("Export CSV created: %s (%s participants, %s periods, NO database save)", export_filepath, total_participants, total_periods)
            return str(export_filepath)

        except (OSError, PermissionError, ValueError, pd.errors.ParserError) as e:
            logger.warning("Error creating export CSV: %s", e)
            return None

    def perform_direct_export(
        self,
        sleep_metrics_list: list[SleepMetrics],
        grouping_option: int,
        output_directory: str,
        selected_columns: list[str],
        include_headers: bool = True,
        include_metadata: bool = True,
        include_config_in_metadata: bool = False,
        export_config_sidecar: bool = False,
        config_manager: Any | None = None,
        export_nonwear_separate: bool = True,
    ) -> ExportResult:
        """Perform direct export from UI tab without modal dialog."""
        result = ExportResult(success=False)

        if not sleep_metrics_list:
            result.add_error("No sleep metrics provided for export")
            return result

        try:
            # Create output directory if it doesn't exist
            output_path = Path(output_directory)
            output_path.mkdir(parents=True, exist_ok=True)

            # CRITICAL FIX: Ensure metrics are calculated before export
            calculation_warnings = self._ensure_metrics_calculated_for_export(sleep_metrics_list)
            for warning in calculation_warnings:
                result.add_warning(warning)

            # Check for missing columns BEFORE export
            # Get a sample of the data to check available columns
            if sleep_metrics_list and selected_columns:
                sample_metric = sleep_metrics_list[0]
                sample_rows = sample_metric.to_export_dict_list()
                if sample_rows:
                    sample_df = pd.DataFrame(sample_rows)
                    missing_columns = [col for col in selected_columns if col not in sample_df.columns]
                    if missing_columns:
                        result.add_warning(f"Selected columns not available in data and will be skipped: {', '.join(missing_columns)}")

            # Filter data based on grouping option
            grouped_data = self._group_export_data(sleep_metrics_list, grouping_option)

            # Export each group
            for group_name, metrics in grouped_data.items():
                # Create filename based on group
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"sleep_data_{group_name}_{timestamp}.csv"
                filepath = output_path / filename

                # Convert to export format - multiple periods per participant
                export_data = []
                for metric in metrics:
                    period_rows = metric.to_export_dict_list()
                    export_data.extend(period_rows)

                export_df = pd.DataFrame(export_data)

                # Sanitize string columns
                for col in export_df.select_dtypes(include=["object"]).columns:
                    export_df[col] = export_df[col].apply(self._sanitize_csv_cell)

                # Sort by Participant ID, Sleep Date, and Marker Index for consistent ordering
                sort_columns = []
                if "Numerical Participant ID" in export_df.columns:
                    sort_columns.append("Numerical Participant ID")
                if "Sleep Date" in export_df.columns:
                    sort_columns.append("Sleep Date")
                if "Marker Index" in export_df.columns:
                    sort_columns.append("Marker Index")

                if sort_columns:
                    export_df = export_df.sort_values(by=sort_columns, ascending=True)

                # Filter columns if specified
                if selected_columns:
                    available_columns = [col for col in selected_columns if col in export_df.columns]
                    if available_columns:
                        export_df = export_df[available_columns]
                    else:
                        error_msg = (
                            f"Export for group '{group_name}': None of the selected columns are available. "
                            f"Selected: {selected_columns}, Available: {list(export_df.columns)}"
                        )
                        result.add_error(error_msg)
                        result.files_with_issues += 1
                        continue

                # Count totals for metadata
                total_periods = len(export_data)
                total_participants = len(metrics)

                # Write to CSV atomically
                temp_path = filepath.with_suffix(f".tmp.{os.getpid()}")
                try:
                    with open(temp_path, "w", newline="", encoding="utf-8") as f:
                        if include_metadata:
                            f.write("#\n")
                            f.write("# Sleep Scoring Export Data (Multiple Periods)\n")
                            f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                            f.write(f"# Group: {group_name}\n")
                            f.write(f"# Participants: {total_participants}\n")
                            f.write(f"# Sleep Periods: {total_periods}\n")
                            f.write("# Note: Each row represents one sleep period (main sleep or nap)\n")
                            f.write("#\n")

                            # Include configuration in metadata if requested
                            if include_config_in_metadata and config_manager is not None:
                                config_lines = config_manager.get_config_metadata_header()
                                f.writelines(line + "\n" for line in config_lines)
                                f.write("#\n")

                        export_df.to_csv(f, index=False, header=include_headers, float_format="%.4f")

                        f.flush()
                        os.fsync(f.fileno())

                    if temp_path.stat().st_size == 0:
                        msg = "CSV write produced empty file"
                        raise OSError(msg)

                    temp_path.replace(filepath)
                    result.files_exported += 1

                except Exception as e:
                    if temp_path.exists():
                        temp_path.unlink()
                    result.add_error(f"Failed to write file {filename}: {e}")
                    result.files_with_issues += 1
                    continue

                logger.debug("Exported %s participants (%s periods) to %s", total_participants, total_periods, filepath)

                # Export config sidecar file if requested
                if export_config_sidecar and config_manager is not None:
                    try:
                        config_sidecar_path = filepath.with_suffix(".config.csv")
                        config_manager.export_config_csv(config_sidecar_path)
                        logger.debug("Exported config sidecar to %s", config_sidecar_path)
                    except Exception as e:
                        result.add_warning(f"Failed to export config sidecar for {filename}: {e}")

            # Export nonwear markers to separate file if requested
            if export_nonwear_separate:
                nonwear_warnings, nonwear_errors = self._export_nonwear_markers_separate(
                    sleep_metrics_list,
                    output_path,
                    include_headers,
                    include_metadata,
                )
                for warning in nonwear_warnings:
                    result.add_warning(warning)
                for error in nonwear_errors:
                    result.add_error(error)

            # Mark as successful if at least some files were exported
            result.success = result.files_exported > 0
            return result

        except (OSError, PermissionError, ValueError, DatabaseError) as e:
            result.add_error(f"Export failed: {e}")
            return result

    def _ensure_metrics_calculated_for_export(self, sleep_metrics_list: list[SleepMetrics]) -> list[str]:
        """Ensure all sleep metrics have calculated values before export. Returns list of warnings."""
        from datetime import datetime, timedelta

        import pandas as pd

        from sleep_scoring_app.core.algorithms import AlgorithmFactory, NonwearAlgorithmFactory
        from sleep_scoring_app.core.constants import NonwearDataSource
        from sleep_scoring_app.services.data_service import DataManager
        from sleep_scoring_app.services.nonwear_service import NonwearDataService

        warnings = []
        failure_count = 0
        total_files = len(sleep_metrics_list)

        # Get service instances
        data_manager = DataManager(database_manager=self.db_manager)
        nonwear_service = NonwearDataService(database_manager=self.db_manager)

        # CRITICAL FIX #4: Cache for activity data to avoid redundant database calls
        # Key is filename, value is (timestamps, axis_y, vector_mag)
        # This prevents loading the same file's data multiple times for different periods
        activity_data_cache: dict[str, tuple[list, list, list]] = {}

        for metrics in sleep_metrics_list:
            # Get all complete sleep periods
            complete_periods = metrics.daily_sleep_markers.get_complete_periods()
            if not complete_periods:
                continue

            try:
                filename = metrics.filename

                # Load activity data ONCE per file (cache hit or miss)
                # FIX: Load ALL activity data for the file without time constraints.
                # The previous implementation only loaded data for ONE date's time range,
                # causing metrics calculation to fail for all other dates of the same file.
                # Per-period filtering (below) extracts the correct subset for each period.
                if filename not in activity_data_cache:
                    # Load ALL AXIS_Y data for Sadeh (no time constraints)
                    timestamps, axis_y_values = self.db_manager.load_raw_activity_data(
                        filename=filename, start_time=None, end_time=None, activity_column=ActivityDataPreference.AXIS_Y
                    )

                    if not timestamps or not axis_y_values:
                        warning_msg = (
                            f"No activity data found for {filename} - metrics will be incomplete. Check that the file was imported correctly."
                        )
                        warnings.append(warning_msg)
                        logger.warning(warning_msg)  # WARNING level so it's visible in logs
                        activity_data_cache[filename] = ([], [], [])
                        continue

                    # Also load ALL vector magnitude for Choi algorithm (no time constraints)
                    _, vector_magnitude = self.db_manager.load_raw_activity_data(
                        filename=filename, start_time=None, end_time=None, activity_column=ActivityDataPreference.VECTOR_MAGNITUDE
                    )

                    activity_data_cache[filename] = (timestamps, axis_y_values, vector_magnitude or [])
                    logger.debug("Cached ALL activity data for %s (%d epochs covering full file)", filename, len(timestamps))

                # Get cached data
                cached_timestamps, cached_axis_y, cached_vector_mag = activity_data_cache[filename]
                if not cached_timestamps:
                    continue

                # Calculate metrics for ALL periods using cached data
                for period in complete_periods:
                    # Extract the subset of data for this period
                    # Complete periods guaranteed to have non-None timestamps
                    if period.onset_timestamp is None or period.offset_timestamp is None:
                        continue
                    period_start = datetime.fromtimestamp(period.onset_timestamp) - timedelta(minutes=5)
                    period_end = datetime.fromtimestamp(period.offset_timestamp) + timedelta(minutes=5)

                    # Filter cached data to the period's time range
                    # Note: cached_timestamps are guaranteed to be datetime objects
                    # from load_raw_activity_data() which parses from ISO format
                    indices = []
                    for i, ts in enumerate(cached_timestamps):
                        if period_start <= ts <= period_end:
                            indices.append(i)

                    if not indices:
                        continue

                    timestamps = [cached_timestamps[i] for i in indices]
                    axis_y_values = [cached_axis_y[i] for i in indices]
                    vector_magnitude = [cached_vector_mag[i] for i in indices] if cached_vector_mag else []

                    # Convert datetime timestamps to Unix timestamps for metrics calculation
                    unix_timestamps = [ts.timestamp() for ts in timestamps]

                    # Get the algorithm from metrics or use default
                    algorithm_id = metrics.sleep_algorithm_name or AlgorithmFactory.get_default_algorithm_id()
                    sleep_algorithm = AlgorithmFactory.create(algorithm_id)

                    # Convert algorithm_id to AlgorithmType for metrics
                    try:
                        algorithm_type_for_metrics = AlgorithmType(algorithm_id) if algorithm_id else AlgorithmType.SADEH_1994_ACTILIFE
                    except ValueError:
                        algorithm_type_for_metrics = AlgorithmType.SADEH_1994_ACTILIFE

                    # Run sleep scoring algorithm using DI pattern
                    scoring_df = pd.DataFrame({"datetime": timestamps, DefaultColumn.AXIS_Y: axis_y_values})
                    scored_df = sleep_algorithm.score(scoring_df)
                    sadeh_results = scored_df[AlgorithmOutputColumn.SLEEP_SCORE].tolist()

                    # Run REAL Choi algorithm for nonwear detection
                    choi_results = []
                    if vector_magnitude:
                        # Create DataFrame for Choi algorithm
                        _ = pd.DataFrame(
                            {
                                "datetime": timestamps,
                                ActivityDataPreference.AXIS_Y: axis_y_values,
                                ActivityDataPreference.VECTOR_MAGNITUDE: vector_magnitude,
                            }
                        )

                        # Run Choi nonwear detection using DI pattern
                        choi_algorithm = NonwearAlgorithmFactory.create(NonwearAlgorithm.CHOI_2011)
                        choi_results = choi_algorithm.detect_mask(vector_magnitude)
                    else:
                        choi_results = [0] * len(sadeh_results)

                    # Get NWT sensor data from database
                    nwt_sensor_results = []
                    try:
                        # Get nonwear periods from sensor - convert timestamps to datetime
                        from datetime import datetime as dt

                        onset_dt = (
                            dt.fromtimestamp(period.onset_timestamp) if isinstance(period.onset_timestamp, int | float) else period.onset_timestamp
                        )
                        offset_dt = (
                            dt.fromtimestamp(period.offset_timestamp) if isinstance(period.offset_timestamp, int | float) else period.offset_timestamp
                        )

                        sensor_periods = nonwear_service.get_nonwear_periods_for_file(
                            filename=filename, source=NonwearDataSource.NONWEAR_SENSOR, start_time=onset_dt, end_time=offset_dt
                        )

                        # Convert to per-minute results
                        nwt_sensor_results = [0] * len(timestamps)
                        for nw_period in sensor_periods:
                            for i, ts in enumerate(timestamps):
                                # Convert timestamp to datetime if needed
                                ts_dt = datetime.fromtimestamp(ts) if isinstance(ts, int | float) else ts
                                # Access attributes of NonwearPeriod object
                                if nw_period.start_time <= ts_dt <= nw_period.end_time:
                                    nwt_sensor_results[i] = 1
                    except Exception as e:
                        warning_msg = f"Could not get NWT sensor data for {filename}: {e}"
                        warnings.append(warning_msg)
                        logger.debug(warning_msg)
                        nwt_sensor_results = [0] * len(timestamps)

                    # Calculate metrics for this period with REAL algorithm results using SleepPeriod directly
                    period_metrics = data_manager.calculate_sleep_metrics_for_period(
                        sleep_period=period,
                        sadeh_results=sadeh_results,
                        choi_results=choi_results,  # REAL Choi results
                        axis_y_data=axis_y_values,
                        x_data=unix_timestamps,
                        file_path=filename,
                        nwt_sensor_results=nwt_sensor_results,  # REAL NWT sensor data
                        algorithm_type=algorithm_type_for_metrics,
                    )

                    if period_metrics:
                        if not isinstance(period_metrics, dict):
                            warning_msg = (
                                f"Metrics calculation returned {type(period_metrics)} instead of dict for {filename} period {period.onset_timestamp}"
                            )
                            warnings.append(warning_msg)
                            logger.warning(warning_msg)
                            continue

                        # Store calculated metrics for this specific period
                        # CRITICAL: Use ExportColumn keys to match to_export_dict() keys
                        # so that row.update() in to_export_dict_list() properly overwrites
                        # the main sleep values with period-specific values for naps
                        period_metrics_for_storage: dict[str, Any] = {
                            ExportColumn.TOTAL_SLEEP_TIME: period_metrics.get("Total Sleep Time (TST)"),
                            ExportColumn.EFFICIENCY: period_metrics.get("Efficiency"),
                            ExportColumn.TOTAL_MINUTES_IN_BED: period_metrics.get("Total Minutes in Bed"),
                            ExportColumn.WASO: period_metrics.get("Wake After Sleep Onset (WASO)"),
                            ExportColumn.NUMBER_OF_AWAKENINGS: period_metrics.get("Number of Awakenings"),
                            ExportColumn.AVERAGE_AWAKENING_LENGTH: period_metrics.get("Average Awakening Length"),
                            ExportColumn.TOTAL_COUNTS: period_metrics.get("Total Counts"),
                            ExportColumn.MOVEMENT_INDEX: period_metrics.get("Movement Index"),
                            ExportColumn.FRAGMENTATION_INDEX: period_metrics.get("Fragmentation Index"),
                            ExportColumn.SLEEP_FRAGMENTATION_INDEX: period_metrics.get("Sleep Fragmentation Index"),
                            ExportColumn.SLEEP_ALGORITHM_ONSET: period_metrics.get("Sleep Algorithm Value at Onset"),
                            ExportColumn.SLEEP_ALGORITHM_OFFSET: period_metrics.get("Sleep Algorithm Value at Offset"),
                            ExportColumn.OVERLAPPING_NONWEAR_MINUTES_ALGORITHM: period_metrics.get("Overlapping Nonwear Minutes (Algorithm)"),
                            ExportColumn.OVERLAPPING_NONWEAR_MINUTES_SENSOR: period_metrics.get("Overlapping Nonwear Minutes (Sensor)"),
                        }

                        # Store metrics for this period (works for both main sleep and naps).
                        # Period-level storage in _dynamic_fields is the canonical source;
                        # to_export_dict_list() reads from here for each row.
                        metrics.store_period_metrics(period, period_metrics_for_storage)

            except Exception as e:
                import traceback

                failure_count += 1
                warning_msg = f"Error calculating metrics for {metrics.filename}: {e}"
                warnings.append(warning_msg)
                logger.warning(warning_msg)
                logger.warning("Full traceback: %s", traceback.format_exc())
                # Continue with export even if calculation fails for one file
                continue

        # Add summary warning if there were failures so user is aware of partial export
        if failure_count > 0:
            summary_msg = f"EXPORT WARNING: {failure_count} of {total_files} files had metrics calculation errors. Check log for details."
            warnings.insert(0, summary_msg)  # Put at start so it's visible
            logger.warning(summary_msg)

        return warnings

    def _export_nonwear_markers_separate(
        self,
        sleep_metrics_list: list[SleepMetrics],
        output_path: Path,
        include_headers: bool,
        include_metadata: bool,
    ) -> tuple[list[str], list[str]]:
        """Export manual nonwear markers to a separate CSV file. Returns (warnings, errors)."""
        from datetime import datetime

        warnings = []
        errors = []
        nonwear_data = []

        for metrics in sleep_metrics_list:
            try:
                filename = metrics.filename
                if not filename or not metrics.analysis_date:
                    continue

                # Parse analysis date
                try:
                    analysis_date = datetime.strptime(metrics.analysis_date, "%Y-%m-%d").date()
                except ValueError:
                    continue

                # Load manual nonwear markers for this file/date
                daily_nonwear = self.db_manager.load_manual_nonwear_markers(filename, str(analysis_date))
                complete_periods = daily_nonwear.get_complete_periods()

                if not complete_periods:
                    continue

                # Get participant info
                participant_id = ""
                group = ""
                timepoint = ""
                if metrics.participant is not None:  # participant is a dataclass field
                    participant_id = getattr(metrics.participant, "numerical_id", "")
                    group = getattr(metrics.participant, "group_str", "")
                    timepoint = getattr(metrics.participant, "timepoint_str", "")

                # Add each nonwear period as a row
                for i, period in enumerate(complete_periods, start=1):
                    # Defensive check: get_complete_periods() should only return periods
                    # with both timestamps set, but we guard against edge cases
                    if period.start_timestamp is None or period.end_timestamp is None:
                        logger.warning("Skipping incomplete nonwear period %d for %s", i, filename)
                        continue
                    start_dt = datetime.fromtimestamp(period.start_timestamp)
                    end_dt = datetime.fromtimestamp(period.end_timestamp)
                    duration = period.duration_minutes or 0.0

                    nonwear_data.append(
                        {
                            "Participant ID": participant_id,
                            "Group": group,
                            "Timepoint": timepoint,
                            "Filename": filename,
                            "Date": metrics.analysis_date,
                            "Nonwear Period Index": i,
                            "Start Time": start_dt.strftime("%H:%M"),
                            "End Time": end_dt.strftime("%H:%M"),
                            "Start Datetime": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "End Datetime": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                            "Duration (minutes)": round(duration, 1),
                        }
                    )

            except Exception as e:
                warning_msg = f"Failed to get nonwear data for {metrics.filename}: {e}"
                warnings.append(warning_msg)
                logger.warning(warning_msg)
                continue

        if not nonwear_data:
            logger.debug("No nonwear markers to export separately")
            return warnings, errors

        # Create DataFrame and export
        nonwear_df = pd.DataFrame(nonwear_data)

        # Sanitize string columns
        for col in nonwear_df.select_dtypes(include=["object"]).columns:
            nonwear_df[col] = nonwear_df[col].apply(self._sanitize_csv_cell)

        # Sort by participant and date
        sort_columns = []
        if "Participant ID" in nonwear_df.columns:
            sort_columns.append("Participant ID")
        if "Date" in nonwear_df.columns:
            sort_columns.append("Date")
        if "Nonwear Period Index" in nonwear_df.columns:
            sort_columns.append("Nonwear Period Index")

        if sort_columns:
            nonwear_df = nonwear_df.sort_values(by=sort_columns, ascending=True)

        # Create filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = output_path / f"nonwear_markers_{timestamp}.csv"

        # Write to CSV atomically
        temp_path = filepath.with_suffix(f".tmp.{os.getpid()}")
        try:
            with open(temp_path, "w", newline="", encoding="utf-8") as f:
                if include_metadata:
                    f.write("#\n")
                    f.write("# Manual Nonwear Markers Export\n")
                    f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"# Total Nonwear Periods: {len(nonwear_data)}\n")
                    f.write(f"# Participants with Nonwear: {len({row['Participant ID'] for row in nonwear_data})}\n")
                    f.write("#\n")

                nonwear_df.to_csv(f, index=False, header=include_headers, float_format="%.1f")

                f.flush()
                os.fsync(f.fileno())

            if temp_path.stat().st_size == 0:
                msg = "Nonwear CSV write produced empty file"
                raise OSError(msg)

            temp_path.replace(filepath)
            logger.info("Exported %d nonwear periods to %s", len(nonwear_data), filepath)

        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            error_msg = f"Failed to write nonwear markers file: {e}"
            errors.append(error_msg)
            logger.exception(error_msg)

        return warnings, errors

    def export_sleep_data(
        self,
        output_path: Path,
        column_selection: list[str],
        study_data: Any,
    ) -> None:
        """Export sleep markers and metrics to CSV."""
        # Get sleep rows from StudyData
        rows = study_data.export_sleep_rows()

        if not rows:
            logger.warning("No sleep data to export")
            return

        # Convert to DataFrame
        df = pd.DataFrame(rows)

        # Convert timestamps to formatted strings if needed
        if "onset_timestamp" in df.columns:
            df["onset_time"] = pd.to_datetime(df["onset_timestamp"], unit="s").dt.strftime("%H:%M")
            df["onset_datetime"] = pd.to_datetime(df["onset_timestamp"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")

        if "offset_timestamp" in df.columns:
            df["offset_time"] = pd.to_datetime(df["offset_timestamp"], unit="s").dt.strftime("%H:%M")
            df["offset_datetime"] = pd.to_datetime(df["offset_timestamp"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")

        # Filter to selected columns if specified
        if column_selection:
            # Map internal names to export column names for filtering
            available_columns = [col for col in column_selection if col in df.columns]
            if available_columns:
                # Ensure we keep a DataFrame (not Series) by using double brackets
                df = df[available_columns].copy()

        # Sanitize string columns
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(self._sanitize_csv_cell)

        # Write CSV atomically (df is always DataFrame due to .copy() above)
        assert isinstance(df, pd.DataFrame)
        self._atomic_csv_write(df, output_path, index=False)
        logger.info("Exported %d sleep periods to %s", len(df), output_path)

    def export_nonwear_data(
        self,
        output_path: Path,
        column_selection: list[str],
        study_data: Any,
    ) -> None:
        """Export nonwear markers to separate CSV."""
        # Get nonwear rows from StudyData
        rows = study_data.export_nonwear_rows()

        if not rows:
            logger.warning("No nonwear data to export")
            return

        # Convert to DataFrame
        df = pd.DataFrame(rows)

        # Convert timestamps to formatted strings if needed
        if "start_timestamp" in df.columns:
            df["start_time"] = pd.to_datetime(df["start_timestamp"], unit="s").dt.strftime("%H:%M")
            df["start_datetime"] = pd.to_datetime(df["start_timestamp"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")

        if "end_timestamp" in df.columns:
            df["end_time"] = pd.to_datetime(df["end_timestamp"], unit="s").dt.strftime("%H:%M")
            df["end_datetime"] = pd.to_datetime(df["end_timestamp"], unit="s").dt.strftime("%Y-%m-%d %H:%M:%S")

        # Filter to selected columns if specified
        if column_selection:
            available_columns = [col for col in column_selection if col in df.columns]
            if available_columns:
                # Ensure we keep a DataFrame (not Series) by using .copy()
                df = df[available_columns].copy()

        # Sanitize string columns
        for col in df.select_dtypes(include=["object"]).columns:
            df[col] = df[col].apply(self._sanitize_csv_cell)

        # Write CSV atomically
        assert isinstance(df, pd.DataFrame)
        self._atomic_csv_write(df, output_path, index=False)
        logger.info("Exported %d nonwear periods to %s", len(df), output_path)

    def export_combined(
        self,
        output_dir: Path,
        sleep_columns: list[str],
        nonwear_columns: list[str],
        study_data: Any,
    ) -> tuple[Path, Path]:
        """Export both sleep and nonwear data to separate files."""
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        sleep_path = output_dir / f"sleep_export_{timestamp}.csv"
        nonwear_path = output_dir / f"nonwear_export_{timestamp}.csv"

        self.export_sleep_data(sleep_path, sleep_columns, study_data)
        self.export_nonwear_data(nonwear_path, nonwear_columns, study_data)

        return sleep_path, nonwear_path

    def _group_export_data(self, sleep_metrics_list: list[SleepMetrics], grouping_option: int) -> dict[str, list[SleepMetrics]]:
        """Group sleep metrics based on grouping option."""
        if grouping_option == 0:  # All data in one file
            return {"all_data": sleep_metrics_list}
        if grouping_option == 1:  # By participant
            groups = {}
            for metrics in sleep_metrics_list:
                participant_id = metrics.participant.numerical_id
                if participant_id not in groups:
                    groups[participant_id] = []
                groups[participant_id].append(metrics)
            return groups
        if grouping_option == 2:  # By group
            groups = {}
            for metrics in sleep_metrics_list:
                group = metrics.participant.group_str
                if group not in groups:
                    groups[group] = []
                groups[group].append(metrics)
            return groups
        if grouping_option == 3:  # By timepoint
            groups = {}
            for metrics in sleep_metrics_list:
                timepoint = metrics.participant.timepoint_str
                if timepoint not in groups:
                    groups[timepoint] = []
                groups[timepoint].append(metrics)
            return groups
        return {"all_data": sleep_metrics_list}

    def save_comprehensive_sleep_metrics(
        self,
        sleep_metrics_list: list[SleepMetrics],
        algorithm_name: AlgorithmType = AlgorithmType.SADEH_1994_ACTILIFE,
    ) -> str | None:
        """
        Save comprehensive sleep metrics to ongoing backup file.

        This saves BOTH the main sleep_metrics table AND the sleep_markers_extended
        table to ensure data consistency between legacy single-period storage and
        multi-period extended storage.
        """
        if not sleep_metrics_list:
            return None

        # Sanitize algorithm name to prevent security issues
        safe_algorithm_name = sanitize_filename_component(algorithm_name)
        if not safe_algorithm_name:
            safe_algorithm_name = sanitize_filename_component(AlgorithmType.SADEH_1994_ACTILIFE)

        try:
            # Save to database - ATOMICALLY save to both tables in a single transaction
            for metrics in sleep_metrics_list:
                metrics.algorithm_type = algorithm_name
                # Use atomic save that writes to both sleep_metrics and sleep_markers_extended
                # in a single transaction for data consistency
                success = self.db_manager.save_sleep_metrics_atomic(metrics)
                if not success:
                    logger.warning("Failed to save metrics for %s on %s", metrics.filename, metrics.analysis_date)
                    return None

            logger.debug("Saved comprehensive sleep metrics to database for %s", sleep_metrics_list[0].filename)
            return "saved"

        except (DatabaseError, ValidationError) as e:
            logger.warning("Error saving comprehensive sleep metrics: %s", e)
            return None

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _create_backup(self, csv_path: Path) -> Path:
        """Create a backup copy with hash verification and rotation."""
        backup_dir = csv_path.parent / DirectoryName.BACKUPS
        backup_dir.mkdir(mode=0o755, exist_ok=True)

        backup_filename = get_backup_filename(csv_path.name)
        backup_path = backup_dir / backup_filename

        original_hash = self._calculate_file_hash(csv_path)

        shutil.copy2(csv_path, backup_path)

        backup_hash = self._calculate_file_hash(backup_path)
        if original_hash != backup_hash:
            backup_path.unlink()
            msg = f"Backup verification failed for {csv_path.name}"
            raise DatabaseError(msg, ErrorCodes.FILE_CORRUPTED)

        checksum_path = backup_path.with_suffix(".sha256")
        checksum_path.write_text(f"{backup_hash}  {backup_path.name}\n")

        logger.info(f"Backup verified: {backup_path}")

        backup_pattern = f"*_{csv_path.stem}_*.csv"
        existing_backups = sorted(backup_dir.glob(backup_pattern))

        if len(existing_backups) > self.max_backups:
            for old_backup in existing_backups[: -self.max_backups]:
                try:
                    old_backup.unlink()
                    checksum_file = old_backup.with_suffix(".sha256")
                    if checksum_file.exists():
                        checksum_file.unlink()
                    logger.debug(f"Deleted old backup: {old_backup.name}")
                except OSError as e:
                    logger.warning(f"Failed to delete old backup {old_backup}: {e}")

        return backup_path
