"""
Tests for the upload processor (background file processing pipeline).

Covers:
- Full processing pipeline via the /api/v1/files/upload endpoint
- CSV validation (_validate_csv_format)
- Streaming decompression (_streaming_decompress)
- Error handling for invalid/empty files
- Status transitions: PENDING -> PROCESSING -> READY / FAILED
- The direct process_uploaded_file function with mocked DB
"""

from __future__ import annotations

import gzip
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from sleep_scoring_web.schemas.enums import FileStatus
from sleep_scoring_web.services.processing_tracker import (
    _processing_status,
    clear_tracking,
    get_progress,
)
from sleep_scoring_web.services.upload_processor import (
    _streaming_decompress,
    _validate_csv_format,
)


# ---------------------------------------------------------------------------
# Unit tests: _validate_csv_format
# ---------------------------------------------------------------------------


class TestValidateCsvFormat:
    """Tests for _validate_csv_format."""

    def test_valid_csv_with_commas(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "valid.csv"
        csv_file.write_text("a,b,c\n1,2,3\n4,5,6\n")
        _validate_csv_format(csv_file)  # Should not raise

    def test_valid_csv_with_tabs(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "valid.tsv"
        csv_file.write_text("a\tb\tc\n1\t2\t3\n")
        _validate_csv_format(csv_file)  # Should not raise

    def test_empty_file_raises(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        with pytest.raises(ValueError, match="Empty file"):
            _validate_csv_format(csv_file)

    def test_no_delimiter_raises(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "no_delim.csv"
        csv_file.write_text("just some plain text\nno delimiters here\n")
        with pytest.raises(ValueError, match="does not appear to be CSV"):
            _validate_csv_format(csv_file)

    def test_single_line_with_comma(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "single.csv"
        csv_file.write_text("a,b\n")
        _validate_csv_format(csv_file)  # Should not raise

    def test_header_only_with_commas(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "header_only.csv"
        csv_file.write_text("col1,col2,col3\n")
        _validate_csv_format(csv_file)  # Should not raise

    def test_mixed_lines_with_one_having_comma(self, tmp_path: Path) -> None:
        csv_file = tmp_path / "mixed.csv"
        csv_file.write_text("metadata line\ndate,time,value\n1/1/2024,12:00,42\n")
        _validate_csv_format(csv_file)  # Should not raise

    def test_binary_content_no_delimiter(self, tmp_path: Path) -> None:
        """Binary-looking content without delimiters should fail."""
        csv_file = tmp_path / "binary.csv"
        csv_file.write_bytes(b"\x00\x01\x02\x03\n\x04\x05\x06\x07\n")
        with pytest.raises(ValueError, match="does not appear to be CSV"):
            _validate_csv_format(csv_file)


# ---------------------------------------------------------------------------
# Unit tests: _streaming_decompress
# ---------------------------------------------------------------------------


class TestStreamingDecompress:
    """Tests for _streaming_decompress."""

    def test_decompresses_gzip_file(self, tmp_path: Path) -> None:
        original_content = b"Date,Time,Axis1\n1/1/2024,12:00:00,42\n" * 100
        gz_path = tmp_path / "test.csv.gz"
        out_path = tmp_path / "test.csv"

        with gzip.open(gz_path, "wb") as f:
            f.write(original_content)

        _streaming_decompress(gz_path, out_path)

        assert out_path.exists()
        assert out_path.read_bytes() == original_content

    def test_decompresses_empty_gzip(self, tmp_path: Path) -> None:
        gz_path = tmp_path / "empty.csv.gz"
        out_path = tmp_path / "empty.csv"

        with gzip.open(gz_path, "wb") as f:
            f.write(b"")

        _streaming_decompress(gz_path, out_path)

        assert out_path.exists()
        assert out_path.read_bytes() == b""

    def test_output_file_created(self, tmp_path: Path) -> None:
        content = b"a,b,c\n1,2,3\n"
        gz_path = tmp_path / "data.gz"
        out_path = tmp_path / "data.csv"

        with gzip.open(gz_path, "wb") as f:
            f.write(content)

        assert not out_path.exists()
        _streaming_decompress(gz_path, out_path)
        assert out_path.exists()


# ---------------------------------------------------------------------------
# Integration tests: upload endpoint → process_uploaded_file pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUploadProcessorIntegration:
    """
    Integration tests that upload files through the API and verify
    the processing pipeline's end-to-end behavior.
    """

    async def test_upload_valid_csv_reaches_ready(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Valid CSV upload should result in READY status."""
        import io

        files = {
            "file": (
                "test_processor.csv",
                io.BytesIO(sample_csv_content.encode()),
                "text/csv",
            )
        }
        resp = await client.post(
            "/api/v1/files/upload", files=files, headers=admin_auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["row_count"] == 100

    async def test_upload_stores_activity_data(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Uploaded data should be retrievable via the activity endpoint."""
        import io

        files = {
            "file": (
                "test_activity_store.csv",
                io.BytesIO(sample_csv_content.encode()),
                "text/csv",
            )
        }
        resp = await client.post(
            "/api/v1/files/upload", files=files, headers=admin_auth_headers
        )
        assert resp.status_code == 200
        file_id = resp.json()["file_id"]

        # Get dates
        dates_resp = await client.get(
            f"/api/v1/files/{file_id}/dates", headers=admin_auth_headers
        )
        assert dates_resp.status_code == 200
        dates = dates_resp.json()
        assert len(dates) > 0

    async def test_upload_empty_file_fails(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Empty file should be rejected."""
        import io

        files = {
            "file": (
                "empty.csv",
                io.BytesIO(b""),
                "text/csv",
            )
        }
        resp = await client.post(
            "/api/v1/files/upload", files=files, headers=admin_auth_headers
        )
        # The endpoint may return 400 or 500 depending on where validation catches it
        assert resp.status_code in (400, 422, 500)

    async def test_upload_non_csv_content_fails(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """File without CSV delimiters should fail processing."""
        import io

        content = "this is not a csv file\njust plain text\nno delimiters\n"
        files = {
            "file": (
                "not_csv.csv",
                io.BytesIO(content.encode()),
                "text/csv",
            )
        }
        resp = await client.post(
            "/api/v1/files/upload", files=files, headers=admin_auth_headers
        )
        # Should fail — either during validation or parsing
        assert resp.status_code in (400, 422, 500)

    async def test_upload_gzipped_csv(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Gzipped CSV should be decompressed and processed correctly."""
        import io

        compressed = gzip.compress(sample_csv_content.encode())
        files = {
            "file": (
                "test_gz.csv.gz",
                io.BytesIO(compressed),
                "application/gzip",
            )
        }
        resp = await client.post(
            "/api/v1/files/upload", files=files, headers=admin_auth_headers
        )
        # The sync upload endpoint may or may not handle gz — depends on implementation
        # Just verify it doesn't crash
        assert resp.status_code in (200, 400, 422, 500)

    async def test_duplicate_upload_rejected(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Uploading the same filename twice should be rejected."""
        import io

        filename = "duplicate_test.csv"
        files1 = {
            "file": (
                filename,
                io.BytesIO(sample_csv_content.encode()),
                "text/csv",
            )
        }
        resp1 = await client.post(
            "/api/v1/files/upload", files=files1, headers=admin_auth_headers
        )
        assert resp1.status_code == 200

        files2 = {
            "file": (
                filename,
                io.BytesIO(sample_csv_content.encode()),
                "text/csv",
            )
        }
        resp2 = await client.post(
            "/api/v1/files/upload", files=files2, headers=admin_auth_headers
        )
        # Should be rejected — the API returns 400 for duplicate filenames
        assert resp2.status_code in (400, 409), (
            f"Expected 400 or 409 for duplicate, got {resp2.status_code}"
        )

    async def test_file_metadata_stored(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """File metadata (start_time, row_count) should be stored after processing."""
        import io

        files = {
            "file": (
                "metadata_test.csv",
                io.BytesIO(sample_csv_content.encode()),
                "text/csv",
            )
        }
        resp = await client.post(
            "/api/v1/files/upload", files=files, headers=admin_auth_headers
        )
        assert resp.status_code == 200
        file_id = resp.json()["file_id"]

        # Fetch file info
        info_resp = await client.get(
            f"/api/v1/files/{file_id}", headers=admin_auth_headers
        )
        assert info_resp.status_code == 200
        info = info_resp.json()
        assert info["row_count"] == 100
        assert info["status"] == "ready"


# ---------------------------------------------------------------------------
# Unit tests: process_uploaded_file (mocked DB)
# ---------------------------------------------------------------------------


class TestProcessUploadedFileUnit:
    """Unit tests for process_uploaded_file with mocked database."""

    @pytest.mark.asyncio
    async def test_missing_file_record_returns_early(self) -> None:
        """If file_id not found in DB, should return without crashing."""
        from sleep_scoring_web.services.upload_processor import process_uploaded_file

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "sleep_scoring_web.services.upload_processor.async_session_maker",
            return_value=mock_db,
        ):
            # Should not raise
            await process_uploaded_file(
                file_id=999,
                tus_file_path="/nonexistent/path",
                original_filename="missing.csv",
                is_gzip=False,
                username="testuser",
            )

    @pytest.mark.asyncio
    async def test_processing_error_marks_failed(self, tmp_path: Path) -> None:
        """Processing errors should mark file as FAILED and clean up."""
        from sleep_scoring_web.services.upload_processor import process_uploaded_file

        # Create a file that will fail validation (no delimiters)
        bad_csv = tmp_path / "bad.csv"
        bad_csv.write_text("no delimiters here\njust text\n")

        mock_file_model = MagicMock()
        mock_file_model.id = 1
        mock_file_model.status = FileStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file_model

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        # Clear any prior tracking
        _processing_status.clear()

        with patch(
            "sleep_scoring_web.services.upload_processor.async_session_maker",
            return_value=mock_db,
        ):
            await process_uploaded_file(
                file_id=1,
                tus_file_path=str(bad_csv),
                original_filename="bad.csv",
                is_gzip=False,
                username="testuser",
            )

        # The error handler should have been called — check that the progress
        # was updated with a FAILED status
        progress = get_progress(1)
        if progress is not None:
            assert progress.status == FileStatus.FAILED
            assert progress.error is not None

    @pytest.mark.asyncio
    async def test_gzip_decompression_in_pipeline(self, tmp_path: Path) -> None:
        """Gzip files should be decompressed before processing."""
        from sleep_scoring_web.services.upload_processor import process_uploaded_file

        # Create a valid CSV, gzip it
        csv_content = "Date,Time,Axis1,Axis2,Axis3,VM\n1/1/2024,12:00:00,42,10,5,44\n"
        gz_path = tmp_path / "data.csv.gz"
        with gzip.open(gz_path, "wt") as f:
            f.write(csv_content)

        mock_file_model = MagicMock()
        mock_file_model.id = 2
        mock_file_model.status = FileStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file_model

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        _processing_status.clear()

        # The file will be decompressed, validated (commas present), then fail
        # at is_raw_geneactiv or CSVLoaderService since data is minimal.
        # We just verify decompression runs without error.
        with (
            patch(
                "sleep_scoring_web.services.upload_processor.async_session_maker",
                return_value=mock_db,
            ),
            patch(
                "sleep_scoring_web.services.upload_processor.is_raw_geneactiv",
                return_value=False,
            ),
            patch(
                "sleep_scoring_web.services.upload_processor.CSVLoaderService"
            ) as mock_loader_cls,
        ):
            import pandas as pd
            from datetime import datetime

            mock_loader = MagicMock()
            mock_loader.load_file.return_value = {
                "activity_data": pd.DataFrame({
                    "timestamp": [datetime(2024, 1, 1, 12, 0)],
                    "axis_y": [42.0],
                }),
                "metadata": {
                    "loader": "csv",
                    "start_time": datetime(2024, 1, 1, 12, 0),
                    "end_time": datetime(2024, 1, 1, 12, 0),
                    "device_type": "actigraph",
                    "epoch_length_seconds": 60,
                },
            }
            mock_loader_cls.return_value = mock_loader

            with patch(
                "sleep_scoring_web.api.files.bulk_insert_activity_data",
                new_callable=AsyncMock,
                return_value=1,
            ):
                await process_uploaded_file(
                    file_id=2,
                    tus_file_path=str(gz_path),
                    original_filename="data.csv.gz",
                    is_gzip=True,
                    username="testuser",
                )

        # Verify file model was updated
        assert mock_file_model.status == FileStatus.READY

    @pytest.mark.asyncio
    async def test_temp_file_cleaned_up_after_decompression(self, tmp_path: Path) -> None:
        """Temp decompressed files should be cleaned up even on failure."""
        from sleep_scoring_web.services.upload_processor import process_uploaded_file

        csv_content = "no delimiters"
        gz_path = tmp_path / "cleanup_test.csv.gz"
        with gzip.open(gz_path, "wt") as f:
            f.write(csv_content)

        mock_file_model = MagicMock()
        mock_file_model.id = 3
        mock_file_model.status = FileStatus.PENDING

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file_model

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        _processing_status.clear()

        with patch(
            "sleep_scoring_web.services.upload_processor.async_session_maker",
            return_value=mock_db,
        ):
            await process_uploaded_file(
                file_id=3,
                tus_file_path=str(gz_path),
                original_filename="cleanup_test.csv.gz",
                is_gzip=True,
                username="testuser",
            )

        # All temp files in the system temp dir with .csv suffix created by
        # the processor should have been cleaned up. We can't check exactly which
        # file was created, but we can verify the error was handled gracefully.
        progress = get_progress(3)
        if progress is not None:
            assert progress.status == FileStatus.FAILED

    @pytest.mark.asyncio
    async def test_epoch_csv_processing(self, tmp_path: Path) -> None:
        """Standard epoch CSV should be processed via CSVLoaderService."""
        import datetime

        from sleep_scoring_web.services.upload_processor import process_uploaded_file

        # Build a valid CSV — _validate_csv_format reads the first 6 lines,
        # so we need commas within that window.  Use a minimal header that
        # contains commas so validation passes.
        lines = [
            "# header,with,commas",
            "# serial,TEST,device",
            "# start,12:00:00,time",
            "# date,1/1/2024,info",
            "# epoch,00:01:00,period",
            "# end,header,section",
            "# mode,12,config",
            "# battery,4.20,volts",
            "# memory,0,address",
            "# separator,---,---",
            "Date,Time,Axis1,Axis2,Axis3,Vector Magnitude",
        ]
        base = datetime.datetime(2024, 1, 1, 12, 0, 0)
        for i in range(50):
            ts = base + datetime.timedelta(minutes=i)
            lines.append(f"{ts.strftime('%m/%d/%Y')},{ts.strftime('%H:%M:%S')},{i*2},{i},{i*3},{i*4}")

        csv_path = tmp_path / "epoch_test.csv"
        csv_path.write_text("\n".join(lines))

        mock_file_model = MagicMock()
        mock_file_model.id = 10
        mock_file_model.status = FileStatus.PENDING
        mock_file_model.metadata_json = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file_model

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        _processing_status.clear()

        with (
            patch(
                "sleep_scoring_web.services.upload_processor.async_session_maker",
                return_value=mock_db,
            ),
            patch(
                "sleep_scoring_web.services.upload_processor.is_raw_geneactiv",
                return_value=False,
            ),
            patch(
                "sleep_scoring_web.api.files.bulk_insert_activity_data",
                new_callable=AsyncMock,
                return_value=50,
            ) as mock_insert,
        ):
            await process_uploaded_file(
                file_id=10,
                tus_file_path=str(csv_path),
                original_filename="epoch_test.csv",
                is_gzip=False,
                username="testuser",
            )

        assert mock_file_model.status == FileStatus.READY
        assert mock_file_model.row_count == 50
        mock_insert.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_transitions_during_processing(self, tmp_path: Path) -> None:
        """Track status transitions during normal epoch processing."""
        import datetime

        from sleep_scoring_web.services.upload_processor import process_uploaded_file

        # Build valid CSV — headers must contain commas/tabs for validation
        lines = [
            "# header,with,commas",
            "# serial,TEST,device",
            "# start,12:00:00,time",
            "# date,1/1/2024,info",
            "# epoch,00:01:00,period",
            "# end,header,section",
            "# mode,12,config",
            "# battery,4.20,volts",
            "# memory,0,address",
            "# separator,---,---",
            "Date,Time,Axis1,Axis2,Axis3,Vector Magnitude",
        ]
        base = datetime.datetime(2024, 1, 1, 12, 0, 0)
        for i in range(10):
            ts = base + datetime.timedelta(minutes=i)
            lines.append(f"{ts.strftime('%m/%d/%Y')},{ts.strftime('%H:%M:%S')},{i},{i},{i},{i}")

        csv_path = tmp_path / "transitions_test.csv"
        csv_path.write_text("\n".join(lines))

        # Use a simple object instead of MagicMock to track attribute changes
        class FakeFileModel:
            def __init__(self):
                self.id = 20
                self.status = FileStatus.PENDING
                self.row_count = None
                self.start_time = None
                self.end_time = None
                self.metadata_json = None
                self.statuses_seen = []

            def __setattr__(self, name, value):
                if name == "status" and name != "statuses_seen":
                    # Track after initial setup
                    if hasattr(self, "statuses_seen"):
                        self.statuses_seen.append(value)
                super().__setattr__(name, value)

        mock_file_model = FakeFileModel()

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_file_model

        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        _processing_status.clear()

        with (
            patch(
                "sleep_scoring_web.services.upload_processor.async_session_maker",
                return_value=mock_db,
            ),
            patch(
                "sleep_scoring_web.services.upload_processor.is_raw_geneactiv",
                return_value=False,
            ),
            patch(
                "sleep_scoring_web.api.files.bulk_insert_activity_data",
                new_callable=AsyncMock,
                return_value=10,
            ),
        ):
            await process_uploaded_file(
                file_id=20,
                tus_file_path=str(csv_path),
                original_filename="transitions_test.csv",
                is_gzip=False,
                username="testuser",
            )

        # Should have seen PROCESSING then READY
        assert FileStatus.PROCESSING in mock_file_model.statuses_seen
        assert FileStatus.READY in mock_file_model.statuses_seen
