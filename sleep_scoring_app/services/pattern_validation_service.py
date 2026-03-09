"""
Pattern Validation Service
Pure service for validating regex patterns and testing participant extraction.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sleep_scoring_app.core.dataclasses import AppConfig
    from sleep_scoring_app.utils.participant_extractor import ParticipantInfo

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PatternValidationResult:
    """Result of pattern validation."""

    is_valid: bool
    error_message: str | None = None


@dataclass(frozen=True)
class ExtractionTestResult:
    """Result of testing participant extraction."""

    test_input: str
    participant_info: ParticipantInfo | None
    error_message: str | None = None
    id_status: str = ""
    id_color: str = ""
    id_icon: str = ""
    group_status: str = ""
    group_color: str = ""
    group_icon: str = ""
    timepoint_status: str = ""
    timepoint_color: str = ""
    timepoint_icon: str = ""


class PatternValidationService:
    """Service for validating regex patterns and testing participant extraction."""

    @staticmethod
    def validate_pattern(pattern: str) -> PatternValidationResult:
        """
        Validate a regex pattern.

        Args:
            pattern: The regex pattern to validate

        Returns:
            PatternValidationResult with validation status

        """
        if not pattern.strip():
            # Empty pattern is valid (neutral)
            return PatternValidationResult(is_valid=True)

        try:
            # Test compile the regex
            re.compile(pattern)
            return PatternValidationResult(is_valid=True)
        except re.error as e:
            return PatternValidationResult(is_valid=False, error_message=str(e))

    @staticmethod
    def test_extraction(
        test_input: str,
        config: AppConfig,
        valid_groups: list[str],
        valid_timepoints: list[str],
        default_group: str,
        default_timepoint: str,
    ) -> ExtractionTestResult:
        """
        Test participant extraction with current patterns.

        Args:
            test_input: The test ID or filename to extract from
            config: Application config with patterns
            valid_groups: List of valid groups
            valid_timepoints: List of valid timepoints
            default_group: Default group value
            default_timepoint: Default timepoint value

        Returns:
            ExtractionTestResult with extraction results and status

        """
        if not test_input.strip():
            return ExtractionTestResult(test_input="", participant_info=None)

        try:
            from sleep_scoring_app.utils.participant_extractor import extract_participant_info

            # Extract participant info using current patterns
            participant_info = extract_participant_info(test_input, config)

            # Evaluate ID extraction
            id_value = participant_info.numerical_id
            if id_value and id_value not in (default_group, "Unknown"):
                id_color = "#28a745"  # green
                id_icon = "✓"
                id_status = f'"{id_value}" (matched pattern)'
            else:
                id_color = "#dc3545"  # red
                id_icon = "✗"
                id_status = "not extracted"

            # Evaluate Group extraction
            group_value = participant_info.group_str
            if group_value.upper() in [g.upper() for g in valid_groups]:
                group_color = "#28a745"  # green
                group_icon = "✓"
                group_status = f'"{group_value}" (✓ valid group)'
            elif group_value == default_group:
                group_color = "#ffc107"  # yellow
                group_icon = "⚠"
                group_status = f'"{group_value}" (⚠ Could not extract group from input, using default value)'
            else:
                group_color = "#ffc107"  # yellow
                group_icon = "⚠"
                group_status = f'"{group_value}" (✗ Could not extract group from input, using default value)'

            # Evaluate Timepoint extraction
            timepoint_value = participant_info.timepoint_str
            if timepoint_value.upper() in [tp.upper() for tp in valid_timepoints]:
                timepoint_color = "#28a745"  # green
                timepoint_icon = "✓"
                timepoint_status = f'"{timepoint_value}" (✓ valid timepoint)'
            elif timepoint_value == default_timepoint:
                timepoint_color = "#ffc107"  # yellow
                timepoint_icon = "⚠"
                timepoint_status = f'"{timepoint_value}" (⚠ Could not extract timepoint from input, using default value)'
            else:
                timepoint_color = "#ffc107"  # yellow
                timepoint_icon = "⚠"
                timepoint_status = f'"{timepoint_value}" (✗ Could not extract timepoint from input, using default value)'

            return ExtractionTestResult(
                test_input=test_input,
                participant_info=participant_info,
                id_status=id_status,
                id_color=id_color,
                id_icon=id_icon,
                group_status=group_status,
                group_color=group_color,
                group_icon=group_icon,
                timepoint_status=timepoint_status,
                timepoint_color=timepoint_color,
                timepoint_icon=timepoint_icon,
            )

        except Exception as e:
            logger.exception("Error testing extraction: %s", e)
            return ExtractionTestResult(
                test_input=test_input,
                participant_info=None,
                error_message=str(e),
            )

    @staticmethod
    def get_default_patterns() -> dict[str, str]:
        """
        Get default regex patterns.

        Returns:
            Dictionary with default patterns

        """
        return {
            "id_pattern": r"^(\d{4,})[_-]",
            "timepoint_pattern": r"([A-Z0-9]+)",
            "group_pattern": r"g[123]",
        }

    @staticmethod
    def format_test_result_html(result: ExtractionTestResult) -> str:
        """
        Format extraction test result as HTML.

        Args:
            result: The extraction test result

        Returns:
            HTML string for display

        """
        if not result.test_input:
            return """
                <div style="color: #666; font-style: italic;">
                    Enter an ID or filename above to see extraction results...
                </div>
            """

        if result.error_message:
            return f"""
                <div style="color: #dc3545; font-family: monospace; font-size: 12px;">
                    <b>Extraction Error:</b><br>
                    {result.error_message}
                </div>
            """

        return f"""
            <div style="font-family: monospace; font-size: 12px;">
                <b>Test ID:</b> "{result.test_input}"<br><br>
                <b>Extraction Results:</b><br>
                <span style="color: {result.id_color};">{result.id_icon} ID:</span> {result.id_status}<br>
                <span style="color: {result.group_color};">{result.group_icon} Group:</span> {result.group_status}<br>
                <span style="color: {result.timepoint_color};">{result.timepoint_icon} Timepoint:</span> {result.timepoint_status}<br><br>
            </div>
        """
