"""
Data management module for sleep scoring application.
Handles file operations, data loading, and participant information extraction.

This module now delegates to specialized services:
- DataLoadingService: File discovery and activity data loading
- MetricsCalculationService: Sleep metrics calculations
- DataQueryService: Lookups, filtering, and participant info
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import ActivityDataPreference
from sleep_scoring_app.core.exceptions import DataLoadingError, ErrorCodes, ValidationError
from sleep_scoring_app.core.validation import InputValidator
from sleep_scoring_app.data.database import DatabaseManager
from sleep_scoring_app.services.data_loading_service import DataLoadingService
from sleep_scoring_app.services.data_query_service import DataQueryService
from sleep_scoring_app.services.metrics_calculation_service import MetricsCalculationService

if TYPE_CHECKING:
    from datetime import date, datetime

    from sleep_scoring_app.core.dataclasses import AlignedActivityData, FileInfo, ParticipantInfo, SleepMetrics

logger = logging.getLogger(__name__)


class DataManager:
    """
    Handles all data loading and management operations.

    This class serves as the main interface for data operations and delegates
    to specialized services for specific functionality.
    """

    def __init__(self, database_manager: DatabaseManager | None = None) -> None:
        self.data_folder = Path.cwd()  # Default to current directory
        self.db_manager = database_manager or DatabaseManager()
        self.use_database = True  # Flag to enable database-first approach

        # Activity column preferences - will be set by service using this manager
        self.preferred_activity_column: ActivityDataPreference = ActivityDataPreference.AXIS_Y
        self.choi_activity_column: ActivityDataPreference = ActivityDataPreference.AXIS_Y

        # Initialize specialized services
        self._loading_service = DataLoadingService(self.db_manager, self.data_folder)
        self._metrics_service = MetricsCalculationService()
        self._query_service = DataQueryService(self.db_manager)

        # Current file info
        self.current_file_info = None

    def set_activity_column_preferences(
        self, preferred_activity_column: ActivityDataPreference, choi_activity_column: ActivityDataPreference
    ) -> None:
        """Set activity column preferences for data loading and algorithms."""
        self.preferred_activity_column = preferred_activity_column
        self.choi_activity_column = choi_activity_column
        logger.debug("Activity column preferences set: preferred=%s, choi=%s", preferred_activity_column, choi_activity_column)

    def set_data_folder(self, folder_path) -> None:
        """Set the folder to search for data files with validation."""
        try:
            # Validate the folder path
            self.data_folder = InputValidator.validate_directory_path(folder_path, must_exist=True, create_if_missing=False)
            # Update loading service's data folder
            self._loading_service.data_folder = self.data_folder
            logger.debug("Data folder set to: %s", self.data_folder)
        except ValidationError as e:
            msg = f"Invalid data folder: {e}"
            raise DataLoadingError(msg, ErrorCodes.INVALID_INPUT) from e

    def find_data_files(self) -> list[FileInfo]:
        """Find available data files - prioritize database imports, fallback to CSV files."""
        return self._loading_service.find_data_files()

    def load_selected_file(self, file_info: FileInfo, skip_rows: int = 10) -> list[date]:
        """Load file and extract available dates - handles both database and CSV sources."""
        return self._loading_service.load_selected_file(file_info, skip_rows)

    def load_real_data(
        self, target_date, hours, filename: str | None = None, activity_column: ActivityDataPreference | None = None
    ) -> tuple[list[datetime], list[float]] | tuple[None, None]:
        """Load real activity data with configurable activity column - prioritize database, fallback to CSV."""
        # Use preferred activity column if not specified
        if activity_column is None:
            activity_column = self.preferred_activity_column

        return self._loading_service.load_real_data(target_date, hours, filename, activity_column)

    def load_activity_data_only(
        self, filename: str, target_date: datetime, activity_column: ActivityDataPreference, hours: int = 24
    ) -> tuple[list[datetime], list[float]] | None:
        """Load only activity data for the specified column without triggering full reload cycle."""
        return self._loading_service.load_activity_data_only(filename, target_date, activity_column, hours)

    def load_axis_y_data_for_sadeh(self, filename: str, target_date: datetime, hours: int = 48) -> tuple[list[datetime], list[float]] | None:
        """Unified method to load axis_y (vertical) data specifically for Sadeh algorithm."""
        return self._loading_service.load_axis_y_data_for_sadeh(filename, target_date, hours)

    def load_axis_y_aligned(self, filename: str, target_date: datetime, hours: int = 48) -> AlignedActivityData:
        """
        Load axis_y data as an aligned immutable container.

        This is the SINGLE SOURCE OF TRUTH for axis_y loading that guarantees
        timestamps and activity values are ALWAYS aligned and cannot get out of sync.

        Delegates to DataLoadingService.load_axis_y_aligned().
        """
        return self._loading_service.load_axis_y_aligned(filename, target_date, hours)

    def filter_to_24h_view(self, timestamps_48h, activity_data_48h, target_date) -> tuple[list[datetime], list[float]]:
        """Filter 48h dataset to 24h noon-to-noon view."""
        return self._query_service.filter_to_24h_view(timestamps_48h, activity_data_48h, target_date)

    def extract_enhanced_participant_info(self, file_path: str | None = None) -> ParticipantInfo:
        """Extract comprehensive participant information using centralized extractor."""
        return self._query_service.extract_enhanced_participant_info(file_path)

    def extract_group_from_path(self, file_path) -> str | None:
        """Extract group information from file path using centralized extractor."""
        return self._query_service.extract_group_from_path(file_path)

    def calculate_sleep_metrics_for_period(
        self,
        sleep_period,
        sadeh_results,
        choi_results,
        axis_y_data,
        x_data,
        file_path=None,
        nwt_sensor_results=None,
        algorithm_type=None,
    ) -> dict[str, Any] | None:
        """Calculate sleep metrics for a specific sleep period."""
        participant_info = self.extract_enhanced_participant_info(file_path)
        return self._metrics_service.calculate_sleep_metrics_for_period(
            sleep_period,
            sadeh_results,
            choi_results,
            axis_y_data,
            x_data,
            participant_info,
            file_path,
            nwt_sensor_results,
            algorithm_type,
        )

    def calculate_sleep_metrics_for_period_object(
        self,
        sleep_period,
        sadeh_results,
        choi_results,
        axis_y_data,
        x_data,
        file_path=None,
        nwt_sensor_results=None,
        algorithm_type=None,
    ) -> SleepMetrics | None:
        """Calculate sleep metrics for a SleepPeriod and return as SleepMetrics object."""
        participant_info = self.extract_enhanced_participant_info(file_path)
        return self._metrics_service.calculate_sleep_metrics_for_period_object(
            sleep_period,
            sadeh_results,
            choi_results,
            axis_y_data,
            x_data,
            participant_info,
            file_path,
            nwt_sensor_results,
            algorithm_type,
        )

    def calculate_sleep_metrics_for_all_periods(
        self,
        daily_sleep_markers,
        sadeh_results,
        choi_results,
        axis_y_data,
        x_data,
        file_path=None,
        nwt_sensor_results=None,
        algorithm_type=None,
    ) -> list[dict[str, Any]]:
        """Calculate sleep metrics for all complete sleep periods."""
        participant_info = self.extract_enhanced_participant_info(file_path)
        return self._metrics_service.calculate_sleep_metrics_for_all_periods(
            daily_sleep_markers,
            sadeh_results,
            choi_results,
            axis_y_data,
            x_data,
            participant_info,
            file_path,
            nwt_sensor_results,
            algorithm_type,
        )

    def get_database_statistics(self) -> dict[str, Any]:
        """Get database import statistics."""
        return self._query_service.get_database_statistics()

    def is_file_imported(self, filename: str) -> bool:
        """Check if a file has been imported into the database."""
        return self._query_service.is_file_imported(filename)

    def get_participant_info_from_database(self, filename: str) -> dict[str, Any] | None:
        """Get participant info from database for imported file."""
        return self._query_service.get_participant_info_from_database(filename)

    def set_current_file_info(self, file_info: dict[str, Any]) -> None:
        """Set current file information for processing."""
        self.current_file_info = file_info
        logger.info("Set current file: %s", file_info.get("filename", "Unknown"))

    def toggle_database_mode(self, use_database: bool) -> None:
        """Toggle between database and CSV mode."""
        self.use_database = use_database
        self._loading_service.use_database = use_database
        self._query_service.use_database = use_database
        logger.info("Database mode %s", "enabled" if use_database else "disabled")

    def clear_current_data(self) -> None:
        """Clear current loaded data."""
        self._loading_service.clear_current_data()
        self.current_file_info = None
        logger.debug("Cleared current data")
