"""
HTTP integration tests for the analysis summary endpoint.

Tests GET /api/v1/analysis/summary with focus on:
- Empty study baseline
- Scored-date counting (sleep markers, nonwear markers, no-sleep flag)
- Access control (annotator assignment filtering vs admin visibility)
- Multi-file aggregation
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from sleep_scoring_web.db.models import FileAssignment

from tests.web.conftest import upload_and_get_date


@pytest.mark.asyncio
class TestAnalysisSummaryEndpoint:
    """Tests for GET /api/v1/analysis/summary."""

    async def test_empty_study_returns_zeroed_summary(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """With no files uploaded, all counters should be zero and lists empty."""
        resp = await client.get("/api/v1/analysis/summary", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_files"] == 0
        assert data["total_dates"] == 0
        assert data["scored_dates"] == 0
        assert data["files_summary"] == []
        assert data["aggregate_metrics"]["mean_tst_minutes"] is None
        assert data["aggregate_metrics"]["mean_sleep_efficiency"] is None
        assert data["aggregate_metrics"]["mean_waso_minutes"] is None
        assert data["aggregate_metrics"]["mean_sleep_onset_latency"] is None
        assert data["aggregate_metrics"]["total_sleep_periods"] == 0
        assert data["aggregate_metrics"]["total_nap_periods"] == 0

    async def test_file_with_no_markers_has_zero_scored_dates(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """An uploaded file with no markers should have total_dates > 0 but scored_dates == 0."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_no_markers.csv"
        )

        resp = await client.get("/api/v1/analysis/summary", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_files"] >= 1

        our_file = next(
            (f for f in data["files_summary"] if f["file_id"] == file_id), None
        )
        assert our_file is not None
        assert our_file["filename"] == "summary_no_markers.csv"
        assert our_file["total_dates"] > 0
        assert our_file["scored_dates"] == 0
        assert our_file["has_diary"] is False

    async def test_file_with_sleep_markers_increments_scored_dates(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Saving sleep markers for a date should increase scored_dates for that file."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_with_markers.csv"
        )

        # Save a sleep marker on the first date
        save_resp = await client.put(
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
        assert save_resp.status_code == 200

        resp = await client.get("/api/v1/analysis/summary", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        our_file = next(
            (f for f in data["files_summary"] if f["file_id"] == file_id), None
        )
        assert our_file is not None
        assert our_file["scored_dates"] >= 1

    async def test_annotator_sees_only_assigned_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Annotator should only see files they are assigned to in the summary."""
        # Upload two files as admin
        file_id_assigned, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_assigned.csv"
        )
        file_id_unassigned, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_unassigned.csv"
        )

        # Assign only one file to the annotator
        async with test_session_maker() as session:
            session.add(FileAssignment(
                file_id=file_id_assigned,
                username="testannotator",
                assigned_by="testadmin",
            ))
            await session.commit()

        resp = await client.get(
            "/api/v1/analysis/summary", headers=annotator_auth_headers
        )

        assert resp.status_code == 200
        data = resp.json()
        file_ids_in_summary = [f["file_id"] for f in data["files_summary"]]
        assert file_id_assigned in file_ids_in_summary
        assert file_id_unassigned not in file_ids_in_summary
        assert data["total_files"] == 1

    async def test_admin_sees_all_files(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Admin should see all uploaded files regardless of assignment."""
        file_id_a, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_admin_a.csv"
        )
        file_id_b, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_admin_b.csv"
        )

        resp = await client.get("/api/v1/analysis/summary", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        file_ids_in_summary = [f["file_id"] for f in data["files_summary"]]
        assert file_id_a in file_ids_in_summary
        assert file_id_b in file_ids_in_summary
        assert data["total_files"] >= 2

    async def test_multiple_files_aggregate_correctly(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Totals across multiple files should aggregate correctly."""
        file_id_1, date_1 = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_multi_1.csv"
        )
        file_id_2, date_2 = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_multi_2.csv"
        )

        # Score a date on each file
        for fid, dt in [(file_id_1, date_1), (file_id_2, date_2)]:
            save_resp = await client.put(
                f"/api/v1/markers/{fid}/{dt}",
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
            assert save_resp.status_code == 200

        resp = await client.get("/api/v1/analysis/summary", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()

        # Both files should be present
        summary_ids = [f["file_id"] for f in data["files_summary"]]
        assert file_id_1 in summary_ids
        assert file_id_2 in summary_ids

        # total_dates should be the sum across both files
        file_1_summary = next(f for f in data["files_summary"] if f["file_id"] == file_id_1)
        file_2_summary = next(f for f in data["files_summary"] if f["file_id"] == file_id_2)
        expected_total_dates = file_1_summary["total_dates"] + file_2_summary["total_dates"]
        assert data["total_dates"] >= expected_total_dates

        # scored_dates should be the sum of per-file scored_dates
        expected_scored = file_1_summary["scored_dates"] + file_2_summary["scored_dates"]
        assert data["scored_dates"] >= expected_scored
        assert expected_scored >= 2  # at least 1 scored per file

    async def test_no_sleep_dates_count_as_scored(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """A date flagged as no-sleep (is_no_sleep=True) should count as scored."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "summary_no_sleep.csv"
        )

        # Verify scored_dates is 0 before marking no-sleep
        resp_before = await client.get(
            "/api/v1/analysis/summary", headers=admin_auth_headers
        )
        assert resp_before.status_code == 200
        file_before = next(
            (f for f in resp_before.json()["files_summary"] if f["file_id"] == file_id),
            None,
        )
        assert file_before is not None
        scored_before = file_before["scored_dates"]

        # Mark the date as no-sleep (save with is_no_sleep=True, no markers)
        save_resp = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [],
                "nonwear_markers": [],
                "is_no_sleep": True,
            },
        )
        assert save_resp.status_code == 200

        resp_after = await client.get(
            "/api/v1/analysis/summary", headers=admin_auth_headers
        )
        assert resp_after.status_code == 200
        file_after = next(
            (f for f in resp_after.json()["files_summary"] if f["file_id"] == file_id),
            None,
        )
        assert file_after is not None
        assert file_after["scored_dates"] > scored_before
