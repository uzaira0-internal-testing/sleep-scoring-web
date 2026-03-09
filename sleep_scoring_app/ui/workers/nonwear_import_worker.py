#!/usr/bin/env python3
"""
Nonwear Import Worker for Sleep Scoring Application
Provides threaded nonwear data import functionality with progress tracking.

Uses the recommended QThread + Worker Object pattern instead of subclassing QThread.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, QThread, pyqtSignal

from sleep_scoring_app.services.import_service import ImportProgress

if TYPE_CHECKING:
    from pathlib import Path

    from sleep_scoring_app.services.import_service import ImportService

logger = logging.getLogger(__name__)


class NonwearImportWorkerObject(QObject):
    """
    Worker object that performs nonwear data import operations.

    This object is moved to a QThread to perform work off the main thread.
    Uses the recommended worker-object pattern for PyQt6 threading.
    """

    progress_updated = pyqtSignal(object)  # ImportProgress
    import_completed = pyqtSignal(object)  # ImportProgress
    finished = pyqtSignal()  # Signals work is complete

    def __init__(
        self,
        import_service: ImportService,
        directory_or_files: Path | list[Path],
    ) -> None:
        super().__init__()
        self.import_service = import_service
        self.directory_or_files = directory_or_files
        self.is_cancelled = False

    def run(self) -> None:
        """Run the nonwear import operation. Called when thread starts."""
        try:
            # Create progress object
            progress = ImportProgress()

            # Progress callback emits signals for UI updates
            def progress_callback(p: ImportProgress) -> None:
                self.progress_updated.emit(p)

            # Start import - check if we have a list of files or a directory
            if isinstance(self.directory_or_files, list):
                # Import specific files
                self.import_service.import_nonwear_files(self.directory_or_files, progress, progress_callback=progress_callback)
            else:
                # Import directory (legacy behavior)
                self.import_service.import_nonwear_data(self.directory_or_files, progress, progress_callback=progress_callback)

            # Emit completion
            self.import_completed.emit(progress)

        except Exception as e:
            logger.exception("Nonwear import worker error")
            error_progress = ImportProgress()
            error_progress.add_error(f"Nonwear import failed: {e}")
            self.import_completed.emit(error_progress)
        finally:
            self.finished.emit()

    def cancel(self) -> None:
        """Request cooperative cancellation."""
        self.is_cancelled = True


class NonwearImportWorker:
    """
    Manager for threaded nonwear data import operations.

    Uses the recommended QThread + Worker Object pattern.
    The worker object is moved to a thread for execution.
    """

    def __init__(
        self,
        import_service: ImportService,
        directory_or_files: Path | list[Path],
    ) -> None:
        # Create thread and worker
        self._thread = QThread()
        self._worker = NonwearImportWorkerObject(import_service, directory_or_files)

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
    def import_completed(self) -> pyqtSignal:
        """Signal emitted when import completes."""
        return self._worker.import_completed

    def start(self) -> None:
        """Start the nonwear import operation in the background thread."""
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
