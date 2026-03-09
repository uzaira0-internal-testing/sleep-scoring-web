"""
Concrete implementations of MarkerPersistence protocol.

This module provides persistence implementations for both sleep and nonwear markers,
injected via dependency injection to ensure consistent save behavior.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sleep_scoring_app.core.constants import AlgorithmType
from sleep_scoring_app.core.markers.protocol import (
    DailyMarkersProtocol,
    MarkerPersistence,
    MetricsSaver,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from sleep_scoring_app.core.dataclasses import SleepMetrics
    from sleep_scoring_app.core.dataclasses_markers import DailyNonwearMarkers
    from sleep_scoring_app.data.database import DatabaseManager

logger = logging.getLogger(__name__)


class SleepMarkerPersistence(MarkerPersistence):
    """
    Persistence implementation for sleep markers.

    Saves sleep markers to the sleep_metrics table via ExportManager,
    calculating metrics before persistence.
    """

    def __init__(
        self,
        db_manager: DatabaseManager,
        metrics_saver: MetricsSaver,
        metrics_calculator: Any = None,
    ) -> None:
        """
        Initialize sleep marker persistence.

        Args:
            db_manager: Database manager for direct DB operations
            metrics_saver: Service for saving comprehensive sleep metrics
            metrics_calculator: Optional callable to calculate sleep metrics

        """
        self._db_manager = db_manager
        self._metrics_saver = metrics_saver
        self._metrics_calculator = metrics_calculator

    def save(
        self,
        filename: str,
        participant_id: str,
        date: datetime,
        markers: DailyMarkersProtocol,
        *,
        sleep_metrics: SleepMetrics | None = None,
        algorithm_type: Any = None,
        **kwargs: Any,
    ) -> bool:
        """
        Save sleep markers to permanent storage.

        Args:
            filename: The source file name
            participant_id: Participant identifier
            date: The date for these markers
            markers: The daily markers container to save
            sleep_metrics: Pre-calculated sleep metrics (optional)
            algorithm_type: Algorithm type used for scoring

        Returns:
            True if save succeeded

        Raises:
            ValidationError: If required data is missing
            DatabaseError: If save operation fails

        """
        from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes, ValidationError

        if sleep_metrics is None:
            msg = "No sleep metrics provided for save"
            raise ValidationError(msg, ErrorCodes.MISSING_REQUIRED)

        # Ensure markers are attached
        sleep_metrics.daily_sleep_markers = markers
        sleep_metrics.analysis_date = date.strftime("%Y-%m-%d")
        sleep_metrics.filename = filename

        algo_type = algorithm_type or AlgorithmType.SADEH_1994_ACTILIFE

        # Save via metrics saver and CHECK the result
        saved = self._metrics_saver.save_comprehensive_sleep_metrics([sleep_metrics], algo_type)

        if not saved:
            msg = f"Failed to save sleep metrics for {filename}"
            raise DatabaseError(
                msg,
                ErrorCodes.DB_INSERT_FAILED,
            )

        logger.debug("Saved sleep markers for %s on %s", filename, date)
        return True

    def load(
        self,
        filename: str,
        date: datetime,
    ) -> DailyMarkersProtocol | None:
        """
        Load sleep markers from persistent storage.

        Args:
            filename: The source file name
            date: The date to load markers for

        Returns:
            The loaded markers container, or None if not found

        Raises:
            DatabaseError: If database operation fails

        """
        from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes

        try:
            metrics = self._db_manager.get_sleep_metrics_by_filename_and_date(filename, date.strftime("%Y-%m-%d"))
            if metrics and metrics.daily_sleep_markers:
                return metrics.daily_sleep_markers
            return None
        except DatabaseError:
            raise  # Re-raise our custom exceptions
        except Exception as e:
            logger.exception("Failed to load sleep markers: %s", e)
            msg = f"Failed to load sleep markers for {filename}"
            raise DatabaseError(
                msg,
                ErrorCodes.DB_QUERY_FAILED,
            ) from e

    def delete(
        self,
        filename: str,
        date: datetime,
    ) -> bool:
        """
        Delete sleep markers from persistent storage.

        Args:
            filename: The source file name
            date: The date to delete markers for

        Returns:
            True if delete succeeded

        Raises:
            DatabaseError: If delete operation fails

        """
        from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes

        try:
            self._db_manager.delete_sleep_metrics_for_date(filename, date.strftime("%Y-%m-%d"))
            logger.debug("Deleted sleep markers for %s on %s", filename, date)
            return True
        except DatabaseError:
            raise  # Re-raise our custom exceptions
        except Exception as e:
            logger.exception("Failed to delete sleep markers: %s", e)
            msg = f"Failed to delete sleep markers for {filename}"
            raise DatabaseError(
                msg,
                ErrorCodes.DB_DELETE_FAILED,
            ) from e


class NonwearMarkerPersistence(MarkerPersistence):
    """
    Persistence implementation for nonwear markers.

    Saves nonwear markers directly to the manual_nwt_markers table.
    """

    def __init__(self, db_manager: DatabaseManager) -> None:
        """
        Initialize nonwear marker persistence.

        Args:
            db_manager: Database manager for DB operations

        """
        self._db_manager = db_manager

    def save(
        self,
        filename: str,
        participant_id: str,
        date: datetime,
        markers: DailyMarkersProtocol,
        **kwargs: Any,
    ) -> bool:
        """
        Save nonwear markers to permanent storage.

        Args:
            filename: The source file name
            participant_id: Participant identifier
            date: The date for these markers
            markers: The daily markers container to save
            **kwargs: Ignored (for protocol compatibility)

        Returns:
            True if save succeeded

        Raises:
            DatabaseError: If save operation fails

        """
        from typing import cast

        from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes

        # Cast to concrete type - the database expects DailyNonwearMarkers
        nonwear_markers = cast("DailyNonwearMarkers", markers)

        try:
            self._db_manager.save_manual_nonwear_markers(
                filename=filename,
                participant_id=participant_id,
                sleep_date=date.strftime("%Y-%m-%d"),
                daily_nonwear_markers=nonwear_markers,
            )
            logger.debug("Saved nonwear markers for %s on %s", filename, date)
            return True
        except DatabaseError:
            raise  # Re-raise our custom exceptions
        except Exception as e:
            logger.exception("Failed to save nonwear markers: %s", e)
            msg = f"Failed to save nonwear markers for {filename}"
            raise DatabaseError(
                msg,
                ErrorCodes.DB_INSERT_FAILED,
            ) from e

    def load(
        self,
        filename: str,
        date: datetime,
    ) -> DailyMarkersProtocol | None:
        """
        Load nonwear markers from persistent storage.

        Args:
            filename: The source file name
            date: The date to load markers for

        Returns:
            The loaded markers container, or None if not found

        Raises:
            DatabaseError: If database operation fails

        """
        from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes

        try:
            return self._db_manager.load_manual_nonwear_markers(
                filename=filename,
                sleep_date=date.strftime("%Y-%m-%d"),
            )
        except DatabaseError:
            raise  # Re-raise our custom exceptions
        except Exception as e:
            logger.exception("Failed to load nonwear markers: %s", e)
            msg = f"Failed to load nonwear markers for {filename}"
            raise DatabaseError(
                msg,
                ErrorCodes.DB_QUERY_FAILED,
            ) from e

    def delete(
        self,
        filename: str,
        date: datetime,
    ) -> bool:
        """
        Delete nonwear markers from persistent storage.

        Args:
            filename: The source file name
            date: The date to delete markers for

        Returns:
            True if delete succeeded

        Raises:
            DatabaseError: If delete operation fails

        """
        from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes

        try:
            self._db_manager.delete_manual_nonwear_markers(
                filename=filename,
                sleep_date=date.strftime("%Y-%m-%d"),
            )
            logger.debug("Deleted nonwear markers for %s on %s", filename, date)
            return True
        except DatabaseError:
            raise  # Re-raise our custom exceptions
        except Exception as e:
            logger.exception("Failed to delete nonwear markers: %s", e)
            msg = f"Failed to delete nonwear markers for {filename}"
            raise DatabaseError(
                msg,
                ErrorCodes.DB_DELETE_FAILED,
            ) from e


class UnifiedMarkerHandler:
    """
    Unified handler for marker changes with consistent behavior.

    This class provides a single entry point for handling marker changes,
    using dependency injection to ensure both sleep and nonwear markers
    are persisted with the same pattern.
    """

    def __init__(
        self,
        sleep_persistence: SleepMarkerPersistence,
        nonwear_persistence: NonwearMarkerPersistence,
    ) -> None:
        """
        Initialize unified marker handler.

        Args:
            sleep_persistence: Persistence implementation for sleep markers
            nonwear_persistence: Persistence implementation for nonwear markers

        """
        self._sleep_persistence = sleep_persistence
        self._nonwear_persistence = nonwear_persistence
        self._on_save_callbacks: list[Callable[[str, str, datetime], None]] = []

    def add_on_save_callback(self, callback: Callable[[str, str, datetime], None]) -> None:
        """Add callback to be invoked after successful save."""
        self._on_save_callbacks.append(callback)

    def on_sleep_markers_changed(
        self,
        markers: DailyMarkersProtocol,
        filename: str,
        participant_id: str,
        date: datetime,
        sleep_metrics: Any = None,
        algorithm_type: Any = None,
    ) -> None:
        """
        Handle sleep marker change with automatic persistence.

        Args:
            markers: Updated sleep markers
            filename: Source file name
            participant_id: Participant identifier
            date: Date for these markers
            sleep_metrics: Pre-calculated metrics
            algorithm_type: Algorithm used

        Raises:
            ValidationError: If required data is missing
            DatabaseError: If save operation fails

        """
        self._sleep_persistence.save(
            filename=filename,
            participant_id=participant_id,
            date=date,
            markers=markers,
            sleep_metrics=sleep_metrics,
            algorithm_type=algorithm_type,
        )

        for callback in self._on_save_callbacks:
            try:
                callback("sleep", filename, date)
            except Exception as e:
                logger.warning("Save callback failed: %s", e)

    def on_nonwear_markers_changed(
        self,
        markers: DailyMarkersProtocol,
        filename: str,
        participant_id: str,
        date: datetime,
    ) -> None:
        """
        Handle nonwear marker change with automatic persistence.

        Args:
            markers: Updated nonwear markers
            filename: Source file name
            participant_id: Participant identifier
            date: Date for these markers

        Raises:
            DatabaseError: If save operation fails

        """
        self._nonwear_persistence.save(
            filename=filename,
            participant_id=participant_id,
            date=date,
            markers=markers,
        )

        for callback in self._on_save_callbacks:
            try:
                callback("nonwear", filename, date)
            except Exception as e:
                logger.warning("Save callback failed: %s", e)
