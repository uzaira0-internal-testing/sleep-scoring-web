#!/usr/bin/env python3
"""
Unified Data Service for Sleep Scoring Application.
Pure data service facade that delegates to focused sub-services.
NO UI references allowed - this service is headless.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import ActivityDataPreference
from sleep_scoring_app.services.cache_service import CacheService
from sleep_scoring_app.services.diary_service import DiaryService
from sleep_scoring_app.services.file_service import FileService
from sleep_scoring_app.utils.participant_extractor import extract_participant_info

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import date, datetime

    from sleep_scoring_app.core.dataclasses import FileInfo
    from sleep_scoring_app.data.database import DatabaseManager
    from sleep_scoring_app.services.memory_service import BoundedCache

logger = logging.getLogger(__name__)


class UnifiedDataService:
    """
    Unified service facade that delegates to focused sub-services.

    This service is HEADLESS - it has no UI dependencies and does not import
    from ui.store. All state that was previously read from the store must now
    be passed as explicit parameters to methods.
    """

    _instance: UnifiedDataService | None = None

    def __init__(self, db_manager: DatabaseManager) -> None:
        """Initialize UnifiedDataService with database manager only."""
        self.db_manager = db_manager

        # Initialize core sub-services (all headless - no store dependency)
        self._file_service = FileService(db_manager)
        self._diary_service = DiaryService(db_manager)

        # Initialize cache service (depends on file service)
        self._cache_service = CacheService(
            db_manager,
            self._file_service,
        )

        self._data_manager = self._file_service.data_manager

        # Set singleton instance
        UnifiedDataService._instance = self

    # === Pure Data Operations ===

    def load_current_date(
        self,
        current_date_48h_cache: BoundedCache,
        available_dates_iso: list[str],
        current_date_index: int,
        selected_file: str,
    ) -> tuple | None:
        """
        Load data for the current date.

        Args:
            current_date_48h_cache: Cache for 48h data
            available_dates_iso: List of ISO date strings (required)
            current_date_index: Index into available_dates (required)
            selected_file: Filename (required)

        Returns: (timestamps, activity_data) or None.

        """
        if not available_dates_iso or not selected_file:
            return None

        from datetime import date

        available_dates = [date.fromisoformat(d) for d in available_dates_iso]

        return self._file_service.load_current_date_core(available_dates, current_date_index, current_date_48h_cache, selected_file)

    def load_selected_file(self, file_info: FileInfo, skip_rows: int = 10) -> list[date]:
        """Load a selected file and return available dates."""
        return self._data_manager.load_selected_file(file_info, skip_rows)

    def load_unified_activity_data(self, filename: str, target_date: date, hours: int = 48) -> dict[str, list] | None:
        """
        Load ALL activity columns in ONE query with unified timestamps.

        This is the PUBLIC API for connectors to load activity data.
        Delegates to the internal loading service.

        Args:
            filename: Name of file to load (filename only, not full path)
            target_date: Target date for data loading
            hours: Number of hours to load (default 48)

        Returns:
            Dictionary with keys: 'timestamps', 'axis_y', 'axis_x', 'axis_z', 'vector_magnitude'
            All lists have the SAME length (guaranteed).
            Returns None if loading fails.

        """
        loading_service = self._data_manager._loading_service
        return loading_service.load_unified_activity_data(filename, target_date, hours)

    def find_available_files(self) -> list[FileInfo]:
        """Find all available data files."""
        return self._file_service.find_available_files()

    def find_available_files_with_completion_count(self) -> list[FileInfo]:
        """Find available files and include completion counts."""
        return self._file_service.find_available_files_with_completion_count()

    def delete_files(self, filenames: list[str]) -> Any:
        """Delete files via the file service."""
        return self._file_service.delete_files(filenames)

    def load_available_files(
        self,
        load_completion_counts: bool = False,
        on_files_loaded: Callable[[list[FileInfo]], None] | None = None,
    ) -> list[FileInfo]:
        """
        Load available files.

        Args:
            load_completion_counts: Whether to include completion counts
            on_files_loaded: Optional callback to receive loaded files.
                           Callers should use this to dispatch to store.

        Returns:
            List of loaded FileInfo objects

        """
        if load_completion_counts:
            files = self.find_available_files_with_completion_count()
        else:
            files = self.find_available_files()

        # Call the callback if provided - caller is responsible for store dispatch
        if on_files_loaded is not None:
            on_files_loaded(files)

        return files

    def toggle_database_mode(self, use_database: bool) -> None:
        """Toggle between database and CSV mode."""
        self._file_service.toggle_database_mode(use_database)
        self._cache_service.clear_all_caches_on_mode_change()

    def get_database_mode(self) -> bool:
        """Get current database mode."""
        return self._file_service.get_database_mode()

    def clear_file_cache(self, filename: str) -> None:
        """Clear all cached data for a specific file."""
        self._cache_service.clear_file_cache(filename)

    def set_data_folder(self, folder_path: str | Path) -> bool:  # pyright: ignore[reportReturnType]
        """Set data folder and validate it."""
        return self._file_service.set_data_folder(folder_path)

    def get_data_folder(self) -> Path | None:
        """Get current data folder."""
        return self._file_service.get_data_folder()

    def get_activity_column_preferences(self) -> tuple[str, str]:
        """Get current activity column preferences."""
        return (self._data_manager.preferred_activity_column, self._data_manager.choi_activity_column)

    def get_available_activity_columns(self, filename: str) -> list:
        """Check which activity columns have data for the specified file."""
        return self.db_manager.get_available_activity_columns(filename)

    def load_raw_activity_data(
        self,
        filename: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        activity_column: ActivityDataPreference = ActivityDataPreference.VECTOR_MAGNITUDE,
    ) -> tuple[list, list]:
        """Load raw activity data for visualization."""
        return self.db_manager.load_raw_activity_data(filename, start_time, end_time, activity_column)

    def load_activity_data_only(
        self,
        filename: str,
        target_date: datetime,
        activity_column: ActivityDataPreference,
        hours: int = 24,
    ) -> tuple[list[datetime], list[float]] | None:
        """Load only activity data for the specified column without triggering full reload cycle."""
        return self._data_manager.load_activity_data_only(filename, target_date, activity_column, hours)

    def load_real_data(
        self,
        target_date: datetime,
        hours: int,
        filename: str | None = None,
        activity_column: ActivityDataPreference | None = None,
    ) -> tuple[list[datetime], list[float]] | tuple[None, None]:
        """Load activity data with DB-first, CSV-fallback strategy."""
        return self._data_manager.load_real_data(target_date, hours, filename, activity_column)

    def clear_nonwear_cache(self) -> None:
        """Clear the nonwear data factory cache."""
        self._file_service.nonwear_data_factory.clear_cache()

    def invalidate_marker_status_cache(self, filename: str | None = None) -> None:
        """Invalidate marker status cache."""
        self._cache_service.invalidate_marker_status_cache(filename)

    def clear_algorithm_caches(self) -> None:
        """Clear all algorithm-related caches."""
        self._cache_service.clear_all_algorithm_caches()

    # === Diary Data Operations ===

    def check_current_participant_has_diary_data(self, selected_file: str) -> bool:
        """
        Check if current participant has diary data.

        Args:
            selected_file: Filename (required)

        """
        if not selected_file:
            return False

        filename = Path(selected_file).name
        participant_info = extract_participant_info(filename)
        participant_id = participant_info.full_id if participant_info.numerical_id != "UNKNOWN" else None

        if not participant_id:
            return False

        return self._diary_service.check_participant_has_diary_data(participant_id)

    def load_diary_data_for_current_file(self, selected_file: str) -> list:
        """
        Load diary data for currently selected file.

        Args:
            selected_file: Filename (required)

        """
        if not selected_file:
            return []

        filename = Path(selected_file).name
        participant_info = extract_participant_info(filename)
        participant_id = participant_info.full_id if participant_info.numerical_id != "UNKNOWN" else None

        if not participant_id:
            return []

        return self._diary_service.get_diary_data_for_participant(participant_id)

    @property
    def diary_service(self) -> DiaryService:
        """Get diary service."""
        return self._diary_service

    @classmethod
    def get_instance(cls) -> UnifiedDataService | None:
        """Get the singleton instance."""
        return cls._instance
