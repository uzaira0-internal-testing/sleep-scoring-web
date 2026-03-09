# Test Coverage Review: sleep-scoring-demo

**Date**: 2026-02-25
**Reviewer**: Claude (automated)
**Scope**: Full test suite analysis for coverage gaps, broken tests, quality issues, and policy violations

---

## Current Test Suite State

### Desktop Unit Tests
```
4 failed, 2378 passed, 7 skipped (73s)
```

**All 4 failures** in `tests/unit/services/test_batch_scoring_service.py`:
- `TestAutoScoreWithRealFiles::test_auto_score_processes_real_files_and_returns_results`
- `TestAutoScoreWithRealFiles::test_auto_score_diary_times_constrain_detection`
- `TestProcessActivityFile::test_process_activity_file_success_with_content_verification`
- `TestExtractParticipantInfo::test_extract_participant_info_success`

Root cause: Participant ID extraction returns `'UNKNOWN'` instead of expected `'DEMO-001'`/`'DEMO-002'`. The ID pattern or extraction logic changed without updating tests.

### Web Tests
```
22 failed, 131 passed, 1 error (3.69s)
```

**14 failures** in `test_auth.py` -- tests assume JWT-based auth (register/login/refresh/bearer tokens) but the actual web app uses site-password auth (`X-Username`/`X-Site-Password` headers, as configured in `conftest.py`). These tests are testing auth endpoints that no longer exist.

**8 failures** in `test_files.py` -- cascading from the auth mechanism mismatch (wrong status codes, KeyError on response parsing).

### Hygiene Check (E2E Policy)
```bash
rg -n "assert True|pass\s*#\s*Placeholder|mock_main_window|__new__\(|store\.dispatch\(" tests/gui/e2e
```
**Result**: No violations found in E2E test files. All 3 E2E files (`test_e2e_marker_interaction.py`, `test_e2e_settings_persistence.py`, `test_e2e_smoke_startup_navigation.py`) comply with the test policy.

---

## Findings

### F-01: BROKEN_TEST -- Web Auth Tests Against Non-Existent JWT Endpoints

- **Type**: BROKEN_TEST
- **Location**: `tests/web/test_auth.py` (all 14 tests)
- **Priority**: HIGH
- **Description**: Every test in this file tests JWT-based auth (POST `/auth/register`, POST `/auth/login`, POST `/auth/refresh`, GET `/auth/me`) with bearer tokens. The web app was migrated to site-password auth using `X-Username`/`X-Site-Password` headers. These endpoints no longer exist. All 14 tests fail with 404s or wrong status codes. The `conftest.py` already has the correct site-password auth setup (`auth_headers` fixture), but `test_auth.py` never uses it.

### F-02: BROKEN_TEST -- Web File Tests Fail Due to Auth Mismatch

- **Type**: BROKEN_TEST
- **Location**: `tests/web/test_files.py` (8 failures)
- **Priority**: HIGH
- **Description**: Several file tests fail because they depend on the JWT auth mechanism that was removed. Specific failures:
  - `test_upload_without_auth` expects 401 but gets 200 (site-password middleware differs)
  - `test_list_files_*` fail with `KeyError` on response parsing (response structure changed)
  - `test_delete_file_as_annotator_forbidden` and `test_scan_as_annotator_forbidden` fail (role enforcement changed)

### F-03: BROKEN_TEST -- Batch Scoring Service Participant ID Extraction

- **Type**: BROKEN_TEST
- **Location**: `tests/unit/services/test_batch_scoring_service.py` (4 failures)
- **Priority**: MEDIUM
- **Description**: Participant ID extraction returns `'UNKNOWN'` instead of expected values (`'DEMO-001'`, `'DEMO-002'`). The `id_pattern` regex or the extraction logic in `batch_scoring_service.py` was modified without updating the test expectations. This also causes downstream failures where diary times cannot be matched (no diary entry found for `'UNKNOWN'`).

---

### F-04: COVERAGE_GAP -- No E2E Test for Marker Persistence Across Date Navigation

- **Type**: COVERAGE_GAP
- **Location**: Missing
- **Priority**: CRITICAL
- **Description**: The prompt identifies this as the app's most critical path, and there are 3 recent commits fixing exactly this bug (`54f0e09`, `6948c31`). Yet no E2E test exists for this scenario:
  1. Place onset/offset markers on Day 1
  2. Save markers
  3. Navigate to Day 2
  4. Navigate back to Day 1
  5. Assert markers are still present in both store state and database

  The existing `test_save_button_persists_markers_to_database` only tests save on a single day. The view-mode persistence test (`test_view_mode_persists_across_file_selection`) tests settings persistence, not marker persistence.

### F-05: COVERAGE_GAP -- No E2E Test for Marker Deletion Persistence

- **Type**: COVERAGE_GAP
- **Location**: Missing
- **Priority**: HIGH
- **Description**: Commit `6948c31` fixed "marker deletion not persisting after date navigation." There is `test_clear_markers_removes_from_state` which tests clearing markers from Redux state, but no test verifies:
  1. Place and save markers
  2. Delete a specific period
  3. Navigate away and back
  4. Assert the deleted period is NOT reloaded from the database

  Unit tests for `SleepMarkerPersistence.delete()` and `NonwearMarkerPersistence.delete()` exist but only verify the mock DB call -- they do not test the full round-trip.

### F-06: COVERAGE_GAP -- No Web API Integration Tests for Marker Endpoints (6 routes)

- **Type**: COVERAGE_GAP
- **Location**: `tests/web/test_markers.py` tests only Pydantic models; `sleep_scoring_web/api/markers.py` has 6 untested routes
- **Priority**: HIGH
- **Description**: The marker API has 6 endpoints, none tested through actual HTTP requests:
  - `GET /{file_id}/{analysis_date}` -- get markers for a date
  - `PUT /{file_id}/{analysis_date}` -- save/update markers
  - `DELETE /{file_id}/{analysis_date}/{period_index}` -- delete a period
  - `GET /{file_id}/{analysis_date}/adjacent` -- get adjacent day markers
  - `GET /{file_id}/{analysis_date}/table/{period_index}` -- get epoch table for a period
  - `GET /{file_id}/{analysis_date}/table-full` -- get full epoch table

  `test_markers.py` constructs `OnsetOffsetDataPoint`, `OnsetOffsetResponse`, and other Pydantic models directly and asserts field values. It never calls `client.get()`, `client.put()`, or `client.delete()`. This means serialization, DB persistence, error handling, and response formatting of the actual endpoints are completely untested.

### F-07: COVERAGE_GAP -- No Web API Tests for Activity Endpoints (3 routes)

- **Type**: COVERAGE_GAP
- **Location**: Missing; `sleep_scoring_web/api/activity.py` has 3 untested routes
- **Priority**: MEDIUM
- **Description**: Three activity API endpoints have zero tests:
  - `GET /{file_id}/{analysis_date}` -- get activity data
  - `GET /{file_id}/{analysis_date}/score` -- get scored activity
  - `GET /{file_id}/{analysis_date}/sadeh` -- get Sadeh algorithm results

### F-08: COVERAGE_GAP -- No Web API Integration Tests for Diary Endpoints (4 routes)

- **Type**: COVERAGE_GAP
- **Location**: `tests/web/test_diary.py` tests only Pydantic models and helper functions; `sleep_scoring_web/api/diary.py` has 4 untested routes
- **Priority**: MEDIUM
- **Description**: Four diary API endpoints untested through HTTP:
  - `GET /{file_id}/{analysis_date}` -- get diary entry
  - `PUT /{file_id}/{analysis_date}` -- create/update diary entry
  - `DELETE /{file_id}/{analysis_date}` -- delete diary entry
  - `POST /{file_id}/upload` -- upload diary CSV

  `test_diary.py` tests `DiaryEntryResponse` model construction and helper functions (`get_time_field`, `get_int_field`, etc.) but makes no HTTP requests.

### F-09: COVERAGE_GAP -- No Web API Integration Tests for Settings Endpoints (3 routes)

- **Type**: COVERAGE_GAP
- **Location**: `tests/web/test_settings.py` tests only Pydantic models; `sleep_scoring_web/api/settings.py` has 3 untested routes
- **Priority**: LOW
- **Description**: Three settings API endpoints untested through HTTP:
  - `GET ""` -- get current settings
  - `PUT ""` -- update settings
  - `DELETE ""` -- reset settings

  `test_settings.py` tests `SettingsResponse` and `SettingsUpdate` model construction but makes no API calls.

### F-10: COVERAGE_GAP -- No Web API Integration Tests for Export Endpoints (4 routes)

- **Type**: COVERAGE_GAP
- **Location**: `tests/web/test_export.py` tests utility classes; `sleep_scoring_web/api/export.py` has 4 untested routes
- **Priority**: MEDIUM
- **Description**: Four export API endpoints untested through HTTP:
  - `GET /columns` -- get available export columns
  - `POST /csv` -- generate CSV export
  - `POST /csv/download` -- download CSV export
  - `GET /csv/quick` -- quick CSV export

  `test_export.py` tests `ColumnRegistry` and `ExportService` utility methods but no actual HTTP round-trips.

### F-11: COVERAGE_GAP -- 9 of 12 Connectors Have No Test Coverage

- **Type**: COVERAGE_GAP
- **Location**: `sleep_scoring_app/ui/connectors/`
- **Priority**: MEDIUM
- **Description**: The connectors layer bridges widgets and the Redux store. Only 3 of 12 connectors have dedicated tests:

  | Connector | Has Tests? | Notes |
  |-----------|-----------|-------|
  | `marker.py` (MarkersConnector) | Yes | `test_marker_connector_filtering.py` |
  | `table.py` (SideTableConnector) | Yes | `test_side_table_connector.py` |
  | `plot.py` (PlotClickConnector) | Partial | Tested indirectly in `test_no_sleep_day_behavior.py` |
  | `activity.py` | No | |
  | `error.py` | No | |
  | `file.py` | No | |
  | `manager.py` | No | |
  | `navigation.py` | No | |
  | `persistence.py` | No | |
  | `save_status.py` | No | |
  | `settings.py` | No | |
  | `ui_controls.py` | No | |

  The `navigation.py` connector is particularly concerning since date navigation is a critical path with recent bugs.

### F-12: COVERAGE_GAP -- 6 of 9 Coordinators Have No Dedicated Tests

- **Type**: COVERAGE_GAP
- **Location**: `sleep_scoring_app/ui/coordinators/`
- **Priority**: MEDIUM
- **Description**: Only 3 of 9 coordinators have dedicated test coverage:

  | Coordinator | Has Tests? | Notes |
  |-------------|-----------|-------|
  | `autosave_coordinator.py` | Yes | `test_coordinators.py` |
  | `marker_loading_coordinator.py` | Yes | `test_coordinators.py` |
  | `diary_integration_coordinator.py` | Partial | Tested in `test_coordinators.py` via SessionStateService |
  | `analysis_dialog_coordinator.py` | No | |
  | `diary_table_connector.py` | No | |
  | `import_ui_coordinator.py` | No | |
  | `seamless_source_switcher.py` | No | Has integration tests in `tests/gui/integration/` |
  | `time_field_coordinator.py` | No | Critical for marker placement workflow |
  | `ui_state_coordinator.py` | No | |

  `time_field_coordinator.py` is especially important since it drives the onset/offset time field behavior used in marker placement.

---

### F-13: QUALITY -- Web Marker Tests Only Validate Pydantic Models, Not Behavior

- **Type**: QUALITY
- **Location**: `tests/web/test_markers.py`
- **Priority**: HIGH
- **Description**: All 13 test methods in this file construct Pydantic model instances and assert on field values. None make HTTP requests. For example, `test_data_point_required_fields` creates an `OnsetOffsetDataPoint(timestamp=..., sadeh=..., ...)` and asserts `point.timestamp == 1704067200.0`. This tests Pydantic's constructor, not the application. The `TestAlgorithmIntegration` class name is misleading -- it only tests that model fields accept certain values.

### F-14: QUALITY -- Empty Test Body in test_markers.py

- **Type**: QUALITY
- **Location**: `tests/web/test_markers.py:187-194` (`test_window_minutes_range`)
- **Priority**: LOW
- **Description**: Test method has an empty body with only `pass # Constraint validation is done by FastAPI`. The docstring claims to test "Window minutes should be between 5 and 120" but validates nothing. If the constraint is removed from the API, this test would still pass.

### F-15: QUALITY -- assert True Used as No-Crash Test

- **Type**: QUALITY
- **Location**: `tests/unit/services/test_data_loading_service.py:401`
- **Priority**: LOW
- **Description**: `assert True  # Fallback doesn't raise` -- the test calls `service.load_real_data()` but discards the result and only asserts that no exception was raised. The return value (which could be None or valid data) is never checked. A regression that returns corrupt data instead of raising would pass this test.

### F-16: QUALITY -- Redundant assert True After Real Assertions

- **Type**: QUALITY
- **Location**: `tests/integration/test_gt3x_loading.py:464`
- **Priority**: NEGLIGIBLE
- **Description**: `assert True` appears after valid assertions (`assert metadata["total_epochs"] == len(df)`, `assert column_mapping.activity_column == DatabaseColumn.AXIS_Y`). The comment says "Workflow completed successfully." This is cosmetic noise -- the real assertions above it are fine.

### F-17: QUALITY -- Migration Tests 002-013 Only Test Instantiation

- **Type**: QUALITY
- **Location**: `tests/unit/data/test_migrations.py` (classes `TestMigration002` through `TestMigration013`)
- **Priority**: MEDIUM
- **Description**: Migrations 002 through 013 each have a single test that creates the migration instance and asserts its `version` number and `description` contains a keyword. None of them test the actual `up()` method against a real database. Only `TestMigration001` tests actual DB schema creation. This means schema changes from migrations 002-013 (adding columns, renaming columns, adding JSON fields) have never been verified to actually work against SQLite.

  The `TestMigrationIdempotency` class does run all migrations sequentially, which provides some coverage for execution success, but individual migration tests don't verify schema results.

---

### F-18: VIOLATION -- No E2E Test for Plot-Click Marker Placement

- **Type**: VIOLATION (of "most critical paths" requirement)
- **Location**: Missing
- **Priority**: HIGH
- **Description**: The E2E marker interaction test (`test_e2e_marker_interaction.py`) places markers by typing times into onset/offset time fields and calling `window.set_manual_sleep_times()`. This is valid but does not test the primary user workflow: clicking on the activity plot to place onset/offset markers. Plot-click marker placement is the most common user interaction and goes through a completely different code path (`PlotClickConnector` -> `MarkerInteractionHandler` -> store dispatch).

  No E2E test simulates clicking on the plot at a specific X coordinate to place an onset marker, then clicking again to place an offset marker.

### F-19: COVERAGE_GAP -- No Test for No-Sleep-Day Effects on Algorithm Scoring

- **Type**: COVERAGE_GAP
- **Location**: Missing
- **Priority**: MEDIUM
- **Description**: The unit tests in `test_no_sleep_day_behavior.py` thoroughly test that no-sleep-day:
  - Clears sleep markers
  - Prevents nap creation
  - Prevents main sleep creation
  - Prevents algorithm scoring when set

  But there is no test for the reverse: marking a day as no-sleep-day that previously had saved markers, then unmarking it, and verifying previous markers can be restored or new ones can be placed again.

### F-20: COVERAGE_GAP -- No Test for Multi-Period Marker Editing

- **Type**: COVERAGE_GAP
- **Location**: Missing
- **Priority**: MEDIUM
- **Description**: When a date has multiple sleep periods (main sleep + naps), the user needs to select a specific period before editing its onset/offset. No test verifies:
  1. Place a main sleep period
  2. Place a nap period
  3. Select the nap period
  4. Edit the nap's onset time
  5. Assert only the nap was modified, not the main sleep

### F-21: COVERAGE_GAP -- No Test for Export Data Correctness End-to-End

- **Type**: COVERAGE_GAP
- **Location**: Missing
- **Priority**: MEDIUM
- **Description**: `test_export_service.py` has thorough unit tests for `ExportManager` (CSV sanitization, path validation, grouping), but no integration test loads real data, places markers, scores them, exports to CSV, and then reads the CSV back to verify the exported values match. The unit tests mock the data inputs. A regression in the data flow from store -> export could go undetected.

---

## Summary by Priority

| Priority | Count | IDs |
|----------|-------|-----|
| CRITICAL | 1 | F-04 |
| HIGH | 6 | F-01, F-02, F-05, F-06, F-13, F-18 |
| MEDIUM | 9 | F-03, F-07, F-08, F-10, F-11, F-12, F-17, F-19, F-20, F-21 |
| LOW | 3 | F-09, F-14, F-15 |
| NEGLIGIBLE | 1 | F-16 |

## Summary by Type

| Type | Count | IDs |
|------|-------|-----|
| BROKEN_TEST | 3 | F-01, F-02, F-03 |
| COVERAGE_GAP | 11 | F-04, F-05, F-06, F-07, F-08, F-09, F-10, F-11, F-12, F-19, F-20, F-21 |
| QUALITY | 5 | F-13, F-14, F-15, F-16, F-17 |
| VIOLATION | 1 | F-18 |

## Recommended Action Order

1. **Fix F-04** (CRITICAL): Write E2E test for marker persistence across date navigation. This is the app's most-fixed bug and has zero test coverage.
2. **Fix F-01, F-02**: Either rewrite web auth tests for site-password auth or delete the dead JWT tests entirely. The 22 broken web tests create noise that masks real regressions.
3. **Fix F-06, F-13**: Replace Pydantic-only marker tests with real HTTP integration tests. Marker save/load/delete through the API is the web app's core functionality.
4. **Fix F-18**: Add E2E test for plot-click marker placement (the primary user workflow).
5. **Fix F-05**: Add E2E test for marker deletion + navigation round-trip.
6. **Fix F-03**: Update batch scoring tests to match current participant ID extraction logic.
7. **Fix F-17**: Add actual DB-level assertions for migrations 002-013.
8. **Fix F-07, F-08, F-10**: Add HTTP integration tests for activity, diary, and export API endpoints.
9. **Fix F-11, F-12**: Add unit tests for untested connectors and coordinators, prioritizing `navigation.py` and `time_field_coordinator.py`.
