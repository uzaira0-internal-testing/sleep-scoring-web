"""
Automatic file watcher service.

Monitors the data directory for new CSV files and automatically ingests them
into the database. Runs as a background task on application startup.

Features:
- Automatic ingestion on startup (scans for existing files)
- Real-time file watching using watchdog
- Duplicate detection (skips files already in database)
- Non-blocking async ingestion
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from sleep_scoring_web.config import settings

if TYPE_CHECKING:
    from watchdog.observers.api import BaseObserver

logger = logging.getLogger(__name__)


@dataclass
class WatcherStatus:
    """Track file watcher status."""

    is_running: bool = False
    total_ingested: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    last_scan_time: datetime | None = None
    watched_directory: str = ""
    pending_files: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# Global watcher status
_watcher_status = WatcherStatus()
_watcher_observer: BaseObserver | None = None
_ingestion_queue: asyncio.Queue[Path] = asyncio.Queue()
_ingestion_task: asyncio.Task | None = None
_background_scan_task: asyncio.Task | None = None


class CSVFileHandler(FileSystemEventHandler):
    """
    Handle file system events for CSV files.

    Only processes .csv files, ignores other file types.
    Queues new files for async ingestion.
    """

    def __init__(self, queue: asyncio.Queue[Path], loop: asyncio.AbstractEventLoop) -> None:
        self.queue = queue
        self.loop = loop
        super().__init__()

    @staticmethod
    def _normalize_path(value: str | bytes | Any) -> Path:
        """Normalize watchdog path values to a text Path."""
        if isinstance(value, bytes):
            return Path(value.decode("utf-8", errors="replace"))
        return Path(str(value))

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle new file creation."""
        if event.is_directory:
            return

        path = self._normalize_path(event.src_path)
        if path.suffix.lower() == ".csv":
            logger.info(f"New CSV file detected: {path.name}")
            # Schedule async queue put from sync context
            self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._queue_file(path)))

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file moved into watched directory."""
        if event.is_directory:
            return

        # dest_path is the new location
        if hasattr(event, "dest_path"):
            path = self._normalize_path(event.dest_path)
            if path.suffix.lower() == ".csv":
                logger.info(f"CSV file moved in: {path.name}")
                self.loop.call_soon_threadsafe(lambda: asyncio.create_task(self._queue_file(path)))

    async def _queue_file(self, path: Path) -> None:
        """Add file to ingestion queue."""
        await self.queue.put(path)
        _watcher_status.pending_files.append(path.name)


async def _check_file_exists_in_db(filename: str) -> bool:
    """Check if a file already exists in the database."""
    from sqlalchemy import select

    from sleep_scoring_web.db.models import File as FileModel
    from sleep_scoring_web.db.session import async_session_maker

    async with async_session_maker() as db:
        result = await db.execute(select(FileModel.id).where(FileModel.filename == filename))
        return result.scalar_one_or_none() is not None


async def _ingest_file(file_path: Path) -> bool:
    """
    Ingest a single file into the database.

    Returns True if ingested, False if skipped or failed.
    """
    from sleep_scoring_web.api.files import import_file_from_disk_async
    from sleep_scoring_web.db.session import async_session_maker

    filename = file_path.name

    # Remove from pending
    if filename in _watcher_status.pending_files:
        _watcher_status.pending_files.remove(filename)

    # Check if already exists
    if await _check_file_exists_in_db(filename):
        logger.debug(f"Skipping duplicate file: {filename}")
        _watcher_status.total_skipped += 1
        return False

    # Ingest the file
    try:
        async with async_session_maker() as db:
            # Use "system" username for automatic ingestion
            result = await import_file_from_disk_async(file_path, db, username="system")
            if result:
                logger.info(f"Auto-ingested: {filename} ({result.row_count} rows)")
                _watcher_status.total_ingested += 1
                return True
            _watcher_status.total_skipped += 1
            return False
    except Exception as e:
        logger.exception(f"Failed to ingest {filename}: {e}")
        _watcher_status.total_failed += 1
        _watcher_status.errors.append(f"{filename}: {e!s}")
        # Keep only last 10 errors
        _watcher_status.errors = _watcher_status.errors[-10:]
        return False


async def _ingestion_worker() -> None:
    """
    Background worker that processes the ingestion queue.

    Runs continuously, waiting for files to be added to the queue.
    """
    logger.info("File ingestion worker started")

    while True:
        try:
            # Wait for a file to be queued
            file_path = await _ingestion_queue.get()

            # Small delay to ensure file is fully written
            await asyncio.sleep(0.5)

            # Check if file still exists (might have been moved/deleted)
            if file_path.exists():
                await _ingest_file(file_path)
            else:
                logger.warning(f"File no longer exists: {file_path}")

            _ingestion_queue.task_done()

        except asyncio.CancelledError:
            logger.info("File ingestion worker stopped")
            break
        except Exception as e:
            logger.exception(f"Ingestion worker error: {e}")
            await asyncio.sleep(1)  # Prevent tight loop on errors


async def _scan_existing_files_background() -> None:
    """
    Background task to scan and ingest existing files.

    This runs after startup to avoid blocking the server.
    """
    # Small delay to ensure server is fully started
    await asyncio.sleep(1)

    try:
        ingested = await scan_existing_files()
        logger.info(f"Background scan complete: {ingested} files ingested")
    except Exception as e:
        logger.exception(f"Background scan failed: {e}")


async def scan_existing_files() -> int:
    """
    Scan data directory for existing files and ingest any not in database.

    Returns the number of files ingested.
    """
    data_path = Path(settings.data_dir)
    if not data_path.exists():
        logger.warning(f"Data directory does not exist: {data_path}")
        return 0

    csv_files = list(data_path.glob("*.csv")) + list(data_path.glob("*.CSV"))
    logger.info(f"Found {len(csv_files)} CSV files in {data_path}")

    ingested = 0
    for file_path in csv_files:
        if await _ingest_file(file_path):
            ingested += 1

    _watcher_status.last_scan_time = datetime.now()
    return ingested


async def start_file_watcher() -> None:
    """
    Start the file watcher service.

    This should be called during application startup (lifespan).
    It will:
    1. Scan for existing files and ingest any new ones
    2. Start watching for new files
    3. Start the background ingestion worker
    """
    global _watcher_observer, _ingestion_task, _background_scan_task

    data_path = Path(settings.data_dir)
    data_path.mkdir(parents=True, exist_ok=True)

    _watcher_status.is_running = True
    _watcher_status.watched_directory = str(data_path.absolute())

    logger.info(f"Starting file watcher for: {data_path}")

    # Start ingestion worker
    _ingestion_task = asyncio.create_task(_ingestion_worker())

    # Queue existing files for background ingestion (non-blocking)
    # This allows the server to start accepting requests immediately
    _background_scan_task = asyncio.create_task(_scan_existing_files_background())

    # Set up file system watcher
    loop = asyncio.get_running_loop()
    event_handler = CSVFileHandler(_ingestion_queue, loop)

    _watcher_observer = Observer()
    _watcher_observer.schedule(event_handler, str(data_path), recursive=False)
    _watcher_observer.start()

    logger.info(f"File watcher active on: {data_path}")


async def stop_file_watcher() -> None:
    """
    Stop the file watcher service.

    This should be called during application shutdown.
    """
    global _watcher_observer, _ingestion_task

    logger.info("Stopping file watcher...")

    _watcher_status.is_running = False

    # Stop the observer
    if _watcher_observer:
        _watcher_observer.stop()
        _watcher_observer.join(timeout=5)
        _watcher_observer = None

    # Cancel ingestion task
    if _ingestion_task:
        _ingestion_task.cancel()
        try:
            await _ingestion_task
        except asyncio.CancelledError:
            pass
        _ingestion_task = None

    logger.info("File watcher stopped")


def get_watcher_status() -> dict:
    """Get current watcher status as a dict."""
    return {
        "is_running": _watcher_status.is_running,
        "watched_directory": _watcher_status.watched_directory,
        "total_ingested": _watcher_status.total_ingested,
        "total_skipped": _watcher_status.total_skipped,
        "total_failed": _watcher_status.total_failed,
        "pending_files": _watcher_status.pending_files[:10],
        "last_scan_time": (_watcher_status.last_scan_time.isoformat() if _watcher_status.last_scan_time else None),
        "recent_errors": _watcher_status.errors[-5:],
    }
