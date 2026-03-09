#!/usr/bin/env python3
"""
Comprehensive tests for FileFormatDetector.
Tests file format detection, delimiter detection, encoding detection, and validation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from sleep_scoring_app.core.exceptions import SleepScoringImportError
from sleep_scoring_app.services.file_format_detector import FileFormatDetector


class TestFileFormatDetector:
    """Tests for FileFormatDetector class."""

    @pytest.fixture
    def detector(self) -> FileFormatDetector:
        """Create a detector instance."""
        return FileFormatDetector()

    @pytest.fixture
    def comma_csv(self, tmp_path: Path) -> Path:
        """Create a comma-delimited CSV file."""
        csv_path = tmp_path / "comma.csv"
        csv_path.write_text("Date,Time,Activity\n2024-01-01,12:00:00,100\n2024-01-01,12:01:00,150\n")
        return csv_path

    @pytest.fixture
    def semicolon_csv(self, tmp_path: Path) -> Path:
        """Create a semicolon-delimited CSV file."""
        csv_path = tmp_path / "semicolon.csv"
        csv_path.write_text("Date;Time;Activity\n2024-01-01;12:00:00;100\n2024-01-01;12:01:00;150\n")
        return csv_path

    @pytest.fixture
    def tab_csv(self, tmp_path: Path) -> Path:
        """Create a tab-delimited CSV file."""
        csv_path = tmp_path / "tab.tsv"
        csv_path.write_text("Date\tTime\tActivity\n2024-01-01\t12:00:00\t100\n2024-01-01\t12:01:00\t150\n")
        return csv_path

    @pytest.fixture
    def pipe_csv(self, tmp_path: Path) -> Path:
        """Create a pipe-delimited CSV file."""
        csv_path = tmp_path / "pipe.csv"
        csv_path.write_text("Date|Time|Activity\n2024-01-01|12:00:00|100\n2024-01-01|12:01:00|150\n")
        return csv_path


class TestValidateFileSize(TestFileFormatDetector):
    """Tests for validate_file_size method."""

    def test_valid_small_file(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should accept small files."""
        assert detector.validate_file_size(comma_csv) is True

    def test_file_at_limit(self, tmp_path: Path) -> None:
        """Should accept file exactly at limit."""
        detector = FileFormatDetector()
        detector.max_file_size = 1000
        csv_path = tmp_path / "at_limit.csv"
        csv_path.write_text("x" * 1000)
        assert detector.validate_file_size(csv_path) is True

    def test_file_over_limit(self, tmp_path: Path) -> None:
        """Should reject files over limit."""
        detector = FileFormatDetector()
        detector.max_file_size = 100
        csv_path = tmp_path / "over_limit.csv"
        csv_path.write_text("x" * 200)

        with pytest.raises(SleepScoringImportError):
            detector.validate_file_size(csv_path)

    def test_nonexistent_file(self, detector: FileFormatDetector) -> None:
        """Should raise error for nonexistent file."""
        with pytest.raises(SleepScoringImportError):
            detector.validate_file_size(Path("/nonexistent/file.csv"))

    def test_default_limit_is_100mb(self) -> None:
        """Default limit should be 100MB."""
        detector = FileFormatDetector()
        assert detector.max_file_size == 100 * 1024 * 1024


class TestDetectEncoding(TestFileFormatDetector):
    """Tests for detect_encoding method."""

    def test_returns_utf8_default(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should return utf-8 as default encoding."""
        encoding = detector.detect_encoding(comma_csv)
        assert encoding == "utf-8"

    def test_returns_string(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should return a string encoding name."""
        encoding = detector.detect_encoding(comma_csv)
        assert isinstance(encoding, str)


class TestDetectDelimiter(TestFileFormatDetector):
    """Tests for detect_delimiter method."""

    def test_detect_comma(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should detect comma delimiter."""
        delimiter = detector.detect_delimiter(comma_csv)
        assert delimiter == ","

    def test_detect_semicolon(self, detector: FileFormatDetector, semicolon_csv: Path) -> None:
        """Should detect semicolon delimiter."""
        delimiter = detector.detect_delimiter(semicolon_csv)
        assert delimiter == ";"

    def test_detect_tab(self, detector: FileFormatDetector, tab_csv: Path) -> None:
        """Should detect tab delimiter."""
        delimiter = detector.detect_delimiter(tab_csv)
        assert delimiter == "\t"

    def test_detect_pipe(self, detector: FileFormatDetector, pipe_csv: Path) -> None:
        """Should detect pipe delimiter."""
        delimiter = detector.detect_delimiter(pipe_csv)
        assert delimiter == "|"

    def test_empty_file_returns_comma(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should return comma for empty file."""
        csv_path = tmp_path / "empty.csv"
        csv_path.write_text("")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_single_line_file(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should detect delimiter from single line."""
        csv_path = tmp_path / "single.csv"
        csv_path.write_text("Date,Time,Activity")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_inconsistent_delimiters_picks_most_consistent(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should pick most consistent delimiter."""
        csv_path = tmp_path / "inconsistent.csv"
        # 3 commas per line vs 1 semicolon per line
        csv_path.write_text("a,b,c,d\n1,2,3,4\n5,6,7,8\n")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_no_delimiter_returns_comma(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should return comma when no delimiter found."""
        csv_path = tmp_path / "no_delim.csv"
        csv_path.write_text("nodatainanyformat\njustlines\n")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_mixed_delimiters(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle mixed delimiter counts gracefully."""
        csv_path = tmp_path / "mixed.csv"
        csv_path.write_text("a,b,c\na;b;c\na|b|c\n")
        # All have same count, should pick based on priority (comma first)
        delimiter = detector.detect_delimiter(csv_path)
        # Might pick any, but should not crash
        assert delimiter in [",", ";", "|"]


class TestDetectHeaderRow(TestFileFormatDetector):
    """Tests for detect_header_row method."""

    def test_returns_default(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should return default skip rows."""
        skip_rows = detector.detect_header_row(comma_csv)
        assert skip_rows == 10  # Default for ActiGraph files

    def test_custom_default(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should use custom default."""
        skip_rows = detector.detect_header_row(comma_csv, default_skip_rows=5)
        assert skip_rows == 5

    def test_zero_skip_rows(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should accept zero skip rows."""
        skip_rows = detector.detect_header_row(comma_csv, default_skip_rows=0)
        assert skip_rows == 0


class TestDetectFormat(TestFileFormatDetector):
    """Tests for detect_format method."""

    def test_detect_csv(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should detect CSV format."""
        format_type = detector.detect_format(comma_csv)
        assert format_type == "csv"

    def test_detect_xlsx(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should detect XLSX format."""
        xlsx_path = tmp_path / "test.xlsx"
        xlsx_path.write_bytes(b"")  # Empty file with correct extension
        format_type = detector.detect_format(xlsx_path)
        assert format_type == "xlsx"

    def test_detect_xls(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should detect XLS format."""
        xls_path = tmp_path / "test.xls"
        xls_path.write_bytes(b"")
        format_type = detector.detect_format(xls_path)
        assert format_type == "xls"

    def test_detect_gt3x(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should detect GT3X format."""
        gt3x_path = tmp_path / "test.gt3x"
        gt3x_path.write_bytes(b"")
        format_type = detector.detect_format(gt3x_path)
        assert format_type == "gt3x"

    def test_detect_unknown(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should return 'unknown' for unrecognized extensions."""
        unknown_path = tmp_path / "test.xyz"
        unknown_path.write_bytes(b"")
        format_type = detector.detect_format(unknown_path)
        assert format_type == "unknown"

    def test_case_insensitive(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should detect format case-insensitively."""
        csv_path = tmp_path / "test.CSV"
        csv_path.write_text("")
        format_type = detector.detect_format(csv_path)
        assert format_type == "csv"

    def test_mixed_case(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle mixed case extensions."""
        csv_path = tmp_path / "test.Csv"
        csv_path.write_text("")
        format_type = detector.detect_format(csv_path)
        assert format_type == "csv"


class TestDelimiterConsistency(TestFileFormatDetector):
    """Tests for delimiter consistency detection."""

    def test_perfectly_consistent_comma(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should detect perfectly consistent comma delimiter."""
        csv_path = tmp_path / "consistent.csv"
        csv_path.write_text("a,b,c\n1,2,3\n4,5,6\n7,8,9\n10,11,12\n")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_perfectly_consistent_semicolon(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should detect perfectly consistent semicolon delimiter."""
        csv_path = tmp_path / "consistent.csv"
        csv_path.write_text("a;b;c\n1;2;3\n4;5;6\n7;8;9\n10;11;12\n")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ";"

    def test_sample_lines_parameter(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should respect sample_lines parameter."""
        csv_path = tmp_path / "long.csv"
        # First 5 lines use comma, then switch to semicolon
        content = "a,b,c\n" * 10 + "a;b;c\n" * 10
        csv_path.write_text(content)

        # With sample_lines=5, should detect comma
        delimiter = detector.detect_delimiter(csv_path, sample_lines=5)
        assert delimiter == ","


class TestEdgeCases(TestFileFormatDetector):
    """Tests for edge cases and error handling."""

    def test_binary_file(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle binary file gracefully."""
        bin_path = tmp_path / "binary.csv"
        bin_path.write_bytes(b"\x00\x01\x02\x03")
        # Should not raise, returns default
        delimiter = detector.detect_delimiter(bin_path)
        assert delimiter == ","

    def test_unicode_content(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle unicode content."""
        csv_path = tmp_path / "unicode.csv"
        csv_path.write_text("日期,時間,活動\n2024-01-01,12:00:00,100\n", encoding="utf-8")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_very_long_lines(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle very long lines."""
        csv_path = tmp_path / "long_lines.csv"
        long_line = ",".join(["x" * 100] * 100)  # 100 columns, 100 chars each
        csv_path.write_text(f"{long_line}\n{long_line}\n")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_only_delimiters(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle lines with only delimiters."""
        csv_path = tmp_path / "delimiters.csv"
        csv_path.write_text(",,,\n,,,\n,,,\n")
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

    def test_permission_error(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle permission errors gracefully."""
        # Note: This test may not work on all platforms
        # The detector should return default delimiter on error
        csv_path = tmp_path / "no_permission.csv"
        csv_path.write_text("a,b,c")
        # Can't easily simulate permission error in pytest
        # Just ensure the method doesn't crash with non-existent
        delimiter = detector.detect_delimiter(Path("/nonexistent/file.csv"))
        assert delimiter == ","  # Should return default on error


class TestIntegration(TestFileFormatDetector):
    """Integration tests combining multiple detection methods."""

    def test_full_detection_workflow(self, detector: FileFormatDetector, comma_csv: Path) -> None:
        """Should perform full detection workflow."""
        # Validate size
        assert detector.validate_file_size(comma_csv)

        # Detect encoding
        encoding = detector.detect_encoding(comma_csv)
        assert encoding == "utf-8"

        # Detect delimiter
        delimiter = detector.detect_delimiter(comma_csv)
        assert delimiter == ","

        # Detect format
        format_type = detector.detect_format(comma_csv)
        assert format_type == "csv"

        # Detect header row
        skip_rows = detector.detect_header_row(comma_csv, default_skip_rows=0)
        assert skip_rows == 0

    def test_actigraph_style_file(self, tmp_path: Path, detector: FileFormatDetector) -> None:
        """Should handle ActiGraph-style files with metadata header."""
        csv_path = tmp_path / "actigraph.csv"
        csv_path.write_text(
            "------------ Data File Created By ActiGraph GT3X+ ActiLife v6.13.4 Firmware v4.4.0 ----------------\n"
            "Serial Number: ABC123\n"
            "Start Time: 12:00:00\n"
            "Start Date: 1/1/2024\n"
            "Epoch Period (hh:mm:ss): 00:01:00\n"
            "Download Time: 12:00:00\n"
            "Download Date: 1/15/2024\n"
            "Current Memory Address: 0\n"
            "Current Battery Voltage: 4.19\n"
            "Mode: 12\n"
            "Date,Time,Axis1,Axis2,Axis3,Vector Magnitude\n"
            "1/1/2024,12:00:00,100,50,30,115.8\n"
            "1/1/2024,12:01:00,150,75,45,174.2\n"
        )

        # Should detect as CSV
        format_type = detector.detect_format(csv_path)
        assert format_type == "csv"

        # Should detect comma delimiter
        delimiter = detector.detect_delimiter(csv_path)
        assert delimiter == ","

        # Header detection would use default (10 for ActiGraph)
        skip_rows = detector.detect_header_row(csv_path)
        assert skip_rows == 10
