"""
HTTP integration tests for the activity API endpoints.

Tests GET /api/v1/activity/{file_id}/{date} and /score endpoints.
"""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient


async def _upload_file(client: AsyncClient, headers: dict, content: str, filename: str = "activity_test.csv") -> int:
    """Upload a CSV file and return its file_id."""
    files = {"file": (filename, io.BytesIO(content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", headers=headers, files=files)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["file_id"]


@pytest.mark.asyncio
class TestGetActivityData:
    """Tests for GET /api/v1/activity/{file_id}/{analysis_date}."""

    async def test_returns_activity_data(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return columnar activity data for a valid file and date."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content)

        # Get dates first to know which date has data
        dates_resp = await client.get(f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers)
        dates = dates_resp.json()
        assert len(dates) >= 1

        response = await client.get(f"/api/v1/activity/{file_id}/{dates[0]}", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "timestamps" in data["data"]
        assert "axis_y" in data["data"]
        assert "vector_magnitude" in data["data"]
        assert len(data["data"]["timestamps"]) > 0

    async def test_file_not_found(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return 404 for non-existent file."""
        response = await client.get("/api/v1/activity/99999/2024-01-01", headers=admin_auth_headers)

        assert response.status_code == 404


@pytest.mark.asyncio
class TestGetActivityDataWithScore:
    """Tests for GET /api/v1/activity/{file_id}/{analysis_date}/score."""

    async def test_returns_scored_data(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return activity data with algorithm scores."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "score_test.csv")

        dates_resp = await client.get(f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers)
        dates = dates_resp.json()
        assert len(dates) >= 1

        response = await client.get(
            f"/api/v1/activity/{file_id}/{dates[0]}/score",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "algorithm_results" in data
        assert "nonwear_results" in data

    async def test_custom_view_hours(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should respect view_hours parameter."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "view_hours_test.csv")

        dates_resp = await client.get(f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers)
        dates = dates_resp.json()

        response = await client.get(
            f"/api/v1/activity/{file_id}/{dates[0]}/score?view_hours=48",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
