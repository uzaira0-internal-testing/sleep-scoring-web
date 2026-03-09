#!/usr/bin/env python3
"""
File Format Detector for Sleep Scoring Application
Handles file format detection, validation, and encoding detection.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from sleep_scoring_app.core.exceptions import ErrorCodes, SleepScoringImportError

if TYPE_CHECKING:
    from pathlib import Path

    pass

logger = logging.getLogger(__name__)


class FileFormatDetector:
    """Detects file format, encoding, delimiter, and validates file properties."""

    MAX_FILE_SIZE_MB = 100

    def __init__(self) -> None:
        self.max_file_size = self.MAX_FILE_SIZE_MB * 1024 * 1024  # Convert to bytes

    def validate_file_size(self, file_path: Path) -> bool:
        """
        Validate that file size is within acceptable limits.

        Args:
            file_path: Path to file to validate

        Returns:
            True if file size is acceptable

        Raises:
            SleepScoringImportError: If file is too large

        """
        try:
            file_size = file_path.stat().st_size
            if file_size > self.max_file_size:
                msg = f"File {file_path.name} too large: {file_size / 1024 / 1024:.1f}MB > {self.MAX_FILE_SIZE_MB}MB"
                raise SleepScoringImportError(msg, ErrorCodes.FILE_CORRUPTED)
            return True
        except OSError as e:
            msg = f"Failed to check file size for {file_path}: {e}"
            raise SleepScoringImportError(msg, ErrorCodes.FILE_CORRUPTED) from e

    def detect_encoding(self, file_path: Path) -> str:
        """
        Detect file encoding.

        Args:
            file_path: Path to file

        Returns:
            Detected encoding string (e.g., 'utf-8', 'latin-1')

        Note:
            Currently returns 'utf-8' as default. Can be extended with chardet
            library for more sophisticated detection if needed.

        """
        # Default to UTF-8, can be extended with chardet if needed
        return "utf-8"

    def detect_delimiter(self, file_path: Path, sample_lines: int = 5) -> str:
        """
        Detect CSV delimiter by analyzing first few lines.

        Args:
            file_path: Path to CSV file
            sample_lines: Number of lines to sample for detection

        Returns:
            Detected delimiter (default: ',')

        """
        try:
            with open(file_path, encoding=self.detect_encoding(file_path)) as f:
                # Read sample lines
                lines = []
                for _ in range(sample_lines):
                    line = f.readline()
                    if not line:
                        break
                    lines.append(line)

                if not lines:
                    return ","

                # Count delimiters in each line
                delimiters = [",", ";", "\t", "|"]
                delimiter_counts = {delim: [] for delim in delimiters}

                for line in lines:
                    for delim in delimiters:
                        delimiter_counts[delim].append(line.count(delim))

                # Find most consistent delimiter
                best_delimiter = ","
                best_consistency = -1

                for delim, counts in delimiter_counts.items():
                    if not counts or max(counts) == 0:
                        continue

                    # Check consistency (all lines should have same count)
                    if len(set(counts)) == 1 and counts[0] > 0:
                        if counts[0] > best_consistency:
                            best_consistency = counts[0]
                            best_delimiter = delim

                return best_delimiter

        except (OSError, UnicodeDecodeError) as e:
            logger.warning("Failed to detect delimiter for %s: %s, using default ','", file_path.name, e)
            return ","

    def detect_header_row(self, file_path: Path, default_skip_rows: int = 10) -> int:
        """
        Detect the header row in a CSV file.

        Args:
            file_path: Path to CSV file
            default_skip_rows: Default number of rows to skip

        Returns:
            Number of rows to skip before header

        Note:
            Currently returns the default value. Can be extended with
            heuristics to detect ActiGraph metadata rows vs data rows.

        """
        # For now, use the default skip_rows value
        # Can be extended with heuristics to detect ActiGraph metadata
        return default_skip_rows

    def detect_format(self, file_path: Path) -> str:
        """
        Detect file format based on extension and content.

        Args:
            file_path: Path to file

        Returns:
            Format string ('csv', 'xlsx', 'gt3x', etc.)

        """
        suffix = file_path.suffix.lower()

        format_map = {
            ".csv": "csv",
            ".xlsx": "xlsx",
            ".xls": "xls",
            ".gt3x": "gt3x",
        }

        return format_map.get(suffix, "unknown")
