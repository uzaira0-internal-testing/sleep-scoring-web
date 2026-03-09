# Review 014: Web Frontend & Backend Security Review

**Date**: 2026-02-25
**Scope**: FastAPI backend (`sleep_scoring_web/`), React frontend (`frontend/src/`), Docker config (`docker/`)
**Focus**: CRITICAL and HIGH severity issues only (security, data integrity, crashes, wrong behavior)

---

## Summary

Reviewed all `.py` files in `sleep_scoring_web/`, all `.tsx/.ts` files in `frontend/src/`, and all Docker configuration files. Found **3 CRITICAL** and **6 HIGH** severity issues.

---

## CRITICAL Issues

### C-1: Path Traversal in File Upload (Both Endpoints)

**File**: `sleep_scoring_web/api/files.py:297` and `sleep_scoring_web/api/files.py:400`

**Description**: The uploaded filename is taken directly from `file.filename` (user-controlled) and joined with the upload directory path using `get_upload_path() / filename`. A malicious filename such as `../../etc/crontab` or `..\..\..\windows\system32\config` could write files outside the upload directory. This affects both the session-authenticated upload (`POST /upload`) and the API-key-authenticated upload (`POST /upload/api`).

**Evidence**:
```python
# Line 280: filename comes from user input
filename = file.filename

# Line 297: directly used in path construction -- NO sanitization
upload_path = get_upload_path() / filename

# Same pattern at line 400 for API upload:
upload_path = get_upload_path() / filename
```

The extension check on line 281 (`filename.lower().endswith((".csv", ".xlsx", ".xls"))`) does NOT prevent path traversal -- `../../etc/crontab.csv` passes the extension check.

**Fix**: Sanitize the filename to strip directory separators and path components:
```python
from pathlib import PurePosixPath
safe_filename = PurePosixPath(filename).name  # Strips all directory components
if safe_filename != filename:
    raise HTTPException(status_code=400, detail="Invalid filename")
upload_path = get_upload_path() / safe_filename
```

---

### C-2: API Key Comparison Vulnerable to Timing Attack

**File**: `sleep_scoring_web/api/deps.py:30`

**Description**: The `verify_api_key` function uses regular string comparison (`!=`) to check the API key. This is vulnerable to timing attacks where an attacker can determine the correct key character-by-character by measuring response time differences. The site password verification correctly uses `secrets.compare_digest` (via `global_auth`), but the API key check does not.

**Evidence**:
```python
# deps.py line 30 -- NOT constant-time comparison
if x_api_key != settings.upload_api_key:
    raise HTTPException(status_code=401, detail="Invalid API key")
```

Compare with the correct pattern used in `global_auth/dependencies.py:74`:
```python
# CORRECT: constant-time comparison
if not secrets.compare_digest(
    x_site_password.encode("utf-8"),
    site_password.encode("utf-8"),
):
```

**Fix**: Replace with `secrets.compare_digest`:
```python
import secrets
if not secrets.compare_digest(x_api_key.encode("utf-8"), settings.upload_api_key.encode("utf-8")):
    raise HTTPException(status_code=401, detail="Invalid API key")
```

---

### C-3: Nginx Security Headers Silently Dropped in Nested Location Blocks

**File**: `docker/frontend/nginx.conf:40-55`

**Description**: In Nginx, when a child `location` block uses `add_header`, it **completely replaces** all headers from the parent block. The nested `.css` and `.js` location blocks inside `/assets/` use `add_header`, which means the security headers defined at the `server` level (lines 20-22: `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`) are silently dropped for all CSS and JS assets. This opens the door for clickjacking and MIME-type sniffing attacks on these resources.

**Evidence**:
```nginx
# Server-level security headers (lines 20-22) -- GOOD
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;

# Nested locations (lines 45-54) -- BAD: replaces ALL parent headers
location ~* \.css$ {
    add_header Content-Type text/css;           # This REPLACES security headers
    add_header Cache-Control "public, immutable";
    expires 1y;
}
location ~* \.js$ {
    add_header Content-Type application/javascript;  # This REPLACES security headers
    add_header Cache-Control "public, immutable";
    expires 1y;
}
```

**Fix**: Either (a) repeat the security headers in each nested block, or (b) use the `more_set_headers` directive from `ngx_http_headers_more_module` which doesn't have the replacement behavior, or (c) remove the nested location blocks entirely since `include /etc/nginx/mime.types` on line 8 already handles MIME types correctly:
```nginx
# Simplest fix: remove nested locations (MIME types already handled)
location /assets/ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

---

## HIGH Issues

### H-1: API Key Upload Endpoint Unreachable for Pipeline Clients

**File**: `sleep_scoring_web/main.py:102-117` and `sleep_scoring_web/api/files.py:360-460`

**Description**: The `SessionAuthMiddleware` blocks ALL requests without a valid session cookie, except for explicitly allowlisted paths. The API key upload endpoint `POST /api/v1/files/upload/api` is NOT in the `allowed_paths` list (lines 106-116). This means a headless pipeline client that sends only an `X-Api-Key` header will receive a `401 Not authenticated` response from the middleware BEFORE the endpoint handler ever runs. The API key authentication is effectively useless.

**Evidence**:
```python
# main.py lines 106-116: allowed_paths does NOT include upload/api
app.add_middleware(
    SessionAuthMiddleware,
    ...
    allowed_paths=[
        "/api/v1/auth/status",
        "/api/v1/auth/session/login",
        "/api/v1/auth/login",
        "/api/v1/auth/verify",
        "/health",
        "/",
        "/api/v1/docs",
        "/api/v1/redoc",
        "/api/v1/openapi.json",
    ],
)
```

```python
# files.py line 360-365: this endpoint is never reachable without session
@router.post("/upload/api")
async def upload_file_api(
    ...
    _api_key: ApiKey,  # This dependency never runs
    ...
```

**Fix**: Add the API upload path to the session middleware `allowed_paths`:
```python
allowed_paths=[
    ...
    "/api/v1/files/upload/api",  # API key auth handles its own security
],
```

---

### H-2: Background Task Errors Silently Swallowed During File Import

**File**: `sleep_scoring_web/api/files.py:207-211`

**Description**: When `import_file_from_disk_async` fails during the file watcher's automatic ingestion, the exception is caught and the function returns `None` without logging the error. The file is marked as `FAILED` in the database but no diagnostic information is preserved. This makes debugging failed imports nearly impossible in production.

**Evidence**:
```python
# files.py lines 207-211
except Exception as e:
    # Mark file as failed
    file_record.status = FileStatus.FAILED
    await db.commit()
    return None  # Error swallowed -- no logging, no error message stored
```

The same error is also printed without the actual exception in the background scan at line 236:
```python
except Exception as e:
    _scan_status.failed += 1
    # 'e' is available but not logged
```

**Fix**: Log the exception and store the error message:
```python
except Exception as e:
    logger.exception("Failed to import file %s: %s", filename, e)
    file_record.status = FileStatus.FAILED
    file_record.metadata_json = {"import_error": str(e)}
    await db.commit()
    return None
```

---

### H-3: `datetime.fromtimestamp()` Uses Local Timezone in Export

**File**: `sleep_scoring_web/services/export_service.py:250-251`

**Description**: The export service uses `datetime.fromtimestamp()` to convert Unix timestamps to datetime strings. This function interprets the timestamp in the **server's local timezone**, not UTC. If the server timezone differs from the data timezone, exported onset/offset times will be wrong. This is particularly dangerous because the rest of the codebase uses `calendar.timegm()` for the reverse conversion (which treats datetimes as UTC), creating an asymmetric conversion.

**Evidence**:
```python
# export_service.py lines 250-251
onset_dt = datetime.fromtimestamp(marker.start_timestamp) if marker.start_timestamp else None
offset_dt = datetime.fromtimestamp(marker.end_timestamp) if marker.end_timestamp else None
```

Compare with the correct approach used in `activity.py:27` and `markers.py:28`:
```python
# These use calendar.timegm which treats datetime as UTC
def naive_to_unix(dt: datetime) -> float:
    return float(calendar.timegm(dt.timetuple()))
```

The conversion is asymmetric: `naive_to_unix` treats datetimes as UTC-like (no timezone adjustment), but `datetime.fromtimestamp` applies the server's local timezone offset when converting back.

**Fix**: Use `datetime.utcfromtimestamp()` or `datetime.fromtimestamp(ts, tz=timezone.utc)`:
```python
from datetime import timezone
onset_dt = datetime.fromtimestamp(marker.start_timestamp, tz=timezone.utc) if marker.start_timestamp else None
```

---

### H-4: `datetime.fromtimestamp()` Uses Local Timezone in Marker Table Endpoint

**File**: `sleep_scoring_web/api/markers.py:493` and `sleep_scoring_web/api/markers.py:511`

**Description**: Same issue as H-3 but in the marker table endpoint. The onset/offset datetime windows are computed using `datetime.fromtimestamp()` with local timezone, causing the data window to be shifted from the actual marker position.

**Evidence**:
```python
# markers.py line 493 -- uses local timezone
onset_dt = datetime.fromtimestamp(marker.start_timestamp)
onset_start = onset_dt - timedelta(minutes=window_minutes)
onset_end = onset_dt + timedelta(minutes=window_minutes)

# markers.py line 511 -- same issue
offset_dt = datetime.fromtimestamp(marker.end_timestamp)
```

Since the activity data timestamps are stored as naive datetimes in the database and compared using `>=`/`<=`, a timezone offset here means the query window will be shifted, potentially returning data from the wrong time range (or missing the marker entirely).

**Fix**: Use `datetime.utcfromtimestamp()` to match the naive-UTC convention used elsewhere:
```python
onset_dt = datetime.utcfromtimestamp(marker.start_timestamp)
```

---

### H-5: No File Size Limit Enforced Before Writing to Disk

**File**: `sleep_scoring_web/api/files.py:297-300` and `sleep_scoring_web/api/files.py:400-403`

**Description**: The upload endpoint writes the file to disk using `shutil.copyfileobj` without checking the file size first. While `settings.max_upload_size_mb` exists (100MB), it is never enforced at the upload level. A malicious or accidental upload of an extremely large file could fill the disk, causing a denial of service for the entire application (database, other uploads, file watcher).

**Evidence**:
```python
# files.py lines 297-300: writes entire file without size check
upload_path = get_upload_path() / filename
try:
    with upload_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)  # No size limit!
```

The `CSVLoaderService` has a check (`max_upload_size_mb`) but it runs AFTER the file is already saved to disk:
```python
# csv_loader.py -- this check happens too late
class CSVLoaderService:
    def __init__(self, ..., max_file_size_mb: int = 100): ...
```

**Fix**: Add size-limited reading before or during the file write:
```python
# Option 1: Check Content-Length header (can be spoofed but catches honest mistakes)
if file.size and file.size > settings.max_upload_size_mb * 1024 * 1024:
    raise HTTPException(status_code=413, detail="File too large")

# Option 2: Stream with size limit
MAX_SIZE = settings.max_upload_size_mb * 1024 * 1024
total_read = 0
with upload_path.open("wb") as buffer:
    while chunk := await file.read(8192):
        total_read += len(chunk)
        if total_read > MAX_SIZE:
            upload_path.unlink()  # Clean up partial file
            raise HTTPException(status_code=413, detail="File too large")
        buffer.write(chunk)
```

---

### H-6: Docker `.env` File Contains Hardcoded Development Credentials

**File**: `docker/.env:11,28`

**Description**: The `docker/.env` file is tracked in git (appears in `git status` without `??` prefix, meaning it's a tracked file) and contains hardcoded development credentials. While the file contains a comment saying "Never commit .env to version control!", it IS tracked. Anyone with repo access can see the development credentials, and if the production deployment uses the same file without changing values, the application is exposed.

**Evidence**:
```bash
# docker/.env lines 11, 28
POSTGRES_PASSWORD=sleepscoring_dev_password
SECRET_KEY=change-me-in-production-use-32-char-key
```

The `.env.example` file exists with placeholder values, but the actual `.env` with real development credentials is also tracked.

**Fix**: Add `docker/.env` to `.gitignore` and remove it from tracking:
```bash
git rm --cached docker/.env
echo "docker/.env" >> .gitignore
```

---

## Verification Checklist

- [x] Read `CLAUDE.md` for architecture understanding
- [x] Checked every `.py` file in `sleep_scoring_web/` (main.py, config.py, auth_setup.py, api/deps.py, api/files.py, api/markers.py, api/export.py, api/activity.py, api/diary.py, api/settings.py, db/models.py, db/session.py, services/file_watcher.py, services/loaders/csv_loader.py, services/export_service.py, services/metrics.py, schemas/models.py, schemas/enums.py, algorithms/__init__.py)
- [x] Checked key `.tsx/.ts` files in `frontend/src/` (store/index.ts, api/client.ts, api/types.ts, api/schema.ts, config.ts, pages/scoring.tsx, pages/login.tsx, components/activity-plot.tsx, hooks/useMarkerAutoSave.ts, hooks/useMarkerLoad.ts, utils/api-errors.ts, App.tsx)
- [x] Docker configuration reviewed (docker-compose.prod.yml, .env, .env.example, nginx.conf, docker-entrypoint.sh, Dockerfile.local)
- [x] Each reported issue has specific file:line reference
- [x] Security issues verified (not speculative) -- traced through actual code paths and confirmed behavior

---

## Items Reviewed But Not Flagged (Adequate or Low Severity)

The following areas were reviewed and found to be adequate or only have low-severity issues:

- **CORS configuration**: Properly configured with environment variable, not hardcoded to `*`
- **Session cookie security**: Uses `httponly=True`, `secure=True`, `samesite="strict"` -- well done
- **SQL injection**: All database queries use SQLAlchemy ORM with parameterized queries -- no raw SQL injection vectors found
- **XSS in frontend**: The `innerHTML` usage in `activity-plot.tsx:1146` uses only formatted date/number values (not user input), making it low risk
- **Rate limiting**: Configured via `fastapi-ratelimit` with sensible defaults
- **Error handling**: `fastapi-errors` package handles error responses; exceptions generally caught at endpoint level
- **Site password in localStorage** (`frontend/src/store/index.ts:560`): This is a design trade-off for the header-based auth approach. Since the app uses a shared site password (not per-user credentials), and the session cookie provides the actual auth, the localStorage value is functionally equivalent to the session cookie in terms of security exposure. Flagging as a design note, not a vulnerability.
- **Formula injection in CSV export**: `export_service.py` sanitizes cell values starting with `=`, `+`, `-`, `@` -- properly handled
- **Auth on all endpoints**: All API endpoints use `VerifiedPassword` or `ApiKey` dependency -- no unauthenticated endpoints found (except health check and auth endpoints, which is correct)
