"""
Golden file tests for export CSV format stability.

Constructs a known set of markers/metrics data, generates export CSV output
via the ExportService's _generate_csv method, and compares against a
checked-in golden file at tests/golden/export_sample.csv.

The golden file ensures the export format is stable. Any intentional change
to the export format must update the golden file.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from sleep_scoring_web.services.export_service import (
    DEFAULT_COLUMNS,
    EXPORT_COLUMNS,
    ExportService,
    _ALGORITHM_DISPLAY,
    _DETECTION_RULE_DISPLAY,
    _MARKER_TYPE_DISPLAY,
    _VERIFICATION_DISPLAY,
    _empty_metric_fields,
)

GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden"
GOLDEN_FILE = GOLDEN_DIR / "export_sample.csv"


# ---------------------------------------------------------------------------
# Fixture data: deterministic rows matching real export output
# ---------------------------------------------------------------------------

def _build_sample_rows() -> list[dict[str, str | int | float]]:
    """Build a deterministic set of export rows.

    Mimics the structure produced by ExportService._fetch_export_data
    for sleep markers with metrics, without metrics, and a no-sleep row.
    """
    rows = [
        # Row 1: Main sleep with full metrics
        {
            "Filename": "participant_001.csv",
            "File ID": 1,
            "Participant ID": "P001",
            "Study Date": "2025-01-15",
            "Period Index": 1,
            "Marker Type": "Main Sleep",
            "Onset Time": "22:30",
            "Offset Time": "06:45",
            "Onset Datetime": "2025-01-15 22:30:00",
            "Offset Datetime": "2025-01-16 06:45:00",
            "Time in Bed (min)": "495.00",
            "Total Sleep Time (min)": "462.00",
            "WASO (min)": "28.00",
            "Sleep Onset Latency (min)": "5.00",
            "Number of Awakenings": 4,
            "Avg Awakening Length (min)": "7.00",
            "Sleep Efficiency (%)": "93.33",
            "Movement Index": "12.50",
            "Fragmentation Index": "8.20",
            "Sleep Fragmentation Index": "20.70",
            "Total Activity Counts": 15420,
            "Non-zero Epochs": 185,
            "Algorithm": "Sadeh 1994 (ActiLife)",
            "Detection Rule": "3 Epochs / 5 Min",
            "Verification Status": "Submitted",
            "Scored By": "scorer1",
            "Is No Sleep": "False",
            "Needs Consensus": "False",
            "Notes": "",
        },
        # Row 2: Nap with partial metrics
        {
            "Filename": "participant_001.csv",
            "File ID": 1,
            "Participant ID": "P001",
            "Study Date": "2025-01-15",
            "Period Index": 2,
            "Marker Type": "Nap",
            "Onset Time": "14:00",
            "Offset Time": "15:30",
            "Onset Datetime": "2025-01-15 14:00:00",
            "Offset Datetime": "2025-01-15 15:30:00",
            "Time in Bed (min)": "90.00",
            "Total Sleep Time (min)": "78.00",
            "WASO (min)": "7.00",
            "Sleep Onset Latency (min)": "5.00",
            "Number of Awakenings": 1,
            "Avg Awakening Length (min)": "7.00",
            "Sleep Efficiency (%)": "86.67",
            "Movement Index": "5.30",
            "Fragmentation Index": "3.10",
            "Sleep Fragmentation Index": "8.40",
            "Total Activity Counts": 2310,
            "Non-zero Epochs": 42,
            "Algorithm": "Sadeh 1994 (ActiLife)",
            "Detection Rule": "3 Epochs / 5 Min",
            "Verification Status": "Draft",
            "Scored By": "scorer1",
            "Is No Sleep": "False",
            "Needs Consensus": "False",
            "Notes": "",
        },
        # Row 3: No-sleep date (no markers, no metrics)
        {
            "Filename": "participant_002.csv",
            "File ID": 2,
            "Participant ID": "P002",
            "Study Date": "2025-01-16",
            "Period Index": "",
            "Marker Type": "",
            "Onset Time": "",
            "Offset Time": "",
            "Onset Datetime": "",
            "Offset Datetime": "",
            "Scored By": "scorer2",
            "Is No Sleep": "True",
            "Needs Consensus": "False",
            "Notes": "Travel day",
            **_empty_metric_fields(detection_rule="3 Epochs / 5 Min"),
        },
    ]
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGoldenExportFormat:
    """Tests that the export CSV format matches the golden file."""

    def _generate_csv(
        self,
        rows: list[dict],
        columns: list[str] | None = None,
        include_header: bool = True,
    ) -> str:
        """Generate CSV via ExportService._generate_csv (static-ish method)."""
        # ExportService.__init__ requires a db session, but _generate_csv
        # does not use it — pass a mock.
        svc = ExportService(db=MagicMock())
        cols = columns or DEFAULT_COLUMNS
        return svc._generate_csv(rows, cols, include_header=include_header, include_metadata=False)

    def test_golden_file_matches(self) -> None:
        """Generated CSV matches the checked-in golden file."""
        rows = _build_sample_rows()
        generated = self._generate_csv(rows)

        golden_text = GOLDEN_FILE.read_bytes().decode("utf-8")
        assert generated == golden_text, (
            "Export CSV does not match golden file. "
            "If the format change is intentional, regenerate the golden file:\n"
            "  python -c \"\n"
            "from tests.unit.test_golden_export import regenerate_golden\n"
            "regenerate_golden()\n"
            "\""
        )

    def test_header_row_matches_default_columns(self) -> None:
        """CSV header row contains exactly the default columns in order."""
        rows = _build_sample_rows()
        generated = self._generate_csv(rows)
        reader = csv.reader(io.StringIO(generated))
        header = next(reader)
        assert header == DEFAULT_COLUMNS

    def test_row_count(self) -> None:
        """CSV has header + 3 data rows."""
        rows = _build_sample_rows()
        generated = self._generate_csv(rows)
        lines = [l for l in generated.strip().split("\n") if l]
        assert len(lines) == 4  # 1 header + 3 data

    def test_no_header_mode(self) -> None:
        """include_header=False omits the header row."""
        rows = _build_sample_rows()
        generated = self._generate_csv(rows, include_header=False)
        lines = [l for l in generated.strip().split("\n") if l]
        assert len(lines) == 3  # 3 data rows only

    def test_no_sleep_row_has_empty_metrics(self) -> None:
        """No-sleep sentinel row has empty metric fields."""
        rows = _build_sample_rows()
        generated = self._generate_csv(rows)
        reader = csv.DictReader(io.StringIO(generated))
        data_rows = list(reader)
        no_sleep_row = data_rows[2]  # Third row
        assert no_sleep_row["Is No Sleep"] == "True"
        assert no_sleep_row["Total Sleep Time (min)"] == ""
        assert no_sleep_row["Algorithm"] == ""
        assert no_sleep_row["Marker Type"] == ""

    def test_column_subset_export(self) -> None:
        """Exporting a subset of columns works correctly."""
        rows = _build_sample_rows()
        subset = ["Filename", "Study Date", "Marker Type"]
        generated = self._generate_csv(rows, columns=subset)
        reader = csv.reader(io.StringIO(generated))
        header = next(reader)
        assert header == subset
        data = list(reader)
        assert len(data) == 3
        assert data[0][0] == "participant_001.csv"

    def test_csv_sanitization(self) -> None:
        """Values starting with = + - @ are sanitized to prevent injection."""
        rows = [{
            **_build_sample_rows()[0],
            "Notes": "=CMD()",
        }]
        generated = self._generate_csv(rows)
        reader = csv.DictReader(io.StringIO(generated))
        row = next(reader)
        assert row["Notes"] == "'=CMD()", "CSV injection should be sanitized with leading quote"

    def test_display_value_mappings_exist(self) -> None:
        """Display value lookup dicts cover expected enum values."""
        # Marker types
        assert "Main Sleep" in _MARKER_TYPE_DISPLAY.values()
        assert "Nap" in _MARKER_TYPE_DISPLAY.values()

        # Algorithms
        assert "Sadeh 1994 (ActiLife)" in _ALGORITHM_DISPLAY.values()
        assert "Cole-Kripke 1992 (ActiLife)" in _ALGORITHM_DISPLAY.values()

        # Detection rules
        assert "3 Epochs / 5 Min" in _DETECTION_RULE_DISPLAY.values()

        # Verification statuses
        assert "Draft" in _VERIFICATION_DISPLAY.values()
        assert "Verified" in _VERIFICATION_DISPLAY.values()

    def test_all_export_columns_defined(self) -> None:
        """All export columns have required attributes."""
        for col in EXPORT_COLUMNS:
            assert col.name, "Column must have a name"
            assert col.category, "Column must have a category"
            assert col.description, "Column must have a description"


# ---------------------------------------------------------------------------
# Golden file regeneration utility
# ---------------------------------------------------------------------------

def regenerate_golden() -> None:
    """Regenerate the golden file from current code. Run manually when format changes."""
    rows = _build_sample_rows()
    svc = ExportService(db=MagicMock())
    csv_content = svc._generate_csv(rows, DEFAULT_COLUMNS, include_header=True, include_metadata=False)
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    # Write in binary mode to preserve exact line endings from csv module (\r\n)
    GOLDEN_FILE.write_bytes(csv_content.encode("utf-8"))
    print(f"Golden file written to {GOLDEN_FILE}")


if __name__ == "__main__":
    regenerate_golden()
