"""Format detection service for automatic CSV format identification."""

from __future__ import annotations

import csv
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

from sleep_scoring_app.core.constants import DevicePreset

logger = logging.getLogger(__name__)

# Common datetime formats to try
DATETIME_FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%m-%d-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%m/%d/%Y %I:%M:%S %p",
    "%d/%m/%Y %I:%M:%S %p",
]

# Device signatures based on column names
DEVICE_SIGNATURES = {
    DevicePreset.ACTIGRAPH: {"Axis1", "Axis2", "Axis3", "Vector Magnitude", "Activity"},
    DevicePreset.GENEACTIV: {"timestamp", "x", "y", "z", "SVM", "Temperature"},
    DevicePreset.AXIVITY: {"Time", "X", "Y", "Z", "SVM"},
    DevicePreset.ACTIWATCH: {"Activity", "White Light", "Sleep/Wake"},
    DevicePreset.MOTIONWATCH: {"Activity", "Light", "Sleep"},
}


class FormatDetector:
    """Service for detecting CSV file formats and data parameters."""

    def _try_parse_datetime(self, date_str: str, time_str: str | None = None) -> datetime | None:
        """Try to parse datetime from string(s) using common formats."""
        # Combine date and time if separate
        if time_str:
            combined = f"{date_str} {time_str}"
        else:
            combined = date_str

        combined = combined.strip()

        for fmt in DATETIME_FORMATS:
            try:
                return datetime.strptime(combined, fmt)
            except ValueError:
                continue
        return None

    def _is_data_row(self, row: list[str]) -> bool:
        """Check if a row appears to be a data row (has datetime and numeric values)."""
        if len(row) < 2:
            return False

        # Check if first cell(s) could be datetime
        has_datetime = False
        for i in range(min(2, len(row))):
            if self._try_parse_datetime(row[i]) is not None:
                has_datetime = True
                break
            # Try combining first two cells as date + time
            if i == 0 and len(row) > 1:
                if self._try_parse_datetime(row[0], row[1]) is not None:
                    has_datetime = True
                    break

        if not has_datetime:
            return False

        # Check if there are numeric values
        numeric_count = 0
        for cell in row[2:]:  # Skip date/time columns
            try:
                float(cell.replace(",", ""))
                numeric_count += 1
            except (ValueError, AttributeError):
                pass

        return numeric_count >= 1

    def detect_header_rows(self, file_path: str | Path) -> tuple[int, float]:
        """
        Detect the number of header rows to skip.

        Algorithm:
        1. Read first 50 lines of file
        2. For each line, try to parse as data row (look for datetime + numeric)
        3. First line that parses successfully = end of headers
        4. Confidence based on consistency of subsequent rows

        Args:
            file_path: Path to the CSV file

        Returns:
            tuple[int, float]: (skip_rows, confidence 0.0-1.0)

        """
        file_path = Path(file_path)

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                # Try to detect delimiter
                sample = f.read(4096)
                f.seek(0)

                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
                except csv.Error:
                    dialect = csv.excel

                reader = csv.reader(f, dialect)
                lines = []
                for i, row in enumerate(reader):
                    if i >= 50:  # Read first 50 lines
                        break
                    lines.append(row)

            # Find first data row
            first_data_row = -1
            for i, row in enumerate(lines):
                if self._is_data_row(row):
                    first_data_row = i
                    break

            if first_data_row == -1:
                return (10, 0.5)  # Default fallback

            # Calculate confidence based on consistency of subsequent rows
            data_rows_found = 0
            for row in lines[first_data_row : first_data_row + 10]:
                if self._is_data_row(row):
                    data_rows_found += 1

            confidence = data_rows_found / 10.0 if data_rows_found > 0 else 0.5

            # skip_rows = rows to skip BEFORE the column header row
            # first_data_row - 1 = header row index, so skip everything before it
            skip_rows = max(0, first_data_row - 1)
            return (skip_rows, confidence)

        except Exception as e:
            logger.warning("Error detecting header rows: %s", e)
            return (10, 0.3)  # Default fallback with low confidence

    def detect_epoch_length(self, file_path: str | Path, skip_rows: int) -> tuple[int, float]:
        """
        Detect the epoch length (time between data points).

        Algorithm:
        1. Read first 100 data rows after headers
        2. Parse datetime column
        3. Calculate time differences between consecutive rows
        4. Take mode of differences (most common interval)
        5. Confidence = % of rows matching mode interval

        Args:
            file_path: Path to the CSV file
            skip_rows: Number of header rows to skip

        Returns:
            tuple[int, float]: (epoch_seconds, confidence 0.0-1.0)

        """
        file_path = Path(file_path)

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                # Skip header rows
                for _ in range(skip_rows):
                    f.readline()

                sample = f.read(8192)
                f.seek(0)
                for _ in range(skip_rows):
                    f.readline()

                try:
                    dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
                except csv.Error:
                    dialect = csv.excel

                reader = csv.reader(f, dialect)

                timestamps = []
                for i, row in enumerate(reader):
                    if i >= 100:  # Read first 100 data rows
                        break
                    if len(row) < 2:
                        continue

                    # Try to parse datetime
                    dt = self._try_parse_datetime(row[0])
                    if dt is None and len(row) > 1:
                        dt = self._try_parse_datetime(row[0], row[1])

                    if dt:
                        timestamps.append(dt)

            if len(timestamps) < 2:
                return (60, 0.3)  # Default fallback

            # Calculate time differences
            diffs = []
            for i in range(1, len(timestamps)):
                diff = (timestamps[i] - timestamps[i - 1]).total_seconds()
                if 0 < diff <= 300:  # Ignore gaps > 5 minutes
                    diffs.append(int(diff))

            if not diffs:
                return (60, 0.3)

            # Find mode (most common interval)
            counter = Counter(diffs)
            most_common = counter.most_common(1)[0]
            epoch_length = most_common[0]
            confidence = most_common[1] / len(diffs)

            return (epoch_length, confidence)

        except Exception as e:
            logger.warning("Error detecting epoch length: %s", e)
            return (60, 0.3)

    def detect_device_format(self, file_path: str | Path) -> tuple[DevicePreset, float]:
        """
        Detect the device/format based on column names and file structure.

        Heuristics:
        - ActiGraph: Has "Axis1", "Axis2", "Axis3", "Vector Magnitude"
        - GENEActiv: Has "timestamp", "x", "y", "z", "SVM"
        - Axivity: Has "Time", "X", "Y", "Z"
        - Actiwatch: Has "Activity", typically single axis

        Args:
            file_path: Path to the CSV file

        Returns:
            tuple[DevicePreset, float]: (device_preset, confidence 0.0-1.0)

        """
        file_path = Path(file_path)

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                # Read enough lines to find column headers
                lines = []
                for i, line in enumerate(f):
                    if i >= 20:
                        break
                    lines.append(line)

            # Find potential header row (row with column names)
            columns = set()
            for line in lines:
                # Try to parse as CSV
                try:
                    reader = csv.reader([line])
                    row = next(reader)
                    # Check if this looks like a header row (has non-numeric strings)
                    non_numeric = [c for c in row if c and not c.replace(".", "").replace("-", "").isdigit()]
                    if len(non_numeric) >= 3:
                        columns.update(c.strip() for c in row if c.strip())
                except Exception:
                    continue

            # Match against device signatures
            best_match = DevicePreset.GENERIC_CSV
            best_score = 0.0

            for device, signature in DEVICE_SIGNATURES.items():
                # Case-insensitive matching
                columns_lower = {c.lower() for c in columns}
                signature_lower = {s.lower() for s in signature}

                matches = len(columns_lower & signature_lower)
                score = matches / len(signature) if signature else 0

                if score > best_score:
                    best_score = score
                    best_match = device

            confidence = min(best_score * 1.2, 1.0)  # Boost confidence slightly

            return (best_match, confidence)

        except Exception as e:
            logger.warning("Error detecting device format: %s", e)
            return (DevicePreset.GENERIC_CSV, 0.3)
