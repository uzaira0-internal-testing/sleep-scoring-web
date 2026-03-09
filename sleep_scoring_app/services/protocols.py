#!/usr/bin/env python3
"""
Service Protocol Interfaces for Sleep Scoring Application.

Defines Protocol interfaces for all services to enable proper dependency
injection, testability, and loose coupling. Consumers should type hint
against these protocols rather than concrete implementations.

Usage:
    from sleep_scoring_app.services.protocols import FileDiscoveryProtocol

    def some_function(file_service: FileDiscoveryProtocol) -> None:
        files = file_service.find_available_files()
        ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import datetime
    from pathlib import Path

    from sleep_scoring_app.core.constants import ActivityDataPreference


@runtime_checkable
class FileDiscoveryProtocol(Protocol):
    """
    Protocol for file discovery operations.

    Implementations are responsible for finding, tracking, and managing
    data files within configured directories.
    """

    @property
    def available_files(self) -> list[dict[str, Any]]:
        """Get list of currently available files."""
        ...

    def find_available_files(self) -> list[dict[str, Any]]:
        """
        Find all available data files with memory bounds.

        Returns:
            List of file info dictionaries containing at minimum:
            - 'filename': str
            - 'path': str (optional)
            - 'display_name': str (optional)

        """
        ...

    def get_file_count(self) -> int:
        """Get the current number of available files."""
        ...

    def get_file_by_filename(self, filename: str) -> dict[str, Any] | None:
        """
        Get file info by filename.

        Args:
            filename: The filename to look up

        Returns:
            File info dictionary or None if not found

        """
        ...

    def clear_files(self) -> None:
        """Clear the list of available files."""
        ...


@runtime_checkable
class DataSourceConfigProtocol(Protocol):
    """
    Protocol for data source configuration.

    Implementations manage data folder configuration, database mode,
    and activity column preferences.
    """

    def set_data_folder(self, folder_path: str | Path) -> bool:  # pyright: ignore[reportReturnType]
        """
        Set data folder and validate it.

        Args:
            folder_path: Path to the data folder

        Returns:
            True if successful, False otherwise

        """
        ...

    def get_data_folder(self) -> str | None:
        """Get current data folder path."""
        ...

    def toggle_database_mode(self, use_database: bool) -> None:
        """
        Toggle between database and CSV mode.

        Args:
            use_database: True for database mode, False for CSV mode

        """
        ...

    def get_database_mode(self) -> bool:
        """Get current database mode."""
        ...

    def set_activity_column_preferences(
        self,
        preferred_activity_column: ActivityDataPreference,
        choi_activity_column: ActivityDataPreference,
    ) -> None:
        """
        Set activity column preferences for data loading.

        Args:
            preferred_activity_column: Preferred column for general activity
            choi_activity_column: Column to use for Choi nonwear algorithm

        """
        ...

    def get_activity_column_preferences(self) -> tuple[str, str]:
        """
        Get current activity column preferences.

        Returns:
            Tuple of (preferred_activity_column, choi_activity_column)

        """
        ...


@runtime_checkable
class MarkerCacheProtocol(Protocol):
    """
    Protocol for marker-related caching operations.

    Implementations manage caching of marker status, date ranges,
    and main data to improve performance.
    """

    def get_marker_status(self, filename: str) -> tuple[int, int] | None:
        """
        Get cached marker completion status for a file.

        Args:
            filename: The filename to look up

        Returns:
            Tuple of (completed_count, total_count) or None if not cached

        """
        ...

    def set_marker_status(self, filename: str, completed: int, total: int) -> None:
        """
        Cache marker completion status for a file.

        Args:
            filename: The filename to cache
            completed: Number of completed markers
            total: Total number of dates

        """
        ...

    def get_date_range(self, filename: str) -> tuple[str, str] | None:
        """
        Get cached date range for a file.

        Args:
            filename: The filename to look up

        Returns:
            Tuple of (start_date, end_date) or None if not cached

        """
        ...

    def set_date_range(self, filename: str, start_date: str, end_date: str) -> None:
        """
        Cache date range for a file.

        Args:
            filename: The filename to cache
            start_date: Start date string
            end_date: End date string

        """
        ...

    def invalidate_marker_status(self, filename: str | None = None) -> None:
        """
        Invalidate marker status cache.

        Args:
            filename: Specific file to invalidate, or None to clear all

        """
        ...

    def invalidate_date_ranges(self) -> None:
        """Invalidate all date range cache entries."""
        ...

    def invalidate_all(self) -> None:
        """Invalidate all caches."""
        ...


@runtime_checkable
class DiaryServiceProtocol(Protocol):
    """
    Protocol for diary data operations.

    Implementations manage loading and accessing sleep diary data
    for participants.
    """

    def load_diary_data_for_file(self, filename: str) -> list[dict[str, Any]]:
        """
        Load diary data for a specific file.

        Args:
            filename: The filename to load diary data for

        Returns:
            List of diary entry dictionaries

        """
        ...

    def get_diary_data_for_date(self, filename: str, target_date: datetime) -> dict[str, Any] | None:
        """
        Get diary data for a specific date.

        Args:
            filename: The filename
            target_date: The date to look up

        Returns:
            Diary entry dictionary or None if not found

        """
        ...

    def has_diary_data(self, filename: str) -> bool:
        """
        Check if diary data exists for a file.

        Args:
            filename: The filename to check

        Returns:
            True if diary data exists

        """
        ...


@runtime_checkable
class ExportServiceProtocol(Protocol):
    """
    Protocol for export operations.

    Implementations handle exporting sleep data to various formats.
    """

    def export_sleep_data(
        self,
        sleep_metrics_list: list[Any],
        output_path: str | Path,
        format_type: str = "csv",
    ) -> bool:
        """
        Export sleep metrics to file.

        Args:
            sleep_metrics_list: List of SleepMetrics to export
            output_path: Output file path
            format_type: Export format (default: 'csv')

        Returns:
            True if successful

        """
        ...


@runtime_checkable
class NonwearServiceProtocol(Protocol):
    """
    Protocol for nonwear data operations.

    Implementations manage loading and accessing nonwear detection data.
    """

    def get_nonwear_periods_for_file(
        self,
        filename: str,
        source: Any,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[Any]:
        """
        Get nonwear periods for a file.

        Args:
            filename: The filename to query
            source: The nonwear data source
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            List of nonwear period objects

        """
        ...

    def has_nonwear_data(self, filename: str, source: Any) -> bool:
        """
        Check if nonwear data exists for a file and source.

        Args:
            filename: The filename
            source: The nonwear data source

        Returns:
            True if nonwear data exists

        """
        ...


@runtime_checkable
class AlgorithmServiceProtocol(Protocol):
    """
    Protocol for algorithm service operations.

    Provides access to sleep scoring algorithms without exposing
    the underlying factory implementations.
    """

    # Sleep/Wake Algorithms
    def get_available_sleep_algorithms(self) -> dict[str, str]:
        """Get available sleep/wake algorithms as id->display_name dict."""
        ...

    def create_sleep_algorithm(self, algorithm_id: str, config: Any | None = None) -> Any:
        """Create a sleep/wake algorithm instance."""
        ...

    def get_default_sleep_algorithm_id(self) -> str:
        """Get the default sleep/wake algorithm ID."""
        ...

    # Nonwear Algorithms
    def get_available_nonwear_algorithms(self) -> dict[str, str]:
        """Get available nonwear detection algorithms as id->display_name dict."""
        ...

    def get_nonwear_algorithms_for_paradigm(self, paradigm: str) -> dict[str, str]:
        """Get nonwear algorithms compatible with a specific paradigm."""
        ...

    def create_nonwear_algorithm(self, algorithm_id: str, config: Any | None = None) -> Any:
        """Create a nonwear detection algorithm instance."""
        ...

    def get_default_nonwear_algorithm_id(self) -> str:
        """Get the default nonwear algorithm ID."""
        ...

    # Sleep Period Detectors
    def get_available_sleep_period_detectors(self) -> dict[str, str]:
        """Get available sleep period detectors as id->display_name dict."""
        ...

    def get_sleep_period_detectors_for_paradigm(self, paradigm: str) -> dict[str, str]:
        """Get sleep period detectors compatible with a specific paradigm."""
        ...

    def create_sleep_period_detector(self, detector_id: str) -> Any:
        """Create a sleep period detector instance."""
        ...

    def get_default_sleep_period_detector_id(self) -> str:
        """Get the default sleep period detector ID."""
        ...

    # Algorithm Information
    def is_algorithm_available(self, algorithm_id: str) -> bool:
        """Check if an algorithm is available."""
        ...


@runtime_checkable
class ProgressCallback(Protocol):
    """
    Protocol for progress tracking callbacks.

    Used throughout the application for reporting progress during
    long-running operations like batch processing or file imports.

    Usage:
        def my_operation(progress_callback: ProgressCallback) -> None:
            progress_callback("Starting...", 0, 100)
            # ... do work ...
            progress_callback("Processing...", 50, 100)
            # ... do more work ...
            progress_callback("Complete", 100, 100)
    """

    def __call__(self, status: str, current: int, total: int) -> None:
        """
        Report progress status.

        Args:
            status: Human-readable status message
            current: Current progress value
            total: Total progress value (for percentage calculation)

        """
        ...


@runtime_checkable
class FileInfo(Protocol):
    """
    Protocol for file information objects.

    Represents metadata about a data file, whether it comes from
    the database or filesystem. This protocol allows both dict-based
    and object-based implementations.

    Usage:
        def process_file(file_info: FileInfo) -> None:
            print(f"Processing {file_info.filename}")
            if file_info.participant_id:
                print(f"  Participant: {file_info.participant_id}")
    """

    @property
    def filename(self) -> str:
        """Get the base filename."""
        ...

    @property
    def path(self) -> str | None:
        """Get the full file path (None for database files)."""
        ...

    @property
    def display_name(self) -> str:
        """Get the display name for UI presentation."""
        ...

    @property
    def source(self) -> str:
        """Get the data source ('database' or 'filesystem')."""
        ...

    @property
    def participant_id(self) -> str | None:
        """Get the participant ID if available."""
        ...


@runtime_checkable
class CompatibilityHelper(Protocol):
    """
    Protocol for algorithm compatibility checking.

    Implementations verify whether the current data and configuration
    are compatible with a specific algorithm or detector.

    Usage:
        if not helper.check_compatibility("sadeh"):
            print("Sadeh algorithm not compatible with current data")
    """

    def check_compatibility(self, algorithm_name: str | None = None) -> tuple[bool, str]:
        """
        Check if the current data is compatible with an algorithm.

        Args:
            algorithm_name: Name of the algorithm to check, or None
                           to check general compatibility

        Returns:
            Tuple of (is_compatible, error_message)
            If compatible, error_message will be empty string

        """
        ...


@runtime_checkable
class AlgorithmCache(Protocol):
    """
    Protocol for algorithm result caching.

    Implementations provide caching for expensive algorithm computations
    to avoid redundant processing when parameters haven't changed.

    Usage:
        # Check if results are cached
        if "sadeh_results" not in cache._algorithm_cache:
            # ... compute results ...
            cache._algorithm_cache["sadeh_results"] = results

        # Invalidate when data changes
        cache.invalidate_algorithm_cache()
    """

    @property
    def _algorithm_cache(self) -> dict[str, Any]:
        """
        Get the algorithm cache dictionary.

        Returns:
            Dictionary mapping cache keys to cached results

        """
        ...

    def invalidate_algorithm_cache(self) -> None:
        """
        Invalidate all algorithm cache entries.

        Should be called when underlying data changes or algorithm
        parameters are modified.
        """
        ...


__all__ = [
    # Helper protocols
    "AlgorithmCache",
    # Core service protocols
    "AlgorithmServiceProtocol",
    "CompatibilityHelper",
    "DataSourceConfigProtocol",
    "DiaryServiceProtocol",
    "ExportServiceProtocol",
    "FileDiscoveryProtocol",
    "FileInfo",
    "MarkerCacheProtocol",
    "NonwearServiceProtocol",
    "ProgressCallback",
]
