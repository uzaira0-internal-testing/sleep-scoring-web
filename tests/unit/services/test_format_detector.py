"""
Tests for FormatDetector service.

Tests file format detection, header row detection, and device identification.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sleep_scoring_app.core.constants import DevicePreset
from sleep_scoring_app.services.format_detector import FormatDetector


@pytest.fixture
def detector() -> FormatDetector:
    """Create a FormatDetector instance."""
    return FormatDetector()


class TestDetectHeaderRows:
    """Tests for detect_header_rows method."""

    def test_detects_actigraph_header(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Detects ActiGraph metadata header."""
        csv_file = tmp_path / "actigraph.csv"
        csv_file.write_text(
            "------------ Data File Created By ActiGraph -----------\n"
            "Serial Number: ABC123\n"
            "Start Time 00:00:00\n"
            "Start Date 01/15/2024\n"
            "Epoch Period 00:01:00\n"
            "Download Time 12:00:00\n"
            "Download Date 01/16/2024\n"
            "Current Memory Address: 0\n"
            "Current Battery Voltage: 4.0\n"
            "--------------------------------------------------\n"
            "Date,Time,Axis1\n"
            "01/15/2024,00:00:00,0\n"
        )

        skip_rows, confidence = detector.detect_header_rows(csv_file)

        assert skip_rows == 10
        assert 0.0 <= confidence <= 1.0

    def test_detects_simple_csv_without_metadata(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Returns lower skip_rows for CSV without metadata headers."""
        csv_file = tmp_path / "simple.csv"
        # Create a CSV with column header and multiple data rows
        lines = ["Date,Time,Axis1\n"]
        for i in range(20):
            minute = str(i).zfill(2)
            lines.append(f"01/15/2024,00:{minute}:00,{100 + i}\n")
        csv_file.write_text("".join(lines))

        skip_rows, confidence = detector.detect_header_rows(csv_file)

        # For a simple CSV with no metadata header, skip_rows should be 0
        # The first data row is at index 1, so skip_rows = 1 - 1 = 0
        assert skip_rows == 0
        assert confidence >= 0.0

    def test_returns_tuple(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Returns tuple of (skip_rows, confidence)."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("datetime,Axis1\n2024-01-15 08:00:00,100\n")

        result = detector.detect_header_rows(csv_file)

        assert isinstance(result, tuple)
        assert len(result) == 2


class TestDetectEpochLength:
    """Tests for detect_epoch_length method."""

    def test_detects_60_second_epoch(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Detects 60-second epoch length."""
        csv_file = tmp_path / "epoch_60s.csv"
        lines = ["datetime,Axis1\n"]
        for i in range(10):
            lines.append(f"2024-01-15 00:{i:02d}:00,{100 + i}\n")
        csv_file.write_text("".join(lines))

        epoch_length, confidence = detector.detect_epoch_length(csv_file, skip_rows=0)

        assert epoch_length == 60
        assert confidence > 0.5

    def test_detects_30_second_epoch(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Detects 30-second epoch length."""
        csv_file = tmp_path / "epoch_30s.csv"
        lines = ["datetime,Axis1\n"]
        for i in range(20):
            minute = i // 2
            second = (i % 2) * 30
            lines.append(f"2024-01-15 00:{minute:02d}:{second:02d},{100 + i}\n")
        csv_file.write_text("".join(lines))

        epoch_length, confidence = detector.detect_epoch_length(csv_file, skip_rows=0)

        assert epoch_length == 30
        assert confidence > 0.5

    def test_returns_tuple(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Returns tuple of (epoch_seconds, confidence)."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("datetime,Axis1\n2024-01-15 08:00:00,100\n2024-01-15 08:01:00,105\n")

        result = detector.detect_epoch_length(csv_file, skip_rows=0)

        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_handles_no_data(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Returns fallback for file with no data."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("datetime,Axis1\n")

        epoch_length, confidence = detector.detect_epoch_length(csv_file, skip_rows=0)

        # Should return default fallback
        assert epoch_length == 60
        assert confidence <= 0.5


class TestDetectDeviceFormat:
    """Tests for detect_device_format method."""

    def test_detects_actigraph_columns(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Detects ActiGraph format from column names."""
        csv_file = tmp_path / "actigraph.csv"
        csv_file.write_text("Date,Time,Axis1,Axis2,Axis3,Vector Magnitude\n01/15/2024,00:00:00,100,50,25,112\n")

        device, confidence = detector.detect_device_format(csv_file)

        assert device == DevicePreset.ACTIGRAPH
        assert confidence > 0.5

    def test_detects_geneactiv_columns(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Detects GENEActiv format from column names."""
        csv_file = tmp_path / "geneactiv.csv"
        csv_file.write_text("timestamp,x,y,z,SVM,Temperature\n2024-01-15 00:00:00,0.1,0.2,-0.8,0.9,25.0\n")

        device, confidence = detector.detect_device_format(csv_file)

        assert device == DevicePreset.GENEACTIV
        assert confidence > 0.5

    def test_returns_generic_for_unknown(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Returns GENERIC_CSV for unknown format."""
        csv_file = tmp_path / "unknown.csv"
        csv_file.write_text("col1,col2,col3\na,b,c\n")

        device, _confidence = detector.detect_device_format(csv_file)

        assert device == DevicePreset.GENERIC_CSV

    def test_returns_tuple(self, detector: FormatDetector, tmp_path: Path) -> None:
        """Returns tuple of (device_preset, confidence)."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("datetime,Axis1\n2024-01-15 08:00:00,100\n")

        result = detector.detect_device_format(csv_file)

        assert isinstance(result, tuple)
        assert len(result) == 2


class TestTryParseDatetime:
    """Tests for _try_parse_datetime method."""

    def test_parses_iso_format(self, detector: FormatDetector) -> None:
        """Parses ISO datetime format."""
        result = detector._try_parse_datetime("2024-01-15 08:30:45")

        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 8

    def test_parses_us_format(self, detector: FormatDetector) -> None:
        """Parses US datetime format."""
        result = detector._try_parse_datetime("01/15/2024 08:30:45")

        assert result is not None
        assert result.month == 1
        assert result.day == 15

    def test_parses_separate_date_time(self, detector: FormatDetector) -> None:
        """Parses separate date and time strings."""
        result = detector._try_parse_datetime("01/15/2024", "08:30:45")

        assert result is not None
        assert result.hour == 8

    def test_returns_none_for_invalid(self, detector: FormatDetector) -> None:
        """Returns None for invalid datetime string."""
        result = detector._try_parse_datetime("not a date")

        assert result is None


class TestIsDataRow:
    """Tests for _is_data_row method."""

    def test_identifies_data_row(self, detector: FormatDetector) -> None:
        """Identifies valid data row."""
        row = ["2024-01-15 08:00:00", "100", "50", "25"]

        result = detector._is_data_row(row)

        assert result is True

    def test_identifies_data_row_separate_date_time(self, detector: FormatDetector) -> None:
        """Identifies data row with separate date/time."""
        row = ["01/15/2024", "08:00:00", "100", "50"]

        result = detector._is_data_row(row)

        assert result is True

    def test_rejects_header_row(self, detector: FormatDetector) -> None:
        """Rejects header row with text labels."""
        row = ["Date", "Time", "Axis1", "Axis2"]

        result = detector._is_data_row(row)

        assert result is False

    def test_rejects_short_row(self, detector: FormatDetector) -> None:
        """Rejects row with too few columns."""
        row = ["2024-01-15"]

        result = detector._is_data_row(row)

        assert result is False
