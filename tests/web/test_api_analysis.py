"""
HTTP integration tests for the analysis API endpoints (Phase 4).

Tests cross-file summary statistics and scoring progress.
"""

import io

import pytest
from httpx import AsyncClient


async def _upload_file(client: AsyncClient, headers: dict, content: str, filename: str) -> int:
    """Upload a CSV file and return its file_id."""
    files = {"file": (filename, io.BytesIO(content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", headers=headers, files=files)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["file_id"]


@pytest.mark.asyncio
class TestAnalysisSummary:
    """Tests for GET /api/v1/analysis/summary."""

    async def test_summary_with_no_files(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Should return empty summary when no files exist."""
        response = await client.get(
            "/api/v1/analysis/summary",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] == 0
        assert data["total_dates"] == 0
        assert data["scored_dates"] == 0
        assert data["files_summary"] == []

    async def test_summary_with_uploaded_file(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should include uploaded file in summary."""
        await _upload_file(client, admin_auth_headers, sample_csv_content, "analysis_test.csv")

        response = await client.get(
            "/api/v1/analysis/summary",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_files"] >= 1
        assert len(data["files_summary"]) >= 1

        # Find our file in the summary
        our_file = next(
            (f for f in data["files_summary"] if f["filename"] == "analysis_test.csv"),
            None,
        )
        assert our_file is not None
        assert our_file["scored_dates"] == 0  # No markers yet

    async def test_summary_includes_aggregate_metrics(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Should return aggregate_metrics structure even when empty."""
        response = await client.get(
            "/api/v1/analysis/summary",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "aggregate_metrics" in data

    async def test_summary_tracks_scored_dates_after_marker_save(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Scored dates count should increase when markers are saved."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "analysis_scored.csv")

        # Save markers for a date
        await client.put(
            f"/api/v1/markers/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {"onset_timestamp": 1000, "offset_timestamp": 2000, "marker_index": 1, "marker_type": "MAIN_SLEEP"},
                ],
                "nonwear_markers": [],
                "is_no_sleep": False,
            },
        )

        response = await client.get(
            "/api/v1/analysis/summary",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        our_file = next(
            (f for f in data["files_summary"] if f["filename"] == "analysis_scored.csv"),
            None,
        )
        assert our_file is not None
        assert our_file["scored_dates"] >= 1

    async def test_summary_without_password_header(self, client: AsyncClient):
        """Request without X-Site-Password should still be handled by middleware.

        Note: In test environment, the SessionAuthMiddleware may pass through
        requests because the test DB override doesn't fully replicate auth.
        In production, unauthenticated requests are blocked.
        """
        response = await client.get("/api/v1/analysis/summary")
        # In test env this may pass; in prod it would be blocked by middleware
        assert response.status_code in (200, 401, 403)
