"""
HTTP integration tests for the markers API endpoints.

Tests CRUD operations for sleep/nonwear markers via /api/v1/markers.
"""

import asyncio
import io
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient

from sleep_scoring_web.db.models import DiaryEntry
from sleep_scoring_web.db.models import File as FileModel


async def _upload_and_get_date(client: AsyncClient, headers: dict, content: str, filename: str) -> tuple[int, str]:
    """Upload a CSV file and return (file_id, first_date)."""
    files = {"file": (filename, io.BytesIO(content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", headers=headers, files=files)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    file_id = resp.json()["file_id"]

    dates_resp = await client.get(f"/api/v1/files/{file_id}/dates", headers=headers)
    dates = dates_resp.json()
    assert len(dates) >= 1
    return file_id, dates[0]


@pytest.mark.asyncio
class TestGetMarkers:
    """Tests for GET /api/v1/markers/{file_id}/{date}."""

    async def test_empty_markers_for_new_date(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return empty markers for a date with no saved markers."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_empty.csv")

        response = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["sleep_markers"] == []
        assert data["nonwear_markers"] == []
        assert data["metrics"] == []
        assert data["is_no_sleep"] is False

    async def test_file_not_found(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return 404 for non-existent file."""
        response = await client.get("/api/v1/markers/99999/2024-01-01", headers=admin_auth_headers)

        assert response.status_code == 404


@pytest.mark.asyncio
class TestSaveMarkers:
    """Tests for PUT /api/v1/markers/{file_id}/{date}."""

    async def test_save_sleep_markers(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should save sleep markers and return success."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_save.csv")

        # Get activity timestamps to use realistic values
        activity_resp = await client.get(
            f"/api/v1/activity/{file_id}/{analysis_date}/score",
            headers=admin_auth_headers,
        )
        timestamps = activity_resp.json()["data"]["timestamps"]
        onset_ts = timestamps[10]  # 10 minutes in
        offset_ts = timestamps[50]  # 50 minutes in

        response = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": onset_ts,
                        "offset_timestamp": offset_ts,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["sleep_marker_count"] == 1

    async def test_save_and_retrieve_markers(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Saved markers should be retrievable via GET."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_roundtrip.csv")

        # Save a marker
        await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704070800.0,
                        "offset_timestamp": 1704096000.0,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )

        # Retrieve it
        response = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["sleep_markers"]) == 1
        assert data["sleep_markers"][0]["onset_timestamp"] == 1704070800.0

    async def test_save_nonwear_markers(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should save nonwear markers."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_nw.csv")

        response = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [],
                "nonwear_markers": [
                    {
                        "start_timestamp": 1704070800.0,
                        "end_timestamp": 1704074400.0,
                        "marker_index": 1,
                    }
                ],
            },
        )

        assert response.status_code == 200
        assert response.json()["nonwear_marker_count"] == 1

    async def test_markers_isolated_per_user(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Saving as one scorer should not overwrite another scorer's markers."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_user_iso.csv")

        # Assign file to annotator so they have access
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert assign_resp.status_code == 200

        # Admin saves marker A
        resp_a = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704070800.0,
                        "offset_timestamp": 1704074400.0,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )
        assert resp_a.status_code == 200

        # Annotator saves marker B (different time)
        resp_b = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=annotator_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704085200.0,
                        "offset_timestamp": 1704088800.0,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )
        assert resp_b.status_code == 200

        # Each user should see their own markers
        get_a = await client.get(f"/api/v1/markers/{file_id}/{analysis_date}", headers=admin_auth_headers)
        get_b = await client.get(f"/api/v1/markers/{file_id}/{analysis_date}", headers=annotator_auth_headers)
        assert get_a.status_code == 200
        assert get_b.status_code == 200
        assert get_a.json()["sleep_markers"][0]["onset_timestamp"] == 1704070800.0
        assert get_b.json()["sleep_markers"][0]["onset_timestamp"] == 1704085200.0


@pytest.mark.asyncio
class TestDeleteMarker:
    """Tests for DELETE /api/v1/markers/{file_id}/{date}/{period_index}."""

    async def test_delete_saved_marker(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should delete a specific marker period."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_del.csv")

        # Save a marker first
        await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704070800.0,
                        "offset_timestamp": 1704096000.0,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )

        # Delete it
        response = await client.delete(
            f"/api/v1/markers/{file_id}/{analysis_date}/1",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["deleted"] is True

    async def test_delete_not_found(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return 404 when deleting non-existent marker."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_del_nf.csv")

        response = await client.delete(
            f"/api/v1/markers/{file_id}/{analysis_date}/999",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404

    async def test_delete_isolated_per_user(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Deleting marker as one scorer should not delete another scorer's marker."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_del_user_iso.csv")

        # Assign file to annotator so they have access
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert assign_resp.status_code == 200

        await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704070800.0,
                        "offset_timestamp": 1704074400.0,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )
        await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=annotator_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704085200.0,
                        "offset_timestamp": 1704088800.0,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )

        # Admin deletes their own period_index=1
        del_resp = await client.delete(
            f"/api/v1/markers/{file_id}/{analysis_date}/1",
            headers=admin_auth_headers,
        )
        assert del_resp.status_code == 200

        get_a = await client.get(f"/api/v1/markers/{file_id}/{analysis_date}", headers=admin_auth_headers)
        get_b = await client.get(f"/api/v1/markers/{file_id}/{analysis_date}", headers=annotator_auth_headers)
        assert get_a.status_code == 200
        assert get_b.status_code == 200
        assert get_a.json()["sleep_markers"] == []
        assert len(get_b.json()["sleep_markers"]) == 1
        assert get_b.json()["sleep_markers"][0]["onset_timestamp"] == 1704085200.0


@pytest.mark.asyncio
class TestOnsetOffsetTable:
    """Tests for GET /api/v1/markers/{file_id}/{date}/table/{period_index}."""

    async def test_table_with_timestamps(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return table data when onset/offset timestamps are provided."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_table.csv")

        # Get activity data to get valid timestamps
        activity_resp = await client.get(
            f"/api/v1/activity/{file_id}/{analysis_date}/score",
            headers=admin_auth_headers,
        )
        timestamps = activity_resp.json()["data"]["timestamps"]
        onset_ts = timestamps[10]
        offset_ts = timestamps[50]

        response = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}/table/1",
            headers=admin_auth_headers,
            params={"onset_ts": onset_ts, "offset_ts": offset_ts, "window_minutes": 10},
        )

        assert response.status_code == 200
        data = response.json()
        assert "onset_data" in data
        assert "offset_data" in data
        assert data["period_index"] == 1

    async def test_table_404_without_timestamps_or_marker(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return 404 when no timestamps and no saved marker."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_table_nf.csv")

        response = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}/table/1",
            headers=admin_auth_headers,
        )

        assert response.status_code == 404


@pytest.mark.asyncio
class TestAdjacentMarkers:
    """Tests for GET /api/v1/markers/{file_id}/{date}/adjacent."""

    async def test_adjacent_empty(self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str):
        """Should return empty adjacent markers when none saved."""
        file_id, analysis_date = await _upload_and_get_date(client, admin_auth_headers, sample_csv_content, "markers_adj.csv")

        response = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}/adjacent",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["previous_day_markers"] == []
        assert data["next_day_markers"] == []


@pytest.mark.asyncio
class TestAutoScore:
    """Tests for auto-score endpoints and persistence behavior."""

    async def test_auto_score_clears_stale_result_when_no_markers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """
        If auto-score produces no markers, any previously saved auto_score result
        for that date should be removed to prevent stale Accept Auto behavior.
        """
        from sleep_scoring_web.db.models import UserAnnotation
        from sleep_scoring_web.schemas.enums import VerificationStatus

        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "markers_auto_score_stale_clear.csv",
        )

        # Use real in-range timestamps from activity data for deterministic saves.
        activity_resp = await client.get(
            f"/api/v1/activity/{file_id}/{analysis_date}/score",
            headers=admin_auth_headers,
        )
        assert activity_resp.status_code == 200
        timestamps = activity_resp.json()["data"]["timestamps"]
        onset_ts = timestamps[10]
        offset_ts = timestamps[50]

        # Seed a stale auto_score result directly in the DB.
        # The auto_score pseudo-user is not a real user with file access,
        # so we insert the UserAnnotation row that the auto-score-result
        # endpoint reads.
        analysis_date_obj = date.fromisoformat(analysis_date)
        async with test_session_maker() as session:
            annotation = UserAnnotation(
                file_id=file_id,
                analysis_date=analysis_date_obj,
                username="auto_score",
                sleep_markers_json=[
                    {
                        "onset_timestamp": onset_ts,
                        "offset_timestamp": offset_ts,
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                nonwear_markers_json=None,
                is_no_sleep=False,
                needs_consensus=False,
                status=VerificationStatus.SUBMITTED,
            )
            session.add(annotation)
            await session.commit()

        # Confirm stale result exists before re-running auto-score.
        pre = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}/auto-score-result",
            headers=admin_auth_headers,
        )
        assert pre.status_code == 200
        assert len(pre.json()["sleep_markers"]) == 1

        # No diary exists in this test setup, so auto-score should return no markers
        # and clear any stale saved auto_score result.
        auto_resp = await client.post(
            f"/api/v1/markers/{file_id}/{analysis_date}/auto-score",
            headers=admin_auth_headers,
        )
        assert auto_resp.status_code == 200
        assert auto_resp.json()["sleep_markers"] == []
        assert auto_resp.json()["nap_markers"] == []

        # Stale saved result should now be gone.
        post = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}/auto-score-result",
            headers=admin_auth_headers,
        )
        assert post.status_code == 404

        # Date status should also reflect no available auto-score to accept.
        status_resp = await client.get(
            f"/api/v1/files/{file_id}/dates/status",
            headers=admin_auth_headers,
        )
        assert status_resp.status_code == 200
        status_row = next((d for d in status_resp.json() if d["date"] == analysis_date), None)
        assert status_row is not None
        assert status_row["has_auto_score"] is False

    async def test_auto_score_batch_skips_incomplete_diary(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Batch auto-score should skip dates with incomplete diary rows."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "markers_auto_score_batch_incomplete.csv",
        )

        # Create incomplete diary: onset present, wake missing.
        diary_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={"lights_out": "23:00"},
        )
        assert diary_resp.status_code == 200

        start_resp = await client.post(
            "/api/v1/markers/auto-score/batch",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "only_missing": False},
        )
        assert start_resp.status_code == 200
        started = start_resp.json()
        assert started["is_running"] is True
        assert started["total_dates"] == 0
        assert started["skipped_incomplete_diary"] >= 1

        # Wait for worker completion.
        final = started
        for _ in range(30):
            status_resp = await client.get(
                "/api/v1/markers/auto-score/batch/status",
                headers=admin_auth_headers,
            )
            assert status_resp.status_code == 200
            final = status_resp.json()
            if not final["is_running"]:
                break
            await asyncio.sleep(0.05)
        assert final["is_running"] is False
        assert final["processed_dates"] == 0

        # No auto-score annotation should be available.
        result_resp = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}/auto-score-result",
            headers=admin_auth_headers,
        )
        assert result_resp.status_code == 404

    async def test_auto_score_batch_processes_complete_diary_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Batch endpoint should process complete-diary dates for selected files."""
        header = "\n".join(
            [
                "------------ Data File Created By ActiGraph -----------",
                "Serial Number: TEST",
                "Start Time 12:00:00",
                "Start Date 1/1/2024",
                "Epoch Period (hh:mm:ss) 00:01:00",
                "Download Time 12:00:00",
                "Download Date 1/2/2024",
                "Current Memory Address: 0",
                "Current Battery Voltage: 4.20     Mode = 12",
                "--------------------------------------------------",
                "Date,Time,Axis1,Axis2,Axis3,Vector Magnitude",
            ]
        )
        rows = [
            f"01/01/2024,{12 + (minute // 60):02d}:{minute % 60:02d}:00,0,0,0,0"
            for minute in range(100)
        ]
        csv_content = "\n".join([header, *rows])

        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            csv_content,
            "markers_auto_score_batch_complete.csv",
        )

        diary_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={"lights_out": "12:10", "wake_time": "13:20"},
        )
        assert diary_resp.status_code == 200

        start_resp = await client.post(
            "/api/v1/markers/auto-score/batch",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "only_missing": False},
        )
        assert start_resp.status_code == 200
        started = start_resp.json()
        assert started["is_running"] is True
        assert started["total_dates"] == 1

        final = started
        for _ in range(40):
            status_resp = await client.get(
                "/api/v1/markers/auto-score/batch/status",
                headers=admin_auth_headers,
            )
            assert status_resp.status_code == 200
            final = status_resp.json()
            if not final["is_running"]:
                break
            await asyncio.sleep(0.05)

        assert final["is_running"] is False
        assert final["processed_dates"] == 1
        assert final["failed_dates"] == 0

    async def test_auto_score_batch_ignores_excluded_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_session_maker,
    ):
        """Batch auto-score should not target files with IGNORE/ISSUE in filename."""
        async with test_session_maker() as session:
            excluded = FileModel(
                filename="P1-4000_T1_ISSUE.csv",
                file_type="csv",
                status="ready",
                uploaded_by="testadmin",
            )
            session.add(excluded)
            await session.commit()
            await session.refresh(excluded)

            session.add(
                DiaryEntry(
                    file_id=excluded.id,
                    analysis_date=date(2024, 1, 1),
                    lights_out="23:00",
                    wake_time="07:00",
                    imported_by="testadmin",
                )
            )
            await session.commit()

        start_resp = await client.post(
            "/api/v1/markers/auto-score/batch",
            headers=admin_auth_headers,
            json={"file_ids": [excluded.id], "only_missing": False},
        )
        assert start_resp.status_code == 200
        started = start_resp.json()
        assert started["total_dates"] == 0
