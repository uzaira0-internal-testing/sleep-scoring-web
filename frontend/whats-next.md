<original_task>
Fix all web issues from `reviews/web-issues-backlog.md` covering CRITICAL (3), HIGH (8), MEDIUM (5), and LOW (1) items. Also fix the "no data available" bug on non-first dates.
</original_task>

<work_completed>
## "No Data Available" on Non-First Dates (UNCOMMITTED)
- Added `onset_ts`/`offset_ts` query params to `markers.py:get_onset_offset_data()`
- `marker-data-table.tsx` passes client-side timestamps to the API
- Fixed `test_window_minutes_range` test for Annotated Query constraints

## CRITICAL Issues
- **C-1** (path traversal): Already fixed in previous session
- **C-2** (timing attack): Already fixed with `secrets.compare_digest`
- **C-3** (Nginx security headers): Fixed - added `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection` to `/assets/` and `/health` location blocks in `docker/frontend/nginx.conf`

## HIGH Issues
- **H-1 through H-5**: All fixed in previous session (commit 1c02e5d)
- **H-6** (dev creds): `docker/.env` already in `.gitignore`, not tracked
- **H-7/H-8**: Password hashing migration - these are F-01/F-02 refactors

## MEDIUM Issues
- **F-01/F-02**: Fixed in previous session (commit 1c02e5d)
- **F-14**: Fixed in previous session
- **F-15**: Fixed - replaced `assert True` placeholder in `tests/unit/services/test_data_loading_service.py`

## HTTP Integration Test Suite (F-06/F-07/F-08/F-09/F-10/F-13)
Created 6 new test files with 45 HTTP integration tests, all passing:
- `tests/web/test_api_files.py` - 10 tests (upload, list, dates, delete)
- `tests/web/test_api_activity.py` - 4 tests (activity data, scoring)
- `tests/web/test_api_markers.py` - 10 tests (CRUD, tables, adjacent)
- `tests/web/test_api_diary.py` - 7 tests (CRUD, upload)
- `tests/web/test_api_export.py` - 5 tests (columns, CSV)
- `tests/web/test_api_settings.py` - 9 tests (GET/PUT/DELETE)

## Test Infrastructure Fixes
- Fixed `conftest.py` sample CSV to start at noon (noon-to-noon view window)
- Patched `async_session_maker` so background tasks use test DB
- Fixed `MarkerType` enum values: `"MAIN_SLEEP"` (uppercase, matching StrEnum)

## All Tests Green
- Web tests: 165 passed
- Frontend tests: 84 passed
- Backend unit tests: 2036 passed, 7 skipped
</work_completed>

<work_remaining>
1. **Commit all uncommitted changes** - numerous files modified across multiple fix categories
2. **F-17** (migration tests): Tests only check instantiation, not actual migration logic (LOWER PRIORITY)
3. **F-18** (E2E plot-click test): No E2E test for plot-click marker placement in frontend (LOWER PRIORITY - requires Playwright infrastructure)
</work_remaining>

<context>
## Key Fixes
- Background tasks (`_update_user_annotation`, `_calculate_and_store_metrics`) bypass FastAPI DI and use module-level `async_session_maker` directly. Test conftest patches this for test isolation.
- Nginx `add_header` in child location blocks replaces ALL parent headers (not additive). Each location block needs its own security headers.
- `MarkerType.MAIN_SLEEP = "MAIN_SLEEP"` (uppercase) - Pydantic validation is case-exact for StrEnum.
- Activity endpoints use noon-to-noon view windows. Test sample data must start at noon to be visible.
- File DELETE endpoint returns 204 (not 200).
</context>
