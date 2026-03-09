# Test Coverage Review - Desktop Application

**Date**: 2026-02-25
**Scope**: Desktop tests only (`tests/unit/`, `tests/gui/`, `tests/integration/`). Web and frontend tests excluded.

---

## Test Suite Health Summary

| Suite | Result |
|-------|--------|
| `tests/unit/` | 2425 passed, 7 skipped (HEALTHY) |
| `tests/gui/` | 108 passed, 53 errors (PARTIALLY BROKEN) |

The 53 errors are all in `tests/gui/integration/test_real_e2e_workflow.py` -- caused by a frozen dataclass mutation bug in the fixture (`config.data_folder = str(temp_data_folder)` on a frozen `AppConfig`). The other 108 GUI tests pass.

---

## 1. E2E Hygiene Check

### Violations Found

#### VIOLATION-01: `mock_main_window` usage in tests marked `@pytest.mark.e2e` in `tests/gui/integration/test_complete_workflow.py`

- **Type**: VIOLATION
- **Priority**: HIGH
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_complete_workflow.py`
- **Description**: Multiple test classes (`TestStudySettingsConfiguration`, `TestFileImportWorkflow`, `TestAnalysisTabMarkerPlacement`, `TestMarkerSavingWorkflow`, `TestCompleteWorkflowIntegration`, `TestErrorHandlingWorkflow`) are decorated with `@pytest.mark.e2e` and `@pytest.mark.gui`, but they use the `mock_main_window` fixture heavily. The test policy explicitly states E2E tests must NOT use `mock_main_window`. These tests mock the very thing being tested -- e.g., `mock_main_window.data_service.set_data_folder = Mock(return_value=True)` then asserts `result is True`, which is just testing the mock itself.

  These tests should either:
  1. Be moved to `tests/gui/integration/` and re-tagged `@pytest.mark.integration`, OR
  2. Be rewritten to use real `SleepScoringMainWindow()` per the e2e fixture pattern in `test_e2e_smoke_startup_navigation.py`.

#### VIOLATION-02: `__new__()` usage in `tests/gui/integration/test_real_e2e_workflow.py`

- **Type**: VIOLATION
- **Priority**: HIGH
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_real_e2e_workflow.py`, line 128
- **Description**: The `real_main_window` fixture uses `SleepScoringMainWindow.__new__(SleepScoringMainWindow)` followed by manual `QMainWindow.__init__(window)`. The CLAUDE.md test policy forbids `__new__()` in E2E tests. The file is in `integration/` but classes are marked `@pytest.mark.e2e`. This file also has 53 errors because the fixture tries to mutate a frozen dataclass (`config.data_folder = str(temp_data_folder)`), making every test in this file non-functional.

#### VIOLATION-03: `store.dispatch()` in E2E tests without adequate justification

- **Type**: VIOLATION (minor, partially justified)
- **Priority**: LOW
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/e2e/test_e2e_marker_interaction.py`, lines 510, 514, 553, 555
- **Description**: Four `store.dispatch(Actions.date_navigated(...))` calls in `TestMarkerPersistence`. The comments explain this is due to a QMessageBox dialog guard that cannot be automated in headless mode, which is a valid justification per the policy (one-time environment seeding when no UI path exists). However, the policy notes this should include a comment explaining why, which it does. **This is borderline acceptable** but ideally the date navigation button could be tested with QMessageBox mocked.

---

## 2. Critical Path Coverage Analysis

### Covered Critical Paths

| Scenario | Test Location | Quality |
|----------|--------------|---------|
| Marker placement (time fields) | `tests/gui/e2e/test_e2e_marker_interaction.py::TestMarkerInteraction` | GOOD - types onset/offset, calls `set_manual_sleep_times()`, asserts Redux state |
| Marker placement (plot clicks) | `tests/gui/e2e/test_e2e_marker_interaction.py::TestPlotClickMarkerPlacement` | GOOD - emits `plot_left_clicked`, asserts complete period in Redux |
| Marker persistence after save | `tests/gui/e2e/test_e2e_marker_interaction.py::test_save_button_persists_markers_to_database` | GOOD - saves to DB, loads back, verifies onset/offset |
| Marker persistence across dates | `tests/gui/e2e/test_e2e_marker_interaction.py::TestMarkerPersistence` | GOOD - saves, navigates away/back, verifies restored |
| Marker deletion persistence | `tests/gui/e2e/test_e2e_marker_interaction.py::test_deleted_markers_stay_deleted_after_navigation` | GOOD - clears, saves, navigates, verifies still absent |
| Marker clear | `tests/gui/e2e/test_e2e_marker_interaction.py::test_clear_markers_removes_from_state` | GOOD - asserts periods list is empty after clear |
| No-sleep-day marking | `tests/gui/e2e/test_e2e_marker_interaction.py::TestNoSleepDay` | GOOD - marks no-sleep, overrides with real markers |
| No-sleep-day nap behavior | `tests/unit/ui/test_no_sleep_day_behavior.py` | GOOD - 4 behavioral tests with real store |
| Right-click cancel | `tests/gui/e2e/test_e2e_marker_interaction.py::test_right_click_cancels_incomplete_marker` | GOOD |
| Multi-period editing | `tests/gui/e2e/test_e2e_marker_interaction.py::TestMultiPeriodEditing` | GOOD |
| Sadeh algorithm | `tests/unit/core/test_sadeh.py` | EXCELLENT - 18 tests covering constants, edge cases, thresholds, NaN, negatives, cap behavior |
| Cole-Kripke algorithm | `tests/unit/core/test_cole_kripke.py` | GOOD |
| Algorithm edge: empty data | `tests/unit/core/test_sadeh.py::test_raises_for_empty_dataframe` | GOOD - raises ValueError |
| Algorithm edge: all sleep | `tests/unit/core/test_sadeh.py::test_low_activity_scores_sleep` | GOOD |
| Algorithm edge: all wake | `tests/unit/core/test_sadeh.py::test_high_activity_scores_wake` | GOOD |
| Export correctness | `tests/unit/services/test_export_service.py` | EXCELLENT - 40+ tests covering columns, grouping, sanitization, atomicity, backup rotation |
| CSV file loading | `tests/unit/io/test_loaders.py`, `tests/unit/test_csv_datasource.py` | GOOD |
| GT3X file loading | `tests/unit/test_gt3x_datasource.py`, `tests/integration/test_gt3x_loading.py` | EXCELLENT - 50+ tests |
| Database migrations | `tests/unit/data/test_migrations.py` | EXCELLENT - all 14 migrations tested individually, idempotency tested, MigrationManager lifecycle tested |
| Redux store | `tests/unit/ui/test_store.py` | EXCELLENT - 76 tests covering all actions, reducer, selectors, store lifecycle, middleware |
| Connector lifecycle | `tests/unit/ui/connectors/test_connector_manager.py` | GOOD - connect_all, disconnect_all, no double-connect |
| Connector subscribe/unsubscribe | `tests/unit/ui/connectors/test_settings_connector.py`, `test_navigation_connector.py` | GOOD |
| Time field coordinator | `tests/unit/ui/coordinators/test_time_field_coordinator.py` | GOOD - init, update, duration, overnight, invalid format |
| Autosave coordinator | `tests/unit/ui/test_coordinators.py` | EXCELLENT - debounce, pending changes, force save, cleanup, callbacks |
| Sleep period metrics | `tests/unit/core/test_sleep_period_metrics.py` | GOOD - TST, efficiency, WASO, awakenings |
| Settings persistence (E2E) | `tests/gui/e2e/test_e2e_settings_persistence.py` | GOOD - algorithm, nonwear algo, ID pattern, view mode |
| Startup + navigation (E2E) | `tests/gui/e2e/test_e2e_smoke_startup_navigation.py` | GOOD - window visible, 4 tabs, import, date nav, view toggle |

### Coverage Gaps

#### GAP-01: No E2E test for full data export via UI

- **Type**: COVERAGE_GAP
- **Priority**: HIGH
- **Location**: Missing from `tests/gui/e2e/`
- **Description**: While unit tests in `test_export_service.py` thoroughly test `ExportManager` methods, there is no E2E test that navigates to the Export tab, clicks the export button, and verifies the CSV file is created on disk with correct content. The `test_complete_workflow.py` tests that attempt this use `mock_main_window` (VIOLATION-01 above), which tests the mock not the real app. The real E2E fixtures in `test_e2e_smoke_startup_navigation.py` never navigate to the Export tab to perform an export.

#### GAP-02: No test for file loading error UI feedback

- **Type**: COVERAGE_GAP
- **Priority**: MEDIUM
- **Location**: Missing from `tests/gui/e2e/` or `tests/gui/integration/`
- **Description**: Per the CLAUDE.md Known Issues section, database queries and data loading can fail silently. No test verifies that a user-visible error or warning is shown when: (a) a file fails to import, (b) the database query returns 0 rows unexpectedly, or (c) a corrupt CSV is selected. The `test_faithful_integration.py::TestErrorHandling::test_algorithm_handles_empty_data` catches `ValueError` but the `except` block uses bare `pass`, never asserting any behavior.

#### GAP-03: No test for keyboard shortcuts via actual key events

- **Type**: COVERAGE_GAP
- **Priority**: MEDIUM
- **Location**: `tests/gui/e2e/test_e2e_smoke_startup_navigation.py::test_keyboard_shortcut_date_navigation`
- **Description**: The test calls `window.next_date()` and `window.prev_date()` directly instead of sending actual key events. The comment says "QShortcut-registered sequences don't reliably fire via QTest.keyClick in headless mode." While practical, this means the shortcut registration itself is untested. No test verifies that pressing the right/left arrow keys triggers the correct callbacks.

#### GAP-04: No test for marker drag/move behavior

- **Type**: COVERAGE_GAP
- **Priority**: MEDIUM
- **Location**: Missing
- **Description**: Marker placement via click and time fields is tested, but marker dragging (moving an existing onset or offset to a new timestamp) is not tested at any level (unit, integration, or E2E). The `move_marker_to_timestamp` method exists but is only mocked in `test_complete_workflow.py`.

#### GAP-05: No test for Choi nonwear algorithm edge cases (unit level)

- **Type**: COVERAGE_GAP
- **Priority**: LOW
- **Location**: Missing from `tests/unit/core/test_choi_algorithm.py`
- **Description**: While `test_choi_algorithm.py` exists, there are no explicit tests for edge cases like: all-zero data (everything nonwear), all-nonzero data (no nonwear), data shorter than the minimum nonwear window (90 min for Choi), or data with exactly one spike in a nonwear window. The `test_faithful_integration.py` tests Choi at the integration level but with randomly-generated data where results are approximate, not deterministic.

#### GAP-06: No test for batch scoring service

- **Type**: COVERAGE_GAP
- **Priority**: LOW
- **Location**: `tests/unit/services/test_batch_scoring_service.py` exists but needs verification
- **Description**: The file exists (discovered in glob results) but was not read. If it is comprehensive, this gap does not apply. The batch scoring service runs algorithms across all dates for a participant, which is a key workflow.

---

## 3. Test Quality Issues

#### QUALITY-01: `test_real_e2e_workflow.py` is entirely broken (53 errors)

- **Type**: BROKEN_TEST
- **Priority**: CRITICAL
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_real_e2e_workflow.py`
- **Description**: The `temp_config` fixture at line 109 tries `config.data_folder = str(temp_data_folder)` on a frozen `AppConfig` dataclass, raising `FrozenInstanceError` for every single test that depends on it (all 53 tests). The correct pattern is used in `test_e2e_marker_interaction.py` which uses `dataclasses.replace()`. This has been broken since `AppConfig` was made frozen and no one noticed because these tests were probably not in CI, or they were silently skipping.

  **Fix**: Change `temp_config` fixture to use `replace(AppConfig.create_default(), data_folder=str(temp_data_folder), export_directory=str(tmp_path / "exports"))`.

#### QUALITY-02: `test_complete_workflow.py` tests mock the thing being tested

- **Type**: QUALITY
- **Priority**: HIGH
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_complete_workflow.py`
- **Description**: Multiple tests are effectively no-ops because they mock the service then assert the mock's return value. Examples:
  - `test_set_data_folder`: Mocks `set_data_folder = Mock(return_value=True)`, calls it, asserts `True`. Tests nothing.
  - `test_discover_csv_files`: Mocks `find_available_files = Mock(return_value=file_infos)`, calls it, asserts the mock return. Tests nothing.
  - `test_load_file_and_extract_dates`: Same pattern.
  - `test_configure_algorithm_preferences`: Sets attributes on a mock, reads them back. Tests nothing.
  - `test_handles_missing_data_folder`: Mocks return `False`, asserts `False`.
  - `test_handles_database_save_failure`: Mocks return `False`, asserts `False`.

  These provide zero coverage of actual application behavior. The tests that DO use `isolated_db` directly (like `TestExportWorkflow`) are legitimate service-level integration tests and should be re-tagged as `@pytest.mark.integration` not `@pytest.mark.e2e`.

#### QUALITY-03: `test_faithful_integration.py::TestErrorHandling` has bare `pass` in except

- **Type**: QUALITY
- **Priority**: MEDIUM
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_faithful_integration.py`, lines 785-810
- **Description**: `test_algorithm_handles_empty_data` and `test_algorithm_handles_nan_values` catch exceptions with bare `pass`, meaning the test passes regardless of behavior. These tests assert nothing when exceptions occur, violating the "every test must assert observable outcomes" rule. They should either:
  - Assert that a specific exception is raised (`pytest.raises`), or
  - Assert that the function returns a specific fallback value.

#### QUALITY-04: `test_export_tab.py` tests a fabricated widget, not the real ExportTab

- **Type**: QUALITY
- **Priority**: MEDIUM
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_export_tab.py`
- **Description**: The `export_widget` fixture creates a `QWidget()` from scratch with manually-added buttons, labels, and combos that mimic the ExportTab. It does NOT instantiate the real `ExportTab` class. All assertions test the manually-constructed fake widget's behavior (e.g., `assert btn.text() == "Export to CSV"`), which is testing Qt itself, not the application. These tests provide zero assurance that the real ExportTab works.

#### QUALITY-05: `test_main_window_tabs.py` tests generic QTabWidget, not real app tabs

- **Type**: QUALITY
- **Priority**: LOW
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_main_window_tabs.py`
- **Description**: The `tab_widget_with_tabs` fixture creates a plain `QTabWidget` with four plain `QWidget` children. All tests verify generic Qt behavior (tab count, tab switching, signal emission). The real app's tabs are complex custom widgets (`AnalysisTab`, `ExportTab`, `StudySettingsTab`, `DataSettingsTab`). These tests would pass even if the real app had zero tabs.

#### QUALITY-06: Random seeds not controlled in data generators

- **Type**: QUALITY
- **Priority**: LOW
- **Location**: Multiple E2E test files using `np.random.randint()` for activity data generation
- **Description**: `_create_test_csv()` in E2E tests uses `np.random.randint()` without setting a seed. This makes tests non-deterministic: a test might produce different activity patterns on each run, potentially causing flaky pass/fail with threshold-based assertions. The `test_faithful_integration.py::TestSadehAlgorithmExecution` asserts `sleep_percentage > 70` which could theoretically fail with an unlucky random seed.

---

## 4. Misplacement Issues

#### MISPLACED-01: Test classes in `test_complete_workflow.py` are tagged `@pytest.mark.e2e` but belong in `integration` or `unit`

- **Type**: VIOLATION
- **Priority**: HIGH
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_complete_workflow.py`
- **Description**: Per test policy, tests using `mock_main_window` belong in `integration` or `unit`, not `e2e`. The file is already in the `integration/` directory (correct placement) but the marker is wrong. All `@pytest.mark.e2e` decorators in this file should be changed to `@pytest.mark.integration`.

#### MISPLACED-02: `test_real_e2e_workflow.py` and `test_faithful_integration.py` are in `integration/` but tagged `@pytest.mark.e2e`

- **Type**: VIOLATION
- **Priority**: MEDIUM
- **Location**: `D:/Scripts/monorepo/apps/sleep-scoring-demo/tests/gui/integration/test_real_e2e_workflow.py` and `test_faithful_integration.py`
- **Description**: Both files live in `tests/gui/integration/` but use `@pytest.mark.e2e`. The test policy says E2E tests go in `tests/gui/e2e/`. Either move the files or retag them. `test_faithful_integration.py` tests algorithms and data loading without UI, so `@pytest.mark.e2e` is questionable (these are really integration tests of the core/services layers).

---

## 5. Priority-Ordered Action Items

| Priority | Finding | Action |
|----------|---------|--------|
| CRITICAL | QUALITY-01 | Fix frozen dataclass bug in `test_real_e2e_workflow.py` fixture: use `replace()` instead of assignment. This will restore 53 tests. |
| HIGH | VIOLATION-01, QUALITY-02 | Retag `test_complete_workflow.py` classes from `@pytest.mark.e2e` to `@pytest.mark.integration`. Rewrite mock-the-mock tests to test actual behavior, or delete them if covered elsewhere. |
| HIGH | GAP-01 | Add E2E test for export workflow: navigate to Export tab, click export, verify CSV on disk. |
| HIGH | VIOLATION-02 | Fix `test_real_e2e_workflow.py` to use normal constructor (match the pattern in `test_e2e_smoke_startup_navigation.py`). |
| MEDIUM | MISPLACED-01, MISPLACED-02 | Fix pytest markers to match directory placement. |
| MEDIUM | GAP-02 | Add tests for error feedback when file loading fails. |
| MEDIUM | GAP-03 | Document or add test for keyboard shortcut registration (even if via callback test). |
| MEDIUM | QUALITY-03 | Replace bare `pass` in error handling tests with proper assertions. |
| MEDIUM | QUALITY-04 | Rewrite `test_export_tab.py` to test real `ExportTab` class or delete. |
| MEDIUM | GAP-04 | Add unit test for marker drag/move behavior. |
| LOW | QUALITY-05 | Rewrite `test_main_window_tabs.py` to use real tab classes or delete. |
| LOW | QUALITY-06 | Set `np.random.seed()` in test fixtures that generate random activity data. |
| LOW | GAP-05 | Add deterministic edge case tests for Choi algorithm. |

---

## 6. Strengths

The test suite has several notable strengths:

1. **Redux store tests** (`test_store.py`) are exemplary: 76 tests covering every action type, reducer branch, boundary check, middleware, subscriber lifecycle, and concurrent dispatch protection.

2. **Database migration tests** (`test_migrations.py`) are thorough: every migration (1-14) has creation, execution, and column verification tests. Idempotency is tested. The `MigrationManager` is tested for status, history, version targeting, and pending detection.

3. **True E2E tests** in `tests/gui/e2e/` are well-structured: they construct real `SleepScoringMainWindow()`, use `qtbot.mouseClick` and `qtbot.keyClicks` for user-like interaction, and assert both UI state and Redux state.

4. **Export service tests** are comprehensive: 40+ tests cover CSV structure, column presence, grouping, sanitization against formula injection, atomic writes, backup rotation, and edge cases.

5. **Algorithm tests** cover both Sadeh and Cole-Kripke with edge cases, threshold boundaries, and variant comparisons.

6. **Unit test pass rate** is excellent: 2425 passed with only 7 skips and zero failures.
