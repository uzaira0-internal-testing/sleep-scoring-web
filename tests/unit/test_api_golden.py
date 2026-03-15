"""
API response golden tests.

Verifies that the OpenAPI spec contains expected endpoints and that
Pydantic response model schemas have the expected fields and types.

These tests catch unintentional breaking changes to the API contract.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from sleep_scoring_web.main import app
from sleep_scoring_web.schemas.models import (
    ActivityDataColumnar,
    ActivityDataResponse,
    ConsensusStatusResponse,
    DateStatus,
    ExportColumnInfo,
    ExportColumnsResponse,
    ExportRequest,
    ExportResponse,
    FileInfo,
    FileUploadResponse,
    FullTableColumnar,
    ManualNonwearPeriod,
    MarkerResponse,
    MarkerUpdateRequest,
    OnsetOffsetColumnar,
    OnsetOffsetColumnarResponse,
    ProcessingStatusResponse,
    SleepMetrics,
    SleepPeriod,
)


# ---------------------------------------------------------------------------
# OpenAPI endpoint presence tests
# ---------------------------------------------------------------------------

class TestOpenAPIEndpoints:
    """Verify the OpenAPI spec lists all expected endpoints."""

    @pytest.fixture(autouse=True)
    def _load_spec(self) -> None:
        self.spec = app.openapi()
        self.paths = set(self.spec.get("paths", {}).keys())

    EXPECTED_ENDPOINTS = [
        "/health",
        "/api/v1/files",
        "/api/v1/files/upload",
        "/api/v1/markers/{file_id}/{analysis_date}",
        "/api/v1/activity/{file_id}/{analysis_date}",
    ]

    @pytest.mark.parametrize("path", EXPECTED_ENDPOINTS)
    def test_endpoint_present(self, path: str) -> None:
        """Endpoint must appear in the OpenAPI paths."""
        assert path in self.paths, (
            f"Endpoint '{path}' missing from OpenAPI spec. "
            f"Available paths (first 20): {sorted(self.paths)[:20]}"
        )

    def test_health_is_get(self) -> None:
        """Health check must be a GET endpoint."""
        health = self.spec["paths"].get("/health", {})
        assert "get" in health, "/health must support GET"

    def test_files_upload_is_post(self) -> None:
        """File upload must be a POST endpoint."""
        upload = self.spec["paths"].get("/api/v1/files/upload", {})
        assert "post" in upload, "/api/v1/files/upload must support POST"

    def test_markers_supports_get_and_put(self) -> None:
        """Markers endpoint must support GET (read) and PUT (update)."""
        markers = self.spec["paths"].get("/api/v1/markers/{file_id}/{analysis_date}", {})
        assert "get" in markers, "markers endpoint must support GET"
        assert "put" in markers, "markers endpoint must support PUT"

    def test_spec_has_info(self) -> None:
        """Spec must have title and version."""
        info = self.spec.get("info", {})
        assert "title" in info
        assert "version" in info


# ---------------------------------------------------------------------------
# Pydantic model schema golden tests
# ---------------------------------------------------------------------------

class TestSleepPeriodSchema:
    """SleepPeriod model must have expected fields."""

    EXPECTED_FIELDS = {"onset_timestamp", "offset_timestamp", "marker_index", "marker_type"}

    def test_fields_present(self) -> None:
        schema_fields = set(SleepPeriod.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"SleepPeriod missing fields: {missing}"

    def test_default_marker_type(self) -> None:
        period = SleepPeriod()
        assert period.marker_type == "MAIN_SLEEP"

    def test_default_marker_index(self) -> None:
        period = SleepPeriod()
        assert period.marker_index == 1


class TestManualNonwearPeriodSchema:
    """ManualNonwearPeriod model must have expected fields."""

    EXPECTED_FIELDS = {"start_timestamp", "end_timestamp", "marker_index"}

    def test_fields_present(self) -> None:
        schema_fields = set(ManualNonwearPeriod.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"ManualNonwearPeriod missing fields: {missing}"


class TestSleepMetricsSchema:
    """SleepMetrics model must have Tudor-Locke metric fields."""

    EXPECTED_FIELDS = {
        "in_bed_time",
        "out_bed_time",
        "sleep_onset",
        "sleep_offset",
        "time_in_bed_minutes",
        "total_sleep_time_minutes",
        "sleep_onset_latency_minutes",
        "waso_minutes",
        "number_of_awakenings",
        "average_awakening_length_minutes",
        "sleep_efficiency",
        "movement_index",
        "fragmentation_index",
        "sleep_fragmentation_index",
        "total_activity",
        "nonzero_epochs",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(SleepMetrics.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"SleepMetrics missing fields: {missing}"

    def test_all_fields_default_none(self) -> None:
        """All SleepMetrics fields should default to None."""
        metrics = SleepMetrics()
        for field in self.EXPECTED_FIELDS:
            assert getattr(metrics, field) is None, f"Field '{field}' should default to None"


class TestFileInfoSchema:
    """FileInfo model must have expected fields."""

    EXPECTED_FIELDS = {
        "id", "filename", "file_type", "participant_id",
        "status", "row_count", "start_time", "end_time",
        "uploaded_by", "uploaded_at",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(FileInfo.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"FileInfo missing fields: {missing}"


class TestFileUploadResponseSchema:
    """FileUploadResponse model must have expected fields."""

    EXPECTED_FIELDS = {"file_id", "filename", "status", "row_count", "message"}

    def test_fields_present(self) -> None:
        schema_fields = set(FileUploadResponse.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"FileUploadResponse missing fields: {missing}"


class TestMarkerResponseSchema:
    """MarkerResponse model must have expected fields."""

    EXPECTED_FIELDS = {
        "sleep_markers", "nonwear_markers", "verification_status",
        "algorithm_used", "last_modified_by", "last_modified_at",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(MarkerResponse.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"MarkerResponse missing fields: {missing}"


class TestMarkerUpdateRequestSchema:
    """MarkerUpdateRequest model must have expected fields."""

    EXPECTED_FIELDS = {
        "sleep_markers", "nonwear_markers", "algorithm_used",
        "detection_rule", "notes", "is_no_sleep", "needs_consensus",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(MarkerUpdateRequest.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"MarkerUpdateRequest missing fields: {missing}"


class TestActivityDataResponseSchema:
    """ActivityDataResponse model must have expected fields."""

    EXPECTED_FIELDS = {
        "data", "available_dates", "current_date_index",
        "algorithm_results", "nonwear_results", "sensor_nonwear_periods",
        "file_id", "analysis_date", "view_start", "view_end",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(ActivityDataResponse.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"ActivityDataResponse missing fields: {missing}"


class TestActivityDataColumnarSchema:
    """ActivityDataColumnar model must have expected fields."""

    EXPECTED_FIELDS = {"timestamps", "axis_x", "axis_y", "axis_z", "vector_magnitude"}

    def test_fields_present(self) -> None:
        schema_fields = set(ActivityDataColumnar.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"ActivityDataColumnar missing fields: {missing}"


class TestProcessingStatusResponseSchema:
    """ProcessingStatusResponse model must have expected fields."""

    EXPECTED_FIELDS = {
        "file_id", "status", "phase", "percent",
        "rows_processed", "total_rows_estimate", "error",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(ProcessingStatusResponse.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"ProcessingStatusResponse missing fields: {missing}"


class TestConsensusStatusResponseSchema:
    """ConsensusStatusResponse model must have expected fields."""

    EXPECTED_FIELDS = {
        "file_id", "analysis_date", "annotation_count",
        "has_consensus", "verification_tier",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(ConsensusStatusResponse.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"ConsensusStatusResponse missing fields: {missing}"


class TestExportModelsSchema:
    """Export-related models must have expected fields."""

    def test_export_column_info_fields(self) -> None:
        expected = {"name", "category", "description", "data_type", "is_default"}
        actual = set(ExportColumnInfo.model_fields.keys())
        missing = expected - actual
        assert not missing, f"ExportColumnInfo missing: {missing}"

    def test_export_request_fields(self) -> None:
        expected = {"file_ids", "date_range", "columns", "include_header", "include_metadata"}
        actual = set(ExportRequest.model_fields.keys())
        missing = expected - actual
        assert not missing, f"ExportRequest missing: {missing}"

    def test_export_response_fields(self) -> None:
        expected = {"success", "filename", "row_count", "file_count", "message", "warnings"}
        actual = set(ExportResponse.model_fields.keys())
        missing = expected - actual
        assert not missing, f"ExportResponse missing: {missing}"


class TestDateStatusSchema:
    """DateStatus model must have expected fields."""

    EXPECTED_FIELDS = {
        "date", "has_markers", "is_no_sleep",
        "needs_consensus", "has_auto_score",
        "complexity_pre", "complexity_post",
    }

    def test_fields_present(self) -> None:
        schema_fields = set(DateStatus.model_fields.keys())
        missing = self.EXPECTED_FIELDS - schema_fields
        assert not missing, f"DateStatus missing fields: {missing}"


# ---------------------------------------------------------------------------
# Timestamp normalization golden tests
# ---------------------------------------------------------------------------

class TestTimestampNormalization:
    """Verify the ms-to-s auto-conversion on SleepPeriod timestamps."""

    def test_seconds_pass_through(self) -> None:
        """Timestamps already in seconds should pass through unchanged."""
        period = SleepPeriod(onset_timestamp=1704110400.0, offset_timestamp=1704135600.0)
        assert period.onset_timestamp == 1704110400.0
        assert period.offset_timestamp == 1704135600.0

    def test_milliseconds_auto_converted(self) -> None:
        """Timestamps in milliseconds should be auto-converted to seconds."""
        ms_value = 1704110400000.0
        period = SleepPeriod(onset_timestamp=ms_value)
        assert period.onset_timestamp is not None
        assert period.onset_timestamp == pytest.approx(1704110400.0, abs=1.0)

    def test_none_timestamps_allowed(self) -> None:
        """None timestamps should be allowed (incomplete markers)."""
        period = SleepPeriod()
        assert period.onset_timestamp is None
        assert period.offset_timestamp is None
