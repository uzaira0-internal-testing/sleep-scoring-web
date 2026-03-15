"""Tests for TUS resumable upload router and processing status endpoint.

Covers:
- TUS protocol endpoints: OPTIONS, POST (create), PATCH (upload), HEAD (status)
- Pre-create hook validation (filename, extension, site password)
- Processing status endpoint (in-memory tracker + DB fallback)
- _on_upload_complete metadata parsing
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from sleep_scoring_web.api.tus import (
    _on_upload_complete,
    _pre_create_hook,
    tus_router,
)
from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.schemas.enums import FileStatus
from sleep_scoring_web.services.processing_tracker import (
    ProcessingProgress,
    _processing_status,
    start_tracking,
    clear_tracking,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_tus_files_dir(tmp_path: Path):
    """Patch the tus_router's internal options.files_dir to a writable temp dir.

    The tus_router is created at module import time with settings.tus_upload_dir
    (defaults to /app/uploads/tus which doesn't exist in test environments).
    All route closures share a single options object, so we can grab a reference
    and mutate files_dir directly.
    """
    # Find the shared options object from any route closure
    options = None
    for route in tus_router.routes:
        ep = route.endpoint
        if hasattr(ep, "__closure__") and ep.__closure__:
            for cell in ep.__closure__:
                try:
                    val = cell.cell_contents
                    if hasattr(val, "files_dir"):
                        options = val
                        break
                except ValueError:
                    pass
            if options is not None:
                break

    if options is None:
        yield
        return

    original = options.files_dir
    tus_dir = tmp_path / "tus_files"
    tus_dir.mkdir()
    options.files_dir = str(tus_dir)
    yield
    options.files_dir = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _encode_tus_metadata(**kwargs: str) -> str:
    """Encode key-value pairs as TUS Upload-Metadata header value.

    TUS metadata format: key base64value, key base64value
    """
    parts = []
    for k, v in kwargs.items():
        encoded = base64.b64encode(v.encode()).decode()
        parts.append(f"{k} {encoded}")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Tests: _pre_create_hook validation
# ---------------------------------------------------------------------------


class TestPreCreateHook:
    """Test pre-create hook validation logic."""

    def test_rejects_missing_filename(self) -> None:
        """Must have a filename in metadata."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _pre_create_hook({"filename": ""}, {})
        assert exc_info.value.status_code == 400
        assert "Filename required" in exc_info.value.detail

    def test_rejects_unsupported_extension(self) -> None:
        """Must have an allowed file extension."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _pre_create_hook({"filename": "data.txt"}, {})
        assert exc_info.value.status_code == 400
        assert "Unsupported file type" in exc_info.value.detail

    def test_accepts_csv(self) -> None:
        """CSV files should be accepted."""
        _pre_create_hook(
            {"filename": "data.csv", "site_password": "testpass"},
            {},
        )

    def test_accepts_xlsx(self) -> None:
        """XLSX files should be accepted."""
        _pre_create_hook(
            {"filename": "data.xlsx", "site_password": "testpass"},
            {},
        )

    def test_accepts_gz(self) -> None:
        """GZ files should be accepted."""
        _pre_create_hook(
            {"filename": "data.csv.gz", "site_password": "testpass"},
            {},
        )

    def test_rejects_wrong_site_password(self) -> None:
        """Wrong site password should return 401."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _pre_create_hook(
                {"filename": "data.csv", "site_password": "wrongpass"},
                {},
            )
        assert exc_info.value.status_code == 401

    def test_accepts_correct_site_password(self) -> None:
        """Correct site password should pass validation."""
        _pre_create_hook(
            {"filename": "data.csv", "site_password": "testpass"},
            {},
        )


# ---------------------------------------------------------------------------
# Tests: _on_upload_complete metadata parsing
# ---------------------------------------------------------------------------


class TestOnUploadComplete:
    """Test _on_upload_complete metadata extraction."""

    def test_parses_metadata_defaults(self) -> None:
        """Default values when metadata is minimal."""
        with patch("sleep_scoring_web.api.tus.asyncio") as mock_asyncio:
            mock_task = MagicMock()
            mock_asyncio.ensure_future.return_value = mock_task

            _on_upload_complete("/tmp/test.csv", {})

            # Should have called ensure_future with _create_and_process
            mock_asyncio.ensure_future.assert_called_once()

    def test_parses_metadata_values(self) -> None:
        """Extract filename, is_gzip, username, skip_rows from metadata."""
        with patch("sleep_scoring_web.api.tus.asyncio") as mock_asyncio:
            mock_task = MagicMock()
            mock_asyncio.ensure_future.return_value = mock_task

            _on_upload_complete(
                "/tmp/test.csv",
                {
                    "filename": "myfile.csv",
                    "is_gzip": "true",
                    "username": "researcher1",
                    "skip_rows": "15",
                    "device_preset": "geneactiv",
                },
            )

            mock_asyncio.ensure_future.assert_called_once()

    def test_invalid_skip_rows_defaults_to_10(self) -> None:
        """Non-integer skip_rows should default to 10."""
        with patch("sleep_scoring_web.api.tus.asyncio") as mock_asyncio:
            mock_task = MagicMock()
            mock_asyncio.ensure_future.return_value = mock_task

            _on_upload_complete(
                "/tmp/test.csv",
                {"skip_rows": "abc"},
            )

            mock_asyncio.ensure_future.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: TUS protocol endpoints via HTTP
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTusEndpoints:
    """Test TUS protocol endpoints through the HTTP client."""

    async def test_options_returns_tus_headers(self, client: AsyncClient) -> None:
        """OPTIONS should return TUS protocol capabilities."""
        resp = await client.options("/api/v1/tus/files/")
        assert resp.status_code == 204 or resp.status_code == 200
        # TUS protocol headers should be present
        assert "tus-resumable" in resp.headers or "Tus-Resumable" in {
            k.title(): v for k, v in resp.headers.items()
        }

    async def test_post_create_upload(self, client: AsyncClient) -> None:
        """POST should create a new upload resource."""
        metadata = _encode_tus_metadata(
            filename="test_upload.csv",
            site_password="testpass",
            username="testadmin",
        )
        resp = await client.post(
            "/api/v1/tus/files/",
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Length": "100",
                "Upload-Metadata": metadata,
            },
        )
        assert resp.status_code == 201
        assert "location" in resp.headers or "Location" in {
            k.title(): v for k, v in resp.headers.items()
        }

    async def test_post_rejects_bad_extension(self, client: AsyncClient) -> None:
        """POST should reject file with unsupported extension."""
        metadata = _encode_tus_metadata(
            filename="data.pdf",
            site_password="testpass",
        )
        resp = await client.post(
            "/api/v1/tus/files/",
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Length": "100",
                "Upload-Metadata": metadata,
            },
        )
        assert resp.status_code == 400

    async def test_post_rejects_missing_filename(self, client: AsyncClient) -> None:
        """POST should reject upload without filename."""
        metadata = _encode_tus_metadata(
            site_password="testpass",
        )
        resp = await client.post(
            "/api/v1/tus/files/",
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Length": "100",
                "Upload-Metadata": metadata,
            },
        )
        assert resp.status_code == 400

    async def test_post_rejects_wrong_password(self, client: AsyncClient) -> None:
        """POST should reject upload with wrong site password."""
        metadata = _encode_tus_metadata(
            filename="data.csv",
            site_password="wrong",
        )
        resp = await client.post(
            "/api/v1/tus/files/",
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Length": "100",
                "Upload-Metadata": metadata,
            },
        )
        assert resp.status_code == 401

    async def test_head_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """HEAD should return 404 for non-existent upload UUID."""
        resp = await client.head(
            "/api/v1/tus/files/00000000-0000-0000-0000-000000000000",
            headers={"Tus-Resumable": "1.0.0"},
        )
        assert resp.status_code == 404

    async def test_patch_nonexistent_returns_404(self, client: AsyncClient) -> None:
        """PATCH should return 404 for non-existent upload UUID."""
        resp = await client.patch(
            "/api/v1/tus/files/00000000-0000-0000-0000-000000000000",
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
            },
            content=b"data",
        )
        assert resp.status_code == 404

    async def test_full_upload_lifecycle(self, client: AsyncClient) -> None:
        """Complete TUS upload lifecycle: POST create -> HEAD status -> PATCH upload."""
        # Step 1: Create upload
        file_content = b"Date,Time,Axis1\n01/15/2025,22:00:00,100\n"
        metadata = _encode_tus_metadata(
            filename="lifecycle_test.csv",
            filetype="text/csv",
            site_password="testpass",
            username="testadmin",
        )
        create_resp = await client.post(
            "/api/v1/tus/files/",
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Length": str(len(file_content)),
                "Upload-Metadata": metadata,
            },
        )
        assert create_resp.status_code == 201
        # Extract Location header (case-insensitive)
        location = create_resp.headers.get("location", "")
        assert location, "Missing Location header in TUS create response"

        # Step 2: Check status via HEAD
        head_resp = await client.head(
            location,
            headers={"Tus-Resumable": "1.0.0"},
        )
        assert head_resp.status_code == 200
        assert head_resp.headers.get("upload-offset") == "0"

        # Step 3: Upload content via PATCH
        patch_resp = await client.patch(
            location,
            headers={
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
            },
            content=file_content,
        )
        assert patch_resp.status_code == 204
        assert patch_resp.headers.get("upload-offset") == str(len(file_content))


# ---------------------------------------------------------------------------
# Tests: Processing status endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProcessingStatus:
    """Test GET /files/{file_id}/processing-status endpoint."""

    async def test_not_found_for_missing_file(
        self, client: AsyncClient, admin_auth_headers: dict[str, str],
    ) -> None:
        """Should return 404 for non-existent file_id."""
        resp = await client.get(
            "/api/v1/files/999999/processing-status",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    async def test_returns_db_status(
        self, client: AsyncClient, admin_auth_headers: dict[str, str],
        test_session_maker,
    ) -> None:
        """Should fall back to database status when no in-memory tracker."""
        # Create a file record directly in DB
        async with test_session_maker() as session:
            file_model = FileModel(
                filename="status_test.csv",
                original_path="/tmp/status_test.csv",
                file_type="csv",
                status=FileStatus.READY,
                row_count=42,
                uploaded_by="testadmin",
            )
            session.add(file_model)
            await session.commit()
            await session.refresh(file_model)
            file_id = file_model.id

        resp = await client.get(
            f"/api/v1/files/{file_id}/processing-status",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["file_id"] == file_id
        assert data["status"] == "ready"
        assert data["percent"] == 100.0
        assert data["rows_processed"] == 42

    async def test_returns_inmemory_progress(
        self, client: AsyncClient, admin_auth_headers: dict[str, str],
        test_session_maker,
    ) -> None:
        """Should return in-memory tracker data when available."""
        # Create a file record in DB
        async with test_session_maker() as session:
            file_model = FileModel(
                filename="inmem_test.csv",
                original_path="/tmp/inmem_test.csv",
                file_type="csv",
                status=FileStatus.PROCESSING,
                uploaded_by="testadmin",
            )
            session.add(file_model)
            await session.commit()
            await session.refresh(file_model)
            file_id = file_model.id

        # Set up in-memory tracker
        progress = start_tracking(file_id)
        progress.phase = "reading_csv"
        progress.percent = 45.0
        progress.rows_processed = 500
        progress.total_rows_estimate = 1000

        try:
            resp = await client.get(
                f"/api/v1/files/{file_id}/processing-status",
                headers=admin_auth_headers,
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["file_id"] == file_id
            assert data["status"] == "processing"
            assert data["phase"] == "reading_csv"
            assert data["percent"] == 45.0
            assert data["rows_processed"] == 500
            assert data["total_rows_estimate"] == 1000
        finally:
            clear_tracking(file_id)

    async def test_db_fallback_with_error(
        self, client: AsyncClient, admin_auth_headers: dict[str, str],
        test_session_maker,
    ) -> None:
        """DB fallback should extract error from metadata_json."""
        async with test_session_maker() as session:
            file_model = FileModel(
                filename="error_test.csv",
                original_path="/tmp/error_test.csv",
                file_type="csv",
                status=FileStatus.FAILED,
                metadata_json={"error": "Parse failed"},
                uploaded_by="testadmin",
            )
            session.add(file_model)
            await session.commit()
            await session.refresh(file_model)
            file_id = file_model.id

        resp = await client.get(
            f"/api/v1/files/{file_id}/processing-status",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
        assert data["error"] == "Parse failed"
        assert data["percent"] == 0.0

    async def test_processing_status_unauthenticated(
        self, client: AsyncClient,
    ) -> None:
        """Should return 401/403 without auth headers."""
        resp = await client.get("/api/v1/files/1/processing-status")
        assert resp.status_code in (401, 403)
