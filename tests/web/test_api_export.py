"""
HTTP integration tests for the export API endpoints.

Tests CSV export via /api/v1/export.
"""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient


async def _upload_file(client: AsyncClient, headers: dict, content: str, filename: str) -> int:
    """Upload a CSV file and return its file_id."""
    files = {"file": (filename, io.BytesIO(content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", headers=headers, files=files)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["file_id"]


@pytest.mark.asyncio
class TestExportColumns:
    """Tests for GET /api/v1/export/columns."""

    async def test_returns_available_columns(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return all available export columns."""
        response = await client.get("/api/v1/export/columns", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert "columns" in data
        assert len(data["columns"]) > 0
        # Each column should have name, category, description
        col = data["columns"][0]
        assert "name" in col
        assert "category" in col

    async def test_columns_include_expected_fields(self, client: AsyncClient, admin_auth_headers: dict):
        """Should include key columns like Filename, Total Sleep Time, etc."""
        response = await client.get("/api/v1/export/columns", headers=admin_auth_headers)

        data = response.json()
        column_names = [c["name"] for c in data["columns"]]
        assert "Filename" in column_names
        assert "Analysis Date" in column_names


@pytest.mark.asyncio
class TestExportCsv:
    """Tests for POST /api/v1/export/csv."""

    async def test_export_csv_empty(self, client: AsyncClient, admin_auth_headers: dict):
        """Should handle export with no matching data."""
        response = await client.post(
            "/api/v1/export/csv",
            headers=admin_auth_headers,
            json={
                "file_ids": [99999],
            },
        )

        # Should succeed with empty result or a reasonable error
        assert response.status_code in (200, 404)


@pytest.mark.asyncio
class TestQuickExport:
    """Tests for GET /api/v1/export/csv/quick."""

    async def test_quick_export_with_file(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return CSV data for a valid file."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "export_quick.csv")

        response = await client.get(
            f"/api/v1/export/csv/quick?file_ids={file_id}",
            headers=admin_auth_headers,
        )

        # May return 200 with CSV or empty result if no markers
        assert response.status_code == 200

    async def test_quick_export_invalid_file(self, client: AsyncClient, admin_auth_headers: dict):
        """Should handle non-existent file gracefully."""
        response = await client.get(
            "/api/v1/export/csv/quick?file_ids=99999",
            headers=admin_auth_headers,
        )

        # Should return 200 with empty CSV rather than error
        assert response.status_code == 200
