"""
HTTP integration tests for the files API endpoints.

Tests file upload, listing, dates, and deletion via /api/v1/files.
"""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from sleep_scoring_web.db.models import File as FileModel


@pytest.mark.asyncio
class TestFileUpload:
    """Tests for POST /api/v1/files/upload."""

    async def test_upload_csv(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should upload a CSV file and return file info."""
        files = {"file": ("test_upload.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        response = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "test_upload.csv"
        assert data["status"] == "ready"
        assert data["file_id"] > 0

    async def test_upload_rejects_non_csv(self, client: AsyncClient, admin_auth_headers: dict):
        """Should reject files that are not CSV/Excel."""
        files = {"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")}
        response = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)

        assert response.status_code == 400
        assert "CSV" in response.json()["detail"] or "supported" in response.json()["detail"]

    async def test_upload_rejects_path_traversal(self, client: AsyncClient, admin_auth_headers: dict):
        """Path traversal filenames are sanitized (directory components stripped)."""
        files = {"file": ("../../etc/crontab.csv", io.BytesIO(b"data"), "text/csv")}
        response = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)

        # Server strips directory components via PurePosixPath.name → "crontab.csv"
        # Then rejects the file because the content is invalid (not a real CSV)
        assert response.status_code == 400

    async def test_upload_duplicate_filename_rejected(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should reject upload of duplicate filename."""
        files = {"file": ("duplicate.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)

        # Upload same filename again
        files = {"file": ("duplicate.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        response = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    async def test_upload_rejects_excluded_filename_tokens(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Should reject files with IGNORE or ISSUE in filename."""
        files_ignore = {"file": ("night_IGNORE.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        resp_ignore = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files_ignore)
        assert resp_ignore.status_code == 400
        assert "excluded from scoring" in resp_ignore.json()["detail"].lower()

        files_issue = {"file": ("night_issue_01.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        resp_issue = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files_issue)
        assert resp_issue.status_code == 400
        assert "excluded from scoring" in resp_issue.json()["detail"].lower()


@pytest.mark.asyncio
class TestFileList:
    """Tests for GET /api/v1/files."""

    async def test_list_empty(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return empty list when no files uploaded."""
        response = await client.get("/api/v1/files", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_after_upload(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should list uploaded files."""
        files = {"file": ("listed.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)

        response = await client.get("/api/v1/files", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        filenames = [item["filename"] for item in data["items"]]
        assert "listed.csv" in filenames

    async def test_list_hides_excluded_and_purge_deletes_them(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Excluded files should not be counted/listed and can be purged."""
        files = {"file": ("normal.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        upload_resp = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)
        assert upload_resp.status_code == 200

        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="legacy_IGNORE_file.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                )
            )
            session.add(
                FileModel(
                    filename="legacy_issue_file.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                )
            )
            await session.commit()

        list_resp = await client.get("/api/v1/files", headers=admin_auth_headers)
        assert list_resp.status_code == 200
        data = list_resp.json()
        filenames = [item["filename"] for item in data["items"]]
        assert "normal.csv" in filenames
        assert "legacy_IGNORE_file.csv" not in filenames
        assert "legacy_issue_file.csv" not in filenames
        assert data["total"] == 1

        purge_resp = await client.post("/api/v1/files/purge-excluded", headers=admin_auth_headers)
        assert purge_resp.status_code == 200
        purge_data = purge_resp.json()
        assert purge_data["deleted_count"] == 2

        async with test_session_maker() as session:
            remaining = await session.execute(select(FileModel.filename))
            names = set(remaining.scalars().all())
        assert "normal.csv" in names
        assert "legacy_IGNORE_file.csv" not in names
        assert "legacy_issue_file.csv" not in names


@pytest.mark.asyncio
class TestFileDates:
    """Tests for GET /api/v1/files/{file_id}/dates."""

    async def test_get_dates_for_file(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return available dates for a file."""
        files = {"file": ("dates_test.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        upload_resp = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)
        file_id = upload_resp.json()["file_id"]

        response = await client.get(f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers)

        assert response.status_code == 200
        dates = response.json()
        assert isinstance(dates, list)
        # Sample data starts at 2024-01-01
        assert len(dates) >= 1

    async def test_get_dates_not_found(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return 404 for non-existent file."""
        response = await client.get("/api/v1/files/99999/dates", headers=admin_auth_headers)

        assert response.status_code == 404


@pytest.mark.asyncio
class TestFileDelete:
    """Tests for DELETE /api/v1/files/{file_id}."""

    async def test_delete_file(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should delete an uploaded file."""
        files = {"file": ("to_delete.csv", io.BytesIO(sample_csv_content.encode()), "text/csv")}
        upload_resp = await client.post("/api/v1/files/upload", headers=admin_auth_headers, files=files)
        file_id = upload_resp.json()["file_id"]

        response = await client.delete(f"/api/v1/files/{file_id}", headers=admin_auth_headers)

        assert response.status_code == 204

    async def test_delete_not_found(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return 404 for non-existent file."""
        response = await client.delete("/api/v1/files/99999", headers=admin_auth_headers)

        assert response.status_code == 404
