# Web Application Issues Backlog

> **Status**: Deferred — these issues are documented but not prioritized for immediate work.
> **Source**: Reviews [014-web-frontend-review.md](014-web-frontend-review.md) and [015-test-coverage-review.md](015-test-coverage-review.md)
> **Created**: 2026-02-25

---

## CRITICAL (3)

### C-1: Path traversal in file upload

- **Files**: `sleep_scoring_web/api/files.py:280,297,400`
- **Description**: `file.filename` (user-controlled) is joined directly with the upload directory via `get_upload_path() / filename` with no path sanitization. The extension check `.endswith((".csv", ".xlsx", ".xls"))` does NOT prevent traversal — `../../etc/crontab.csv` passes. Affects both session-auth and API-key-auth upload endpoints.
- **Fix**: `safe_filename = PurePosixPath(filename).name`; raise HTTP 400 if sanitized name differs from original.

### C-2: API key comparison vulnerable to timing attack

- **File**: `sleep_scoring_web/api/deps.py:30`
- **Description**: `verify_api_key` uses `!=` (non-constant-time) instead of `secrets.compare_digest`. Site password auth already uses `compare_digest` correctly; the API key check does not.
- **Fix**: `secrets.compare_digest(x_api_key.encode("utf-8"), settings.upload_api_key.encode("utf-8"))`

### C-3: Nginx security headers silently dropped in nested location blocks

- **File**: `docker/frontend/nginx.conf:40-55`
- **Description**: Child `.css` and `.js` location blocks inside `/assets/` call `add_header`, which in Nginx completely replaces all parent-level headers. `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection` disappear for all CSS/JS assets.
- **Fix**: Remove the nested location blocks (MIME types already handled by `include mime.types`), or repeat the security headers in each nested block.

---

## HIGH — Bugs (5)

### H-1: API key upload endpoint unreachable (middleware bypass)

- **Files**: `sleep_scoring_web/main.py:102-117`, `sleep_scoring_web/api/files.py:360-460`
- **Description**: `SessionAuthMiddleware` blocks all requests without a session cookie. `/api/v1/files/upload/api` is not in `allowed_paths`. A headless pipeline client with only an `X-Api-Key` header gets 401 before the endpoint handler runs.
- **Fix**: Add `"/api/v1/files/upload/api"` to `allowed_paths`.

### H-2: Background task errors silently swallowed during file import

- **File**: `sleep_scoring_web/api/files.py:207-211,236`
- **Description**: Exception handler marks file as `FAILED` and returns `None` with no logging and no error stored. Debugging failed imports in production is impossible.
- **Fix**: Add `logger.exception(...)` and store error in `file_record.metadata_json`.

### H-3: `datetime.fromtimestamp()` uses local timezone in export

- **File**: `sleep_scoring_web/services/export_service.py:250-251`
- **Description**: Uses server local timezone. Rest of codebase uses `calendar.timegm()` (UTC-like) for the reverse, creating asymmetric round-trip. Exported times will be wrong on non-UTC servers.
- **Fix**: `datetime.fromtimestamp(ts, tz=timezone.utc)` or `datetime.utcfromtimestamp(ts)`

### H-4: Same timezone bug in marker table endpoint

- **File**: `sleep_scoring_web/api/markers.py:493,511`
- **Description**: Data window for epoch table queries is computed with local-timezone timestamps, shifting the query window relative to actual marker position.
- **Fix**: Same as H-3.

### H-5: No file size limit enforced before writing to disk

- **File**: `sleep_scoring_web/api/files.py:297-300,400-403`
- **Description**: `shutil.copyfileobj` writes entire upload without size check. `settings.max_upload_size_mb` (100 MB) exists but is only checked in `CSVLoaderService` AFTER the file is saved.
- **Fix**: Check `file.size` before writing; raise HTTP 413 if exceeded.

---

## HIGH — Security (1)

### H-6: `docker/.env` with dev credentials tracked in git

- **File**: `docker/.env:11,28`
- **Description**: Contains `POSTGRES_PASSWORD=sleepscoring_dev_password` and `SECRET_KEY=change-me-in-production-use-32-char-key` despite the file's own comment saying "Never commit .env to version control!".
- **Fix**: `git rm --cached docker/.env` and add to `.gitignore`.

---

## HIGH — Broken Tests (2)

### F-01: 14 web auth tests target non-existent JWT endpoints

- **File**: `tests/web/test_auth.py`
- **Description**: Every test targets JWT-based auth (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/me`). App was migrated to site-password auth. All 14 fail with 404s. The correct `auth_headers` fixture exists in `conftest.py` but is unused.
- **Fix**: Delete or rewrite for site-password auth.

### F-02: 8 web file tests fail due to auth mismatch

- **File**: `tests/web/test_files.py`
- **Description**: `test_upload_without_auth` expects 401 but gets 200; list/delete/scan tests fail with `KeyError` on response parsing.
- **Fix**: Update to use site-password auth and current response schema.

---

## HIGH — Coverage Gaps (4)

### F-06: 6 marker API routes have zero HTTP-level tests

- **File**: `tests/web/test_markers.py` (only tests Pydantic models)
- **Untested routes**: GET/PUT/DELETE markers, adjacent markers, table endpoints in `sleep_scoring_web/api/markers.py`
- **Fix**: Replace with real HTTP integration tests using FastAPI `TestClient`.

### F-13: Web marker tests validate Pydantic constructors, not behavior

- **File**: `tests/web/test_markers.py` (all 13 methods)
- **Description**: Tests create model instances and assert field values. None call `client.get()`, `client.put()`, or `client.delete()`. This tests Pydantic, not the application.
- **Fix**: Replace with HTTP integration tests (same effort as F-06).

### F-14: Empty test body in `test_markers.py:187-194`

- **File**: `tests/web/test_markers.py:187-194` (`test_window_minutes_range`)
- **Description**: Only contains `pass # Constraint validation is done by FastAPI`. If constraint is removed, test still passes.

### F-18: No E2E test for plot-click marker placement

- **File**: Missing
- **Description**: Primary user workflow (click on plot to place markers) goes through `PlotClickConnector` -> `MarkerInteractionHandler` -> store dispatch with no E2E coverage.

---

## MEDIUM — Coverage Gaps (5)

### F-07: 3 activity API routes untested

- **File**: `sleep_scoring_web/api/activity.py`
- **Routes**: `GET /{file_id}/{analysis_date}`, `/score`, `/sadeh`

### F-08: 4 diary API routes untested

- **File**: `sleep_scoring_web/api/diary.py`
- **Routes**: GET/PUT/DELETE diary, POST upload

### F-10: 4 export API routes untested

- **File**: `sleep_scoring_web/api/export.py`
- **Routes**: `GET /columns`, `POST /csv`, `POST /csv/download`, `GET /csv/quick`

### F-17: Migrations 002-013 only test instantiation

- **File**: `tests/unit/data/test_migrations.py`
- **Description**: Each migration test asserts `version` and `description` only. No `up()` is run against a real database.

### F-15: `assert True` as no-crash test

- **File**: `tests/unit/services/test_data_loading_service.py:401`
- **Description**: Calls `service.load_real_data()`, discards result, and asserts `True`.

---

## LOW (1)

### F-09: 3 settings API routes untested

- **File**: `sleep_scoring_web/api/settings.py`
- **Routes**: GET/PUT/DELETE settings
