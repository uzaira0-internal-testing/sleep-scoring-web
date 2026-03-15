"""
HTTP integration tests for file access control.

Tests admin/annotator visibility, file assignment CRUD, progress tracking,
and the excluded-filename filtering (IGNORE/ISSUE tokens).
"""

from __future__ import annotations

import io

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from sleep_scoring_web.db.models import File as FileModel
from sleep_scoring_web.db.models import FileAssignment, User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _upload_and_get_file(
    client: AsyncClient,
    auth_headers: dict[str, str],
    csv_content: str,
    filename: str = "test_data.csv",
) -> dict:
    """Upload a CSV file and return the file info."""
    files = {"file": (filename, io.BytesIO(csv_content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", files=files, headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _create_second_annotator(test_session_maker) -> None:
    """Create a second annotator user ('testannotator2') in the test DB."""
    async with test_session_maker() as session:
        existing = await session.execute(
            select(User).where(User.username == "testannotator2")
        )
        if existing.scalar_one_or_none() is None:
            session.add(
                User(
                    username="testannotator2",
                    role=UserRole.ANNOTATOR,
                    is_active=True,
                )
            )
            await session.commit()


# ---------------------------------------------------------------------------
# 1. Admin sees all non-excluded files (no assignments needed)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAdminSeesAllFiles:

    async def test_admin_sees_all_non_excluded_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Admin should see every uploaded file without needing assignments."""
        await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "admin_visible_a.csv")
        await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "admin_visible_b.csv")

        resp = await client.get("/api/v1/files", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        filenames = [item["filename"] for item in data["items"]]
        assert "admin_visible_a.csv" in filenames
        assert "admin_visible_b.csv" in filenames
        assert data["total"] >= 2


# ---------------------------------------------------------------------------
# 2. Annotator with zero assignments -> empty file list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAnnotatorEmptyAssignments:

    async def test_annotator_no_assignments_empty_list(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """An annotator with no assignments should see an empty file list."""
        # Upload a file as admin so data exists
        await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "not_assigned.csv")

        resp = await client.get("/api/v1/files", headers=annotator_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0


# ---------------------------------------------------------------------------
# 3. Assign file to annotator -> annotator sees only that file
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAnnotatorAssignedFile:

    async def test_annotator_sees_assigned_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """After assignment, the annotator should see exactly the assigned file."""
        info_a = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "assigned_file.csv")
        await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "other_file.csv")

        # Assign file_a to the annotator
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [info_a["file_id"]], "username": "testannotator"},
            headers=admin_auth_headers,
        )
        assert assign_resp.status_code == 200

        # Annotator list should contain only the assigned file
        resp = await client.get("/api/v1/files", headers=annotator_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        filenames = [item["filename"] for item in data["items"]]
        assert "assigned_file.csv" in filenames
        assert "other_file.csv" not in filenames
        assert data["total"] == 1


# ---------------------------------------------------------------------------
# 4. Annotator access unassigned file's markers -> 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAnnotatorMarkersAccessDenied:

    async def test_annotator_cannot_access_unassigned_markers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Fetching markers for an unassigned file should return 404."""
        info = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "no_marker_access.csv")
        file_id = info["file_id"]

        resp = await client.get(
            f"/api/v1/markers/{file_id}/2024-01-01",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 5. Annotator access unassigned file's activity -> 404
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAnnotatorActivityAccessDenied:

    async def test_annotator_cannot_access_unassigned_activity(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Fetching activity data for an unassigned file should return 404."""
        info = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "no_activity_access.csv")
        file_id = info["file_id"]

        resp = await client.get(
            f"/api/v1/activity/{file_id}/2024-01-01",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 6. Annotator access unassigned file's dates -> 404 (or empty)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAnnotatorDatesAccessDenied:

    async def test_annotator_cannot_access_unassigned_dates(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Fetching dates for an unassigned file should return 404."""
        info = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "no_dates_access.csv")
        file_id = info["file_id"]

        resp = await client.get(
            f"/api/v1/files/{file_id}/dates",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 7. Admin accesses any file without assignment -> 200
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAdminAccessWithoutAssignment:

    async def test_admin_access_any_file_without_assignment(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Admin should access any file's dates/activity without assignment."""
        info = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "admin_no_assign.csv")
        file_id = info["file_id"]

        dates_resp = await client.get(
            f"/api/v1/files/{file_id}/dates",
            headers=admin_auth_headers,
        )
        assert dates_resp.status_code == 200

        activity_resp = await client.get(
            f"/api/v1/activity/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )
        assert activity_resp.status_code == 200


# ---------------------------------------------------------------------------
# 8. File with "IGNORE" in name hidden from admin in list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestIgnoreFileHidden:

    async def test_ignore_file_hidden_from_admin_list(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Files with IGNORE in the filename should not appear in the file list."""
        # Upload a normal file
        await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "normal_file.csv")

        # Insert an IGNORE file directly into the DB (upload rejects excluded names)
        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="participant_IGNORE.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                )
            )
            await session.commit()

        resp = await client.get("/api/v1/files", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        filenames = [item["filename"] for item in data["items"]]
        assert "participant_IGNORE.csv" not in filenames
        assert "normal_file.csv" in filenames


# ---------------------------------------------------------------------------
# 9. File with "ISSUE" in name hidden from admin in list
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestIssueFileHidden:

    async def test_issue_file_hidden_from_admin_list(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Files with ISSUE in the filename should not appear in the file list."""
        await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "clean_file.csv")

        async with test_session_maker() as session:
            session.add(
                FileModel(
                    filename="participant_issue_01.csv",
                    file_type="csv",
                    status="ready",
                    uploaded_by="testadmin",
                )
            )
            await session.commit()

        resp = await client.get("/api/v1/files", headers=admin_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        filenames = [item["filename"] for item in data["items"]]
        assert "participant_issue_01.csv" not in filenames
        assert "clean_file.csv" in filenames


# ---------------------------------------------------------------------------
# 10. Assignment CRUD: create, list, delete
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAssignmentCRUD:

    async def test_assignment_create_list_delete(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Should create, list, and delete file assignments."""
        info = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "crud_file.csv")
        file_id = info["file_id"]

        # CREATE
        create_resp = await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [file_id], "username": "testannotator"},
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 200
        create_data = create_resp.json()
        assert create_data["created"] == 1

        # LIST
        list_resp = await client.get("/api/v1/files/assignments", headers=admin_auth_headers)
        assert list_resp.status_code == 200
        assignments = list_resp.json()
        matching = [a for a in assignments if a["file_id"] == file_id and a["username"] == "testannotator"]
        assert len(matching) == 1

        # DELETE (by file_id + target_username)
        del_resp = await client.delete(
            f"/api/v1/files/{file_id}/assignments/testannotator",
            headers=admin_auth_headers,
        )
        assert del_resp.status_code == 200
        assert del_resp.json()["deleted"] == 1

        # Verify deletion
        list_resp2 = await client.get("/api/v1/files/assignments", headers=admin_auth_headers)
        assignments2 = list_resp2.json()
        matching2 = [a for a in assignments2 if a["file_id"] == file_id and a["username"] == "testannotator"]
        assert len(matching2) == 0


# ---------------------------------------------------------------------------
# 11. Assignment progress returns correct counts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAssignmentProgress:

    async def test_assignment_progress(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Progress endpoint should return per-user, per-file date counts."""
        info = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "progress_file.csv")
        file_id = info["file_id"]

        # Assign to annotator
        await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [file_id], "username": "testannotator"},
            headers=admin_auth_headers,
        )

        resp = await client.get("/api/v1/files/assignments/progress", headers=admin_auth_headers)
        assert resp.status_code == 200
        progress = resp.json()
        assert type(progress) is list
        assert len(progress) == 1

        # Find the testannotator entry
        annotator_progress = [p for p in progress if p["username"] == "testannotator"]
        assert len(annotator_progress) == 1
        entry = annotator_progress[0]
        assert entry["total_files"] == 1
        # scored_dates should be 0 since no markers were placed
        file_entry = [f for f in entry["files"] if f["file_id"] == file_id]
        assert len(file_entry) == 1
        assert file_entry[0]["scored_dates"] == 0


# ---------------------------------------------------------------------------
# 12. Unassigned files endpoint returns correct files
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestUnassignedFiles:

    async def test_unassigned_files_endpoint(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Unassigned endpoint should return files with zero assignments."""
        info_a = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "unassigned_file.csv")
        info_b = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "assigned_away.csv")

        # Assign file_b to annotator so only file_a is unassigned
        await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [info_b["file_id"]], "username": "testannotator"},
            headers=admin_auth_headers,
        )

        resp = await client.get("/api/v1/files/assignments/unassigned", headers=admin_auth_headers)
        assert resp.status_code == 200
        unassigned = resp.json()
        unassigned_ids = [f["id"] for f in unassigned]
        assert info_a["file_id"] in unassigned_ids
        assert info_b["file_id"] not in unassigned_ids


# ---------------------------------------------------------------------------
# 13. Two annotators with different assignments see different lists
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestTwoAnnotatorsDifferentViews:

    async def test_two_annotators_see_different_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Two annotators assigned different files should see non-overlapping lists."""
        # Create a second annotator user
        await _create_second_annotator(test_session_maker)
        annotator2_headers: dict[str, str] = {"X-Username": "testannotator2", "X-Site-Password": "testpass"}

        info_a = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "ann1_file.csv")
        info_b = await _upload_and_get_file(client, admin_auth_headers, sample_csv_content, "ann2_file.csv")

        # Assign file_a to annotator1, file_b to annotator2
        await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [info_a["file_id"]], "username": "testannotator"},
            headers=admin_auth_headers,
        )
        await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [info_b["file_id"]], "username": "testannotator2"},
            headers=admin_auth_headers,
        )

        # Annotator 1 sees only file_a
        annotator1_headers: dict[str, str] = {"X-Username": "testannotator", "X-Site-Password": "testpass"}
        resp1 = await client.get("/api/v1/files", headers=annotator1_headers)
        assert resp1.status_code == 200
        filenames1 = [item["filename"] for item in resp1.json()["items"]]
        assert "ann1_file.csv" in filenames1
        assert "ann2_file.csv" not in filenames1

        # Annotator 2 sees only file_b
        resp2 = await client.get("/api/v1/files", headers=annotator2_headers)
        assert resp2.status_code == 200
        filenames2 = [item["filename"] for item in resp2.json()["items"]]
        assert "ann2_file.csv" in filenames2
        assert "ann1_file.csv" not in filenames2
