"""
Tests for no-sleep date semantics.

Verifies that:
- is_no_sleep=true deletes MAIN_SLEEP markers (client omits them)
- NAP markers are preserved on no-sleep dates
- Nonwear markers are preserved on no-sleep dates
- is_no_sleep=false allows MAIN_SLEEP markers
- is_no_sleep flag persists across GET
- No-sleep dates appear as scored in dates status
- No-sleep with NAPs returns both is_no_sleep and NAP markers
- Round-trip: save is_no_sleep=true with NAPs, read back, verify both
"""

import pytest
from httpx import AsyncClient

from tests.web.conftest import upload_and_get_date


@pytest.mark.asyncio
class TestNoSleepSemantics:
    """Tests for no-sleep date semantics via the markers API."""

    async def test_no_sleep_deletes_main_sleep_markers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """When is_no_sleep=true, MAIN_SLEEP markers should not be present."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_del_main.csv"
        )

        # First save a MAIN_SLEEP marker
        resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
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
                "is_no_sleep": False,
            },
        )
        assert resp.status_code == 200

        # Verify MAIN_SLEEP is present
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        assert len(get_resp.json()["sleep_markers"]) == 1

        # Now toggle to no-sleep: client omits MAIN_SLEEP markers
        resp2 = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [],
                "nonwear_markers": [],
                "is_no_sleep": True,
            },
        )
        assert resp2.status_code == 200

        # Verify MAIN_SLEEP markers are gone
        get_resp2 = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp2.status_code == 200
        assert get_resp2.json()["sleep_markers"] == []
        assert get_resp2.json()["is_no_sleep"] is True

    async def test_no_sleep_preserves_nap_markers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """When is_no_sleep=true, NAP markers should be preserved."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_keep_nap.csv"
        )

        # Save is_no_sleep=true with a NAP marker
        resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": 1704078000.0,
                        "offset_timestamp": 1704081600.0,
                        "marker_index": 1,
                        "marker_type": "NAP",
                    }
                ],
                "nonwear_markers": [],
                "is_no_sleep": True,
            },
        )
        assert resp.status_code == 200

        # Verify NAP marker is preserved
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["is_no_sleep"] is True
        assert len(data["sleep_markers"]) == 1
        assert data["sleep_markers"][0]["marker_type"] == "NAP"

    async def test_no_sleep_preserves_nonwear_markers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """When is_no_sleep=true, nonwear markers should be preserved."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_keep_nw.csv"
        )

        # Save is_no_sleep=true with a nonwear marker
        resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
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
                "is_no_sleep": True,
            },
        )
        assert resp.status_code == 200

        # Verify nonwear marker is preserved
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["is_no_sleep"] is True
        assert len(data["nonwear_markers"]) == 1
        assert data["nonwear_markers"][0]["start_timestamp"] == 1704070800.0

    async def test_no_sleep_false_allows_main_sleep(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """When is_no_sleep=false, MAIN_SLEEP markers should be allowed."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_false_main.csv"
        )

        # Save with is_no_sleep=false and a MAIN_SLEEP marker
        resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
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
                "is_no_sleep": False,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["sleep_marker_count"] == 1

        # Verify MAIN_SLEEP marker is present and is_no_sleep is false
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["is_no_sleep"] is False
        assert len(data["sleep_markers"]) == 1
        assert data["sleep_markers"][0]["marker_type"] == "MAIN_SLEEP"

    async def test_no_sleep_persists_across_get(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """The is_no_sleep flag should persist and be returned by GET."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_persist.csv"
        )

        # Initially is_no_sleep should be false
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["is_no_sleep"] is False

        # Set is_no_sleep=true
        resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [],
                "nonwear_markers": [],
                "is_no_sleep": True,
            },
        )
        assert resp.status_code == 200

        # Verify it persists
        get_resp2 = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp2.status_code == 200
        assert get_resp2.json()["is_no_sleep"] is True

    async def test_no_sleep_appears_as_scored_in_dates_status(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """A no-sleep date should appear as has_markers=true in dates status."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_status.csv"
        )

        # Mark as no-sleep with no markers
        resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [],
                "nonwear_markers": [],
                "is_no_sleep": True,
            },
        )
        assert resp.status_code == 200

        # Check dates status
        status_resp = await client.get(
            f"/api/v1/files/{file_id}/dates/status",
            headers=admin_auth_headers,
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        date_row = next((d for d in status_data if d["date"] == date_str), None)
        assert date_row is not None, f"Date {date_str} not found in dates status"
        assert date_row["has_markers"] is True
        assert date_row["is_no_sleep"] is True

    async def test_no_sleep_with_naps_returns_both(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """A no-sleep date with NAP markers should return both is_no_sleep and the NAP markers."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_nap_both.csv"
        )

        nap_onset = 1704078000.0
        nap_offset = 1704081600.0

        # Save no-sleep with a NAP
        resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": nap_onset,
                        "offset_timestamp": nap_offset,
                        "marker_index": 1,
                        "marker_type": "NAP",
                    }
                ],
                "nonwear_markers": [],
                "is_no_sleep": True,
            },
        )
        assert resp.status_code == 200

        # Retrieve and verify both flags and markers
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        assert data["is_no_sleep"] is True
        assert len(data["sleep_markers"]) == 1
        marker = data["sleep_markers"][0]
        assert marker["marker_type"] == "NAP"
        assert marker["onset_timestamp"] == nap_onset
        assert marker["offset_timestamp"] == nap_offset

    async def test_no_sleep_round_trip_with_naps(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Round-trip: save is_no_sleep=true with NAPs, read back, verify both present."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "nosleep_roundtrip.csv"
        )

        nap1_onset = 1704078000.0
        nap1_offset = 1704081600.0
        nap2_onset = 1704092400.0
        nap2_offset = 1704096000.0
        nw_start = 1704070800.0
        nw_end = 1704074400.0

        # Save no-sleep with two NAPs and a nonwear marker
        save_resp = await client.put(
            f"/api/v1/markers/{file_id}/{date_str}",
            headers=admin_auth_headers,
            json={
                "sleep_markers": [
                    {
                        "onset_timestamp": nap1_onset,
                        "offset_timestamp": nap1_offset,
                        "marker_index": 1,
                        "marker_type": "NAP",
                    },
                    {
                        "onset_timestamp": nap2_onset,
                        "offset_timestamp": nap2_offset,
                        "marker_index": 2,
                        "marker_type": "NAP",
                    },
                ],
                "nonwear_markers": [
                    {
                        "start_timestamp": nw_start,
                        "end_timestamp": nw_end,
                        "marker_index": 1,
                    }
                ],
                "is_no_sleep": True,
            },
        )
        assert save_resp.status_code == 200
        save_data = save_resp.json()
        assert save_data["sleep_marker_count"] == 2
        assert save_data["nonwear_marker_count"] == 1

        # Read back and verify everything is preserved
        get_resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}", headers=admin_auth_headers
        )
        assert get_resp.status_code == 200
        data = get_resp.json()

        # Verify is_no_sleep flag
        assert data["is_no_sleep"] is True

        # Verify NAP markers
        nap_markers = [m for m in data["sleep_markers"] if m["marker_type"] == "NAP"]
        assert len(nap_markers) == 2
        nap_onsets = sorted(m["onset_timestamp"] for m in nap_markers)
        assert nap_onsets == [nap1_onset, nap2_onset]

        # Verify no MAIN_SLEEP markers leaked in
        main_markers = [m for m in data["sleep_markers"] if m["marker_type"] == "MAIN_SLEEP"]
        assert main_markers == []

        # Verify nonwear marker
        assert len(data["nonwear_markers"]) == 1
        assert data["nonwear_markers"][0]["start_timestamp"] == nw_start
        assert data["nonwear_markers"][0]["end_timestamp"] == nw_end
