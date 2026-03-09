#!/usr/bin/env python3
"""Fluent builder for AppConfig."""

from __future__ import annotations

import re
from typing import Any

from sleep_scoring_app.core.constants import (
    AlgorithmType,
    NonwearAlgorithm,
    SleepPeriodDetectorType,
)
from sleep_scoring_app.core.dataclasses_config import AppConfig


class ConfigBuilder:
    r"""
    Fluent builder for AppConfig with validation.

    Provides a chainable API for building AppConfig instances with validation
    at build time. All builder methods return self for method chaining.

    Example:
        >>> config = (
        ...     AppConfig.builder()
        ...     .with_sleep_algorithm(AlgorithmType.SADEH_1994_ACTILIFE.value)
        ...     .with_nonwear_algorithm(NonwearAlgorithm.CHOI_2011.value)
        ...     .with_night_hours(22, 6)
        ...     .with_study_patterns(id_pattern=r"(\\d{4})")
        ...     .build()
        ... )

    """

    def __init__(self) -> None:
        """Initialize builder with empty values dict."""
        self._values: dict[str, Any] = {}

    def with_sleep_algorithm(self, algorithm_id: str) -> ConfigBuilder:
        """
        Set sleep scoring algorithm.

        Args:
            algorithm_id: Algorithm identifier from AlgorithmType enum

        Returns:
            Self for method chaining

        Raises:
            ValueError: If algorithm_id is not a valid AlgorithmType value

        """
        # Validate algorithm exists
        valid_ids = [a.value for a in AlgorithmType]
        if algorithm_id not in valid_ids:
            msg = f"Unknown algorithm: {algorithm_id}. Valid: {valid_ids}"
            raise ValueError(msg)
        self._values["sleep_algorithm_id"] = algorithm_id
        return self

    def with_nonwear_algorithm(self, algorithm_id: str) -> ConfigBuilder:
        """
        Set nonwear detection algorithm.

        Args:
            algorithm_id: Algorithm identifier from NonwearAlgorithm enum

        Returns:
            Self for method chaining

        Raises:
            ValueError: If algorithm_id is not a valid NonwearAlgorithm value

        """
        # Validate algorithm exists
        valid_ids = [a.value for a in NonwearAlgorithm]
        if algorithm_id not in valid_ids:
            msg = f"Unknown nonwear algorithm: {algorithm_id}. Valid: {valid_ids}"
            raise ValueError(msg)
        self._values["nonwear_algorithm_id"] = algorithm_id
        return self

    def with_sleep_period_detector(self, detector_id: str) -> ConfigBuilder:
        """
        Set sleep period detector (onset/offset rule).

        Args:
            detector_id: Detector identifier from SleepPeriodDetectorType enum

        Returns:
            Self for method chaining

        Raises:
            ValueError: If detector_id is not a valid SleepPeriodDetectorType value

        """
        # Validate detector exists
        valid_ids = [d.value for d in SleepPeriodDetectorType]
        if detector_id not in valid_ids:
            msg = f"Unknown sleep period detector: {detector_id}. Valid: {valid_ids}"
            raise ValueError(msg)
        self._values["onset_offset_rule_id"] = detector_id
        return self

    def with_night_hours(self, start: int, end: int) -> ConfigBuilder:
        """
        Set night hour boundaries (24-hour format).

        Args:
            start: Night start hour (0-23)
            end: Night end hour (0-23)

        Returns:
            Self for method chaining

        Raises:
            ValueError: If hours are not in valid range (0-23)

        """
        if not (0 <= start <= 23 and 0 <= end <= 23):
            msg = "Hours must be 0-23"
            raise ValueError(msg)
        self._values["night_start_hour"] = start
        self._values["night_end_hour"] = end
        return self

    def with_study_patterns(
        self,
        id_pattern: str | None = None,
        group_pattern: str | None = None,
        timepoint_pattern: str | None = None,
    ) -> ConfigBuilder:
        """
        Set participant extraction patterns (validates regex).

        Args:
            id_pattern: Regex pattern for extracting participant ID from filename
            group_pattern: Regex pattern for extracting group from filename
            timepoint_pattern: Regex pattern for extracting timepoint from filename

        Returns:
            Self for method chaining

        Raises:
            re.error: If any pattern is not a valid regex

        """
        if id_pattern:
            re.compile(id_pattern)  # Raises re.error if invalid
            self._values["study_participant_id_patterns"] = [id_pattern]
        if group_pattern:
            re.compile(group_pattern)  # Raises re.error if invalid
            self._values["study_group_pattern"] = group_pattern
        if timepoint_pattern:
            re.compile(timepoint_pattern)  # Raises re.error if invalid
            self._values["study_timepoint_pattern"] = timepoint_pattern
        return self

    def with_study_defaults(
        self,
        default_group: str | None = None,
        default_timepoint: str | None = None,
        unknown_value: str | None = None,
    ) -> ConfigBuilder:
        """
        Set study default values for when extraction fails.

        Args:
            default_group: Default group value (e.g., "G1")
            default_timepoint: Default timepoint value (e.g., "T1")
            unknown_value: Value to use for unknown fields (e.g., "Unknown")

        Returns:
            Self for method chaining

        """
        if default_group is not None:
            self._values["study_default_group"] = default_group
        if default_timepoint is not None:
            self._values["study_default_timepoint"] = default_timepoint
        if unknown_value is not None:
            self._values["study_unknown_value"] = unknown_value
        return self

    def with_study_valid_values(
        self,
        valid_groups: list[str] | None = None,
        valid_timepoints: list[str] | None = None,
    ) -> ConfigBuilder:
        """
        Set valid values for categorical study fields.

        Args:
            valid_groups: List of valid group values (e.g., ["G1", "G2"])
            valid_timepoints: List of valid timepoint values (e.g., ["T1", "T2", "T3"])

        Returns:
            Self for method chaining

        """
        if valid_groups is not None:
            self._values["study_valid_groups"] = valid_groups
        if valid_timepoints is not None:
            self._values["study_valid_timepoints"] = valid_timepoints
        return self

    def with_export_settings(
        self,
        grouping: int = 0,
        include_headers: bool = True,
        include_metadata: bool = True,
    ) -> ConfigBuilder:
        """
        Set export preferences.

        Args:
            grouping: Export grouping mode (0=all, 1=participant, 2=group, 3=timepoint)
            include_headers: Whether to include column headers in CSV export
            include_metadata: Whether to include metadata comments in CSV export

        Returns:
            Self for method chaining

        Raises:
            ValueError: If grouping is not in valid range (0-3)

        """
        if not (0 <= grouping <= 3):
            msg = "Export grouping must be 0-3 (0=all, 1=participant, 2=group, 3=timepoint)"
            raise ValueError(msg)
        self._values["export_grouping"] = grouping
        self._values["include_headers"] = include_headers
        self._values["include_metadata"] = include_metadata
        return self

    def with_data_folder(self, path: str) -> ConfigBuilder:
        """
        Set default data folder.

        Args:
            path: Path to data folder

        Returns:
            Self for method chaining

        """
        self._values["data_folder"] = path
        return self

    def with_export_directory(self, path: str) -> ConfigBuilder:
        """
        Set export directory.

        Args:
            path: Path to export directory

        Returns:
            Self for method chaining

        """
        self._values["export_directory"] = path
        return self

    def with_import_directories(
        self,
        activity_dir: str | None = None,
        nonwear_dir: str | None = None,
        diary_dir: str | None = None,
        actilife_dir: str | None = None,
    ) -> ConfigBuilder:
        """
        Set import directories for various data types.

        Args:
            activity_dir: Directory for activity data imports
            nonwear_dir: Directory for nonwear data imports
            diary_dir: Directory for diary data imports
            actilife_dir: Directory for ActiLife data imports

        Returns:
            Self for method chaining

        """
        if activity_dir is not None:
            self._values["import_activity_directory"] = activity_dir
        if nonwear_dir is not None:
            self._values["import_nonwear_directory"] = nonwear_dir
        if diary_dir is not None:
            self._values["diary_import_directory"] = diary_dir
        if actilife_dir is not None:
            self._values["actilife_import_directory"] = actilife_dir
        return self

    def with_data_processing(
        self,
        epoch_length: int | None = None,
        skip_rows: int | None = None,
    ) -> ConfigBuilder:
        """
        Set data processing parameters.

        Args:
            epoch_length: Epoch length in seconds
            skip_rows: Number of header rows to skip in CSV files

        Returns:
            Self for method chaining

        Raises:
            ValueError: If epoch_length or skip_rows are negative

        """
        if epoch_length is not None:
            if epoch_length <= 0:
                msg = "Epoch length must be positive"
                raise ValueError(msg)
            self._values["epoch_length"] = epoch_length
        if skip_rows is not None:
            if skip_rows < 0:
                msg = "Skip rows must be non-negative"
                raise ValueError(msg)
            self._values["skip_rows"] = skip_rows
            self._values["import_skip_rows"] = skip_rows
            self._values["csv_skip_rows"] = skip_rows
        return self

    def with_auto_processing(
        self,
        auto_place_diary_markers: bool | None = None,
        auto_detect_nonwear_overlap: bool | None = None,
        auto_save_markers: bool | None = None,
    ) -> ConfigBuilder:
        """
        Set automatic processing flags.

        Args:
            auto_place_diary_markers: Automatically place markers from diary data
            auto_detect_nonwear_overlap: Automatically detect nonwear overlap with sleep
            auto_save_markers: Automatically save markers when navigating away

        Returns:
            Self for method chaining

        """
        if auto_place_diary_markers is not None:
            self._values["auto_place_diary_markers"] = auto_place_diary_markers
        if auto_detect_nonwear_overlap is not None:
            self._values["auto_detect_nonwear_overlap"] = auto_detect_nonwear_overlap
        if auto_save_markers is not None:
            self._values["auto_save_markers"] = auto_save_markers
        return self

    def build(self) -> AppConfig:
        """
        Build immutable config, applying defaults for unset values.

        Returns:
            Frozen AppConfig instance with all values set

        Note:
            AppConfig is @dataclass(frozen=True), so the result is immutable.

        """
        defaults = AppConfig.create_default()
        final_values = {**defaults.__dict__, **self._values}
        return AppConfig(**final_values)
