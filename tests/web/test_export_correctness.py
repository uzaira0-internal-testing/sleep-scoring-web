"""
Export correctness tests.

Validates export column listing, CSV generation, access control filtering,
date range filtering, and metadata response accuracy.
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient

from tests.web.conftest import make_sleep_marker, upload_and_get_date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _upload_file(
    client: AsyncClient,
    auth_headers: dict[str, str],
    csv_content: str,
    filename: str = "test_data.csv",
) -> int:
    """Upload a CSV file and return its file_id."""
    files = {"file": (filename, io.BytesIO(csv_content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", files=files, headers=auth_headers)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["file_id"]


async def _upload_and_save_markers(
    client: AsyncClient,
    auth_headers: dict[str, str],
    csv_content: str,
    filename: str = "test_data.csv",
) -> tuple[int, str]:
    """Upload a file, wait for processing, save markers, return (file_id, analysis_date)."""
    file_id, analysis_date = await upload_and_get_date(
        client, auth_headers, csv_content, filename=filename
    )

    # Save a sleep marker for this date.
    # Use timestamps within 2024-01-01 noon-to-noon window to match sample data.
    markers = {
        "sleep_markers": [make_sleep_marker()],
        "nonwear_markers": [],
        "is_no_sleep": False,
    }
    save_resp = await client.put(
        f"/api/v1/markers/{file_id}/{analysis_date}",
        json=markers,
        headers=auth_headers,
    )
    assert save_resp.status_code == 200, f"Save markers failed: {save_resp.text}"

    return file_id, analysis_date


# ---------------------------------------------------------------------------
# 1. Default columns: GET /export/columns returns non-empty column list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDefaultColumns:

    async def test_returns_non_empty_column_list(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ):
        """GET /export/columns should return a non-empty list of columns."""
        resp = await client.get("/api/v1/export/columns", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert "columns" in data
        assert type(data["columns"]) is list
        assert len(data["columns"]) > 0

        # Each column should have required fields
        col = data["columns"][0]
        assert "name" in col
        assert "category" in col
        assert "description" in col
        assert "data_type" in col
        assert "is_default" in col


# ---------------------------------------------------------------------------
# 2. Column listing: categories are grouped correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestColumnCategoriesGrouped:

    async def test_categories_grouped_correctly(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ):
        """Categories should each contain at least one column, and every column
        in the flat list should belong to a category that appears in the
        categories list."""
        resp = await client.get("/api/v1/export/columns", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()

        categories = data["categories"]
        assert type(categories) is list
        assert len(categories) > 0

        # Each category must have a name and a non-empty columns list
        category_names = set()
        for cat in categories:
            assert "name" in cat
            assert "columns" in cat
            assert type(cat["columns"]) is list
            assert len(cat["columns"]) > 0, f"Category '{cat['name']}' has no columns"
            category_names.add(cat["name"])

        # Every column's category must appear in the categories list
        for col in data["columns"]:
            assert col["category"] in category_names, (
                f"Column '{col['name']}' has category '{col['category']}' "
                f"which is not in the categories list"
            )


# ---------------------------------------------------------------------------
# 3. Access control: annotator export only includes assigned files
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAnnotatorExportAccessControl:

    async def test_annotator_export_only_includes_assigned_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """An annotator should only export files they are assigned to.
        Unassigned files should be silently excluded from the export."""
        # Upload two files as admin
        file_id_assigned, _ = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "assigned_export.csv"
        )
        file_id_unassigned, _ = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "unassigned_export.csv"
        )

        # Assign only one file to the annotator
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [file_id_assigned], "username": "testannotator"},
            headers=admin_auth_headers,
        )
        assert assign_resp.status_code == 200

        # Annotator requests export for both files
        export_resp = await client.post(
            "/api/v1/export/csv",
            json={"file_ids": [file_id_assigned, file_id_unassigned]},
            headers=annotator_auth_headers,
        )
        assert export_resp.status_code == 200
        data = export_resp.json()

        # The export should include at most 1 file (the assigned one)
        assert data["file_count"] <= 1

        # Download the CSV and verify only the assigned file appears
        dl_resp = await client.post(
            "/api/v1/export/csv/download",
            json={"file_ids": [file_id_assigned, file_id_unassigned]},
            headers=annotator_auth_headers,
        )
        assert dl_resp.status_code == 200
        csv_text = dl_resp.text

        # If there are rows, they must only reference the assigned file
        if csv_text.strip():
            assert "unassigned_export.csv" not in csv_text


# ---------------------------------------------------------------------------
# 4. Quick export with valid file IDs returns CSV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestQuickExportValidIds:

    async def test_quick_export_returns_csv(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """GET /export/csv/quick with valid file IDs should return a 200
        response with text/csv content type."""
        file_id, _ = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "quick_export.csv"
        )

        resp = await client.get(
            f"/api/v1/export/csv/quick?file_ids={file_id}",
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")

        # Should contain CSV content (at least a header or data)
        csv_text = resp.text
        assert len(csv_text) > 0

    async def test_quick_export_multiple_file_ids(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Quick export should accept comma-separated file IDs."""
        file_id1 = await _upload_file(
            client, admin_auth_headers, sample_csv_content, "quick_multi_1.csv"
        )
        file_id2 = await _upload_file(
            client, admin_auth_headers, sample_csv_content, "quick_multi_2.csv"
        )

        resp = await client.get(
            f"/api/v1/export/csv/quick?file_ids={file_id1},{file_id2}",
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# 5. Export with no data returns empty/error
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExportNoData:

    async def test_export_nonexistent_file_ids(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ):
        """Exporting with file IDs that do not exist should succeed with
        zero rows or return an appropriate warning."""
        resp = await client.post(
            "/api/v1/export/csv",
            json={"file_ids": [999999]},
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        # Should either report success with 0 rows or include a warning
        assert data["row_count"] == 0

    async def test_export_empty_file_ids_list(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ):
        """Exporting with an empty file_ids list should fail gracefully."""
        resp = await client.post(
            "/api/v1/export/csv",
            json={"file_ids": []},
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        # success=False because no files were specified
        assert data["success"] is False

    async def test_quick_export_nonexistent_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ):
        """Quick export with a non-existent file ID should return 200 with
        an error CSV (comment-based error message)."""
        resp = await client.get(
            "/api/v1/export/csv/quick?file_ids=999999",
            headers=admin_auth_headers,
        )

        # The endpoint returns 200 with a CSV containing an error comment
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 6. Export request with date range filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExportDateRangeFilter:

    async def test_date_range_filters_results(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Export with a date_range that excludes the marker date should
        return zero rows."""
        file_id, analysis_date = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "daterange_export.csv"
        )

        # Export with a date range that does NOT cover the analysis date
        # (use a far-future range so no real data falls in it)
        resp = await client.post(
            "/api/v1/export/csv",
            json={
                "file_ids": [file_id],
                "date_range": ["2099-01-01", "2099-12-31"],
            },
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["row_count"] == 0

    async def test_date_range_includes_matching_data(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Export with a date_range covering the marker date should return
        the expected rows."""
        file_id, analysis_date = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "daterange_incl.csv"
        )

        # Use a broad date range that covers the sample data dates
        resp = await client.post(
            "/api/v1/export/csv",
            json={
                "file_ids": [file_id],
                "date_range": ["2023-01-01", "2025-12-31"],
            },
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        # Should find at least one row (the marker we saved)
        assert data["row_count"] >= 1
        assert data["file_count"] >= 1


# ---------------------------------------------------------------------------
# 7. Export metadata response includes correct row/file counts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestExportMetadataCounts:

    async def test_metadata_row_and_file_counts(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """POST /export/csv metadata response should report accurate
        row_count and file_count."""
        file_id, analysis_date = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "meta_counts.csv"
        )

        resp = await client.post(
            "/api/v1/export/csv",
            json={"file_ids": [file_id]},
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["row_count"] >= 1
        assert data["file_count"] == 1
        assert "message" in data

    async def test_metadata_counts_with_multiple_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """Exporting multiple files should correctly count each distinct file."""
        file_id1, _ = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "meta_multi_1.csv"
        )
        file_id2, _ = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "meta_multi_2.csv"
        )

        resp = await client.post(
            "/api/v1/export/csv",
            json={"file_ids": [file_id1, file_id2]},
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["row_count"] >= 2
        assert data["file_count"] == 2

    async def test_metadata_message_format(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ):
        """The message field should reference the row and file counts."""
        file_id, _ = await _upload_and_save_markers(
            client, admin_auth_headers, sample_csv_content, "meta_msg.csv"
        )

        resp = await client.post(
            "/api/v1/export/csv",
            json={"file_ids": [file_id]},
            headers=admin_auth_headers,
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Message should contain the word "Exported" and reference counts
        assert "Exported" in data["message"]
        assert str(data["row_count"]) in data["message"]
        assert str(data["file_count"]) in data["message"]
