"""Tests for REDCap wide-format diary converter."""

import polars as pl
import pytest

from sleep_scoring_web.services.redcap_diary_converter import (
    _combine_time,
    _convert_reason,
    _safe_num,
    _safe_str,
    convert_redcap_wide_to_long,
    is_redcap_wide_format,
)


# ---------------------------------------------------------------------------
# Helpers to build test DataFrames
# ---------------------------------------------------------------------------


def _make_wide_columns(days: int = 1) -> dict[str, list]:
    """Build minimal REDCap wide-format column data for the given number of days."""
    data: dict[str, list] = {}
    for d in range(1, days + 1):
        v = f"_v{d}"
        # Only include columns needed for detection + basic extraction
        data[f"id{v}"] = ["P3-3001"]
        data[f"date_lastnight{v}"] = ["2025-06-01"] if d == 1 else [""]
        data[f"time_ampm{v}"] = [2]  # PM
        data[f"inbed_hour{v}"] = [7]
        data[f"inbed_min{v}"] = [50]
        data[f"asleep_hour{v}"] = [8]
        data[f"asleep_min{v}"] = [0]
        data[f"time_ampm_2{v}"] = [2]  # PM
        data[f"wake_hour{v}"] = [6]
        data[f"wake_min{v}"] = [57]
        data[f"time_ampm_3{v}"] = [1]  # AM
    return data


def _make_full_day_data(day: int = 1) -> dict[str, list]:
    """Build a complete single-day REDCap block with naps and nonwear."""
    v = f"_v{day}"
    return {
        f"id{v}": ["P3-3001"],
        f"date_lastnight{v}": ["2025-06-01"],
        # Bed time: 7:50 PM
        f"time_ampm{v}": [2],
        f"inbed_hour{v}": [7],
        f"inbed_min{v}": [50],
        # Lights out: 8:00 PM
        f"asleep_hour{v}": [8],
        f"asleep_min{v}": [0],
        f"time_ampm_2{v}": [2],
        # Wake: 6:57 AM
        f"wake_hour{v}": [6],
        f"wake_min{v}": [57],
        f"time_ampm_3{v}": [1],
        # Nap 1: 1:30 PM - 2:15 PM
        f"napstart_hour_1{v}": [1],
        f"napstart_min_1{v}": [30],
        f"time_ampm_10{v}": [2],
        f"napend_hour_1{v}": [2],
        f"napend_min_1{v}": [15],
        f"time_ampm_13{v}": [2],
        # Nap 2: empty
        f"napstart_hour_2{v}": [None],
        f"napstart_min_2{v}": [None],
        f"time_ampm_11{v}": [None],
        f"napend_hour_2{v}": [None],
        f"napend_min_2{v}": [None],
        f"time_ampm_14{v}": [None],
        # Nap 3: empty
        f"napstart_hour_3{v}": [None],
        f"napstart_min_3{v}": [None],
        f"time_ampm_12{v}": [None],
        f"napend_hour_3{v}": [None],
        f"napend_min_3{v}": [None],
        f"time_ampm_15{v}": [None],
        # Nonwear 1: 9:00 AM - 9:20 AM, Bath/Shower
        f"takeoffstart_hour_1{v}": [9],
        f"takeoffstart_min_1{v}": [0],
        f"time_ampm_16{v}": [1],
        f"takeoffend_hour_1{v}": [9],
        f"takeoffend_min_1{v}": [20],
        f"time_ampm_17{v}": [1],
        f"why_timeoff_1{v}": [1],
        # Nonwear 2: empty
        f"takeoffstart_hour_2{v}": [None],
        f"takeoffstart_min_2{v}": [None],
        f"time_ampm_18{v}": [None],
        f"takeoffend_hour_2{v}": [None],
        f"takeoffend_min_2{v}": [None],
        f"time_ampm_19{v}": [None],
        f"why_timeoff_2{v}": [None],
        # Nonwear 3: empty
        f"takeoffstart_hour_3{v}": [None],
        f"takeoffstart_min_3{v}": [None],
        f"time_ampm_20{v}": [None],
        f"takeoffend_hour_3{v}": [None],
        f"takeoffend_min_3{v}": [None],
        f"time_ampm_21{v}": [None],
        f"why_timeoff_3{v}": [None],
    }


# ===========================================================================
# Detection tests
# ===========================================================================


class TestIsRedcapWideFormat:
    def test_detects_valid_wide_format(self):
        cols = ["id_v1", "date_lastnight_v1", "inbed_hour_v1", "other_col"]
        assert is_redcap_wide_format(cols) is True

    def test_case_insensitive(self):
        cols = ["ID_V1", "Date_Lastnight_V1", "INBED_HOUR_V1"]
        assert is_redcap_wide_format(cols) is True

    def test_rejects_long_format(self):
        cols = ["participant_id", "startdate", "in_bed_time", "sleep_onset_time"]
        assert is_redcap_wide_format(cols) is False

    def test_rejects_partial_match(self):
        cols = ["id_v1", "date_lastnight_v1"]  # missing inbed_hour_v1
        assert is_redcap_wide_format(cols) is False

    def test_empty_columns(self):
        assert is_redcap_wide_format([]) is False

    def test_strips_whitespace(self):
        cols = ["  id_v1 ", " date_lastnight_v1", "inbed_hour_v1  "]
        assert is_redcap_wide_format(cols) is True


# ===========================================================================
# Conversion tests
# ===========================================================================


class TestConvertRedcapWideToLong:
    def test_basic_sleep_times(self):
        """Verify bed, lights-out, and wake times convert correctly."""
        data = _make_wide_columns(days=1)
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)

        assert result.height == 1
        row = result.row(0, named=True)
        assert row["participant_id"] == "P3-3001"
        assert row["startdate"] == "2025-06-01"
        assert row["in_bed_time"] == "19:50"  # 7:50 PM
        assert row["sleep_onset_time"] == "20:00"  # 8:00 PM
        assert row["sleep_offset_time"] == "06:57"  # 6:57 AM

    def test_am_pm_conversion_12am(self):
        """12 AM should convert to 00:xx."""
        data = _make_wide_columns(days=1)
        data["wake_hour_v1"] = [12]
        data["wake_min_v1"] = [30]
        data["time_ampm_3_v1"] = [1]  # AM
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.row(0, named=True)["sleep_offset_time"] == "00:30"

    def test_am_pm_conversion_12pm(self):
        """12 PM should stay as 12:xx."""
        data = _make_wide_columns(days=1)
        data["wake_hour_v1"] = [12]
        data["wake_min_v1"] = [0]
        data["time_ampm_3_v1"] = [2]  # PM
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.row(0, named=True)["sleep_offset_time"] == "12:00"

    def test_skips_days_without_date(self):
        """Days with empty date_lastnight should be skipped."""
        data = _make_wide_columns(days=2)
        # Day 2 has empty date (already set by helper)
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.height == 1  # Only day 1

    def test_multiple_days(self):
        """Multiple days in a single row produce multiple output rows."""
        data = _make_wide_columns(days=3)
        data["date_lastnight_v2"] = ["2025-06-02"]
        data["date_lastnight_v3"] = ["2025-06-03"]
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.height == 3
        dates = result["startdate"].to_list()
        assert dates == ["2025-06-01", "2025-06-02", "2025-06-03"]

    def test_multiple_participants(self):
        """Multiple rows (participants) are handled."""
        data = _make_wide_columns(days=1)
        # Add second participant row
        for col in data:
            data[col] = data[col] + (["P3-3002"] if col == "id_v1" else data[col])
        data["date_lastnight_v1"] = ["2025-06-01", "2025-06-01"]
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.height == 2
        pids = result["participant_id"].to_list()
        assert set(pids) == {"P3-3001", "P3-3002"}

    def test_nap_times(self):
        """Nap start/end times convert correctly."""
        data = _make_full_day_data(day=1)
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        row = result.row(0, named=True)
        assert row["napstart_1_time"] == "13:30"  # 1:30 PM
        assert row["napend_1_time"] == "14:15"  # 2:15 PM
        assert row["nap_onset_time_2"] is None
        assert row["nap_offset_time_2"] is None

    def test_nonwear_times_and_reason(self):
        """Nonwear start/end/reason convert correctly."""
        data = _make_full_day_data(day=1)
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        row = result.row(0, named=True)
        assert row["nonwear_start_time"] == "09:00"
        assert row["nonwear_end_time"] == "09:20"
        assert row["nonwear_reason"] == "Bath/Shower"
        assert row["nonwear_start_time_2"] is None
        assert row["nonwear_reason_2"] is None

    def test_nonwear_reason_codes(self):
        """All nonwear reason codes map correctly."""
        data = _make_full_day_data(day=1)
        data["why_timeoff_1_v1"] = [2]  # Swimming
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.row(0, named=True)["nonwear_reason"] == "Swimming"

        data["why_timeoff_1_v1"] = [3]  # Other
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.row(0, named=True)["nonwear_reason"] == "Other"

    def test_empty_dataframe(self):
        """Empty input returns empty output with correct schema."""
        data = _make_wide_columns(days=1)
        data["date_lastnight_v1"] = [""]  # No valid date
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.height == 0
        assert "participant_id" in result.columns
        assert "startdate" in result.columns

    def test_output_columns_match_importer(self):
        """Output columns should match what _DESKTOP_COLUMN_ALIASES expects."""
        data = _make_full_day_data(day=1)
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        expected_cols = {
            "participant_id",
            "startdate",
            "in_bed_time",
            "sleep_onset_time",
            "sleep_offset_time",
            "napstart_1_time",
            "napend_1_time",
            "nap_onset_time_2",
            "nap_offset_time_2",
            "nap_onset_time_3",
            "nap_offset_time_3",
            "nonwear_start_time",
            "nonwear_end_time",
            "nonwear_reason",
            "nonwear_start_time_2",
            "nonwear_end_time_2",
            "nonwear_reason_2",
            "nonwear_start_time_3",
            "nonwear_end_time_3",
            "nonwear_reason_3",
        }
        assert set(result.columns) == expected_cols

    def test_float_values_handled(self):
        """Hour/minute values stored as floats (e.g., 7.0) are handled."""
        data = _make_wide_columns(days=1)
        data["inbed_hour_v1"] = [7.0]
        data["inbed_min_v1"] = [50.0]
        data["time_ampm_v1"] = [2.0]
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.row(0, named=True)["in_bed_time"] == "19:50"

    def test_uppercase_columns(self):
        """Mixed-case column names are handled."""
        data = {}
        data["ID_V1"] = ["P3-3001"]
        data["Date_Lastnight_V1"] = ["2025-06-01"]
        data["Time_AMPM_V1"] = [2]
        data["Inbed_Hour_V1"] = [7]
        data["Inbed_Min_V1"] = [50]
        data["Asleep_Hour_V1"] = [8]
        data["Asleep_Min_V1"] = [0]
        data["Time_AMPM_2_V1"] = [2]
        data["Wake_Hour_V1"] = [6]
        data["Wake_Min_V1"] = [57]
        data["Time_AMPM_3_V1"] = [1]
        df = pl.DataFrame(data)
        result = convert_redcap_wide_to_long(df)
        assert result.height == 1
        assert result.row(0, named=True)["in_bed_time"] == "19:50"


# ===========================================================================
# Internal helper tests
# ===========================================================================


class TestSafeStr:
    def test_returns_value(self):
        assert _safe_str({"a": "hello"}, "a", {"a"}) == "hello"

    def test_returns_none_for_missing_col(self):
        assert _safe_str({"a": "hello"}, "b", {"a"}) is None

    def test_returns_none_for_nan(self):
        assert _safe_str({"a": "nan"}, "a", {"a"}) is None

    def test_returns_none_for_none(self):
        assert _safe_str({"a": None}, "a", {"a"}) is None

    def test_returns_none_for_empty(self):
        assert _safe_str({"a": ""}, "a", {"a"}) is None


class TestSafeNum:
    def test_returns_int(self):
        assert _safe_num({"a": "7"}, "a", {"a"}) == 7

    def test_handles_float_string(self):
        assert _safe_num({"a": "7.0"}, "a", {"a"}) == 7

    def test_returns_none_for_invalid(self):
        assert _safe_num({"a": "abc"}, "a", {"a"}) is None


class TestCombineTime:
    def test_am_regular(self):
        row = {"h": 6, "m": 30, "ap": 1}
        assert _combine_time(row, "h", "m", "ap", {"h", "m", "ap"}) == "06:30"

    def test_pm_regular(self):
        row = {"h": 7, "m": 50, "ap": 2}
        assert _combine_time(row, "h", "m", "ap", {"h", "m", "ap"}) == "19:50"

    def test_12am(self):
        row = {"h": 12, "m": 0, "ap": 1}
        assert _combine_time(row, "h", "m", "ap", {"h", "m", "ap"}) == "00:00"

    def test_12pm(self):
        row = {"h": 12, "m": 0, "ap": 2}
        assert _combine_time(row, "h", "m", "ap", {"h", "m", "ap"}) == "12:00"

    def test_missing_hour(self):
        row = {"m": 30, "ap": 1}
        assert _combine_time(row, "h", "m", "ap", {"h", "m", "ap"}) is None


class TestConvertReason:
    def test_bath_shower(self):
        assert _convert_reason({"r": "1"}, "r", {"r"}) == "Bath/Shower"

    def test_swimming(self):
        assert _convert_reason({"r": "2"}, "r", {"r"}) == "Swimming"

    def test_other(self):
        assert _convert_reason({"r": "3"}, "r", {"r"}) == "Other"

    def test_float_code(self):
        assert _convert_reason({"r": "1.0"}, "r", {"r"}) == "Bath/Shower"

    def test_unknown_code_passthrough(self):
        assert _convert_reason({"r": "99"}, "r", {"r"}) == "99"

    def test_none(self):
        assert _convert_reason({"r": None}, "r", {"r"}) is None
