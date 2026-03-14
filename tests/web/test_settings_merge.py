"""
HTTP integration tests for settings merge logic.

Tests how study-wide, per-user, and default settings are merged when
served through GET /api/v1/settings. Covers study-scoped field priority,
per-user field independence, extra_settings merge semantics, and resets.
"""

import pytest
from httpx import AsyncClient


# ── Default values (keep in sync with get_default_settings()) ────────────────
DEFAULTS = {
    "sleep_detection_rule": "consecutive_onset3s_offset5s",
    "night_start_hour": "21:00",
    "night_end_hour": "09:00",
    "device_preset": "actigraph",
    "epoch_length_seconds": 60,
    "skip_rows": 10,
    "preferred_display_column": "axis_y",
    "view_mode_hours": 24,
    "default_algorithm": "sadeh_1994_actilife",
}


@pytest.mark.asyncio
class TestSettingsMerge:
    """Tests for the settings merge logic across study, user, and defaults."""

    # ── 1. No settings → defaults returned ─────────────────────────────

    async def test_no_settings_returns_defaults(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ) -> None:
        """When neither study nor user settings exist, defaults are returned."""
        resp = await client.get("/api/v1/settings", headers=admin_auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        for key, expected in DEFAULTS.items():
            assert data[key] == expected, f"{key}: expected {expected!r}, got {data[key]!r}"
        assert data["extra_settings"] == {}

    # ── 2. Admin writes study settings → 200 ───────────────────────────

    async def test_admin_can_write_study_settings(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ) -> None:
        """Admin should be able to create/update study-wide settings."""
        resp = await client.put(
            "/api/v1/settings/study",
            headers=admin_auth_headers,
            json={"night_start_hour": "22:00", "epoch_length_seconds": 30},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["night_start_hour"] == "22:00"
        assert data["epoch_length_seconds"] == 30

    # ── 3. Non-admin writes study settings → 403 ───────────────────────

    async def test_non_admin_cannot_write_study_settings(
        self,
        client: AsyncClient,
        annotator_auth_headers: dict,
    ) -> None:
        """Annotators must not be able to modify study-wide settings."""
        resp = await client.put(
            "/api/v1/settings/study",
            headers=annotator_auth_headers,
            json={"night_start_hour": "22:00"},
        )

        assert resp.status_code == 403

    # ── 4. Study settings override defaults for all users ──────────────

    async def test_study_settings_override_defaults(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
    ) -> None:
        """Study-wide settings should override defaults for every user."""
        await client.put(
            "/api/v1/settings/study",
            headers=admin_auth_headers,
            json={
                "night_start_hour": "23:00",
                "device_preset": "geneactiv",
                "default_algorithm": "cole_kripke_1992_actilife",
            },
        )

        # Both admin and annotator should see the study values
        for headers in (admin_auth_headers, annotator_auth_headers):
            resp = await client.get("/api/v1/settings", headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["night_start_hour"] == "23:00"
            assert data["device_preset"] == "geneactiv"
            assert data["default_algorithm"] == "cole_kripke_1992_actilife"
            # Non-overridden study-scoped field should still be default
            assert data["night_end_hour"] == DEFAULTS["night_end_hour"]

    # ── 5. Study-scoped keys override user values ──────────────────────

    async def test_study_scoped_keys_override_user_values(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
    ) -> None:
        """For study-scoped fields, study value wins over user value."""
        # Annotator sets their own night_start_hour and detection rule
        await client.put(
            "/api/v1/settings",
            headers=annotator_auth_headers,
            json={
                "night_start_hour": "20:00",
                "sleep_detection_rule": "tudor_locke_2014",
            },
        )

        # Admin sets study-level overrides for the same fields
        await client.put(
            "/api/v1/settings/study",
            headers=admin_auth_headers,
            json={
                "night_start_hour": "22:30",
                "sleep_detection_rule": "consecutive_onset5s_offset10s",
            },
        )

        # Annotator's merged settings should reflect study values
        resp = await client.get("/api/v1/settings", headers=annotator_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["night_start_hour"] == "22:30"
        assert data["sleep_detection_rule"] == "consecutive_onset5s_offset10s"

    # ── 6. Per-user keys are independent ───────────────────────────────

    async def test_per_user_keys_are_independent(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
    ) -> None:
        """preferred_display_column and view_mode_hours are per-user only."""
        # Admin sets study settings (no per-user fields there)
        await client.put(
            "/api/v1/settings/study",
            headers=admin_auth_headers,
            json={"night_start_hour": "23:00"},
        )

        # Annotator sets per-user preferences
        await client.put(
            "/api/v1/settings",
            headers=annotator_auth_headers,
            json={
                "preferred_display_column": "vector_magnitude",
                "view_mode_hours": 48,
            },
        )

        # Admin sets different per-user preferences
        await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={
                "preferred_display_column": "axis_y",
                "view_mode_hours": 24,
            },
        )

        # Annotator's per-user fields should reflect annotator's values
        resp_ann = await client.get("/api/v1/settings", headers=annotator_auth_headers)
        assert resp_ann.status_code == 200
        ann_data = resp_ann.json()
        assert ann_data["preferred_display_column"] == "vector_magnitude"
        assert ann_data["view_mode_hours"] == 48

        # Admin's per-user fields should reflect admin's values
        resp_adm = await client.get("/api/v1/settings", headers=admin_auth_headers)
        assert resp_adm.status_code == 200
        adm_data = resp_adm.json()
        assert adm_data["preferred_display_column"] == "axis_y"
        assert adm_data["view_mode_hours"] == 24

        # Both see same study-scoped field
        assert ann_data["night_start_hour"] == "23:00"
        assert adm_data["night_start_hour"] == "23:00"

    # ── 7. extra_settings merge ────────────────────────────────────────

    async def test_extra_settings_merge(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
    ) -> None:
        """
        Study extras are visible to all users. User extras are merged in,
        but user extras must NOT override STUDY_EXTRA_KEYS.
        """
        # Admin sets study extras with a study-scoped key and a non-study key
        await client.put(
            "/api/v1/settings/study",
            headers=admin_auth_headers,
            json={
                "extra_settings": {
                    "id_pattern": r"^SUB_\d+$",
                    "choi_axis": "axis_y",
                    "study_note": "longitudinal",
                },
            },
        )

        # Annotator sets user extras, including an attempt to override a study key
        await client.put(
            "/api/v1/settings",
            headers=annotator_auth_headers,
            json={
                "extra_settings": {
                    "id_pattern": "SHOULD_NOT_APPEAR",  # STUDY_EXTRA_KEY
                    "choi_axis": "SHOULD_NOT_APPEAR",    # STUDY_EXTRA_KEY
                    "theme": "dark",                     # non-study key
                },
            },
        )

        # Annotator's merged settings should keep study extras intact
        resp = await client.get("/api/v1/settings", headers=annotator_auth_headers)
        assert resp.status_code == 200
        extra = resp.json()["extra_settings"]

        # Study keys preserved
        assert extra["id_pattern"] == r"^SUB_\d+$"
        assert extra["choi_axis"] == "axis_y"
        # Non-study study key passes through
        assert extra["study_note"] == "longitudinal"
        # User non-study key merged in
        assert extra["theme"] == "dark"

    # ── 8. After user reset → merged settings use study values ─────────

    async def test_user_reset_falls_back_to_study(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
    ) -> None:
        """After a user deletes their settings, study values still apply."""
        # Set study-level night_start_hour
        await client.put(
            "/api/v1/settings/study",
            headers=admin_auth_headers,
            json={"night_start_hour": "22:00"},
        )

        # Annotator sets per-user settings
        await client.put(
            "/api/v1/settings",
            headers=annotator_auth_headers,
            json={"view_mode_hours": 48, "night_start_hour": "20:00"},
        )

        # Annotator resets their personal settings
        resp_del = await client.delete("/api/v1/settings", headers=annotator_auth_headers)
        assert resp_del.status_code == 204

        # Merged settings should use study value for night_start_hour
        # and default for per-user fields
        resp = await client.get("/api/v1/settings", headers=annotator_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["night_start_hour"] == "22:00"   # study value
        assert data["view_mode_hours"] == DEFAULTS["view_mode_hours"]  # default

    # ── 9. After study reset → users fall back to defaults ─────────────

    async def test_study_reset_falls_back_to_defaults(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
    ) -> None:
        """After study settings are reset, users fall back to defaults."""
        # Set study settings
        await client.put(
            "/api/v1/settings/study",
            headers=admin_auth_headers,
            json={"night_start_hour": "23:30", "skip_rows": 5},
        )

        # Verify study values propagate
        resp = await client.get("/api/v1/settings", headers=annotator_auth_headers)
        assert resp.json()["night_start_hour"] == "23:30"

        # Admin resets study settings
        resp_del = await client.delete("/api/v1/settings/study", headers=admin_auth_headers)
        assert resp_del.status_code == 204

        # Annotator should now see defaults
        resp = await client.get("/api/v1/settings", headers=annotator_auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["night_start_hour"] == DEFAULTS["night_start_hour"]
        assert data["skip_rows"] == DEFAULTS["skip_rows"]

    # ── 10. Two users have independent settings ────────────────────────

    async def test_two_users_independent_settings(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        annotator_auth_headers: dict,
    ) -> None:
        """Each user's settings are stored and retrieved independently."""
        # Admin saves settings
        await client.put(
            "/api/v1/settings",
            headers=admin_auth_headers,
            json={
                "preferred_display_column": "vector_magnitude",
                "view_mode_hours": 48,
                "night_start_hour": "20:00",
            },
        )

        # Annotator saves different settings
        await client.put(
            "/api/v1/settings",
            headers=annotator_auth_headers,
            json={
                "preferred_display_column": "axis_y",
                "view_mode_hours": 24,
                "night_start_hour": "23:00",
            },
        )

        # Read back each user's merged settings
        resp_adm = await client.get("/api/v1/settings", headers=admin_auth_headers)
        resp_ann = await client.get("/api/v1/settings", headers=annotator_auth_headers)

        adm = resp_adm.json()
        ann = resp_ann.json()

        # Per-user fields differ
        assert adm["preferred_display_column"] == "vector_magnitude"
        assert ann["preferred_display_column"] == "axis_y"
        assert adm["view_mode_hours"] == 48
        assert ann["view_mode_hours"] == 24

        # Study-scoped fields: no study settings set, so each user's value is used
        assert adm["night_start_hour"] == "20:00"
        assert ann["night_start_hour"] == "23:00"

    # ── 11. Partial PUT preserves other fields ─────────────────────────

    async def test_partial_put_preserves_other_fields(
        self,
        client: AsyncClient,
        annotator_auth_headers: dict,
    ) -> None:
        """A partial PUT should only update the provided fields."""
        # Create settings with multiple fields
        await client.put(
            "/api/v1/settings",
            headers=annotator_auth_headers,
            json={
                "night_start_hour": "22:00",
                "device_preset": "actiwatch",
                "view_mode_hours": 48,
                "extra_settings": {"theme": "dark"},
            },
        )

        # Partial update: only change epoch_length_seconds
        resp = await client.put(
            "/api/v1/settings",
            headers=annotator_auth_headers,
            json={"epoch_length_seconds": 30},
        )

        assert resp.status_code == 200
        data = resp.json()
        # Updated field
        assert data["epoch_length_seconds"] == 30
        # Previously set fields preserved
        assert data["night_start_hour"] == "22:00"
        assert data["device_preset"] == "actiwatch"
        assert data["view_mode_hours"] == 48
        assert data["extra_settings"]["theme"] == "dark"
