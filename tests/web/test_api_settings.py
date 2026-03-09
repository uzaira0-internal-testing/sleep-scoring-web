"""
HTTP integration tests for the settings API endpoints.

Tests GET/PUT/DELETE /api/v1/settings using the async test client.
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
class TestGetSettings:
    """Tests for GET /api/v1/settings."""

    async def test_returns_defaults_when_no_settings_saved(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return default settings for a new user."""
        response = await client.get("/api/v1/settings", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["night_start_hour"] == "21:00"
        assert data["night_end_hour"] == "09:00"
        assert data["device_preset"] == "actigraph"
        assert data["epoch_length_seconds"] == 60
        assert data["skip_rows"] == 10
        assert data["view_mode_hours"] == 24

    async def test_works_without_auth_in_dev_mode(self, client: AsyncClient):
        """With empty site_password (dev mode), requests without auth should succeed."""
        response = await client.get("/api/v1/settings")

        # In dev mode (no site_password configured), auth is not enforced
        assert response.status_code == 200


@pytest.mark.asyncio
class TestUpdateSettings:
    """Tests for PUT /api/v1/settings."""

    async def test_creates_settings_on_first_update(self, client: AsyncClient, admin_auth_headers: dict):
        """Should create settings record when none exists."""
        response = await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={"night_start_hour": "23:00"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["night_start_hour"] == "23:00"
        # Other fields should get defaults
        assert data["device_preset"] == "actigraph"

    async def test_partial_update_preserves_other_fields(self, client: AsyncClient, admin_auth_headers: dict):
        """Should only update provided fields."""
        # Create settings first
        await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={"night_start_hour": "22:00", "device_preset": "actiwatch"},
        )

        # Update only one field
        response = await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={"epoch_length_seconds": 30},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["epoch_length_seconds"] == 30
        # Previously set fields should be preserved
        assert data["night_start_hour"] == "22:00"
        assert data["device_preset"] == "actiwatch"

    async def test_update_extra_settings(self, client: AsyncClient, admin_auth_headers: dict):
        """Should support extra_settings JSON field."""
        response = await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={"extra_settings": {"theme": "dark", "auto_save": True}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["extra_settings"]["theme"] == "dark"
        assert data["extra_settings"]["auto_save"] is True

    async def test_get_reflects_update(self, client: AsyncClient, admin_auth_headers: dict):
        """GET should reflect previously PUT values."""
        await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={"view_mode_hours": 48, "skip_rows": 5},
        )

        response = await client.get("/api/v1/settings", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["view_mode_hours"] == 48
        assert data["skip_rows"] == 5


@pytest.mark.asyncio
class TestResetSettings:
    """Tests for DELETE /api/v1/settings."""

    async def test_reset_returns_204(self, client: AsyncClient, admin_auth_headers: dict):
        """Should return 204 on successful reset."""
        # Create settings first
        await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={"night_start_hour": "23:00"},
        )

        response = await client.delete("/api/v1/settings", headers=admin_auth_headers)
        assert response.status_code == 204

    async def test_get_returns_defaults_after_reset(self, client: AsyncClient, admin_auth_headers: dict):
        """After reset, GET should return defaults."""
        # Create custom settings
        await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={"night_start_hour": "23:00", "view_mode_hours": 48},
        )

        # Reset
        await client.delete("/api/v1/settings", headers=admin_auth_headers)

        # GET should return defaults
        response = await client.get("/api/v1/settings", headers=admin_auth_headers)

        assert response.status_code == 200
        data = response.json()
        assert data["night_start_hour"] == "21:00"
        assert data["view_mode_hours"] == 24

    async def test_reset_when_no_settings_exist(self, client: AsyncClient, admin_auth_headers: dict):
        """Should not error when resetting non-existent settings."""
        response = await client.delete("/api/v1/settings", headers=admin_auth_headers)
        assert response.status_code == 204
