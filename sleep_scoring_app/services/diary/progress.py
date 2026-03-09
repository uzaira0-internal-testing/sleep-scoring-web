"""Progress tracking for diary import operations."""

from __future__ import annotations


class DiaryImportProgress:
    """Progress tracking for diary import operations."""

    def __init__(self, total_files: int = 0, total_sheets: int = 0) -> None:
        self.total_files = total_files
        self.total_sheets = total_sheets
        self.processed_files = 0
        self.processed_sheets = 0
        self.current_file = ""
        self.current_sheet = ""
        self.current_operation = ""
        self.entries_imported = 0

    @property
    def file_progress_percent(self) -> float:
        """Calculate file progress percentage."""
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100

    @property
    def sheet_progress_percent(self) -> float:
        """Calculate sheet progress percentage."""
        if self.total_sheets == 0:
            return 0.0
        return (self.processed_sheets / self.total_sheets) * 100

    def get_status_text(self) -> str:
        """Get current status as readable text."""
        if self.current_operation == "loading":
            return f"Loading {self.current_file} - {self.current_sheet}"
        if self.current_operation == "importing":
            return f"Importing {self.current_file} - {self.current_sheet}"
        if self.current_operation == "processing":
            return f"Processing {self.current_file}"
        return f"Processing file {self.processed_files + 1} of {self.total_files}"
