#!/usr/bin/env python3
"""Simple participant extraction - extracts participant info from filenames."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from sleep_scoring_app.core.constants import ParticipantGroup, ParticipantTimepoint
from sleep_scoring_app.core.dataclasses import ParticipantInfo

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import AppConfig

logger = logging.getLogger(__name__)

# Module-level config reference (set by application at startup via set_global_config)
# This replaces the previous upward import from ui.utils.config (layer violation)
_global_config: AppConfig | None = None

# Track if we've already warned about missing patterns (to avoid spam)
_warned_no_patterns = False


def set_global_config(config: AppConfig | None) -> None:
    """
    Set the module-level config for participant extraction.

    Called by the application at startup (e.g., from MainWindow or ConfigManager)
    so that callers of extract_participant_info don't need to pass config explicitly.
    """
    global _global_config
    _global_config = config


def extract_participant_info(input_string: str, config: AppConfig | None = None) -> ParticipantInfo:
    """
    Extract participant info from input string.

    Args:
        input_string: Filename or string to extract from
        config: AppConfig with patterns and defaults. If None, falls back to
                the module-level config set via set_global_config().

    Returns:
        ParticipantInfo with extracted data

    """
    if not input_string:
        # Return defaults for empty input
        return ParticipantInfo(
            numerical_id="UNKNOWN", timepoint=ParticipantTimepoint.T1, group=ParticipantGroup.GROUP_1, timepoint_str="T1", group_str="G1"
        )

    input_string = str(input_string).strip()

    # If no config provided, use module-level config
    if config is None:
        config = _global_config

    # Get configured patterns if available
    # JUSTIFIED hasattr: Config attributes may be None or missing in older config versions
    id_patterns_from_config = []
    if config and hasattr(config, "study_participant_id_patterns") and config.study_participant_id_patterns:
        id_patterns_from_config = config.study_participant_id_patterns

    # Get timepoint pattern from config (with fallback to default)
    # JUSTIFIED hasattr: Config attribute may be None or missing in older config versions
    timepoint_pattern = None
    if config and hasattr(config, "study_timepoint_pattern") and config.study_timepoint_pattern:
        timepoint_pattern = config.study_timepoint_pattern

    # Get group pattern from config (with fallback to default)
    # JUSTIFIED hasattr: Config attribute may be None or missing in older config versions
    group_pattern = None
    if config and hasattr(config, "study_group_pattern") and config.study_group_pattern:
        group_pattern = config.study_group_pattern

    # Get default values from config (use configured defaults, not first item in valid lists)
    # JUSTIFIED hasattr: Config attributes may be None or missing in older config versions
    default_group = "G1"
    default_timepoint = "T1"
    if config and hasattr(config, "study_default_group") and config.study_default_group:
        default_group = config.study_default_group
    if config and hasattr(config, "study_default_timepoint") and config.study_default_timepoint:
        default_timepoint = config.study_default_timepoint

    # Try configured patterns - if none configured or none match, return UNKNOWN
    if not id_patterns_from_config:
        global _warned_no_patterns
        if not _warned_no_patterns:
            _warned_no_patterns = True
            logger.warning("No participant ID patterns configured. Configure patterns in Study Settings.")
        return ParticipantInfo(
            numerical_id="UNKNOWN",
            timepoint=ParticipantTimepoint.T1,
            group=ParticipantGroup.GROUP_1,
            full_id="UNKNOWN T1 G1",
            timepoint_str=default_timepoint,
            group_str=default_group,
        )

    for pattern_str in id_patterns_from_config:
        try:
            pattern = re.compile(pattern_str, re.IGNORECASE)
            match = pattern.search(input_string)

            if match:
                groups = match.groups()

                # The first capture group is always the participant ID
                if len(groups) >= 1:
                    numerical_id = groups[0]

                    # Extract timepoint using configured pattern
                    timepoint = _extract_timepoint(input_string, timepoint_pattern, default_timepoint)

                    # Extract group using configured pattern
                    group_str = _extract_group(input_string, group_pattern, default_group)

                    # Convert to enums (with flexible mapping)
                    timepoint_enum = _string_to_timepoint_enum(timepoint)
                    group_enum = _string_to_group_enum(group_str)

                    logger.debug("Extracted participant ID '%s' using configured pattern '%s'", numerical_id, pattern_str)
                    return ParticipantInfo(
                        numerical_id=numerical_id,
                        timepoint=timepoint_enum,
                        group=group_enum,
                        full_id=f"{numerical_id} {timepoint} {group_str}",
                        timepoint_str=timepoint,
                        group_str=group_str,
                    )
        except re.error as e:
            logger.exception("Invalid regex pattern '%s': %s", pattern_str, e)
            continue

    # No patterns matched - log which patterns were tried
    logger.warning(
        "No configured patterns matched input '%s'. Configured patterns: %s",
        input_string,
        id_patterns_from_config,
    )
    return ParticipantInfo(
        numerical_id="UNKNOWN",
        timepoint=ParticipantTimepoint.T1,
        group=ParticipantGroup.GROUP_1,
        full_id="UNKNOWN T1 G1",
        timepoint_str=default_timepoint,
        group_str=default_group,
    )


def _extract_timepoint(input_string: str, pattern: str | None, default: str) -> str:
    """Extract timepoint from string using configured pattern."""
    if not pattern or pattern.upper() == "N/A":
        # No pattern configured, use default
        return default

    try:
        regex = re.compile(pattern, re.IGNORECASE)
        match = regex.search(input_string)
        if match:
            # Return the first capture group if present, otherwise the full match
            if match.groups():
                return match.group(1).upper()
            return match.group(0).upper()
    except re.error as e:
        logger.warning("Invalid timepoint regex pattern '%s': %s", pattern, e)

    return default


def _extract_group(input_string: str, pattern: str | None, default: str) -> str:
    """Extract group from string using configured pattern."""
    if not pattern or pattern.upper() == "N/A":
        # No pattern configured, use default
        return default

    try:
        regex = re.compile(pattern, re.IGNORECASE)
        match = regex.search(input_string)
        if match:
            # Return the first capture group if present, otherwise the full match
            if match.groups():
                return match.group(1).upper()
            return match.group(0).upper()
    except re.error as e:
        logger.warning("Invalid group regex pattern '%s': %s", pattern, e)

    return default


def _string_to_timepoint_enum(timepoint: str) -> ParticipantTimepoint:
    """Convert timepoint string to enum with flexible mapping."""
    timepoint = timepoint.upper()
    # Direct enum value match
    if timepoint == "T1":
        return ParticipantTimepoint.T1
    if timepoint == "T2":
        return ParticipantTimepoint.T2
    if timepoint == "T3":
        return ParticipantTimepoint.T3
    # For any other value, return T1 as default but the string will be preserved in full_id
    return ParticipantTimepoint.T1


def _string_to_group_enum(group: str) -> ParticipantGroup:
    """Convert group string to enum with flexible mapping."""
    group = group.upper()
    # Check for known enum values
    if group in ("G1", "GROUP_1", "GROUP1"):
        return ParticipantGroup.GROUP_1
    if group in ("G2", "GROUP_2", "GROUP2"):
        return ParticipantGroup.GROUP_2
    if group in ("G3", "GROUP_3", "GROUP3"):
        return ParticipantGroup.GROUP_3
    if group in ("ISSUE", "IGNORE"):
        return ParticipantGroup.ISSUE
    # For any other value, return GROUP_1 as default but the string will be preserved in full_id
    return ParticipantGroup.GROUP_1
