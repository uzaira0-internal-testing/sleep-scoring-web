"""
Tests for sleep_scoring_web.services.choi_helpers module.

Covers column extraction from ORM rows and columnar data,
default values, and valid column checking.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from sleep_scoring_web.schemas.enums import ActivityDataPreference
from sleep_scoring_web.services.choi_helpers import (
    DEFAULT_CHOI_COLUMN,
    VALID_CHOI_COLUMNS,
    extract_choi_input,
    extract_choi_input_from_columnar,
    get_choi_column,
)


# =============================================================================
# Constants
# =============================================================================

class TestConstants:
    def test_default_column(self):
        assert DEFAULT_CHOI_COLUMN == ActivityDataPreference.VECTOR_MAGNITUDE

    def test_valid_columns_contains_all_axes(self):
        assert "axis_x" in VALID_CHOI_COLUMNS
        assert "axis_y" in VALID_CHOI_COLUMNS
        assert "axis_z" in VALID_CHOI_COLUMNS
        assert "vector_magnitude" in VALID_CHOI_COLUMNS

    def test_valid_columns_count(self):
        assert len(VALID_CHOI_COLUMNS) == 4


# =============================================================================
# get_choi_column
# =============================================================================

class TestGetChoiColumn:
    @pytest.mark.asyncio
    async def test_empty_username_returns_default(self):
        db = AsyncMock()
        result = await get_choi_column(db, "")
        assert result == DEFAULT_CHOI_COLUMN

    @pytest.mark.asyncio
    async def test_no_settings_returns_default(self):
        """When no UserSettings row exists, should return default."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await get_choi_column(db, "testuser")
        assert result == DEFAULT_CHOI_COLUMN

    @pytest.mark.asyncio
    async def test_settings_with_valid_axis(self):
        """When UserSettings has a valid choi_axis, should return it."""
        settings = MagicMock()
        settings.extra_settings_json = {"choi_axis": "axis_y"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = settings
        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await get_choi_column(db, "testuser")
        assert result == "axis_y"

    @pytest.mark.asyncio
    async def test_settings_with_invalid_axis(self):
        """When UserSettings has an invalid choi_axis, should return default."""
        settings = MagicMock()
        settings.extra_settings_json = {"choi_axis": "invalid_column"}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = settings
        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await get_choi_column(db, "testuser")
        assert result == DEFAULT_CHOI_COLUMN

    @pytest.mark.asyncio
    async def test_settings_with_no_extra_json(self):
        """When extra_settings_json is None, should return default."""
        settings = MagicMock()
        settings.extra_settings_json = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = settings
        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await get_choi_column(db, "testuser")
        assert result == DEFAULT_CHOI_COLUMN

    @pytest.mark.asyncio
    async def test_settings_with_empty_extra_json(self):
        """When extra_settings_json is empty dict, should return default."""
        settings = MagicMock()
        settings.extra_settings_json = {}

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = settings
        db = AsyncMock()
        db.execute.return_value = mock_result

        result = await get_choi_column(db, "testuser")
        assert result == DEFAULT_CHOI_COLUMN

    @pytest.mark.asyncio
    async def test_settings_with_each_valid_column(self):
        """Each valid column should be accepted."""
        for col in VALID_CHOI_COLUMNS:
            settings = MagicMock()
            settings.extra_settings_json = {"choi_axis": col}

            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = settings
            db = AsyncMock()
            db.execute.return_value = mock_result

            result = await get_choi_column(db, "testuser")
            assert result == col, f"Expected {col}"


# =============================================================================
# extract_choi_input
# =============================================================================

class TestExtractChoiInput:
    def test_extract_vector_magnitude(self):
        rows = [
            SimpleNamespace(vector_magnitude=100, axis_x=10, axis_y=20, axis_z=30),
            SimpleNamespace(vector_magnitude=200, axis_x=11, axis_y=21, axis_z=31),
            SimpleNamespace(vector_magnitude=300, axis_x=12, axis_y=22, axis_z=32),
        ]
        result = extract_choi_input(rows, "vector_magnitude")
        assert result == [100, 200, 300]

    def test_extract_axis_y(self):
        rows = [
            SimpleNamespace(vector_magnitude=100, axis_y=20),
            SimpleNamespace(vector_magnitude=200, axis_y=21),
        ]
        result = extract_choi_input(rows, "axis_y")
        assert result == [20, 21]

    def test_extract_missing_attribute_returns_zero(self):
        rows = [SimpleNamespace(vector_magnitude=100)]
        result = extract_choi_input(rows, "nonexistent_col")
        assert result == [0]

    def test_extract_none_values_become_zero(self):
        rows = [
            SimpleNamespace(vector_magnitude=None),
            SimpleNamespace(vector_magnitude=100),
        ]
        result = extract_choi_input(rows, "vector_magnitude")
        assert result == [0, 100]

    def test_empty_rows(self):
        result = extract_choi_input([], "vector_magnitude")
        assert result == []


# =============================================================================
# extract_choi_input_from_columnar
# =============================================================================

class TestExtractChoiInputFromColumnar:
    def test_extract_vector_magnitude(self):
        data = SimpleNamespace(
            vector_magnitude=[100, 200, 300],
            axis_x=[10, 11, 12],
            axis_y=[20, 21, 22],
            axis_z=[30, 31, 32],
        )
        result = extract_choi_input_from_columnar(data, "vector_magnitude")
        assert result == [100, 200, 300]

    def test_extract_axis_x(self):
        data = SimpleNamespace(
            vector_magnitude=[100, 200],
            axis_x=[10, 11],
            axis_y=[20, 21],
            axis_z=[30, 31],
        )
        result = extract_choi_input_from_columnar(data, "axis_x")
        assert result == [10, 11]

    def test_extract_missing_column_falls_back_to_vector_magnitude(self):
        data = SimpleNamespace(
            vector_magnitude=[100, 200],
        )
        result = extract_choi_input_from_columnar(data, "nonexistent")
        assert result == [100, 200]

    def test_all_valid_columns(self):
        data = SimpleNamespace(
            vector_magnitude=[1],
            axis_x=[2],
            axis_y=[3],
            axis_z=[4],
        )
        assert extract_choi_input_from_columnar(data, "vector_magnitude") == [1]
        assert extract_choi_input_from_columnar(data, "axis_x") == [2]
        assert extract_choi_input_from_columnar(data, "axis_y") == [3]
        assert extract_choi_input_from_columnar(data, "axis_z") == [4]
