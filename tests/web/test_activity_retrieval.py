"""
Tests for activity data retrieval endpoints.

Covers columnar format correctness, array consistency, timestamp ordering,
algorithm overlay via /score, access control, and available-dates shape.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from tests.web.conftest import upload_and_get_date

API = "/api/v1"


@pytest.mark.asyncio
class TestActivityRetrieval:
    """Tests for GET /api/v1/activity/{file_id}/{date}."""

    async def test_columnar_format_correct(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """All expected columnar arrays are present in the response."""
        file_id, date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "col_format.csv"
        )

        resp = await client.get(
            f"{API}/activity/{file_id}/{date}", headers=admin_auth_headers
        )
        assert resp.status_code == 200

        body: dict[str, Any] = resp.json()
        data = body["data"]
        for key in ("timestamps", "axis_x", "axis_y", "axis_z", "vector_magnitude"):
            assert key in data, f"Missing key: {key}"
            assert isinstance(data[key], list), f"{key} should be a list"

    async def test_all_arrays_same_length(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """All columnar arrays must have equal length."""
        file_id, date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "array_len.csv"
        )

        resp = await client.get(
            f"{API}/activity/{file_id}/{date}", headers=admin_auth_headers
        )
        assert resp.status_code == 200

        data = resp.json()["data"]
        lengths = {
            k: len(data[k])
            for k in ("timestamps", "axis_x", "axis_y", "axis_z", "vector_magnitude")
        }
        unique_lengths = set(lengths.values())
        assert len(unique_lengths) == 1, f"Array lengths differ: {lengths}"

    async def test_timestamps_monotonically_increasing(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """Timestamps must be in strictly non-decreasing order."""
        file_id, date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "ts_order.csv"
        )

        resp = await client.get(
            f"{API}/activity/{file_id}/{date}", headers=admin_auth_headers
        )
        assert resp.status_code == 200

        timestamps: list[float] = resp.json()["data"]["timestamps"]
        assert len(timestamps) > 0, "Expected non-empty timestamps"
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i - 1], (
                f"Timestamp at index {i} ({timestamps[i]}) < previous ({timestamps[i - 1]})"
            )

    async def test_score_endpoint_includes_algorithm_overlay(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """The /score endpoint must include algorithm_results in its response."""
        file_id, date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "algo_overlay.csv"
        )

        resp = await client.get(
            f"{API}/activity/{file_id}/{date}/score?algorithm=sadeh_1994_actilife",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        assert "algorithm_results" in body
        assert body["algorithm_results"] is not None, (
            "algorithm_results should not be null when data exists"
        )

    async def test_invalid_file_id_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Requesting activity for a non-existent file_id must return 404."""
        resp = await client.get(
            f"{API}/activity/99999/2024-01-01", headers=admin_auth_headers
        )
        assert resp.status_code == 404

    async def test_annotator_cannot_access_unassigned_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        annotator_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """An annotator should get 404 for a file not assigned to them."""
        # Upload as admin — file is NOT assigned to the annotator.
        file_id, date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "access_ctrl.csv"
        )

        resp = await client.get(
            f"{API}/activity/{file_id}/{date}", headers=annotator_auth_headers
        )
        assert resp.status_code == 404

    async def test_available_dates_sorted_and_non_empty(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """available_dates must be a sorted, non-empty list of date strings."""
        file_id, date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "avail_dates.csv"
        )

        resp = await client.get(
            f"{API}/activity/{file_id}/{date}", headers=admin_auth_headers
        )
        assert resp.status_code == 200

        available_dates: list[str] = resp.json()["available_dates"]
        assert len(available_dates) > 0, "available_dates should not be empty"
        assert available_dates == sorted(available_dates), (
            "available_dates should be sorted"
        )

    async def test_score_algorithm_results_matches_data_length(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        sample_csv_content: str,
    ) -> None:
        """algorithm_results length must equal the data array length."""
        file_id, date = await upload_and_get_date(
            client, admin_auth_headers, sample_csv_content, "algo_len.csv"
        )

        resp = await client.get(
            f"{API}/activity/{file_id}/{date}/score?algorithm=sadeh_1994_actilife",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200

        body = resp.json()
        data_len = len(body["data"]["timestamps"])
        algo_len = len(body["algorithm_results"])
        assert algo_len == data_len, (
            f"algorithm_results length ({algo_len}) != data length ({data_len})"
        )
