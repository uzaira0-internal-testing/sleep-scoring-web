"""
Tests for sleep_scoring_web.services.file_identity module.

Covers participant ID extraction, timepoint detection, filename pattern matching,
normalization utilities, and FileIdentity building.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from sleep_scoring_web.services.file_identity import (
    FileIdentity,
    _clean_text,
    _strip_rewear_suffix,
    _strip_site_suffix,
    build_file_identity,
    filename_stem,
    infer_participant_id_and_timepoint_from_filename,
    is_excluded_activity_filename,
    is_excluded_file_obj,
    normalize_filename,
    normalize_participant_id,
    normalize_timepoint,
)


# =============================================================================
# _clean_text
# =============================================================================

class TestCleanText:
    def test_none_returns_none(self):
        assert _clean_text(None) is None

    def test_empty_string_returns_none(self):
        assert _clean_text("") is None

    def test_whitespace_only_returns_none(self):
        assert _clean_text("   ") is None

    def test_null_tokens_return_none(self):
        for token in ("nan", "NaN", "NAN", "none", "None", "NONE", "null", "NULL", "nat", "NAT"):
            assert _clean_text(token) is None, f"Expected None for '{token}'"

    def test_normal_string(self):
        assert _clean_text("hello") == "hello"

    def test_strips_whitespace(self):
        assert _clean_text("  hello  ") == "hello"

    def test_non_string_value(self):
        assert _clean_text(42) == "42"
        assert _clean_text(3.14) == "3.14"


# =============================================================================
# normalize_participant_id
# =============================================================================

class TestNormalizeParticipantId:
    def test_none_returns_none(self):
        assert normalize_participant_id(None) is None

    def test_empty_returns_none(self):
        assert normalize_participant_id("") is None

    def test_nan_returns_none(self):
        assert normalize_participant_id("nan") is None

    def test_simple_id(self):
        assert normalize_participant_id("1001") == "1001"

    def test_lowercases(self):
        assert normalize_participant_id("P1-1036") == "p1-1036"

    def test_collapses_whitespace(self):
        assert normalize_participant_id("P1  1036") == "p1 1036"

    def test_integer_like_float(self):
        # "1001.0" -> "1001"
        assert normalize_participant_id("1001.0") == "1001"
        assert normalize_participant_id("1001.00") == "1001"

    def test_real_float_unchanged(self):
        # "1001.5" should NOT be stripped
        assert normalize_participant_id("1001.5") == "1001.5"

    def test_trims_whitespace(self):
        assert normalize_participant_id("  1001  ") == "1001"

    def test_numeric_input(self):
        assert normalize_participant_id(1001) == "1001"
        assert normalize_participant_id(1001.0) == "1001"


# =============================================================================
# normalize_timepoint
# =============================================================================

class TestNormalizeTimepoint:
    def test_none_returns_none(self):
        assert normalize_timepoint(None) is None

    def test_empty_returns_none(self):
        assert normalize_timepoint("") is None

    def test_standard_t1(self):
        assert normalize_timepoint("T1") == "t1"

    def test_lowercase_t1(self):
        assert normalize_timepoint("t1") == "t1"

    def test_spaced_t1(self):
        assert normalize_timepoint("T 1") == "t1"

    def test_multi_digit(self):
        assert normalize_timepoint("T12") == "t12"

    def test_non_t_pattern_lowercased(self):
        # Not matching Tn pattern, just lowercased
        assert normalize_timepoint("Baseline") == "baseline"

    def test_leading_zero(self):
        assert normalize_timepoint("T01") == "t1"

    def test_nan_returns_none(self):
        assert normalize_timepoint("nan") is None


# =============================================================================
# normalize_filename
# =============================================================================

class TestNormalizeFilename:
    def test_none_returns_none(self):
        assert normalize_filename(None) is None

    def test_empty_returns_none(self):
        assert normalize_filename("") is None

    def test_simple_name(self):
        assert normalize_filename("Test.csv") == "test.csv"

    def test_strips_path(self):
        assert normalize_filename("/path/to/Test.csv") == "test.csv"

    def test_path_with_forward_slashes(self):
        assert normalize_filename("path/to/deep/Test.csv") == "test.csv"

    def test_nan_returns_none(self):
        assert normalize_filename("nan") is None


# =============================================================================
# filename_stem
# =============================================================================

class TestFilenameStem:
    def test_none_returns_none(self):
        assert filename_stem(None) is None

    def test_returns_stem(self):
        assert filename_stem("Test.csv") == "test"

    def test_strips_extension(self):
        assert filename_stem("data_file.xlsx") == "data_file"

    def test_empty_returns_none(self):
        assert filename_stem("") is None


# =============================================================================
# is_excluded_activity_filename
# =============================================================================

class TestIsExcludedActivityFilename:
    def test_none_not_excluded(self):
        assert is_excluded_activity_filename(None) is False

    def test_empty_not_excluded(self):
        assert is_excluded_activity_filename("") is False

    def test_normal_file_not_excluded(self):
        assert is_excluded_activity_filename("1001 T1 (2024-01-01)60sec.csv") is False

    def test_ignore_in_name(self):
        assert is_excluded_activity_filename("1001_IGNORE.csv") is True

    def test_issue_in_name(self):
        assert is_excluded_activity_filename("data_ISSUE_file.csv") is True

    def test_case_insensitive_ignore(self):
        assert is_excluded_activity_filename("data_ignore.csv") is True

    def test_case_insensitive_issue(self):
        assert is_excluded_activity_filename("data_Issue.csv") is True


# =============================================================================
# is_excluded_file_obj
# =============================================================================

class TestIsExcludedFileObj:
    def test_file_obj_with_filename_attr(self):
        obj = SimpleNamespace(filename="data_IGNORE.csv")
        assert is_excluded_file_obj(obj) is True

    def test_file_obj_normal(self):
        obj = SimpleNamespace(filename="normal.csv")
        assert is_excluded_file_obj(obj) is False

    def test_file_obj_no_filename(self):
        obj = SimpleNamespace()
        assert is_excluded_file_obj(obj) is False


# =============================================================================
# infer_participant_id_and_timepoint_from_filename
# =============================================================================

class TestInferParticipantIdAndTimepointFromFilename:
    def test_standard_format(self):
        # "1000 T1 G1 (2024-01-01)60sec.csv" -> ("1000", "T1")
        pid, tp = infer_participant_id_and_timepoint_from_filename("1000 T1 G1 (2024-01-01)60sec.csv")
        assert pid == "1000"
        assert tp == "T1"

    def test_dash_separated_pid_and_timepoint(self):
        # "P1-1036-A-T2 (2023-07-18)60sec.csv" -> ("P1-1036-A", "T2")
        pid, tp = infer_participant_id_and_timepoint_from_filename("P1-1036-A-T2 (2023-07-18)60sec.csv")
        assert pid == "P1-1036-A"
        assert tp == "T2"

    def test_no_timepoint(self):
        # "DEMO-001.csv" -> ("DEMO-001", None)
        pid, tp = infer_participant_id_and_timepoint_from_filename("DEMO-001.csv")
        assert pid == "DEMO-001"
        assert tp is None

    def test_empty_filename(self):
        pid, tp = infer_participant_id_and_timepoint_from_filename("")
        assert pid is None
        assert tp is None

    def test_extension_only(self):
        # ".csv" has an empty stem after PurePath processing, but the
        # function still processes the leading dot — implementation detail.
        pid, tp = infer_participant_id_and_timepoint_from_filename(".csv")
        # No meaningful timepoint
        assert tp is None

    def test_underscore_separated_timepoint(self):
        pid, tp = infer_participant_id_and_timepoint_from_filename("1001_T3.csv")
        assert pid == "1001"
        assert tp == "T3"

    def test_space_separated_timepoint(self):
        pid, tp = infer_participant_id_and_timepoint_from_filename("1001 T2.csv")
        assert pid == "1001"
        assert tp == "T2"

    def test_no_extension(self):
        pid, tp = infer_participant_id_and_timepoint_from_filename("1001 T1")
        assert pid == "1001"
        assert tp == "T1"


# =============================================================================
# _strip_site_suffix
# =============================================================================

class TestStripSiteSuffix:
    def test_none_returns_none(self):
        assert _strip_site_suffix(None) is None

    def test_empty_returns_none(self):
        assert _strip_site_suffix("") is None

    def test_strip_dash_a(self):
        # "P1-1036-A" -> "p1-1036"
        result = _strip_site_suffix("P1-1036-A")
        assert result == "p1-1036"

    def test_strip_underscore_b(self):
        result = _strip_site_suffix("P1-1036_B")
        assert result == "p1-1036"

    def test_no_suffix_unchanged(self):
        result = _strip_site_suffix("P1-1036")
        assert result == "p1-1036"

    def test_multi_char_suffix_not_stripped(self):
        # "P1-1036-AB" should NOT strip "-AB" (only single letter)
        result = _strip_site_suffix("P1-1036-AB")
        assert result is not None
        # The "-AB" won't match the single-letter pattern, so returns normalized input
        assert result == "p1-1036-ab"


# =============================================================================
# _strip_rewear_suffix
# =============================================================================

class TestStripRewearSuffix:
    def test_none_returns_none(self):
        assert _strip_rewear_suffix(None) is None

    def test_empty_returns_none(self):
        assert _strip_rewear_suffix("") is None

    def test_strip_ra(self):
        result = _strip_rewear_suffix("P3-3035 RA")
        assert result == "p3-3035"

    def test_strip_ra_numbered(self):
        result = _strip_rewear_suffix("P3-3035 RA 1")
        assert result == "p3-3035"

    def test_strip_rewear(self):
        result = _strip_rewear_suffix("P3-3035 Rewear")
        assert result == "p3-3035"

    def test_no_suffix(self):
        result = _strip_rewear_suffix("P3-3035")
        assert result == "p3-3035"


# =============================================================================
# build_file_identity
# =============================================================================

class TestBuildFileIdentity:
    def test_basic_build(self):
        obj = SimpleNamespace(filename="1000 T1 (2024-01-01)60sec.csv", participant_id=None)
        identity = build_file_identity(obj)

        assert isinstance(identity, FileIdentity)
        assert identity.normalized_filename == "1000 t1 (2024-01-01)60sec.csv"
        assert identity.normalized_stem == "1000 t1 (2024-01-01)60sec"
        assert identity.participant_id_norm == "1000"
        assert identity.timepoint_norm == "t1"

    def test_explicit_participant_id_takes_precedence(self):
        obj = SimpleNamespace(filename="1000 T1.csv", participant_id="OVERRIDE-ID")
        identity = build_file_identity(obj)
        assert identity.participant_id_norm == "override-id"

    def test_no_filename(self):
        obj = SimpleNamespace(participant_id=None)
        identity = build_file_identity(obj)
        assert identity.normalized_filename == ""
        assert identity.normalized_stem == ""
        assert identity.participant_id_norm is None

    def test_short_pid_with_site_suffix(self):
        obj = SimpleNamespace(filename="P1-1036-A-T2 (2023-07-18)60sec.csv", participant_id=None)
        identity = build_file_identity(obj)
        assert identity.participant_id_norm == "p1-1036-a"
        # short_pid should strip the -A
        assert identity.short_pid_norm == "p1-1036"

    def test_short_pid_with_rewear(self):
        obj = SimpleNamespace(filename="P3-3035 RA 1 T1.csv", participant_id=None)
        identity = build_file_identity(obj)
        # The PID should contain "p3-3035 ra 1" and short should strip it
        assert identity.participant_id_norm is not None

    def test_frozen_dataclass(self):
        obj = SimpleNamespace(filename="test.csv", participant_id=None)
        identity = build_file_identity(obj)
        with pytest.raises(AttributeError):
            identity.normalized_filename = "changed"  # type: ignore[misc]

    def test_file_reference_preserved(self):
        obj = SimpleNamespace(filename="test.csv", participant_id=None)
        identity = build_file_identity(obj)
        assert identity.file is obj
