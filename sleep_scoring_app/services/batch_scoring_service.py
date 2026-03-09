"""
Automatic sleep scoring orchestration for activity epoch files.

This module provides high-level functions for automatically scoring sleep across
multiple activity files using diary data as reference ranges.

Example usage:
    >>> from sleep_scoring_app.services.batch_scoring_service import auto_score_activity_epoch_files
    >>> from sleep_scoring_app.data.database import DatabaseManager
    >>>
    >>> # Auto-score all files in folder
    >>> results = auto_score_activity_epoch_files(
    ...     activity_folder='./study_data/',
    ...     diary_file='./sleep_diary.csv'
    ... )
    >>>
    >>> # Save to database
    >>> db = DatabaseManager()
    >>> for sleep_metrics in results:
    ...     db.save_sleep_metrics(sleep_metrics)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from sleep_scoring_app.core.algorithms import (
    AlgorithmFactory,
    SleepPeriodDetectorFactory,
    choi_detect_nonwear,
)
from sleep_scoring_app.core.algorithms.types import ActivityColumn
from sleep_scoring_app.core.constants import AlgorithmOutputColumn, AlgorithmType, DefaultColumn, SleepPeriodDetectorType
from sleep_scoring_app.core.dataclasses import DailySleepMarkers, ParticipantInfo, SleepMetrics, SleepPeriod
from sleep_scoring_app.utils.participant_extractor import extract_participant_info

if TYPE_CHECKING:
    from sleep_scoring_app.core.algorithms import SleepPeriodDetector, SleepScoringAlgorithm

logger = logging.getLogger(__name__)


def auto_score_activity_epoch_files(
    activity_folder: str,
    diary_file: str,
    nwt_folder: str | None = None,
    choi_activity_column: ActivityColumn = ActivityColumn.VECTOR_MAGNITUDE,
    sleep_algorithm: SleepScoringAlgorithm | None = None,
    sleep_period_detector: SleepPeriodDetector | None = None,
) -> list[SleepMetrics]:
    """
    Automatically score sleep for all activity epoch files in a folder.

    Applies Sadeh algorithm, Choi nonwear detection, and sleep rules to each file.
    Uses diary entries as reference ranges for sleep onset/offset detection.
    Returns SleepMetrics objects that can be saved to database via
    DatabaseManager.save_sleep_metrics().

    Args:
        activity_folder: Path to folder containing activity epoch CSV files
        diary_file: Path to diary CSV file with sleep entries
        nwt_folder: Optional path to NWT sensor data folder (reserved for future use)
        choi_activity_column: Activity column for Choi nonwear detection (default: VECTOR_MAGNITUDE)
        sleep_algorithm: Optional sleep scoring algorithm instance. If None, uses default Sadeh algorithm.
        sleep_period_detector: Optional sleep period detector instance. If None, uses default Consecutive 3/5 rule.

    Returns:
        List of SleepMetrics objects, one per successfully processed file

    Example:
        >>> from sleep_scoring_app.services.batch_scoring_service import auto_score_activity_epoch_files
        >>> from sleep_scoring_app.data.database import DatabaseManager
        >>>
        >>> # Auto-score all files
        >>> results = auto_score_activity_epoch_files(
        ...     activity_folder='./study_data/',
        ...     diary_file='./sleep_diary.csv'
        ... )
        >>>
        >>> # Save to database
        >>> db = DatabaseManager()
        >>> for sleep_metrics in results:
        ...     db.save_sleep_metrics(sleep_metrics)

    """
    # 0. Initialize algorithm (use default Sadeh if none provided)
    if sleep_algorithm is None:
        sleep_algorithm = AlgorithmFactory.create(AlgorithmFactory.get_default_algorithm_id())
    logger.info("Using sleep scoring algorithm: %s", sleep_algorithm.name)

    # 0b. Initialize sleep period detector (use default Consecutive 3/5 if none provided)
    if sleep_period_detector is None:
        sleep_period_detector = SleepPeriodDetectorFactory.create(SleepPeriodDetectorFactory.get_default_detector_id())
    logger.info("Using sleep period detector: %s", sleep_period_detector.name)

    # 1. Discover activity files
    activity_files = _discover_activity_files(activity_folder)
    logger.info("Found %d activity files", len(activity_files))

    # 2. Load diary data
    diary_df = _load_diary_file(diary_file)
    logger.info("Loaded diary with %d entries", len(diary_df))

    # 3. Process each activity file
    results = []
    failed_files: list[tuple[str, str]] = []  # (filename, error_message)

    for activity_file in activity_files:
        try:
            sleep_metrics = _process_activity_file(activity_file, diary_df, choi_activity_column, sleep_algorithm, sleep_period_detector)
            if sleep_metrics:
                results.append(sleep_metrics)
                num_periods = len(sleep_metrics.daily_sleep_markers.get_complete_periods())
                logger.info("Processed %s: %d periods", activity_file.name, num_periods)
            else:
                failed_files.append((activity_file.name, "Processing returned None (check logs for details)"))
                logger.warning("Processing %s returned None", activity_file.name)
        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            failed_files.append((activity_file.name, error_msg))
            logger.exception("Error processing %s: %s", activity_file.name, error_msg)
            continue

    # Log summary with failure details
    if failed_files:
        logger.warning(
            "Batch scoring completed with %d failures out of %d files:",
            len(failed_files),
            len(activity_files),
        )
        for filename, error in failed_files:
            logger.warning("  - %s: %s", filename, error)
    else:
        logger.info("Successfully processed all %d files", len(activity_files))

    logger.info("Batch scoring summary: %d succeeded, %d failed", len(results), len(failed_files))
    return results


def _discover_activity_files(activity_folder: str) -> list[Path]:
    """
    Discover all activity epoch CSV files in folder.

    Args:
        activity_folder: Path to folder containing CSV files

    Returns:
        Sorted list of CSV file paths

    Raises:
        FileNotFoundError: If activity folder does not exist

    """
    folder = Path(activity_folder)
    if not folder.exists():
        msg = f"Activity folder not found: {activity_folder}"
        raise FileNotFoundError(msg)

    # Find all CSV files
    activity_files = list(folder.glob("*.csv"))
    return sorted(activity_files)


def _load_diary_file(diary_file: str) -> pd.DataFrame:
    """
    Load diary CSV file.

    Args:
        diary_file: Path to diary CSV file

    Returns:
        DataFrame with diary entries

    Raises:
        FileNotFoundError: If diary file does not exist

    """
    diary_path = Path(diary_file)
    if not diary_path.exists():
        msg = f"Diary file not found: {diary_file}"
        raise FileNotFoundError(msg)

    return pd.read_csv(diary_path)


def _process_activity_file(
    activity_file: Path,
    diary_df: pd.DataFrame,
    choi_activity_column: ActivityColumn = ActivityColumn.VECTOR_MAGNITUDE,
    sleep_algorithm: SleepScoringAlgorithm | None = None,
    sleep_period_detector: SleepPeriodDetector | None = None,
) -> SleepMetrics | None:
    """
    Process a single activity file and return SleepMetrics.

    Args:
        activity_file: Path to activity CSV file
        diary_df: DataFrame with diary entries
        choi_activity_column: Activity column for Choi nonwear detection
        sleep_algorithm: Sleep scoring algorithm instance to use
        sleep_period_detector: Sleep period detector instance to use

    Returns:
        SleepMetrics object with calculated metrics, or None if processing fails

    """
    # 1. Extract participant ID and date from filename
    participant_info = _extract_participant_info(activity_file)
    analysis_date = _extract_analysis_date(activity_file)

    # 2. Load activity data
    activity_df = pd.read_csv(activity_file)

    # Validate required columns exist
    if "datetime" not in activity_df.columns:
        logger.warning("No 'datetime' column in %s, skipping", activity_file.name)
        return None

    # Ensure datetime column is parsed
    activity_df["datetime"] = pd.to_datetime(activity_df["datetime"])

    # 3. Apply algorithms
    # Use injected sleep algorithm (default: Sadeh) - adds score column based on algorithm
    if sleep_algorithm is None:
        sleep_algorithm = AlgorithmFactory.create(AlgorithmFactory.get_default_algorithm_id())
    activity_df = sleep_algorithm.score(activity_df)  # Adds algorithm-specific score column
    activity_df = choi_detect_nonwear(activity_df, choi_activity_column)  # Adds 'Choi Nonwear' column

    # 4. Find diary entry for this participant/date
    diary_entry = _find_diary_entry(diary_df, participant_info.numerical_id, analysis_date)

    if diary_entry is None:
        logger.warning("No diary entry found for %s on %s", participant_info.numerical_id, analysis_date)
        # Continue without diary reference - will search entire dataset
        diary_onset = None
        diary_offset = None
    else:
        # Extract diary times as reference points
        diary_onset, diary_offset = _extract_diary_times(diary_entry, analysis_date)

    # 5. Apply sleep rules to find onset/offset
    daily_markers = _apply_sleep_rules(
        activity_df=activity_df,
        diary_onset=diary_onset,
        diary_offset=diary_offset,
        sleep_period_detector=sleep_period_detector,
    )

    # 6. Calculate metrics for main sleep period
    metrics_dict = _calculate_metrics(
        daily_markers=daily_markers,
        activity_df=activity_df,
    )

    # 7. Create SleepMetrics object
    # Use the algorithm's identifier to determine the algorithm_type
    algorithm_id = sleep_algorithm.identifier
    try:
        algorithm_type = AlgorithmType(algorithm_id)
    except ValueError:
        # Fallback if identifier doesn't match enum - log warning so user knows
        logger.warning(
            "Algorithm identifier '%s' does not match any AlgorithmType enum value. "
            "Falling back to SADEH_1994_ACTILIFE for database storage. "
            "The actual algorithm used (%s) is preserved in sleep_algorithm_name.",
            algorithm_id,
            sleep_algorithm.name,
        )
        algorithm_type = AlgorithmType.SADEH_1994_ACTILIFE

    return SleepMetrics(
        filename=activity_file.name,
        analysis_date=analysis_date,
        algorithm_type=algorithm_type,
        daily_sleep_markers=daily_markers,
        participant=participant_info,
        sleep_algorithm_name=algorithm_id,
        sleep_period_detector_id=sleep_period_detector.identifier if sleep_period_detector else SleepPeriodDetectorType.CONSECUTIVE_ONSET3S_OFFSET5S,
        **metrics_dict,
    )


def _extract_participant_info(activity_file: Path) -> ParticipantInfo:
    """
    Extract participant info from filename.

    Args:
        activity_file: Path to activity file

    Returns:
        ParticipantInfo extracted from filename

    """
    return extract_participant_info(activity_file.name)


def _extract_analysis_date(activity_file: Path) -> str:
    """
    Extract analysis date from filename.

    Expected format: ParticipantID_YYYY-MM-DD.csv

    Args:
        activity_file: Path to activity file

    Returns:
        Date string in YYYY-MM-DD format, or current date if not found

    """
    import re

    # Try to extract date in YYYY-MM-DD format
    match = re.search(r"(\d{4}-\d{2}-\d{2})", activity_file.name)
    if match:
        return match.group(1)

    # Fallback: use file modification date
    mtime = activity_file.stat().st_mtime
    return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")


def _find_diary_entry(
    diary_df: pd.DataFrame,
    participant_id: str,
    analysis_date: str,
) -> dict | None:
    """
    Find diary entry matching participant and date.

    Args:
        diary_df: DataFrame with diary entries
        participant_id: Participant ID to match
        analysis_date: Date to match (YYYY-MM-DD format)

    Returns:
        Dictionary with diary entry data, or None if not found

    """
    # Common diary column names for participant ID
    participant_id_columns = ["participant_id", "Participant ID", "ParticipantID", "ID"]

    # Common diary column names for date
    date_columns = ["date", "Date", "diary_date", "analysis_date", "sleep_date"]

    # Find matching columns in diary
    pid_col = None
    for col in participant_id_columns:
        if col in diary_df.columns:
            pid_col = col
            break

    date_col = None
    for col in date_columns:
        if col in diary_df.columns:
            date_col = col
            break

    if pid_col is None or date_col is None:
        logger.warning("Could not find required columns in diary (need participant_id and date)")
        return None

    # Match by participant ID and date
    matching = diary_df[(diary_df[pid_col].astype(str) == participant_id) & (diary_df[date_col].astype(str) == analysis_date)]

    if len(matching) == 0:
        return None

    # NOTE: to_dict() is correct here - converting pandas Series to dict for downstream processing.
    # This is the interface between pandas DataFrame and the _extract_diary_times function.
    return matching.iloc[0].to_dict()


def _extract_diary_times(diary_entry: dict, analysis_date: str) -> tuple[datetime | None, datetime | None]:
    """
    Extract sleep onset and offset times from diary entry.

    Args:
        diary_entry: Dictionary with diary data
        analysis_date: Date being analyzed (YYYY-MM-DD format)

    Returns:
        Tuple of (onset_datetime, offset_datetime), both may be None

    """
    # Common column names for sleep times
    onset_columns = ["sleep_onset_time", "bedtime", "in_bed_time", "onset"]
    offset_columns = ["sleep_offset_time", "wake_time", "out_of_bed_time", "offset"]

    onset_time_str = None
    for col in onset_columns:
        if col in diary_entry and diary_entry[col] is not None:
            onset_time_str = str(diary_entry[col])
            break

    offset_time_str = None
    for col in offset_columns:
        if col in diary_entry and diary_entry[col] is not None:
            offset_time_str = str(diary_entry[col])
            break

    # Parse times into datetime objects
    from datetime import timedelta

    onset_dt = None
    offset_dt = None

    if onset_time_str:
        try:
            onset_dt = datetime.strptime(f"{analysis_date} {onset_time_str}", "%Y-%m-%d %H:%M")
            # For main sleep, early morning times (midnight to noon) are ALWAYS the next
            # calendar day since analysis_date is the bedtime evening date.
            onset_hour = onset_dt.hour
            if onset_hour < 12:
                onset_dt = onset_dt + timedelta(days=1)
        except ValueError:
            logger.warning("Could not parse onset time: %s", onset_time_str)

    if offset_time_str:
        try:
            offset_dt = datetime.strptime(f"{analysis_date} {offset_time_str}", "%Y-%m-%d %H:%M")

            if onset_dt and offset_dt < onset_dt:
                # Offset before onset means next day relative to onset
                offset_dt = offset_dt + timedelta(days=1)
            elif onset_dt is None and offset_dt.hour < 12:
                # No onset to compare — early morning offset is next day (same logic as onset)
                offset_dt = offset_dt + timedelta(days=1)
        except ValueError:
            logger.warning("Could not parse offset time: %s", offset_time_str)

    return onset_dt, offset_dt


def _apply_sleep_rules(
    activity_df: pd.DataFrame,
    diary_onset: datetime | None,
    diary_offset: datetime | None,
    sleep_period_detector: SleepPeriodDetector | None = None,
) -> DailySleepMarkers:
    """
    Apply sleep rules to find onset/offset markers.

    Args:
        activity_df: DataFrame with 'Sadeh Score' and 'datetime' columns
        diary_onset: Diary-reported onset time (or None)
        diary_offset: Diary-reported offset time (or None)
        sleep_period_detector: Sleep period detector instance to use

    Returns:
        DailySleepMarkers with identified sleep periods

    """
    daily_markers = DailySleepMarkers()

    # Use provided detector or create default
    if sleep_period_detector is None:
        sleep_period_detector = SleepPeriodDetectorFactory.create(SleepPeriodDetectorFactory.get_default_detector_id())

    # Extract data from DataFrame
    sleep_scores = activity_df[AlgorithmOutputColumn.SLEEP_SCORE].tolist()
    timestamps = activity_df["datetime"].tolist()

    # If no diary reference, use entire dataset
    if diary_onset is None or diary_offset is None:
        # Use first and last timestamps as rough markers
        diary_onset = timestamps[0] if timestamps else datetime.now()
        diary_offset = timestamps[-1] if timestamps else datetime.now()
        logger.info("No diary reference, searching entire dataset")

    # Apply sleep period detection via injected detector instance
    assert diary_onset is not None  # guaranteed by fallback assignment above
    assert diary_offset is not None  # guaranteed by fallback assignment above
    onset_idx, offset_idx = sleep_period_detector.apply_rules(
        sleep_scores=sleep_scores,
        sleep_start_marker=diary_onset,
        sleep_end_marker=diary_offset,
        timestamps=timestamps,
    )

    # Create sleep period if both markers found
    if onset_idx is not None and offset_idx is not None:
        sleep_period = SleepPeriod(
            onset_timestamp=timestamps[onset_idx].timestamp(),
            offset_timestamp=timestamps[offset_idx].timestamp(),
            marker_index=1,
        )
        daily_markers.period_1 = sleep_period

        # Update classifications (MAIN_SLEEP vs NAP)
        daily_markers.update_classifications()
    else:
        logger.warning("Sleep rules did not find valid onset/offset")

    return daily_markers


def _calculate_metrics(
    daily_markers: DailySleepMarkers,
    activity_df: pd.DataFrame,
) -> dict:
    """
    Calculate sleep metrics for main sleep period.

    Args:
        daily_markers: DailySleepMarkers with identified periods
        activity_df: DataFrame with activity and algorithm results

    Returns:
        Dictionary with calculated metrics

    """
    main_sleep = daily_markers.get_main_sleep()

    if main_sleep is None or not main_sleep.is_complete:
        # Return empty metrics
        return {
            "onset_time": "",
            "offset_time": "",
            "total_sleep_time": None,
            "sleep_efficiency": None,
            "total_minutes_in_bed": None,
            "waso": None,
            "awakenings": None,
            "average_awakening_length": None,
            "total_activity": None,
            "movement_index": None,
            "fragmentation_index": None,
            "sleep_fragmentation_index": None,
            "sleep_algorithm_onset": None,
            "sleep_algorithm_offset": None,
            "overlapping_nonwear_minutes_algorithm": None,
            "overlapping_nonwear_minutes_sensor": None,
        }

    # Find indices for onset and offset in the DataFrame
    if main_sleep.onset_timestamp is None or main_sleep.offset_timestamp is None:
        logger.warning("Main sleep period has no onset/offset timestamps")
        return {
            "onset_time": "",
            "offset_time": "",
            "total_sleep_time": None,
            "sleep_efficiency": None,
            "total_minutes_in_bed": None,
            "waso": None,
            "awakenings": None,
            "average_awakening_length": None,
            "total_activity": None,
            "movement_index": None,
            "fragmentation_index": None,
            "sleep_fragmentation_index": None,
            "sleep_algorithm_onset": None,
            "sleep_algorithm_offset": None,
            "overlapping_nonwear_minutes_algorithm": None,
            "overlapping_nonwear_minutes_sensor": None,
        }
    onset_dt = datetime.fromtimestamp(main_sleep.onset_timestamp)
    offset_dt = datetime.fromtimestamp(main_sleep.offset_timestamp)

    # Find closest indices
    timestamps = activity_df["datetime"].tolist()
    onset_idx = _find_closest_index(timestamps, onset_dt)
    offset_idx = _find_closest_index(timestamps, offset_dt)

    if onset_idx is None or offset_idx is None:
        logger.warning("Could not find indices for onset/offset in activity data")
        return {}

    # Extract period data
    period_sleep = activity_df[AlgorithmOutputColumn.SLEEP_SCORE].iloc[onset_idx : offset_idx + 1]
    period_nonwear = (
        activity_df[AlgorithmOutputColumn.NONWEAR_SCORE].iloc[onset_idx : offset_idx + 1]
        if AlgorithmOutputColumn.NONWEAR_SCORE in activity_df.columns
        else None
    )

    # Get activity column (prefer Vector Magnitude, fallback to Axis1)
    activity_col = None
    if DefaultColumn.VECTOR_MAGNITUDE in activity_df.columns:
        activity_col = DefaultColumn.VECTOR_MAGNITUDE
    elif DefaultColumn.AXIS_Y in activity_df.columns:
        activity_col = DefaultColumn.AXIS_Y

    period_activity = activity_df[activity_col].iloc[onset_idx : offset_idx + 1] if activity_col else None

    # Calculate basic metrics

    # Note: batch scoring uses inclusive range (offset_idx - onset_idx + 1)
    # while data_service uses exclusive range (offset_idx - onset_idx)
    # This is intentional for batch processing compatibility
    total_minutes_in_bed = offset_idx - onset_idx + 1
    sleep_minutes = period_sleep.sum()
    total_sleep_time = float(sleep_minutes)

    # Calculate WASO (wake after sleep onset)
    # Find first and last sleep epochs
    first_sleep_idx = None
    last_sleep_idx = None
    for i, score in enumerate(period_sleep):
        if score == 1:
            if first_sleep_idx is None:
                first_sleep_idx = i
            last_sleep_idx = i

    if first_sleep_idx is not None and last_sleep_idx is not None:
        sleep_period_length = last_sleep_idx - first_sleep_idx + 1
        waso = float(sleep_period_length - sleep_minutes)
    else:
        waso = None

    # Calculate efficiency
    efficiency = (total_sleep_time / total_minutes_in_bed * 100) if total_minutes_in_bed > 0 else None

    # Calculate awakenings
    awakenings = 0
    awakening_lengths = []
    current_awakening_length = 0

    for i, score in enumerate(period_sleep):
        if score == 1:  # Sleep
            if current_awakening_length > 0:
                awakening_lengths.append(current_awakening_length)
                current_awakening_length = 0
        elif first_sleep_idx is not None and last_sleep_idx is not None and i > first_sleep_idx and i <= last_sleep_idx:
            current_awakening_length += 1
            if current_awakening_length == 1:
                awakenings += 1

    avg_awakening_length = sum(awakening_lengths) / len(awakening_lengths) if awakening_lengths else None

    # Calculate activity metrics
    total_activity = int(period_activity.sum()) if period_activity is not None else None
    movement_events = int((period_activity > 0).sum()) if period_activity is not None else 0
    movement_index = movement_events / total_minutes_in_bed if total_minutes_in_bed > 0 else None
    fragmentation_index = (awakenings / total_sleep_time * 100) if total_sleep_time > 0 else None
    sleep_fragmentation_index = ((waso + movement_events) / total_minutes_in_bed * 100) if total_minutes_in_bed > 0 and waso is not None else None

    # Get algorithm values at markers
    algorithm_onset = int(period_sleep.iloc[0]) if len(period_sleep) > 0 else None
    algorithm_offset = int(period_sleep.iloc[-1]) if len(period_sleep) > 0 else None

    # Calculate overlapping nonwear minutes during sleep period
    # Sum of 0/1 values per minute epoch = total nonwear minutes
    from sleep_scoring_app.utils.calculations import calculate_overlapping_nonwear_minutes

    # Note: For batch scoring we need to convert series to list for the calculation
    choi_list = period_nonwear.tolist() if period_nonwear is not None else None
    overlapping_nonwear_minutes_algorithm = calculate_overlapping_nonwear_minutes(choi_list, 0, len(choi_list) - 1) if choi_list else None

    return {
        "onset_time": onset_dt.strftime("%H:%M"),
        "offset_time": offset_dt.strftime("%H:%M"),
        "total_sleep_time": total_sleep_time,
        "sleep_efficiency": round(efficiency, 2) if efficiency is not None else None,
        "total_minutes_in_bed": float(total_minutes_in_bed),
        "waso": round(waso, 1) if waso is not None else None,
        "awakenings": awakenings,
        "average_awakening_length": round(avg_awakening_length, 1) if avg_awakening_length is not None else None,
        "total_activity": total_activity,
        "movement_index": round(movement_index, 3) if movement_index is not None else None,
        "fragmentation_index": round(fragmentation_index, 2) if fragmentation_index is not None else None,
        "sleep_fragmentation_index": round(sleep_fragmentation_index, 2) if sleep_fragmentation_index is not None else None,
        "sleep_algorithm_onset": algorithm_onset,
        "sleep_algorithm_offset": algorithm_offset,
        "overlapping_nonwear_minutes_algorithm": overlapping_nonwear_minutes_algorithm,
        "overlapping_nonwear_minutes_sensor": None,  # NWT sensor calculation happens elsewhere
    }


def _find_closest_index(timestamps: list[datetime], target: datetime) -> int | None:
    """
    Find index of closest timestamp to target.

    Args:
        timestamps: List of datetime objects
        target: Target datetime to find

    Returns:
        Index of closest timestamp, or None if list is empty

    """
    if not timestamps:
        return None

    min_diff = float("inf")
    closest_idx = None

    for i, ts in enumerate(timestamps):
        diff = abs((ts - target).total_seconds())
        if diff < min_diff:
            min_diff = diff
            closest_idx = i

    return closest_idx
