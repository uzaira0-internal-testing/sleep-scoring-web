# UI Layer Review - 016

**Date:** 2026-02-25
**Scope:** `sleep_scoring_app/ui/` -- store, connectors, coordinators, widgets, main_window, protocols
**Focus:** Bugs, state management errors, race conditions, stale data, signal/slot misconnections, Redux pattern violations

---

## CRITICAL Issues

### C-1: FILE_SELECTED Reducer Does Not Reset Marker State, Selection, or Flags

**Severity:** CRITICAL (stale markers from previous file displayed on new file)
**File:** `sleep_scoring_app/ui/store.py:540-545`

**Description:** When a new file is selected, the reducer resets `current_date_index` and `available_dates`, but does NOT reset:
- `current_sleep_markers` / `current_nonwear_markers`
- `sleep_markers_dirty` / `nonwear_markers_dirty`
- `selected_period_index` / `selected_nonwear_index`
- `is_no_sleep_marked` / `needs_consensus`
- `last_markers_save_time` / `last_marker_update_time`
- `sadeh_results`
- `activity_timestamps` and related data columns

The marker state from File A is still present in the store when File B is selected. The `MarkerLoadingCoordinator` waits for activity data to change before loading new markers (line 82), but there is a window between FILE_SELECTED and ACTIVITY_DATA_LOADED where stale markers from the old file remain in Redux. Any connector reacting to FILE_SELECTED will see the old markers.

**Evidence:**
```python
# store.py:540-545
return replace(
    state,
    current_file=filename,
    current_date_index=-1,  # Reset date when file changes
    available_dates=(),  # Clear dates - will be loaded separately
)
# Missing: current_sleep_markers=None, current_nonwear_markers=None,
#          sleep_markers_dirty=False, nonwear_markers_dirty=False,
#          selected_period_index=None, selected_nonwear_index=0,
#          is_no_sleep_marked=False, needs_consensus=False,
#          sadeh_results=(), activity_timestamps=(), etc.
```

**Risk:** If marker loading from the DB fails for the new file (exception, network error), the old file's markers remain displayed forever and could be accidentally saved against the new file.

---

### C-2: Double Dispatch of FILE_SELECTED During Session Restore

**Severity:** CRITICAL (redundant state resets and subscriber cascade)
**File:** `sleep_scoring_app/ui/main_window.py:402-403`

**Description:** In `_restore_session()`, `file_selected` is dispatched explicitly on line 402, and then `self.selected_file = last_file_path` on line 403 triggers the `selected_file` setter, which dispatches `file_selected` AGAIN (line 312). The second dispatch extracts the filename from the path, so if the filename matches, the guard `if filename != self.store.state.current_file` prevents it. But if `last_file_path` is a full path and `matching_file.filename` is just the filename, the setter dispatch IS suppressed. However, if they happen to match (e.g., user previously had only a filename stored), there is a double dispatch that triggers all subscribers twice, including clearing dates that were just loaded.

**Evidence:**
```python
# main_window.py:402-403
self.store.dispatch(Actions.file_selected(matching_file.filename))
self.selected_file = last_file_path  # This triggers setter -> second dispatch
```

The `selected_file` setter (line 310-312):
```python
filename = Path(value).name if value else None
if filename != self.store.state.current_file and filename is not None:
    self.store.dispatch(Actions.file_selected(filename))
```

Since line 402 already set `current_file` to `matching_file.filename`, and line 403's setter extracts the same filename, the guard usually prevents the second dispatch. But the setter call is still confusing, error-prone, and serves no purpose since the store already has the file.

---

### C-3: `on_file_selected_from_table` Also Double-Dispatches

**Severity:** HIGH (redundant subscribers fired, marker/date state bounced)
**File:** `sleep_scoring_app/ui/main_window.py:818-821`

**Description:** In `on_file_selected_from_table`, line 818 dispatches `file_selected(filename)`, then line 821 sets `self.selected_file = str(file_info.source_path)`, which triggers the setter to potentially dispatch `file_selected` AGAIN. Since the reducer already set `current_file` to the filename, and the setter extracts the same filename from `source_path`, the guard usually prevents a second dispatch. However, this is a fragile pattern that can break if source_path parsing produces a different filename.

**Evidence:**
```python
# main_window.py:818-821
self.store.dispatch(Actions.file_selected(file_info.filename))
# 2. Update the path property
self.selected_file = str(file_info.source_path) if file_info.source_path else file_info.filename
```

---

## HIGH Issues

### H-1: `_on_file_cleared` Dispatches Two Actions Sequentially -- Second Can Be Skipped on Error

**Severity:** HIGH (partial state reset if first dispatch's subscribers throw)
**File:** `sleep_scoring_app/ui/connectors/settings.py:382-387`

**Description:** `_on_file_cleared` calls `dispatch(file_selected(None))` then immediately calls `dispatch(dates_loaded([]))`. The first dispatch calls subscribers synchronously. If any subscriber throws an exception, it is caught by `_notify_subscribers` (line 1111-1112 in store.py) which logs but continues. So the second dispatch will execute. However, `file_selected(None)` does not clear markers (see C-1), and the `dates_loaded([])` action does not clear markers either. The result is a state where `current_file=None` and `available_dates=()` but markers from the old file remain.

**Evidence:**
```python
def _on_file_cleared(self) -> None:
    self._store.dispatch(Actions.file_selected(None))
    self._store.dispatch(Actions.dates_loaded([]))
    # Missing: markers_cleared(), activity_data_cleared()
```

---

### H-2: `SideEffectConnector.handle_clear_activity_data` Dispatches 5 Actions Sequentially

**Severity:** HIGH (partial state reset if any dispatch fails; excessive subscriber notifications)
**File:** `sleep_scoring_app/ui/connectors/manager.py:105-109`

**Description:** When clearing activity data, 5 sequential dispatches occur. Each dispatch notifies all 30+ subscribers. This is 150+ subscriber callbacks for a single logical operation. Additionally, intermediate states (e.g., file=None but markers still present) are visible to subscribers between dispatches, which can cause incorrect UI updates. This should be a single compound action in the reducer.

**Evidence:**
```python
self.store.dispatch_safe(Actions.file_selected(None))
self.store.dispatch_safe(Actions.dates_loaded([]))
self.store.dispatch_safe(Actions.activity_data_cleared())
self.store.dispatch_safe(Actions.markers_cleared())
self.store.dispatch_safe(Actions.files_loaded([]))
```

---

### H-3: `SeamlessSourceSwitcher` Restores Markers Directly to Widget, Bypassing Redux Store

**Severity:** HIGH (widget state diverges from Redux store)
**File:** `sleep_scoring_app/ui/coordinators/seamless_source_switcher.py:271-281`

**Description:** In `_restore_complete_plot_state`, markers are deserialized and loaded directly into the plot widget via `pw.load_daily_sleep_markers(restored_markers)` (line 281). This bypasses the Redux store entirely. The Redux store still holds the OLD marker objects (or references), while the widget displays newly deserialized copies. Any subsequent store-driven update will overwrite the widget's state with the store's version, potentially discarding the restored state.

**Evidence:**
```python
# Line 167-168: Capture from Redux store
daily_markers = self.store.state.current_sleep_markers

# Line 275-281: Restore directly to widget, NOT to store
restored_markers = DailySleepMarkers(
    period_1=self._deserialize_sleep_period(daily_markers_data.get("period_1")),
    ...
)
self.plot_widget.load_daily_sleep_markers(restored_markers)
# Missing: self.store.dispatch(Actions.markers_loaded(sleep=restored_markers, ...))
```

---

### H-4: `AutosaveCoordinator._execute_save` Records Wrong Date in `markers_saved()` Metadata

**Severity:** HIGH (incorrect `last_saved_date` in Redux state after debounced save)
**File:** `sleep_scoring_app/ui/coordinators/autosave_coordinator.py:244` and `sleep_scoring_app/ui/store.py:783-786`

**Description:** The autosave coordinator debounces saves by 500ms. When `_execute_save` fires, it dispatches `markers_saved()`. The reducer for `MARKERS_SAVED` computes `last_saved_date` from `state.current_date_index` and `state.available_dates` at DISPATCH TIME. If the user navigated to a different date during the 500ms debounce window, the metadata records the WRONG date. The actual DB save (via callback) used the correct date at the time the dirty flag was set, but the Redux metadata is out of sync.

**Evidence:**
```python
# store.py:783-786 (MARKERS_SAVED reducer)
last_saved_file=state.current_file,
last_saved_date=state.available_dates[state.current_date_index]
    if 0 <= state.current_date_index < len(state.available_dates)
    else None,
```

This metadata is used by `FileTableConnector` and `CacheConnector` to update UI indicators. A wrong `last_saved_date` could cause the file completion indicator to update for the wrong date.

---

### H-5: `NavigationConnector` Clears Markers From Plot Directly, Racing With `MarkersConnector`

**Severity:** HIGH (visual flicker, both connectors manipulate widget state)
**File:** `sleep_scoring_app/ui/connectors/navigation.py:257-262`

**Description:** When the date changes, `NavigationConnector._update_navigation` calls `pw.clear_sleep_markers()`, `pw.clear_nonwear_markers()`, and `pw.clear_sleep_onset_offset_markers()` directly on the widget. Meanwhile, `MarkersConnector` (registered at index 5 in the connector list, before NavigationConnector at index ~21) also subscribes to the same state change and processes markers. Since subscribers run in registration order, `MarkersConnector` fires FIRST and may see stale markers from the previous date, then `NavigationConnector` fires and clears them.

Both connectors directly manipulate the same widget state (plot markers), violating the principle that each piece of widget state should have a single authority. The marker clearing should be done exclusively by `MarkersConnector` when it detects the date change.

**Evidence:**
```python
# navigation.py:257-262 (NavigationConnector)
if state.current_date_index != -1:
    pw = self.main_window.plot_widget
    if pw:
        pw.clear_sleep_markers()
        pw.clear_nonwear_markers()
        pw.clear_sleep_onset_offset_markers()
```

---

### H-6: `DateDropdownConnector._update_visuals` Queries Database on Every `sleep_markers_dirty` Change

**Severity:** HIGH (database query on every marker drag pixel)
**File:** `sleep_scoring_app/ui/connectors/navigation.py:53-58, 136`

**Description:** The `should_update_colors` condition includes `old_state.sleep_markers_dirty != new_state.sleep_markers_dirty`. During marker dragging, `sleep_markers_dirty` toggles from False to True on the first drag pixel, but once True it stays True until save. So this only fires once per drag session. However, it also fires on `last_markers_save_time` change (every autosave) and `is_no_sleep_marked` change, each triggering a full `load_sleep_metrics` database query inside a subscriber callback.

The database query itself (line 136) loads ALL metrics for the current file (not just current date), which could be expensive for files with many dates.

**Evidence:**
```python
should_update_colors = (
    old_state.last_markers_save_time != new_state.last_markers_save_time
    or old_state.is_no_sleep_marked != new_state.is_no_sleep_marked
    or old_state.current_date_index != new_state.current_date_index
    or old_state.sleep_markers_dirty != new_state.sleep_markers_dirty
)
# ...
metrics_list = self.main_window.db_manager.load_sleep_metrics(filename=filename)
```

---

### H-7: `PopOutConnector` Refreshes On `last_marker_update_time` (Every Marker Drag)

**Severity:** HIGH (performance -- pop-out window data fetched on every drag)
**File:** `sleep_scoring_app/ui/connectors/table.py:217-226`

**Description:** `PopOutConnector._on_state_change` checks `last_marker_update_time` which changes on every marker drag. This triggers `_refresh_popouts()` which calls `tab.refresh_onset_popout()` and `tab.refresh_offset_popout()`, potentially involving 48h data fetches and table rebuilds on every drag pixel.

**Evidence:**
```python
markers_changed = (
    ...
    or old_state.last_marker_update_time != new_state.last_marker_update_time  # every drag
    ...
)
if markers_changed or algorithm_changed:
    self._refresh_popouts()
```

---

### H-8: `_check_unsaved_markers_before_navigation` Shows Modal Dialog During Event Processing

**Severity:** HIGH (nested event loop can process deferred dispatches)
**File:** `sleep_scoring_app/ui/main_window.py:920-939`

**Description:** This method shows QMessageBox dialogs (line 939: `msg.exec()`) which enter a nested event loop. During this nested loop, pending QTimer callbacks can fire, including:
- `AutosaveCoordinator._execute_save` (500ms debounce timer)
- `dispatch_async` deferred dispatches (QTimer.singleShot(0))
- `MarkerLoadingCoordinator._load_markers` (QTimer.singleShot(0))

These callbacks can change Redux state while the dialog is open, invalidating assumptions made before the dialog was shown. For example, the autosave timer could save markers and clear dirty flags while the "unsaved markers" dialog is still visible.

---

### H-9: `WindowGeometryConnector` Polls Every 500ms via QTimer

**Severity:** HIGH (unnecessary polling dispatches actions to 30+ subscribers)
**File:** `sleep_scoring_app/ui/connectors/persistence.py:103-106`

**Description:** The connector uses a 500ms QTimer to poll window geometry, dispatching `window_geometry_changed` and `window_maximized_changed` actions whenever geometry differs. During window resizing, this fires multiple dispatches per second, each notifying all 30+ subscribers. The `AutosaveCoordinator` detects these as config changes and restarts its debounce timer on every poll cycle.

Qt provides `moveEvent()` and `resizeEvent()` virtual methods on QMainWindow that should be used instead of polling.

**Evidence:**
```python
self._timer = QTimer()
self._timer.timeout.connect(self._check_geometry)
self._timer.start(500)  # Polls every 500ms, dispatches to 30+ subscribers
```

---

## Summary

| ID | Severity | Component | Issue |
|----|----------|-----------|-------|
| C-1 | CRITICAL | store.py reducer | FILE_SELECTED does not reset markers, selection, flags |
| C-2 | CRITICAL | main_window.py | Double dispatch of FILE_SELECTED during session restore |
| C-3 | HIGH | main_window.py | Double dispatch of FILE_SELECTED in on_file_selected_from_table |
| H-1 | HIGH | settings.py connector | _on_file_cleared leaves markers in state |
| H-2 | HIGH | manager.py connector | 5 sequential dispatches for clear_activity_data |
| H-3 | HIGH | seamless_source_switcher.py | Restores markers to widget bypassing Redux store |
| H-4 | HIGH | autosave_coordinator.py | markers_saved() metadata uses current state, not save-time state |
| H-5 | HIGH | navigation.py connector | Two connectors both clear/set plot markers (dual authority) |
| H-6 | HIGH | navigation.py connector | Database query in subscriber on dirty/save changes |
| H-7 | HIGH | table.py connector | Pop-out windows refreshed on every marker drag |
| H-8 | HIGH | main_window.py | Modal dialog during state transition allows deferred dispatches |
| H-9 | HIGH | persistence.py connector | 500ms geometry polling instead of event-based |

### Positive Observations

1. **Widgets do not dispatch to the store** -- confirmed via grep. The widget/connector/store boundary is cleanly maintained.
2. **`blockSignals(True/False)` pattern** is used consistently in connectors to prevent signal loops when updating widgets from store state.
3. **`dispatch_safe`/`dispatch_async`** are used appropriately in most subscriber callbacks to avoid dispatch-in-dispatch errors.
4. **Deep-copy of markers** in `MarkersConnector._copy_and_filter_sleep_markers` correctly prevents Redux state mutation when filtering out-of-bounds periods.
5. **Proper disconnect/cleanup** is implemented in most connectors with `disconnect()` methods.
6. **hasattr usage in widgets** is limited to legitimate cases: optional library features (pyqtgraph API detection), monkey-patched marker line attributes (documented in MarkerLineProtocol), and duck-typing for timestamp objects.
