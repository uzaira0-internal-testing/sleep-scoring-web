"""
Integration tests for marker table data endpoints.

Covers onset/offset table, full table, columnar variants,
algorithm selection, access control, empty data, and window_minutes param.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.web.conftest import make_sleep_marker, upload_and_get_date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _upload_save_marker_and_get_ids(
    client: AsyncClient,
    auth_headers: dict[str, str],
    csv_content: str,
    filename: str,
) -> tuple[int, str]:
    """Upload a file, save a sleep marker, and return (file_id, date_str).

    The sample CSV data starts at 2024-01-01 12:00 UTC and has 100 one-minute
    epochs.  We place the marker well inside that range so both onset and
    offset windows contain activity rows.
    """
    file_id, date_str = await upload_and_get_date(
        client, auth_headers, csv_content, filename
    )

    # Onset near middle of data: 2024-01-01 12:30 UTC = 1704112200
    # Offset 30 min later: 2024-01-01 13:00 UTC = 1704114000
    onset = 1704112200.0
    offset = 1704114000.0

    marker = make_sleep_marker(onset, offset, period_index=1)
    # Ensure marker_index matches period_index for DB storage
    marker["marker_index"] = 1

    resp = await client.put(
        f"/api/v1/markers/{file_id}/{date_str}",
        headers=auth_headers,
        json={
            "sleep_markers": [marker],
            "nonwear_markers": [],
        },
    )
    assert resp.status_code == 200, resp.text
    return file_id, date_str


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMarkersTablesOnsetOffset:
    """Tests for GET /{file_id}/{date}/table/{period_index} (onset/offset)."""

    # 1. Onset/offset data returns correct format
    async def test_onset_offset_returns_correct_format(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Response must contain onset_data, offset_data lists and period_index."""
        file_id, date_str = await _upload_save_marker_and_get_ids(
            client, admin_auth_headers, sample_csv_content, "table_format.csv"
        )

        resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table/1",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        # Top-level keys
        assert "onset_data" in data
        assert "offset_data" in data
        assert data["period_index"] == 1

        # Each data point has the expected fields
        assert len(data["onset_data"]) > 0
        point = data["onset_data"][0]
        assert "timestamp" in point
        assert "datetime_str" in point
        assert "axis_y" in point
        assert "vector_magnitude" in point
        assert "algorithm_result" in point
        assert "choi_result" in point
        assert "is_nonwear" in point

    # 2. Onset/offset with explicit onset_ts/offset_ts query params
    async def test_onset_offset_with_explicit_timestamps(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Passing onset_ts and offset_ts should bypass the DB marker lookup."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_explicit_ts.csv"
        )
        # No marker saved — use explicit timestamps
        onset_ts = 1704112200.0  # 12:30 UTC
        offset_ts = 1704114000.0  # 13:00 UTC

        resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table/0",
            headers=admin_auth_headers,
            params={"onset_ts": onset_ts, "offset_ts": offset_ts},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["onset_data"]) > 0
        assert len(data["offset_data"]) > 0

    # 3. Window size parameter controls range
    async def test_window_minutes_parameter(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """A smaller window_minutes should return fewer data points."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_window.csv"
        )
        onset_ts = 1704112200.0
        offset_ts = 1704114000.0

        # Large window — should capture more rows
        resp_large = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table/0",
            headers=admin_auth_headers,
            params={
                "onset_ts": onset_ts,
                "offset_ts": offset_ts,
                "window_minutes": 60,
            },
        )
        assert resp_large.status_code == 200

        # Small window — should capture fewer rows
        resp_small = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table/0",
            headers=admin_auth_headers,
            params={
                "onset_ts": onset_ts,
                "offset_ts": offset_ts,
                "window_minutes": 5,
            },
        )
        assert resp_small.status_code == 200

        large_count = len(resp_large.json()["onset_data"])
        small_count = len(resp_small.json()["onset_data"])
        assert large_count > small_count, (
            f"Large window ({large_count}) should return more rows than small ({small_count})"
        )

    # 4. Missing marker and no explicit timestamps returns 404
    async def test_missing_marker_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Without a saved marker or explicit timestamps, the endpoint
        should return 404."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_no_marker.csv"
        )

        resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table/0",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestMarkersTablesFullTable:
    """Tests for GET /{file_id}/{date}/table-full (full 24h table)."""

    # 5. Full table data returns correct format
    async def test_full_table_returns_correct_format(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Full table response must contain data list, total_rows, and time bounds."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_full.csv"
        )

        resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table-full",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "data" in data
        assert "total_rows" in data
        assert data["total_rows"] == len(data["data"])
        assert data["total_rows"] > 0

        # Time bounds present when data exists
        assert data["start_time"] is not None
        assert data["end_time"] is not None

        # Check data point shape
        point = data["data"][0]
        assert "timestamp" in point
        assert "datetime_str" in point
        assert "axis_y" in point
        assert "vector_magnitude" in point
        assert "algorithm_result" in point
        assert "choi_result" in point
        assert "is_nonwear" in point

    # 6. Different algorithm selection
    async def test_full_table_different_algorithm(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Specifying a different algorithm should still return valid data."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_algo.csv"
        )

        # Default algorithm (sadeh_1994_actilife)
        resp_default = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table-full",
            headers=admin_auth_headers,
        )
        assert resp_default.status_code == 200

        # Cole-Kripke algorithm
        resp_ck = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table-full",
            headers=admin_auth_headers,
            params={"algorithm": "cole_kripke_1992_actilife"},
        )
        assert resp_ck.status_code == 200
        assert resp_ck.json()["total_rows"] > 0

    # 7. Invalid algorithm returns 400
    async def test_invalid_algorithm_returns_400(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """An unrecognized algorithm name should yield a 400 error."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_bad_algo.csv"
        )

        resp = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table-full",
            headers=admin_auth_headers,
            params={"algorithm": "totally_bogus_algo"},
        )
        assert resp.status_code == 400
        assert "Unknown algorithm" in resp.json()["detail"]


@pytest.mark.asyncio
class TestMarkersTablesAccessControl:
    """Access control and invalid-ID tests for table endpoints."""

    # 8. Annotator without assignment gets 404
    async def test_annotator_no_access_gets_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """An unassigned annotator must receive 404 on table endpoints."""
        file_id, date_str = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_acl.csv"
        )

        # Full table — annotator blocked
        resp_full = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table-full",
            headers=annotator_auth_headers,
        )
        assert resp_full.status_code == 404

        # Onset/offset — annotator blocked
        resp_oo = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table/0",
            headers=annotator_auth_headers,
            params={"onset_ts": 1704112200.0, "offset_ts": 1704114000.0},
        )
        assert resp_oo.status_code == 404

        # Grant access then retry
        assign_resp = await client.post(
            "/api/v1/files/assignments",
            headers=admin_auth_headers,
            json={"file_ids": [file_id], "username": "testannotator"},
        )
        assert assign_resp.status_code == 200

        resp_full2 = await client.get(
            f"/api/v1/markers/{file_id}/{date_str}/table-full",
            headers=annotator_auth_headers,
        )
        assert resp_full2.status_code == 200

    # 9. Invalid file_id returns 404
    async def test_invalid_file_id_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """A non-existent file_id should return 404 for table endpoints."""
        fake_id = 999999

        resp_full = await client.get(
            f"/api/v1/markers/{fake_id}/2024-01-01/table-full",
            headers=admin_auth_headers,
        )
        assert resp_full.status_code == 404

    # 10. Empty data handling (date with no activity rows)
    async def test_full_table_empty_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """A date that has no activity rows should return an empty data list."""
        file_id, _ = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "table_empty.csv"
        )

        # Use a date far from the actual data so no epochs fall in the noon-to-noon window
        resp = await client.get(
            f"/api/v1/markers/{file_id}/2025-06-15/table-full",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"] == []
        assert data["total_rows"] == 0
        assert data["start_time"] is None
        assert data["end_time"] is None
