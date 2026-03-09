"""
Data query service for lookups, filtering, and utility operations.
Handles participant info extraction, time filtering, and database queries.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.exceptions import DatabaseError, ValidationError
from sleep_scoring_app.utils.date_range import get_24h_range

if TYPE_CHECKING:
    from datetime import datetime

    from sleep_scoring_app.core.dataclasses import ParticipantInfo
    from sleep_scoring_app.data.database import DatabaseManager

logger = logging.getLogger(__name__)


class DataQueryService:
    """Handles data lookups, filtering, and participant information extraction."""

    def __init__(self, database_manager: DatabaseManager) -> None:
        self.db_manager = database_manager
        self.use_database = True

    def filter_to_24h_view(self, timestamps_48h, activity_data_48h, target_date) -> tuple[list[datetime], list[float]]:
        """Filter 48h dataset to 24h noon-to-noon view."""
        # Get date range using centralized utility
        date_range = get_24h_range(target_date)
        start_time = date_range.start
        end_time = date_range.end

        filtered_timestamps = []
        filtered_activity = []

        for i, ts in enumerate(timestamps_48h):
            if start_time <= ts <= end_time and i < len(activity_data_48h):
                filtered_timestamps.append(ts)
                filtered_activity.append(activity_data_48h[i])

        return filtered_timestamps, filtered_activity

    def extract_enhanced_participant_info(self, file_path: str | None = None) -> ParticipantInfo:
        """Extract comprehensive participant information using centralized extractor."""
        from sleep_scoring_app.utils.participant_extractor import extract_participant_info

        return extract_participant_info(file_path or "")

    def extract_group_from_path(self, file_path) -> str | None:
        """Extract group information from file path using centralized extractor."""
        from sleep_scoring_app.utils.participant_extractor import extract_participant_info

        if not file_path:
            return None
        info = extract_participant_info(file_path)
        return info.group_str if info.group_str != "G1" else None

    def get_database_statistics(self) -> dict[str, Any]:
        """Get database import statistics."""
        if self.use_database:
            return self.db_manager.get_import_statistics()
        return {
            "total_files": 0,
            "imported_files": 0,
            "total_activity_records": 0,
        }

    def is_file_imported(self, filename: str) -> bool:
        """Check if a file has been imported into the database."""
        if not self.use_database:
            return False

        try:
            files = self.db_manager.get_available_files()
            return any(f["filename"] == filename for f in files)
        except (DatabaseError, ValidationError) as e:
            logger.warning("Failed to check import status for %s: %s", filename, e)
            return False

    def get_participant_info_from_database(self, filename: str) -> dict[str, Any] | None:
        """Get participant info from database for imported file."""
        if not self.use_database:
            return None

        try:
            files = self.db_manager.get_available_files()
            for file_info in files:
                if file_info["filename"] == filename:
                    return {
                        "numerical_participant_id": file_info["participant_id"],
                        "participant_group": file_info["participant_group"],
                        "participant_timepoint": file_info["participant_timepoint"],
                        "full_participant_id": f"{file_info['participant_id']} {file_info['participant_timepoint']}",
                    }
            return None
        except (DatabaseError, ValidationError, KeyError) as e:
            logger.warning("Failed to get participant info for %s: %s", filename, e)
            return None
