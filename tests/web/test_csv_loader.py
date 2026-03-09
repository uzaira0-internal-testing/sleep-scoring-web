"""Tests for CSVLoaderService, especially GENEActiv format handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from sleep_scoring_web.services.loaders.csv_loader import CSVLoaderService


# ---------------------------------------------------------------------------
# Fixtures: synthetic GENEActiv files
# ---------------------------------------------------------------------------


@pytest.fixture
def geneactiv_epoch_file(tmp_path: Path) -> Path:
    """Real GENEActiv epoch-compressed export: 100 metadata rows, NO column header, tab-separated, 12 columns."""
    lines: list[str] = []
    lines.append("Device Type\tGENEActiv")
    lines.append("Device Model\t1.2")
    lines.append("Device Unique Serial Code\tTEST001")
    lines.append("Subject Code\tDEMO-TEST")
    lines.append("Start Time\t2025-06-12 13:20:18")
    lines.append("Measurement Frequency\t100 Hz")
    # Fill rest of 100-row header with empty lines
    for _ in range(6, 100):
        lines.append("")

    # Tab-separated epoch-compressed data with colon-millisecond timestamps
    # Columns: timestamp, mean_x, mean_y, mean_z, mean_lux, sum_button, mean_temp, SVMgs, sd_x, sd_y, sd_z, peak_lux
    data = [
        "2025-06-12 13:20:18:000\t0.8633\t0.1839\t0.102\t388\t0\t26\t154.14\t0.3988\t0.1489\t0.2439\t9510",
        "2025-06-12 13:20:18:010\t0.8594\t0.1836\t0.1016\t388\t0\t26\t154.14\t0.3984\t0.1484\t0.2435\t9510",
        "2025-06-12 13:20:18:020\t0.8555\t0.1875\t0.1055\t389\t0\t26\t154.15\t0.3977\t0.1496\t0.2441\t9511",
    ]
    lines.extend(data)

    file_path = tmp_path / "test_geneactiv_epoch.csv"
    file_path.write_text("\n".join(lines) + "\n")
    return file_path


@pytest.fixture
def geneactiv_raw_file(tmp_path: Path) -> Path:
    """Real GENEActiv raw export: 100 metadata rows, NO column header, tab-separated, 7 columns."""
    lines: list[str] = []
    lines.append("Device Type\tGENEActiv")
    lines.append("Device Model\t1.2")
    lines.append("Device Unique Serial Code\tTEST002")
    lines.append("Subject Code\tDEMO-RAW")
    lines.append("Start Time\t2025-06-12 13:20:18")
    lines.append("Measurement Frequency\t100 Hz")
    for _ in range(6, 100):
        lines.append("")

    # Tab-separated raw data: timestamp, x, y, z, lux, button, temperature
    data = [
        "2025-06-12 13:20:18:000\t0.8633\t0.1839\t0.102\t388\t0\t26",
        "2025-06-12 13:20:18:010\t0.8594\t0.1836\t0.1016\t388\t0\t26",
        "2025-06-12 13:20:18:020\t0.8555\t0.1875\t0.1055\t389\t0\t26",
    ]
    lines.extend(data)

    file_path = tmp_path / "test_geneactiv_raw.csv"
    file_path.write_text("\n".join(lines) + "\n")
    return file_path


@pytest.fixture
def geneactiv_with_header_file(tmp_path: Path) -> Path:
    """GENEActiv file with a column header row (like the demo file format)."""
    lines = [
        "Device Type,GENEActiv",
        "Device Model,1.2",
        "Device Unique Serial Code,DEMO_GA_001",
        "Subject Code,DEMO-001",
        "Start Time,2000-01-01 00:00:00",
        "Measurement Frequency,60 Hz",
        "",
        "timestamp,x,y,z,light,button,temperature",
        "2000-01-01 00:00:00,6,25,2,0,0,25.0",
        "2000-01-01 00:01:00,23,64,0,0,0,25.0",
        "2000-01-01 00:02:00,15,42,10,0,0,25.0",
    ]
    file_path = tmp_path / "test_geneactiv_demo.csv"
    file_path.write_text("\n".join(lines) + "\n")
    return file_path


@pytest.fixture
def actigraph_file(tmp_path: Path) -> Path:
    """Standard ActiGraph CSV (10 header rows, then column header, then data)."""
    header = ["--- header line ---"] * 10
    header.append("Date,Time,Axis1,Axis2,Axis3,Vector Magnitude")
    data = [
        "01/15/2025,22:00:00,100,50,30,115.32",
        "01/15/2025,22:01:00,80,40,20,93.27",
        "01/15/2025,22:02:00,60,30,10,68.07",
    ]
    file_path = tmp_path / "test_actigraph.csv"
    file_path.write_text("\n".join(header + data) + "\n")
    return file_path


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------


class TestDetectGeneactiv:
    """Test GENEActiv file format auto-detection."""

    def test_detects_epoch_file(self, geneactiv_epoch_file: Path) -> None:
        assert CSVLoaderService.detect_geneactiv(geneactiv_epoch_file) is True

    def test_detects_raw_file(self, geneactiv_raw_file: Path) -> None:
        assert CSVLoaderService.detect_geneactiv(geneactiv_raw_file) is True

    def test_detects_demo_geneactiv(self, geneactiv_with_header_file: Path) -> None:
        assert CSVLoaderService.detect_geneactiv(geneactiv_with_header_file) is True

    def test_does_not_detect_actigraph(self, actigraph_file: Path) -> None:
        assert CSVLoaderService.detect_geneactiv(actigraph_file) is False


class TestFindDataStart:
    """Test finding where data begins in GENEActiv files."""

    def test_headerless_starts_at_100(self, geneactiv_epoch_file: Path) -> None:
        data_start, has_header = CSVLoaderService._find_geneactiv_data_start(
            geneactiv_epoch_file
        )
        assert data_start == 100
        assert has_header is False

    def test_with_header_finds_header(self, geneactiv_with_header_file: Path) -> None:
        data_start, has_header = CSVLoaderService._find_geneactiv_data_start(
            geneactiv_with_header_file
        )
        assert data_start == 8
        assert has_header is True


# ---------------------------------------------------------------------------
# Loading tests
# ---------------------------------------------------------------------------


class TestLoadGeneactivEpoch:
    """Test loading epoch-compressed GENEActiv files (12 cols, no header row)."""

    def test_loads_successfully(self, geneactiv_epoch_file: Path) -> None:
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_epoch_file)
        df = result["activity_data"]

        assert len(df) == 3
        assert "timestamp" in df.columns
        assert "axis_y" in df.columns  # mapped from "y"
        assert "axis_x" in df.columns  # mapped from "x"
        assert "axis_z" in df.columns  # mapped from "z"
        assert "vector_magnitude" in df.columns  # mapped from "svm"

    def test_timestamp_colon_millis_fixed(self, geneactiv_epoch_file: Path) -> None:
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_epoch_file)
        df = result["activity_data"]

        ts = df["timestamp"].iloc[0]
        assert ts.year == 2025
        assert ts.month == 6
        assert ts.day == 12

    def test_svm_mapped_to_vector_magnitude(self, geneactiv_epoch_file: Path) -> None:
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_epoch_file)
        df = result["activity_data"]

        assert "vector_magnitude" in df.columns
        assert df["vector_magnitude"].iloc[0] == pytest.approx(154.14)

    def test_autodetects_without_preset(self, geneactiv_epoch_file: Path) -> None:
        """Auto-detection should work even without device_preset hint."""
        loader = CSVLoaderService(skip_rows=10)  # wrong skip_rows, but auto-detect overrides
        result = loader.load_file(geneactiv_epoch_file)
        assert len(result["activity_data"]) == 3

    def test_metadata_device_type(self, geneactiv_epoch_file: Path) -> None:
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_epoch_file)
        assert result["metadata"]["device_type"] == "geneactiv"


class TestLoadGeneactivRaw:
    """Test loading raw GENEActiv files (7 cols, no header row)."""

    def test_loads_successfully(self, geneactiv_raw_file: Path) -> None:
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_raw_file)
        df = result["activity_data"]

        assert len(df) == 3
        assert "timestamp" in df.columns
        assert "axis_y" in df.columns
        assert "axis_x" in df.columns
        assert "axis_z" in df.columns

    def test_vector_magnitude_computed(self, geneactiv_raw_file: Path) -> None:
        """Raw files have no SVM column — VM should be computed from x/y/z."""
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_raw_file)
        df = result["activity_data"]

        assert "vector_magnitude" in df.columns
        # sqrt(0.8633² + 0.1839² + 0.102²) ≈ 0.895
        assert df["vector_magnitude"].iloc[0] == pytest.approx(0.895, abs=0.01)


class TestLoadGeneactivWithHeader:
    """Test loading GENEActiv files that have a column header row (demo format)."""

    def test_loads_successfully(self, geneactiv_with_header_file: Path) -> None:
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_with_header_file)
        df = result["activity_data"]

        assert len(df) == 3
        assert "timestamp" in df.columns
        assert "axis_y" in df.columns

    def test_values_correct(self, geneactiv_with_header_file: Path) -> None:
        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(geneactiv_with_header_file)
        df = result["activity_data"]

        # y column mapped to axis_y
        assert df["axis_y"].iloc[0] == 25.0
        assert df["axis_x"].iloc[0] == 6.0
        assert df["axis_z"].iloc[0] == 2.0


class TestLoadActigraph:
    """Ensure ActiGraph loading is not broken by GENEActiv changes."""

    def test_loads_with_skip_rows(self, actigraph_file: Path) -> None:
        loader = CSVLoaderService(skip_rows=10)
        result = loader.load_file(actigraph_file)
        df = result["activity_data"]

        assert len(df) == 3
        assert "axis_y" in df.columns
        assert df["axis_y"].iloc[0] == 100.0  # Axis1 value
