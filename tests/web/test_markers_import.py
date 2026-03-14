"""
Integration tests for the marker CSV import endpoints.

Covers nonwear sensor CSV upload (study-wide and per-file), sleep marker CSV
import, column validation, encoding handling, re-import replacement semantics,
and access control for the endpoints in ``markers_import.py``.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from sleep_scoring_web.db.models import File as FileModel, Marker
from sleep_scoring_web.schemas.enums import FileStatus, MarkerCategory, MarkerType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_file_record(
    test_session_maker,
    filename: str,
    *,
    uploaded_by: str = "testadmin",
    participant_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> int:
    """Insert a File record directly into the test DB and return its id.

    This bypasses the upload+processing pipeline (which requires actual CSV
    parsing and activity data insertion) and gives the import endpoints a
    file to match against.
    """
    async with test_session_maker() as session:
        f = FileModel(
            filename=filename,
            file_type="csv",
            participant_id=participant_id,
            status=FileStatus.READY,
            uploaded_by=uploaded_by,
            start_time=start_time or datetime(2024, 1, 1, 12, 0, 0),
            end_time=end_time or datetime(2024, 1, 2, 12, 0, 0),
        )
        session.add(f)
        await session.commit()
        await session.refresh(f)
        return f.id


def _make_nonwear_csv(
    rows: list[dict[str, str]],
    *,
    columns: list[str] | None = None,
    encoding: str = "utf-8",
) -> bytes:
    """Build a nonwear CSV as raw bytes."""
    if columns is None:
        columns = list(rows[0].keys())
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(row.get(c, "") for c in columns))
    return "\n".join(lines).encode(encoding)


def _make_sleep_csv(
    rows: list[dict[str, str]],
    *,
    columns: list[str] | None = None,
    encoding: str = "utf-8",
    comment_lines: list[str] | None = None,
) -> bytes:
    """Build a sleep-marker import CSV as raw bytes."""
    if columns is None:
        columns = list(rows[0].keys())
    lines: list[str] = []
    if comment_lines:
        lines.extend(comment_lines)
    lines.append(",".join(columns))
    for row in rows:
        lines.append(",".join(row.get(c, "") for c in columns))
    return "\n".join(lines).encode(encoding)


async def _count_markers(
    test_session_maker,
    file_id: int,
    category: str | None = None,
    marker_type: str | None = None,
) -> int:
    """Count markers in the DB for a given file, optionally filtered."""
    async with test_session_maker() as session:
        stmt = select(Marker).where(Marker.file_id == file_id)
        if category is not None:
            stmt = stmt.where(Marker.marker_category == category)
        if marker_type is not None:
            stmt = stmt.where(Marker.marker_type == marker_type)
        result = await session.execute(stmt)
        return len(result.scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMarkersImport:
    """Marker CSV import integration tests."""

    # 1. Valid nonwear CSV import for a specific file
    async def test_nonwear_upload_for_file_valid(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """A well-formed nonwear CSV with date/start_time/end_time columns
        should create sensor nonwear markers for the specified file."""
        file_id = await _create_file_record(test_session_maker, "nw_valid.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "02:00", "end_time": "04:00"},
            {"date": "2024-01-01", "start_time": "06:00", "end_time": "07:30"},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nonwear.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 2
        assert data["dates_imported"] == 1
        assert data["dates_skipped"] == 0

        # Verify markers actually exist in the database
        count = await _count_markers(
            test_session_maker, file_id,
            category=MarkerCategory.NONWEAR,
            marker_type=MarkerType.SENSOR_NONWEAR,
        )
        assert count == 2

    # 2. Nonwear CSV with missing required columns -> 400
    async def test_nonwear_upload_missing_columns(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """CSV without start/end time columns should return 400."""
        file_id = await _create_file_record(test_session_maker, "nw_badcol.csv")

        bad_csv = b"date,value\n2024-01-01,42\n"

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        assert resp.status_code == 400
        detail = resp.json()["detail"].lower()
        assert "start" in detail or "end" in detail

    # 3. Study-wide nonwear upload matches by filename column
    async def test_nonwear_upload_study_wide_by_filename(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Study-wide nonwear CSV with a 'filename' column should match
        rows to the correct uploaded activity file."""
        await _create_file_record(test_session_maker, "participant_abc.csv")

        csv_bytes = _make_nonwear_csv([
            {
                "filename": "participant_abc.csv",
                "date": "2024-01-01",
                "start_time": "03:00",
                "end_time": "05:00",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["matched_rows"] >= 1
        assert data["markers_created"] >= 1

    # 4. Study-wide nonwear upload with unmatched identifier
    async def test_nonwear_upload_study_wide_unmatched(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """When the filename column refers to a file that doesn't exist,
        the row should be skipped and reported in unmatched_identifiers."""
        await _create_file_record(test_session_maker, "real_file.csv")

        csv_bytes = _make_nonwear_csv([
            {
                "filename": "nonexistent_file.csv",
                "date": "2024-01-01",
                "start_time": "01:00",
                "end_time": "02:00",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("unmatched.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] >= 1
        assert len(data["unmatched_identifiers"]) >= 1

    # 5. File-specific nonwear upload: file not found -> 404
    async def test_nonwear_upload_file_not_found(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Uploading nonwear CSV for a non-existent file_id should return 404."""
        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "01:00", "end_time": "02:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/999999/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 404

    # 6. Annotator without file assignment cannot use file-specific nonwear upload
    async def test_nonwear_upload_annotator_no_access(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """An annotator without a FileAssignment row should get 404 on the
        per-file nonwear upload endpoint."""
        file_id = await _create_file_record(test_session_maker, "nw_acl.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "02:00", "end_time": "04:00"},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=annotator_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 404

    # 7. Re-importing nonwear replaces existing sensor nonwear markers
    async def test_nonwear_reimport_replaces_markers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """A second nonwear CSV upload for the same file should delete old
        sensor nonwear markers and replace them with the new ones."""
        file_id = await _create_file_record(test_session_maker, "nw_replace.csv")

        # First upload: 2 markers
        csv1 = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "01:00", "end_time": "02:00"},
            {"date": "2024-01-01", "start_time": "03:00", "end_time": "04:00"},
        ])
        resp1 = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw1.csv", io.BytesIO(csv1), "text/csv")},
        )
        assert resp1.status_code == 200
        assert resp1.json()["markers_created"] == 2

        count_after_first = await _count_markers(
            test_session_maker, file_id,
            category=MarkerCategory.NONWEAR,
            marker_type=MarkerType.SENSOR_NONWEAR,
        )
        assert count_after_first == 2

        # Second upload: 1 marker (replaces the previous 2)
        csv2 = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "05:00", "end_time": "06:00"},
        ])
        resp2 = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw2.csv", io.BytesIO(csv2), "text/csv")},
        )
        assert resp2.status_code == 200
        assert resp2.json()["markers_created"] == 1

        count_after_second = await _count_markers(
            test_session_maker, file_id,
            category=MarkerCategory.NONWEAR,
            marker_type=MarkerType.SENSOR_NONWEAR,
        )
        assert count_after_second == 1

    # 8. Sleep marker CSV import with valid data
    async def test_sleep_import_valid(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """A valid sleep marker CSV with filename, date, onset/offset should
        create sleep markers and return a success response."""
        file_id = await _create_file_record(test_session_maker, "sleep_import_valid.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_import_valid.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:30",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] >= 1
        assert data["dates_imported"] >= 1

        # Verify markers in DB
        count = await _count_markers(
            test_session_maker, file_id, category=MarkerCategory.SLEEP,
        )
        assert count >= 1

    # 9. Sleep marker CSV with missing onset column -> 400
    async def test_sleep_import_missing_onset_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """A sleep CSV without onset_time or onset_datetime should fail with 400."""
        await _create_file_record(test_session_maker, "sleep_badcol.csv")

        bad_csv = b"filename,sleep_date,offset_time\nsleep_badcol.csv,2024-01-01,07:00\n"

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("bad_sleep.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        assert resp.status_code == 400
        assert "onset" in resp.json()["detail"].lower()

    # 10. Sleep marker CSV with latin-1 encoding is handled
    async def test_sleep_import_latin1_encoding(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """CSV encoded as latin-1 (with non-UTF-8 chars) should be parsed
        successfully via the fallback decoder."""
        await _create_file_record(test_session_maker, "sleep_latin1.csv")

        csv_bytes = _make_sleep_csv(
            [
                {
                    "filename": "sleep_latin1.csv",
                    "sleep_date": "2024-01-01",
                    "onset_time": "23:00",
                    "offset_time": "06:00",
                    "marker_type": "MAIN_SLEEP",
                },
            ],
            encoding="latin-1",
            comment_lines=["# R\xe9sum\xe9 of sleep periods"],
        )

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("latin1.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["markers_created"] >= 1

    # 11. Sleep marker CSV with missing date column -> 400
    async def test_sleep_import_missing_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """A sleep CSV without any recognized date column should fail with 400."""
        bad_csv = b"filename,onset_time,offset_time\nfoo.csv,22:00,07:00\n"

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("no_date.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        assert resp.status_code == 400
        assert "date" in resp.json()["detail"].lower()

    # 12. Empty CSV (only comments) -> 400
    async def test_nonwear_upload_empty_csv(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """A CSV that is empty after stripping comment lines should return 400."""
        file_id = await _create_file_record(test_session_maker, "empty_test.csv")

        empty_csv = b"# comment line 1\n# comment line 2\n"

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("empty.csv", io.BytesIO(empty_csv), "text/csv")},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()
