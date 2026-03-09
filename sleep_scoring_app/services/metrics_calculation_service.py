"""
Metrics calculation service for sleep metrics and analysis.
Handles calculation of sleep metrics from markers and algorithm results.
"""

from __future__ import annotations

import bisect
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sleep_scoring_app.core.constants import AlgorithmType
from sleep_scoring_app.core.dataclasses import DailySleepMarkers, ParticipantInfo, SleepMetrics, SleepPeriod

logger = logging.getLogger(__name__)


class MetricsCalculationService:
    """Handles sleep metrics calculations from algorithm results."""

    def __init__(self) -> None:
        pass

    def _calculate_sleep_metrics_from_timestamps(
        self,
        onset_timestamp: float,
        offset_timestamp: float,
        sadeh_results,
        choi_results,
        activity_data,
        x_data,
        participant_info: ParticipantInfo,
        nwt_sensor_results=None,
        algorithm_type: AlgorithmType | None = None,
    ) -> dict[str, Any] | None:
        """Calculate comprehensive sleep metrics from onset/offset timestamps."""
        try:
            # Convert to datetime objects
            onset_dt = datetime.fromtimestamp(onset_timestamp)
            offset_dt = datetime.fromtimestamp(offset_timestamp)

            # Find indices for onset and offset
            onset_idx = self._find_closest_data_index(x_data, onset_timestamp)
            offset_idx = self._find_closest_data_index(x_data, offset_timestamp)

            # Algorithm values at markers (for sleep scoring algorithm only)
            algorithm_onset = sadeh_results[onset_idx] if onset_idx is not None and onset_idx < len(sadeh_results) else 0
            algorithm_offset = sadeh_results[offset_idx] if offset_idx is not None and offset_idx < len(sadeh_results) else 0

            # Initialize all variables
            total_activity = 0
            movement_events = 0

            # Calculate sleep period metrics from Sadeh results
            if onset_idx is not None and offset_idx is not None and sadeh_results:
                sleep_minutes = 0
                awakenings = 0
                awakening_lengths = []
                current_awakening_length = 0

                # Find first and last actual sleep epochs for WASO calculation (ActiLife-compatible)
                first_sleep_idx = None
                last_sleep_idx = None
                for i in range(onset_idx, min(offset_idx, len(sadeh_results))):
                    if sadeh_results[i] == 1:
                        if first_sleep_idx is None:
                            first_sleep_idx = i
                        last_sleep_idx = i

                for i in range(onset_idx, min(offset_idx, len(sadeh_results))):
                    if i < len(activity_data):
                        activity = activity_data[i]
                        total_activity += activity

                        if activity > 0:
                            movement_events += 1

                    if sadeh_results[i] == 1:  # Sleep
                        sleep_minutes += 1
                        if current_awakening_length > 0:
                            awakening_lengths.append(current_awakening_length)
                            current_awakening_length = 0
                    # Only count awakenings AFTER first sleep epoch (ActiLife-compatible)
                    elif first_sleep_idx is not None and last_sleep_idx is not None and i > first_sleep_idx and i <= last_sleep_idx:
                        current_awakening_length += 1
                        if current_awakening_length == 1:  # Start of new awakening
                            awakenings += 1

                # Handle case where sleep period ends during an awakening
                if current_awakening_length > 0 and last_sleep_idx is not None:
                    awakening_lengths.append(current_awakening_length)

                # Calculate TIB from epoch count (exclusive range)
                from sleep_scoring_app.utils.calculations import calculate_total_minutes_in_bed_from_indices

                total_minutes_in_bed = calculate_total_minutes_in_bed_from_indices(onset_idx, offset_idx)

                # Calculate derived metrics
                if first_sleep_idx is not None and last_sleep_idx is not None:
                    total_sleep_time = sum(1 for i in range(first_sleep_idx, last_sleep_idx + 1) if sadeh_results[i] == 1)
                else:
                    total_sleep_time = 0

                # WASO: Wake time between first and last sleep epochs (ActiLife-compatible)
                if first_sleep_idx is not None and last_sleep_idx is not None:
                    sleep_period_length = last_sleep_idx - first_sleep_idx + 1
                    waso = sleep_period_length - total_sleep_time
                else:
                    waso = total_minutes_in_bed - total_sleep_time

                efficiency = (total_sleep_time / total_minutes_in_bed * 100) if total_minutes_in_bed > 0 else 0
                avg_awakening_length = sum(awakening_lengths) / len(awakening_lengths) if awakening_lengths else 0
                movement_index = movement_events / total_minutes_in_bed if total_minutes_in_bed > 0 else 0
                fragmentation_index = (awakenings / total_sleep_time * 100) if total_sleep_time > 0 else 0
                sleep_fragmentation_index = ((waso + movement_events) / total_minutes_in_bed * 100) if total_minutes_in_bed > 0 else 0

                # Calculate overlapping nonwear minutes during sleep period
                from sleep_scoring_app.utils.calculations import calculate_overlapping_nonwear_minutes

                overlapping_nonwear_minutes_algorithm = calculate_overlapping_nonwear_minutes(choi_results, onset_idx, offset_idx)
                overlapping_nonwear_minutes_sensor = calculate_overlapping_nonwear_minutes(nwt_sensor_results, onset_idx, offset_idx)
            else:
                # No algorithm data available - use None for all calculated metrics
                from sleep_scoring_app.utils.calculations import calculate_duration_minutes_from_timestamps

                total_minutes_in_bed = calculate_duration_minutes_from_timestamps(onset_timestamp, offset_timestamp)
                total_sleep_time = None
                waso = None
                efficiency = None
                awakenings = None
                avg_awakening_length = None
                movement_index = None
                fragmentation_index = None
                sleep_fragmentation_index = None
                overlapping_nonwear_minutes_algorithm = None
                overlapping_nonwear_minutes_sensor = None

            # Use passed algorithm_type or default to SADEH
            algo_type = algorithm_type or AlgorithmType.SADEH_1994_ACTILIFE

            return {
                "Full Participant ID": participant_info.full_id,
                "Numerical Participant ID": participant_info.numerical_id,
                "Participant Group": participant_info.group_str,
                "Participant Timepoint": participant_info.timepoint_str,
                "Sleep Algorithm": algo_type.value,
                "Onset Date": onset_dt.strftime("%Y-%m-%d"),
                "Onset Time": onset_dt.strftime("%H:%M"),
                "Offset Date": offset_dt.strftime("%Y-%m-%d"),
                "Offset Time": offset_dt.strftime("%H:%M"),
                "Total Counts": int(total_activity) if total_activity is not None else None,
                "Efficiency": round(efficiency, 2) if efficiency is not None else None,
                "Total Minutes in Bed": round(total_minutes_in_bed, 1),
                "Total Sleep Time (TST)": round(total_sleep_time, 1) if total_sleep_time is not None else None,
                "Wake After Sleep Onset (WASO)": round(waso, 1) if waso is not None else None,
                "Number of Awakenings": int(awakenings) if awakenings is not None else None,
                "Average Awakening Length": round(avg_awakening_length, 1) if avg_awakening_length is not None else None,
                "Movement Index": round(movement_index, 3) if movement_index is not None else None,
                "Fragmentation Index": round(fragmentation_index, 2) if fragmentation_index is not None else None,
                "Sleep Fragmentation Index": round(sleep_fragmentation_index, 2) if sleep_fragmentation_index is not None else None,
                "Sleep Algorithm Value at Onset": algorithm_onset if onset_idx is not None and onset_idx < len(sadeh_results) else None,
                "Sleep Algorithm Value at Offset": algorithm_offset if offset_idx is not None and offset_idx < len(sadeh_results) else None,
                "Overlapping Nonwear Minutes (Algorithm)": int(overlapping_nonwear_minutes_algorithm)
                if overlapping_nonwear_minutes_algorithm is not None
                else None,
                "Overlapping Nonwear Minutes (Sensor)": int(overlapping_nonwear_minutes_sensor)
                if overlapping_nonwear_minutes_sensor is not None
                else None,
            }

        except (ValueError, TypeError, KeyError, IndexError):
            logger.exception("Error calculating sleep metrics")
            return None

    def _find_closest_data_index(self, x_data: list[float] | None, timestamp: float) -> int | None:
        """
        Find the index of the closest data point to the given timestamp.

        Uses binary search (O(log n)) instead of linear search (O(n)) for efficiency.
        Assumes x_data is sorted in ascending order (which is guaranteed by
        database queries that ORDER BY timestamp).
        """
        if x_data is None or len(x_data) == 0:
            return None

        # Binary search to find insertion point
        idx = bisect.bisect_left(x_data, timestamp)

        # Handle edge cases
        if idx == 0:
            return 0
        if idx >= len(x_data):
            return len(x_data) - 1

        # Compare neighbors to find closest
        before = x_data[idx - 1]
        after = x_data[idx]

        if abs(timestamp - before) <= abs(after - timestamp):
            return idx - 1
        return idx

    def _dict_to_sleep_metrics(self, metrics_dict: dict, file_path: str | None = None) -> SleepMetrics:
        """Convert dictionary metrics to SleepMetrics object."""
        # Extract participant info from the dictionary
        numerical_id = metrics_dict.get("Numerical Participant ID", "Unknown")
        timepoint = metrics_dict.get("Participant Timepoint", "BO")
        group = metrics_dict.get("Participant Group", "G1")

        # Reconstruct full_id from all three components
        if numerical_id != "UNKNOWN":
            full_id = f"{numerical_id} {timepoint} {group}"
        else:
            full_id = metrics_dict.get("Full Participant ID", "Unknown BO G1")

        participant = ParticipantInfo(
            numerical_id=numerical_id,
            full_id=full_id,
            group=group,
            timepoint=timepoint,
            date=metrics_dict.get("Onset Date", ""),
            group_str=group,  # Set string representation for export
            timepoint_str=timepoint,  # Set string representation for export
        )

        # Create daily sleep markers from onset/offset data
        daily_markers = DailySleepMarkers()

        # Get timestamps from dictionary
        onset_time_str = metrics_dict.get("Onset Time", "")
        offset_time_str = metrics_dict.get("Offset Time", "")
        onset_date_str = metrics_dict.get("Onset Date", "")
        offset_date_str = metrics_dict.get("Offset Date", "")

        # Try to construct timestamps from date/time if available
        onset_timestamp = None
        offset_timestamp = None

        if onset_date_str and onset_time_str:
            try:
                onset_dt = datetime.strptime(f"{onset_date_str} {onset_time_str}", "%Y-%m-%d %H:%M")
                onset_timestamp = onset_dt.timestamp()
            except ValueError:
                onset_timestamp = None

        if offset_date_str and offset_time_str:
            try:
                offset_dt = datetime.strptime(f"{offset_date_str} {offset_time_str}", "%Y-%m-%d %H:%M")
                offset_timestamp = offset_dt.timestamp()
            except ValueError:
                offset_timestamp = None

        # Create sleep period if both timestamps are available
        if onset_timestamp is not None and offset_timestamp is not None:
            sleep_period = SleepPeriod(
                onset_timestamp=onset_timestamp,
                offset_timestamp=offset_timestamp,
            )
            daily_markers.period_1 = sleep_period

        # Calculate total minutes in bed if not present
        total_minutes_in_bed = metrics_dict.get("Total Minutes in Bed")
        if total_minutes_in_bed is None and onset_timestamp is not None and offset_timestamp is not None:
            from sleep_scoring_app.utils.calculations import calculate_duration_minutes_from_timestamps

            total_minutes_in_bed = calculate_duration_minutes_from_timestamps(onset_timestamp, offset_timestamp)

        # Create SleepMetrics object
        return SleepMetrics(
            participant=participant,
            filename=Path(file_path).name if file_path else metrics_dict.get("filename", ""),
            analysis_date=onset_date_str,
            algorithm_type=AlgorithmType.from_value(metrics_dict.get("Sleep Algorithm", AlgorithmType.SADEH_1994_ACTILIFE.value)),
            daily_sleep_markers=daily_markers,
            onset_time=onset_time_str,
            offset_time=offset_time_str,
            total_sleep_time=metrics_dict.get("Total Sleep Time (TST)"),
            sleep_efficiency=metrics_dict.get("Efficiency"),
            total_minutes_in_bed=int(total_minutes_in_bed) if total_minutes_in_bed is not None else None,
            waso=metrics_dict.get("Wake After Sleep Onset (WASO)"),
            awakenings=metrics_dict.get("Number of Awakenings"),
            average_awakening_length=metrics_dict.get("Average Awakening Length"),
            total_activity=metrics_dict.get("Total Counts"),
            movement_index=metrics_dict.get("Movement Index"),
            fragmentation_index=metrics_dict.get("Fragmentation Index"),
            sleep_fragmentation_index=metrics_dict.get("Sleep Fragmentation Index"),
            sleep_algorithm_onset=metrics_dict.get("Sleep Algorithm Value at Onset"),
            sleep_algorithm_offset=metrics_dict.get("Sleep Algorithm Value at Offset"),
            overlapping_nonwear_minutes_algorithm=metrics_dict.get("Overlapping Nonwear Minutes (Algorithm)"),
            overlapping_nonwear_minutes_sensor=metrics_dict.get("Overlapping Nonwear Minutes (Sensor)"),
            updated_at=datetime.now().isoformat(),
        )

    def calculate_sleep_metrics_for_period(
        self,
        sleep_period: SleepPeriod,
        sadeh_results,
        choi_results,
        axis_y_data,
        x_data,
        participant_info: ParticipantInfo,
        file_path: str | None = None,
        nwt_sensor_results=None,
        algorithm_type: AlgorithmType | None = None,
    ) -> dict[str, Any] | None:
        """Calculate sleep metrics for a specific sleep period."""
        if not sleep_period or not sleep_period.is_complete:
            return None

        # is_complete guarantees both timestamps are set
        assert sleep_period.onset_timestamp is not None
        assert sleep_period.offset_timestamp is not None

        # Use SleepPeriod timestamps directly
        metrics = self._calculate_sleep_metrics_from_timestamps(
            onset_timestamp=sleep_period.onset_timestamp,
            offset_timestamp=sleep_period.offset_timestamp,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            activity_data=axis_y_data,
            x_data=x_data,
            participant_info=participant_info,
            nwt_sensor_results=nwt_sensor_results,
            algorithm_type=algorithm_type,
        )

        if metrics:
            # Add period-specific metadata
            metrics["marker_type"] = sleep_period.marker_type.value if sleep_period.marker_type else None
            metrics["marker_index"] = sleep_period.marker_index
            metrics["period_duration_hours"] = sleep_period.duration_hours

        return metrics

    def calculate_sleep_metrics_for_period_object(
        self,
        sleep_period: SleepPeriod,
        sadeh_results,
        choi_results,
        axis_y_data,
        x_data,
        participant_info: ParticipantInfo,
        file_path: str | None = None,
        nwt_sensor_results=None,
        algorithm_type: AlgorithmType | None = None,
    ) -> SleepMetrics | None:
        """Calculate sleep metrics for a SleepPeriod and return as SleepMetrics object."""
        if not sleep_period or not sleep_period.is_complete:
            return None

        metrics_dict = self.calculate_sleep_metrics_for_period(
            sleep_period=sleep_period,
            sadeh_results=sadeh_results,
            choi_results=choi_results,
            axis_y_data=axis_y_data,
            x_data=x_data,
            participant_info=participant_info,
            file_path=file_path,
            nwt_sensor_results=nwt_sensor_results,
            algorithm_type=algorithm_type,
        )

        if metrics_dict is None:
            return None

        # Convert dictionary to SleepMetrics object
        sleep_metrics = self._dict_to_sleep_metrics(metrics_dict, file_path)

        # Set the actual sleep period directly (no parsing from strings)
        daily_markers = DailySleepMarkers()
        daily_markers.period_1 = sleep_period
        sleep_metrics.daily_sleep_markers = daily_markers

        return sleep_metrics

    def calculate_sleep_metrics_for_all_periods(
        self,
        daily_sleep_markers: DailySleepMarkers,
        sadeh_results,
        choi_results,
        axis_y_data,
        x_data,
        participant_info: ParticipantInfo,
        file_path: str | None = None,
        nwt_sensor_results=None,
        algorithm_type: AlgorithmType | None = None,
    ) -> list[dict[str, Any]]:
        """Calculate sleep metrics for all complete sleep periods."""
        all_metrics = []

        for period in daily_sleep_markers.get_complete_periods():
            period_metrics = self.calculate_sleep_metrics_for_period(
                period, sadeh_results, choi_results, axis_y_data, x_data, participant_info, file_path, nwt_sensor_results, algorithm_type
            )
            if period_metrics:
                all_metrics.append(period_metrics)

        return all_metrics
