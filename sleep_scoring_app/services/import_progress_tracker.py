#!/usr/bin/env python3
"""
Import Progress Tracker for Sleep Scoring Application
Tracks progress for import operations with file and record counts.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ImportProgress:
    """Progress tracking for import operations."""

    def __init__(self, total_files: int = 0, total_records: int = 0) -> None:
        self.total_files = total_files
        self.processed_files = 0
        self.total_records = total_records
        self.processed_records = 0
        self.current_file = ""
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.skipped_files: list[str] = []
        self.imported_files: list[str] = []
        self.info_messages: list[str] = []

        # Separate tracking for nonwear data
        self.total_nonwear_files = 0
        self.processed_nonwear_files = 0
        self.current_nonwear_file = ""
        self.imported_nonwear_files: list[str] = []

    def add_info(self, message: str) -> None:
        """Add an informational message to the progress."""
        self.info_messages.append(message)

    @property
    def file_progress_percent(self) -> float:
        """Calculate file progress percentage."""
        try:
            if self.total_files == 0:
                return 0.0
            return (self.processed_files / self.total_files) * 100
        except (TypeError, AttributeError):
            # Handle mock objects during testing
            return 0.0

    @property
    def record_progress_percent(self) -> float:
        """Calculate record progress percentage."""
        try:
            if self.total_records == 0:
                return 0.0
            return (self.processed_records / self.total_records) * 100
        except (TypeError, AttributeError):
            # Handle mock objects during testing
            return 0.0

    @property
    def nonwear_progress_percent(self) -> float:
        """Calculate nonwear file progress percentage."""
        try:
            if self.total_nonwear_files == 0:
                return 0.0
            return (self.processed_nonwear_files / self.total_nonwear_files) * 100
        except (TypeError, AttributeError):
            # Handle mock objects during testing
            return 0.0

    @property
    def is_complete(self) -> bool:
        """Check if import is complete."""
        return self.processed_files >= self.total_files

    def add_error(self, error: str) -> None:
        """
        Add an error message to the progress.

        Args:
            error: Error message to add

        """
        self.errors.append(error)
        logger.error(error)

    def add_warning(self, warning: str) -> None:
        """
        Add a warning message to the progress.

        Args:
            warning: Warning message to add

        """
        self.warnings.append(warning)
        logger.warning(warning)

    def get_summary(self) -> dict[str, int | list[str]]:
        """
        Get a summary of import progress.

        Returns:
            Dictionary with progress statistics

        """
        return {
            "total_files": self.total_files,
            "processed_files": self.processed_files,
            "imported_files_count": len(self.imported_files),
            "skipped_files_count": len(self.skipped_files),
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "imported_files": self.imported_files,
            "skipped_files": self.skipped_files,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class ImportProgressTracker:
    """Wrapper for ImportProgress with convenient tracking methods."""

    def __init__(self, total_files: int = 0, total_records: int = 0) -> None:
        self.progress = ImportProgress(total_files, total_records)

    def file_started(self, filename: str) -> None:
        """Mark that processing of a file has started."""
        self.progress.current_file = filename
        logger.info("Starting import of file: %s", filename)

    def file_completed(self, filename: str, success: bool) -> None:
        """
        Mark that processing of a file has completed.

        Args:
            filename: Name of file that was processed
            success: Whether processing was successful

        """
        if success:
            self.progress.imported_files.append(filename)
            logger.info("Successfully completed import of file: %s", filename)
        else:
            logger.error("Failed to import file: %s", filename)

        self.progress.processed_files += 1

    def file_skipped(self, filename: str, reason: str) -> None:
        """
        Mark that a file was skipped.

        Args:
            filename: Name of file that was skipped
            reason: Reason for skipping

        """
        skip_message = f"{filename}: {reason}"
        self.progress.skipped_files.append(skip_message)
        logger.info("Skipping %s: %s", filename, reason)

    def add_error(self, message: str) -> None:
        """Add an error message."""
        self.progress.add_error(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.progress.add_warning(message)

    def add_info(self, message: str) -> None:
        """Add an informational message."""
        self.progress.add_info(message)

    def update_record_progress(self, records_processed: int) -> None:
        """Update the number of records processed."""
        self.progress.processed_records += records_processed

    def get_progress(self) -> ImportProgress:
        """Get the current progress object."""
        return self.progress
