"""Tests for GENEActiv raw data processor (chunked agcounts conversion).

Tests _detect_frequency, _estimate_total_rows, is_raw_geneactiv,
and process_raw_geneactiv with synthetic 100Hz accelerometer data.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from sleep_scoring_web.services.loaders.geneactiv_processor import (
    CHUNK_SIZE,
    EPOCH_SECONDS,
    _detect_frequency,
    _estimate_total_rows,
    is_raw_geneactiv,
    process_raw_geneactiv,
)


# ---------------------------------------------------------------------------
# Helpers — build synthetic GENEActiv files
# ---------------------------------------------------------------------------


def _make_geneactiv_raw_file(
    tmp_path: Path,
    *,
    freq: int = 100,
    duration_seconds: int = 120,
    tab_sep: bool = True,
    include_header_row: bool = False,
    filename: str = "geneactiv_raw.csv",
) -> Path:
    """Create a synthetic GENEActiv raw file with controllable parameters.

    The file has the standard GENEActiv header (100 lines) followed by
    raw 7-column data at the specified frequency.
    """
    sep = "\t" if tab_sep else ","
    lines: list[str] = []
    lines.append(f"Device Type{sep}GENEActiv")
    lines.append(f"Device Model{sep}1.2")
    lines.append(f"Device Unique Serial Code{sep}TEST001")
    lines.append(f"Subject Code{sep}DEMO-TEST")
    lines.append(f"Start Time{sep}2025-06-12 13:20:18")
    lines.append(f"Measurement Frequency{sep}{freq} Hz")
    # Fill rest of header up to line 99
    for _ in range(6, 100):
        lines.append("")

    if include_header_row:
        lines.append(f"timestamp{sep}x{sep}y{sep}z{sep}lux{sep}button{sep}temperature")

    # Generate raw data rows
    total_samples = freq * duration_seconds
    base_ts = pd.Timestamp("2025-06-12 13:20:18")
    rng = np.random.default_rng(42)

    for i in range(total_samples):
        ts = base_ts + pd.Timedelta(seconds=i / freq)
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") + f":{int(ts.microsecond / 1000):03d}"
        x = rng.normal(0.0, 0.3)
        y = rng.normal(1.0, 0.2)  # ~1g gravity on y-axis
        z = rng.normal(0.0, 0.1)
        row = f"{ts_str}{sep}{x:.4f}{sep}{y:.4f}{sep}{z:.4f}{sep}0{sep}0{sep}25.0"
        lines.append(row)

    file_path = tmp_path / filename
    file_path.write_text("\n".join(lines) + "\n")
    return file_path


def _make_epoch_geneactiv_file(tmp_path: Path) -> Path:
    """Create a GENEActiv epoch-compressed file (12 columns)."""
    sep = "\t"
    lines: list[str] = []
    lines.append(f"Device Type{sep}GENEActiv")
    for _ in range(1, 100):
        lines.append("")
    # 12-column epoch data
    lines.append(f"2025-06-12 13:20:18:000{sep}0.86{sep}0.18{sep}0.10{sep}388{sep}0{sep}26{sep}154{sep}0.39{sep}0.14{sep}0.24{sep}9510")
    file_path = tmp_path / "epoch_geneactiv.csv"
    file_path.write_text("\n".join(lines) + "\n")
    return file_path


# ---------------------------------------------------------------------------
# Tests: _detect_frequency
# ---------------------------------------------------------------------------


class TestDetectFrequency:
    """Test frequency detection from GENEActiv header."""

    def test_detects_100hz(self, tmp_path: Path) -> None:
        file_path = _make_geneactiv_raw_file(tmp_path, freq=100, duration_seconds=1)
        assert _detect_frequency(file_path) == 100

    def test_detects_custom_frequency(self, tmp_path: Path) -> None:
        """Test with non-standard frequency."""
        sep = "\t"
        lines = [
            f"Device Type{sep}GENEActiv",
            f"Measurement Frequency{sep}50 Hz",
        ]
        for _ in range(2, 100):
            lines.append("")
        lines.append("2025-06-12 13:20:18:000\t0.86\t0.18\t0.10\t388\t0\t26")
        file_path = tmp_path / "freq50.csv"
        file_path.write_text("\n".join(lines) + "\n")
        assert _detect_frequency(file_path) == 50

    def test_defaults_to_100_when_not_found(self, tmp_path: Path) -> None:
        """Default to 100 Hz when no frequency line found."""
        lines = ["some header line"] * 5
        lines.append("2025-06-12 13:20:18:000\t0.86\t0.18\t0.10\t388\t0\t26")
        file_path = tmp_path / "nofreq.csv"
        file_path.write_text("\n".join(lines) + "\n")
        assert _detect_frequency(file_path) == 100

    def test_sample_rate_variant(self, tmp_path: Path) -> None:
        """'Sample Rate' is also accepted as a frequency header."""
        lines = [
            "Device Type\tGENEActiv",
            "Sample Rate\t75",
        ]
        for _ in range(2, 100):
            lines.append("")
        lines.append("2025-06-12 13:20:18:000\t0.86\t0.18\t0.10\t388\t0\t26")
        file_path = tmp_path / "samplerate.csv"
        file_path.write_text("\n".join(lines) + "\n")
        assert _detect_frequency(file_path) == 75


# ---------------------------------------------------------------------------
# Tests: _estimate_total_rows
# ---------------------------------------------------------------------------


class TestEstimateTotalRows:
    """Test row count estimation from file size."""

    def test_estimates_nonzero(self, tmp_path: Path) -> None:
        file_path = _make_geneactiv_raw_file(tmp_path, freq=100, duration_seconds=2)
        data_start = 100
        estimate = _estimate_total_rows(file_path, data_start)
        assert estimate >= 1

    def test_fallback_line_length(self, tmp_path: Path) -> None:
        """Covers for-else branch when data_start line not found."""
        file_path = tmp_path / "tiny.csv"
        file_path.write_text("abc\n")
        # data_start beyond file length — for-else triggers avg_line_len=80
        estimate = _estimate_total_rows(file_path, 999)
        assert estimate >= 1


# ---------------------------------------------------------------------------
# Tests: is_raw_geneactiv
# ---------------------------------------------------------------------------


class TestIsRawGeneactiv:
    """Test detection of raw (7-col) vs epoch (12-col) GENEActiv files."""

    def test_raw_file_returns_true(self, tmp_path: Path) -> None:
        file_path = _make_geneactiv_raw_file(tmp_path, freq=100, duration_seconds=1)
        assert is_raw_geneactiv(file_path) is True

    def test_epoch_file_returns_false(self, tmp_path: Path) -> None:
        file_path = _make_epoch_geneactiv_file(tmp_path)
        assert is_raw_geneactiv(file_path) is False

    def test_non_geneactiv_returns_false(self, tmp_path: Path) -> None:
        file_path = tmp_path / "actigraph.csv"
        file_path.write_text("Date,Time,Axis1\n01/15/2025,22:00:00,100\n")
        assert is_raw_geneactiv(file_path) is False


# ---------------------------------------------------------------------------
# Tests: process_raw_geneactiv
# ---------------------------------------------------------------------------


class TestProcessRawGeneactiv:
    """Test end-to-end chunked processing of raw GENEActiv files."""

    def test_basic_processing(self, tmp_path: Path) -> None:
        """Process 2 minutes of 100Hz data -> should produce 2 epochs."""
        file_path = _make_geneactiv_raw_file(
            tmp_path, freq=100, duration_seconds=120,
        )
        result = process_raw_geneactiv(
            file_path=file_path,
            file_id=1,
            db_session=None,
            insert_fn=lambda db, fid, df: len(df),
        )

        assert result["total_epochs"] == 2
        assert result["sample_rate"] == 100
        assert result["start_time"] is not None
        assert result["end_time"] is not None
        assert len(result["epoch_dfs"]) >= 1
        # Check epoch DataFrame structure
        epoch_df = pd.concat(result["epoch_dfs"], ignore_index=True)
        assert "timestamp" in epoch_df.columns
        assert "axis_x" in epoch_df.columns
        assert "axis_y" in epoch_df.columns
        assert "axis_z" in epoch_df.columns
        assert "vector_magnitude" in epoch_df.columns
        assert len(epoch_df) == 2

    def test_progress_callback_called(self, tmp_path: Path) -> None:
        """Progress callback should be invoked during processing."""
        file_path = _make_geneactiv_raw_file(
            tmp_path, freq=100, duration_seconds=120,
        )
        progress_calls: list[tuple[str, float, int]] = []

        def callback(phase: str, pct: float, rows: int) -> None:
            progress_calls.append((phase, pct, rows))

        process_raw_geneactiv(
            file_path=file_path,
            file_id=1,
            db_session=None,
            insert_fn=lambda db, fid, df: len(df),
            progress_callback=callback,
        )

        assert len(progress_calls) >= 1
        # First call should be "reading_csv" at 0%
        assert progress_calls[0] == ("reading_csv", 0.0, 0)
        # Should have converting_counts calls
        phases = [c[0] for c in progress_calls]
        assert "converting_counts" in phases

    def test_with_header_row(self, tmp_path: Path) -> None:
        """Process a GENEActiv file that has a header row before data."""
        file_path = _make_geneactiv_raw_file(
            tmp_path, freq=100, duration_seconds=120,
            include_header_row=True,
            filename="with_header.csv",
        )
        result = process_raw_geneactiv(
            file_path=file_path,
            file_id=1,
            db_session=None,
            insert_fn=lambda db, fid, df: len(df),
        )
        assert result["total_epochs"] == 2

    def test_comma_separated(self, tmp_path: Path) -> None:
        """Process a comma-separated GENEActiv file."""
        file_path = _make_geneactiv_raw_file(
            tmp_path, freq=100, duration_seconds=120,
            tab_sep=False,
            filename="comma_raw.csv",
        )
        result = process_raw_geneactiv(
            file_path=file_path,
            file_id=1,
            db_session=None,
            insert_fn=lambda db, fid, df: len(df),
        )
        assert result["total_epochs"] == 2

    def test_short_file_no_epoch(self, tmp_path: Path) -> None:
        """File with less than 1 epoch of data produces 0 epochs."""
        file_path = _make_geneactiv_raw_file(
            tmp_path, freq=100, duration_seconds=30,  # Only 30s < 60s epoch
            filename="short.csv",
        )
        result = process_raw_geneactiv(
            file_path=file_path,
            file_id=1,
            db_session=None,
            insert_fn=lambda db, fid, df: len(df),
        )
        assert result["total_epochs"] == 0

    def test_vector_magnitude_positive(self, tmp_path: Path) -> None:
        """Vector magnitude should be non-negative for all epochs."""
        file_path = _make_geneactiv_raw_file(
            tmp_path, freq=100, duration_seconds=180,
        )
        result = process_raw_geneactiv(
            file_path=file_path,
            file_id=1,
            db_session=None,
            insert_fn=lambda db, fid, df: len(df),
        )
        epoch_df = pd.concat(result["epoch_dfs"], ignore_index=True)
        assert (epoch_df["vector_magnitude"] >= 0).all()

    def test_three_epochs(self, tmp_path: Path) -> None:
        """Process 3 minutes of data -> should produce 3 epochs."""
        file_path = _make_geneactiv_raw_file(
            tmp_path, freq=100, duration_seconds=180,
            filename="three_epochs.csv",
        )
        result = process_raw_geneactiv(
            file_path=file_path,
            file_id=1,
            db_session=None,
            insert_fn=lambda db, fid, df: len(df),
        )
        assert result["total_epochs"] == 3
