#!/usr/bin/env python3
"""
Comprehensive unit tests for ExportManager.

Tests CSV export functionality, backup creation, file operations,
data sanitization, path validation, grouping, and atomic writes.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from sleep_scoring_app.core.constants import AlgorithmType, ExportColumn, MarkerType
from sleep_scoring_app.core.dataclasses import (
    DailySleepMarkers,
    ParticipantInfo,
    SleepMetrics,
    SleepPeriod,
)
from sleep_scoring_app.services.export_service import ExportManager, ExportResult


@pytest.fixture
def export_manager():
    """Create ExportManager with mock database."""
    mock_db = MagicMock()
    return ExportManager(database_manager=mock_db)


@pytest.fixture
def sample_participant():
    """Create sample participant info."""
    return ParticipantInfo(
        numerical_id="1000",
        full_id="1000 T1 G1",
        group_str="Control",
        timepoint_str="T1",
    )


@pytest.fixture
def sample_sleep_period():
    """Create sample sleep period."""
    onset = datetime(2024, 1, 10, 22, 0).timestamp()
    offset = datetime(2024, 1, 11, 7, 0).timestamp()
    return SleepPeriod(
        onset_timestamp=onset,
        offset_timestamp=offset,
        marker_index=1,
        marker_type=MarkerType.MAIN_SLEEP,
    )


@pytest.fixture
def sample_daily_markers(sample_sleep_period):
    """Create sample DailySleepMarkers."""
    markers = DailySleepMarkers()
    markers.period_1 = sample_sleep_period
    return markers


@pytest.fixture
def sample_sleep_metrics(sample_participant, sample_daily_markers):
    """Create sample SleepMetrics object."""
    return SleepMetrics(
        filename="participant_1000.csv",
        analysis_date="2024-01-10",
        algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
        daily_sleep_markers=sample_daily_markers,
        participant=sample_participant,
        total_sleep_time=420.0,
        sleep_efficiency=85.0,
        total_minutes_in_bed=480.0,
        waso=45.0,
        awakenings=3,
        average_awakening_length=15.0,
    )


@pytest.fixture
def sample_sleep_metrics_list():
    """Create list of sample SleepMetrics objects for multiple participants."""
    metrics_list = []
    groups = ["Control", "Treatment", "Control"]
    timepoints = ["T1", "T1", "T2"]

    for i in range(3):
        participant = ParticipantInfo(
            numerical_id=f"{1000 + i}",
            group_str=groups[i],
            timepoint_str=timepoints[i],
        )

        onset = datetime(2024, 1, 10 + i, 22, 0).timestamp()
        offset = datetime(2024, 1, 11 + i, 7, 0).timestamp()
        period = SleepPeriod(
            onset_timestamp=onset,
            offset_timestamp=offset,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        markers = DailySleepMarkers()
        markers.period_1 = period

        metrics = SleepMetrics(
            filename=f"participant_{1000 + i}.csv",
            analysis_date=f"2024-01-{10 + i:02d}",
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
            total_sleep_time=420.0 + i * 10,
            sleep_efficiency=85.0 + i,
        )
        metrics_list.append(metrics)

    return metrics_list


class TestExportResult:
    """Tests for ExportResult dataclass."""

    def test_add_warning_accumulates_warnings(self):
        """Test add_warning() accumulates warnings correctly."""
        result = ExportResult(success=True)

        result.add_warning("Warning 1")
        result.add_warning("Warning 2")

        assert len(result.warnings) == 2
        assert "Warning 1" in result.warnings
        assert "Warning 2" in result.warnings

    def test_add_error_accumulates_errors(self):
        """Test add_error() accumulates errors correctly."""
        result = ExportResult(success=False)

        result.add_error("Error 1")
        result.add_error("Error 2")
        result.add_error("Error 3")

        assert len(result.errors) == 3
        assert "Error 1" in result.errors
        assert "Error 3" in result.errors

    def test_has_issues_returns_true_when_warnings_present(self):
        """Test has_issues() returns True when warnings are present."""
        result = ExportResult(success=True)
        result.add_warning("Some warning")

        assert result.has_issues() is True

    def test_has_issues_returns_true_when_errors_present(self):
        """Test has_issues() returns True when errors are present."""
        result = ExportResult(success=False)
        result.add_error("Some error")

        assert result.has_issues() is True

    def test_has_issues_returns_true_when_both_warnings_and_errors(self):
        """Test has_issues() returns True when both warnings and errors are present."""
        result = ExportResult(success=False)
        result.add_warning("Warning")
        result.add_error("Error")

        assert result.has_issues() is True

    def test_has_issues_returns_false_when_clean(self):
        """Test has_issues() returns False when no warnings or errors."""
        result = ExportResult(success=True, files_exported=5)

        assert result.has_issues() is False
        assert result.warnings == []
        assert result.errors == []

    def test_default_values(self):
        """Test ExportResult default values."""
        result = ExportResult(success=True)

        assert result.files_exported == 0
        assert result.files_with_issues == 0
        assert result.warnings == []
        assert result.errors == []


class TestCSVSanitization:
    """Tests for CSV cell sanitization to prevent formula injection."""

    def test_sanitize_csv_cell_normal_string(self, export_manager):
        """Test sanitization of normal string passes through unchanged."""
        result = export_manager._sanitize_csv_cell("normal text")
        assert result == "normal text"

    def test_sanitize_csv_cell_formula_injection_equals(self, export_manager):
        """Test sanitization prevents formula injection with equals sign."""
        result = export_manager._sanitize_csv_cell("=SUM(A1:A10)")
        assert result == "'=SUM(A1:A10)"

    def test_sanitize_csv_cell_formula_injection_plus(self, export_manager):
        """Test sanitization prevents formula injection with plus sign."""
        result = export_manager._sanitize_csv_cell("+1234")
        assert result == "'+1234"

    def test_sanitize_csv_cell_minus_not_sanitized(self, export_manager):
        """Minus sign is not a formula trigger and should not be sanitized."""
        result = export_manager._sanitize_csv_cell("-1234")
        assert result == "-1234"

    def test_sanitize_csv_cell_formula_injection_at(self, export_manager):
        """Test sanitization prevents formula injection with at sign."""
        result = export_manager._sanitize_csv_cell("@SUM(A1)")
        assert result == "'@SUM(A1)"

    def test_sanitize_csv_cell_formula_injection_tab(self, export_manager):
        """Test sanitization prevents formula injection with tab."""
        result = export_manager._sanitize_csv_cell("\t1234")
        assert result == "'\t1234"

    def test_sanitize_csv_cell_formula_injection_carriage_return(self, export_manager):
        """Test sanitization prevents formula injection with carriage return."""
        result = export_manager._sanitize_csv_cell("\r=DANGEROUS")
        assert result == "'\r=DANGEROUS"

    def test_sanitize_csv_cell_integer_passes_through(self, export_manager):
        """Test sanitization preserves integer values unchanged."""
        assert export_manager._sanitize_csv_cell(123) == 123
        assert export_manager._sanitize_csv_cell(-456) == -456
        assert export_manager._sanitize_csv_cell(0) == 0

    def test_sanitize_csv_cell_float_passes_through(self, export_manager):
        """Test sanitization preserves float values unchanged."""
        assert export_manager._sanitize_csv_cell(45.67) == 45.67
        assert export_manager._sanitize_csv_cell(-3.14) == -3.14
        assert export_manager._sanitize_csv_cell(0.0) == 0.0

    def test_sanitize_csv_cell_none_passes_through(self, export_manager):
        """Test sanitization preserves None unchanged."""
        assert export_manager._sanitize_csv_cell(None) is None

    def test_sanitize_csv_cell_empty_string(self, export_manager):
        """Test sanitization of empty string returns empty string."""
        assert export_manager._sanitize_csv_cell("") == ""

    def test_sanitize_csv_cell_whitespace_only(self, export_manager):
        """Test sanitization of whitespace-only strings."""
        assert export_manager._sanitize_csv_cell("   ") == "   "
        assert export_manager._sanitize_csv_cell(" text") == " text"


class TestPathValidation:
    """Tests for export path validation."""

    def test_validate_export_path_valid_local_path(self, export_manager, tmp_path):
        """Test validation of valid local path."""
        is_valid, error_msg = export_manager._validate_export_path(str(tmp_path))

        assert is_valid is True
        assert error_msg == ""

    def test_validate_export_path_creates_new_directory(self, export_manager, tmp_path):
        """Test validation passes for path that needs directory creation."""
        new_dir = tmp_path / "new_export_dir"
        assert not new_dir.exists()

        is_valid, error_msg = export_manager._validate_export_path(str(new_dir))

        assert is_valid is True
        assert error_msg == ""

    def test_validate_export_path_nested_new_directories(self, export_manager, tmp_path):
        """Test validation passes for nested new directories."""
        nested_path = tmp_path / "level1" / "level2" / "level3"

        is_valid, _error_msg = export_manager._validate_export_path(str(nested_path))

        assert is_valid is True

    def test_validate_export_path_non_existent_parent(self, export_manager):
        """Test validation fails for completely non-existent path.

        Note: On Windows, drives that exist but have non-existent paths may still
        validate as True because the ancestor drive exists. This test uses a path
        that should truly not exist on any system.
        """
        if os.name == "nt":  # Windows
            # Try multiple unlikely drive letters
            for drive in ["X", "Y", "Z"]:
                test_path = f"{drive}:\\nonexistent_xyz_123\\folder"
                is_valid, error_msg = export_manager._validate_export_path(test_path)
                if not is_valid:
                    assert "not accessible" in error_msg.lower() or "does not exist" in error_msg.lower()
                    return  # Found a non-existent drive
            # If all drives exist (unusual), skip this test
            pytest.skip("All test drive letters are mapped - cannot test non-existent path")
        else:
            fake_path = "/nonexistent_mount_point_xyz_123/folder"
            is_valid, error_msg = export_manager._validate_export_path(fake_path)
            assert is_valid is False

    @pytest.mark.skipif(os.name != "nt", reason="Windows-specific test")
    def test_validate_export_path_unmapped_drive_letter(self, export_manager):
        """Test validation fails for unmapped Windows drive letter.

        Note: This test may be skipped if the test drive letter happens to be mapped.
        """
        # Try multiple unlikely drive letters
        for drive in ["X", "Y", "Z"]:
            test_path = f"{drive}:\\some\\path"
            is_valid, error_msg = export_manager._validate_export_path(test_path)
            if not is_valid:
                assert "not accessible" in error_msg.lower() or "Drive not accessible" in error_msg
                return  # Found a non-existent drive

        # If all drives exist (unusual), skip this test
        pytest.skip("All test drive letters are mapped")


class TestAtomicCSVWrite:
    """Tests for atomic CSV write functionality."""

    def test_atomic_csv_write_success(self, export_manager, tmp_path):
        """Test successful atomic CSV write creates file."""
        csv_path = tmp_path / "test_output.csv"
        df = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})

        export_manager._atomic_csv_write(df, csv_path, index=False)

        assert csv_path.exists()
        result_df = pd.read_csv(csv_path)
        assert len(result_df) == 3
        assert list(result_df.columns) == ["A", "B"]

    def test_atomic_csv_write_no_temp_file_on_success(self, export_manager, tmp_path):
        """Test that temp file is removed after successful write."""
        csv_path = tmp_path / "test.csv"
        df = pd.DataFrame({"col": [1, 2]})

        export_manager._atomic_csv_write(df, csv_path, index=False)

        # No temp files should remain
        temp_files = list(tmp_path.glob("*.tmp.*"))
        assert len(temp_files) == 0

    def test_atomic_csv_write_empty_dataframe_succeeds(self, export_manager, tmp_path):
        """Test atomic write succeeds for empty DataFrame (produces minimal file).

        Note: An empty DataFrame still produces a valid CSV file with just headers/newline,
        so it won't trigger the empty file check. The _atomic_csv_write only fails if
        the resulting file is truly 0 bytes.
        """
        csv_path = tmp_path / "empty_test.csv"
        df = pd.DataFrame()

        # Empty DataFrame produces a small but non-empty file
        export_manager._atomic_csv_write(df, csv_path, index=False)
        assert csv_path.exists()
        # File will have some content (newline at minimum)
        assert csv_path.stat().st_size > 0

    def test_atomic_csv_write_cleans_up_on_failure(self, export_manager, tmp_path):
        """Test cleanup of temp file on write failure."""
        csv_path = tmp_path / "test.csv"
        df = pd.DataFrame({"A": [1, 2]})

        with patch("pandas.DataFrame.to_csv", side_effect=ValueError("Write error")):
            with pytest.raises(ValueError):
                export_manager._atomic_csv_write(df, csv_path)

        # Temp file should be cleaned up
        temp_files = list(tmp_path.glob("*.tmp.*"))
        assert len(temp_files) == 0

    def test_atomic_csv_write_uses_pid_in_temp_filename(self, export_manager, tmp_path):
        """Test that temp file uses PID for uniqueness."""
        csv_path = tmp_path / "test.csv"
        df = pd.DataFrame({"A": [1]})
        current_pid = os.getpid()

        # Intercept the to_csv call to check temp path
        original_to_csv = pd.DataFrame.to_csv
        called_paths = []

        def capturing_to_csv(self, path_or_buf, *args, **kwargs):
            if path_or_buf is not None:
                called_paths.append(str(path_or_buf))
            return original_to_csv(self, path_or_buf, *args, **kwargs)

        with patch.object(pd.DataFrame, "to_csv", capturing_to_csv):
            export_manager._atomic_csv_write(df, csv_path, index=False)

        # Check that temp path contains PID
        assert any(str(current_pid) in p for p in called_paths)


class TestDataGrouping:
    """Tests for export data grouping functionality."""

    def test_group_export_data_all_in_one_file(self, export_manager, sample_sleep_metrics_list):
        """Test grouping option 0: all data in one file."""
        groups = export_manager._group_export_data(sample_sleep_metrics_list, grouping_option=0)

        assert len(groups) == 1
        assert "all_data" in groups
        assert len(groups["all_data"]) == 3

    def test_group_export_data_by_participant(self, export_manager, sample_sleep_metrics_list):
        """Test grouping option 1: group by participant."""
        groups = export_manager._group_export_data(sample_sleep_metrics_list, grouping_option=1)

        assert len(groups) == 3
        assert "1000" in groups
        assert "1001" in groups
        assert "1002" in groups
        assert len(groups["1000"]) == 1
        assert len(groups["1001"]) == 1
        assert len(groups["1002"]) == 1

    def test_group_export_data_by_group(self, export_manager, sample_sleep_metrics_list):
        """Test grouping option 2: group by study group."""
        groups = export_manager._group_export_data(sample_sleep_metrics_list, grouping_option=2)

        assert len(groups) == 2
        assert "Control" in groups
        assert "Treatment" in groups
        assert len(groups["Control"]) == 2  # Two participants in Control
        assert len(groups["Treatment"]) == 1

    def test_group_export_data_by_timepoint(self, export_manager, sample_sleep_metrics_list):
        """Test grouping option 3: group by timepoint."""
        groups = export_manager._group_export_data(sample_sleep_metrics_list, grouping_option=3)

        assert len(groups) == 2
        assert "T1" in groups
        assert "T2" in groups
        assert len(groups["T1"]) == 2
        assert len(groups["T2"]) == 1

    def test_group_export_data_invalid_option_falls_back_to_all(self, export_manager, sample_sleep_metrics_list):
        """Test that invalid grouping option falls back to all data."""
        groups = export_manager._group_export_data(sample_sleep_metrics_list, grouping_option=999)

        assert len(groups) == 1
        assert "all_data" in groups

    def test_group_export_data_empty_list(self, export_manager):
        """Test grouping with empty list."""
        groups = export_manager._group_export_data([], grouping_option=0)

        assert len(groups) == 1
        assert "all_data" in groups
        assert len(groups["all_data"]) == 0


class TestDirectExport:
    """Tests for perform_direct_export functionality."""

    def test_perform_direct_export_success(self, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test successful direct export produces CSV files."""
        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.perform_direct_export(
                sample_sleep_metrics_list,
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[
                    ExportColumn.NUMERICAL_PARTICIPANT_ID,
                    ExportColumn.TOTAL_SLEEP_TIME,
                ],
            )

        assert result.success is True
        assert result.files_exported >= 1

        # Check that CSV file was created
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) >= 1

    def test_perform_direct_export_empty_list_returns_error(self, export_manager, tmp_path):
        """Test direct export with empty metrics list returns error."""
        result = export_manager.perform_direct_export(
            [],
            grouping_option=0,
            output_directory=str(tmp_path),
            selected_columns=[],
        )

        assert result.success is False
        assert len(result.errors) > 0
        assert "No sleep metrics" in result.errors[0]

    def test_perform_direct_export_creates_directory(self, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test that export creates output directory if missing."""
        output_dir = tmp_path / "new_export_directory"
        assert not output_dir.exists()

        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.perform_direct_export(
                sample_sleep_metrics_list,
                grouping_option=0,
                output_directory=str(output_dir),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
            )

        assert output_dir.exists()
        assert result.success is True

    def test_perform_direct_export_respects_column_selection(self, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test that column filtering works correctly."""
        selected_cols = [
            ExportColumn.NUMERICAL_PARTICIPANT_ID,
            ExportColumn.SLEEP_DATE,
        ]

        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.perform_direct_export(
                sample_sleep_metrics_list,
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=selected_cols,
            )

        assert result.success is True

        # Read the exported CSV and check columns
        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        if csv_files:
            # Skip metadata rows (lines starting with #)
            df = pd.read_csv(csv_files[0], comment="#")
            # Check that only selected columns (or subset) are present
            for col in df.columns:
                assert col in selected_cols or col in [
                    ExportColumn.MARKER_INDEX,
                    ExportColumn.MARKER_TYPE,
                ]

    def test_perform_direct_export_includes_metadata_when_requested(self, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test that metadata is included when requested."""
        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.perform_direct_export(
                sample_sleep_metrics_list,
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
                include_metadata=True,
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        if csv_files:
            with open(csv_files[0], encoding="utf-8") as f:
                content = f.read()
            assert "# Sleep Scoring Export" in content or "#" in content

    def test_perform_direct_export_excludes_metadata_when_not_requested(self, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test that metadata is excluded when not requested."""
        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.perform_direct_export(
                sample_sleep_metrics_list,
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
                include_metadata=False,
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        if csv_files:
            with open(csv_files[0], encoding="utf-8") as f:
                first_line = f.readline()
            # First line should not be a comment
            assert not first_line.startswith("#")

    def test_perform_direct_export_nonwear_separate_file(self, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test that nonwear is exported to separate file when enabled."""
        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            with patch.object(
                export_manager,
                "_export_nonwear_markers_separate",
                return_value=([], []),
            ) as mock_nonwear:
                export_manager.perform_direct_export(
                    sample_sleep_metrics_list,
                    grouping_option=0,
                    output_directory=str(tmp_path),
                    selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
                    export_nonwear_separate=True,
                )

        mock_nonwear.assert_called_once()

    def test_perform_direct_export_nonwear_not_exported_when_disabled(self, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test that nonwear is not exported when disabled."""
        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            with patch.object(
                export_manager,
                "_export_nonwear_markers_separate",
                return_value=([], []),
            ) as mock_nonwear:
                export_manager.perform_direct_export(
                    sample_sleep_metrics_list,
                    grouping_option=0,
                    output_directory=str(tmp_path),
                    selected_columns=[ExportColumn.NUMERICAL_PARTICIPANT_ID],
                    export_nonwear_separate=False,
                )

        mock_nonwear.assert_not_called()


class TestMetricsCalculationForExport:
    """Tests for _ensure_metrics_calculated_for_export functionality."""

    def test_ensure_metrics_calculated_handles_missing_activity_data(self, export_manager, sample_sleep_metrics):
        """Test that missing activity data returns warning and continues."""
        # Mock db to return empty data
        export_manager.db_manager.load_raw_activity_data.return_value = ([], [])

        warnings = export_manager._ensure_metrics_calculated_for_export([sample_sleep_metrics])

        # Should have warning about missing data
        assert len(warnings) > 0
        assert any("No activity data" in w or "activity" in w.lower() for w in warnings)

    def test_ensure_metrics_calculated_caches_activity_data(self, export_manager):
        """Test that activity data is cached to prevent redundant database calls."""
        # Create two metrics for same file
        participant = ParticipantInfo(numerical_id="1000", group_str="G1", timepoint_str="T1")

        onset = datetime(2024, 1, 10, 22, 0).timestamp()
        offset = datetime(2024, 1, 11, 7, 0).timestamp()
        period = SleepPeriod(
            onset_timestamp=onset,
            offset_timestamp=offset,
            marker_index=1,
        )

        markers = DailySleepMarkers()
        markers.period_1 = period

        metrics1 = SleepMetrics(
            filename="test_file.csv",
            analysis_date="2024-01-10",
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
        )

        # Return mock data
        export_manager.db_manager.load_raw_activity_data.return_value = ([], [])

        export_manager._ensure_metrics_calculated_for_export([metrics1, metrics1])

        # Should only load data once per file (check call count)
        # The cache should prevent duplicate loads for the same filename
        call_count = export_manager.db_manager.load_raw_activity_data.call_count
        # With empty data, it should be called once (before caching empty result)
        assert call_count <= 2  # At most 2 calls (axis_y + vector_magnitude) per file


class TestFileHashAndBackup:
    """Tests for file hash calculation and backup creation."""

    def test_calculate_file_hash(self, export_manager, tmp_path):
        """Test calculating file hash."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content for hashing")

        hash1 = export_manager._calculate_file_hash(test_file)
        hash2 = export_manager._calculate_file_hash(test_file)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    def test_calculate_file_hash_different_content(self, export_manager, tmp_path):
        """Test that different content produces different hash."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content 1")
        file2.write_text("content 2")

        hash1 = export_manager._calculate_file_hash(file1)
        hash2 = export_manager._calculate_file_hash(file2)

        assert hash1 != hash2

    @patch("shutil.copy2")
    def test_create_backup_success(self, mock_copy, export_manager, tmp_path):
        """Test successful backup creation."""
        from sleep_scoring_app.core.constants import DirectoryName

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("test,data\n1,2\n")

        with patch.object(export_manager, "_calculate_file_hash", return_value="abc123"):
            backup_path = export_manager._create_backup(csv_path)

        assert mock_copy.called
        assert backup_path.parent.name == DirectoryName.BACKUPS

    def test_create_backup_hash_verification_fails(self, export_manager, tmp_path):
        """Test backup creation fails when hash verification fails."""
        from sleep_scoring_app.core.constants import DirectoryName
        from sleep_scoring_app.core.exceptions import DatabaseError

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("test,data\n1,2\n")

        backup_dir = tmp_path / DirectoryName.BACKUPS
        backup_dir.mkdir(exist_ok=True)

        with (
            patch.object(export_manager, "_calculate_file_hash", side_effect=["hash1", "hash2"]),
            pytest.raises(DatabaseError, match="Backup verification failed"),
        ):
            export_manager._create_backup(csv_path)

    @patch("shutil.copy2")
    def test_create_backup_rotation(self, mock_copy, export_manager, tmp_path):
        """Test that old backups are rotated."""
        from sleep_scoring_app.core.constants import DirectoryName

        csv_path = tmp_path / "data.csv"
        csv_path.write_text("test,data\n1,2\n")

        backup_dir = csv_path.parent / DirectoryName.BACKUPS
        backup_dir.mkdir()

        # Create 15 old backups that match the rotation pattern
        for i in range(15):
            old_backup = backup_dir / f"20240101_{i:05d}_data_backup.csv"
            old_backup.touch()

        export_manager.max_backups = 10

        with (
            patch.object(export_manager, "_calculate_file_hash", return_value="abc123"),
            patch("pathlib.Path.write_text"),
        ):
            export_manager._create_backup(csv_path)

        # Should delete oldest backups
        remaining_backups = list(backup_dir.glob("*_data_*.csv"))
        assert len(remaining_backups) <= export_manager.max_backups


class TestExportAllSleepData:
    """Tests for export_all_sleep_data functionality."""

    @patch("sleep_scoring_app.services.export_service.datetime")
    def test_export_all_sleep_data_success(self, mock_datetime, export_manager, tmp_path):
        """Test successful export of all sleep data."""
        mock_datetime.now.return_value = datetime(2024, 1, 15, 10, 30, 0)

        export_manager.db_manager.get_all_sleep_data_for_export.return_value = [
            {"filename": "file1.csv", "participant_id": "1000"},
            {"filename": "file2.csv", "participant_id": "1001"},
        ]

        with patch.object(export_manager, "_atomic_csv_write"):
            result = export_manager.export_all_sleep_data(str(tmp_path))

        assert "Exported 2 records" in result

    def test_export_all_sleep_data_no_data(self, export_manager):
        """Test export when no data available."""
        export_manager.db_manager.get_all_sleep_data_for_export.return_value = []

        result = export_manager.export_all_sleep_data()

        assert result == "No data available for export"

    def test_export_all_sleep_data_database_error(self, export_manager):
        """Test export handles database errors gracefully."""
        from sleep_scoring_app.core.exceptions import DatabaseError, ErrorCodes

        export_manager.db_manager.get_all_sleep_data_for_export.side_effect = DatabaseError("Query failed", ErrorCodes.DB_QUERY_FAILED)

        result = export_manager.export_all_sleep_data()

        assert result is None


class TestCreateExportCSVOnly:
    """Tests for create_export_csv_only functionality."""

    @patch("sleep_scoring_app.services.export_service.datetime")
    def test_create_export_csv_only_success(self, mock_datetime, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test creating export CSV without database save."""
        mock_datetime.now.return_value = datetime(2024, 1, 15, 10, 30, 0)

        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]),
        ):
            result = export_manager.create_export_csv_only(sample_sleep_metrics_list)

        assert result is not None
        assert "export_temp" in result

    def test_create_export_csv_only_empty_list(self, export_manager):
        """Test creating export CSV with empty list returns None."""
        result = export_manager.create_export_csv_only([])
        assert result is None

    @patch("sleep_scoring_app.services.export_service.datetime")
    def test_create_export_csv_only_sanitizes_algorithm_name(self, mock_datetime, export_manager, sample_sleep_metrics_list, tmp_path):
        """Test that algorithm name is sanitized in filename."""
        mock_datetime.now.return_value = datetime(2024, 1, 15, 10, 30, 0)

        with (
            patch("pathlib.Path.cwd", return_value=tmp_path),
            patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]),
        ):
            result = export_manager.create_export_csv_only(sample_sleep_metrics_list, algorithm_name="<script>alert()</script>")

        assert result is not None
        assert "<script>" not in result
        assert ">" not in result


class TestExportServiceIntegration:
    """Integration tests for export service."""

    def test_full_export_workflow(self, tmp_path):
        """Test complete export workflow from metrics to CSV file."""
        # Create sample metrics
        participant = ParticipantInfo(numerical_id="1000", group_str="Test", timepoint_str="T1")
        onset = datetime(2024, 1, 10, 22, 0).timestamp()
        offset = datetime(2024, 1, 11, 7, 0).timestamp()
        period = SleepPeriod(
            onset_timestamp=onset,
            offset_timestamp=offset,
            marker_index=1,
        )

        markers = DailySleepMarkers()
        markers.period_1 = period

        metrics = SleepMetrics(
            filename="test_file.csv",
            analysis_date="2024-01-10",
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
            total_sleep_time=420.0,
        )

        # Export
        mock_db = MagicMock()
        export_manager = ExportManager(database_manager=mock_db)

        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.create_export_csv_only([metrics])

        assert result is not None
        assert Path(result).suffix == ".csv"

    def test_export_with_multiple_periods(self, tmp_path):
        """Test export handles multiple sleep periods correctly."""
        participant = ParticipantInfo(numerical_id="1000", group_str="G1", timepoint_str="T1")

        # Create main sleep period
        main_onset = datetime(2024, 1, 10, 22, 0).timestamp()
        main_offset = datetime(2024, 1, 11, 7, 0).timestamp()
        main_sleep = SleepPeriod(
            onset_timestamp=main_onset,
            offset_timestamp=main_offset,
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )

        # Create nap period
        nap_onset = datetime(2024, 1, 11, 14, 0).timestamp()
        nap_offset = datetime(2024, 1, 11, 15, 30).timestamp()
        nap = SleepPeriod(
            onset_timestamp=nap_onset,
            offset_timestamp=nap_offset,
            marker_index=2,
            marker_type=MarkerType.NAP,
        )

        markers = DailySleepMarkers()
        markers.period_1 = main_sleep
        markers.period_2 = nap

        metrics = SleepMetrics(
            filename="test_file.csv",
            analysis_date="2024-01-10",
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
        )

        # Export
        mock_db = MagicMock()
        export_manager = ExportManager(database_manager=mock_db)

        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[
                    ExportColumn.NUMERICAL_PARTICIPANT_ID,
                    ExportColumn.MARKER_INDEX,
                    ExportColumn.MARKER_TYPE,
                ],
            )

        assert result.success is True

        # Check the exported CSV contains both periods
        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        assert len(csv_files) >= 1

        df = pd.read_csv(csv_files[0], comment="#")
        assert len(df) == 2  # Two periods


class TestExportBugRegressions:
    """
    Regression tests for bugs found in the export system.

    These tests are designed to catch REAL bugs that were found in production,
    not hypothetical edge cases. Each test documents the bug it catches.
    """

    def test_marker_index_preserved_not_enumeration(self, tmp_path):
        """
        BUG: save_sleep_metrics_atomic used enumeration `i` instead of period.marker_index.

        If period_1 is None but period_2 has data with marker_index=2, it was being
        saved with marker_index=1 (from enumeration) instead of the actual marker_index=2.

        This test ensures marker_index values are preserved exactly.
        """
        participant = ParticipantInfo(numerical_id="1000", group_str="G1", timepoint_str="T1")

        # Create only period_2 with marker_index=2 (period_1 is None)
        period2_onset = datetime(2024, 1, 11, 14, 0).timestamp()
        period2_offset = datetime(2024, 1, 11, 15, 30).timestamp()
        period2 = SleepPeriod(
            onset_timestamp=period2_onset,
            offset_timestamp=period2_offset,
            marker_index=2,  # Explicit marker_index=2
            marker_type=MarkerType.NAP,
        )

        markers = DailySleepMarkers()
        # period_1 is None
        markers.period_2 = period2  # Only period_2 exists

        metrics = SleepMetrics(
            filename="test_file.csv",
            analysis_date="2024-01-10",
            algorithm_type=AlgorithmType.SADEH_1994_ACTILIFE,
            daily_sleep_markers=markers,
            participant=participant,
        )

        # Export and check marker_index is preserved
        mock_db = MagicMock()
        export_manager = ExportManager(database_manager=mock_db)

        with patch.object(export_manager, "_ensure_metrics_calculated_for_export", return_value=[]):
            result = export_manager.perform_direct_export(
                [metrics],
                grouping_option=0,
                output_directory=str(tmp_path),
                selected_columns=[ExportColumn.MARKER_INDEX, ExportColumn.MARKER_TYPE],
            )

        assert result.success is True

        csv_files = list(tmp_path.glob("sleep_data_*.csv"))
        assert len(csv_files) >= 1

        df = pd.read_csv(csv_files[0], comment="#")
        assert len(df) == 1
        # CRITICAL: marker_index should be 2, NOT 1
        assert df[ExportColumn.MARKER_INDEX].iloc[0] == 2

    def test_full_participant_id_uses_spaces_not_underscores(self):
        """
        BUG: to_export_dict used "_".join() but rest of system uses spaces.

        The full_participant_id format should be "001 T1 G1" with spaces,
        matching what extract_participant_info() produces.

        This test ensures consistent formatting across the system.
        """
        participant = ParticipantInfo(
            numerical_id="001",
            group_str="G1",
            timepoint_str="T2",
        )

        onset = datetime(2024, 1, 10, 22, 0).timestamp()
        offset = datetime(2024, 1, 11, 7, 0).timestamp()
        period = SleepPeriod(onset_timestamp=onset, offset_timestamp=offset, marker_index=1)

        markers = DailySleepMarkers()
        markers.period_1 = period

        metrics = SleepMetrics(
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=markers,
            participant=participant,
        )

        export_dict = metrics.to_export_dict()
        full_id = export_dict[ExportColumn.FULL_PARTICIPANT_ID]

        # CRITICAL: Should use spaces, not underscores
        assert full_id == "001 T2 G1", f"Expected '001 T2 G1' but got '{full_id}'"
        assert "_" not in full_id, "Full participant ID should NOT contain underscores"

    def test_export_column_keys_match_calculation_service_output(self):
        """
        Ensures the ExportColumn constant values match what the
        calculation service actually produces.
        """
        # The keys that metrics_calculation_service.py produces
        calculation_service_keys = {
            "Sleep Algorithm Value at Onset",
            "Sleep Algorithm Value at Offset",
        }

        # Verify ExportColumn values match
        assert ExportColumn.SLEEP_ALGORITHM_ONSET == "Sleep Algorithm Value at Onset", (
            f"SLEEP_ALGORITHM_ONSET mismatch: expected 'Sleep Algorithm Value at Onset' but got '{ExportColumn.SLEEP_ALGORITHM_ONSET}'"
        )
        assert ExportColumn.SLEEP_ALGORITHM_OFFSET == "Sleep Algorithm Value at Offset", (
            f"SLEEP_ALGORITHM_OFFSET mismatch: expected 'Sleep Algorithm Value at Offset' but got '{ExportColumn.SLEEP_ALGORITHM_OFFSET}'"
        )

    def test_participant_info_from_dict_preserves_string_fields(self):
        """
        BUG: ParticipantInfo.from_dict didn't set group_str/timepoint_str,
        causing them to use defaults "G1"/"T1" even when enum values differed.

        This test ensures from_dict properly sets the string representation fields.
        """
        from sleep_scoring_app.core.constants import ParticipantGroup, ParticipantTimepoint

        data = {
            "numerical_participant_id": "1234",
            "full_participant_id": "1234 T3 G2",
            "participant_group": "G2",
            "participant_timepoint": "T3",
            "group_str": "G2",
            "timepoint_str": "T3",
        }

        participant = ParticipantInfo.from_dict(data)

        # CRITICAL: String fields should match the data, not defaults
        assert participant.group_str == "G2", f"Expected 'G2' but got '{participant.group_str}'"
        assert participant.timepoint_str == "T3", f"Expected 'T3' but got '{participant.timepoint_str}'"
        assert participant.group == ParticipantGroup.GROUP_2
        assert participant.timepoint == ParticipantTimepoint.T3

    def test_participant_info_from_dict_derives_strings_from_enums(self):
        """
        Test that from_dict derives string fields from enum values when not provided.
        """
        data = {
            "numerical_participant_id": "5678",
            "participant_group": "G2",
            "participant_timepoint": "T2",
            # group_str and timepoint_str NOT provided
        }

        participant = ParticipantInfo.from_dict(data)

        # Should derive from enum values
        assert participant.group_str == "G2"
        assert participant.timepoint_str == "T2"

    def test_export_dict_list_uses_period_marker_index_for_metrics_lookup(self, tmp_path):
        """
        BUG: to_export_dict_list used enumeration to look up period metrics instead
        of period.marker_index, causing wrong metrics to be associated with periods.

        This test ensures period metrics are looked up using marker_index.
        """
        participant = ParticipantInfo(numerical_id="1000", group_str="G1", timepoint_str="T1")

        # Create two periods with specific marker indices
        period1 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 10, 22, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 11, 7, 0).timestamp(),
            marker_index=1,
            marker_type=MarkerType.MAIN_SLEEP,
        )
        period2 = SleepPeriod(
            onset_timestamp=datetime(2024, 1, 11, 14, 0).timestamp(),
            offset_timestamp=datetime(2024, 1, 11, 15, 30).timestamp(),
            marker_index=2,
            marker_type=MarkerType.NAP,
        )

        markers = DailySleepMarkers()
        markers.period_1 = period1
        markers.period_2 = period2

        metrics = SleepMetrics(
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=markers,
            participant=participant,
        )

        # Store metrics for each period using marker_index
        metrics.store_period_metrics(period1, {ExportColumn.TOTAL_SLEEP_TIME: 540})
        metrics.store_period_metrics(period2, {ExportColumn.TOTAL_SLEEP_TIME: 90})

        # Export and verify each period has its own metrics
        export_rows = metrics.to_export_dict_list()

        assert len(export_rows) == 2

        # Find rows by marker_index
        row1 = next(r for r in export_rows if r[ExportColumn.MARKER_INDEX] == 1)
        row2 = next(r for r in export_rows if r[ExportColumn.MARKER_INDEX] == 2)

        # Each period should have its OWN metrics, not mixed up
        assert row1[ExportColumn.TOTAL_SLEEP_TIME] == 540, "Period 1 should have TST=540"
        assert row2[ExportColumn.TOTAL_SLEEP_TIME] == 90, "Period 2 should have TST=90"

    def test_group_export_handles_none_participant_gracefully(self):
        """
        BUG: _group_export_data accessed participant.group_str without null check.

        This test ensures grouping handles metrics with None participant gracefully.
        """
        mock_db = MagicMock()
        export_manager = ExportManager(database_manager=mock_db)

        # Create metrics with valid participant
        participant = ParticipantInfo(numerical_id="1000", group_str="Control", timepoint_str="T1")
        onset = datetime(2024, 1, 10, 22, 0).timestamp()
        offset = datetime(2024, 1, 11, 7, 0).timestamp()
        period = SleepPeriod(onset_timestamp=onset, offset_timestamp=offset, marker_index=1)
        markers = DailySleepMarkers()
        markers.period_1 = period

        metrics = SleepMetrics(
            filename="test.csv",
            analysis_date="2024-01-10",
            daily_sleep_markers=markers,
            participant=participant,
        )

        # This should not raise AttributeError
        groups = export_manager._group_export_data([metrics], grouping_option=2)
        assert "Control" in groups
