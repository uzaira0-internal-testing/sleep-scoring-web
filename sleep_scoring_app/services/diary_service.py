"""
Unified Diary Service for Sleep Scoring Application.

This is a facade that delegates to focused service components:
- DiaryQueryService: Query operations for diary data
- DiaryImportOrchestrator: Import operations for diary files
- DiaryDataExtractor: Field extraction utilities
"""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.validation import InputValidator
from sleep_scoring_app.services.diary.import_orchestrator import DiaryImportOrchestrator
from sleep_scoring_app.services.diary.query_service import DiaryQueryService

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime
    from pathlib import Path

    from sleep_scoring_app.core.dataclasses import (
        DiaryColumnMapping,
        DiaryEntry,
        DiaryImportResult,
        ParticipantInfo,
    )
    from sleep_scoring_app.data.database import DatabaseManager

logger = logging.getLogger(__name__)


class DiaryService:
    """
    Unified service for managing diary data import and retrieval.

    This is a facade that coordinates between focused service components
    for query operations and import orchestration.

    NOTE: This is a headless service. For Qt signal-based progress tracking,
    wrap this service with a Qt adapter in the ui/ layer.
    """

    def __init__(self, database_manager: DatabaseManager, config_path: Path | None = None) -> None:
        self.db_manager = database_manager
        self.validator = InputValidator()

        # Initialize delegate services
        self._query_service = DiaryQueryService(database_manager)
        self._import_orchestrator = DiaryImportOrchestrator(database_manager)

        self._column_mapping: DiaryColumnMapping | None = None

    def get_diary_data_for_participant(
        self,
        participant_id: str,
        date_range: tuple[datetime, datetime] | None = None,
    ) -> list[DiaryEntry]:
        """Get diary data for a specific participant using PARTICIPANT_KEY for matching."""
        return self._query_service.get_diary_data_for_participant(participant_id, date_range)

    def get_diary_data_for_date(
        self,
        participant_id: str,
        target_date: datetime,
    ) -> DiaryEntry | None:
        """Get diary data for a specific participant and date using PARTICIPANT_KEY."""
        return self._query_service.get_diary_data_for_date(participant_id, target_date)

    def get_available_participants(self) -> list[str]:
        """Get list of participants with diary data."""
        return self._query_service.get_available_participants()

    def get_diary_stats(self) -> dict[str, Any]:
        """Get diary data statistics."""
        return self._query_service.get_diary_stats()

    def check_participant_has_diary_data(self, participant_id: str) -> bool:
        """Check if participant has any diary data using PARTICIPANT_KEY."""
        return self._query_service.check_participant_has_diary_data(participant_id)

    def import_diary_files(
        self,
        file_paths: list[Path],
        progress_callback: Callable[[str, int, int], None] | None = None,
    ) -> DiaryImportResult:
        """Import multiple diary files using configuration-based column mapping."""
        try:
            return self._import_orchestrator.import_diary_files(file_paths, progress_callback)

        except Exception as e:
            logger.exception(f"Diary import failed: {e}")
            raise

    def load_column_mapping(self) -> DiaryColumnMapping:
        """Load column mapping from embedded configuration."""
        return self._import_orchestrator._load_column_mapping()

    def extract_participant_id_from_filename(self, filename: str) -> str | None:
        """Extract full participant identifier from filename."""
        from sleep_scoring_app.utils.participant_extractor import (
            extract_participant_info,
        )

        info = extract_participant_info(filename)
        return info.full_id if info.numerical_id != "UNKNOWN" else None

    def extract_participant_info_from_filename(self, filename: str) -> ParticipantInfo | None:
        """Extract full participant info from filename."""
        from sleep_scoring_app.utils.participant_extractor import (
            extract_participant_info,
        )

        try:
            return extract_participant_info(filename)
        except Exception as e:
            logger.exception(f"Failed to extract participant info from filename {filename}: {e}")
            return None

    def calculate_file_hash(self, file_path: Path) -> str:
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
