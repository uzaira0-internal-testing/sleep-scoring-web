"""
Tests for PatternValidationService.

Tests regex pattern validation and participant extraction testing.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.services.pattern_validation_service import (
    ExtractionTestResult,
    PatternValidationResult,
    PatternValidationService,
)


class TestValidatePattern:
    """Tests for validate_pattern method."""

    def test_valid_simple_pattern(self) -> None:
        """Valid simple pattern passes validation."""
        result = PatternValidationService.validate_pattern(r"^\d+")

        assert result.is_valid is True
        assert result.error_message is None

    def test_valid_complex_pattern(self) -> None:
        """Valid complex pattern passes validation."""
        result = PatternValidationService.validate_pattern(r"^(\d{4})[_-]([A-Z]+)_(\d+)")

        assert result.is_valid is True

    def test_empty_pattern_is_valid(self) -> None:
        """Empty pattern is considered valid (neutral)."""
        result = PatternValidationService.validate_pattern("")

        assert result.is_valid is True

    def test_whitespace_pattern_is_valid(self) -> None:
        """Whitespace-only pattern is considered valid."""
        result = PatternValidationService.validate_pattern("   ")

        assert result.is_valid is True

    def test_invalid_pattern_unbalanced_paren(self) -> None:
        """Unbalanced parentheses fails validation."""
        result = PatternValidationService.validate_pattern(r"(\d+")

        assert result.is_valid is False
        assert result.error_message is not None

    def test_invalid_pattern_bad_quantifier(self) -> None:
        """Invalid quantifier fails validation."""
        result = PatternValidationService.validate_pattern(r"+")

        assert result.is_valid is False

    def test_invalid_pattern_bad_escape(self) -> None:
        """Invalid escape sequence fails validation."""
        # Using single backslash as non-raw string
        result = PatternValidationService.validate_pattern("\\")

        assert result.is_valid is False


class TestTestExtraction:
    """Tests for test_extraction method."""

    def test_empty_input_returns_empty_result(self) -> None:
        """Empty input returns result with no participant info."""
        config = MagicMock()

        result = PatternValidationService.test_extraction(
            test_input="",
            config=config,
            valid_groups=["G1", "G2"],
            valid_timepoints=["T1", "T2"],
            default_group="G1",
            default_timepoint="T1",
        )

        assert result.test_input == ""
        assert result.participant_info is None

    def test_successful_extraction(self) -> None:
        """Successful extraction returns all status fields."""
        config = MagicMock()

        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "1234"
            mock_info.group_str = "G1"
            mock_info.timepoint_str = "T1"
            mock_extract.return_value = mock_info

            result = PatternValidationService.test_extraction(
                test_input="1234_G1_T1.csv",
                config=config,
                valid_groups=["G1", "G2"],
                valid_timepoints=["T1", "T2"],
                default_group="CTRL",
                default_timepoint="BL",
            )

        assert result.participant_info is mock_info
        assert result.id_icon == "✓"
        assert result.group_icon == "✓"
        assert result.timepoint_icon == "✓"

    def test_valid_id_green_status(self) -> None:
        """Valid ID shows green status."""
        config = MagicMock()

        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "1234"
            mock_info.group_str = "G1"
            mock_info.timepoint_str = "T1"
            mock_extract.return_value = mock_info

            result = PatternValidationService.test_extraction(
                test_input="1234_G1_T1.csv",
                config=config,
                valid_groups=["G1"],
                valid_timepoints=["T1"],
                default_group="CTRL",
                default_timepoint="BL",
            )

        assert result.id_color == "#28a745"  # green

    def test_default_group_yellow_status(self) -> None:
        """Using default group shows yellow status."""
        config = MagicMock()

        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_info = MagicMock()
            mock_info.numerical_id = "1234"
            mock_info.group_str = "CTRL"  # Default
            mock_info.timepoint_str = "T1"
            mock_extract.return_value = mock_info

            result = PatternValidationService.test_extraction(
                test_input="1234.csv",
                config=config,
                valid_groups=["G1", "G2"],
                valid_timepoints=["T1"],
                default_group="CTRL",
                default_timepoint="BL",
            )

        assert result.group_icon == "⚠"
        assert result.group_color == "#ffc107"  # yellow

    def test_extraction_error_returns_message(self) -> None:
        """Extraction error returns error message."""
        config = MagicMock()

        with patch("sleep_scoring_app.utils.participant_extractor.extract_participant_info") as mock_extract:
            mock_extract.side_effect = ValueError("Test error")

            result = PatternValidationService.test_extraction(
                test_input="bad_input",
                config=config,
                valid_groups=["G1"],
                valid_timepoints=["T1"],
                default_group="CTRL",
                default_timepoint="BL",
            )

        assert result.error_message is not None
        assert "Test error" in result.error_message


class TestGetDefaultPatterns:
    """Tests for get_default_patterns method."""

    def test_returns_id_pattern(self) -> None:
        """Returns ID pattern."""
        patterns = PatternValidationService.get_default_patterns()

        assert "id_pattern" in patterns
        assert patterns["id_pattern"]

    def test_returns_timepoint_pattern(self) -> None:
        """Returns timepoint pattern."""
        patterns = PatternValidationService.get_default_patterns()

        assert "timepoint_pattern" in patterns

    def test_returns_group_pattern(self) -> None:
        """Returns group pattern."""
        patterns = PatternValidationService.get_default_patterns()

        assert "group_pattern" in patterns


class TestFormatTestResultHtml:
    """Tests for format_test_result_html method."""

    def test_empty_input_shows_placeholder(self) -> None:
        """Empty input shows placeholder message."""
        result = ExtractionTestResult(test_input="", participant_info=None)

        html = PatternValidationService.format_test_result_html(result)

        assert "Enter an ID" in html
        assert "italic" in html

    def test_error_shows_red(self) -> None:
        """Error result shows red message."""
        result = ExtractionTestResult(
            test_input="bad",
            participant_info=None,
            error_message="Something went wrong",
        )

        html = PatternValidationService.format_test_result_html(result)

        assert "dc3545" in html  # red color
        assert "Something went wrong" in html

    def test_successful_result_shows_all_fields(self) -> None:
        """Successful result shows all extraction fields."""
        result = ExtractionTestResult(
            test_input="1234_G1_T1.csv",
            participant_info=MagicMock(),
            id_status="1234",
            id_color="#28a745",
            id_icon="✓",
            group_status="G1",
            group_color="#28a745",
            group_icon="✓",
            timepoint_status="T1",
            timepoint_color="#28a745",
            timepoint_icon="✓",
        )

        html = PatternValidationService.format_test_result_html(result)

        assert "1234_G1_T1.csv" in html
        assert "ID:" in html
        assert "Group:" in html
        assert "Timepoint:" in html
