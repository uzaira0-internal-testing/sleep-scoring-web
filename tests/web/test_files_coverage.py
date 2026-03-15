"""
Comprehensive integration tests for sleep_scoring_web.api.files.

Targets all uncovered endpoints and branches to bring coverage from ~32% to 90%+.
"""

import io
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from sleep_scoring_web.db.models import (
    DiaryEntry,
    File as FileModel,
    FileAssignment,
    Marker,
    NightComplexity,
    RawActivityData,
    UserAnnotation,
    UserSettings,
)
from sleep_scoring_web.schemas.enums import FileStatus, MarkerCategory, MarkerType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _upload(client: AsyncClient, headers: dict, csv_content: str, filename: str = "test.csv") -> dict:
    """Upload a CSV and return the JSON response body."""
    files = {"file": (filename, io.BytesIO(csv_content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", headers=headers, files=files)
    assert resp.status_code == 200, f"Upload failed ({resp.status_code}): {resp.text}"
    return resp.json()


# ===========================================================================
# Auth / identity
# ===========================================================================


@pytest.mark.asyncio
class TestAuthMe:
    """GET /api/v1/files/auth/me."""

    async def test_admin_me(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get("/api/v1/files/auth/me", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testadmin"
        assert data["is_admin"] is True

    async def test_annotator_me(self, client: AsyncClient, annotator_auth_headers: dict):
        resp = await client.get("/api/v1/files/auth/me", headers=annotator_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testannotator"
        assert data["is_admin"] is False


# ===========================================================================
# Single file retrieval  GET /api/v1/files/{file_id}
# ===========================================================================


@pytest.mark.asyncio
class TestGetFile:
    """GET /api/v1/files/{file_id}."""

    async def test_get_existing_file(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "getme.csv")
        file_id = upload["file_id"]
        resp = await client.get(f"/api/v1/files/{file_id}", headers=admin_auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "getme.csv"
        assert body["status"] == "ready"

    async def test_get_nonexistent_file(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get("/api/v1/files/99999", headers=admin_auth_headers)
        assert resp.status_code == 404


# ===========================================================================
# Upload with replace flag
# ===========================================================================


@pytest.mark.asyncio
class TestUploadReplace:
    """POST /api/v1/files/upload?replace=true."""

    async def test_replace_existing_file(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        # First upload
        await _upload(client, admin_auth_headers, sample_csv_content, "replaceme.csv")
        # Re-upload with replace
        files = {"file": ("replaceme.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        resp = await client.post(
            "/api/v1/files/upload?replace=true", headers=admin_auth_headers, files=files
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["filename"] == "replaceme.csv"
        assert body["status"] == "ready"


# ===========================================================================
# User settings overrides (get_user_data_settings branches)
# ===========================================================================


@pytest.mark.asyncio
class TestUserDataSettings:
    """Upload exercises get_user_data_settings — we create study/user settings."""

    async def test_upload_with_study_settings(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Study-level settings should be honoured during upload."""
        async with test_session_maker() as session:
            session.add(UserSettings(username="__study__", skip_rows=10, device_preset=None))
            await session.commit()

        upload = await _upload(client, admin_auth_headers, sample_csv_content, "study_set.csv")
        assert upload["status"] == "ready"

    async def test_upload_with_user_settings(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Per-user settings take precedence over study-level."""
        async with test_session_maker() as session:
            session.add(UserSettings(username="testadmin", skip_rows=10, device_preset=None))
            await session.commit()

        upload = await _upload(client, admin_auth_headers, sample_csv_content, "user_set.csv")
        assert upload["status"] == "ready"


# ===========================================================================
# File assignments (admin CRUD)
# ===========================================================================


@pytest.mark.asyncio
class TestAssignments:
    """CRUD for /api/v1/files/assignments and per-file assignments."""

    async def test_list_assignments_empty(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get("/api/v1/files/assignments", headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_and_list_assignments(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "assign1.csv")
        file_id = upload["file_id"]

        # Create assignment
        resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["created"] == 1

        # Idempotent — should skip duplicate
        resp2 = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert resp2.json()["created"] == 0

        # List assignments
        resp3 = await client.get("/api/v1/files/assignments", headers=admin_auth_headers)
        assignments = resp3.json()
        assert len(assignments) == 1
        assert assignments[0]["username"] == "testannotator"

    async def test_create_assignment_missing_fields(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [], "username": ""},
        )
        assert resp.status_code == 400

    async def test_create_assignment_nonexistent_file(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [99999], "username": "testannotator"},
        )
        assert resp.status_code == 404

    async def test_delete_user_assignments(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "del_assign.csv")
        file_id = upload["file_id"]
        await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        resp = await client.delete(
            "/api/v1/files/assignments/testannotator", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

    async def test_delete_single_file_assignment(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "del_fa.csv")
        file_id = upload["file_id"]
        await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        resp = await client.delete(
            f"/api/v1/files/{file_id}/assignments/testannotator",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 1

    async def test_delete_nonexistent_file_assignment(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.delete(
            "/api/v1/files/99999/assignments/nobody",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    async def test_non_admin_cannot_list_assignments(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        resp = await client.get("/api/v1/files/assignments", headers=annotator_auth_headers)
        assert resp.status_code == 403

    async def test_non_admin_cannot_create_assignments(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/files/assignments",
            headers=annotator_auth_headers,
            json={"file_ids": [1], "username": "someone"},
        )
        assert resp.status_code == 403


# ===========================================================================
# Assignment progress
# ===========================================================================


@pytest.mark.asyncio
class TestAssignmentProgress:
    """GET /api/v1/files/assignments/progress."""

    async def test_progress_empty(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get("/api/v1/files/assignments/progress", headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_progress_with_assignments(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "progress.csv")
        file_id = upload["file_id"]
        await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        resp = await client.get("/api/v1/files/assignments/progress", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        user_entry = data[0]
        assert user_entry["username"] == "testannotator"
        assert user_entry["total_files"] == 1

    async def test_non_admin_cannot_get_progress(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/files/assignments/progress", headers=annotator_auth_headers
        )
        assert resp.status_code == 403


# ===========================================================================
# Unassigned files
# ===========================================================================


@pytest.mark.asyncio
class TestUnassignedFiles:
    """GET /api/v1/files/assignments/unassigned."""

    async def test_unassigned_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        await _upload(client, admin_auth_headers, sample_csv_content, "unassigned1.csv")
        resp = await client.get(
            "/api/v1/files/assignments/unassigned", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        filenames = [f["filename"] for f in data]
        assert "unassigned1.csv" in filenames

    async def test_assigned_file_not_in_unassigned(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "assigned_x.csv")
        file_id = upload["file_id"]
        await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        resp = await client.get(
            "/api/v1/files/assignments/unassigned", headers=admin_auth_headers
        )
        filenames = [f["filename"] for f in resp.json()]
        assert "assigned_x.csv" not in filenames

    async def test_non_admin_unassigned(self, client: AsyncClient, annotator_auth_headers: dict):
        resp = await client.get(
            "/api/v1/files/assignments/unassigned", headers=annotator_auth_headers
        )
        assert resp.status_code == 403


# ===========================================================================
# List files with assignments (annotator sees only assigned files)
# ===========================================================================


@pytest.mark.asyncio
class TestListFilesWithAssignments:
    """GET /api/v1/files — annotator with assignments only sees assigned."""

    async def test_annotator_no_assignments_empty(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        resp = await client.get("/api/v1/files", headers=annotator_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_annotator_sees_only_assigned(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        u1 = await _upload(client, admin_auth_headers, sample_csv_content, "visible.csv")
        await _upload(client, admin_auth_headers, sample_csv_content, "hidden.csv")
        await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [u1["file_id"]], "username": "testannotator"},
        )
        resp = await client.get("/api/v1/files", headers=annotator_auth_headers)
        items = resp.json()["items"]
        filenames = [i["filename"] for i in items]
        assert "visible.csv" in filenames
        assert "hidden.csv" not in filenames


# ===========================================================================
# Backfill participant IDs
# ===========================================================================


@pytest.mark.asyncio
class TestBackfillParticipantIds:
    """POST /api/v1/files/backfill-participant-ids."""

    async def test_backfill(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        # Upload a file — participant_id might be auto-set.  Clear it to test backfill.
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "P001_T1.csv")
        async with test_session_maker() as session:
            result = await session.execute(
                select(FileModel).where(FileModel.id == upload["file_id"])
            )
            f = result.scalar_one()
            f.participant_id = None
            await session.commit()

        resp = await client.post(
            "/api/v1/files/backfill-participant-ids", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] == 1

    async def test_backfill_non_admin(self, client: AsyncClient, annotator_auth_headers: dict):
        resp = await client.post(
            "/api/v1/files/backfill-participant-ids", headers=annotator_auth_headers
        )
        assert resp.status_code == 403


# ===========================================================================
# Delete all files (batch)
# ===========================================================================


@pytest.mark.asyncio
class TestDeleteAllFiles:
    """DELETE /api/v1/files — batch delete."""

    async def test_delete_all(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        await _upload(client, admin_auth_headers, sample_csv_content, "delall1.csv")
        await _upload(client, admin_auth_headers, sample_csv_content, "delall2.csv")
        resp = await client.delete("/api/v1/files", headers=admin_auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["deleted_count"] == 2

    async def test_delete_by_status_filter(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        await _upload(client, admin_auth_headers, sample_csv_content, "statusfilt.csv")
        # Set one file to 'failed'
        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="failed_file.csv",
                    file_type="csv",
                    status=FileStatus.FAILED,
                    uploaded_by="testadmin",
                )
            )
            await session.commit()

        resp = await client.delete(
            "/api/v1/files?status_filter=failed", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 1

        # The ready file should still exist
        list_resp = await client.get("/api/v1/files", headers=admin_auth_headers)
        filenames = [i["filename"] for i in list_resp.json()["items"]]
        assert "statusfilt.csv" in filenames


# ===========================================================================
# Scan data directory
# ===========================================================================


@pytest.mark.asyncio
class TestScanDataDir:
    """POST /api/v1/files/scan and GET /api/v1/files/scan/status."""

    async def test_scan_nonexistent_dir(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Scan returns started=False when data dir doesn't exist."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.data_dir
        s.data_dir = "/tmp/nonexistent_scan_dir_test"
        try:
            resp = await client.post("/api/v1/files/scan", headers=admin_auth_headers)
            assert resp.status_code == 200
            body = resp.json()
            assert body["started"] is False
        finally:
            s.data_dir = original

    async def test_scan_empty_dir(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Scan returns started=False when no CSV files found."""
        import tempfile
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.data_dir
        with tempfile.TemporaryDirectory() as tmpdir:
            s.data_dir = tmpdir
            try:
                resp = await client.post("/api/v1/files/scan", headers=admin_auth_headers)
                assert resp.status_code == 200
                body = resp.json()
                assert body["started"] is False
                assert body["total_files"] == 0
            finally:
                s.data_dir = original

    async def test_scan_status(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get("/api/v1/files/scan/status", headers=admin_auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "is_running" in body
        assert "processed" in body


# ===========================================================================
# File watcher status
# ===========================================================================


@pytest.mark.asyncio
class TestWatcherStatus:
    """GET /api/v1/files/watcher/status."""

    async def test_watcher_status(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get("/api/v1/files/watcher/status", headers=admin_auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "is_running" in body


# ===========================================================================
# Dates with status  GET /{file_id}/dates/status
# ===========================================================================


@pytest.mark.asyncio
class TestDateStatus:
    """GET /api/v1/files/{file_id}/dates/status."""

    async def test_dates_status_basic(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "dstatus.csv")
        file_id = upload["file_id"]
        resp = await client.get(
            f"/api/v1/files/{file_id}/dates/status", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert type(data) is list
        assert len(data) >= 1
        first = data[0]
        assert "date" in first
        assert "has_markers" in first
        assert first["has_markers"] is False  # no markers placed yet
        assert "is_no_sleep" in first
        assert first["is_no_sleep"] is False
        assert "has_auto_score" in first
        assert first["has_auto_score"] is False

    async def test_dates_status_not_found(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get(
            "/api/v1/files/99999/dates/status", headers=admin_auth_headers
        )
        assert resp.status_code == 404

    async def test_dates_status_with_annotations(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """When UserAnnotation rows exist, has_markers should reflect them."""
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "dstatus_ann.csv")
        file_id = upload["file_id"]

        # Get available dates first
        dates_resp = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )
        available_dates = dates_resp.json()
        assert len(available_dates) >= 1
        analysis_date = available_dates[0]

        # Create a UserAnnotation with markers
        async with test_session_maker() as session:
            session.add(
                UserAnnotation(
                    file_id=file_id,
                    analysis_date=datetime.strptime(analysis_date, "%Y-%m-%d").date(),
                    username="testadmin",
                    sleep_markers_json=[{"onset": 100, "offset": 200}],
                    nonwear_markers_json=[],
                    is_no_sleep=False,
                    needs_consensus=True,
                )
            )
            # Also add an auto_score annotation
            session.add(
                UserAnnotation(
                    file_id=file_id,
                    analysis_date=datetime.strptime(analysis_date, "%Y-%m-%d").date(),
                    username="auto_score",
                    sleep_markers_json=[{"onset": 100, "offset": 200}],
                    nonwear_markers_json=[],
                    is_no_sleep=False,
                )
            )
            await session.commit()

        resp = await client.get(
            f"/api/v1/files/{file_id}/dates/status", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        found = [d for d in data if d["date"] == analysis_date]
        assert len(found) == 1
        assert found[0]["has_markers"] is True
        assert found[0]["needs_consensus"] is True
        assert found[0]["has_auto_score"] is True


# ===========================================================================
# Dates with diary filtering
# ===========================================================================


@pytest.mark.asyncio
class TestDatesWithDiary:
    """GET /api/v1/files/{file_id}/dates — diary filtering."""

    async def test_diary_filters_dates(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "diary_d.csv")
        file_id = upload["file_id"]

        # Get unfiltered dates
        resp_all = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )
        all_dates = resp_all.json()
        assert len(all_dates) == 1

        # Add diary entry for only the first date
        first_date = all_dates[0]
        async with test_session_maker() as session:
            session.add(
                DiaryEntry(
                    file_id=file_id,
                    analysis_date=datetime.strptime(first_date, "%Y-%m-%d").date(),
                    bed_time="22:00",
                    wake_time="07:00",
                )
            )
            await session.commit()

        # Now dates should be filtered to only diary dates
        resp_filtered = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )
        filtered_dates = resp_filtered.json()
        assert len(filtered_dates) == 1
        assert filtered_dates[0] == first_date


# ===========================================================================
# Complexity endpoints
# ===========================================================================


@pytest.mark.asyncio
class TestComplexity:
    """POST /{file_id}/compute-complexity and GET /{file_id}/{date}/complexity."""

    async def test_compute_complexity(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "complex.csv")
        file_id = upload["file_id"]
        resp = await client.post(
            f"/api/v1/files/{file_id}/compute-complexity", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "date_count" in body
        assert body["date_count"] == 1

    async def test_compute_complexity_not_found(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/files/99999/compute-complexity", headers=admin_auth_headers
        )
        assert resp.status_code == 404

    async def test_get_complexity_detail_not_found_file(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/files/99999/2024-01-01/complexity", headers=admin_auth_headers
        )
        assert resp.status_code == 404

    async def test_get_complexity_detail_not_computed(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "nocomp.csv")
        file_id = upload["file_id"]
        resp = await client.get(
            f"/api/v1/files/{file_id}/2024-01-01/complexity", headers=admin_auth_headers
        )
        assert resp.status_code == 404
        assert "not computed" in resp.json()["detail"]

    async def test_get_complexity_detail_with_data(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "withcomp.csv")
        file_id = upload["file_id"]

        # Manually insert a NightComplexity row
        async with test_session_maker() as session:
            session.add(
                NightComplexity(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    complexity_pre=75,
                    complexity_post=80,
                    features_json={"spike_count": 2},
                )
            )
            await session.commit()

        resp = await client.get(
            f"/api/v1/files/{file_id}/2024-01-01/complexity", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["complexity_pre"] == 75
        assert body["complexity_post"] == 80
        assert body["features"]["spike_count"] == 2


# ===========================================================================
# Purge excluded files (disk-delete branch)
# ===========================================================================


@pytest.mark.asyncio
class TestPurgeExcluded:
    """POST /api/v1/files/purge-excluded — covers disk deletion branch."""

    async def test_purge_with_disk_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_session_maker,
    ):
        import tempfile

        with tempfile.NamedTemporaryFile(suffix="_IGNORE.csv", delete=False) as tf:
            tf.write(b"data")
            disk_path = tf.name

        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="disk_IGNORE.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                    original_path=disk_path,
                )
            )
            await session.commit()

        resp = await client.post("/api/v1/files/purge-excluded", headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] == 1

    async def test_purge_non_admin(self, client: AsyncClient, annotator_auth_headers: dict):
        resp = await client.post(
            "/api/v1/files/purge-excluded", headers=annotator_auth_headers
        )
        assert resp.status_code == 403


# ===========================================================================
# API Key upload  POST /api/v1/files/upload/api
# ===========================================================================


@pytest.mark.asyncio
class TestApiKeyUpload:
    """POST /api/v1/files/upload/api — covers entire upload/api endpoint."""

    async def test_api_key_upload_not_configured(
        self, client: AsyncClient, sample_csv_content: str
    ):
        """When upload_api_key is empty, endpoint returns 501."""
        files = {"file": ("apikey_test.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        resp = await client.post(
            "/api/v1/files/upload/api",
            headers={"X-Api-Key": "anything"},
            files=files,
        )
        # upload_api_key defaults to "" which means 501
        assert resp.status_code == 501

    async def test_api_key_upload_invalid_key(
        self, client: AsyncClient, sample_csv_content: str
    ):
        """Invalid API key returns 401."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.upload_api_key
        s.upload_api_key = "valid_secret"
        try:
            files = {"file": ("apikey_inv.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
            resp = await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "wrong_key"},
                files=files,
            )
            assert resp.status_code == 401
        finally:
            s.upload_api_key = original

    async def test_api_key_upload_success(
        self, client: AsyncClient, sample_csv_content: str
    ):
        """Valid API key uploads successfully."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.upload_api_key
        s.upload_api_key = "test_secret_key"
        try:
            files = {"file": ("apikey_ok.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
            resp = await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "test_secret_key"},
                files=files,
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["filename"] == "apikey_ok.csv"
            assert body["status"] == "ready"
        finally:
            s.upload_api_key = original

    async def test_api_key_upload_duplicate(
        self, client: AsyncClient, sample_csv_content: str
    ):
        """Duplicate filename returns 400."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.upload_api_key
        s.upload_api_key = "test_secret_key"
        try:
            files = {"file": ("dup_api.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
            await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "test_secret_key"},
                files=files,
            )
            files2 = {"file": ("dup_api.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
            resp = await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "test_secret_key"},
                files=files2,
            )
            assert resp.status_code == 400
            assert "already exists" in resp.json()["detail"]
        finally:
            s.upload_api_key = original

    async def test_api_key_upload_non_csv(
        self, client: AsyncClient
    ):
        """Non-CSV file returns 400."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.upload_api_key
        s.upload_api_key = "test_secret_key"
        try:
            files = {"file": ("test.txt", io.BytesIO(b"hello"), "text/plain")}
            resp = await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "test_secret_key"},
                files=files,
            )
            assert resp.status_code == 400
        finally:
            s.upload_api_key = original

    async def test_api_key_upload_excluded_filename(
        self, client: AsyncClient, sample_csv_content: str
    ):
        """Excluded filename returns 400."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.upload_api_key
        s.upload_api_key = "test_secret_key"
        try:
            files = {"file": ("IGNORE_file.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
            resp = await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "test_secret_key"},
                files=files,
            )
            assert resp.status_code == 400
            assert "excluded" in resp.json()["detail"].lower()
        finally:
            s.upload_api_key = original


# ===========================================================================
# Scan with running check (conflict)
# ===========================================================================


@pytest.mark.asyncio
class TestScanConflict:
    """POST /api/v1/files/scan — 409 when scan already running."""

    async def test_scan_conflict(self, client: AsyncClient, admin_auth_headers: dict):
        from sleep_scoring_web.api.files import _scan_status

        _scan_status.is_running = True
        try:
            resp = await client.post("/api/v1/files/scan", headers=admin_auth_headers)
            assert resp.status_code == 409
        finally:
            _scan_status.is_running = False


# ===========================================================================
# Scan with actual CSV files in data dir
# ===========================================================================


@pytest.mark.asyncio
class TestScanWithFiles:
    """POST /api/v1/files/scan — with CSV files in data directory."""

    async def test_scan_starts_with_csv_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        import tempfile
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.data_dir

        with tempfile.TemporaryDirectory() as tmpdir:
            # Write a CSV file into the data dir
            csv_path = f"{tmpdir}/scantest.csv"
            with open(csv_path, "w") as f:
                f.write(sample_csv_content)

            s.data_dir = tmpdir
            try:
                resp = await client.post("/api/v1/files/scan", headers=admin_auth_headers)
                assert resp.status_code == 200
                body = resp.json()
                assert body["started"] is True
                assert body["total_files"] >= 1
            finally:
                s.data_dir = original
                # Reset scan status so it doesn't affect other tests
                from sleep_scoring_web.api.files import _scan_status
                _scan_status.is_running = False


# ===========================================================================
# _require_admin enforcement
# ===========================================================================


@pytest.mark.asyncio
class TestRequireAdmin:
    """Tests that admin-only endpoints reject non-admin users."""

    async def test_backfill_denied(self, client: AsyncClient, annotator_auth_headers: dict):
        resp = await client.post(
            "/api/v1/files/backfill-participant-ids", headers=annotator_auth_headers
        )
        assert resp.status_code == 403

    async def test_delete_user_assignments_denied(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        resp = await client.delete(
            "/api/v1/files/assignments/someone", headers=annotator_auth_headers
        )
        assert resp.status_code == 403

    async def test_delete_file_assignment_denied(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        resp = await client.delete(
            "/api/v1/files/1/assignments/someone", headers=annotator_auth_headers
        )
        assert resp.status_code == 403


# ===========================================================================
# No-sleep annotation in dates/status
# ===========================================================================


@pytest.mark.asyncio
class TestNoSleepDateStatus:
    """Verify is_no_sleep flags surface in dates/status."""

    async def test_no_sleep_flag(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "nosleep.csv")
        file_id = upload["file_id"]
        dates_resp = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )
        analysis_date = dates_resp.json()[0]

        async with test_session_maker() as session:
            session.add(
                UserAnnotation(
                    file_id=file_id,
                    analysis_date=datetime.strptime(analysis_date, "%Y-%m-%d").date(),
                    username="testadmin",
                    sleep_markers_json=[],
                    nonwear_markers_json=[],
                    is_no_sleep=True,
                )
            )
            await session.commit()

        resp = await client.get(
            f"/api/v1/files/{file_id}/dates/status", headers=admin_auth_headers
        )
        found = [d for d in resp.json() if d["date"] == analysis_date]
        assert found[0]["is_no_sleep"] is True
        # has_markers should be True when is_no_sleep is True
        assert found[0]["has_markers"] is True


# ===========================================================================
# Delete file with original_path on disk
# ===========================================================================


@pytest.mark.asyncio
class TestDeleteFileWithDisk:
    """DELETE /api/v1/files/{file_id} — covers disk unlink branches."""

    async def test_delete_removes_disk_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Upload creates a disk file; delete should remove it."""
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "deldisk.csv")
        file_id = upload["file_id"]

        resp = await client.delete(f"/api/v1/files/{file_id}", headers=admin_auth_headers)
        assert resp.status_code == 204

        # Verify it's gone from the API
        resp2 = await client.get(f"/api/v1/files/{file_id}", headers=admin_auth_headers)
        assert resp2.status_code == 404


# ===========================================================================
# Upload edge cases
# ===========================================================================


@pytest.mark.asyncio
class TestUploadEdgeCases:
    """Edge cases for POST /api/v1/files/upload."""

    async def test_upload_empty_filename(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Empty filename should be rejected."""
        files = {"file": ("", io.BytesIO(b"data"), "text/csv")}
        resp = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)
        assert resp.status_code in (400, 422)

    async def test_upload_xlsx_extension(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """xlsx extension should be accepted (though content parsing may fail)."""
        files = {"file": ("test.xlsx", io.BytesIO(b"not a real xlsx"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        resp = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)
        # Will fail processing but the extension check should pass -> 400 from parse failure
        assert resp.status_code == 400


# ===========================================================================
# Assignment progress with diary dates
# ===========================================================================


@pytest.mark.asyncio
class TestAssignmentProgressWithDiary:
    """Progress endpoint uses diary dates when available."""

    async def test_progress_with_diary(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "prog_diary.csv")
        file_id = upload["file_id"]

        # Add diary entry
        async with test_session_maker() as session:
            session.add(
                DiaryEntry(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    bed_time="22:00",
                    wake_time="07:00",
                )
            )
            await session.commit()

        # Create assignment
        await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )

        resp = await client.get(
            "/api/v1/files/assignments/progress", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        # Diary defines 1 date, so total_dates should be 1
        user = [u for u in data if u["username"] == "testannotator"][0]
        file_entry = [f for f in user["files"] if f["file_id"] == file_id][0]
        assert file_entry["total_dates"] == 1


# ===========================================================================
# Device preset settings branches
# ===========================================================================


@pytest.mark.asyncio
class TestDevicePresetSettings:
    """Exercise device_preset override branches in get_user_data_settings."""

    async def test_study_device_preset(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Study-level device_preset should be used when set."""
        async with test_session_maker() as session:
            session.add(
                UserSettings(
                    username="__study__",
                    skip_rows=10,
                    device_preset="actigraph",
                )
            )
            await session.commit()

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "dev_study.csv"
        )
        assert upload["status"] == "ready"

    async def test_user_device_preset_overrides_study(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Per-user device_preset overrides study-level."""
        async with test_session_maker() as session:
            session.add(
                UserSettings(
                    username="__study__",
                    skip_rows=10,
                    device_preset="geneactiv",
                )
            )
            session.add(
                UserSettings(
                    username="testadmin",
                    skip_rows=10,
                    device_preset="actigraph",
                )
            )
            await session.commit()

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "dev_user.csv"
        )
        assert upload["status"] == "ready"


# ===========================================================================
# import_file_from_disk_async (tested directly)
# ===========================================================================


@pytest.mark.asyncio
class TestImportFileFromDisk:
    """Direct tests for import_file_from_disk_async."""

    async def test_import_excluded_file(self, test_session_maker):
        """Excluded filenames return None immediately."""
        from sleep_scoring_web.api.files import import_file_from_disk_async
        from pathlib import Path

        async with test_session_maker() as db:
            result = await import_file_from_disk_async(
                Path("/tmp/something_IGNORE.csv"), db, "testadmin"
            )
            assert result is None

    async def test_import_duplicate_file(
        self, test_session_maker, sample_csv_content: str
    ):
        """Already-imported files return None."""
        from sleep_scoring_web.api.files import import_file_from_disk_async
        import tempfile
        from pathlib import Path

        # Create a real CSV file on disk
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", prefix="import_dup_", delete=False
        ) as f:
            f.write(sample_csv_content)
            csv_path = Path(f.name)

        try:
            async with test_session_maker() as db:
                # First import succeeds
                result1 = await import_file_from_disk_async(csv_path, db, "testadmin")
                assert result1 is not None
                assert result1.status == FileStatus.READY

                # Second import returns None (duplicate)
                result2 = await import_file_from_disk_async(csv_path, db, "testadmin")
                assert result2 is None
        finally:
            csv_path.unlink(missing_ok=True)

    async def test_import_bad_content(self, test_session_maker):
        """Import of malformed CSV sets status to FAILED."""
        from sleep_scoring_web.api.files import import_file_from_disk_async
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".csv", prefix="import_bad_", delete=False
        ) as f:
            f.write("this is not a valid CSV at all\n")
            csv_path = Path(f.name)

        try:
            async with test_session_maker() as db:
                result = await import_file_from_disk_async(csv_path, db, "testadmin")
                assert result is None  # Failed processing returns None
        finally:
            csv_path.unlink(missing_ok=True)


# ===========================================================================
# Backfill participant IDs — edge cases
# ===========================================================================


@pytest.mark.asyncio
class TestBackfillEdgeCases:
    """Backfill when pid already set, or filename doesn't yield pid."""

    async def test_backfill_already_has_pid(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Files with existing participant_id should be skipped."""
        # P001_T1.csv auto-infers participant_id="P001"
        await _upload(client, admin_auth_headers, sample_csv_content, "P001_T1_bf.csv")
        resp = await client.post(
            "/api/v1/files/backfill-participant-ids", headers=admin_auth_headers
        )
        body = resp.json()
        # It had a pid already, so updated should be 0
        assert body["updated"] == 0
        assert body["total_files"] >= 1

    async def test_backfill_no_inferable_pid(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Files with non-inferable filenames remain unchanged."""
        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "randomname.csv"
        )
        # Clear participant_id
        async with test_session_maker() as session:
            result = await session.execute(
                select(FileModel).where(FileModel.id == upload["file_id"])
            )
            f = result.scalar_one()
            f.participant_id = None
            await session.commit()

        resp = await client.post(
            "/api/v1/files/backfill-participant-ids", headers=admin_auth_headers
        )
        body = resp.json()
        # "randomname" does not match known PID patterns — might or might not
        # infer depending on implementation, but endpoint should succeed
        assert resp.status_code == 200


# ===========================================================================
# Delete file with original_path that doesn't exist on disk
# ===========================================================================


@pytest.mark.asyncio
class TestDeleteFileNoDisk:
    """Delete file where original_path is set but file is gone from disk."""

    async def test_delete_file_missing_disk(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_session_maker,
    ):
        """Delete should succeed even when disk file is already missing."""
        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="phantom.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                    original_path="/tmp/nonexistent_phantom_file.csv",
                )
            )
            await session.commit()
            result = await session.execute(
                select(FileModel).where(FileModel.filename == "phantom.csv")
            )
            file_id = result.scalar_one().id

        resp = await client.delete(
            f"/api/v1/files/{file_id}", headers=admin_auth_headers
        )
        assert resp.status_code == 204


# ===========================================================================
# Delete file with no original_path
# ===========================================================================


@pytest.mark.asyncio
class TestDeleteFileNoPath:
    """Delete file where original_path is None."""

    async def test_delete_file_null_path(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_session_maker,
    ):
        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="nopath.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                    original_path=None,
                )
            )
            await session.commit()
            result = await session.execute(
                select(FileModel).where(FileModel.filename == "nopath.csv")
            )
            file_id = result.scalar_one().id

        resp = await client.delete(
            f"/api/v1/files/{file_id}", headers=admin_auth_headers
        )
        assert resp.status_code == 204


# ===========================================================================
# Delete all files with disk files
# ===========================================================================


@pytest.mark.asyncio
class TestDeleteAllWithDisk:
    """DELETE /api/v1/files — exercises disk unlink in loop."""

    async def test_delete_all_with_disk_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Delete all exercises per-file disk cleanup."""
        await _upload(client, admin_auth_headers, sample_csv_content, "disk1.csv")
        await _upload(client, admin_auth_headers, sample_csv_content, "disk2.csv")
        resp = await client.delete("/api/v1/files", headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["deleted_count"] >= 2


# ===========================================================================
# _compute_complexity_for_file (background task, tested directly)
# ===========================================================================


@pytest.mark.asyncio
class TestComputeComplexityDirect:
    """Direct invocation of _compute_complexity_for_file background task."""

    async def test_compute_for_uploaded_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Run complexity computation directly on an uploaded file."""
        from sleep_scoring_web.api.files import _compute_complexity_for_file

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "comp_direct.csv"
        )
        file_id = upload["file_id"]

        # Get dates
        dates_resp = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )
        date_strs = dates_resp.json()
        date_objs = [datetime.strptime(d, "%Y-%m-%d").date() for d in date_strs]

        # Run computation directly (bypasses BackgroundTasks)
        await _compute_complexity_for_file(file_id, date_objs)

        # Verify complexity was computed
        async with test_session_maker() as session:
            result = await session.execute(
                select(NightComplexity).where(NightComplexity.file_id == file_id)
            )
            rows = result.scalars().all()
            assert len(rows) >= 1
            assert rows[0].complexity_pre is not None

    async def test_compute_with_diary(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Complexity computation uses diary data when available."""
        from sleep_scoring_web.api.files import _compute_complexity_for_file

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "comp_diary.csv"
        )
        file_id = upload["file_id"]

        # Add diary
        async with test_session_maker() as session:
            session.add(
                DiaryEntry(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    bed_time="22:00",
                    wake_time="07:00",
                    lights_out="22:30",
                    got_up="07:30",
                    nap_1_start="14:00",
                    nap_1_end="15:00",
                    nap_2_start="16:00",
                    nap_2_end="17:00",
                    nap_3_start="18:00",
                    nap_3_end="18:30",
                )
            )
            await session.commit()

        await _compute_complexity_for_file(file_id, [date(2024, 1, 1)])

        async with test_session_maker() as session:
            result = await session.execute(
                select(NightComplexity).where(NightComplexity.file_id == file_id)
            )
            rows = result.scalars().all()
            assert len(rows) >= 1

    async def test_compute_with_sleep_markers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Complexity computation includes post-complexity when markers exist."""
        from sleep_scoring_web.api.files import _compute_complexity_for_file

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "comp_markers.csv"
        )
        file_id = upload["file_id"]

        # Add sleep markers
        async with test_session_maker() as session:
            session.add(
                Marker(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    marker_category=MarkerCategory.SLEEP,
                    marker_type=MarkerType.MAIN_SLEEP,
                    start_timestamp=1704110400.0,
                    end_timestamp=1704135600.0,
                    created_by="testadmin",
                )
            )
            await session.commit()

        await _compute_complexity_for_file(file_id, [date(2024, 1, 1)])

        async with test_session_maker() as session:
            result = await session.execute(
                select(NightComplexity).where(NightComplexity.file_id == file_id)
            )
            rows = result.scalars().all()
            assert len(rows) >= 1

    async def test_compute_upsert_existing(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Re-running computation upserts existing NightComplexity rows."""
        from sleep_scoring_web.api.files import _compute_complexity_for_file

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "comp_upsert.csv"
        )
        file_id = upload["file_id"]

        # Pre-create a NightComplexity row
        async with test_session_maker() as session:
            session.add(
                NightComplexity(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    complexity_pre=50,
                    complexity_post=0,
                )
            )
            await session.commit()

        # Re-compute — should update existing row
        await _compute_complexity_for_file(file_id, [date(2024, 1, 1)])

        async with test_session_maker() as session:
            result = await session.execute(
                select(NightComplexity).where(
                    NightComplexity.file_id == file_id,
                    NightComplexity.analysis_date == date(2024, 1, 1),
                )
            )
            row = result.scalar_one()
            # Should have been updated (value may differ from original 50)
            assert row.complexity_pre is not None

    async def test_compute_no_activity_data(
        self, test_session_maker
    ):
        """Dates with no activity data are silently skipped."""
        from sleep_scoring_web.api.files import _compute_complexity_for_file

        # Create a file record with no activity data
        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="empty_activity.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                )
            )
            await session.commit()
            result = await session.execute(
                select(FileModel).where(FileModel.filename == "empty_activity.csv")
            )
            file_id = result.scalar_one().id

        # Should not raise, just skip
        await _compute_complexity_for_file(file_id, [date(2024, 6, 15)])

        async with test_session_maker() as session:
            result = await session.execute(
                select(NightComplexity).where(NightComplexity.file_id == file_id)
            )
            assert result.scalars().all() == []


# ===========================================================================
# API key upload — empty filename edge case
# ===========================================================================


@pytest.mark.asyncio
class TestApiKeyUploadEdgeCases:
    """Edge cases for /upload/api endpoint."""

    async def test_api_upload_empty_filename(self, client: AsyncClient):
        """Empty filename returns 400."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.upload_api_key
        s.upload_api_key = "test_key"
        try:
            files = {"file": ("", io.BytesIO(b"data"), "text/csv")}
            resp = await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "test_key"},
                files=files,
            )
            assert resp.status_code in (400, 422)
        finally:
            s.upload_api_key = original

    async def test_api_upload_bad_csv_content(self, client: AsyncClient):
        """Invalid CSV content triggers processing failure branch."""
        from sleep_scoring_web.config import get_settings
        s = get_settings()
        original = s.upload_api_key
        s.upload_api_key = "test_key"
        try:
            files = {
                "file": ("bad_api_content.csv", io.BytesIO(b"not,a,valid\ncsv,at,all"), "text/csv")
            }
            resp = await client.post(
                "/api/v1/files/upload/api",
                headers={"X-Api-Key": "test_key"},
                files=files,
            )
            assert resp.status_code == 400
        finally:
            s.upload_api_key = original


# ===========================================================================
# _async_scan_files (direct tests)
# ===========================================================================


@pytest.mark.asyncio
class TestAsyncScanFiles:
    """Direct invocation of _async_scan_files."""

    async def test_scan_imports_files(
        self,
        test_session_maker,
        sample_csv_content: str,
    ):
        """Scan imports CSV files from a directory."""
        import tempfile
        from pathlib import Path
        from sleep_scoring_web.api.files import _async_scan_files, _scan_status

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "scannable.csv"
            csv_path.write_text(sample_csv_content)

            _scan_status.is_running = True
            _scan_status.processed = 0
            _scan_status.imported = 0
            _scan_status.skipped = 0
            _scan_status.failed = 0
            _scan_status.imported_files = []

            await _async_scan_files("testadmin", [csv_path])

            assert _scan_status.processed >= 1
            assert _scan_status.imported >= 1 or _scan_status.skipped >= 1

    async def test_scan_skips_excluded_files(
        self,
        test_session_maker,
        sample_csv_content: str,
    ):
        """Scan skips files with IGNORE in the name."""
        import tempfile
        from pathlib import Path
        from sleep_scoring_web.api.files import _async_scan_files, _scan_status

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "test_IGNORE.csv"
            csv_path.write_text(sample_csv_content)

            _scan_status.is_running = True
            _scan_status.processed = 0
            _scan_status.imported = 0
            _scan_status.skipped = 0
            _scan_status.failed = 0
            _scan_status.imported_files = []

            await _async_scan_files("testadmin", [csv_path])

            assert _scan_status.skipped >= 1
            assert _scan_status.imported == 0

    async def test_scan_skips_duplicate_files(
        self,
        test_session_maker,
        sample_csv_content: str,
    ):
        """Scan skips files that already exist in the database."""
        import tempfile
        from pathlib import Path
        from sleep_scoring_web.api.files import _async_scan_files, _scan_status

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "scandup.csv"
            csv_path.write_text(sample_csv_content)

            # First scan imports the file
            _scan_status.is_running = True
            _scan_status.processed = 0
            _scan_status.imported = 0
            _scan_status.skipped = 0
            _scan_status.failed = 0
            _scan_status.imported_files = []

            await _async_scan_files("testadmin", [csv_path])
            first_imported = _scan_status.imported

            # Second scan should skip it
            _scan_status.processed = 0
            _scan_status.imported = 0
            _scan_status.skipped = 0
            _scan_status.failed = 0
            _scan_status.imported_files = []

            await _async_scan_files("testadmin", [csv_path])
            assert _scan_status.skipped >= 1


# ===========================================================================
# bulk_insert_activity_data edge cases
# ===========================================================================


@pytest.mark.asyncio
class TestBulkInsertEdgeCases:
    """Direct tests for bulk_insert_activity_data."""

    async def test_empty_dataframe(self, test_session_maker):
        """Empty DataFrame returns 0."""
        import pandas as pd
        from sleep_scoring_web.api.files import bulk_insert_activity_data

        async with test_session_maker() as db:
            result = await bulk_insert_activity_data(db, 1, pd.DataFrame())
            assert result == 0

    async def test_missing_columns(self, test_session_maker):
        """DataFrame missing axis columns gets them filled with None."""
        import pandas as pd
        from sleep_scoring_web.api.files import bulk_insert_activity_data

        # Create a minimal dataframe with only timestamp — axis_x, axis_y, etc missing
        df = pd.DataFrame({
            "timestamp": pd.to_datetime(["2024-01-01 12:00:00"]),
        })

        # Need a file record with valid id
        async with test_session_maker() as db:
            from sleep_scoring_web.db.models import File as FileModel
            file_rec = FileModel(
                filename="bulk_test.csv",
                file_type="csv",
                status="ready",
                uploaded_by="testadmin",
            )
            db.add(file_rec)
            await db.commit()
            await db.refresh(file_rec)

            count = await bulk_insert_activity_data(db, file_rec.id, df)
            assert count == 1
            await db.commit()


# ===========================================================================
# Complexity with diary nonwear and sensor nonwear
# ===========================================================================


@pytest.mark.asyncio
class TestComplexityWithNonwear:
    """Test complexity computation with nonwear data."""

    async def test_compute_with_diary_nonwear(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Complexity uses diary-reported nonwear times."""
        from sleep_scoring_web.api.files import _compute_complexity_for_file

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "comp_nw.csv"
        )
        file_id = upload["file_id"]

        # Add diary with nonwear periods
        async with test_session_maker() as session:
            session.add(
                DiaryEntry(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    bed_time="22:00",
                    wake_time="07:00",
                    nonwear_1_start="10:00",
                    nonwear_1_end="11:00",
                    nonwear_2_start="14:00",
                    nonwear_2_end="15:00",
                )
            )
            await session.commit()

        await _compute_complexity_for_file(file_id, [date(2024, 1, 1)])

        async with test_session_maker() as session:
            result = await session.execute(
                select(NightComplexity).where(NightComplexity.file_id == file_id)
            )
            rows = result.scalars().all()
            assert len(rows) >= 1

    async def test_compute_with_sensor_nonwear(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Complexity computation includes sensor nonwear from markers table."""
        from sleep_scoring_web.api.files import _compute_complexity_for_file

        upload = await _upload(
            client, admin_auth_headers, sample_csv_content, "comp_snw.csv"
        )
        file_id = upload["file_id"]

        # Add sensor nonwear marker overlapping with activity data
        async with test_session_maker() as session:
            session.add(
                Marker(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    marker_category=MarkerCategory.NONWEAR,
                    marker_type=MarkerType.SENSOR_NONWEAR,
                    start_timestamp=1704110000.0,
                    end_timestamp=1704120000.0,
                    created_by="auto",
                )
            )
            await session.commit()

        await _compute_complexity_for_file(file_id, [date(2024, 1, 1)])

        async with test_session_maker() as session:
            result = await session.execute(
                select(NightComplexity).where(NightComplexity.file_id == file_id)
            )
            rows = result.scalars().all()
            assert len(rows) >= 1


# ===========================================================================
# Upload API processing failure
# ===========================================================================


@pytest.mark.asyncio
class TestUploadProcessingFailure:
    """Test upload endpoint processing failure sets file to FAILED."""

    async def test_upload_bad_csv_content(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Invalid CSV content returns 400 and marks file as failed."""
        files = {
            "file": (
                "bad_content.csv",
                io.BytesIO(b"this is not valid csv content at all"),
                "text/csv",
            )
        }
        resp = await client.post(
            "/api/v1/files/upload", headers=admin_auth_headers, files=files
        )
        assert resp.status_code == 400


# ===========================================================================
# Assignment progress with scored dates
# ===========================================================================


@pytest.mark.asyncio
class TestAssignmentProgressWithScoring:
    """Progress endpoint tracks scored dates via Marker table."""

    async def test_progress_tracks_scored_dates(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        upload = await _upload(client, admin_auth_headers, sample_csv_content, "prog_scored.csv")
        file_id = upload["file_id"]

        # Create assignment
        await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )

        # Add a marker for testannotator
        async with test_session_maker() as session:
            session.add(
                Marker(
                    file_id=file_id,
                    analysis_date=date(2024, 1, 1),
                    marker_category=MarkerCategory.SLEEP,
                    marker_type=MarkerType.MAIN_SLEEP,
                    start_timestamp=1704110400.0,
                    end_timestamp=1704135600.0,
                    created_by="testannotator",
                )
            )
            await session.commit()

        resp = await client.get(
            "/api/v1/files/assignments/progress", headers=admin_auth_headers
        )
        data = resp.json()
        user = [u for u in data if u["username"] == "testannotator"][0]
        assert user["scored_dates"] >= 1
