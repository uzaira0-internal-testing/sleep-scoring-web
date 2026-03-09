"""
HTTP integration tests for the diary API endpoints.

Tests CRUD operations for sleep diary entries via /api/v1/diary.
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
class TestGetDiaryEntry:
    """Tests for GET /api/v1/diary/{file_id}/{date}."""

    async def test_no_entry_returns_null(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return null/empty when no diary entry exists."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_get.csv")

        response = await client.get(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )

        # Either 200 with null or 404
        assert response.status_code in (200, 404)


@pytest.mark.asyncio
class TestSaveDiaryEntry:
    """Tests for PUT /api/v1/diary/{file_id}/{date}."""

    async def test_create_diary_entry(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should create a diary entry."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_put.csv")

        response = await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={
                "bed_time": "22:30",
                "wake_time": "07:00",
                "sleep_quality": 4,
                "notes": "Slept well",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bed_time"] == "22:30"
        assert data["wake_time"] == "07:00"
        assert data["sleep_quality"] == 4

    async def test_create_and_retrieve_diary_entry(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should be able to retrieve a saved diary entry."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_roundtrip.csv")

        # Create entry
        await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={"bed_time": "23:00", "wake_time": "06:30"},
        )

        # Retrieve it
        response = await client.get(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bed_time"] == "23:00"
        assert data["wake_time"] == "06:30"

    async def test_update_diary_entry(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should update an existing diary entry."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_update.csv")

        # Create first
        await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={"bed_time": "22:00"},
        )

        # Update
        response = await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={"bed_time": "23:00", "notes": "Updated"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bed_time"] == "23:00"
        assert data["notes"] == "Updated"


@pytest.mark.asyncio
class TestDeleteDiaryEntry:
    """Tests for DELETE /api/v1/diary/{file_id}/{date}."""

    async def test_delete_diary_entry(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should delete a diary entry."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_del.csv")

        # Create first
        await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={"bed_time": "22:00"},
        )

        # Delete
        response = await client.delete(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )

        assert response.status_code in (200, 204)

    async def test_delete_nonexistent_entry(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should handle deletion of non-existent entry."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_del_nf.csv")

        response = await client.delete(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )

        # Should not error (idempotent)
        assert response.status_code in (200, 204, 404)


@pytest.mark.asyncio
class TestDiaryUpload:
    """Tests for POST /api/v1/diary/{file_id}/upload."""

    async def test_upload_diary_csv(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should import diary entries from CSV."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_upload.csv")

        diary_csv = "date,bed_time,wake_time,sleep_quality\n2024-01-01,22:30,07:00,4\n"
        files = {"file": ("diary.csv", io.BytesIO(diary_csv.encode()), "text/csv")}
        response = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entries_imported"] >= 1
