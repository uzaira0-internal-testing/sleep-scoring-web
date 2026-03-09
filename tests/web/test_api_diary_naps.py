"""
HTTP integration tests for diary nap and nonwear fields (Phase 7).

Tests that diary entries can store/retrieve nap periods and nonwear periods,
and that CSV import correctly handles nap/nonwear columns.
"""

import io

import pytest
from httpx import AsyncClient


async def _upload_file(client: AsyncClient, headers: dict, content: str, filename: str) -> int:
    """Upload a CSV file and return its file_id."""
    files = {"file": (filename, io.BytesIO(content.encode()), "text/csv")}
    resp = await client.post("/api/v1/files/upload", headers=headers, files=files)
    assert resp.status_code == 200, f"Upload failed: {resp.text}"
    return resp.json()["file_id"]


@pytest.mark.asyncio
class TestDiaryNapFields:
    """Tests for nap period fields in diary entries."""

    async def test_create_diary_with_nap_fields(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should create a diary entry with nap start/end times."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_nap1.csv")

        response = await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={
                "bed_time": "22:00",
                "wake_time": "07:00",
                "nap_1_start": "13:00",
                "nap_1_end": "14:00",
                "nap_2_start": "16:00",
                "nap_2_end": "16:30",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["nap_1_start"] == "13:00"
        assert data["nap_1_end"] == "14:00"
        assert data["nap_2_start"] == "16:00"
        assert data["nap_2_end"] == "16:30"
        assert data["nap_3_start"] is None
        assert data["nap_3_end"] is None

    async def test_roundtrip_nap_fields(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should be able to save and retrieve nap fields."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_nap_rt.csv")

        await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={"nap_1_start": "14:00", "nap_1_end": "15:30"},
        )

        response = await client.get(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["nap_1_start"] == "14:00"
        assert data["nap_1_end"] == "15:30"

    async def test_update_nap_fields(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should update nap fields without losing other diary data."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_nap_upd.csv")

        # Create with bed/wake times
        await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={"bed_time": "22:00", "wake_time": "07:00"},
        )

        # Update with nap times
        response = await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={"bed_time": "22:00", "wake_time": "07:00", "nap_1_start": "13:00", "nap_1_end": "14:00"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["bed_time"] == "22:00"
        assert data["nap_1_start"] == "13:00"


@pytest.mark.asyncio
class TestDiaryNonwearFields:
    """Tests for nonwear period fields in diary entries."""

    async def test_create_diary_with_nonwear_fields(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should create a diary entry with nonwear start/end/reason."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_nw1.csv")

        response = await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={
                "bed_time": "22:00",
                "wake_time": "07:00",
                "nonwear_1_start": "08:00",
                "nonwear_1_end": "08:30",
                "nonwear_1_reason": "shower",
                "nonwear_2_start": "18:00",
                "nonwear_2_end": "19:00",
                "nonwear_2_reason": "swimming",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["nonwear_1_start"] == "08:00"
        assert data["nonwear_1_end"] == "08:30"
        assert data["nonwear_1_reason"] == "shower"
        assert data["nonwear_2_start"] == "18:00"
        assert data["nonwear_2_reason"] == "swimming"
        assert data["nonwear_3_start"] is None

    async def test_all_three_nonwear_periods(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should support all three nonwear period slots."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_nw3.csv")

        response = await client.put(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
            json={
                "nonwear_1_start": "08:00",
                "nonwear_1_end": "08:30",
                "nonwear_1_reason": "shower",
                "nonwear_2_start": "12:00",
                "nonwear_2_end": "12:30",
                "nonwear_2_reason": "bath",
                "nonwear_3_start": "18:00",
                "nonwear_3_end": "19:00",
                "nonwear_3_reason": "swimming",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["nonwear_3_reason"] == "swimming"


@pytest.mark.asyncio
class TestDiaryCsvImportNapNonwear:
    """Tests for CSV import of nap/nonwear columns."""

    async def test_csv_import_nap_columns(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should import nap start/end from CSV."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_csv_nap.csv")

        diary_csv = (
            "date,bed_time,wake_time,nap_1_start,nap_1_end\n"
            "2024-01-01,22:30,07:00,13:00,14:00\n"
        )
        files = {"file": ("diary.csv", io.BytesIO(diary_csv.encode()), "text/csv")}
        response = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files=files,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entries_imported"] == 1

        # Verify the imported data
        entry_resp = await client.get(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )
        assert entry_resp.status_code == 200
        entry = entry_resp.json()
        assert entry["nap_1_start"] == "13:00"
        assert entry["nap_1_end"] == "14:00"

    async def test_csv_import_nonwear_columns(
        self, client: AsyncClient, admin_auth_headers: dict, sample_csv_content: str
    ):
        """Should import nonwear start/end/reason from CSV."""
        file_id = await _upload_file(client, admin_auth_headers, sample_csv_content, "diary_csv_nw.csv")

        diary_csv = (
            "date,bed_time,wake_time,nonwear_1_start,nonwear_1_end,nonwear_1_reason\n"
            "2024-01-01,22:30,07:00,08:00,08:30,shower\n"
        )
        files = {"file": ("diary.csv", io.BytesIO(diary_csv.encode()), "text/csv")}
        response = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files=files,
        )

        assert response.status_code == 200

        entry_resp = await client.get(
            f"/api/v1/diary/{file_id}/2024-01-01",
            headers=admin_auth_headers,
        )
        assert entry_resp.status_code == 200
        entry = entry_resp.json()
        assert entry["nonwear_1_start"] == "08:00"
        assert entry["nonwear_1_reason"] == "shower"
