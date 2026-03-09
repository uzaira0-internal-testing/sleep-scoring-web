"""
HTTP integration tests for the consensus API endpoints (Phase 8).

Tests multi-user annotation comparison and admin resolution.
Validates that resolution stores separately and does NOT overwrite main markers.
"""

import asyncio
import io

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketDisconnect

from sleep_scoring_web.config import get_settings
from sleep_scoring_web.main import app

async def _upload_file(client: AsyncClient, headers: dict, content: str, filename: str) -> int:
    """Upload a CSV file and return its file_id."""
    files = {"file": (filename, io.BytesIO(content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", headers=headers, files=files)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["file_id"]


async def _upload_and_get_date(
    client: AsyncClient,
    headers: dict,
    content: str,
    filename: str,
) -> tuple[int, str]:
    """Upload a CSV file and return (file_id, first analysis date)."""
    file_id = await _upload_file(client, headers, content, filename)
    dates_resp = await client.get(f"/api/v1/files/{file_id}/dates", headers=headers)
    assert dates_resp.status_code == 200
    dates = dates_resp.json()
    assert len(dates) >= 1
    return file_id, dates[0]


async def _create_annotation(
    session_maker,
    file_id: int,
    username: str,
    analysis_date: str,
    sleep_markers: list | None = None,
    status: str = "submitted",
) -> None:
    """Directly insert a UserAnnotation for testing."""
    from datetime import datetime

    from sleep_scoring_web.db.models import UserAnnotation

    async with session_maker() as session:
        annotation = UserAnnotation(
            file_id=file_id,
            analysis_date=datetime.strptime(analysis_date, "%Y-%m-%d").date(),
            username=username,
            sleep_markers_json=sleep_markers or [{"onset_timestamp": 1000, "offset_timestamp": 2000, "marker_type": "MAIN_SLEEP"}],
            nonwear_markers_json=[],
            is_no_sleep=False,
            algorithm_used="sadeh_1994_actilife",
            status=status,
        )
        session.add(annotation)
        await session.commit()


async def _save_markers(
    client: AsyncClient, headers: dict, file_id: int, analysis_date: str
) -> None:
    """Save markers via the markers API to populate the main Marker table."""
    await client.put(
        f"/api/v1/markers/{file_id}/{analysis_date}",
        headers=headers,
        json={
            "sleep_markers": [
                {"onset_timestamp": 1000, "offset_timestamp": 2000, "marker_index": 1, "marker_type": "MAIN_SLEEP"},
            ],
            "nonwear_markers": [],
            "is_no_sleep": False,
        },
    )


def _consensus_ws_url(file_id: int, analysis_date: str, username: str = "testadmin", site_password: str = "testpass") -> str:
    """Build websocket URL for consensus stream."""
    return (
        f"/api/v1/consensus/stream?file_id={file_id}"
        f"&analysis_date={analysis_date}&username={username}&site_password={site_password}"
    )


@pytest.mark.asyncio
class TestConsensusOverview:
    """Tests for GET /api/v1/consensus/overview."""

    async def test_empty_overview(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return empty overview when no annotations exist."""
        response = await client.get(
            "/api/v1/consensus/overview",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_dates_with_multiple"] == 0
        assert data["items"] == []

    async def test_overview_shows_dates_with_multiple_annotations(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Should list dates where 2+ users have submitted annotations."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "consensus_ov.csv")

        # Create two submitted annotations
        await _create_annotation(test_session_maker, file_id, "user_a", "2024-01-01", status="submitted")
        await _create_annotation(test_session_maker, file_id, "user_b", "2024-01-01", status="submitted")

        response = await client.get(
            "/api/v1/consensus/overview",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total_dates_with_multiple"] == 1
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["file_id"] == file_id
        assert item["annotation_count"] == 2
        assert set(item["usernames"]) == {"user_a", "user_b"}

    async def test_overview_ignores_single_annotations(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Should not list dates with only one annotation."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "consensus_single.csv")

        await _create_annotation(test_session_maker, file_id, "user_a", "2024-01-01", status="submitted")

        response = await client.get(
            "/api/v1/consensus/overview",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["total_dates_with_multiple"] == 0

    async def test_overview_ignores_draft_annotations(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Should not count draft annotations toward consensus."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "consensus_draft.csv")

        await _create_annotation(test_session_maker, file_id, "user_a", "2024-01-01", status="submitted")
        await _create_annotation(test_session_maker, file_id, "user_b", "2024-01-01", status="draft")

        response = await client.get(
            "/api/v1/consensus/overview",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        assert response.json()["total_dates_with_multiple"] == 0


@pytest.mark.asyncio
class TestConsensusForDate:
    """Tests for GET /api/v1/consensus/{file_id}/{date}."""

    async def test_get_annotations_for_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Should return all annotations for a specific file/date."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "consensus_get.csv")

        await _create_annotation(test_session_maker, file_id, "user_a", "2024-01-01")
        await _create_annotation(
            test_session_maker,
            file_id,
            "user_b",
            "2024-01-01",
            sleep_markers=[{"onset_timestamp": 1100, "offset_timestamp": 2100, "marker_type": "MAIN_SLEEP"}],
        )

        response = await client.get(
            f"/api/v1/consensus/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["annotations"]) == 2
        assert data["has_resolution"] is False
        usernames = {a["username"] for a in data["annotations"]}
        assert usernames == {"user_a", "user_b"}


@pytest.mark.asyncio
class TestConsensusBallotVoting:
    """Tests for ballot candidate listing and vote semantics."""

    async def test_ballot_backfills_candidates_from_submitted_annotations(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Legacy submitted annotations should appear as ballot candidates."""
        from datetime import datetime

        from sleep_scoring_web.db.models import ConsensusCandidate

        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ballot_backfill.csv",
        )

        await _create_annotation(
            test_session_maker,
            file_id,
            "user_a",
            analysis_date,
            sleep_markers=[{"onset_timestamp": 1000, "offset_timestamp": 2000, "marker_type": "MAIN_SLEEP", "marker_index": 1}],
            status="submitted",
        )
        await _create_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[{"onset_timestamp": 1200, "offset_timestamp": 2200, "marker_type": "MAIN_SLEEP", "marker_index": 1}],
            status="submitted",
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
        assert set(c["source_type"] for c in ballot["candidates"]) == {"user"}

        analysis_dt = datetime.strptime(analysis_date, "%Y-%m-%d").date()
        async with test_session_maker() as session:
            db_rows = await session.execute(
                select(ConsensusCandidate).where(
                    ConsensusCandidate.file_id == file_id,
                    ConsensusCandidate.analysis_date == analysis_dt,
                )
            )
            assert len(db_rows.scalars().all()) == 2

    async def test_vote_cast_replace_and_clear(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """A voter should be able to cast, replace, and clear exactly one vote."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_vote_replace_clear.csv",
        )

        await _create_annotation(
            test_session_maker,
            file_id,
            "user_a",
            analysis_date,
            sleep_markers=[{"onset_timestamp": 1000, "offset_timestamp": 2000, "marker_type": "MAIN_SLEEP", "marker_index": 1}],
            status="submitted",
        )
        await _create_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[{"onset_timestamp": 1300, "offset_timestamp": 2300, "marker_type": "MAIN_SLEEP", "marker_index": 1}],
            status="submitted",
        )

        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=annotator_auth_headers,
        )
        assert ballot_resp.status_code == 200
        candidates = ballot_resp.json()["candidates"]
        assert len(candidates) == 2
        first_candidate_id = candidates[0]["candidate_id"]
        second_candidate_id = candidates[1]["candidate_id"]

        vote_one_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=annotator_auth_headers,
            json={"candidate_id": first_candidate_id},
        )
        assert vote_one_resp.status_code == 200
        vote_one = vote_one_resp.json()
        assert vote_one["my_vote_candidate_id"] == first_candidate_id
        assert vote_one["total_votes"] == 1
        first_vote = next(c for c in vote_one["candidates"] if c["candidate_id"] == first_candidate_id)
        assert first_vote["vote_count"] == 1

        vote_two_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=annotator_auth_headers,
            json={"candidate_id": second_candidate_id},
        )
        assert vote_two_resp.status_code == 200
        vote_two = vote_two_resp.json()
        assert vote_two["my_vote_candidate_id"] == second_candidate_id
        assert vote_two["total_votes"] == 1
        first_vote_after_replace = next(c for c in vote_two["candidates"] if c["candidate_id"] == first_candidate_id)
        second_vote_after_replace = next(c for c in vote_two["candidates"] if c["candidate_id"] == second_candidate_id)
        assert first_vote_after_replace["vote_count"] == 0
        assert second_vote_after_replace["vote_count"] == 1

        clear_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=annotator_auth_headers,
            json={"candidate_id": None},
        )
        assert clear_resp.status_code == 200
        cleared = clear_resp.json()
        assert cleared["my_vote_candidate_id"] is None
        assert cleared["total_votes"] == 0
        assert all(c["vote_count"] == 0 for c in cleared["candidates"])

    async def test_auto_score_candidate_is_voteable_and_aggregates_votes(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """
        Auto-score should appear as a separate candidate source and be voteable
        by users who did not place any markers.
        """
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_auto_candidate_vote.csv",
        )

        activity_resp = await client.get(
            f"/api/v1/activity/{file_id}/{analysis_date}/score",
            headers=admin_auth_headers,
        )
        assert activity_resp.status_code == 200
        timestamps = activity_resp.json()["data"]["timestamps"]

        # Human candidate
        human_save_resp = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": timestamps[10],
                        "offset_timestamp": timestamps[30],
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )
        assert human_save_resp.status_code == 200

        # Auto-score pseudo-user candidate
        auto_headers = {**admin_auth_headers, "X-Username": "auto_score"}
        auto_save_resp = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=auto_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": timestamps[40],
                        "offset_timestamp": timestamps[70],
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )
        assert auto_save_resp.status_code == 200

        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=annotator_auth_headers,
        )
        assert ballot_resp.status_code == 200
        ballot = ballot_resp.json()
        assert len(ballot["candidates"]) >= 2

        auto_candidates = [c for c in ballot["candidates"] if c["source_type"] == "auto"]
        assert len(auto_candidates) == 1
        auto_candidate_id = auto_candidates[0]["candidate_id"]

        # Annotator votes for auto candidate without placing own markers.
        annotator_vote_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=annotator_auth_headers,
            json={"candidate_id": auto_candidate_id},
        )
        assert annotator_vote_resp.status_code == 200
        assert annotator_vote_resp.json()["my_vote_candidate_id"] == auto_candidate_id

        # Admin also votes for the same candidate.
        admin_vote_resp = await client.post(
            f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
            headers=admin_auth_headers,
            json={"candidate_id": auto_candidate_id},
        )
        assert admin_vote_resp.status_code == 200

        after_votes_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=annotator_auth_headers,
        )
        assert after_votes_resp.status_code == 200
        after_votes = after_votes_resp.json()
        auto_after_votes = next(c for c in after_votes["candidates"] if c["candidate_id"] == auto_candidate_id)
        assert auto_after_votes["vote_count"] == 2
        assert after_votes["total_votes"] == 2

    async def test_websocket_stream_pushes_vote_update(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """
        Websocket stream should push a consensus_update event when a vote changes.
        """
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ws_vote_push.csv",
        )

        activity_resp = await client.get(
            f"/api/v1/activity/{file_id}/{analysis_date}/score",
            headers=admin_auth_headers,
        )
        assert activity_resp.status_code == 200
        timestamps = activity_resp.json()["data"]["timestamps"]

        # Seed a candidate set to vote on.
        save_resp = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": timestamps[10],
                        "offset_timestamp": timestamps[30],
                        "marker_index": 1,
                        "marker_type": "MAIN_SLEEP",
                    }
                ],
                "nonwear_markers": [],
            },
        )
        assert save_resp.status_code == 200

        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert ballot_resp.status_code == 200
        candidate_id = ballot_resp.json()["candidates"][0]["candidate_id"]

        ws_url = (
            f"/api/v1/consensus/stream?file_id={file_id}"
            f"&analysis_date={analysis_date}&username=testadmin&site_password=testpass"
        )

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(ws_url) as ws:
                connected = ws.receive_json()
                assert connected["type"] == "consensus_connected"
                assert connected["file_id"] == file_id
                assert connected["analysis_date"] == analysis_date

                vote_resp = await client.post(
                    f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
                    headers=admin_auth_headers,
                    json={"candidate_id": candidate_id},
                )
                assert vote_resp.status_code == 200

                pushed = ws.receive_json()
                assert pushed["type"] == "consensus_update"
                assert pushed["event"] == "vote_changed"
                assert pushed["file_id"] == file_id
                assert pushed["analysis_date"] == analysis_date
                assert pushed["candidate_id"] == candidate_id

    async def test_websocket_stream_fanout_to_multiple_clients(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """A single vote update should be pushed to all subscribers on the same topic."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ws_fanout.csv",
        )

        await _save_markers(client, admin_auth_headers, file_id, analysis_date)
        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert ballot_resp.status_code == 200
        candidate_id = ballot_resp.json()["candidates"][0]["candidate_id"]

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(_consensus_ws_url(file_id, analysis_date, "testadmin")) as ws_a:
                with sync_client.websocket_connect(_consensus_ws_url(file_id, analysis_date, "testannotator")) as ws_b:
                    assert ws_a.receive_json()["type"] == "consensus_connected"
                    assert ws_b.receive_json()["type"] == "consensus_connected"

                    vote_resp = await client.post(
                        f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
                        headers=admin_auth_headers,
                        json={"candidate_id": candidate_id},
                    )
                    assert vote_resp.status_code == 200

                    pushed_a = ws_a.receive_json()
                    pushed_b = ws_b.receive_json()
                    assert pushed_a["type"] == "consensus_update"
                    assert pushed_b["type"] == "consensus_update"
                    assert pushed_a["event"] == "vote_changed"
                    assert pushed_b["event"] == "vote_changed"
                    assert pushed_a["candidate_id"] == candidate_id
                    assert pushed_b["candidate_id"] == candidate_id

    async def test_websocket_stream_rejects_invalid_password(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        ):
        """Invalid site password should be rejected during websocket handshake."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ws_bad_password.csv",
        )
        settings = get_settings()
        original_site_password = settings.SITE_PASSWORD
        settings.SITE_PASSWORD = "testpass"

        try:
            bad_url = _consensus_ws_url(file_id, analysis_date, site_password="wrong-pass")
            with TestClient(app) as sync_client:
                with pytest.raises(WebSocketDisconnect) as exc:
                    with sync_client.websocket_connect(bad_url):
                        pass
                assert exc.value.code == 1008
        finally:
            settings.SITE_PASSWORD = original_site_password

    async def test_websocket_stream_rejects_missing_required_params(self):
        """Missing file/date params should be rejected."""
        with TestClient(app) as sync_client:
            with pytest.raises(WebSocketDisconnect) as exc:
                with sync_client.websocket_connect("/api/v1/consensus/stream?site_password=testpass&username=testadmin"):
                    pass
            assert exc.value.code == 1008

    async def test_websocket_stream_emits_candidate_updated_on_save(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Saving markers should emit candidate_updated."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ws_candidate_updated.csv",
        )

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(_consensus_ws_url(file_id, analysis_date)) as ws:
                assert ws.receive_json()["type"] == "consensus_connected"

                save_resp = await client.put(
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
                assert save_resp.status_code == 200

                pushed = ws.receive_json()
                assert pushed["type"] == "consensus_update"
                assert pushed["event"] == "candidate_updated"
                assert pushed["file_id"] == file_id
                assert pushed["analysis_date"] == analysis_date

    async def test_websocket_stream_emits_auto_score_updated(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Auto-score with markers should emit auto_score_updated."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ws_auto_updated.csv",
        )

        def fake_run_auto_scoring(**_: object) -> dict[str, object]:
            return {
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704070800.0,
                        "offset_timestamp": 1704074400.0,
                        "marker_type": "MAIN_SLEEP",
                        "marker_index": 1,
                    }
                ],
                "nap_markers": [],
                "notes": ["mock auto"],
            }

        monkeypatch.setattr("sleep_scoring_web.services.marker_placement.run_auto_scoring", fake_run_auto_scoring)

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(_consensus_ws_url(file_id, analysis_date)) as ws:
                assert ws.receive_json()["type"] == "consensus_connected"

                auto_resp = await client.post(
                    f"/api/v1/markers/{file_id}/{analysis_date}/auto-score",
                    headers=admin_auth_headers,
                )
                assert auto_resp.status_code == 200
                assert len(auto_resp.json()["sleep_markers"]) == 1

                pushed = ws.receive_json()
                assert pushed["type"] == "consensus_update"
                assert pushed["event"] == "auto_score_updated"
                assert pushed["username"] == "auto_score"

    async def test_websocket_stream_emits_auto_score_cleared(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Auto-score with no markers should emit auto_score_cleared when stale auto exists."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ws_auto_cleared.csv",
        )

        # Seed stale auto_score annotation.
        auto_headers = {**admin_auth_headers, "X-Username": "auto_score"}
        seed_resp = await client.put(
            f"/api/v1/markers/{file_id}/{analysis_date}",
            headers=auto_headers,
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
        assert seed_resp.status_code == 200

        def fake_run_auto_scoring(**_: object) -> dict[str, object]:
            return {"sleep_markers": [], "nap_markers": [], "notes": ["none"]}

        monkeypatch.setattr("sleep_scoring_web.services.marker_placement.run_auto_scoring", fake_run_auto_scoring)

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(_consensus_ws_url(file_id, analysis_date)) as ws:
                assert ws.receive_json()["type"] == "consensus_connected"

                auto_resp = await client.post(
                    f"/api/v1/markers/{file_id}/{analysis_date}/auto-score",
                    headers=admin_auth_headers,
                )
                assert auto_resp.status_code == 200

                pushed = ws.receive_json()
                assert pushed["type"] == "consensus_update"
                assert pushed["event"] == "auto_score_cleared"
                assert pushed["username"] == "auto_score"

    async def test_websocket_stream_emits_consensus_resolved(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Resolving consensus should emit consensus_resolved."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_ws_resolved.csv",
        )
        await _create_annotation(test_session_maker, file_id, "user_a", analysis_date)
        await _create_annotation(test_session_maker, file_id, "user_b", analysis_date)

        with TestClient(app) as sync_client:
            with sync_client.websocket_connect(_consensus_ws_url(file_id, analysis_date)) as ws:
                assert ws.receive_json()["type"] == "consensus_connected"

                resolve_resp = await client.post(
                    f"/api/v1/consensus/{file_id}/{analysis_date}/resolve",
                    headers=admin_auth_headers,
                    json={
                        "final_sleep_markers_json": [{"onset_timestamp": 1000, "offset_timestamp": 2000}],
                        "final_nonwear_markers_json": [],
                    },
                )
                assert resolve_resp.status_code == 200

                pushed = ws.receive_json()
                assert pushed["type"] == "consensus_update"
                assert pushed["event"] == "consensus_resolved"
                assert pushed["username"] == "testadmin"

    async def test_concurrent_votes_same_user_ends_with_one_active_vote(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """
        Concurrent vote writes for the same user should still yield one active vote.
        """
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_concurrent_same_user.csv",
        )
        await _create_annotation(test_session_maker, file_id, "user_a", analysis_date)
        await _create_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[{"onset_timestamp": 1100, "offset_timestamp": 2100, "marker_type": "MAIN_SLEEP"}],
        )

        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert ballot_resp.status_code == 200
        candidates = ballot_resp.json()["candidates"]
        c1 = candidates[0]["candidate_id"]
        c2 = candidates[1]["candidate_id"]

        await asyncio.gather(
            client.post(
                f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
                headers=admin_auth_headers,
                json={"candidate_id": c1},
            ),
            client.post(
                f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
                headers=admin_auth_headers,
                json={"candidate_id": c2},
            ),
        )

        final_ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert final_ballot_resp.status_code == 200
        final_ballot = final_ballot_resp.json()
        assert final_ballot["my_vote_candidate_id"] in {c1, c2}
        assert final_ballot["total_votes"] == 1
        assert sum(c["vote_count"] for c in final_ballot["candidates"]) == 1

    async def test_concurrent_votes_different_users_aggregate_correctly(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Concurrent votes from different users should aggregate to two total votes."""
        file_id, analysis_date = await _upload_and_get_date(
            client,
            admin_auth_headers,
            sample_csv_content,
            "consensus_concurrent_multi_user.csv",
        )
        await _create_annotation(test_session_maker, file_id, "user_a", analysis_date)
        await _create_annotation(
            test_session_maker,
            file_id,
            "user_b",
            analysis_date,
            sleep_markers=[{"onset_timestamp": 1100, "offset_timestamp": 2100, "marker_type": "MAIN_SLEEP"}],
        )

        ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert ballot_resp.status_code == 200
        candidates = ballot_resp.json()["candidates"]
        c1 = candidates[0]["candidate_id"]
        c2 = candidates[1]["candidate_id"]

        await asyncio.gather(
            client.post(
                f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
                headers=admin_auth_headers,
                json={"candidate_id": c1},
            ),
            client.post(
                f"/api/v1/consensus/{file_id}/{analysis_date}/vote",
                headers=annotator_auth_headers,
                json={"candidate_id": c2},
            ),
        )

        final_ballot_resp = await client.get(
            f"/api/v1/consensus/{file_id}/{analysis_date}/ballot",
            headers=admin_auth_headers,
        )
        assert final_ballot_resp.status_code == 200
        final_ballot = final_ballot_resp.json()
        assert final_ballot["total_votes"] == 2
        counts = {c["candidate_id"]: c["vote_count"] for c in final_ballot["candidates"]}
        assert counts[c1] == 1
        assert counts[c2] == 1


@pytest.mark.asyncio
class TestConsensusResolve:
    """Tests for POST /api/v1/consensus/{file_id}/{date}/resolve."""

    async def test_resolve_stores_separately(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Resolution should store in resolved_annotations, NOT overwrite main markers."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "consensus_res.csv")

        # Save some main markers first
        await _save_markers(client, admin_auth_headers, file_id, "2024-01-01")

        # Create annotations
        await _create_annotation(test_session_maker, file_id, "user_a", "2024-01-01")
        await _create_annotation(test_session_maker, file_id, "user_b", "2024-01-01")

        # Resolve with different markers than what's in the main table
        resolved_markers = [{"onset_timestamp": 1500, "offset_timestamp": 2500, "marker_type": "MAIN_SLEEP", "marker_index": 1}]

        response = await client.post(
            f"/api/v1/consensus/{file_id}/2024-01-01/resolve",
            headers=admin_auth_headers,
            json={
                "final_sleep_markers_json": resolved_markers,
                "final_nonwear_markers_json": [],
                "resolution_notes": "Accepted user_a with adjustment",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resolved_by"] == "testadmin"
        assert data["resolution_notes"] == "Accepted user_a with adjustment"

        # Verify main markers are NOT overwritten
        markers_resp = await client.get(
            f"/api/v1/markers/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )
        assert markers_resp.status_code == 200
        main_markers = markers_resp.json()["sleep_markers"]
        # Main markers should still have the original timestamps, not the resolved ones
        assert len(main_markers) >= 1
        assert main_markers[0]["onset_timestamp"] == 1000  # Original, not 1500

    async def test_resolve_marks_as_resolved(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Resolving should mark the consensus as having a resolution."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "consensus_mark.csv")

        await _create_annotation(test_session_maker, file_id, "user_a", "2024-01-01")
        await _create_annotation(test_session_maker, file_id, "user_b", "2024-01-01")

        await client.post(
            f"/api/v1/consensus/{file_id}/2024-01-01/resolve",
            headers=admin_auth_headers,
            json={
                "final_sleep_markers_json": [{"onset_timestamp": 1000, "offset_timestamp": 2000}],
                "final_nonwear_markers_json": [],
            },
        )

        # Check consensus status
        response = await client.get(
            f"/api/v1/consensus/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["has_resolution"] is True
        assert data["resolution"] is not None

    async def test_resolve_nonexistent_file(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Should return 404 for nonexistent file."""
        response = await client.post(
            "/api/v1/consensus/99999/2024-01-01/resolve",
            headers=admin_auth_headers,
            json={
                "final_sleep_markers_json": [],
                "final_nonwear_markers_json": [],
            },
        )

        assert response.status_code == 404

    async def test_resolve_can_be_updated(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
        test_session_maker,
    ):
        """Should be able to update an existing resolution."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "consensus_re_resolve.csv")

        await _create_annotation(test_session_maker, file_id, "user_a", "2024-01-01")
        await _create_annotation(test_session_maker, file_id, "user_b", "2024-01-01")

        # First resolution
        await client.post(
            f"/api/v1/consensus/{file_id}/2024-01-01/resolve",
            headers=admin_auth_headers,
            json={
                "final_sleep_markers_json": [{"onset_timestamp": 1000, "offset_timestamp": 2000}],
                "final_nonwear_markers_json": [],
                "resolution_notes": "First pass",
            },
        )

        # Update resolution
        response = await client.post(
            f"/api/v1/consensus/{file_id}/2024-01-01/resolve",
            headers=admin_auth_headers,
            json={
                "final_sleep_markers_json": [{"onset_timestamp": 1100, "offset_timestamp": 2100}],
                "final_nonwear_markers_json": [],
                "resolution_notes": "Revised",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["resolution_notes"] == "Revised"
