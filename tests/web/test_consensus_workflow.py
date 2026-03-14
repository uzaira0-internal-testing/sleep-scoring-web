"""
End-to-end consensus workflow tests.

Validates the full lifecycle: overview, ballot creation from submitted
annotations, voting, vote-changing, admin resolution, and access control.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from sleep_scoring_web.db.models import UserAnnotation
from sleep_scoring_web.schemas.enums import VerificationStatus

from tests.web.conftest import upload_and_get_date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _save_markers_with_status(
    client: AsyncClient,
    auth_headers: dict[str, str],
    file_id: int,
    analysis_date: str,
    *,
    sleep_markers: list[dict[str, Any]] | None = None,
    nonwear_markers: list[dict[str, Any]] | None = None,
    needs_consensus: bool = False,
) -> dict[str, Any]:
    """
    Save markers via PUT /api/v1/markers/{file_id}/{date}.

    The ``upsert_user_annotation`` helper always sets
    ``status = VerificationStatus.SUBMITTED``, so saved annotations
    immediately qualify as consensus candidates.
    """
    if sleep_markers is None:
        sleep_markers = [
            {
                "onset_timestamp": 1704070800.0,
                "offset_timestamp": 1704074400.0,
                "marker_index": 1,
                "marker_type": "MAIN_SLEEP",
            }
        ]
    body: dict[str, Any] = {
        "sleep_markers": sleep_markers,
        "nonwear_markers": nonwear_markers or [],
        "is_no_sleep": False,
        "needs_consensus": needs_consensus,
    }
    resp = await client.put(
        f"/api/v1/markers/{file_id}/{analysis_date}",
        headers=auth_headers,
        json=body,
    )
    assert resp.status_code == 200, f"Marker save failed: {resp.text}"
    return resp.json()


async def _create_submitted_annotation(
    session_maker: async_sessionmaker[AsyncSession],
    file_id: int,
    username: str,
    analysis_date: str,
    *,
    sleep_markers: list[dict[str, Any]] | None = None,
) -> None:
    """Directly insert a ``UserAnnotation`` with status=submitted."""
    from datetime import datetime

    async with session_maker() as session:
        annotation = UserAnnotation(
            file_id=file_id,
            analysis_date=datetime.strptime(analysis_date, "%Y-%m-%d").date(),
            username=username,
            sleep_markers_json=sleep_markers
            or [
                {
                    "onset_timestamp": 1000,
                    "offset_timestamp": 2000,
                    "marker_type": "MAIN_SLEEP",
                }
            ],
            nonwear_markers_json=[],
            is_no_sleep=False,
            algorithm_used="sadeh_1994_actilife",
            status=VerificationStatus.SUBMITTED,
        )
        session.add(annotation)
        await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConsensusWorkflow:
    """Full consensus workflow integration tests."""

    # 1. Overview empty when no annotations submitted
    async def test_overview_empty_when_no_annotations(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Overview should return zero items when there are no submitted annotations."""
        resp = await client.get("/api/v1/consensus/overview", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total_dates_with_multiple"] == 0
        assert data["items"] == []

    # 2. Two users save markers and submit -> ballot shows candidates
    async def test_two_users_submit_ballot_shows_candidates(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """
        When two users save markers (creating submitted annotations),
        the ballot endpoint should list both as candidates.
        """
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "workflow_ballot_candidates.csv"
        )

        # Admin saves markers (creates submitted annotation + candidate)
        await _save_markers_with_status(
            client,
            admin_auth_headers,
            file_id,
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1704070800.0,
                    "offset_timestamp": 1704074400.0,
                    "marker_index": 1,
                    "marker_type": "MAIN_SLEEP",
                }
            ],
        )

        # Assign annotator to the file so they can save markers
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [file_id], "username": "testannotator"},
            headers=admin_auth_headers,
        )
        assert assign_resp.status_code == 200

        # Annotator saves different markers
        await _save_markers_with_status(
            client,
            annotator_auth_headers,
            file_id,
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1704072000.0,
                    "offset_timestamp": 1704076000.0,
                    "marker_index": 1,
                    "marker_type": "MAIN_SLEEP",
                }
            ],
        )

        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert ballot_resp.status_code == 200
        ballot = ballot_resp.json()

        assert len(ballot["candidates"]) == 2
        assert ballot["total_votes"] == 0
        assert ballot["my_vote_candidate_id"] is None
        # All candidates come from users
        assert all(c["source_type"] == "user" for c in ballot["candidates"])

    # 3. Vote casting: user votes for a candidate, ballot reflects vote
    async def test_vote_casting_reflects_in_ballot(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
        test_session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Casting a vote should be reflected in the ballot response."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "workflow_vote_cast.csv"
        )

        await _create_submitted_annotation(
            test_session_maker,
            file_id,
            "user_a",
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1000,
                    "offset_timestamp": 2000,
                    "marker_type": "MAIN_SLEEP",
                    "marker_index": 1,
                }
            ],
        )
        await _create_submitted_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1500,
                    "offset_timestamp": 2500,
                    "marker_type": "MAIN_SLEEP",
                    "marker_index": 1,
                }
            ],
        )

        # Get ballot to discover candidate IDs
        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert ballot_resp.status_code == 200
        candidates = ballot_resp.json()["candidates"]
        assert len(candidates) == 2
        target_id = candidates[0]["candidate_id"]

        # Cast vote
        vote_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=admin_auth_headers,
            json={"candidate_id": target_id},
        )
        assert vote_resp.status_code == 200
        vote_data = vote_resp.json()

        assert vote_data["my_vote_candidate_id"] == target_id
        assert vote_data["total_votes"] == 1

        voted_candidate = next(
            c for c in vote_data["candidates"] if c["candidate_id"] == target_id
        )
        assert voted_candidate["vote_count"] == 1
        assert voted_candidate["selected_by_me"] is True

    # 4. Vote changing: user changes vote, old vote removed
    async def test_vote_changing_removes_old_vote(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
        test_session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Changing a vote should remove the old vote and apply the new one."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "workflow_vote_change.csv"
        )

        await _create_submitted_annotation(
            test_session_maker,
            file_id,
            "user_a",
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1000,
                    "offset_timestamp": 2000,
                    "marker_type": "MAIN_SLEEP",
                    "marker_index": 1,
                }
            ],
        )
        await _create_submitted_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1500,
                    "offset_timestamp": 2500,
                    "marker_type": "MAIN_SLEEP",
                    "marker_index": 1,
                }
            ],
        )

        # Get candidates
        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        candidates = ballot_resp.json()["candidates"]
        first_id = candidates[0]["candidate_id"]
        second_id = candidates[1]["candidate_id"]

        # Vote for first candidate
        await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=admin_auth_headers,
            json={"candidate_id": first_id},
        )

        # Change vote to second candidate
        change_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=admin_auth_headers,
            json={"candidate_id": second_id},
        )
        assert change_resp.status_code == 200
        data = change_resp.json()

        assert data["my_vote_candidate_id"] == second_id
        assert data["total_votes"] == 1

        first_after = next(c for c in data["candidates"] if c["candidate_id"] == first_id)
        second_after = next(c for c in data["candidates"] if c["candidate_id"] == second_id)
        assert first_after["vote_count"] == 0
        assert second_after["vote_count"] == 1

    # 5. Admin resolve: admin creates resolution, resolve endpoint returns resolved data
    async def test_admin_resolve_creates_resolution(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
        test_session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Admin should be able to resolve consensus, and the resolution should be retrievable."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "workflow_resolve.csv"
        )

        await _create_submitted_annotation(test_session_maker, file_id, "user_a", analysis_date)
        await _create_submitted_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1100,
                    "offset_timestamp": 2100,
                    "marker_type": "MAIN_SLEEP",
                }
            ],
        )

        final_sleep = [{"onset_timestamp": 1050, "offset_timestamp": 2050, "marker_type": "MAIN_SLEEP"}]
        resolve_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/resolve",
            headers=admin_auth_headers,
            json={
                "final_sleep_markers_json": final_sleep,
                "final_nonwear_markers_json": [],
                "resolution_notes": "Merged onsets from both scorers",
            },
        )
        assert resolve_resp.status_code == 200
        resolved = resolve_resp.json()

        assert resolved["resolved_by"] == "testadmin"
        assert resolved["resolution_notes"] == "Merged onsets from both scorers"
        assert resolved["final_sleep_markers_json"] == final_sleep
        assert resolved["final_nonwear_markers_json"] == []
        assert resolved["resolved_at"] is not None

        # Verify via the GET consensus endpoint
        consensus_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert consensus_resp.status_code == 200
        consensus_data = consensus_resp.json()
        assert consensus_data["has_resolution"] is True
        assert consensus_data["resolution"]["resolved_by"] == "testadmin"

    # 6. Non-admin 403: annotator tries to resolve -> 403
    async def test_non_admin_resolve_returns_403(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
        test_session_maker: async_sessionmaker[AsyncSession],
    ) -> None:
        """Annotator should receive 403 when attempting to resolve consensus."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "workflow_403.csv"
        )

        await _create_submitted_annotation(test_session_maker, file_id, "user_a", analysis_date)
        await _create_submitted_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1100,
                    "offset_timestamp": 2100,
                    "marker_type": "MAIN_SLEEP",
                }
            ],
        )

        # Assign annotator to the file so they pass the access check
        # and receive 403 (admin-only) instead of 404 (no access)
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [file_id], "username": "testannotator"},
            headers=admin_auth_headers,
        )
        assert assign_resp.status_code == 200

        resolve_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/resolve",
            headers=annotator_auth_headers,
            json={
                "final_sleep_markers_json": [],
                "final_nonwear_markers_json": [],
                "resolution_notes": "Annotator attempt",
            },
        )
        assert resolve_resp.status_code == 403

    # 7. needs_consensus flag: save markers with needs_consensus=true, verify in response
    async def test_needs_consensus_flag_persists(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """
        Saving markers with ``needs_consensus=true`` should persist the flag
        so that a subsequent GET returns ``needs_consensus=true``.
        """
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "workflow_needs_consensus.csv"
        )

        await _save_markers_with_status(
            client,
            admin_auth_headers,
            file_id,
            analysis_date,
            needs_consensus=True,
        )

        # Fetch markers and check the flag
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["needs_consensus"] is True

    # 8. Overview shows dates needing review after 2+ submissions
    async def test_overview_shows_dates_after_two_submissions(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """
        After two different users save markers (auto-submitted), the overview
        endpoint should list that file/date as needing consensus review.
        """
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "workflow_overview_2_subs.csv"
        )

        # First user saves
        await _save_markers_with_status(
            client,
            admin_auth_headers,
            file_id,
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1704070800.0,
                    "offset_timestamp": 1704074400.0,
                    "marker_index": 1,
                    "marker_type": "MAIN_SLEEP",
                }
            ],
        )

        # Assign annotator to the file so they can save markers
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            json={"file_ids": [file_id], "username": "testannotator"},
            headers=admin_auth_headers,
        )
        assert assign_resp.status_code == 200

        # Second user saves different markers
        await _save_markers_with_status(
            client,
            annotator_auth_headers,
            file_id,
            analysis_date,
            sleep_markers=[
                {
                    "onset_timestamp": 1704072000.0,
                    "offset_timestamp": 1704076000.0,
                    "marker_index": 1,
                    "marker_type": "MAIN_SLEEP",
                }
            ],
        )

        overview_resp = await client.get(
            "/api/v1/consensus/overview",
            headers=admin_auth_headers,
        )
        assert overview_resp.status_code == 200
        overview = overview_resp.json()

        assert overview["total_dates_with_multiple"] >= 1

        matching_items = [
            item
            for item in overview["items"]
            if item["file_id"] == file_id and item["analysis_date"] == analysis_date
        ]
        assert len(matching_items) == 1
        item = matching_items[0]
        assert item["annotation_count"] == 2
        assert set(item["usernames"]) == {"testadmin", "testannotator"}
