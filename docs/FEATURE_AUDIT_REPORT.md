# Sleep Scoring Application Feature Audit Report

**Audit Date:** 2026-01-09
**Auditor:** Claude Code
**Scope:** Comprehensive review of Redux store pattern, connector coverage, state synchronization, and feature integration

---

## Executive Summary

The Sleep Scoring Application has undergone significant architectural refactoring to implement a Redux-style store pattern. This audit examined the codebase for broken features, missing functionality, and integration issues.

### Findings by Severity

| Severity | Count | Description |
|----------|-------|-------------|
| Critical | 0 | No blocking bugs found |
| High | 3 | Issues affecting user experience |
| Medium | 5 | Inconveniences and incomplete patterns |
| Low | 4 | Polish items and minor inconsistencies |
| Dead Code | 2 | Methods that can be safely removed |
| Test Gaps | 3 | Missing test coverage |

**Overall Assessment:** The Redux refactor is well-executed. The connector pattern is consistently applied, services are properly headless, and the architecture follows the documented patterns. However, there are several areas where the transition is incomplete or could be improved.

---

## Critical Issues

**None identified.** All major features appear functional based on code review.

---

## High Priority Issues

### HIGH-001: Duplicate File Selection Handlers

**Location:**
- `sleep_scoring_app/ui/file_navigation.py:139-180` - `FileNavigationManager.on_file_selected_from_table()`
- `sleep_scoring_app/ui/main_window.py:825-878` - `MainWindow.on_file_selected_from_table()`

**Description:** Two methods exist for handling file selection from table. The `FileNavigationManager` version notes "file_selected action is ALREADY dispatched by SignalsConnector" but the `MainWindow` version also dispatches the same action. This creates potential for double-dispatch or race conditions.

**Evidence:**
```python
# main_window.py:847
self.store.dispatch(Actions.file_selected(file_info.filename))

# file_navigation.py:154-156 (comment indicating it's redundant)
# NOTE: file_selected action is ALREADY dispatched by SignalsConnector
# DO NOT dispatch again here - it would clear dates that we're about to load
```

**Suggested Fix:**
1. Remove duplicate dispatch from `MainWindow.on_file_selected_from_table()`
2. Consolidate file selection logic into single path through `FileNavigationManager`
3. Update `UIControlsConnector._on_file_selected()` to delegate to `FileNavigationManager`

**Effort:** 2-3 hours

---

### HIGH-002: Incomplete Error Propagation to User

**Location:** Multiple locations in `sleep_scoring_app/ui/connectors/activity.py:141-152`

**Description:** When activity data loading fails, the connector logs an exception and dispatches empty data, but the user receives no visual feedback that an error occurred. The application silently shows no data.

**Evidence:**
```python
except Exception as e:
    logger.exception(f"ACTIVITY DATA CONNECTOR: Error loading data: {e}")
    # Dispatch empty data on error
    self.store.dispatch_safe(
        Actions.activity_data_loaded(
            timestamps=[],
            axis_x=[],
            axis_y=[],
            axis_z=[],
            vector_magnitude=[],
        )
    )
```

**Suggested Fix:**
1. Add `Actions.error_occurred(message, severity)` action to store
2. Create `ErrorNotificationConnector` that shows status bar messages or dialog for errors
3. Dispatch error action alongside empty data

**Effort:** 3-4 hours

---

### HIGH-003: Missing Connector for Time Field Updates

**Location:** `sleep_scoring_app/ui/main_window.py:1233-1352` - `update_sleep_info()` and related methods

**Description:** The time field updates (onset_time_input, offset_time_input, total_duration_label) are still directly updated by `MainWindow.update_sleep_info()` rather than through a connector. This bypasses the Redux pattern and can lead to state synchronization issues.

**Evidence:**
```python
# main_window.py:1287-1288 - Direct widget manipulation outside connector
self.onset_time_input.setText(start_time.strftime("%H:%M"))
self.offset_time_input.setText(end_time.strftime("%H:%M"))
```

The `TimeFieldCoordinator` exists but is used for field-to-marker updates (user input), not store-to-field updates (marker changes).

**Suggested Fix:**
1. Create `TimeFieldConnector` that subscribes to `current_sleep_markers` changes
2. Move time field update logic from `MainWindow` to connector
3. Connector should read from store state and update UI

**Effort:** 2-3 hours

---

## Medium Priority Issues

### MED-001: hasattr() Usage Patterns

**Location:** Multiple files (see grep output below)

**Description:** While most `hasattr()` uses are marked with `# KEEP:` comments explaining why they're valid, there are some that could be replaced with Protocol checks or null checks.

**Affected locations with potential improvement:**
- `sleep_scoring_app/ui/main_window.py:998` - `hasattr(self, "autosave_coordinator")` - Should check `if self.autosave_coordinator is not None`
- `sleep_scoring_app/ui/file_navigation.py:131` - `self.parent._refresh_file_dropdown_indicators()` - Uses parent directly

**Suggested Fix:** Replace runtime `hasattr()` checks with:
1. Protocol type hints where applicable
2. Optional type annotations with null checks
3. Initialize attributes to `None` in `__init__` rather than relying on `hasattr`

**Effort:** 1-2 hours

---

### MED-002: FileNavigationManager Redundant with Connectors

**Location:** `sleep_scoring_app/ui/file_navigation.py`

**Description:** The `FileNavigationManager` class duplicates some functionality that is now handled by connectors. Specifically:
- `update_navigation_buttons()` duplicates `NavigationConnector._update_navigation()`
- `on_date_dropdown_changed()` functionality overlaps with `DateDropdownConnector`

This creates two paths for the same operations, one through the manager and one through connectors.

**Suggested Fix:**
1. Remove redundant methods from `FileNavigationManager`
2. Keep only file selection orchestration logic that involves multiple side effects
3. Update any remaining callers to use connectors

**Effort:** 2-3 hours

---

### MED-003: Inconsistent Store Access Patterns

**Location:** Various widgets and handlers

**Description:** Some widgets directly access `self.store.state` while others go through the `Selectors` class. This inconsistency could lead to bugs if the state structure changes.

**Evidence:**
```python
# Some places use Selectors (correct)
from sleep_scoring_app.ui.store import Selectors
has_dirty = Selectors.is_any_markers_dirty(self.parent.store.state)

# Other places access state directly (less maintainable)
markers_dirty = self.store.state.sleep_markers_dirty or self.store.state.nonwear_markers_dirty
```

**Suggested Fix:**
1. Add more selector functions for common state access patterns
2. Update all state access to use selectors
3. Document preferred access patterns in CLAUDE.md

**Effort:** 1-2 hours

---

### MED-004: Silent Database Query Failures

**Location:** `sleep_scoring_app/ui/main_window.py:1746-1758` and related data loading methods

**Description:** As noted in CLAUDE.md's "Known Issues / Technical Debt" section, database queries can fail silently with empty results. While the issue is documented, it hasn't been fixed.

**Suggested Fix:** Implement the suggested fix from CLAUDE.md:
1. Add WARNING-level logging when queries return 0 rows unexpectedly
2. Show user feedback for data loading failures
3. Add context to log messages about what was requested

**Effort:** 3-4 hours

---

### MED-005: Activity Data Connector Accesses Private Members

**Location:** `sleep_scoring_app/ui/connectors/activity.py:92-93`

**Description:** The ActivityDataConnector directly accesses private members of services:
```python
data_manager = self.main_window.data_service.data_manager
loading_service = data_manager._loading_service  # Private member access
```

**Suggested Fix:**
1. Add public method to `UnifiedDataService` for loading unified activity data
2. Update connector to use public API

**Effort:** 1 hour

---

## Low Priority Issues

### LOW-001: Inconsistent Signal Naming

**Location:** `sleep_scoring_app/ui/analysis_tab.py:80-89`

**Description:** Signal names use mixed conventions:
- `prevDateRequested` (camelCase)
- `activitySourceChanged` (camelCase)

This is consistent with Qt conventions but differs from the snake_case used elsewhere in Python code.

**Suggested Fix:** Document in CLAUDE.md that PyQt signals follow Qt camelCase convention intentionally.

**Effort:** 15 minutes

---

### LOW-002: Magic String in TimeFieldCoordinator

**Location:** `sleep_scoring_app/ui/coordinators/time_field_coordinator.py:40`

**Description:** Uses magic number 50 for timer delay without explanation.

```python
QTimer.singleShot(50, self.parent_coordinator.trigger_update)
```

**Suggested Fix:** Define as constant with comment explaining purpose (likely debounce delay).

**Effort:** 15 minutes

---

### LOW-003: Potential Memory Leak in Popout Windows

**Location:** `sleep_scoring_app/ui/analysis_tab.py:1360-1398`

**Description:** Popout windows are created but may not be properly cleaned up on tab destruction. The `cleanup_tab()` method doesn't explicitly close/delete popout windows.

**Suggested Fix:** Add explicit cleanup of popout windows in `cleanup_tab()` method.

**Effort:** 30 minutes

---

### LOW-004: Unused Protocol Methods

**Location:** `sleep_scoring_app/ui/protocols.py`

**Description:** Some protocol methods may not be used after the Redux refactor:
- `StateManagerProtocol.load_saved_markers()` - Markers are now loaded via store

**Suggested Fix:** Audit protocol methods for usage, remove unused ones.

**Effort:** 1 hour

---

## Dead Code

### DEAD-001: FileNavigationManager.update_navigation_buttons()

**Location:** `sleep_scoring_app/ui/file_navigation.py:133-137`

**Description:** This method duplicates functionality in `NavigationConnector._update_navigation()`. The connector is the authoritative source for button state updates.

**Evidence:** The connector subscribes to store changes and updates buttons automatically. Callers should not need to manually call `update_navigation_buttons()`.

**Suggested Fix:** Remove method after verifying no callers depend on it.

---

### DEAD-002: Obsolete Table Update Flow

**Location:** `sleep_scoring_app/ui/main_window.py:1354-1398` - `update_marker_tables()` and `_on_table_update_timer()`

**Description:** These methods appear to be partially obsolete after the Redux refactor. The `SideTableConnector` now handles table updates in response to store changes.

**Evidence:** The code has complex timer-based update logic that was needed before connectors existed. With `SideTableConnector._update_sleep_tables()` handling updates reactively, this code may be redundant.

**Suggested Fix:**
1. Trace all callers of `update_marker_tables()`
2. Verify `SideTableConnector` covers all use cases
3. Remove if fully redundant

---

## Test Coverage Gaps

### TEST-GAP-001: No Integration Tests for Full Data Flow

**Description:** While unit tests exist for individual connectors (test_store_connectors.py), there are no integration tests that verify the complete data flow from user action to UI update.

**Suggested Test:**
```python
def test_date_navigation_updates_plot():
    """Integration test: date navigation should update plot data."""
    # 1. Set up store with file and dates
    # 2. Dispatch date_navigated action
    # 3. Verify ActivityDataConnector loaded data
    # 4. Verify PlotConnector updated plot widget
    # 5. Verify MarkersConnector loaded markers for new date
```

---

### TEST-GAP-002: Missing Error Path Tests

**Description:** No tests verify that error conditions are handled correctly:
- Empty database results
- Invalid file format
- Network errors (for future web app)

---

### TEST-GAP-003: No Tests for State Persistence

**Description:** The `PersistenceConnector` saves window geometry to QSettings, but there are no tests verifying this works correctly across sessions.

---

## Recommendations

### Immediate Actions (This Sprint)

1. **Fix HIGH-001:** Consolidate file selection handling to eliminate duplicate dispatch
2. **Fix HIGH-002:** Add error notification to ActivityDataConnector
3. **Review DEAD-002:** Verify table update flow is fully handled by connectors

### Short-Term (Next 2-3 Sprints)

4. **Address HIGH-003:** Create TimeFieldConnector for consistent pattern
5. **Fix MED-002:** Remove redundant FileNavigationManager methods
6. **Add TEST-GAP-001:** Create integration test suite

### Long-Term (Backlog)

7. Standardize all state access through Selectors
8. Replace remaining hasattr() patterns with proper type checks
9. Add comprehensive error handling throughout application

---

## Feature Integration Verification

### Verified Working Features

| Feature | Connector | Status |
|---------|-----------|--------|
| Sleep markers (create/edit/drag/delete) | MarkersConnector, PlotConnector | Working |
| Nonwear markers (create/edit/drag/delete) | MarkersConnector, PlotConnector | Working |
| Date navigation (prev/next/dropdown) | NavigationConnector, NavigationGuardConnector | Working |
| View mode switching (24h/48h) | ViewModeConnector | Working |
| File selection and loading | FileListConnector, UIControlsConnector | Working |
| Algorithm display | PlotConnector | Working |
| Auto-save functionality | AutoSaveConnector, MarkersConnector | Working |
| Adjacent day markers | UIControlsConnector | Working |
| Settings persistence | PersistenceConnector, SettingsConnector | Working |

### Features Requiring Manual Verification

| Feature | Notes |
|---------|-------|
| Export functionality | Verify metrics calculation correctness |
| Diary integration | Verify diary-to-marker flow |
| Metrics calculation | Verify WASO, TST, efficiency calculations |

---

## Appendix: Files Examined

- `ui/store.py` - State definition, actions, reducer
- `ui/connectors/*.py` - All 11 connector files
- `ui/main_window.py` - Main window orchestration
- `ui/analysis_tab.py` - Primary UI tab
- `ui/file_navigation.py` - File/date navigation
- `ui/widgets/activity_plot.py` - Plot widget
- `ui/widgets/plot_marker_renderer.py` - Marker rendering
- `ui/protocols.py` - Protocol interfaces
- `services/*.py` - Service layer files (verified headless)
- `tests/unit/ui/test_store_connectors.py` - Connector tests
