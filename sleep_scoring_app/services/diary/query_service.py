"""Query service for diary data retrieval operations."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

    from sleep_scoring_app.data.database import DatabaseManager

from sleep_scoring_app.core.constants import DatabaseColumn, DatabaseTable
from sleep_scoring_app.core.dataclasses import DiaryEntry

logger = logging.getLogger(__name__)


class DiaryQueryService:
    """Service for querying diary data from the database."""

    def __init__(self, database_manager: DatabaseManager) -> None:
        self.db_manager = database_manager

    def get_diary_data_for_participant(
        self,
        participant_id: str,
        date_range: tuple[datetime, datetime] | None = None,
    ) -> list[DiaryEntry]:
        """Get diary data for a specific participant using PARTICIPANT_KEY for matching."""
        try:
            # Extract participant info to get composite key
            from sleep_scoring_app.utils.participant_extractor import (
                extract_participant_info,
            )

            participant_info = extract_participant_info(participant_id)
            participant_key = participant_info.participant_key

            from sleep_scoring_app.data.repositories.base_repository import BaseRepository

            temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
            with temp_repo._get_connection() as conn:
                cursor = conn.cursor()

                # Use PARTICIPANT_KEY for matching across different data sources
                query = f"""
                    SELECT * FROM {DatabaseTable.DIARY_DATA}
                    WHERE {DatabaseColumn.PARTICIPANT_KEY} = ?
                """
                params: list[str] = [participant_key]

                if date_range:
                    query += f" AND {DatabaseColumn.DIARY_DATE} BETWEEN ? AND ?"
                    params.extend(
                        [
                            date_range[0].strftime("%Y-%m-%d"),
                            date_range[1].strftime("%Y-%m-%d"),
                        ]
                    )

                query += f" ORDER BY {DatabaseColumn.DIARY_DATE}"

                cursor.execute(query, params)
                rows = cursor.fetchall()

                if rows:
                    logger.debug(f"Found {len(rows)} diary entries for participant key: '{participant_key}'")
                    all_entries = []
                    for row in rows:
                        row_dict = dict(
                            zip(
                                [desc[0] for desc in cursor.description],
                                row,
                                strict=False,
                            )
                        )
                        all_entries.append(DiaryEntry.from_database_dict(row_dict))
                    return all_entries

                logger.debug(f"No diary entries found for participant key '{participant_key}'")
                return []

        except Exception as e:
            logger.exception(f"Failed to get diary data for participant {participant_id}: {e}")
            return []

    def get_diary_data_for_date(
        self,
        participant_id: str,
        target_date: datetime,
    ) -> DiaryEntry | None:
        """Get diary data for a specific participant and date using PARTICIPANT_KEY."""
        date_str = target_date.strftime("%Y-%m-%d")

        try:
            # Extract participant info to get composite key
            from sleep_scoring_app.utils.participant_extractor import (
                extract_participant_info,
            )

            participant_info = extract_participant_info(participant_id)
            participant_key = participant_info.participant_key

            from sleep_scoring_app.data.repositories.base_repository import BaseRepository

            temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
            with temp_repo._get_connection() as conn:
                cursor = conn.cursor()

                # Use PARTICIPANT_KEY for matching
                query = f"""
                    SELECT * FROM {DatabaseTable.DIARY_DATA}
                    WHERE {DatabaseColumn.PARTICIPANT_KEY} = ?
                    AND {DatabaseColumn.DIARY_DATE} = ?
                """

                cursor.execute(query, [participant_key, date_str])
                row = cursor.fetchone()

                if row:
                    logger.debug(f"Found diary data for date '{date_str}' with participant key: '{participant_key}'")
                    row_dict = dict(
                        zip(
                            [desc[0] for desc in cursor.description],
                            row,
                            strict=False,
                        )
                    )
                    return DiaryEntry.from_database_dict(row_dict)

                logger.debug(f"No diary data found for participant key '{participant_key}' on date '{date_str}'")
                return None

        except Exception as e:
            logger.exception(f"Failed to get diary data for participant {participant_id} on {date_str}: {e}")
            return None

    def get_available_participants(self) -> list[str]:
        """Get list of participants with diary data."""
        from sleep_scoring_app.data.repositories.base_repository import BaseRepository

        temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
        try:
            with temp_repo._get_connection() as conn:
                cursor = conn.cursor()

                query = f"""
                    SELECT DISTINCT {DatabaseColumn.PARTICIPANT_ID}
                    FROM {DatabaseTable.DIARY_DATA}
                    ORDER BY {DatabaseColumn.PARTICIPANT_ID}
                """

                cursor.execute(query)
                rows = cursor.fetchall()

                return [row[0] for row in rows]

        except Exception as e:
            logger.exception(f"Failed to get available participants: {e}")
            return []

    def get_diary_stats(self) -> dict[str, Any]:
        """Get diary data statistics."""
        from sleep_scoring_app.data.repositories.base_repository import BaseRepository

        temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
        try:
            with temp_repo._get_connection() as conn:
                cursor = conn.cursor()

                # Count total entries
                cursor.execute(f"SELECT COUNT(*) FROM {DatabaseTable.DIARY_DATA}")
                total_entries = cursor.fetchone()[0]

                # Count unique participants
                cursor.execute(
                    f"""
                    SELECT COUNT(DISTINCT {DatabaseColumn.PARTICIPANT_ID})
                    FROM {DatabaseTable.DIARY_DATA}
                """
                )
                unique_participants = cursor.fetchone()[0]

                # Get date range
                cursor.execute(
                    f"""
                    SELECT MIN({DatabaseColumn.DIARY_DATE}), MAX({DatabaseColumn.DIARY_DATE})
                    FROM {DatabaseTable.DIARY_DATA}
                """
                )
                date_range = cursor.fetchone()

                return {
                    "total_entries": total_entries,
                    "unique_participants": unique_participants,
                    "date_range_start": date_range[0],
                    "date_range_end": date_range[1],
                }

        except Exception as e:
            logger.exception(f"Failed to get diary stats: {e}")
            return {
                "total_entries": 0,
                "unique_participants": 0,
                "date_range_start": None,
                "date_range_end": None,
            }

    def check_participant_has_diary_data(self, participant_id: str) -> bool:
        """Check if participant has any diary data using PARTICIPANT_KEY."""
        try:
            # Extract participant info to get composite key
            from sleep_scoring_app.utils.participant_extractor import (
                extract_participant_info,
            )

            participant_info = extract_participant_info(participant_id)
            participant_key = participant_info.participant_key

            logger.debug(f"Checking diary data: input={participant_id}, key={participant_key}")

            from sleep_scoring_app.data.repositories.base_repository import BaseRepository

            temp_repo = BaseRepository(self.db_manager.db_path, self.db_manager._validate_table_name, self.db_manager._validate_column_name)
            with temp_repo._get_connection() as conn:
                cursor = conn.cursor()
                query = f"""
                    SELECT 1 FROM {DatabaseTable.DIARY_DATA}
                    WHERE {DatabaseColumn.PARTICIPANT_KEY} = ?
                    LIMIT 1
                """
                cursor.execute(query, [participant_key])
                result = cursor.fetchone()
                return result is not None

        except Exception as e:
            logger.exception(f"Failed to check diary data for participant {participant_id}: {e}")
            return False
