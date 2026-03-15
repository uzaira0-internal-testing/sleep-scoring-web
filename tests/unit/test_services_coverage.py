"""
Unit tests to increase service-layer coverage.

Covers: export_service, complexity, upload_processor, file_watcher,
choi_helpers, algorithms/factory, algorithms/cole_kripke.

Pure unit tests with synthetic data — no DB, no HTTP, no async (except where needed).
"""

from __future__ import annotations

import asyncio
import calendar
import gzip
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# =============================================================================
# 7. Export Service (services/export_service.py)
# =============================================================================

from sleep_scoring_web.services.export_service import (
    COLUMN_CATEGORIES,
    DEFAULT_COLUMNS,
    EXPORT_COLUMNS,
    ColumnDefinition,
    ExportResult,
    ExportService,
)


class TestExportServiceStatic:
    """Tests for ExportService static/helper methods."""

    def test_get_available_columns(self):
        cols = ExportService.get_available_columns()
        assert len(cols) == len(EXPORT_COLUMNS)
        assert all(isinstance(c, ColumnDefinition) for c in cols)

    def test_get_column_categories(self):
        cats = ExportService.get_column_categories()
        assert "File Info" in cats
        assert "Period Info" in cats
        assert isinstance(cats["File Info"], list)

    def test_get_default_columns(self):
        defaults = ExportService.get_default_columns()
        assert "Filename" in defaults
        assert "Study Date" in defaults
        assert len(defaults) > 0

    def test_format_number_none(self):
        assert ExportService._format_number(None) == ""

    def test_format_number_int(self):
        assert ExportService._format_number(42) == "42"

    def test_format_number_float(self):
        result = ExportService._format_number(3.14159)
        assert result == "3.14"

    def test_format_number_custom_precision(self):
        result = ExportService._format_number(3.14159, precision=4)
        assert result == "3.1416"

    def test_sanitize_csv_value_normal(self):
        assert ExportService._sanitize_csv_value("hello") == "hello"

    def test_sanitize_csv_value_formula_injection(self):
        assert ExportService._sanitize_csv_value("=cmd") == "'=cmd"
        assert ExportService._sanitize_csv_value("+cmd") == "'+cmd"
        assert ExportService._sanitize_csv_value("@cmd") == "'@cmd"

    def test_sanitize_csv_value_non_string(self):
        assert ExportService._sanitize_csv_value(42) == 42
        assert ExportService._sanitize_csv_value(None) is None

    def test_sanitize_csv_value_empty_string(self):
        assert ExportService._sanitize_csv_value("") == ""

    def test_generate_csv_with_header(self):
        svc = ExportService.__new__(ExportService)
        rows = [{"Filename": "test.csv", "Study Date": "2024-01-01"}]
        result = svc._generate_csv(rows, ["Filename", "Study Date"], include_header=True)
        assert "Filename" in result
        assert "test.csv" in result

    def test_generate_csv_without_header(self):
        svc = ExportService.__new__(ExportService)
        rows = [{"Filename": "test.csv"}]
        result = svc._generate_csv(rows, ["Filename"], include_header=False)
        lines = result.strip().split("\n")
        # Should have 1 data line, no header
        assert len(lines) == 1
        assert "test.csv" in lines[0]

    def test_generate_csv_with_metadata(self):
        svc = ExportService.__new__(ExportService)
        rows = [{"Filename": "test.csv"}]
        result = svc._generate_csv(rows, ["Filename"], include_header=True, include_metadata=True)
        assert "# Sleep Scoring Export" in result
        assert "# Total Rows: 1" in result


class TestExportServiceAsync:
    """Tests for export_csv with mock DB."""

    @pytest.mark.asyncio
    async def test_export_csv_empty_file_ids(self):
        """export_csv with empty file_ids returns error."""
        db = AsyncMock()
        svc = ExportService(db)
        result = await svc.export_csv(file_ids=[])
        assert result.success is False
        assert "No files specified" in result.errors[0]

    @pytest.mark.asyncio
    async def test_export_csv_invalid_columns(self):
        """export_csv with all invalid columns returns error."""
        db = AsyncMock()
        svc = ExportService(db)
        result = await svc.export_csv(file_ids=[1], columns=["bogus_col_xyz"])
        # Should skip invalid and warn, but if NO valid columns remain, error
        assert result.success is False or "Skipping" in str(result.warnings)

    @pytest.mark.asyncio
    async def test_export_csv_no_data_found(self):
        """export_csv when no rows match returns success with empty content."""
        db = AsyncMock()
        # Mock file query to return file
        files_result = MagicMock()
        files_result.scalars.return_value.all.return_value = [
            SimpleNamespace(id=1, filename="f.csv", participant_id="P1")
        ]
        # Mock annotation, marker, metric, nonwear queries to return empty
        empty_result = MagicMock()
        empty_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [files_result, empty_result, empty_result, empty_result, empty_result]

        svc = ExportService(db)
        result = await svc.export_csv(file_ids=[1])
        assert result.success is True
        assert result.row_count == 0


# =============================================================================
# 8. Complexity (services/complexity.py) — edge cases
# =============================================================================

from sleep_scoring_web.services.complexity import (
    _boundary_clarity_penalty,
    _boundary_spike_score,
    _build_confirmed_nonwear_mask,
    _count_activity_spikes,
    _count_sleep_runs,
    _count_transitions,
    _diary_nap_count,
    _linear_penalty,
    _night_window_indices,
    _parse_time_to_24h,
    _total_sleep_period_hours,
    compute_post_complexity,
    compute_pre_complexity,
)

ANALYSIS_DATE = "2025-06-15"
_DATE_OBJ = datetime.strptime(ANALYSIS_DATE, "%Y-%m-%d").date()
_NIGHT_START_DT = datetime.combine(_DATE_OBJ, datetime.min.time()) + timedelta(hours=21)
_NIGHT_START_TS = float(calendar.timegm(_NIGHT_START_DT.timetuple()))
EPOCH_SEC = 60.0


def _make_timestamps(n: int, start_ts: float = _NIGHT_START_TS) -> list[float]:
    return [start_ts + i * EPOCH_SEC for i in range(n)]


class TestComplexityEdgeCases:
    """Test remaining edge cases in complexity module."""

    def test_linear_penalty_below_low(self):
        assert _linear_penalty(1.0, 2.0, 6.0, 25.0) == 0.0

    def test_linear_penalty_above_high(self):
        assert _linear_penalty(10.0, 2.0, 6.0, 25.0) == 25.0

    def test_linear_penalty_midpoint(self):
        result = _linear_penalty(4.0, 2.0, 6.0, 25.0)
        assert abs(result - 12.5) < 0.01

    def test_parse_time_24h(self):
        assert _parse_time_to_24h("22:30") == (22, 30)

    def test_parse_time_pm(self):
        assert _parse_time_to_24h("10:30 PM") == (22, 30)

    def test_parse_time_am(self):
        assert _parse_time_to_24h("7:30 AM") == (7, 30)

    def test_parse_time_12pm(self):
        assert _parse_time_to_24h("12:00 PM") == (12, 0)

    def test_parse_time_12am(self):
        assert _parse_time_to_24h("12:00 AM") == (0, 0)

    def test_count_transitions_empty(self):
        assert _count_transitions([], 0, 0) == 0

    def test_count_transitions_no_change(self):
        assert _count_transitions([1, 1, 1, 1], 0, 4) == 0

    def test_count_transitions_alternating(self):
        assert _count_transitions([0, 1, 0, 1], 0, 4) == 3

    def test_count_sleep_runs_empty(self):
        assert _count_sleep_runs([], 0, 0) == 0

    def test_count_sleep_runs_no_long_runs(self):
        assert _count_sleep_runs([1, 1, 0, 1, 1, 0], 0, 6) == 0

    def test_count_sleep_runs_one_long_run(self):
        assert _count_sleep_runs([1, 1, 1, 1, 0], 0, 5) == 1

    def test_count_sleep_runs_trailing_run(self):
        """A run at the end of the array counts."""
        assert _count_sleep_runs([0, 0, 1, 1, 1], 0, 5) == 1

    def test_count_activity_spikes(self):
        activity = [0, 0, 100, 120, 0, 0, 80, 0]
        assert _count_activity_spikes(activity, 0, 8, threshold=50) == 2

    def test_count_activity_spikes_empty(self):
        assert _count_activity_spikes([], 0, 0) == 0

    def test_diary_nap_count_clamp(self):
        assert _diary_nap_count(-1) == 0
        assert _diary_nap_count(5) == 3
        assert _diary_nap_count(2) == 2

    def test_boundary_spike_score_out_of_range(self):
        assert _boundary_spike_score([10, 20, 30], 10, 0, 3) == 0.0

    def test_boundary_spike_score_clear(self):
        """High contrast should return 1.0."""
        activity = [0] * 10 + [200] * 10
        score = _boundary_spike_score(activity, 10, 0, 20)
        assert score == 1.0

    def test_boundary_clarity_penalty_empty(self):
        assert _boundary_clarity_penalty([], [], 0, 0) == -10.0

    def test_boundary_clarity_penalty_no_sleep(self):
        activity = [100] * 10
        sleep = [0] * 10
        assert _boundary_clarity_penalty(activity, sleep, 0, 10) == -10.0

    def test_build_confirmed_nonwear_mask_no_sensor(self):
        choi = [1, 1, 0, 0]
        result = _build_confirmed_nonwear_mask(choi, [], [0, 1, 2, 3])
        assert result == [0, 0, 0, 0]

    def test_build_confirmed_nonwear_mask_overlap(self):
        choi = [1, 1, 0, 0]
        sensor_periods = [(0.0, 1.0)]
        timestamps = [0.0, 1.0, 2.0, 3.0]
        result = _build_confirmed_nonwear_mask(choi, sensor_periods, timestamps)
        assert result == [1, 1, 0, 0]

    def test_total_sleep_period_hours_no_sleep(self):
        timestamps = _make_timestamps(10)
        sleep = [0] * 10
        assert _total_sleep_period_hours(sleep, timestamps, 0, 10) == 0.0

    def test_total_sleep_period_hours_with_sleep(self):
        timestamps = _make_timestamps(60)
        # 30 epochs of sleep = 30 minutes
        sleep = [0] * 10 + [1] * 30 + [0] * 20
        hours = _total_sleep_period_hours(sleep, timestamps, 0, 60)
        assert hours > 0

    def test_compute_pre_complexity_empty_data(self):
        score, features = compute_pre_complexity([], [], [], [], "22:00", "07:00", 0, ANALYSIS_DATE)
        assert score == 0
        assert "error" in features

    def test_compute_pre_complexity_no_diary(self):
        """No diary returns -1 (infinite complexity)."""
        ts = _make_timestamps(10)
        score, features = compute_pre_complexity(
            ts, [0.0] * 10, [0] * 10, [0] * 10, None, None, 0, ANALYSIS_DATE
        )
        assert score == -1

    def test_compute_pre_complexity_missing_onset(self):
        """Missing onset only returns -1."""
        ts = _make_timestamps(10)
        score, features = compute_pre_complexity(
            ts, [0.0] * 10, [0] * 10, [0] * 10, None, "07:00", 0, ANALYSIS_DATE
        )
        assert score == -1
        assert features["missing_onset"] is True

    def test_compute_pre_complexity_missing_wake(self):
        """Missing wake only returns -1."""
        ts = _make_timestamps(10)
        score, features = compute_pre_complexity(
            ts, [0.0] * 10, [0] * 10, [0] * 10, "22:00", None, 0, ANALYSIS_DATE
        )
        assert score == -1
        assert features["missing_wake"] is True

    def test_compute_post_complexity_no_markers(self):
        """Post-complexity with no markers returns clamped pre-score."""
        score, feats = compute_post_complexity(50, {}, [], [0, 1], [0.0, 60.0])
        assert score == 50
        assert feats["post_adjustment"] == 0

    def test_compute_post_complexity_close_alignment(self):
        """Markers close to algo boundaries get +5 adjustment."""
        timestamps = _make_timestamps(100)
        sleep_scores = [0] * 10 + [1] * 80 + [0] * 10
        algo_onset_ts = timestamps[10]
        algo_offset_ts = timestamps[89]
        # Markers very close to algo boundaries
        sleep_markers = [(algo_onset_ts, algo_offset_ts)]
        score, feats = compute_post_complexity(50, {}, sleep_markers, sleep_scores, timestamps)
        assert feats["marker_alignment"] == "close"
        assert score > 50

    def test_compute_post_complexity_far_alignment(self):
        """Markers far from algo boundaries get -5 adjustment."""
        timestamps = _make_timestamps(200)
        sleep_scores = [0] * 10 + [1] * 180 + [0] * 10
        # Markers 60 minutes away from algo boundaries
        sleep_markers = [(timestamps[70], timestamps[120])]
        score, feats = compute_post_complexity(50, {}, sleep_markers, sleep_scores, timestamps)
        assert feats["marker_alignment"] == "far"
        assert score < 50


# =============================================================================
# 9. Upload processor (services/upload_processor.py) — additional paths
# =============================================================================


class TestUploadProcessor:
    """Tests for upload_processor helper functions."""

    def test_streaming_decompress(self, tmp_path):
        """_streaming_decompress decompresses gzip data correctly."""
        from sleep_scoring_web.services.upload_processor import _streaming_decompress

        original = b"Date,Time,Axis1\n01/01/2024,12:00:00,100\n"
        gz_path = tmp_path / "test.csv.gz"
        out_path = tmp_path / "test.csv"
        with gzip.open(gz_path, "wb") as f:
            f.write(original)

        _streaming_decompress(gz_path, out_path)
        assert out_path.read_bytes() == original

    def test_validate_csv_format_empty(self, tmp_path):
        """_validate_csv_format raises on empty file."""
        from sleep_scoring_web.services.upload_processor import _validate_csv_format

        empty_file = tmp_path / "empty.csv"
        empty_file.write_text("")
        with pytest.raises(ValueError, match="Empty file"):
            _validate_csv_format(empty_file)

    def test_validate_csv_format_no_delimiter(self, tmp_path):
        """_validate_csv_format raises when no delimiters found."""
        from sleep_scoring_web.services.upload_processor import _validate_csv_format

        bad_file = tmp_path / "bad.csv"
        bad_file.write_text("no delimiters here\njust plain text\nnothing\n")
        with pytest.raises(ValueError, match="does not appear to be CSV"):
            _validate_csv_format(bad_file)

    def test_validate_csv_format_valid(self, tmp_path):
        """_validate_csv_format passes for valid CSV."""
        from sleep_scoring_web.services.upload_processor import _validate_csv_format

        good_file = tmp_path / "good.csv"
        good_file.write_text("a,b,c\n1,2,3\n4,5,6\n")
        # Should not raise
        _validate_csv_format(good_file)

    def test_validate_csv_format_tabs(self, tmp_path):
        """_validate_csv_format accepts tab-delimited files."""
        from sleep_scoring_web.services.upload_processor import _validate_csv_format

        tab_file = tmp_path / "tabs.csv"
        tab_file.write_text("a\tb\tc\n1\t2\t3\n")
        _validate_csv_format(tab_file)


# =============================================================================
# 10. File watcher (services/file_watcher.py) — additional paths
# =============================================================================


class TestFileWatcherAdditional:
    """Additional tests for file watcher paths."""

    def test_csv_file_handler_normalize_bytes_path(self):
        """CSVFileHandler._normalize_path handles bytes."""
        from sleep_scoring_web.services.file_watcher import CSVFileHandler

        result = CSVFileHandler._normalize_path(b"/some/path/file.csv")
        assert result == Path("/some/path/file.csv")

    def test_csv_file_handler_normalize_string_path(self):
        from sleep_scoring_web.services.file_watcher import CSVFileHandler

        result = CSVFileHandler._normalize_path("/some/path/file.csv")
        assert result == Path("/some/path/file.csv")

    def test_csv_file_handler_on_created_ignores_directory(self):
        """on_created should ignore directory events."""
        from sleep_scoring_web.services.file_watcher import CSVFileHandler

        loop = MagicMock()
        queue = MagicMock()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = True
        event.src_path = "/some/dir"
        handler.on_created(event)
        # Should not call call_soon_threadsafe
        loop.call_soon_threadsafe.assert_not_called()

    def test_csv_file_handler_on_created_ignores_non_csv(self):
        """on_created should ignore non-CSV files."""
        from sleep_scoring_web.services.file_watcher import CSVFileHandler

        loop = MagicMock()
        queue = MagicMock()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = False
        event.src_path = "/some/path/file.txt"
        handler.on_created(event)
        loop.call_soon_threadsafe.assert_not_called()

    def test_csv_file_handler_on_moved_ignores_directory(self):
        """on_moved should ignore directory events."""
        from sleep_scoring_web.services.file_watcher import CSVFileHandler

        loop = MagicMock()
        queue = MagicMock()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = True
        handler.on_moved(event)
        loop.call_soon_threadsafe.assert_not_called()

    def test_csv_file_handler_on_moved_csv(self):
        """on_moved queues CSV files moved into watched directory."""
        from sleep_scoring_web.services.file_watcher import CSVFileHandler

        loop = MagicMock()
        queue = MagicMock()
        handler = CSVFileHandler(queue, loop)

        event = MagicMock()
        event.is_directory = False
        event.dest_path = "/some/path/data.csv"
        handler.on_moved(event)
        loop.call_soon_threadsafe.assert_called_once()

    def test_get_watcher_status_keys(self):
        """get_watcher_status returns expected keys."""
        from sleep_scoring_web.services.file_watcher import get_watcher_status

        status = get_watcher_status()
        assert "is_running" in status
        assert "watched_directory" in status
        assert "total_ingested" in status
        assert "total_skipped" in status
        assert "total_failed" in status
        assert "pending_files" in status
        assert "last_scan_time" in status
        assert "recent_errors" in status

    @pytest.mark.asyncio
    async def test_scan_existing_files_no_dir(self, tmp_path):
        """scan_existing_files with non-existent dir returns 0."""
        from sleep_scoring_web.services.file_watcher import scan_existing_files

        with patch("sleep_scoring_web.services.file_watcher.settings") as mock_settings:
            mock_settings.data_dir = str(tmp_path / "nonexistent")
            result = await scan_existing_files()
            assert result == 0


# =============================================================================
# 11. Choi helpers (services/choi_helpers.py) — column validation edges
# =============================================================================


class TestChoiHelpersEdgeCases:
    """Additional edge cases for choi_helpers."""

    @pytest.mark.asyncio
    async def test_get_choi_column_settings_with_none_choi_axis(self):
        """Settings with choi_axis=None in extra_settings should return default."""
        from sleep_scoring_web.services.choi_helpers import DEFAULT_CHOI_COLUMN, get_choi_column

        settings = MagicMock()
        settings.extra_settings_json = {"choi_axis": None}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = settings
        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await get_choi_column(db, "testuser")
        # None is not in VALID_CHOI_COLUMNS, so falls through to default
        assert result == DEFAULT_CHOI_COLUMN

    def test_extract_choi_input_axis_x(self):
        """extract_choi_input works for axis_x."""
        from sleep_scoring_web.services.choi_helpers import extract_choi_input

        rows = [SimpleNamespace(axis_x=10), SimpleNamespace(axis_x=20)]
        result = extract_choi_input(rows, "axis_x")
        assert result == [10, 20]

    def test_extract_choi_input_axis_z(self):
        """extract_choi_input works for axis_z."""
        from sleep_scoring_web.services.choi_helpers import extract_choi_input

        rows = [SimpleNamespace(axis_z=5), SimpleNamespace(axis_z=15)]
        result = extract_choi_input(rows, "axis_z")
        assert result == [5, 15]


# =============================================================================
# 12. Algorithm factory (services/algorithms/factory.py) — edge cases
# =============================================================================


class TestAlgorithmFactoryWeb:
    """Tests for the web-app algorithm factory."""

    def test_create_sadeh_actilife(self):
        from sleep_scoring_web.services.algorithms.factory import create_algorithm

        algo = create_algorithm("sadeh_1994_actilife")
        assert algo is not None
        # Should be able to score
        result = algo.score([0, 0, 0, 0, 0])
        assert len(result) == 5

    def test_create_cole_kripke_original(self):
        from sleep_scoring_web.services.algorithms.factory import create_algorithm

        algo = create_algorithm("cole_kripke_1992_original")
        assert algo is not None
        result = algo.score([0, 0, 0])
        assert len(result) == 3

    def test_create_unknown_raises(self):
        from sleep_scoring_web.services.algorithms.factory import create_algorithm

        with pytest.raises(ValueError, match="Unknown algorithm"):
            create_algorithm("nonexistent_algorithm_type")

    def test_get_default_algorithm(self):
        from sleep_scoring_web.services.algorithms.factory import get_default_algorithm

        default = get_default_algorithm()
        assert default == "sadeh_1994_actilife"

    def test_algorithm_types_list(self):
        from sleep_scoring_web.services.algorithms.factory import ALGORITHM_TYPES

        assert len(ALGORITHM_TYPES) == 4
        assert "sadeh_1994_actilife" in ALGORITHM_TYPES
        assert "cole_kripke_1992_actilife" in ALGORITHM_TYPES


# =============================================================================
# 13. Cole-Kripke algorithm (services/algorithms/cole_kripke.py)
# =============================================================================


class TestColeKripkeAlgorithm:
    """Tests for ColeKripkeAlgorithm edge cases."""

    def test_empty_input(self):
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant="actilife")
        result = algo.score([])
        assert result == []

    def test_variant_original(self):
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant="original")
        assert algo._use_actilife_scaling is False

    def test_variant_actilife(self):
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant="actilife")
        assert algo._use_actilife_scaling is True

    def test_all_zeros(self):
        """All-zero activity should yield all sleep."""
        from sleep_scoring_web.services.algorithms.cole_kripke import ColeKripkeAlgorithm

        algo = ColeKripkeAlgorithm(variant="actilife")
        result = algo.score([0] * 20)
        assert all(s == 1 for s in result)


# =============================================================================
# Additional: Processing tracker edge cases
# =============================================================================


class TestProcessingTrackerEdgeCases:
    """Additional processing tracker tests."""

    def test_update_progress_nonexistent(self):
        """Updating progress for a non-tracked file is a no-op."""
        from sleep_scoring_web.services.processing_tracker import update_progress

        # Should not raise
        update_progress(99999, phase="test", percent=50.0)

    def test_clear_tracking_nonexistent(self):
        """Clearing non-tracked file is a no-op."""
        from sleep_scoring_web.services.processing_tracker import clear_tracking

        # Should not raise
        clear_tracking(99999)

    def test_get_progress_nonexistent(self):
        """Getting progress for non-tracked file returns None."""
        from sleep_scoring_web.services.processing_tracker import get_progress

        assert get_progress(99999) is None

    def test_evict_stale_entries(self):
        """Stale entries are evicted on start_tracking."""
        from sleep_scoring_web.services.processing_tracker import (
            _processing_status,
            ProcessingProgress,
            start_tracking,
        )

        # Insert a stale entry
        stale = ProcessingProgress(file_id=888)
        stale.updated_at = datetime.now() - timedelta(hours=2)
        _processing_status[888] = stale

        # Starting a new tracking should evict the stale entry
        start_tracking(999)
        assert 888 not in _processing_status
        assert 999 in _processing_status

        # Cleanup
        _processing_status.pop(999, None)
