"""
Integration tests for auto-scoring endpoints in markers_autoscore.py.

Covers single-date auto-score with default and specific algorithms,
error handling for missing activity data and incomplete diary,
access control for annotators, DB persistence of auto-score results,
the auto-score-result retrieval endpoint, auto-nonwear detection,
batch auto-score, and the pipeline discovery endpoint.
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any

import pytest
from httpx import AsyncClient

from tests.web.conftest import upload_and_get_date

API = "/api/v1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_diary_entry(
    client: AsyncClient,
    auth_headers: dict[str, str],
    file_id: int,
    analysis_date: str,
    *,
    lights_out: str = "22:30",
    wake_time: str = "07:00",
    bed_time: str = "22:00",
) -> None:
    """Create a diary entry with complete sleep times for the given file/date."""
    resp = await client.put(
        f"{API}/diary/{file_id}/{analysis_date}",
        headers=auth_headers,
        json={
            "lights_out": lights_out,
            "wake_time": wake_time,
            "bed_time": bed_time,
        },
    )
    assert resp.status_code == 200, f"Failed to create diary entry: {resp.text}"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMarkersAutoscore:
    """Integration tests for auto-scoring endpoints."""

    # 1. Auto-score with default algorithm returns a valid response
    async def test_auto_score_default_algorithm(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """POST auto-score with default algorithm should return 200 with
        sleep_markers, nap_markers, and notes fields."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_default.csv"
        )

        # Create diary entry so auto-score has complete diary
        await _create_diary_entry(client, admin_auth_headers, file_id, date_str)

        resp = await client.post(
            f"{API}/markers/{file_id}/{date_str}/auto-score",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        # Verify response structure and value types
        assert "sleep_markers" in body
        assert "nap_markers" in body
        assert "notes" in body
        assert type(body["sleep_markers"]) is list
        assert type(body["nap_markers"]) is list
        assert type(body["notes"]) is list
        # Every sleep marker must have onset/offset timestamps
        for m in body["sleep_markers"]:
            assert "onset_timestamp" in m
            assert "offset_timestamp" in m
            assert m["offset_timestamp"] > m["onset_timestamp"]

    # 2. Auto-score on a date with no activity data returns a note
    async def test_auto_score_no_activity_data(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Auto-scoring a date with no activity data should return an empty
        marker set and a note explaining the absence."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_nodata.csv"
        )

        # Use a date that has no activity data (far future)
        fake_date = "2099-12-31"
        resp = await client.post(
            f"{API}/markers/{file_id}/{fake_date}/auto-score",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sleep_markers"] == []
        assert body["nap_markers"] == []
        assert len(body["notes"]) > 0
        assert any("no activity data" in n.lower() for n in body["notes"])

    # 3. Auto-score with a specific algorithm parameter
    async def test_auto_score_specific_algorithm(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Passing algorithm=cole_kripke_1992_actilife should use that algorithm."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_cole.csv"
        )

        await _create_diary_entry(client, admin_auth_headers, file_id, date_str)

        resp = await client.post(
            f"{API}/markers/{file_id}/{date_str}/auto-score"
            "?algorithm=cole_kripke_1992_actilife",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "sleep_markers" in body
        assert type(body["sleep_markers"]) is list
        assert "nap_markers" in body
        assert "notes" in body

    # 4. Access control: annotator cannot auto-score unassigned file
    async def test_annotator_cannot_autoscore_unassigned_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """An annotator without file assignment must get 404 on auto-score."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_acl.csv"
        )

        resp = await client.post(
            f"{API}/markers/{file_id}/{date_str}/auto-score",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 404

    # 5. Annotator CAN auto-score an assigned file
    async def test_annotator_can_autoscore_assigned_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """After assignment, the annotator should be able to auto-score."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_assigned.csv"
        )

        # Assign file to annotator
        assign_resp = await client.post(
            f"{API}/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert assign_resp.status_code == 200

        # Create diary so auto-score can run
        await _create_diary_entry(client, admin_auth_headers, file_id, date_str)

        resp = await client.post(
            f"{API}/markers/{file_id}/{date_str}/auto-score",
            headers=annotator_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "sleep_markers" in body

    # 6. Auto-score creates a UserAnnotation in the DB (verified via result endpoint)
    async def test_auto_score_persists_annotation(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Auto-scoring should persist an auto_score UserAnnotation retrievable
        via the auto-score-result endpoint."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_persist.csv"
        )

        await _create_diary_entry(client, admin_auth_headers, file_id, date_str)

        # Run auto-score
        score_resp = await client.post(
            f"{API}/markers/{file_id}/{date_str}/auto-score",
            headers=admin_auth_headers,
        )
        assert score_resp.status_code == 200
        score_body = score_resp.json()

        # If markers were produced, the result endpoint should return them
        has_markers = len(score_body["sleep_markers"]) + len(score_body["nap_markers"]) > 0

        result_resp = await client.get(
            f"{API}/markers/{file_id}/{date_str}/auto-score-result",
            headers=admin_auth_headers,
        )

        if has_markers:
            assert result_resp.status_code == 200
            result_body = result_resp.json()
            assert "sleep_markers" in result_body
            assert result_body["algorithm_used"] is not None
        else:
            # No markers produced, result endpoint returns 404
            assert result_resp.status_code == 404

    # 7. Auto-score-result returns 404 when no auto-score has been run
    async def test_auto_score_result_404_when_none(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """GET auto-score-result should return 404 when no auto-score exists."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_no_result.csv"
        )

        resp = await client.get(
            f"{API}/markers/{file_id}/{date_str}/auto-score-result",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    # 8. Auto-score with incomplete diary returns a note and no markers
    async def test_auto_score_incomplete_diary(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """When include_diary=true (default) and diary is missing or incomplete,
        auto-score should return a note about incomplete diary."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_no_diary.csv"
        )

        # Do NOT create a diary entry -- diary is missing

        resp = await client.post(
            f"{API}/markers/{file_id}/{date_str}/auto-score",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["sleep_markers"] == []
        assert len(body["notes"]) > 0
        assert any("incomplete diary" in n.lower() or "requires" in n.lower() for n in body["notes"])

    # 9. Auto-nonwear endpoint returns valid response
    async def test_auto_nonwear_endpoint(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """POST auto-nonwear should return a valid response with nonwear_markers
        and notes fields."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "autoscore_nonwear.csv"
        )

        resp = await client.post(
            f"{API}/markers/{file_id}/{date_str}/auto-nonwear",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "nonwear_markers" in body
        assert "notes" in body
        assert type(body["nonwear_markers"]) is list
        assert type(body["notes"]) is list
        # Every nonwear marker must have start/end timestamps
        for m in body["nonwear_markers"]:
            assert "start_timestamp" in m
            assert "end_timestamp" in m

    # 10. Batch auto-score status endpoint returns valid response
    async def test_batch_auto_score_status(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """GET auto-score/batch/status should return a valid progress snapshot."""
        resp = await client.get(
            f"{API}/markers/auto-score/batch/status",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "is_running" in body
        assert body["is_running"] is False  # no batch running
        assert "total_dates" in body
        assert body["total_dates"] == 0
        assert "processed_dates" in body
        assert body["processed_dates"] == 0
        assert "scored_dates" in body
        assert body["scored_dates"] == 0
        assert "skipped_existing" in body
        assert body["skipped_existing"] == 0
        assert "failed_dates" in body
        assert body["failed_dates"] == 0
        assert body["errors"] == []
