"""
Tests to increase API endpoint coverage.

Covers: settings, export, audit, activity, access, deps modules.
Uses conftest fixtures from tests/web/conftest.py.
"""

from __future__ import annotations

import io
import uuid
from datetime import date, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from sleep_scoring_web.db.models import (
    AuditLogEntry,
    File as FileModel,
    FileAssignment,
    Marker,
    UserAnnotation,
    UserSettings,
)
from sleep_scoring_web.main import app
from sleep_scoring_web.schemas.enums import (
    FileStatus,
    MarkerCategory,
    MarkerType,
    VerificationStatus,
)


# =============================================================================
# Helpers
# =============================================================================


async def _create_test_file(session_maker, *, filename="test_file.csv", status=FileStatus.READY):
    """Insert a bare File row and return its id."""
    async with session_maker() as db:
        f = FileModel(filename=filename, status=status, uploaded_by="testadmin")
        db.add(f)
        await db.commit()
        await db.refresh(f)
        return f.id


async def _assign_file(session_maker, file_id: int, username: str):
    """Assign a file to a user."""
    async with session_maker() as db:
        db.add(FileAssignment(file_id=file_id, username=username, assigned_by="testadmin"))
        await db.commit()


# =============================================================================
# 1. Settings API  (api/settings.py)
# =============================================================================


class TestSettingsAPI:
    """Tests for GET/PUT/DELETE settings endpoints."""

    @pytest.mark.asyncio
    async def test_get_settings_returns_defaults_when_none(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """GET /settings with no saved settings returns defaults."""
        resp = await client.get("/api/v1/settings", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["night_start_hour"] == "21:00"
        assert data["night_end_hour"] == "09:00"
        assert data["device_preset"] == "actigraph"
        assert data["epoch_length_seconds"] == 60

    @pytest.mark.asyncio
    async def test_put_settings_creates_new_record(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """PUT /settings creates a settings record if none exists."""
        resp = await client.put(
            "/api/v1/settings",
            json={"view_mode_hours": 48, "device_preset": "geneactiv"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["view_mode_hours"] == 48
        assert data["device_preset"] == "geneactiv"

    @pytest.mark.asyncio
    async def test_put_settings_updates_existing_record(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """PUT /settings twice — second call updates existing row."""
        await client.put(
            "/api/v1/settings",
            json={"view_mode_hours": 48},
            headers=admin_auth_headers,
        )
        resp = await client.put(
            "/api/v1/settings",
            json={"view_mode_hours": 24},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["view_mode_hours"] == 24

    @pytest.mark.asyncio
    async def test_put_settings_merges_extra_settings(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """PUT /settings with extra_settings merges with existing extras."""
        await client.put(
            "/api/v1/settings",
            json={"extra_settings": {"key1": "val1"}},
            headers=admin_auth_headers,
        )
        resp = await client.put(
            "/api/v1/settings",
            json={"extra_settings": {"key2": "val2"}},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        extras = resp.json()["extra_settings"]
        assert extras["key1"] == "val1"
        assert extras["key2"] == "val2"

    @pytest.mark.asyncio
    async def test_delete_settings_resets(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """DELETE /settings removes user settings, subsequent GET returns defaults."""
        await client.put(
            "/api/v1/settings",
            json={"view_mode_hours": 48},
            headers=admin_auth_headers,
        )
        resp = await client.delete("/api/v1/settings", headers=admin_auth_headers)
        assert resp.status_code == 204

        resp = await client.get("/api/v1/settings", headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["view_mode_hours"] == 24  # default

    @pytest.mark.asyncio
    async def test_study_settings_get_defaults(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """GET /settings/study returns defaults when no study settings exist."""
        resp = await client.get("/api/v1/settings/study", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["night_start_hour"] == "21:00"

    @pytest.mark.asyncio
    async def test_study_settings_put_admin_only(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        """PUT /settings/study by non-admin returns 403."""
        resp = await client.put(
            "/api/v1/settings/study",
            json={"night_start_hour": "22:00"},
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_study_settings_put_creates_and_updates(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """PUT /settings/study creates then updates study settings."""
        resp = await client.put(
            "/api/v1/settings/study",
            json={"night_start_hour": "22:00"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["night_start_hour"] == "22:00"

        # Update existing
        resp2 = await client.put(
            "/api/v1/settings/study",
            json={"night_end_hour": "08:00"},
            headers=admin_auth_headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["night_start_hour"] == "22:00"
        assert resp2.json()["night_end_hour"] == "08:00"

    @pytest.mark.asyncio
    async def test_study_settings_delete_admin_only(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        """DELETE /settings/study by non-admin returns 403."""
        resp = await client.delete(
            "/api/v1/settings/study",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_study_settings_delete(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """DELETE /settings/study resets to defaults."""
        await client.put(
            "/api/v1/settings/study",
            json={"night_start_hour": "23:00"},
            headers=admin_auth_headers,
        )
        resp = await client.delete("/api/v1/settings/study", headers=admin_auth_headers)
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_get_settings_study_overrides_user(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """GET /settings merges study-wide + user settings (study wins for study fields)."""
        await client.put(
            "/api/v1/settings/study",
            json={"night_start_hour": "22:00"},
            headers=admin_auth_headers,
        )
        await client.put(
            "/api/v1/settings",
            json={"night_start_hour": "20:00", "view_mode_hours": 48},
            headers=admin_auth_headers,
        )
        resp = await client.get("/api/v1/settings", headers=admin_auth_headers)
        data = resp.json()
        # Study-wide field: study setting wins
        assert data["night_start_hour"] == "22:00"
        # Per-user field: user setting wins
        assert data["view_mode_hours"] == 48


# =============================================================================
# 2. Export API (api/export.py)
# =============================================================================


class TestExportAPI:
    """Tests for export endpoints."""

    @pytest.mark.asyncio
    async def test_get_columns(self, client: AsyncClient, admin_auth_headers: dict):
        """GET /export/columns returns column definitions."""
        resp = await client.get("/api/v1/export/columns", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "columns" in data
        assert "categories" in data
        assert len(data["columns"]) > 0
        # Check a known column exists
        names = [c["name"] for c in data["columns"]]
        assert "Filename" in names
        assert "Study Date" in names

    @pytest.mark.asyncio
    async def test_csv_export_empty_file_ids(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """POST /export/csv with empty file_ids still returns a response."""
        resp = await client.post(
            "/api/v1/export/csv",
            json={"file_ids": []},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False or data["row_count"] == 0

    @pytest.mark.asyncio
    async def test_csv_download_no_data(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """POST /export/csv/download with valid file but no markers returns CSV."""
        file_id = await _create_test_file(test_session_maker)
        resp = await client.post(
            "/api/v1/export/csv/download",
            json={"file_ids": [file_id]},
            headers=admin_auth_headers,
        )
        # Should return CSV (possibly empty or with a warning)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_quick_export_invalid_ids(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """GET /export/csv/quick with invalid file_ids returns error CSV."""
        resp = await client.get(
            "/api/v1/export/csv/quick?file_ids=abc",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert "Error" in resp.text or "error" in resp.text.lower()

    @pytest.mark.asyncio
    async def test_quick_export_no_visible_ids(
        self, client: AsyncClient, annotator_auth_headers: dict
    ):
        """GET /export/csv/quick by annotator without assignments returns error."""
        resp = await client.get(
            "/api/v1/export/csv/quick?file_ids=9999",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 200
        # Should be an error CSV because the annotator has no access
        assert "Error" in resp.text or "error" in resp.text.lower() or "No file" in resp.text

    @pytest.mark.asyncio
    async def test_nonwear_download_no_nonwear(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """POST /export/csv/download/nonwear with no nonwear markers returns error."""
        file_id = await _create_test_file(test_session_maker, filename="nonwear_test.csv")
        resp = await client.post(
            "/api/v1/export/csv/download/nonwear",
            json={"file_ids": [file_id]},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        # Should report no nonwear markers
        text = resp.text
        assert "nonwear" in text.lower() or "error" in text.lower() or "No" in text


# =============================================================================
# 3. Audit API (api/audit.py)
# =============================================================================


class TestAuditAPI:
    """Tests for audit log endpoints."""

    @pytest.mark.asyncio
    async def test_log_and_retrieve_audit(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """POST /audit/log + GET /audit/{file_id}/{date} round-trip."""
        file_id = await _create_test_file(test_session_maker, filename="audit_test.csv")
        session_id = str(uuid.uuid4())
        resp = await client.post(
            "/api/v1/audit/log",
            json={
                "file_id": file_id,
                "analysis_date": "2024-01-01",
                "events": [
                    {
                        "action": "marker_placed",
                        "client_timestamp": 1704067200.0,
                        "session_id": session_id,
                        "sequence": 0,
                        "payload": {"x": 1},
                    },
                ],
            },
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["logged"] == 1

        # Retrieve
        resp2 = await client.get(
            f"/api/v1/audit/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )
        assert resp2.status_code == 200
        entries = resp2.json()
        assert len(entries) == 1
        assert entries[0]["action"] == "marker_placed"

    @pytest.mark.asyncio
    async def test_audit_idempotent_dedup(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """Re-sending the same audit events should not duplicate them."""
        file_id = await _create_test_file(test_session_maker, filename="audit_dedup.csv")
        session_id = str(uuid.uuid4())
        payload = {
            "file_id": file_id,
            "analysis_date": "2024-01-02",
            "events": [
                {
                    "action": "click",
                    "client_timestamp": 1704153600.0,
                    "session_id": session_id,
                    "sequence": 0,
                },
            ],
        }
        resp1 = await client.post("/api/v1/audit/log", json=payload, headers=admin_auth_headers)
        assert resp1.json()["logged"] == 1

        resp2 = await client.post("/api/v1/audit/log", json=payload, headers=admin_auth_headers)
        assert resp2.json()["logged"] == 0

    @pytest.mark.asyncio
    async def test_audit_summary(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """GET /audit/{file_id}/{date}/summary returns summary stats."""
        file_id = await _create_test_file(test_session_maker, filename="audit_summary.csv")
        session_id = str(uuid.uuid4())
        await client.post(
            "/api/v1/audit/log",
            json={
                "file_id": file_id,
                "analysis_date": "2024-01-03",
                "events": [
                    {"action": "click", "client_timestamp": 1704240000.0, "session_id": session_id, "sequence": 0},
                    {"action": "drag", "client_timestamp": 1704240060.0, "session_id": session_id, "sequence": 1},
                ],
            },
            headers=admin_auth_headers,
        )
        resp = await client.get(
            f"/api/v1/audit/{file_id}/2024-01-03/summary",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 2
        assert "testadmin" in data["users"]
        assert data["sessions"] == 1
        assert data["first_event"] is not None
        assert data["last_event"] is not None

    @pytest.mark.asyncio
    async def test_audit_summary_empty(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """GET /audit/{file_id}/{date}/summary with no events returns zeros."""
        file_id = await _create_test_file(test_session_maker, filename="audit_empty.csv")
        resp = await client.get(
            f"/api/v1/audit/{file_id}/2024-06-01/summary",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_events"] == 0
        assert data["users"] == []
        assert data["sessions"] == 0

    @pytest.mark.asyncio
    async def test_audit_filter_by_username(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """GET /audit/{file_id}/{date}?username=X filters correctly."""
        file_id = await _create_test_file(test_session_maker, filename="audit_filter.csv")
        session_id = str(uuid.uuid4())
        await client.post(
            "/api/v1/audit/log",
            json={
                "file_id": file_id,
                "analysis_date": "2024-02-01",
                "events": [
                    {"action": "click", "client_timestamp": 1706745600.0, "session_id": session_id, "sequence": 0},
                ],
            },
            headers=admin_auth_headers,
        )
        # Filter by existing user
        resp = await client.get(
            f"/api/v1/audit/{file_id}/2024-02-01?username=testadmin",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        # Filter by non-existing user
        resp2 = await client.get(
            f"/api/v1/audit/{file_id}/2024-02-01?username=nobody",
            headers=admin_auth_headers,
        )
        assert resp2.status_code == 200
        assert len(resp2.json()) == 0


# =============================================================================
# 4. Activity API edge cases (api/activity.py)
# =============================================================================


class TestActivityAPI:
    """Tests for activity score endpoint edge cases."""

    @pytest.mark.asyncio
    async def test_score_invalid_algorithm(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker, sample_csv_content: str
    ):
        """GET /activity/{file_id}/{date}/score?algorithm=bad returns 400."""
        from tests.web.conftest import upload_and_get_date

        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )
        resp = await client.get(
            f"/api/v1/activity/{file_id}/{analysis_date}/score?algorithm=nonexistent",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_score_with_fields_filter(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """GET /activity/{file_id}/{date}/score?fields=axis_x strips other axes."""
        from tests.web.conftest import upload_and_get_date

        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )
        resp = await client.get(
            f"/api/v1/activity/{file_id}/{analysis_date}/score?fields=axis_x",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # axis_z should be stripped (empty list)
        assert data["data"]["axis_z"] == []
        # axis_x should be present
        assert len(data["data"]["axis_x"]) > 0


# =============================================================================
# 5. Access control helpers (api/access.py)
# =============================================================================


class TestAccessControl:
    """Tests for access control helper functions via API."""

    @pytest.mark.asyncio
    async def test_non_admin_cannot_see_unassigned_file(
        self, client: AsyncClient, annotator_auth_headers: dict, test_session_maker
    ):
        """Annotator without assignment cannot access a file's activity data."""
        file_id = await _create_test_file(test_session_maker, filename="access_test.csv")
        resp = await client.get(
            f"/api/v1/activity/{file_id}/2024-01-01",
            headers=annotator_auth_headers,
        )
        # Should be 404 (file not found = access denied)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_admin_can_see_any_file(
        self, client: AsyncClient, admin_auth_headers: dict, test_session_maker
    ):
        """Admin can access any file's data."""
        file_id = await _create_test_file(test_session_maker, filename="admin_access.csv")
        # Admin should at least get a response (even if no data) — not a 404 for access
        resp = await client.get(
            f"/api/v1/activity/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )
        # File exists, admin has access — should get 200 (empty data)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_assigned_user_can_access_file(
        self, client: AsyncClient, annotator_auth_headers: dict, test_session_maker
    ):
        """Annotator with assignment can access the file."""
        file_id = await _create_test_file(test_session_maker, filename="assigned_access.csv")
        await _assign_file(test_session_maker, file_id, "testannotator")
        resp = await client.get(
            f"/api/v1/activity/{file_id}/2024-01-01",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 200


# =============================================================================
# 6. Deps module (api/deps.py)
# =============================================================================


class TestDeps:
    """Tests for dependency injection functions."""

    @pytest.mark.asyncio
    async def test_missing_site_password_returns_401(self, client: AsyncClient):
        """Request without site password header should fail auth."""
        resp = await client.get(
            "/api/v1/settings",
            headers={"X-Username": "testadmin"},
        )
        # Should be rejected — no site password
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_wrong_site_password_returns_401(self, client: AsyncClient):
        """Request with wrong site password should fail auth."""
        resp = await client.get(
            "/api/v1/settings",
            headers={"X-Username": "testadmin", "X-Site-Password": "wrongpassword"},
        )
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_verify_api_key_not_configured(self, client: AsyncClient):
        """API key endpoint returns 501 when key not configured."""
        # The upload/api endpoint requires X-Api-Key
        resp = await client.post(
            "/api/v1/files/upload/api",
            headers={"X-Api-Key": "somekey"},
            files={"file": ("test.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")},
        )
        # Should fail with 501 (key not configured) or 401
        assert resp.status_code in (401, 501)
