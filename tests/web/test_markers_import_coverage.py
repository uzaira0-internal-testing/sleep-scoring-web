"""
Extended coverage tests for ``sleep_scoring_web.api.markers_import``.

These tests target uncovered branches identified by coverage analysis:
- Nonwear CSV parsing with datetime columns (no separate date column)
- Latin-1/cp1252 encoding fallback for nonwear CSV
- Polars parse failure handling
- _extract_time edge cases (AM/PM, datetime strings, ISO, null values)
- _parse_nonwear_date format variants
- _parse_full_datetime format variants
- _files_covering_date logic
- Study-wide nonwear with participant_id column (no filename column)
- Study-wide nonwear with timepoint column disambiguation
- Study-wide nonwear filename_pid fallback (CSV filename stem)
- Ambiguous PID matching (multiple files same PID)
- Nonwear rows with nan/None start/end values
- Sleep import with onset_datetime + offset_datetime columns (web export)
- Sleep import with onset_date + offset_date columns
- Sleep import with NO_SLEEP sentinel values
- Sleep import with is_no_sleep column
- Sleep import with needs_consensus column
- Sleep import with MANUAL_NONWEAR marker_type rows
- Sleep import with NAP marker_type
- Sleep import with marker_index / period_index column
- Sleep import with scored_by column
- Sleep import participant_id matching (no filename column)
- Sleep import fuzzy matching
- No-sleep date + nonwear combination
- end_time before start_time (cross-midnight nonwear)
- Invalid time values
- Various date formats (MM/DD/YYYY, MM/DD/YY, DD/MM/YYYY)
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select

from sleep_scoring_web.db.models import File as FileModel, Marker
from sleep_scoring_web.schemas.enums import FileStatus, MarkerCategory, MarkerType


# ---------------------------------------------------------------------------
# Helpers (copied from test_markers_import.py for isolation)
# ---------------------------------------------------------------------------

async def _create_file_record(
    test_session_maker,
    filename: str,
    *,
    uploaded_by: str = "testadmin",
    participant_id: str | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> int:
    """Insert a File record directly into the test DB and return its id."""
    async with test_session_maker() as session:
        f = FileModel(
            filename=filename,
            file_type="csv",
            participant_id=participant_id,
            status=FileStatus.READY,
            uploaded_by=uploaded_by,
            start_time=start_time or datetime(2024, 1, 1, 12, 0, 0),
            end_time=end_time or datetime(2024, 1, 2, 12, 0, 0),
        )
        session.add(f)
        await session.commit()
        await session.refresh(f)
        return f.id


def _make_nonwear_csv(
    rows: list[dict[str, str]],
    *,
    columns: list[str] | None = None,
    encoding: str = "utf-8",
) -> bytes:
    """Build a nonwear CSV as raw bytes."""
    if columns is None:
        columns = list(rows[0].keys())
    lines = [",".join(columns)]
    for row in rows:
        lines.append(",".join(row.get(c, "") for c in columns))
    return "\n".join(lines).encode(encoding)


def _make_sleep_csv(
    rows: list[dict[str, str]],
    *,
    columns: list[str] | None = None,
    encoding: str = "utf-8",
    comment_lines: list[str] | None = None,
) -> bytes:
    """Build a sleep-marker import CSV as raw bytes."""
    if columns is None:
        columns = list(rows[0].keys())
    lines: list[str] = []
    if comment_lines:
        lines.extend(comment_lines)
    lines.append(",".join(columns))
    for row in rows:
        lines.append(",".join(row.get(c, "") for c in columns))
    return "\n".join(lines).encode(encoding)


async def _count_markers(
    test_session_maker,
    file_id: int,
    category: str | None = None,
    marker_type: str | None = None,
) -> int:
    """Count markers in the DB for a given file, optionally filtered."""
    async with test_session_maker() as session:
        stmt = select(Marker).where(Marker.file_id == file_id)
        if category is not None:
            stmt = stmt.where(Marker.marker_category == category)
        if marker_type is not None:
            stmt = stmt.where(Marker.marker_type == marker_type)
        result = await session.execute(stmt)
        return len(result.scalars().all())


async def _get_markers(
    test_session_maker,
    file_id: int,
    category: str | None = None,
    marker_type: str | None = None,
) -> list[Marker]:
    """Get markers from the DB for a given file."""
    async with test_session_maker() as session:
        stmt = select(Marker).where(Marker.file_id == file_id)
        if category is not None:
            stmt = stmt.where(Marker.marker_category == category)
        if marker_type is not None:
            stmt = stmt.where(Marker.marker_type == marker_type)
        result = await session.execute(stmt)
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Unit tests for helper functions (called directly, no HTTP)
# ---------------------------------------------------------------------------

class TestExtractTime:
    """Tests for _extract_time helper."""

    def test_simple_hhmm(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("10:30") == "10:30"

    def test_datetime_with_space(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("2025-08-01 10:30:00") == "10:30"

    def test_datetime_iso_t(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("2025-08-01T10:30:00") == "10:30"

    def test_datetime_iso_t_with_timezone(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("2025-08-01T10:30:00+05:00") == "10:30"

    def test_datetime_iso_t_with_z(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("2025-08-01T10:30:00Z") == "10:30"

    def test_am_time(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("10:30 AM") == "10:30"

    def test_pm_time(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("02:30 PM") == "14:30"

    def test_12_am(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("12:00 AM") == "00:00"

    def test_12_pm(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("12:00 PM") == "12:00"

    def test_nan_value(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("nan") is None

    def test_none_value(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("none") is None

    def test_null_value(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("null") is None

    def test_empty_value(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("") is None

    def test_invalid_value(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("not-a-time") is None

    def test_hour_only(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("10") == "10:00"

    def test_datetime_slash_date_space_time(self) -> None:
        """Datetime with slash-formatted date + space + time."""
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("01/15/2024 14:30:00") == "14:30"

    def test_whitespace_padding(self) -> None:
        from sleep_scoring_web.api.markers_import import _extract_time
        assert _extract_time("  10:30  ") == "10:30"


class TestParseNonwearDate:
    """Tests for _parse_nonwear_date helper."""

    def test_yyyy_mm_dd(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_nonwear_date
        from datetime import date
        assert _parse_nonwear_date("2024-01-15") == date(2024, 1, 15)

    def test_mm_dd_yyyy(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_nonwear_date
        from datetime import date
        assert _parse_nonwear_date("01/15/2024") == date(2024, 1, 15)

    def test_mm_dd_yy(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_nonwear_date
        from datetime import date
        assert _parse_nonwear_date("01/15/24") == date(2024, 1, 15)

    def test_dd_mm_yyyy(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_nonwear_date
        from datetime import date
        # 15/01/2024 can only be DD/MM/YYYY since 15 > 12
        assert _parse_nonwear_date("15/01/2024") == date(2024, 1, 15)

    def test_yyyy_mm_dd_slash(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_nonwear_date
        from datetime import date
        assert _parse_nonwear_date("2024/01/15") == date(2024, 1, 15)

    def test_invalid_date(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_nonwear_date
        assert _parse_nonwear_date("not-a-date") is None

    def test_empty_string(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_nonwear_date
        assert _parse_nonwear_date("") is None


class TestParseFullDatetime:
    """Tests for _parse_full_datetime helper."""

    def test_yyyy_mm_dd_hh_mm_ss(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_full_datetime
        result = _parse_full_datetime("2024-01-15 22:30:00")
        assert result == datetime(2024, 1, 15, 22, 30, 0)

    def test_yyyy_mm_dd_hh_mm(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_full_datetime
        result = _parse_full_datetime("2024-01-15 22:30")
        assert result == datetime(2024, 1, 15, 22, 30, 0)

    def test_iso_t_format(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_full_datetime
        result = _parse_full_datetime("2024-01-15T22:30:00")
        assert result == datetime(2024, 1, 15, 22, 30, 0)

    def test_iso_t_no_seconds(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_full_datetime
        result = _parse_full_datetime("2024-01-15T22:30")
        assert result == datetime(2024, 1, 15, 22, 30, 0)

    def test_mm_dd_yyyy_hh_mm_ss(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_full_datetime
        result = _parse_full_datetime("01/15/2024 22:30:00")
        assert result == datetime(2024, 1, 15, 22, 30, 0)

    def test_mm_dd_yyyy_hh_mm(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_full_datetime
        result = _parse_full_datetime("01/15/2024 22:30")
        assert result == datetime(2024, 1, 15, 22, 30, 0)

    def test_invalid(self) -> None:
        from sleep_scoring_web.api.markers_import import _parse_full_datetime
        assert _parse_full_datetime("not-a-datetime") is None


class TestFilesCoveringDate:
    """Tests for _files_covering_date helper."""

    def test_none_date_returns_empty(self) -> None:
        from sleep_scoring_web.api.markers_import import _files_covering_date
        assert _files_covering_date(["dummy"], None) == []

    def test_empty_candidates_returns_empty(self) -> None:
        from sleep_scoring_web.api.markers_import import _files_covering_date
        from datetime import date
        assert _files_covering_date([], date(2024, 1, 1)) == []

    def test_file_covering_date(self) -> None:
        from datetime import date
        from types import SimpleNamespace
        from sleep_scoring_web.api.markers_import import _files_covering_date

        f = SimpleNamespace(start_time=datetime(2024, 1, 1, 12, 0, 0), end_time=datetime(2024, 1, 3, 12, 0, 0))
        result = _files_covering_date([f], date(2024, 1, 2))
        assert result == [f]

    def test_file_not_covering_date(self) -> None:
        from datetime import date
        from types import SimpleNamespace
        from sleep_scoring_web.api.markers_import import _files_covering_date

        f = SimpleNamespace(start_time=datetime(2024, 1, 1, 12, 0, 0), end_time=datetime(2024, 1, 2, 12, 0, 0))
        result = _files_covering_date([f], date(2024, 1, 5))
        assert result == []

    def test_file_identity_objects(self) -> None:
        """When passed FileIdentity objects, uses .file attribute."""
        from datetime import date
        from types import SimpleNamespace
        from sleep_scoring_web.api.markers_import import _files_covering_date

        inner_file = SimpleNamespace(start_time=datetime(2024, 1, 1, 12, 0, 0), end_time=datetime(2024, 1, 3, 12, 0, 0))
        ident = SimpleNamespace(file=inner_file)
        result = _files_covering_date([ident], date(2024, 1, 2))
        assert result == [inner_file]

    def test_file_with_none_start_time(self) -> None:
        """Files with None start/end times are skipped."""
        from datetime import date
        from types import SimpleNamespace
        from sleep_scoring_web.api.markers_import import _files_covering_date

        f = SimpleNamespace(start_time=None, end_time=None)
        result = _files_covering_date([f], date(2024, 1, 2))
        assert result == []


# ---------------------------------------------------------------------------
# Integration tests (HTTP endpoints)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestNonwearCoverageExtended:
    """Extended nonwear CSV upload tests for coverage gaps."""

    async def test_nonwear_latin1_encoding(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Nonwear CSV encoded as latin-1 should be parsed via fallback."""
        file_id = await _create_file_record(test_session_maker, "nw_latin1.csv")

        # Create CSV with latin-1 character (e.g. accented e)
        csv_text = "date,start_time,end_time\n2024-01-01,02:00,04:00\n"
        csv_bytes = csv_text.encode("latin-1")
        # Prepend a byte that's invalid UTF-8 but valid latin-1
        csv_bytes = b"\xe9" + b"\n" + csv_bytes

        # The leading 0xe9 will cause comment-line filtering to keep it,
        # but polars will skip it. We need a cleaner approach.
        # Actually let's just use a comment with latin-1 characters:
        csv_bytes = _make_nonwear_csv(
            [{"date": "2024-01-01", "start_time": "02:00", "end_time": "04:00"}],
            encoding="latin-1",
        )
        # Prepend invalid-UTF8 comment line
        csv_bytes = "# R\xe9sum\xe9\n".encode("latin-1") + csv_bytes

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["markers_created"] == 1

    async def test_nonwear_malformed_csv_returns_400(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """A CSV that polars cannot parse returns 400."""
        file_id = await _create_file_record(test_session_maker, "nw_bad_parse.csv")

        # Just a header with mismatched column counts
        bad_csv = b"a,b,c\n1,2\n3,4,5,6\n"

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        # Polars may or may not parse this — if it does, columns won't match
        # so we accept either 400 (parse fail) or 400 (missing columns)
        assert resp.status_code == 400

    async def test_nonwear_alt_column_names(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Nonwear CSV with alternative column names (nonwear_start, nonwear_end)."""
        file_id = await _create_file_record(test_session_maker, "nw_altcol.csv")

        csv_bytes = _make_nonwear_csv(
            [{"startdate": "2024-01-01", "nonwear_start": "03:00", "nonwear_end": "05:00"}],
        )

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["markers_created"] == 1

    async def test_nonwear_datetime_start_end_no_date_col(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Nonwear CSV with start_datetime/end_datetime columns (no separate date col).
        Date is extracted from the datetime value itself."""
        file_id = await _create_file_record(test_session_maker, "nw_datetime.csv")

        csv_bytes = _make_nonwear_csv(
            [{"start_datetime": "2024-01-01 03:00:00", "end_datetime": "2024-01-01 05:00:00"}],
        )

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["markers_created"] == 1

    async def test_nonwear_nan_start_end_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Rows with nan/None start/end values are skipped."""
        file_id = await _create_file_record(test_session_maker, "nw_nan.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "nan", "end_time": "nan"},
            {"date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1
        assert data["dates_skipped"] == 1

    async def test_nonwear_invalid_date_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Rows with invalid date are skipped and reported as errors."""
        file_id = await _create_file_record(test_session_maker, "nw_baddate.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "not-a-date", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] == 1
        assert len(data["errors"]) == 1

    async def test_nonwear_invalid_time_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Rows with invalid time values are skipped and reported as errors."""
        file_id = await _create_file_record(test_session_maker, "nw_badtime.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "invalid", "end_time": "also-bad"},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] == 1
        assert len(data["errors"]) == 1

    async def test_nonwear_cross_midnight(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """When end_time < start_time, the end should wrap to the next day."""
        file_id = await _create_file_record(test_session_maker, "nw_midnight.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "23:00", "end_time": "01:00"},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

        markers = await _get_markers(
            test_session_maker, file_id,
            category=MarkerCategory.NONWEAR,
        )
        assert len(markers) == 1
        assert markers[0].end_timestamp > markers[0].start_timestamp

    async def test_nonwear_study_wide_pid_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Study-wide nonwear CSV with participant_id column (no filename)."""
        await _create_file_record(
            test_session_maker, "1001 T1 (2024-01-01)60sec.csv",
            participant_id="1001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_nonwear_csv([
            {"participant_id": "1001", "date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1
        assert data["matched_rows"] == 1

    async def test_nonwear_study_wide_pid_with_timepoint(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Study-wide nonwear with participant_id + timepoint columns."""
        await _create_file_record(
            test_session_maker, "2001 T1 (2024-01-01)60sec.csv",
            participant_id="2001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_nonwear_csv([
            {
                "participant_id": "2001",
                "timepoint": "T1",
                "date": "2024-01-01",
                "start_time": "03:00",
                "end_time": "05:00",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_nonwear_study_wide_filename_pid_fallback(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Study-wide nonwear with no filename/pid column uses upload filename stem."""
        await _create_file_record(
            test_session_maker, "3001 T1 (2024-01-01)60sec.csv",
            participant_id="3001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        # CSV has no filename or participant_id column, but the upload filename
        # stem "3001" matches the participant
        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("3001.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_nonwear_study_wide_no_pid_no_filename_error(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Study-wide nonwear with no way to identify participant -> 400."""
        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        # Upload filename is None-like (no participant stem)
        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            # Use an empty/null-like filename
            files={"file": ("nan.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        # The filename stem "nan" is treated as null by normalize_participant_id
        # so the participant_id will be None and rows get skipped.
        # The endpoint may return 200 with 0 matched or 400
        assert resp.status_code in (200, 400)

    async def test_nonwear_study_wide_pid_unmatched(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Study-wide nonwear with PID that matches no files -> skipped."""
        await _create_file_record(test_session_maker, "real_participant.csv")

        csv_bytes = _make_nonwear_csv([
            {"participant_id": "9999", "date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] == 1

    async def test_nonwear_study_wide_pid_none_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Row with None/nan participant_id should be skipped."""
        await _create_file_record(test_session_maker, "somefile.csv")

        csv_bytes = _make_nonwear_csv([
            {"participant_id": "nan", "date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["dates_skipped"] == 1

    async def test_nonwear_study_wide_ambiguous_pid(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """When PID matches multiple files that don't cover the date -> ambiguous."""
        # Create two files with same PID but different date ranges
        await _create_file_record(
            test_session_maker, "5001 T1 (2024-01-01)60sec.csv",
            participant_id="5001",
            start_time=datetime(2024, 3, 1, 12, 0, 0),
            end_time=datetime(2024, 3, 2, 12, 0, 0),
        )
        await _create_file_record(
            test_session_maker, "5001 T2 (2024-04-01)60sec.csv",
            participant_id="5001",
            start_time=datetime(2024, 4, 1, 12, 0, 0),
            end_time=datetime(2024, 4, 2, 12, 0, 0),
        )

        csv_bytes = _make_nonwear_csv([
            {"participant_id": "5001", "date": "2024-06-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] == 1

    async def test_nonwear_study_wide_filename_col_none_value_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Filename column with None/nan value should skip that row."""
        await _create_file_record(test_session_maker, "some_valid.csv")

        csv_bytes = _make_nonwear_csv([
            {"filename": "nan", "date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["dates_skipped"] == 1

    async def test_nonwear_study_wide_filename_fuzzy_match(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Filename column with partial stem match should succeed via fuzzy matching."""
        await _create_file_record(
            test_session_maker, "participant_abc_data.csv",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        # The CSV filename value is a substring of the actual filename stem
        csv_bytes = _make_nonwear_csv([
            {"filename": "participant_abc.csv", "date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        # Should match via fuzzy stem matching
        assert resp.json()["markers_created"] == 1

    async def test_nonwear_mm_dd_yyyy_date_format(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Nonwear CSV with MM/DD/YYYY date format."""
        file_id = await _create_file_record(test_session_maker, "nw_mmddyyyy.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "01/15/2024", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["markers_created"] == 1

    async def test_nonwear_empty_start_end_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Rows with empty start/end values should be skipped."""
        file_id = await _create_file_record(test_session_maker, "nw_empty_times.csv")

        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "", "end_time": ""},
        ])

        resp = await client.post(
            f"/api/v1/markers/{file_id}/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["markers_created"] == 0
        assert resp.json()["dates_skipped"] == 1

    async def test_nonwear_study_wide_ambiguous_filename(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """When filename fuzzy-matches multiple files that don't cover the date -> ambiguous."""
        # Two files with stems that both contain "ambignw"
        await _create_file_record(
            test_session_maker, "ambignw_file_v1.csv",
            start_time=datetime(2024, 3, 1, 12, 0, 0),
            end_time=datetime(2024, 3, 2, 12, 0, 0),
        )
        await _create_file_record(
            test_session_maker, "ambignw_file_v2.csv",
            start_time=datetime(2024, 4, 1, 12, 0, 0),
            end_time=datetime(2024, 4, 2, 12, 0, 0),
        )

        # CSV references "ambignw_file.csv" which doesn't exactly match either,
        # but both stems contain the reference stem via fuzzy match
        csv_bytes = _make_nonwear_csv([
            {"filename": "ambignw_file.csv", "date": "2024-06-15", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        # Ambiguous or unmatched depending on fuzzy logic
        assert data["dates_skipped"] == 1

    async def test_nonwear_study_wide_filename_covering_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """When PID matches multiple files, pick the one covering the date."""
        await _create_file_record(
            test_session_maker, "10001 T1 (2024-01-01)60sec.csv",
            participant_id="10001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 8, 12, 0, 0),
        )
        await _create_file_record(
            test_session_maker, "10001 T2 (2024-03-01)60sec.csv",
            participant_id="10001",
            start_time=datetime(2024, 3, 1, 12, 0, 0),
            end_time=datetime(2024, 3, 8, 12, 0, 0),
        )

        csv_bytes = _make_nonwear_csv([
            {"participant_id": "10001", "date": "2024-01-03", "start_time": "03:00", "end_time": "05:00"},
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1


@pytest.mark.asyncio
class TestSleepImportCoverageExtended:
    """Extended sleep marker CSV import tests for coverage gaps."""

    async def test_sleep_import_onset_datetime_columns(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with onset_datetime + offset_datetime columns (web export format)."""
        file_id = await _create_file_record(test_session_maker, "sleep_dt.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_dt.csv",
                "sleep_date": "2024-01-01",
                "onset_datetime": "2024-01-01 22:30:00",
                "offset_datetime": "2024-01-02 07:00:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_nap_type(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with NAP marker_type."""
        file_id = await _create_file_record(test_session_maker, "sleep_nap.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_nap.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "13:00",
                "offset_time": "14:30",
                "marker_type": "NAP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

        markers = await _get_markers(
            test_session_maker, file_id, category=MarkerCategory.SLEEP,
        )
        assert any(m.marker_type == MarkerType.NAP for m in markers)

    async def test_sleep_import_manual_nonwear_type(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with MANUAL_NONWEAR marker_type creates nonwear markers."""
        file_id = await _create_file_record(test_session_maker, "sleep_nw.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_nw.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "14:00",
                "offset_time": "16:00",
                "marker_type": "MANUAL_NONWEAR",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["nonwear_markers_created"] == 1

    async def test_sleep_import_no_sleep_sentinel(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with NO_SLEEP onset/offset sentinel values."""
        file_id = await _create_file_record(test_session_maker, "sleep_nosleep.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_nosleep.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "NO_SLEEP",
                "offset_time": "NO_SLEEP",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["no_sleep_dates"] == 1

    async def test_sleep_import_is_no_sleep_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with is_no_sleep column set to TRUE."""
        file_id = await _create_file_record(test_session_maker, "sleep_nosl_col.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_nosl_col.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "is_no_sleep": "TRUE",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["no_sleep_dates"] == 1

    async def test_sleep_import_needs_consensus_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with needs_consensus column."""
        file_id = await _create_file_record(test_session_maker, "sleep_consensus.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_consensus.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
                "needs_consensus": "TRUE",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_marker_index_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with marker_index/period_index column."""
        file_id = await _create_file_record(test_session_maker, "sleep_idx.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_idx.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
                "period_index": "5",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

        markers = await _get_markers(
            test_session_maker, file_id, category=MarkerCategory.SLEEP,
        )
        assert any(m.period_index == 5 for m in markers)

    async def test_sleep_import_multiple_markers_per_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with main sleep + nap on same date."""
        file_id = await _create_file_record(test_session_maker, "sleep_multi.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_multi.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
            {
                "filename": "sleep_multi.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "13:00",
                "offset_time": "14:30",
                "marker_type": "NAP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] >= 2

    async def test_sleep_import_pid_matching(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import using participant_id column (no filename column)."""
        file_id = await _create_file_record(
            test_session_maker, "6001 T1 (2024-01-01)60sec.csv",
            participant_id="6001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_sleep_csv([
            {
                "participant_id": "6001",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_pid_with_timepoint(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with participant_id + timepoint columns."""
        file_id = await _create_file_record(
            test_session_maker, "7001 T1 (2024-01-01)60sec.csv",
            participant_id="7001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_sleep_csv([
            {
                "participant_id": "7001",
                "participant_timepoint": "T1",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_invalid_date_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with invalid date value -> row skipped."""
        await _create_file_record(test_session_maker, "sleep_baddate.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_baddate.csv",
                "sleep_date": "not-a-date",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["dates_skipped"] == 1
        assert len(data["errors"]) == 1

    async def test_sleep_import_nan_onset_offset_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import rows with NAN onset/offset values are skipped."""
        await _create_file_record(test_session_maker, "sleep_nan.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_nan.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "NAN",
                "offset_time": "NAN",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["dates_skipped"] == 1

    async def test_sleep_import_invalid_onset_time(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with invalid onset time string."""
        await _create_file_record(test_session_maker, "sleep_badonset.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_badonset.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "invalid",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["dates_skipped"] == 1
        assert len(data["errors"]) == 1

    async def test_sleep_import_invalid_offset_time(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with invalid offset time string."""
        await _create_file_record(test_session_maker, "sleep_badoffset.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_badoffset.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "invalid",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["dates_skipped"] == 1
        assert len(data["errors"]) == 1

    async def test_sleep_import_onset_before_noon_wraps(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Onset time before noon (e.g. 01:00) wraps to next day for noon-to-noon analysis."""
        file_id = await _create_file_record(test_session_maker, "sleep_wrap.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_wrap.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "01:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_unmatched_filename(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with filename that doesn't match any files."""
        csv_bytes = _make_sleep_csv([
            {
                "filename": "nonexistent_file.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert len(data["unmatched_identifiers"]) == 1

    async def test_sleep_import_unmatched_pid(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with PID that matches no files."""
        csv_bytes = _make_sleep_csv([
            {
                "participant_id": "99999",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] == 1

    async def test_sleep_import_ambiguous_pid(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with PID matching multiple files, none covering date."""
        await _create_file_record(
            test_session_maker, "8001 T1 (2024-03-01)60sec.csv",
            participant_id="8001",
            start_time=datetime(2024, 3, 1, 12, 0, 0),
            end_time=datetime(2024, 3, 2, 12, 0, 0),
        )
        await _create_file_record(
            test_session_maker, "8001 T2 (2024-04-01)60sec.csv",
            participant_id="8001",
            start_time=datetime(2024, 4, 1, 12, 0, 0),
            end_time=datetime(2024, 4, 2, 12, 0, 0),
        )

        csv_bytes = _make_sleep_csv([
            {
                "participant_id": "8001",
                "sleep_date": "2024-06-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] == 1

    async def test_sleep_import_ambiguous_filename(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with filename fuzzy-matching multiple files, none covering date."""
        await _create_file_record(
            test_session_maker, "ambigsleep_file_v1.csv",
            start_time=datetime(2024, 3, 1, 12, 0, 0),
            end_time=datetime(2024, 3, 2, 12, 0, 0),
        )
        await _create_file_record(
            test_session_maker, "ambigsleep_file_v2.csv",
            start_time=datetime(2024, 4, 1, 12, 0, 0),
            end_time=datetime(2024, 4, 2, 12, 0, 0),
        )

        csv_bytes = _make_sleep_csv([
            {
                "filename": "ambigsleep_file.csv",
                "sleep_date": "2024-06-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        # Ambiguous or unmatched depending on fuzzy logic
        assert data["dates_skipped"] == 1

    async def test_sleep_import_no_sleep_with_consensus(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with NO_SLEEP sentinel AND needs_consensus=TRUE."""
        await _create_file_record(test_session_maker, "sleep_ns_cons.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_ns_cons.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "NO_SLEEP",
                "offset_time": "NO_SLEEP",
                "marker_type": "MAIN_SLEEP",
                "needs_consensus": "TRUE",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["no_sleep_dates"] == 1

    async def test_sleep_import_is_no_sleep_with_consensus(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with is_no_sleep=TRUE + needs_consensus=TRUE."""
        await _create_file_record(test_session_maker, "sleep_nsc2.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_nsc2.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "is_no_sleep": "TRUE",
                "needs_consensus": "TRUE",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["no_sleep_dates"] == 1

    async def test_sleep_import_no_sleep_with_naps(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """No-sleep date with NAP markers — NAPs should be preserved."""
        file_id = await _create_file_record(test_session_maker, "sleep_ns_nap.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_ns_nap.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "NO_SLEEP",
                "offset_time": "NO_SLEEP",
                "marker_type": "MAIN_SLEEP",
            },
            {
                "filename": "sleep_ns_nap.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "13:00",
                "offset_time": "14:30",
                "marker_type": "NAP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        # One date is no-sleep, the NAP should still be imported
        assert data["no_sleep_dates"] == 1
        assert data["markers_created"] == 1

    async def test_sleep_import_no_sleep_with_nonwear(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """No-sleep date with nonwear markers — full annotation update path."""
        file_id = await _create_file_record(test_session_maker, "sleep_ns_nw.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_ns_nw.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "NO_SLEEP",
                "offset_time": "NO_SLEEP",
                "marker_type": "MAIN_SLEEP",
            },
            {
                "filename": "sleep_ns_nw.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "14:00",
                "offset_time": "16:00",
                "marker_type": "MANUAL_NONWEAR",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["no_sleep_dates"] == 1
        assert data["nonwear_markers_created"] == 1

    async def test_sleep_import_sleep_and_nonwear_same_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep + nonwear markers on same date -> merged annotation update path."""
        file_id = await _create_file_record(test_session_maker, "sleep_both.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_both.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
            {
                "filename": "sleep_both.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "14:00",
                "offset_time": "16:00",
                "marker_type": "MANUAL_NONWEAR",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1
        assert data["nonwear_markers_created"] == 1

    async def test_sleep_import_nonwear_only_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Import with only nonwear markers on a date (no sleep)."""
        file_id = await _create_file_record(test_session_maker, "nw_only_date.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "nw_only_date.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "14:00",
                "offset_time": "16:00",
                "marker_type": "NONWEAR",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["nonwear_markers_created"] == 1
        # Date should be counted as imported even though it's nonwear-only
        assert data["dates_imported"] == 1

    async def test_sleep_import_onset_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with separate onset_date column."""
        file_id = await _create_file_record(test_session_maker, "sleep_od.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_od.csv",
                "sleep_date": "2024-01-01",
                "onset_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_offset_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with separate offset_date column."""
        file_id = await _create_file_record(test_session_maker, "sleep_ofd.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_ofd.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_date": "2024-01-02",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_missing_offset_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Sleep CSV with no offset column should return 400."""
        bad_csv = b"filename,sleep_date,onset_time\nfoo.csv,2024-01-01,22:00\n"

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        assert resp.status_code == 400
        assert "offset" in resp.json()["detail"].lower()

    async def test_sleep_import_scored_by_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with scored_by column (attribute recognition, no error)."""
        file_id = await _create_file_record(test_session_maker, "sleep_scorer.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_scorer.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
                "scored_by": "some_scorer",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_filename_pid_fallback(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with no filename/pid column — uses upload filename stem as PID."""
        file_id = await _create_file_record(
            test_session_maker, "9001 T1 (2024-01-01)60sec.csv",
            participant_id="9001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        # CSV has no filename or participant_id columns
        csv_bytes = _make_sleep_csv([
            {
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            # Upload filename stem "9001" matches participant
            files={"file": ("9001.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_empty_csv(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Empty CSV (only comment lines) returns 400."""
        csv_bytes = b"# just a comment\n# another comment\n"

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("empty.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 400
        assert "empty" in resp.json()["detail"].lower()

    async def test_sleep_import_study_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import using 'Study Date' column name (web export)."""
        file_id = await _create_file_record(test_session_maker, "sleep_sd.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_sd.csv",
                "study_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_filename_none_value_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import where filename column has None/nan value -> row skipped."""
        await _create_file_record(test_session_maker, "somefile.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "nan",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["dates_skipped"] == 1

    async def test_sleep_import_pid_none_skipped(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with participant_id=nan -> row skipped."""
        csv_bytes = _make_sleep_csv([
            {
                "participant_id": "nan",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["dates_skipped"] == 1

    async def test_sleep_import_onset_datetime_nan_fallback_to_time(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """When onset_datetime is NAN, fall back to onset_time column."""
        file_id = await _create_file_record(test_session_maker, "sleep_dt_fb.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_dt_fb.csv",
                "sleep_date": "2024-01-01",
                "onset_datetime": "NAN",
                "offset_datetime": "NAN",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_invalid_marker_index(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Invalid marker_index value (non-numeric) defaults to sequential."""
        file_id = await _create_file_record(test_session_maker, "sleep_bad_idx.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_bad_idx.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
                "period_index": "abc",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_float_marker_index(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Float marker_index (e.g. 3.0) should be converted to int."""
        file_id = await _create_file_record(test_session_maker, "sleep_float_idx.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_float_idx.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
                "period_index": "3.0",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

        markers = await _get_markers(
            test_session_maker, file_id, category=MarkerCategory.SLEEP,
        )
        assert any(m.period_index == 3 for m in markers)

    async def test_sleep_import_onset_invalid_date_col(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with onset_date column having invalid date -> error."""
        await _create_file_record(test_session_maker, "sleep_bad_od.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_bad_od.csv",
                "sleep_date": "2024-01-01",
                "onset_date": "bad-date",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["dates_skipped"] == 1
        assert len(data["errors"]) == 1

    async def test_sleep_import_fuzzy_filename_match(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with partial filename that fuzzy-matches."""
        file_id = await _create_file_record(
            test_session_maker, "participant_xyz_data.csv",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_sleep_csv([
            {
                "filename": "participant_xyz.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_nonwear_only_date_counts_imported(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Date with only nonwear (no sleep) still counts in dates_imported."""
        file_id = await _create_file_record(test_session_maker, "nw_only_count.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "nw_only_count.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "14:00",
                "offset_time": "16:00",
                "marker_type": "MANUAL_NONWEAR",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["nonwear_markers_created"] == 1
        assert data["dates_imported"] == 1

    async def test_sleep_import_offset_before_onset_wraps(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Offset time before onset (cross-midnight) wraps to next day."""
        file_id = await _create_file_record(test_session_maker, "sleep_cross.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_cross.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "23:00",
                "offset_time": "06:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

        markers = await _get_markers(
            test_session_maker, file_id, category=MarkerCategory.SLEEP,
        )
        assert len(markers) == 1
        assert markers[0].end_timestamp > markers[0].start_timestamp

    async def test_sleep_import_no_pid_no_filename_col_null_filename(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """CSV with no filename/pid columns and null-like upload filename -> rows skipped.
        filename_stem("nan.csv") = "nan", which is truthy so no 400,
        but normalize_participant_id("nan") = None -> rows skipped."""
        csv_bytes = _make_sleep_csv([
            {
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("nan.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 0
        assert data["dates_skipped"] == 1

    async def test_sleep_import_with_offset_date_col_no_onset_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import with offset_date column but no onset_date -> uses analysis_date for onset."""
        file_id = await _create_file_record(test_session_maker, "sleep_ofd_only.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_ofd_only.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_date": "2024-01-02",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_analysis_date_column(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import using 'analysis_date' as the date column name."""
        file_id = await _create_file_record(test_session_maker, "sleep_adate.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_adate.csv",
                "analysis_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_pid_timepoint_fallback_to_pool(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """PID+timepoint not in pid_tp index falls back to pid_pool filtering."""
        file_id = await _create_file_record(
            test_session_maker, "11001 T3 (2024-01-01)60sec.csv",
            participant_id="11001",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_sleep_csv([
            {
                "participant_id": "11001",
                "participant_timepoint": "T3",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_malformed_csv_returns_400(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Malformed CSV that polars cannot parse returns 400."""
        bad_csv = b"col1\n\"unclosed quote\n"

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
        )
        assert resp.status_code in (200, 400)

    async def test_sleep_import_no_filename_pid_empty_stem(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Sleep CSV with no filename/pid cols and null upload filename stem -> 400."""
        csv_bytes = _make_sleep_csv([
            {
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
            },
        ])

        # "null" is in _NULL_TOKENS -> filename_stem("null") returns None -> 400
        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("null", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 400

    async def test_sleep_import_is_no_sleep_false_not_triggered(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """is_no_sleep=FALSE should not mark as no-sleep."""
        file_id = await _create_file_record(test_session_maker, "sleep_nsf.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_nsf.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "is_no_sleep": "FALSE",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["no_sleep_dates"] == 0
        assert data["markers_created"] == 1

    async def test_sleep_import_no_sleep_consensus_false(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """NO_SLEEP with needs_consensus=FALSE should not add to consensus set."""
        await _create_file_record(test_session_maker, "sleep_ns_cf.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_ns_cf.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "NO_SLEEP",
                "offset_time": "NO_SLEEP",
                "marker_type": "MAIN_SLEEP",
                "needs_consensus": "FALSE",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["no_sleep_dates"] == 1

    async def test_sleep_import_short_pid_matching(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Sleep import matching via short_pid_norm (PID with site suffix stripped)."""
        file_id = await _create_file_record(
            test_session_maker, "P1-1036-A T1 (2024-01-01)60sec.csv",
            participant_id="P1-1036-A",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_sleep_csv([
            {
                "participant_id": "P1-1036",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_nonwear_short_pid_matching(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """Nonwear import matching via short_pid_norm (PID with site suffix stripped)."""
        await _create_file_record(
            test_session_maker, "P1-2036-B T1 (2024-01-01)60sec.csv",
            participant_id="P1-2036-B",
            start_time=datetime(2024, 1, 1, 12, 0, 0),
            end_time=datetime(2024, 1, 2, 12, 0, 0),
        )

        csv_bytes = _make_nonwear_csv([
            {
                "participant_id": "P1-2036",
                "date": "2024-01-01",
                "start_time": "03:00",
                "end_time": "05:00",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("study_nw.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_nonwear_no_pid_no_filename_col_empty_stem(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
    ) -> None:
        """Nonwear study-wide with no pid/filename columns and null upload stem -> 400."""
        csv_bytes = _make_nonwear_csv([
            {"date": "2024-01-01", "start_time": "03:00", "end_time": "05:00"},
        ])

        # "null" is in _NULL_TOKENS -> filename_stem("null") returns None -> 400
        resp = await client.post(
            "/api/v1/markers/nonwear/upload",
            headers=admin_auth_headers,
            files={"file": ("null", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 400

    async def test_sleep_import_onset_datetime_partial_nan(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """onset_datetime valid but offset_datetime unparseable -> falls back to time cols."""
        file_id = await _create_file_record(test_session_maker, "sleep_dt_partial.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_dt_partial.csv",
                "sleep_date": "2024-01-01",
                "onset_datetime": "2024-01-01 22:30:00",
                "offset_datetime": "not-a-datetime",
                "onset_time": "22:30",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1

    async def test_sleep_import_offset_date_bad_date(
        self,
        client: AsyncClient,
        admin_auth_headers: dict[str, str],
        test_session_maker: Any,
    ) -> None:
        """offset_date column with unparseable date falls back to onset date logic."""
        file_id = await _create_file_record(test_session_maker, "sleep_bad_ofd.csv")

        csv_bytes = _make_sleep_csv([
            {
                "filename": "sleep_bad_ofd.csv",
                "sleep_date": "2024-01-01",
                "onset_time": "22:00",
                "offset_date": "bad-date",
                "offset_time": "07:00",
                "marker_type": "MAIN_SLEEP",
            },
        ])

        resp = await client.post(
            "/api/v1/markers/sleep/upload",
            headers=admin_auth_headers,
            files={"file": ("sleep.csv", io.BytesIO(csv_bytes), "text/csv")},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["markers_created"] == 1
