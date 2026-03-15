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


# ---------------------------------------------------------------------------
# Error path and edge-case tests (targeting uncovered lines)
# ---------------------------------------------------------------------------


class TestDetectGeneactivErrors:
    """Test detect_geneactiv error/edge paths."""

    def test_nonexistent_file_returns_false(self, tmp_path: Path) -> None:
        """Line 104-105: exception branch in detect_geneactiv."""
        missing = tmp_path / "nonexistent.csv"
        assert CSVLoaderService.detect_geneactiv(missing) is False


class TestFindDataStartFallback:
    """Test _find_geneactiv_data_start fallback behavior."""

    def test_no_timestamp_found_returns_default(self, tmp_path: Path) -> None:
        """Lines 144-145: fallback when no timestamp found within 120 lines."""
        lines = ["some random text"] * 130
        file_path = tmp_path / "no_timestamp.csv"
        file_path.write_text("\n".join(lines))
        data_start, has_header = CSVLoaderService._find_geneactiv_data_start(file_path)
        assert data_start == 100
        assert has_header is False

    def test_first_line_is_timestamp_no_header(self, tmp_path: Path) -> None:
        """Lines 131->141: data starts at line 0, so i==0, no prev line check."""
        lines = [
            "2025-06-12 13:20:18:000\t0.86\t0.18\t0.10\t388\t0\t26",
            "2025-06-12 13:20:19:000\t0.85\t0.17\t0.11\t388\t0\t26",
        ]
        file_path = tmp_path / "ts_at_line0.csv"
        file_path.write_text("\n".join(lines))
        data_start, has_header = CSVLoaderService._find_geneactiv_data_start(file_path)
        assert data_start == 0
        assert has_header is False


class TestLoadGeneactivExtraCols:
    """Test GENEActiv files with more than 12 columns (extra_N naming)."""

    def test_extra_columns_beyond_epoch(self, tmp_path: Path) -> None:
        """Line 173: extra columns beyond GENEACTIV_EPOCH_COLUMNS."""
        lines: list[str] = []
        lines.append("Device Type\tGENEActiv")
        for _ in range(1, 100):
            lines.append("")
        # 14 columns — 12 epoch + 2 extra
        data = "2025-06-12 13:20:18:000\t0.86\t0.18\t0.10\t388\t0\t26\t154\t0.39\t0.14\t0.24\t9510\t99\t88"
        lines.append(data)
        file_path = tmp_path / "extra_cols.csv"
        file_path.write_text("\n".join(lines) + "\n")

        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(file_path)
        df = result["activity_data"]
        assert len(df) == 1


class TestLoadGeneactivCSVDelimiter:
    """Test GENEActiv CSV with comma delimiter and for-else branch."""

    def test_comma_delimited_geneactiv(self, tmp_path: Path) -> None:
        """Lines 159-160: for-else branch when data_start line not found."""
        lines: list[str] = []
        lines.append("Device Type,GENEActiv")
        for _ in range(1, 100):
            lines.append("")
        # Comma-separated data at line 100
        lines.append("2025-06-12 13:20:18:000,0.86,0.18,0.10,388,0,26")
        lines.append("2025-06-12 13:20:19:000,0.85,0.17,0.11,388,0,26")
        file_path = tmp_path / "comma_geneactiv.csv"
        file_path.write_text("\n".join(lines) + "\n")

        loader = CSVLoaderService(device_preset="geneactiv")
        result = loader.load_file(file_path)
        df = result["activity_data"]
        assert len(df) == 2


class TestLoadFileErrors:
    """Test load_file error paths."""

    def test_file_not_found(self, tmp_path: Path) -> None:
        """Lines 231-232: FileNotFoundError."""
        loader = CSVLoaderService()
        with pytest.raises(FileNotFoundError, match="File not found"):
            loader.load_file(tmp_path / "nonexistent.csv")

    def test_unsupported_extension(self, tmp_path: Path) -> None:
        """Lines 236-237: ValueError for unsupported extension."""
        bad_file = tmp_path / "data.json"
        bad_file.write_text("{}")
        loader = CSVLoaderService()
        with pytest.raises(ValueError, match="Unsupported file extension"):
            loader.load_file(bad_file)

    def test_file_too_large(self, tmp_path: Path) -> None:
        """Lines 244-245: ValueError for oversized file."""
        csv_file = tmp_path / "big.csv"
        csv_file.write_text("a,b\n1,2\n")
        loader = CSVLoaderService()
        loader.max_file_size = 1  # 1 byte limit
        with pytest.raises(ValueError, match="File too large"):
            loader.load_file(csv_file)

    def test_empty_csv_raises(self, tmp_path: Path) -> None:
        """Lines 260-262: pd.errors.EmptyDataError caught as ValueError."""
        header = ["--- header ---"] * 10
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("\n".join(header) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        with pytest.raises(ValueError, match="Empty data file|No columns to parse"):
            loader.load_file(csv_file)

    def test_no_data_rows_raises(self, tmp_path: Path) -> None:
        """Lines 268-269: empty DataFrame after parsing."""
        header = ["--- header ---"] * 10
        header.append("Date,Time,Axis1")
        csv_file = tmp_path / "nodata.csv"
        csv_file.write_text("\n".join(header) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        with pytest.raises(ValueError, match="No data in file"):
            loader.load_file(csv_file)

    def test_excel_file_loads(self, tmp_path: Path) -> None:
        """Line 259: Excel loading branch."""
        import pandas as pd

        df = pd.DataFrame({
            "Date": ["01/15/2025", "01/15/2025"],
            "Time": ["22:00:00", "22:01:00"],
            "Axis1": [100, 80],
        })
        xlsx_file = tmp_path / "test.xlsx"
        df.to_excel(xlsx_file, index=False)
        loader = CSVLoaderService(skip_rows=0)
        result = loader.load_file(xlsx_file)
        assert len(result["activity_data"]) == 2

    def test_invalid_column_mapping_raises(self, tmp_path: Path) -> None:
        """Lines 283-284: validation failure when columns not found."""
        header = ["--- header ---"] * 10
        header.append("ColA,ColB,ColC")
        data = ["aaa,bbb,ccc", "ddd,eee,fff"]
        csv_file = tmp_path / "badcols.csv"
        csv_file.write_text("\n".join(header + data) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        with pytest.raises(ValueError, match="Invalid column mapping"):
            loader.load_file(csv_file)


class TestCustomColumnMapping:
    """Test _create_custom_mapping with various custom_columns specs."""

    def test_datetime_combined_mapping(self, tmp_path: Path) -> None:
        """Lines 374-377: datetime_combined=True branch."""
        header = ["--- header ---"] * 10
        header.append("Timestamp,Activity")
        data = ["2025-01-15 22:00:00,100", "2025-01-15 22:01:00,80"]
        csv_file = tmp_path / "custom.csv"
        csv_file.write_text("\n".join(header + data) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        result = loader.load_file(
            csv_file,
            custom_columns={"datetime_combined": True, "date": "Timestamp", "activity": "Activity"},
        )
        df = result["activity_data"]
        assert len(df) == 2
        assert "timestamp" in df.columns

    def test_separate_date_time_mapping(self, tmp_path: Path) -> None:
        """Lines 378-384: separate date/time columns without datetime_combined."""
        header = ["--- header ---"] * 10
        header.append("MyDate,MyTime,MyActivity")
        data = ["01/15/2025,22:00:00,100", "01/15/2025,22:01:00,80"]
        csv_file = tmp_path / "custom_sep.csv"
        csv_file.write_text("\n".join(header + data) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        result = loader.load_file(
            csv_file,
            custom_columns={"date": "MyDate", "time": "MyTime", "activity": "MyActivity"},
        )
        df = result["activity_data"]
        assert len(df) == 2

    def test_axis_y_fallback_as_activity(self, tmp_path: Path) -> None:
        """Lines 390-392: axis_y used as fallback for activity_column."""
        header = ["--- header ---"] * 10
        header.append("Timestamp,Ydata,Xdata,Zdata")
        data = ["2025-01-15 22:00:00,100,50,30", "2025-01-15 22:01:00,80,40,20"]
        csv_file = tmp_path / "axisy.csv"
        csv_file.write_text("\n".join(header + data) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        result = loader.load_file(
            csv_file,
            custom_columns={
                "datetime_combined": True,
                "date": "Timestamp",
                "axis_y": "Ydata",
                "axis_x": "Xdata",
                "axis_z": "Zdata",
            },
        )
        df = result["activity_data"]
        assert df["axis_y"].iloc[0] == 100.0

    def test_vector_magnitude_custom(self, tmp_path: Path) -> None:
        """Lines 402-404: custom vector_magnitude mapping."""
        header = ["--- header ---"] * 10
        header.append("Timestamp,Activity,VM")
        data = ["2025-01-15 22:00:00,100,115.0", "2025-01-15 22:01:00,80,95.0"]
        csv_file = tmp_path / "custom_vm.csv"
        csv_file.write_text("\n".join(header + data) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        result = loader.load_file(
            csv_file,
            custom_columns={
                "datetime_combined": True,
                "date": "Timestamp",
                "activity": "Activity",
                "vector_magnitude": "VM",
            },
        )
        df = result["activity_data"]
        assert "vector_magnitude" in df.columns
        assert df["vector_magnitude"].iloc[0] == pytest.approx(115.0)


class TestColumnDetection:
    """Test detect_columns with different column naming conventions."""

    def test_detects_datetime_column(self) -> None:
        """Lines 327-331: detect combined 'datetime' or 'timestamp' columns."""
        import pandas as pd

        df = pd.DataFrame({"datetime": ["2025-01-15"], "y": [100]})
        loader = CSVLoaderService()
        mapping = loader.detect_columns(df)
        assert mapping.datetime_column == "datetime"

    def test_detects_separate_date_time(self) -> None:
        """Lines 334-340: detect separate date and time columns."""
        import pandas as pd

        df = pd.DataFrame({"date_col": ["2025-01-15"], "time_col": ["22:00"], "axis1": [100]})
        loader = CSVLoaderService()
        mapping = loader.detect_columns(df)
        assert mapping.date_column == "date_col"
        assert mapping.time_column == "time_col"

    def test_detects_vm_as_fallback_activity(self) -> None:
        """Lines 360-364: vector magnitude column used as fallback activity."""
        import pandas as pd

        df = pd.DataFrame({"timestamp": ["2025-01-15"], "vector_magnitude": [100.0]})
        loader = CSVLoaderService()
        mapping = loader.detect_columns(df)
        assert mapping.vector_magnitude_column == "vector_magnitude"
        assert mapping.activity_column == "vector_magnitude"

    def test_y_axis_variants(self) -> None:
        """Lines 343-346: detect y-axis with different names."""
        import pandas as pd

        for col_name in ("axis_y", "axis1", "y", "axis 1", "y-axis"):
            df = pd.DataFrame({"timestamp": ["2025-01-15"], col_name: [100]})
            loader = CSVLoaderService()
            mapping = loader.detect_columns(df)
            assert mapping.activity_column == col_name, f"Failed for column name: {col_name}"


class TestValidateColumnMapping:
    """Test _validate_column_mapping."""

    def test_missing_timestamp(self) -> None:
        """Line 413: error when no timestamp column."""
        from sleep_scoring_web.services.loaders.csv_loader import ColumnMapping

        loader = CSVLoaderService()
        mapping = ColumnMapping(activity_column="axis1")
        is_valid, errors = loader._validate_column_mapping(mapping)
        assert not is_valid
        assert "Missing timestamp column" in errors

    def test_missing_activity(self) -> None:
        """Line 416: error when no activity column."""
        from sleep_scoring_web.services.loaders.csv_loader import ColumnMapping

        loader = CSVLoaderService()
        mapping = ColumnMapping(datetime_column="timestamp")
        is_valid, errors = loader._validate_column_mapping(mapping)
        assert not is_valid
        assert "Missing activity column" in errors


class TestValidateData:
    """Test validate_data method."""

    def test_missing_timestamp_column(self) -> None:
        """Line 461: error when DataFrame lacks timestamp."""
        import pandas as pd

        loader = CSVLoaderService()
        df = pd.DataFrame({"axis_y": [100]})
        is_valid, errors = loader.validate_data(df)
        assert not is_valid
        assert "Missing timestamp column" in errors

    def test_missing_axis_y_column(self) -> None:
        """Line 464: error when DataFrame lacks axis_y."""
        import pandas as pd

        loader = CSVLoaderService()
        df = pd.DataFrame({"timestamp": ["2025-01-15"]})
        is_valid, errors = loader.validate_data(df)
        assert not is_valid
        assert "Missing axis_y column" in errors

    def test_empty_dataframe(self) -> None:
        """Line 467: error when DataFrame is empty."""
        import pandas as pd

        loader = CSVLoaderService()
        df = pd.DataFrame({"timestamp": [], "axis_y": []})
        is_valid, errors = loader.validate_data(df)
        assert not is_valid
        assert "DataFrame is empty" in errors


class TestStandardizeColumns:
    """Test _standardize_columns edge cases."""

    def test_date_only_without_time(self, tmp_path: Path) -> None:
        """Lines 427-432: date column without time column."""
        header = ["--- header ---"] * 10
        header.append("date,Axis1")
        data = ["2025-01-15,100", "2025-01-16,80"]
        csv_file = tmp_path / "dateonly.csv"
        csv_file.write_text("\n".join(header + data) + "\n")
        loader = CSVLoaderService(skip_rows=10)
        result = loader.load_file(csv_file)
        df = result["activity_data"]
        assert len(df) == 2
        assert "timestamp" in df.columns


class TestFileMetadata:
    """Test get_file_metadata."""

    def test_default_device_type(self, tmp_path: Path) -> None:
        """Line 474: default device type is 'actigraph'."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("dummy")
        loader = CSVLoaderService()
        metadata = loader.get_file_metadata(csv_file)
        assert metadata["device_type"] == "actigraph"
        assert metadata["epoch_length_seconds"] == 60

    def test_geneactiv_device_type(self, tmp_path: Path) -> None:
        """Line 474: preset overrides default."""
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("dummy")
        loader = CSVLoaderService(device_preset="geneactiv")
        metadata = loader.get_file_metadata(csv_file)
        assert metadata["device_type"] == "geneactiv"


class TestSampleRate:
    """Test sample rate inference from timestamps."""

    def test_sample_rate_computed(self, actigraph_file: Path) -> None:
        """Lines 300-303: sample rate from adjacent timestamps."""
        loader = CSVLoaderService(skip_rows=10)
        result = loader.load_file(actigraph_file)
        # 60-second epochs -> sample_rate = 1/60
        assert result["metadata"]["sample_rate"] == pytest.approx(1 / 60.0)
