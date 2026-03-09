"""
Tests for participant information extractor.

Tests extraction of participant ID, timepoint, and group from filenames.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from sleep_scoring_app.core.constants import ParticipantGroup, ParticipantTimepoint
from sleep_scoring_app.core.dataclasses import ParticipantInfo
from sleep_scoring_app.utils.participant_extractor import (
    _extract_group,
    _extract_timepoint,
    _string_to_group_enum,
    _string_to_timepoint_enum,
    extract_participant_info,
)


@dataclass
class MockConfig:
    """Mock config for testing."""

    study_participant_id_patterns: list[str] | None = None
    study_timepoint_pattern: str | None = None
    study_group_pattern: str | None = None
    study_default_group: str | None = None
    study_default_timepoint: str | None = None


@pytest.fixture
def config_with_patterns() -> MockConfig:
    """Create mock config with participant ID patterns."""
    return MockConfig(
        study_participant_id_patterns=[r"(\d{4})"],  # 4-digit ID
        study_timepoint_pattern=r"(T\d)",  # T1, T2, T3
        study_group_pattern=r"(G\d)",  # G1, G2, G3
        study_default_group="G1",
        study_default_timepoint="T1",
    )


@pytest.fixture
def config_with_complex_patterns() -> MockConfig:
    """Create mock config with complex patterns."""
    return MockConfig(
        study_participant_id_patterns=[r"STUDY-(\d+)", r"(\d{5})"],
        study_timepoint_pattern=r"(BL|T1|T2|T3)",
        study_group_pattern=r"(CTRL|TREAT)",
        study_default_group="CTRL",
        study_default_timepoint="BL",
    )


class TestStringToTimepointEnum:
    """Tests for _string_to_timepoint_enum function."""

    def test_converts_t1(self) -> None:
        """Converts 'T1' to T1 enum."""
        result = _string_to_timepoint_enum("T1")

        assert result == ParticipantTimepoint.T1

    def test_converts_t2(self) -> None:
        """Converts 'T2' to T2 enum."""
        result = _string_to_timepoint_enum("T2")

        assert result == ParticipantTimepoint.T2

    def test_converts_t3(self) -> None:
        """Converts 'T3' to T3 enum."""
        result = _string_to_timepoint_enum("T3")

        assert result == ParticipantTimepoint.T3

    def test_case_insensitive(self) -> None:
        """Handles lowercase input."""
        result = _string_to_timepoint_enum("t1")

        assert result == ParticipantTimepoint.T1

    def test_unknown_returns_t1_default(self) -> None:
        """Unknown timepoints return T1 as default."""
        result = _string_to_timepoint_enum("T4")

        assert result == ParticipantTimepoint.T1

    def test_baseline_returns_t1_default(self) -> None:
        """Baseline returns T1 as default (string preserved in full_id)."""
        result = _string_to_timepoint_enum("BL")

        assert result == ParticipantTimepoint.T1


class TestStringToGroupEnum:
    """Tests for _string_to_group_enum function."""

    def test_converts_g1(self) -> None:
        """Converts 'G1' to GROUP_1 enum."""
        result = _string_to_group_enum("G1")

        assert result == ParticipantGroup.GROUP_1

    def test_converts_g2(self) -> None:
        """Converts 'G2' to GROUP_2 enum."""
        result = _string_to_group_enum("G2")

        assert result == ParticipantGroup.GROUP_2

    def test_converts_g3(self) -> None:
        """Converts 'G3' to GROUP_3 enum."""
        result = _string_to_group_enum("G3")

        assert result == ParticipantGroup.GROUP_3

    def test_converts_group_1(self) -> None:
        """Converts 'GROUP_1' to GROUP_1 enum."""
        result = _string_to_group_enum("GROUP_1")

        assert result == ParticipantGroup.GROUP_1

    def test_converts_issue(self) -> None:
        """Converts 'ISSUE' to ISSUE enum."""
        result = _string_to_group_enum("ISSUE")

        assert result == ParticipantGroup.ISSUE

    def test_converts_ignore(self) -> None:
        """Converts 'IGNORE' to ISSUE enum."""
        result = _string_to_group_enum("IGNORE")

        assert result == ParticipantGroup.ISSUE

    def test_case_insensitive(self) -> None:
        """Handles lowercase input."""
        result = _string_to_group_enum("g1")

        assert result == ParticipantGroup.GROUP_1

    def test_unknown_returns_group_1_default(self) -> None:
        """Unknown groups return GROUP_1 as default."""
        result = _string_to_group_enum("CTRL")

        assert result == ParticipantGroup.GROUP_1


class TestExtractTimepoint:
    """Tests for _extract_timepoint function."""

    def test_extracts_timepoint_with_pattern(self) -> None:
        """Extracts timepoint using pattern."""
        result = _extract_timepoint("1234_T2_G1.csv", r"(T\d)", "T1")

        assert result == "T2"

    def test_returns_default_when_no_match(self) -> None:
        """Returns default when pattern doesn't match."""
        result = _extract_timepoint("1234_G1.csv", r"(T\d)", "T1")

        assert result == "T1"

    def test_returns_default_when_no_pattern(self) -> None:
        """Returns default when pattern is None."""
        result = _extract_timepoint("1234_T2_G1.csv", None, "T1")

        assert result == "T1"

    def test_returns_default_when_pattern_is_na(self) -> None:
        """Returns default when pattern is 'N/A'."""
        result = _extract_timepoint("1234_T2_G1.csv", "N/A", "T1")

        assert result == "T1"

    def test_case_insensitive_matching(self) -> None:
        """Matches case-insensitively."""
        result = _extract_timepoint("1234_t2_G1.csv", r"(T\d)", "T1")

        assert result == "T2"

    def test_returns_uppercase(self) -> None:
        """Returns uppercase timepoint."""
        result = _extract_timepoint("1234_t2_G1.csv", r"(t\d)", "T1")

        assert result == "T2"


class TestExtractGroup:
    """Tests for _extract_group function."""

    def test_extracts_group_with_pattern(self) -> None:
        """Extracts group using pattern."""
        result = _extract_group("1234_T1_G2.csv", r"(G\d)", "G1")

        assert result == "G2"

    def test_returns_default_when_no_match(self) -> None:
        """Returns default when pattern doesn't match."""
        result = _extract_group("1234_T1.csv", r"(G\d)", "G1")

        assert result == "G1"

    def test_returns_default_when_no_pattern(self) -> None:
        """Returns default when pattern is None."""
        result = _extract_group("1234_T1_G2.csv", None, "G1")

        assert result == "G1"

    def test_returns_default_when_pattern_is_na(self) -> None:
        """Returns default when pattern is 'N/A'."""
        result = _extract_group("1234_T1_G2.csv", "N/A", "G1")

        assert result == "G1"

    def test_extracts_named_group(self) -> None:
        """Extracts named group (CTRL, TREAT)."""
        result = _extract_group("1234_TREAT_T1.csv", r"(CTRL|TREAT)", "CTRL")

        assert result == "TREAT"


class TestExtractParticipantInfo:
    """Tests for extract_participant_info function."""

    def test_returns_participant_info(self, config_with_patterns: MockConfig) -> None:
        """Returns ParticipantInfo object."""
        result = extract_participant_info("1234_T1_G1.csv", config=config_with_patterns)

        assert isinstance(result, ParticipantInfo)

    def test_extracts_numerical_id(self, config_with_patterns: MockConfig) -> None:
        """Extracts numerical ID from filename."""
        result = extract_participant_info("1234_T1_G1.csv", config=config_with_patterns)

        assert result.numerical_id == "1234"

    def test_extracts_timepoint(self, config_with_patterns: MockConfig) -> None:
        """Extracts timepoint from filename."""
        result = extract_participant_info("1234_T2_G1.csv", config=config_with_patterns)

        assert result.timepoint == ParticipantTimepoint.T2
        assert result.timepoint_str == "T2"

    def test_extracts_group(self, config_with_patterns: MockConfig) -> None:
        """Extracts group from filename."""
        result = extract_participant_info("1234_T1_G2.csv", config=config_with_patterns)

        assert result.group == ParticipantGroup.GROUP_2
        assert result.group_str == "G2"

    def test_creates_full_id(self, config_with_patterns: MockConfig) -> None:
        """Creates full ID from components."""
        result = extract_participant_info("1234_T2_G3.csv", config=config_with_patterns)

        assert "1234" in result.full_id
        assert "T2" in result.full_id
        assert "G3" in result.full_id

    def test_returns_unknown_for_empty_input(self, config_with_patterns: MockConfig) -> None:
        """Returns UNKNOWN for empty input."""
        result = extract_participant_info("", config=config_with_patterns)

        assert result.numerical_id == "UNKNOWN"

    def test_returns_unknown_when_no_patterns_configured(self) -> None:
        """Returns UNKNOWN when no patterns configured."""
        config = MockConfig(study_participant_id_patterns=None)

        result = extract_participant_info("1234_T1_G1.csv", config=config)

        assert result.numerical_id == "UNKNOWN"

    def test_returns_unknown_when_empty_patterns_list(self) -> None:
        """Returns UNKNOWN when patterns list is empty."""
        config = MockConfig(study_participant_id_patterns=[])

        result = extract_participant_info("1234_T1_G1.csv", config=config)

        assert result.numerical_id == "UNKNOWN"

    def test_returns_unknown_when_no_pattern_matches(self, config_with_patterns: MockConfig) -> None:
        """Returns UNKNOWN when no pattern matches."""
        result = extract_participant_info("no_id_here.csv", config=config_with_patterns)

        assert result.numerical_id == "UNKNOWN"

    def test_tries_multiple_patterns(self, config_with_complex_patterns: MockConfig) -> None:
        """Tries multiple patterns until one matches."""
        # First pattern looks for STUDY-XXX, second for 5 digits
        result = extract_participant_info("12345_T1.csv", config=config_with_complex_patterns)

        assert result.numerical_id == "12345"

    def test_matches_first_pattern_first(self, config_with_complex_patterns: MockConfig) -> None:
        """Matches first pattern before trying second."""
        result = extract_participant_info("STUDY-999.csv", config=config_with_complex_patterns)

        assert result.numerical_id == "999"

    def test_uses_default_group_when_not_matched(self, config_with_complex_patterns: MockConfig) -> None:
        """Uses default group when pattern doesn't match."""
        result = extract_participant_info("STUDY-123.csv", config=config_with_complex_patterns)

        # No CTRL or TREAT in filename, should use default
        assert result.group_str == "CTRL"

    def test_uses_default_timepoint_when_not_matched(self, config_with_complex_patterns: MockConfig) -> None:
        """Uses default timepoint when pattern doesn't match."""
        result = extract_participant_info("STUDY-123.csv", config=config_with_complex_patterns)

        # No BL, T1, T2, T3 in filename, should use default
        assert result.timepoint_str == "BL"

    def test_handles_invalid_regex_pattern_gracefully(self) -> None:
        """Handles invalid regex pattern gracefully."""
        config = MockConfig(
            study_participant_id_patterns=["[invalid regex"],  # Missing closing bracket
            study_default_group="G1",
            study_default_timepoint="T1",
        )

        result = extract_participant_info("1234.csv", config=config)

        # Should not raise, returns UNKNOWN
        assert result.numerical_id == "UNKNOWN"

    def test_strips_whitespace_from_input(self, config_with_patterns: MockConfig) -> None:
        """Strips whitespace from input string."""
        result = extract_participant_info("  1234_T1_G1.csv  ", config=config_with_patterns)

        assert result.numerical_id == "1234"

    def test_loads_global_config_when_none_provided(self) -> None:
        """Uses module-level global config when none provided."""
        from sleep_scoring_app.utils.participant_extractor import set_global_config

        mock_config = MockConfig(
            study_participant_id_patterns=[r"(\d{4})"],
            study_default_group="G1",
            study_default_timepoint="T1",
        )
        set_global_config(mock_config)
        try:
            result = extract_participant_info("1234.csv")
            assert result.numerical_id == "1234"
        finally:
            set_global_config(None)
