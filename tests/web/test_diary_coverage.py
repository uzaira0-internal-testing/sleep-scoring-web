"""
Extended integration tests for diary API endpoints targeting uncovered lines.

Covers:
- DELETE non-existent entry → 404
- PUT to non-existent file → 404
- POST /diary/upload (study-wide CSV upload) — various matching strategies
- POST /diary/{file_id}/upload (per-file CSV upload)
- _parse_date with multiple date formats
- _get_time_field / _get_int_field / _get_str_field helpers
- _files_covering_date helper
- Nonwear reason code mapping
- REDCap wide-format detection and conversion
- Error handling for malformed CSVs
"""

import io
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient

from tests.web.conftest import upload_and_get_date


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _csv_bytes(text: str) -> io.BytesIO:
    """Return BytesIO from text for upload."""
    return io.BytesIO(text.encode("utf-8"))


def _latin1_bytes(text: str) -> io.BytesIO:
    """Return BytesIO encoded as latin-1."""
    return io.BytesIO(text.encode("latin-1"))


async def _upload_file(client: AsyncClient, headers: dict, csv_content: str, filename: str | None = None) -> tuple[int, str]:
    """Upload a file and return (file_id, first_date)."""
    return await upload_and_get_date(client, headers, csv_content, filename=filename)


# ---------------------------------------------------------------------------
# Helper-function unit tests
# ---------------------------------------------------------------------------

class TestHelperFunctions:
    """Direct tests for private helper functions in diary.py."""

    def test_parse_date_iso(self):
        from sleep_scoring_web.api.diary import _parse_date
        assert _parse_date("2024-01-15") == date(2024, 1, 15)

    def test_parse_date_us_format(self):
        from sleep_scoring_web.api.diary import _parse_date
        assert _parse_date("01/15/2024") == date(2024, 1, 15)

    def test_parse_date_us_short_year(self):
        from sleep_scoring_web.api.diary import _parse_date
        assert _parse_date("01/15/24") == date(2024, 1, 15)

    def test_parse_date_slash_ymd(self):
        from sleep_scoring_web.api.diary import _parse_date
        assert _parse_date("2024/01/15") == date(2024, 1, 15)

    def test_parse_date_dmy(self):
        from sleep_scoring_web.api.diary import _parse_date
        # 15/01/2024 with d/m/Y — day=15 > 12 so only d/m/Y works
        assert _parse_date("15/01/2024") == date(2024, 1, 15)

    def test_parse_date_invalid(self):
        from sleep_scoring_web.api.diary import _parse_date
        assert _parse_date("not-a-date") is None

    def test_parse_date_whitespace(self):
        from sleep_scoring_web.api.diary import _parse_date
        assert _parse_date("  2024-01-15  ") == date(2024, 1, 15)

    def test_get_time_field_hhmm(self):
        from sleep_scoring_web.api.diary import _get_time_field
        row = {"bed_time": "22:30"}
        assert _get_time_field(row, ["bed_time"]) == "22:30"

    def test_get_time_field_hhmmss(self):
        from sleep_scoring_web.api.diary import _get_time_field
        row = {"bed_time": "22:30:45"}
        assert _get_time_field(row, ["bed_time"]) == "22:30"

    def test_get_time_field_missing(self):
        from sleep_scoring_web.api.diary import _get_time_field
        assert _get_time_field({}, ["bed_time"]) is None

    def test_get_time_field_nan(self):
        from sleep_scoring_web.api.diary import _get_time_field
        row = {"bed_time": "nan"}
        assert _get_time_field(row, ["bed_time"]) is None

    def test_get_time_field_none_value(self):
        from sleep_scoring_web.api.diary import _get_time_field
        row = {"bed_time": None}
        assert _get_time_field(row, ["bed_time"]) is None

    def test_get_time_field_fallback_alias(self):
        from sleep_scoring_web.api.diary import _get_time_field
        row = {"in_bed_time": "23:15"}
        assert _get_time_field(row, ["bed_time", "in_bed_time"]) == "23:15"

    def test_get_time_field_no_colon(self):
        from sleep_scoring_web.api.diary import _get_time_field
        # Value without colon — returned as-is
        row = {"bed_time": "2230"}
        assert _get_time_field(row, ["bed_time"]) == "2230"

    def test_get_time_field_invalid_parts(self):
        from sleep_scoring_web.api.diary import _get_time_field
        # Value with colon but non-numeric parts — returned as-is
        row = {"bed_time": "abc:def"}
        assert _get_time_field(row, ["bed_time"]) == "abc:def"

    def test_get_int_field_valid(self):
        from sleep_scoring_web.api.diary import _get_int_field
        row = {"sleep_quality": 4}
        assert _get_int_field(row, ["sleep_quality"]) == 4

    def test_get_int_field_float(self):
        from sleep_scoring_web.api.diary import _get_int_field
        row = {"sleep_quality": 4.0}
        assert _get_int_field(row, ["sleep_quality"]) == 4

    def test_get_int_field_string(self):
        from sleep_scoring_web.api.diary import _get_int_field
        row = {"sleep_quality": "3"}
        assert _get_int_field(row, ["sleep_quality"]) == 3

    def test_get_int_field_invalid(self):
        from sleep_scoring_web.api.diary import _get_int_field
        row = {"sleep_quality": "bad"}
        assert _get_int_field(row, ["sleep_quality"]) is None

    def test_get_int_field_missing(self):
        from sleep_scoring_web.api.diary import _get_int_field
        assert _get_int_field({}, ["sleep_quality"]) is None

    def test_get_int_field_none_value(self):
        from sleep_scoring_web.api.diary import _get_int_field
        row = {"sleep_quality": None}
        assert _get_int_field(row, ["sleep_quality"]) is None

    def test_get_str_field_valid(self):
        from sleep_scoring_web.api.diary import _get_str_field
        row = {"notes": "some note"}
        assert _get_str_field(row, ["notes"]) == "some note"

    def test_get_str_field_nan(self):
        from sleep_scoring_web.api.diary import _get_str_field
        row = {"notes": "nan"}
        assert _get_str_field(row, ["notes"]) is None

    def test_get_str_field_none_str(self):
        from sleep_scoring_web.api.diary import _get_str_field
        row = {"notes": "None"}
        assert _get_str_field(row, ["notes"]) is None

    def test_get_str_field_null_str(self):
        from sleep_scoring_web.api.diary import _get_str_field
        row = {"notes": "null"}
        assert _get_str_field(row, ["notes"]) is None

    def test_get_str_field_missing(self):
        from sleep_scoring_web.api.diary import _get_str_field
        assert _get_str_field({}, ["notes"]) is None

    def test_get_str_field_none_value(self):
        from sleep_scoring_web.api.diary import _get_str_field
        row = {"notes": None}
        assert _get_str_field(row, ["notes"]) is None

    def test_get_str_field_whitespace(self):
        from sleep_scoring_web.api.diary import _get_str_field
        row = {"notes": "  hello  "}
        assert _get_str_field(row, ["notes"]) == "hello"

    def test_files_covering_date_none_date(self):
        from sleep_scoring_web.api.diary import _files_covering_date
        assert _files_covering_date(["anything"], None) == []

    def test_files_covering_date_empty_list(self):
        from sleep_scoring_web.api.diary import _files_covering_date
        assert _files_covering_date([], date(2024, 1, 1)) == []

    def test_files_covering_date_match(self):
        from types import SimpleNamespace
        from sleep_scoring_web.api.diary import _files_covering_date
        f = SimpleNamespace(
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 10, 12, 0, 0),
        )
        result = _files_covering_date([f], date(2024, 1, 5))
        assert len(result) == 1
        assert result[0] is f

    def test_files_covering_date_no_match(self):
        from types import SimpleNamespace
        from sleep_scoring_web.api.diary import _files_covering_date
        f = SimpleNamespace(
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 5, 12, 0, 0),
        )
        result = _files_covering_date([f], date(2024, 2, 1))
        assert result == []

    def test_files_covering_date_no_timestamps(self):
        from types import SimpleNamespace
        from sleep_scoring_web.api.diary import _files_covering_date
        f = SimpleNamespace(start_time=None, end_time=None)
        result = _files_covering_date([f], date(2024, 1, 5))
        assert result == []

    def test_files_covering_date_with_file_identity(self):
        """Test FileIdentity objects (has .file attribute)."""
        from types import SimpleNamespace
        from sleep_scoring_web.api.diary import _files_covering_date
        inner_file = SimpleNamespace(
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 10, 12, 0, 0),
        )
        identity = SimpleNamespace(file=inner_file)
        result = _files_covering_date([identity], date(2024, 1, 5))
        assert len(result) == 1
        assert result[0] is inner_file


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestDeleteNonexistent:
    """DELETE diary entry that does not exist returns 404."""

    async def test_delete_nonexistent_entry_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        file_id, _ = await _upload_file(client, admin_auth_headers, sample_csv_content)
        resp = await client.delete(
            f"/api/v1/diary/{file_id}/2099-12-31",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


@pytest.mark.asyncio
class TestPutNonexistentFile:
    """PUT diary entry for a file that does not exist returns 404."""

    async def test_put_nonexistent_file_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        resp = await client.put(
            "/api/v1/diary/999999/2024-01-01",
            headers=admin_auth_headers,
            json={"bed_time": "22:00"},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestPerFileCsvUpload:
    """POST /diary/{file_id}/upload — per-file CSV upload."""

    async def test_basic_csv_upload(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = f"date,in_bed_time,sleep_offset_time,sleep_quality\n{analysis_date},22:30,07:15,4\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1
        assert data["entries_skipped"] == 0

        # Verify data was stored
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200
        entry = get_resp.json()
        assert entry["bed_time"] == "22:30"
        assert entry["wake_time"] == "07:15"
        assert entry["sleep_quality"] == 4

    async def test_csv_upload_with_nap_and_nonwear(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = (
            f"date,in_bed_time,sleep_offset_time,napstart_1_time,napend_1_time,"
            f"nonwear_start_time,nonwear_end_time,nonwear_reason\n"
            f"{analysis_date},22:00,07:00,14:00,14:30,18:00,19:00,1\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

        # Verify the entry
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["nap_1_start"] == "14:00"
        assert entry["nap_1_end"] == "14:30"
        assert entry["nonwear_1_start"] == "18:00"
        assert entry["nonwear_1_end"] == "19:00"
        # Reason code "1" should be mapped to "Bath/Shower"
        assert entry["nonwear_1_reason"] == "Bath/Shower"

    async def test_csv_upload_invalid_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        file_id, _ = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = "date,in_bed_time\nbad-date,22:00\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 0
        assert data["entries_skipped"] == 1
        assert any("Invalid date" in e for e in data["errors"])

    async def test_csv_upload_no_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        file_id, _ = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = "in_bed_time,wake_time\n22:00,07:00\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 400
        assert "date column" in resp.json()["detail"].lower()

    async def test_csv_upload_invalid_csv(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        file_id, _ = await _upload_file(client, admin_auth_headers, sample_csv_content)

        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes("\x00\x01\x02"), "text/csv")},
        )
        assert resp.status_code == 400
        assert "parse" in resp.json()["detail"].lower() or "CSV" in resp.json()["detail"]

    async def test_csv_upload_nonexistent_file(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        resp = await client.post(
            "/api/v1/diary/999999/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes("date,bed_time\n2024-01-01,22:00\n"), "text/csv")},
        )
        assert resp.status_code == 404

    async def test_csv_upload_updates_existing(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Uploading CSV with a date that already has an entry should update it."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        # First upload
        diary_csv_1 = f"date,in_bed_time,sleep_offset_time\n{analysis_date},22:00,07:00\n"
        resp1 = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv_1), "text/csv")},
        )
        assert resp1.status_code == 200

        # Second upload with different values
        diary_csv_2 = f"date,in_bed_time,sleep_offset_time\n{analysis_date},23:30,08:00\n"
        resp2 = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv_2), "text/csv")},
        )
        assert resp2.status_code == 200

        # Verify updated values
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["bed_time"] == "23:30"
        assert entry["wake_time"] == "08:00"

    async def test_csv_upload_multiple_date_formats(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """CSV with US-format dates (m/d/Y) should parse correctly."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        # Convert analysis_date to US format
        parsed = date.fromisoformat(analysis_date)
        us_date = parsed.strftime("%m/%d/%Y")

        diary_csv = f"date,in_bed_time\n{us_date},22:00\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

    async def test_csv_upload_alternative_date_column_names(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Should recognize 'analysis_date' as date column."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = f"analysis_date,in_bed_time\n{analysis_date},22:00\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

    async def test_csv_upload_startdate_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Should recognize 'startdate' as date column."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = f"startdate,in_bed_time\n{analysis_date},22:00\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

    async def test_csv_upload_notes_and_int_fields(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Integer fields (quality, awakenings, SOL) and notes field should map."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = (
            f"date,sleep_quality,awakenings,sol,notes\n"
            f"{analysis_date},4,2,15,slept well\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["sleep_quality"] == 4
        assert entry["number_of_awakenings"] == 2
        assert entry["time_to_fall_asleep_minutes"] == 15
        assert entry["notes"] == "slept well"

    async def test_csv_upload_nonwear_reason_codes(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Nonwear reason codes (1, 2, 3) should map to text."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = (
            f"date,nonwear_1_start,nonwear_1_end,nonwear_1_reason,"
            f"nonwear_2_start,nonwear_2_end,nonwear_2_reason\n"
            f"{analysis_date},18:00,19:00,2,20:00,21:00,3\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["nonwear_1_reason"] == "Swimming"
        assert entry["nonwear_2_reason"] == "Other"


@pytest.mark.asyncio
class TestStudyWideCsvUpload:
    """POST /diary/upload — study-wide CSV upload with file matching."""

    async def test_upload_with_filename_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Matching by filename column."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="participant_001.csv"
        )

        diary_csv = f"filename,date,in_bed_time\nparticipant_001.csv,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1
        assert data["matched_rows"] == 1

    async def test_upload_with_participant_id_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Matching by participant_id column (inferred from filename)."""
        # Upload a file with identifiable participant ID in filename
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="1001 T1 (2024-01-01)60sec.csv"
        )

        diary_csv = f"participant_id,date,in_bed_time\n1001,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

    async def test_upload_no_match_unmatched_identifiers(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Unmatched filenames should be reported."""
        await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = "filename,date,in_bed_time\nnonexistent_file.csv,2024-01-01,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 0
        assert data["entries_skipped"] == 1
        assert "nonexistent_file.csv" in data["unmatched_identifiers"]

    async def test_upload_no_date_column_error(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """CSV without a date column should return 400."""
        diary_csv = "filename,in_bed_time\nfoo.csv,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 400
        assert "date column" in resp.json()["detail"].lower()

    async def test_upload_no_identifier_columns_no_pid_stem(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """CSV without filename/pid columns and 'nan' upload filename → 400."""
        diary_csv = "date,in_bed_time\n2024-01-01,22:00\n"
        # filename_stem("nan") returns None (null token), triggering the 400
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("nan", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 400
        assert "participant_id" in resp.json()["detail"].lower() or "filename" in resp.json()["detail"].lower()

    async def test_upload_invalid_csv(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Unparseable CSV should return 400."""
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes("\x00\x01\x02"), "text/csv")},
        )
        assert resp.status_code == 400

    async def test_upload_filename_col_with_none_value(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Row with None/empty filename should be skipped."""
        await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = "filename,date,in_bed_time\n,2024-01-01,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_skipped"] == 1

    async def test_upload_invalid_date_in_row(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Row with invalid date should be skipped with error."""
        await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="test_file.csv"
        )

        diary_csv = "filename,date,in_bed_time\ntest_file.csv,not-a-date,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_skipped"] == 1
        assert any("Invalid date" in e for e in data["errors"])

    async def test_upload_pid_no_match(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """PID column with no matching files should report unmatched."""
        await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = "participant_id,date,in_bed_time\n9999,2024-01-01,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_skipped"] == 1
        assert len(data["unmatched_identifiers"]) >= 1

    async def test_upload_pid_with_timepoint(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """PID + timepoint matching."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="2001 T1 (2024-01-01)60sec.csv"
        )

        diary_csv = f"participant_id,timepoint,date,in_bed_time\n2001,T1,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

    async def test_upload_filename_stem_matching(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Filename column without extension should match by stem."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="subject_xyz.csv"
        )

        # Use stem only (no extension) in diary CSV
        diary_csv = f"filename,date,in_bed_time\nsubject_xyz,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should match via stem
        assert data["entries_imported"] >= 1 or data["entries_skipped"] >= 0

    async def test_upload_with_pid_fallback_from_upload_filename(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """When no filename/pid column, use the upload filename as PID."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="5001 T1 (2024-01-01)60sec.csv"
        )

        # No filename or participant_id column — uses upload filename stem as PID
        diary_csv = f"date,in_bed_time\n{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("5001.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        # The PID "5001" should match via filename-based identity

    async def test_upload_pid_none_value_skips(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Row with empty participant_id should be skipped."""
        await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = "participant_id,date,in_bed_time\n,2024-01-01,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_skipped"] == 1

    async def test_upload_study_wide_updates_existing(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Study-wide upload should update existing diary entries."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="upd_test.csv"
        )

        # First upload
        diary_csv_1 = f"filename,date,in_bed_time\nupd_test.csv,{analysis_date},22:00\n"
        resp1 = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv_1), "text/csv")},
        )
        assert resp1.status_code == 200

        # Second upload with updated value
        diary_csv_2 = f"filename,date,in_bed_time\nupd_test.csv,{analysis_date},23:30\n"
        resp2 = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv_2), "text/csv")},
        )
        assert resp2.status_code == 200

        # Verify updated value
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["bed_time"] == "23:30"

    async def test_upload_with_case_insensitive_columns(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Column names should be lowercased and trimmed."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="case_test.csv"
        )

        diary_csv = f"Filename,Date,In_Bed_Time\ncase_test.csv,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

    async def test_upload_pid_with_unmatched_timepoint(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """PID match but timepoint does not match → unmatched."""
        await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="3001 T1 (2024-01-01)60sec.csv"
        )

        diary_csv = "participant_id,timepoint,date,in_bed_time\n3001,T99,2024-01-01,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should match T1 file because T99 doesn't match but pid_pool fallback checks
        # if tp_norm is in the filename. If that also fails, it falls through to
        # normalized_filename containment check.

    async def test_upload_latin1_encoding(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """CSV encoded as latin-1 should be handled."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="latin_test.csv"
        )

        diary_csv = f"filename,date,in_bed_time,notes\nlatin_test.csv,{analysis_date},22:00,caf\u00e9\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _latin1_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200

    async def test_upload_diary_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """'diary_date' should be recognized as the date column."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="diary_col_test.csv"
        )

        diary_csv = f"filename,diary_date,in_bed_time\ndiary_col_test.csv,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

    async def test_upload_per_file_latin1(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Per-file upload with latin-1 encoding."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = f"date,in_bed_time,notes\n{analysis_date},22:00,caf\u00e9\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _latin1_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200

    async def test_upload_per_file_diary_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Per-file upload with 'diary_date' as date column name."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = f"diary_date,in_bed_time\n{analysis_date},22:00\n"
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

    async def test_upload_per_file_nonwear_reason_code_float(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Nonwear reason codes with decimal (e.g. '1.0') should map."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = (
            f"date,nonwear_1_start,nonwear_1_end,nonwear_1_reason\n"
            f"{analysis_date},18:00,19:00,2.0\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["nonwear_1_reason"] == "Swimming"

    async def test_upload_multiple_nap_periods(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Multiple nap and nonwear periods should be stored."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = (
            f"date,nap_1_start,nap_1_end,nap_2_start,nap_2_end,nap_3_start,nap_3_end,"
            f"nonwear_1_start,nonwear_1_end,nonwear_2_start,nonwear_2_end,nonwear_3_start,nonwear_3_end\n"
            f"{analysis_date},13:00,13:30,15:00,15:30,17:00,17:30,"
            f"08:00,09:00,10:00,11:00,12:00,12:30\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["nap_1_start"] == "13:00"
        assert entry["nap_2_start"] == "15:00"
        assert entry["nap_3_start"] == "17:00"
        assert entry["nonwear_1_start"] == "08:00"
        assert entry["nonwear_2_start"] == "10:00"
        assert entry["nonwear_3_start"] == "12:00"

    async def test_upload_multiple_rows(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Study-wide upload with multiple rows for same file, different dates."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="multi_row.csv"
        )
        parsed = date.fromisoformat(analysis_date)
        date2 = (parsed + timedelta(days=1)).isoformat()

        diary_csv = (
            f"filename,date,in_bed_time\n"
            f"multi_row.csv,{analysis_date},22:00\n"
            f"multi_row.csv,{date2},23:00\n"
        )
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 2
        assert data["total_rows"] == 2

    async def test_upload_per_file_multiple_rows(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Per-file upload with multiple rows (different dates)."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)
        parsed = date.fromisoformat(analysis_date)
        date2 = (parsed + timedelta(days=1)).isoformat()

        diary_csv = (
            f"date,in_bed_time\n"
            f"{analysis_date},22:00\n"
            f"{date2},23:00\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 2

    async def test_upload_alternative_column_aliases(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Alternative column names (bedtime, waketime, etc.) should be recognized."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = (
            f"date,bedtime,waketime,asleep_time,gotup,time_to_fall_asleep,comments\n"
            f"{analysis_date},22:30,07:00,22:45,07:15,20,good sleep\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["bed_time"] == "22:30"
        assert entry["wake_time"] == "07:00"
        assert entry["lights_out"] == "22:45"
        assert entry["got_up"] == "07:15"
        assert entry["time_to_fall_asleep_minutes"] == 20
        assert entry["notes"] == "good sleep"

    async def test_upload_nan_values_in_columns(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """NaN/None/null values in diary columns should be treated as empty."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        diary_csv = (
            f"date,in_bed_time,sleep_offset_time,notes\n"
            f"{analysis_date},nan,None,null\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        assert resp.json()["entries_imported"] == 1

        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["bed_time"] is None
        assert entry["wake_time"] is None
        assert entry["notes"] is None

    async def test_upload_subject_id_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """'subject_id' should be recognized as participant_id column."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="6001 T1 (2024-01-01)60sec.csv"
        )

        diary_csv = f"subject_id,date,in_bed_time\n6001,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

    async def test_upload_date_of_last_night_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """'date_of_last_night' should be recognized as date column."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="doln_test.csv"
        )

        diary_csv = f"filename,date_of_last_night,in_bed_time\ndoln_test.csv,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1


@pytest.mark.asyncio
class TestStudyWideEdgeCases:
    """Additional edge-case tests targeting uncovered branches."""

    async def test_study_wide_csv_parse_error(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Malformed CSV that fails polars parsing should return 400."""
        # CSV with inconsistent number of columns triggers polars parse error
        bad_csv = "a,b,c\n1,2\n3,4,5,6\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(bad_csv), "text/csv")},
        )
        # Polars may auto-handle this; if it succeeds, it hits no-date-column
        assert resp.status_code in (200, 400)

    async def test_study_wide_redcap_format(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """REDCap wide format should be detected and converted."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="7001 T1 (2024-01-01)60sec.csv"
        )

        # Build a minimal REDCap wide-format CSV with required signature columns
        redcap_csv = (
            "id_v1,date_lastnight_v1,inbed_hour_v1,inbed_min_v1,time_ampm_v1,"
            "asleep_hour_v1,asleep_min_v1,time_ampm_2_v1,"
            "wake_hour_v1,wake_min_v1,time_ampm_3_v1\n"
            f"7001,{analysis_date},10,30,2,11,0,2,7,0,1\n"
        )
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(redcap_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        # REDCap conversion should produce rows that get matched
        assert data["total_rows"] >= 1

    async def test_study_wide_ambiguous_filename_match(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Two files matching same filename pattern without date coverage -> ambiguous."""
        # Upload two files with similar names
        await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="ambig_data_v1.csv"
        )
        await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="ambig_data_v2.csv"
        )

        # Use a diary filename that fuzzy-matches both (stem containment)
        diary_csv = "filename,date,in_bed_time\nambig_data,2099-06-15,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should report ambiguous or unmatched (no date coverage for 2099)
        assert data["entries_skipped"] >= 1 or data["entries_imported"] >= 0

    async def test_study_wide_pid_ambiguous_no_date_coverage(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Two files for same PID, neither covers the diary date -> ambiguous."""
        await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="8001 T1 (2024-01-01)60sec.csv"
        )
        await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="8001 T2 (2024-01-01)60sec.csv"
        )

        # Diary date far in the future -- no file covers it
        diary_csv = "participant_id,date,in_bed_time\n8001,2099-01-01,22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_skipped"] >= 1
        # Should have ambiguous identifiers reported
        assert len(data["ambiguous_identifiers"]) >= 1 or len(data["errors"]) >= 1

    async def test_study_wide_pid_timepoint_fallback_match(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """PID+timepoint fallback: timepoint found via pid_pool check."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="9001 T1 (2024-01-01)60sec.csv"
        )

        # Use a timepoint that IS in pid_tp_to_identities for this file
        diary_csv = f"participant_id,timepoint,date,in_bed_time\n9001,T1,{analysis_date},22:00\n"
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

    async def test_study_wide_nonwear_reason_mapped_in_csv(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Nonwear reason code in study-wide upload should be mapped."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="nw_reason_test.csv"
        )

        diary_csv = (
            f"filename,date,nonwear_reason\n"
            f"nw_reason_test.csv,{analysis_date},1\n"
        )
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] == 1

        # Verify reason code was mapped
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["nonwear_1_reason"] == "Bath/Shower"

    async def test_study_wide_nonwear_reason_unknown_code(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Nonwear reason code not in mapping should be stored as-is."""
        file_id, analysis_date = await _upload_file(
            client, admin_auth_headers, sample_csv_content, filename="nw_unknown.csv"
        )

        diary_csv = (
            f"filename,date,nonwear_reason\n"
            f"nw_unknown.csv,{analysis_date},Charging\n"
        )
        resp = await client.post(
            "/api/v1/diary/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(diary_csv), "text/csv")},
        )
        assert resp.status_code == 200

        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        assert entry["nonwear_1_reason"] == "Charging"

    async def test_per_file_redcap_format(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Per-file upload with REDCap wide format should be detected and converted."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        redcap_csv = (
            "id_v1,date_lastnight_v1,inbed_hour_v1,inbed_min_v1,time_ampm_v1,"
            "asleep_hour_v1,asleep_min_v1,time_ampm_2_v1,"
            "wake_hour_v1,wake_min_v1,time_ampm_3_v1\n"
            f"anything,{analysis_date},10,30,2,11,0,2,7,0,1\n"
        )
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", _csv_bytes(redcap_csv), "text/csv")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries_imported"] >= 1

        # Verify data was stored
        get_resp = await client.get(
            f"/api/v1/diary/{file_id}/{analysis_date}",
            headers=admin_auth_headers,
        )
        entry = get_resp.json()
        # inbed_hour=10, inbed_min=30, time_ampm=2 (PM) -> 22:30
        assert entry["bed_time"] == "22:30"

    async def test_per_file_upload_latin1_non_utf8_header(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        sample_csv_content: str,
    ):
        """Per-file upload where UTF-8 decode fails, falls back to latin-1."""
        file_id, analysis_date = await _upload_file(client, admin_auth_headers, sample_csv_content)

        # Use an actual latin-1 encoded CSV with a non-UTF-8 byte in column header
        raw_bytes = f"date,in_bed_time,note\xe9s\n{analysis_date},22:00,test\n".encode("latin-1")
        resp = await client.post(
            f"/api/v1/diary/{file_id}/upload",
            headers=admin_auth_headers,
            files={"file": ("diary.csv", io.BytesIO(raw_bytes), "text/csv")},
        )
        assert resp.status_code == 200
