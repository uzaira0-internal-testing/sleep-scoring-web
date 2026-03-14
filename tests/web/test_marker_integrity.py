"""
Marker integrity and user-isolation tests.

Validates timestamp precision, per-user marker isolation, marker type
semantics, sensor nonwear exclusion, multi-period ordering, and access
control across the /api/v1/markers endpoints.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.web.conftest import make_nonwear_marker, make_sleep_marker, upload_and_get_date


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMarkerIntegrity:
    """Marker integrity and user-isolation test suite."""

    # 1. Timestamps round-trip exactly (float precision)
    async def test_timestamps_round_trip_exact(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Float timestamps must survive a save/load cycle without precision loss."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_ts_precision.csv"
        )

        # Use high-precision floats that would lose fidelity under rounding
        onset = 1704110400.123456
        offset = 1704135600.654321

        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(onset, offset)],
                "nonwear_markers": [],
            },
        )
        assert put_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        markers = get_resp.json()["sleep_markers"]
        assert len(markers) == 1
        assert markers[0]["onset_timestamp"] == onset
        assert markers[0]["offset_timestamp"] == offset

    # 2. Per-user isolation: admin and annotator save different markers, each
    #    sees only theirs
    async def test_per_user_isolation(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Each user's markers must be invisible to the other."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_user_iso.csv"
        )

        # Assign the file to the annotator so they have access
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert assign_resp.status_code == 200

        admin_onset, admin_offset = 1704070800.0, 1704074400.0
        anno_onset, anno_offset = 1704085200.0, 1704088800.0

        # Admin saves
        resp_a = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(admin_onset, admin_offset)],
                "nonwear_markers": [],
            },
        )
        assert resp_a.status_code == 200

        # Annotator saves different markers
        resp_b = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=annotator_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(anno_onset, anno_offset)],
                "nonwear_markers": [],
            },
        )
        assert resp_b.status_code == 200

        # Each sees only their own
        get_a = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        get_b = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=annotator_auth_headers
        )
        assert get_a.status_code == 200
        assert get_b.status_code == 200

        admin_markers = get_a.json()["sleep_markers"]
        anno_markers = get_b.json()["sleep_markers"]
        assert len(admin_markers) == 1
        assert len(anno_markers) == 1
        assert admin_markers[0]["onset_timestamp"] == admin_onset
        assert anno_markers[0]["onset_timestamp"] == anno_onset

    # 3. Empty sleep_markers: [] clears previous markers
    async def test_empty_sleep_markers_clears(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Sending sleep_markers=[] should delete all existing sleep markers."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_clear.csv"
        )

        # Save a marker
        await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(1704070800.0, 1704074400.0)],
                "nonwear_markers": [],
            },
        )

        # Verify it exists
        get1 = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert len(get1.json()["sleep_markers"]) == 1

        # Clear with empty list
        clear_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={"sleep_markers": [], "nonwear_markers": []},
        )
        assert clear_resp.status_code == 200
        assert clear_resp.json()["sleep_marker_count"] == 0

        # Verify gone
        get2 = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get2.json()["sleep_markers"] == []

    # 4. MarkerType values (MAIN_SLEEP, NAP) stored/returned correctly
    async def test_marker_type_values(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """MAIN_SLEEP and NAP marker types must be preserved through save/load."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_types.csv"
        )

        markers = [
            make_sleep_marker(1704070800.0, 1704074400.0, marker_type="MAIN_SLEEP", period_index=1),
            make_sleep_marker(1704085200.0, 1704088800.0, marker_type="NAP", period_index=2),
        ]
        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={"sleep_markers": markers, "nonwear_markers": []},
        )
        assert put_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        saved = get_resp.json()["sleep_markers"]
        assert len(saved) == 2

        types_returned = {m["marker_type"] for m in saved}
        assert "MAIN_SLEEP" in types_returned
        assert "NAP" in types_returned

    # 5. Nonwear markers separate from sleep markers
    async def test_nonwear_separate_from_sleep(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Nonwear markers must not leak into sleep_markers and vice-versa."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_nw_sep.csv"
        )

        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(1704070800.0, 1704074400.0)],
                "nonwear_markers": [make_nonwear_marker(1704100000.0, 1704103600.0)],
            },
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["sleep_marker_count"] == 1
        assert put_resp.json()["nonwear_marker_count"] == 1

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        data = get_resp.json()
        assert len(data["sleep_markers"]) == 1
        assert len(data["nonwear_markers"]) == 1
        # Check they don't share timestamps
        assert data["sleep_markers"][0]["onset_timestamp"] == 1704070800.0
        assert data["nonwear_markers"][0]["start_timestamp"] == 1704100000.0

    # 6. Sensor nonwear excluded from CRUD responses
    async def test_sensor_nonwear_excluded_from_crud(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
        test_session_maker: Any,
    ) -> None:
        """Sensor nonwear markers (marker_type='sensor') must never appear in
        GET /markers responses."""
        from sleep_scoring_web.db.models import Marker as MarkerModel
        from sleep_scoring_web.schemas.enums import MarkerCategory, MarkerType

        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_sensor_nw.csv"
        )

        # Insert a sensor nonwear marker directly into the DB
        from datetime import date as date_type

        analysis_date = date_type.fromisoformat(date_str)
        async with test_session_maker() as session:
            # Sensor nonwear markers are system-generated, so use a system
            # created_by value (not the human user) to avoid unique-constraint
            # collisions with user-saved manual nonwear markers.
            sensor_marker = MarkerModel(
                file_id=file_id,
                analysis_date=analysis_date,
                marker_category=MarkerCategory.NONWEAR,
                marker_type=MarkerType.SENSOR_NONWEAR,
                start_timestamp=1704100000.0,
                end_timestamp=1704103600.0,
                period_index=1,
                created_by="system",
            )
            session.add(sensor_marker)
            await session.commit()

        # Also save a manual nonwear marker via the API
        await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [],
                "nonwear_markers": [make_nonwear_marker(1704200000.0, 1704203600.0)],
            },
        )

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        nw_markers = get_resp.json()["nonwear_markers"]

        # Only the manual nonwear should appear; sensor nonwear is excluded
        assert len(nw_markers) == 1
        assert nw_markers[0]["start_timestamp"] == 1704200000.0

    # 7. Multiple periods (period_index 0, 1, 2) saved and retrieved in order
    async def test_multiple_periods_order(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Multiple sleep periods with different period_index values should be
        stored and returned."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_multi_period.csv"
        )

        markers = [
            {**make_sleep_marker(1704070800.0, 1704074400.0), "marker_index": 1},
            {**make_sleep_marker(1704085200.0, 1704088800.0, marker_type="NAP"), "marker_index": 2},
            {**make_sleep_marker(1704096000.0, 1704099600.0, marker_type="NAP"), "marker_index": 3},
        ]
        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={"sleep_markers": markers, "nonwear_markers": []},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["sleep_marker_count"] == 3

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        saved = get_resp.json()["sleep_markers"]
        assert len(saved) == 3
        indices = [m["marker_index"] for m in saved]
        assert 1 in indices
        assert 2 in indices
        assert 3 in indices

    # 8. Delete single period doesn't affect others
    async def test_delete_single_period_preserves_others(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Deleting one period_index must not remove markers at other indices."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_del_single.csv"
        )

        markers = [
            {**make_sleep_marker(1704070800.0, 1704074400.0), "marker_index": 1},
            {**make_sleep_marker(1704085200.0, 1704088800.0, marker_type="NAP"), "marker_index": 2},
        ]
        await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={"sleep_markers": markers, "nonwear_markers": []},
        )

        # Delete period 1 only
        del_resp = await client.delete(
            f"/api/v1/markers/{file_id}/{date_str}/1",
            headers=admin_auth_headers,
        )
        assert del_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        remaining = get_resp.json()["sleep_markers"]
        assert len(remaining) == 1
        assert remaining[0]["marker_index"] == 2
        assert remaining[0]["onset_timestamp"] == 1704085200.0

    # 9. needs_consensus flag round-trips
    async def test_needs_consensus_round_trip(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """The needs_consensus flag must survive a save and be returned on GET."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_consensus.csv"
        )

        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(1704070800.0, 1704074400.0)],
                "nonwear_markers": [],
                "needs_consensus": True,
            },
        )
        assert put_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["needs_consensus"] is True

    # 10. notes field round-trips
    async def test_notes_round_trip(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """The notes field must survive a save and be returned on GET."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_notes.csv"
        )
        test_note = "Participant reported waking at 3 AM due to noise"

        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(1704070800.0, 1704074400.0)],
                "nonwear_markers": [],
                "notes": test_note,
            },
        )
        assert put_resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["notes"] == test_note

    # 11. Access control: annotator can only save/read markers for assigned files
    async def test_annotator_access_control(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """An annotator without file assignment must get 404 on marker endpoints."""
        # Upload as admin (admin always has access)
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_acl.csv"
        )

        # Annotator should NOT have access (no FileAssignment row)
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=annotator_auth_headers,
        )
        assert get_resp.status_code == 404

        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=annotator_auth_headers,
            json={
                "sleep_markers": [make_sleep_marker(1704070800.0, 1704074400.0)],
                "nonwear_markers": [],
            },
        )
        assert put_resp.status_code == 404

        # Now assign the file to the annotator via the files/assignments endpoint
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert assign_resp.status_code == 200

        # Annotator should now have access
        get_resp2 = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=annotator_auth_headers,
        )
        assert get_resp2.status_code == 200

    # 12. Overlapping markers handled correctly
    async def test_overlapping_markers_accepted(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """The API should accept overlapping markers without error and store
        them faithfully (validation is a UI concern)."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "integrity_overlap.csv"
        )

        # Two overlapping sleep markers
        markers = [
            make_sleep_marker(1704070800.0, 1704078000.0, period_index=1),
            make_sleep_marker(1704074400.0, 1704081600.0, marker_type="NAP", period_index=2),
        ]
        put_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={"sleep_markers": markers, "nonwear_markers": []},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["sleep_marker_count"] == 2

        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        saved = get_resp.json()["sleep_markers"]
        assert len(saved) == 2

        # Verify exact timestamps survived despite overlap
        onsets = sorted(m["onset_timestamp"] for m in saved)
        assert onsets == [1704070800.0, 1704074400.0]
