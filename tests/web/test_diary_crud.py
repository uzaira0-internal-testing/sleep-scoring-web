"""
HTTP integration tests for diary CRUD operations.

Tests create, read, update, delete, and access control for sleep diary entries
via /api/v1/diary endpoints.
"""

import pytest
from httpx import AsyncClient

from tests.web.conftest import upload_and_get_date


_FULL_DIARY_ENTRY = {
    "bed_time": "22:30",
    "wake_time": "07:15",
    "lights_out": "22:45",
    "got_up": "07:30",
    "sleep_quality": 4,
    "time_to_fall_asleep_minutes": 15,
    "number_of_awakenings": 2,
    "notes": "test",
    "nap_1_start": "14:00",
    "nap_1_end": "14:30",
    "nonwear_1_start": "18:00",
    "nonwear_1_end": "19:00",
    "nonwear_1_reason": "Bath/Shower",
}


@pytest.mark.asyncio
class TestDiaryCrud:
    """Tests for diary CRUD endpoints."""

    async def test_put_get_roundtrip(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """PUT a diary entry, then GET it back and verify all fields."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        put_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json=_FULL_DIARY_ENTRY,
        )
        assert put_resp.status_code == 200
        put_data = put_resp.json()

        # Verify the PUT response contains all fields
        assert put_data["bed_time"] == "22:30"
        assert put_data["wake_time"] == "07:15"
        assert put_data["lights_out"] == "22:45"
        assert put_data["got_up"] == "07:30"
        assert put_data["sleep_quality"] == 4
        assert put_data["time_to_fall_asleep_minutes"] == 15
        assert put_data["number_of_awakenings"] == 2
        assert put_data["notes"] == "test"

        # GET and verify round-trip
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()

        for field, expected in _FULL_DIARY_ENTRY.items():
            assert get_data[field] == expected, (
                f"Field {field}: expected {expected!r}, got {get_data[field]!r}"
            )

    async def test_nap_periods(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Nap start/end fields should be saved and returned correctly."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        nap_entry = {
            "nap_1_start": "14:00",
            "nap_1_end": "14:30",
        }
        put_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json=nap_entry,
        )
        assert put_resp.status_code == 200
        data = put_resp.json()
        assert data["nap_1_start"] == "14:00"
        assert data["nap_1_end"] == "14:30"

        # Verify via GET as well
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["nap_1_start"] == "14:00"
        assert get_data["nap_1_end"] == "14:30"

    async def test_nonwear_periods(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Nonwear start/end/reason fields should be saved and returned correctly."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        nonwear_entry = {
            "nonwear_1_start": "18:00",
            "nonwear_1_end": "19:00",
            "nonwear_1_reason": "Bath/Shower",
        }
        put_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json=nonwear_entry,
        )
        assert put_resp.status_code == 200
        data = put_resp.json()
        assert data["nonwear_1_start"] == "18:00"
        assert data["nonwear_1_end"] == "19:00"
        assert data["nonwear_1_reason"] == "Bath/Shower"

        # Verify via GET as well
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["nonwear_1_start"] == "18:00"
        assert get_data["nonwear_1_end"] == "19:00"
        assert get_data["nonwear_1_reason"] == "Bath/Shower"

    async def test_access_control_annotator_unassigned_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Annotator should not be able to access diary for files they are not assigned to."""
        # Upload as admin -- annotator has no assignment
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        # Admin can create a diary entry
        put_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={"bed_time": "22:00", "wake_time": "07:00"},
        )
        assert put_resp.status_code == 200

        # Annotator should get 404 (no access) on GET single entry
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=annotator_auth_headers,
        )
        assert get_resp.status_code == 404

        # Annotator should get 404 on list endpoint
        list_resp = await client.get(
            f"/api/v1/diary/{file_id}",
            headers=annotator_auth_headers,
        )
        assert list_resp.status_code == 404

        # Annotator should get 404 on PUT
        annotator_put_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=annotator_auth_headers,
            json={"bed_time": "23:00"},
        )
        assert annotator_put_resp.status_code == 404

        # Annotator should get 404 on DELETE
        del_resp = await client.delete(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=annotator_auth_headers,
        )
        assert del_resp.status_code == 404

    async def test_delete_then_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """DELETE should remove entry; subsequent GET should return null."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        # Create entry
        put_resp = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={"bed_time": "22:30", "wake_time": "07:00"},
        )
        assert put_resp.status_code == 200

        # Confirm it exists
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        assert get_resp.json() is not None
        assert get_resp.json()["bed_time"] == "22:30"

        # Delete it
        del_resp = await client.delete(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert del_resp.status_code == 204

        # Subsequent GET should return null (no entry)
        get_after = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_after.status_code == 200
        assert get_after.json() is None

    async def test_multiple_dates_list(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Creating entries for 2 dates should return both in the list endpoint."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        date_1 = analysis_date
        # Use a second date (one day later)
        from datetime import date as date_type, timedelta

        parsed = date_type.fromisoformat(date_1)
        date_2 = (parsed + timedelta(days=1)).isoformat()

        # Create two entries on different dates
        resp_1 = await client.put(
            f"/api/v1/diary/{file_id}/{date_1}",
            headers=admin_auth_headers,
            json={"bed_time": "22:00", "wake_time": "06:30"},
        )
        assert resp_1.status_code == 200

        resp_2 = await client.put(
            f"/api/v1/diary/{file_id}/{date_2}",
            headers=admin_auth_headers,
            json={"bed_time": "23:00", "wake_time": "07:00"},
        )
        assert resp_2.status_code == 200

        # List should return both
        list_resp = await client.get(
            f"/api/v1/diary/{file_id}",
            headers=admin_auth_headers,
        )
        assert list_resp.status_code == 200
        entries = list_resp.json()
        assert len(entries) >= 2

        returned_dates = {e["analysis_date"] for e in entries}
        assert date_1 in returned_dates
        assert date_2 in returned_dates

    async def test_get_missing_entry_returns_null(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """GET diary for a date with no entry should return null (200 with null body)."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        # Use a date that certainly has no diary entry
        resp = await client.get(
            f"/api/v1/diary/{file_id}/2099-12-31",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() is None

    async def test_update_existing_overwrites(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """PUT twice on the same date should overwrite the first entry."""
        file_id, analysis_date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content
        )

        # First PUT
        resp_1 = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "bed_time": "22:00",
                "wake_time": "06:30",
                "sleep_quality": 3,
                "notes": "first entry",
            },
        )
        assert resp_1.status_code == 200
        assert resp_1.json()["bed_time"] == "22:00"
        assert resp_1.json()["sleep_quality"] == 3
        assert resp_1.json()["notes"] == "first entry"

        # Second PUT with different values
        resp_2 = await client.put(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
            json={
                "bed_time": "23:30",
                "wake_time": "08:00",
                "sleep_quality": 5,
                "notes": "updated entry",
            },
        )
        assert resp_2.status_code == 200
        data = resp_2.json()
        assert data["bed_time"] == "23:30"
        assert data["wake_time"] == "08:00"
        assert data["sleep_quality"] == 5
        assert data["notes"] == "updated entry"

        # Confirm via GET that the update persisted
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        get_data = get_resp.json()
        assert get_data["bed_time"] == "23:30"
        assert get_data["wake_time"] == "08:00"
        assert get_data["sleep_quality"] == 5
        assert get_data["notes"] == "updated entry"
