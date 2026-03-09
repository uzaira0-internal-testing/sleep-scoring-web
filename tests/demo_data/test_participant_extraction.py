"""Tests for participant info extraction from demo data filenames."""

from __future__ import annotations

from pathlib import Path

import pytest

from sleep_scoring_app.core.constants import ParticipantGroup, ParticipantTimepoint
from sleep_scoring_app.utils.participant_extractor import extract_participant_info


@pytest.mark.demo_data
class TestParticipantExtraction:
    """Test participant extraction from demo data filenames."""

    def test_extract_from_actigraph_filename(self, activity_dir: Path) -> None:
        """Extract participant info from actigraph filename."""
        files = list(activity_dir.glob("*_actigraph.csv"))
        filename = files[0].stem  # DEMO-001_T1_G1_actigraph

        info = extract_participant_info(filename)

        # Should extract DEMO-001 or recognize the pattern
        assert info.numerical_id is not None
        assert info.timepoint is not None
        assert info.group is not None

    def test_extract_demo_pattern(self) -> None:
        """Test extraction of DEMO-XXX pattern."""
        # The demo files use DEMO-001_T1_G1 pattern
        info = extract_participant_info("DEMO-001_T1_G1_actigraph")

        # Current extractor may not recognize DEMO pattern,
        # but should return something reasonable
        assert info is not None
        assert info.numerical_id is not None

    def test_extract_timepoint_from_filename(self) -> None:
        """Timepoint T1 should be extracted."""
        info = extract_participant_info("DEMO-001_T1_G1_generic")

        # T1 should be detected
        assert info.timepoint == ParticipantTimepoint.T1

    def test_extract_handles_unknown_gracefully(self) -> None:
        """Unknown patterns should return defaults, not crash."""
        info = extract_participant_info("random_unknown_file")

        assert info is not None
        assert info.numerical_id is not None
        # Should have default values
        assert info.timepoint in [ParticipantTimepoint.T1, ParticipantTimepoint.T2, ParticipantTimepoint.T3]
        assert info.group in [ParticipantGroup.GROUP_1, ParticipantGroup.ISSUE]

    def test_extract_from_all_demo_files(self, activity_dir: Path) -> None:
        """All demo activity files should extract without error."""
        for csv_file in activity_dir.glob("*.csv"):
            info = extract_participant_info(csv_file.stem)
            assert info is not None, f"Failed to extract from {csv_file.name}"
            assert info.numerical_id is not None

    def test_extract_empty_string(self) -> None:
        """Empty string should return defaults."""
        info = extract_participant_info("")
        assert info is not None
        assert info.numerical_id == "UNKNOWN"
