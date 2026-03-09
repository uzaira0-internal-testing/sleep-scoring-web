#!/usr/bin/env python3
"""
Import Worker for Sleep Scoring Application
Provides threaded CSV import functionality with progress tracking.

Uses the recommended QThread + Worker Object pattern instead of subclassing QThread.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from sleep_scoring_app.services.import_service import ImportProgress, ImportService

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)


class ImportWorkerObject(QObject):
    """
    Worker object that performs CSV import operations.

    This object is moved to a QThread to perform work off the main thread.
    Uses the recommended worker-object pattern for PyQt6 threading.
    """

    progress_updated = pyqtSignal(object)  # ImportProgress
    nonwear_progress_updated = pyqtSignal(object)  # ImportProgress
    import_completed = pyqtSignal(object)  # ImportProgress
    finished = pyqtSignal()  # Signals work is complete

    def __init__(
        self,
        import_service: ImportService,
        directory_or_files: Path | list[Path],
        skip_rows: int = 10,
        force_reimport: bool = False,
        include_nonwear: bool = False,
        custom_columns: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.import_service = import_service
        self.directory_or_files = directory_or_files
        self.skip_rows = skip_rows
        self.force_reimport = force_reimport
        self.include_nonwear = include_nonwear
        self.custom_columns = custom_columns
        self.is_cancelled = False

    def run(self) -> None:
        """Run the import operation. Called when thread starts."""
        try:
            # Start import - check if we have a list of files or a directory
            # Provide cancellation check callback so import can be interrupted
            def cancellation_check():
                return self.is_cancelled

            # Progress callback emits signals for UI updates
            def progress_callback(progress: ImportProgress) -> None:
                self.progress_updated.emit(progress)

            if isinstance(self.directory_or_files, list):
                # Import specific files
                result = self.import_service.import_files(
                    self.directory_or_files,
                    self.skip_rows,
                    self.force_reimport,
                    progress_callback=progress_callback,
                    custom_columns=self.custom_columns,
                    cancellation_check=cancellation_check,
                )
            else:
                # Import directory (legacy behavior)
                result = self.import_service.import_directory(
                    self.directory_or_files,
                    self.skip_rows,
                    self.force_reimport,
                    progress_callback=progress_callback,
                    include_nonwear=self.include_nonwear,
                    custom_columns=self.custom_columns,
                    cancellation_check=cancellation_check,
                )

            # Emit completion signal with result
            self.import_completed.emit(result)

        except Exception as e:
            logger.exception("Import worker error")
            error_progress = ImportProgress()
            error_progress.add_error(f"Import failed: {e}")
            self.import_completed.emit(error_progress)
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self.is_cancelled = True


class ImportWorker:
    """
    Manager for threaded CSV import operations.

    Uses the recommended QThread + Worker Object pattern.
    The worker object is moved to a thread for execution.
    """

    def __init__(
        self,
        import_service: ImportService,
        directory_or_files: Path | list[Path],
        skip_rows: int = 10,
        force_reimport: bool = False,
        include_nonwear: bool = False,
        custom_columns: dict[str, str] | None = None,
    ) -> None:
        # Create thread and worker
        self._thread = QThread()
        self._worker = ImportWorkerObject(
            import_service,
            directory_or_files,
            skip_rows,
            force_reimport,
            include_nonwear,
            custom_columns,
        )

        # Move worker to thread
        self._worker.moveToThread(self._thread)

        # Connect thread started signal to worker run method
        self._thread.started.connect(self._worker.run)

        # Clean up when worker finishes
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)

    @property
    def progress_updated(self) -> pyqtSignal:
        """Signal emitted when import progress updates."""
        return self._worker.progress_updated

    @property
    def nonwear_progress_updated(self) -> pyqtSignal:
        """Signal emitted when nonwear import progress updates."""
        return self._worker.nonwear_progress_updated

    @property
    def import_completed(self) -> pyqtSignal:
        """Signal emitted when import completes."""
        return self._worker.import_completed

    def start(self) -> None:
        """Start the import operation in the background thread."""
        self._thread.start()

    def isRunning(self) -> bool:
        """Check if the import is currently running."""
        return self._thread.isRunning()

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self._worker.cancel()
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(5000)

    def wait(self, timeout: int = -1) -> bool:
        """Wait for the thread to finish."""
        return self._thread.wait(timeout)
