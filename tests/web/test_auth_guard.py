"""
Tests for SessionAuthMiddleware authentication guard.

Verifies that protected endpoints reject unauthenticated requests
and that public endpoints remain accessible without auth.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from global_auth import InMemorySessionStorage
from sleep_scoring_web.config import get_settings
from sleep_scoring_web.main import app

# ---------------------------------------------------------------------------
# Protected endpoints: (method, path)
# ---------------------------------------------------------------------------
PROTECTED_ENDPOINTS: list[tuple[str, str]] = [
    ("GET", "/api/v1/files"),
    ("GET", "/api/v1/settings"),
    ("GET", "/api/v1/markers/1/2024-01-01"),
    ("GET", "/api/v1/activity/1/2024-01-01/score"),
    ("GET", "/api/v1/analysis/summary"),
    ("GET", "/api/v1/audit/1/2024-01-01"),
    ("GET", "/api/v1/diary/1"),
    ("GET", "/api/v1/consensus/overview"),
    ("GET", "/api/v1/export/columns"),
    ("PUT", "/api/v1/settings"),
    ("PUT", "/api/v1/markers/1/2024-01-01"),
    ("POST", "/api/v1/audit/log"),
]


def _endpoint_id(val: tuple[str, str]) -> str:
    """Generate readable test ID from (method, path) tuple."""
    method, path = val
    return f"{method} {path}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def _in_memory_storage(setup_db) -> AsyncGenerator[InMemorySessionStorage, None]:
    """Enable SITE_PASSWORD and swap the live middleware's session_storage.

    Yields the InMemorySessionStorage so tests can create sessions directly.
    """
    settings = get_settings()
    original_password = settings.SITE_PASSWORD

    in_memory_storage = InMemorySessionStorage()

    # Walk the live ASGI middleware chain and replace session_storage on the
    # SessionAuthMiddleware instance that Starlette already built.
    _live_mw_patches: list[tuple[Any, Any]] = []
    current = getattr(app, "middleware_stack", None)
    while current is not None:
        if type(current).__name__ == "SessionAuthMiddleware":
            old_storage = getattr(current, "session_storage", None)
            if old_storage is not None:
                _live_mw_patches.append((current, old_storage))
                current.session_storage = in_memory_storage  # type: ignore[attr-defined]
        current = getattr(current, "app", None)

    # Enable auth
    settings.SITE_PASSWORD = "testpass"

    yield in_memory_storage

    # Restore
    settings.SITE_PASSWORD = original_password
    for mw_instance, old_storage in _live_mw_patches:
        mw_instance.session_storage = old_storage  # type: ignore[attr-defined]


@pytest_asyncio.fixture()
async def auth_client(
    _in_memory_storage: InMemorySessionStorage,
) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client with SITE_PASSWORD enabled (no valid session)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Test: protected endpoints reject requests without auth headers (401/403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method_path", PROTECTED_ENDPOINTS, ids=_endpoint_id)
async def test_protected_endpoint_rejects_no_auth(
    auth_client: AsyncClient,
    method_path: tuple[str, str],
) -> None:
    """All protected endpoints must return 401 or 403 without auth."""
    method, path = method_path
    response = await auth_client.request(method, path)
    assert response.status_code in (401, 403), (
        f"{method} {path} returned {response.status_code}, expected 401 or 403"
    )


# ---------------------------------------------------------------------------
# Test: protected endpoints reject wrong password (401/403)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("method_path", PROTECTED_ENDPOINTS, ids=_endpoint_id)
async def test_protected_endpoint_rejects_wrong_password(
    auth_client: AsyncClient,
    method_path: tuple[str, str],
) -> None:
    """All protected endpoints must reject requests with wrong credentials.

    Even sending X-Site-Password + X-Username headers does not bypass
    the SessionAuthMiddleware -- a valid session cookie is required.
    """
    method, path = method_path
    headers = {"X-Username": "testadmin", "X-Site-Password": "wrongpass"}
    response = await auth_client.request(method, path, headers=headers)
    assert response.status_code in (401, 403), (
        f"{method} {path} returned {response.status_code}, expected 401 or 403"
    )


# ---------------------------------------------------------------------------
# Test: correct auth on /api/v1/files returns 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_files_endpoint_accessible_with_valid_session(
    _in_memory_storage: InMemorySessionStorage,
    admin_auth_headers: dict[str, str],
) -> None:
    """With a valid session cookie and auth headers, /api/v1/files returns 200.

    The middleware checks the session cookie, then endpoint-level dependencies
    check the X-Site-Password and X-Username headers.  Both layers must pass.
    """
    # Create a session directly in the in-memory storage (bypasses the login
    # endpoint which would need its own closure-captured storage patched).
    token = await _in_memory_storage.create(username="testadmin")

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"session_token": token},
        headers=admin_auth_headers,
    ) as ac:
        response = await ac.get("/api/v1/files")

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Test: public endpoints work without auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_accessible_without_auth(auth_client: AsyncClient) -> None:
    """/health is in the allowed_paths list and must not require auth."""
    response = await auth_client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_verify_accessible_without_auth(auth_client: AsyncClient) -> None:
    """/api/v1/auth/verify is in the allowed_paths list and must not require auth."""
    response = await auth_client.post(
        "/api/v1/auth/verify",
        json={"password": "testpass"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_auth_status_accessible_without_auth(auth_client: AsyncClient) -> None:
    """/api/v1/auth/status is in the allowed_paths list and must not require auth."""
    response = await auth_client.get("/api/v1/auth/status")
    assert response.status_code == 200
    data = response.json()
    # With SITE_PASSWORD set, password should be required
    assert data["password_required"] is True
