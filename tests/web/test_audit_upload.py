"""
HTTP integration tests for audit logging and upload processing.

Tests audit event batch logging, idempotency, retrieval, and summary
via /api/v1/audit, plus file upload lifecycle via /api/v1/files.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

from tests.web.conftest import upload_and_get_date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _upload_file(
    client: AsyncClient,
    auth_headers: dict[str, str],
    csv_content: str,
    filename: str = "test_data.csv",
):
    """Upload a CSV file and return the raw response.

    Unlike ``upload_and_get_date`` from conftest, this returns the full
    httpx Response so callers can inspect status codes for error-path tests.
    """
    files = {"file": (filename, io.BytesIO(csv_content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", files=files, headers=auth_headers)
    return resp


def _make_audit_batch(
    file_id: int,
    analysis_date: str = "2024-01-01",
    session_id: str = "test-session-123",
    events: list[dict] | None = None,
) -> dict:
    """Build an AuditBatchRequest body."""
    if events is None:
        events = [
            {
                "action": "marker_placed",
                "client_timestamp": 1704110400.0,
                "session_id": session_id,
                "sequence": 0,
                "payload": {"marker_type": "MAIN_SLEEP"},
            },
            {
                "action": "marker_moved",
                "client_timestamp": 1704110401.0,
                "session_id": session_id,
                "sequence": 1,
                "payload": {"marker_type": "MAIN_SLEEP", "offset": 5},
            },
        ]
    return {
        "file_id": file_id,
        "analysis_date": analysis_date,
        "events": events,
    }


# ---------------------------------------------------------------------------
# Audit logging tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuditBatchSave:
    """Tests for POST /api/v1/audit/log — batch event logging."""

    async def test_batch_save_logs_events(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """POST audit events should return 200 with logged count > 0."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "audit_save.csv"
        )

        body = _make_audit_batch(file_id)
        resp = await client.post(
            "/api/v1/audit/log", json=body, headers=admin_auth_headers
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["logged"] > 0
        assert data["logged"] == len(body["events"])

    async def test_batch_save_idempotent(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """POST the same events again should return logged=0 (no duplicates)."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "audit_idem.csv"
        )

        body = _make_audit_batch(file_id, session_id="idem-session-001")

        # First call — events are stored
        resp1 = await client.post(
            "/api/v1/audit/log", json=body, headers=admin_auth_headers
        )
        assert resp1.status_code == 200
        assert resp1.json()["logged"] == len(body["events"])

        # Second call — identical payload, nothing new to log
        resp2 = await client.post(
            "/api/v1/audit/log", json=body, headers=admin_auth_headers
        )
        assert resp2.status_code == 200
        assert resp2.json()["logged"] == 0


@pytest.mark.asyncio
class TestAuditRetrieval:
    """Tests for GET /api/v1/audit/{file_id}/{date}."""

    async def test_get_audit_log_returns_saved_events(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Saved audit events should be retrievable via GET."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "audit_get.csv"
        )

        body = _make_audit_batch(file_id, session_id="retrieve-session")
        await client.post(
            "/api/v1/audit/log", json=body, headers=admin_auth_headers
        )

        resp = await client.get(
            f"/api/v1/audit/{file_id}/2024-01-01", headers=admin_auth_headers
        )

        assert resp.status_code == 200
        entries = resp.json()
        assert len(entries) == len(body["events"])
        actions = [e["action"] for e in entries]
        assert "marker_placed" in actions
        assert "marker_moved" in actions
        # Verify each entry has the expected fields
        for entry in entries:
            assert "id" in entry
            assert "session_id" in entry
            assert "sequence" in entry
            assert "username" in entry

    async def test_query_by_file_and_date_filters_correctly(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """GET audit log should only return events for the requested file/date."""
        # Upload two files
        file_id_a, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "audit_filter_a.csv"
        )
        file_id_b, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "audit_filter_b.csv"
        )

        # Log events to file A on 2024-01-01
        body_a = _make_audit_batch(
            file_id_a,
            analysis_date="2024-01-01",
            session_id="filter-sess-a",
        )
        await client.post(
            "/api/v1/audit/log", json=body_a, headers=admin_auth_headers
        )

        # Log events to file B on 2024-01-02
        body_b = _make_audit_batch(
            file_id_b,
            analysis_date="2024-01-02",
            session_id="filter-sess-b",
        )
        await client.post(
            "/api/v1/audit/log", json=body_b, headers=admin_auth_headers
        )

        # Query file A, date 2024-01-01 — should get only A's events
        resp_a = await client.get(
            f"/api/v1/audit/{file_id_a}/2024-01-01", headers=admin_auth_headers
        )
        assert resp_a.status_code == 200
        entries_a = resp_a.json()
        assert len(entries_a) == len(body_a["events"])
        for entry in entries_a:
            assert entry["session_id"] == "filter-sess-a"

        # Query file B, date 2024-01-01 — should be empty (B's events are on 01-02)
        resp_b_wrong = await client.get(
            f"/api/v1/audit/{file_id_b}/2024-01-01", headers=admin_auth_headers
        )
        assert resp_b_wrong.status_code == 200
        assert len(resp_b_wrong.json()) == 0

        # Query file B, date 2024-01-02 — should get B's events
        resp_b = await client.get(
            f"/api/v1/audit/{file_id_b}/2024-01-02", headers=admin_auth_headers
        )
        assert resp_b.status_code == 200
        entries_b = resp_b.json()
        assert len(entries_b) == len(body_b["events"])
        for entry in entries_b:
            assert entry["session_id"] == "filter-sess-b"


@pytest.mark.asyncio
class TestAuditSummary:
    """Tests for GET /api/v1/audit/{file_id}/{date}/summary."""

    async def test_summary_returns_aggregate_stats(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Summary should report total_events, users, and sessions."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "audit_summary.csv"
        )

        body = _make_audit_batch(file_id, session_id="summary-sess")
        await client.post(
            "/api/v1/audit/log", json=body, headers=admin_auth_headers
        )

        resp = await client.get(
            f"/api/v1/audit/{file_id}/2024-01-01/summary",
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        summary = resp.json()
        assert summary["total_events"] == len(body["events"])
        assert len(summary["users"]) >= 1
        assert summary["sessions"] >= 1
        assert summary["first_event"] is not None
        assert summary["last_event"] is not None

    async def test_summary_empty_when_no_events(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Summary for a file/date with no events should return zeroes."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "audit_empty_sum.csv"
        )

        resp = await client.get(
            f"/api/v1/audit/{file_id}/2024-06-15/summary",
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        summary = resp.json()
        assert summary["total_events"] == 0
        assert summary["users"] == []
        assert summary["sessions"] == 0


# ---------------------------------------------------------------------------
# Upload processing tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUploadProcessing:
    """Tests for file upload lifecycle via /api/v1/files."""

    async def test_valid_csv_upload_reaches_ready(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Uploading a valid CSV should result in status 'ready'."""
        resp = await _upload_file(
            client, admin_auth_headers, sample_csv_content, "upload_ready.csv"
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["file_id"] > 0
        assert data["filename"] == "upload_ready.csv"

    async def test_empty_csv_upload_fails(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ):
        """Uploading an empty CSV should fail or produce a failed status."""
        resp = await _upload_file(
            client, admin_auth_headers, csv_content="", filename="empty.csv"
        )

        # Either a 400 error or a 200 with status="failed" is acceptable
        if resp.status_code == 200:
            assert resp.json()["status"] == "failed"
        else:
            assert resp.status_code in (400, 422)

    async def test_duplicate_filename_rejected(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Uploading the same filename twice should be rejected."""
        resp1 = await _upload_file(
            client, admin_auth_headers, sample_csv_content, "dup_upload.csv"
        )
        assert resp1.status_code == 200

        resp2 = await _upload_file(
            client, admin_auth_headers, sample_csv_content, "dup_upload.csv"
        )
        assert resp2.status_code == 400
        assert "already exists" in resp2.json()["detail"]

    async def test_available_dates_after_upload(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """After uploading a valid CSV, its dates should be available."""
        upload_resp = await _upload_file(
            client, admin_auth_headers, sample_csv_content, "dates_check.csv"
        )
        assert upload_resp.status_code == 200
        file_id = upload_resp.json()["file_id"]

        resp = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )

        assert resp.status_code == 200
        dates = resp.json()
        assert isinstance(dates, list)
        assert len(dates) >= 1

    async def test_delete_file_cascade(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Deleting a file should cascade and clean up associated data."""
        # Upload a file
        upload_resp = await _upload_file(
            client, admin_auth_headers, sample_csv_content, "cascade_del.csv"
        )
        assert upload_resp.status_code == 200
        file_id = upload_resp.json()["file_id"]

        # Log some audit events against this file
        body = _make_audit_batch(file_id, session_id="cascade-sess")
        audit_resp = await client.post(
            "/api/v1/audit/log", json=body, headers=admin_auth_headers
        )
        assert audit_resp.status_code == 200
        assert audit_resp.json()["logged"] > 0

        # Delete the file
        del_resp = await client.delete(
            f"/api/v1/files/{file_id}", headers=admin_auth_headers
        )
        assert del_resp.status_code == 204

        # Verify file is gone (dates endpoint returns 404)
        dates_resp = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )
        assert dates_resp.status_code == 404

        # Verify audit events were cascade-deleted
        audit_get_resp = await client.get(
            f"/api/v1/audit/{file_id}/2024-01-01", headers=admin_auth_headers
        )
        assert audit_get_resp.status_code == 200
        assert len(audit_get_resp.json()) == 0
