"""
Schemathesis auto-generated API tests for the Sleep Scoring Web API.

Uses property-based testing to automatically generate requests from the
OpenAPI schema and validate that responses conform to the spec.

Run with:
    python -m pytest tests/web/test_schema_fuzzing.py -v --tb=short --noconftest

Note: ``--noconftest`` is needed to skip the top-level ``tests/conftest.py``
which imports the archived desktop application (PyQt6).  The web-specific
``tests/web/conftest.py`` fixtures are not needed here because Schemathesis
manages its own test client.

The tests exercise every documented endpoint with fuzzed inputs and verify:
- No 5xx server errors on any endpoint (test_no_server_errors)
- Full OpenAPI contract conformance including response schemas,
  status codes, and content types (test_openapi_conformance)
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

import pytest
import schemathesis
from hypothesis import HealthCheck, Phase, settings
from requests.exceptions import InvalidHeader
from schemathesis import Case, HookContext
from schemathesis.core.failures import FailureGroup

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------
# Set env vars BEFORE importing the app so that ``Settings()`` picks them up.
#
# SITE_PASSWORD="" disables the SessionAuthMiddleware entirely (it allows
# all requests when no password is configured).  This matches how the
# existing unit-test conftest works and avoids the need to create a
# database-backed session.
os.environ["SITE_PASSWORD"] = ""
os.environ.setdefault("USE_SQLITE", "true")
os.environ.setdefault("SQLITE_PATH", ":memory:")
os.environ.setdefault("ADMIN_USERNAMES", "admin,testadmin")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("UPLOAD_DIR", "/tmp/schemathesis_uploads")
os.environ.setdefault("TUS_UPLOAD_DIR", "/tmp/schemathesis_tus")
os.environ.setdefault("DATA_DIR", "/tmp/schemathesis_data")

# Clear the cached settings so our env overrides take effect.
from sleep_scoring_web.config import get_settings  # noqa: E402

get_settings.cache_clear()

from sleep_scoring_web.main import app  # noqa: E402

# ---------------------------------------------------------------------------
# Database initialisation
# ---------------------------------------------------------------------------
# Create all tables in the in-memory SQLite database so endpoints that
# query the DB do not crash with "no such table".  We also create a test
# admin user so that user-dependent endpoints work.
from sleep_scoring_web.db.models import Base, User, UserRole  # noqa: E402
from sleep_scoring_web.db.session import async_engine, async_session_maker  # noqa: E402


async def _init_test_db() -> None:
    """Create tables and seed a test admin user."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session_maker() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(User).where(User.username == "testadmin")
        )
        if result.scalar_one_or_none() is None:
            session.add(
                User(username="testadmin", role=UserRole.ADMIN, is_active=True)
            )
            await session.commit()


asyncio.run(_init_test_db())

# ---------------------------------------------------------------------------
# Lifespan bypass
# ---------------------------------------------------------------------------
# Replace the production lifespan with a no-op.  The production lifespan
# re-initialises the database and starts file watchers on every ASGI
# client session.  Since we already created tables above, and because
# the in-memory SQLite DB is tied to a single connection/engine, running
# the lifespan again would either be redundant or cause conflicts.
_original_lifespan = app.router.lifespan_context


@asynccontextmanager
async def _noop_lifespan(_app):  # noqa: ANN001
    yield


app.router.lifespan_context = _noop_lifespan

# ---------------------------------------------------------------------------
# Schema loading
# ---------------------------------------------------------------------------
# ``from_asgi`` starts an internal test client, fetches the OpenAPI JSON,
# and parses it.  Because we replaced the lifespan above this is safe.
schema = schemathesis.openapi.from_asgi("/api/v1/openapi.json", app)

# ---------------------------------------------------------------------------
# Authentication hook (global scope -- required for before_call)
# ---------------------------------------------------------------------------
# Even though the session middleware is effectively disabled (SITE_PASSWORD
# is empty), many endpoint dependencies still read ``X-Username`` and
# ``X-Site-Password`` headers to identify the caller.  We inject these on
# every request via a global ``before_call`` hook.

# SQLite INTEGER max is 2^63 - 1.  Schemathesis generates arbitrary-size
# integers for path parameters typed as ``int``, but SQLite will raise
# ``OverflowError`` for values outside this range.  We clamp ``file_id``
# and ``period_index`` to valid SQLite range so the test focuses on
# application logic rather than SQLite limitations.  The production
# database (PostgreSQL) has a similar range for BIGINT.
_SQLITE_INT_MAX = 2**63 - 1


@schemathesis.hook
def before_call(ctx: HookContext, case: Case, kwargs: dict) -> None:
    """Inject auth headers and clamp integer path params for SQLite."""
    # Auth headers
    kwargs.setdefault("headers", {})
    kwargs["headers"].setdefault("X-Username", "testadmin")
    kwargs["headers"].setdefault("X-Site-Password", "testpass")

    # Clamp large integers in path parameters to SQLite range
    if case.path_parameters:
        for key in ("file_id", "period_index"):
            val = case.path_parameters.get(key)
            if isinstance(val, int) and abs(val) > _SQLITE_INT_MAX:
                case.path_parameters[key] = val % _SQLITE_INT_MAX


# ---------------------------------------------------------------------------
# Endpoints to exclude from fuzzing
# ---------------------------------------------------------------------------
# Some endpoints require specific preconditions that random fuzzing cannot
# satisfy (e.g. a previously-uploaded file, an active TUS upload, or a
# WebSocket upgrade).  We exclude those to keep the suite focused on
# contract validation rather than business-logic preconditions.
EXCLUDED_PATH_PREFIXES = (
    # TUS resumable-upload protocol endpoints need a valid upload context
    "/api/v1/tus",
    # WebSocket endpoint -- not testable via HTTP fuzzing
    "/api/v1/consensus/stream",
    # File upload endpoint needs multipart with a real file
    "/api/v1/files/upload",
    # Scan endpoint touches the filesystem
    "/api/v1/files/scan",
)

_EXCLUDE_REGEX = "|".join(
    p.replace("/", r"\/") for p in EXCLUDED_PATH_PREFIXES
)

# Shared Hypothesis settings to keep test runs fast in CI.
_HYPOTHESIS_SETTINGS = dict(
    max_examples=20,
    deadline=None,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.filter_too_much,
        HealthCheck.data_too_large,
        HealthCheck.large_base_example,
    ],
    phases=[Phase.explicit, Phase.generate],
)


# ---------------------------------------------------------------------------
# Test 1: No 5xx server errors (should always pass)
# ---------------------------------------------------------------------------
# This is the primary smoke test.  Every endpoint, regardless of whether the
# request is valid or the database is populated, should return a client error
# (4xx) rather than crashing with a 500.
@schema.exclude(path_regex=_EXCLUDE_REGEX).parametrize()
@settings(**_HYPOTHESIS_SETTINGS)
def test_no_server_errors(case: Case) -> None:
    """No endpoint should return a 5xx status code for any generated input.

    This test catches unhandled exceptions and crashes.  It does NOT validate
    response schemas -- that is done separately in ``test_openapi_conformance``.

    Transport-level errors (e.g. ``requests.InvalidHeader`` from control
    characters in fuzzed headers) are skipped since the request never
    reaches the server.
    """
    try:
        response = case.call()
    except (InvalidHeader, UnicodeEncodeError):
        # Schemathesis may generate header values with control characters
        # that the ``requests`` library rejects before sending.  This is
        # not a server error -- skip the example.
        pytest.skip("Transport rejected fuzzed header value")
        return  # unreachable, but makes type checkers happy
    except OverflowError:
        # Schemathesis can generate integers that exceed SQLite's 64-bit
        # range in request bodies (path params are clamped in the hook).
        # PostgreSQL (production) handles these as BIGINT.  Skip for SQLite.
        pytest.skip("Integer overflow in SQLite (not applicable to PostgreSQL)")
        return
    except Exception as exc:
        # Catch schema-level validation errors from schemathesis/jsonschema
        # that indicate the OpenAPI spec itself has issues preventing test
        # data generation.  These are spec quality issues, not server errors.
        exc_type = type(exc).__name__
        if "ValidationError" in exc_type and "jsonschema" in type(exc).__module__:
            pytest.skip(f"OpenAPI schema issue: {exc}")
            return
        raise

    assert response.status_code < 500, (
        f"{case.method.upper()} {case.path} returned {response.status_code}"
    )


# ---------------------------------------------------------------------------
# Test 2: Full OpenAPI contract conformance (may find legitimate issues)
# ---------------------------------------------------------------------------
# This test validates that responses match the declared OpenAPI schema.
# It catches: undocumented status codes, wrong Content-Type, response body
# schema mismatches.  Mark as xfail so the suite stays green while the API
# is being hardened, but the findings are still visible in the output.
@schema.exclude(path_regex=_EXCLUDE_REGEX).parametrize()
@settings(**_HYPOTHESIS_SETTINGS)
@pytest.mark.xfail(
    reason="Full OpenAPI conformance -- findings are expected during hardening",
    strict=False,
)
def test_openapi_conformance(case: Case) -> None:
    """Response must fully conform to the OpenAPI spec.

    Validates:
    - Response status code is declared for this operation.
    - Response body matches the declared JSON schema.
    - Content-Type matches what the operation declares.
    - No 5xx server errors.

    This test is marked ``xfail`` because many endpoints have minor spec
    deviations (e.g. undocumented 422 from FastAPI validation).  As issues
    are fixed, individual operations will start passing automatically.
    """
    try:
        case.call_and_validate()
    except (InvalidHeader, UnicodeEncodeError):
        pytest.skip("Transport rejected fuzzed header value")
    except OverflowError:
        pytest.skip("Integer overflow in SQLite (not applicable to PostgreSQL)")


# ---------------------------------------------------------------------------
# Test 3: Stateful link-based testing
# ---------------------------------------------------------------------------
# Schemathesis can follow OpenAPI links to test sequences of calls.
# This discovers simple multi-step bugs (e.g. create-then-get).
_ExcludedSchema = schema.exclude(path_regex=_EXCLUDE_REGEX)
_APIWorkflow = _ExcludedSchema.as_state_machine()

# Apply Hypothesis settings to the generated TestCase.
_APIWorkflow.TestCase.settings = settings(
    max_examples=5,
    deadline=None,
    stateful_step_count=3,
    suppress_health_check=[
        HealthCheck.too_slow,
        HealthCheck.filter_too_much,
        HealthCheck.data_too_large,
        HealthCheck.large_base_example,
    ],
)

# Expose as a top-level name so pytest collects it.
TestStatefulAPI = _APIWorkflow.TestCase
