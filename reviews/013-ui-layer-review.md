# UI Layer Review - 013

**Date:** 2026-02-25
**Reviewer:** Claude Opus 4.6
**Scope:** `sleep_scoring_app/ui/` -- store, connectors, coordinators, widgets, main_window, protocols, window_state

## Summary

Reviewed all `.py` files in the UI layer (~40 files). Found **1 CRITICAL** and **3 HIGH** severity issues. The Redux store pattern and connector/coordinator architecture are generally well-implemented, with proper deep-copy semantics, re-entrancy guards, and `dispatch_safe`/`dispatch_async` usage.

---

## CRITICAL Issues

### C-1: Non-existent Action crashes fallback reload path in SeamlessSourceSwitcher

**File:Line:** `sleep_scoring_app/ui/coordinators/seamless_source_switcher.py:299`

**Description:** `_fallback_to_full_reload()` calls `Actions.preferred_activity_column_changed(selected_column)`, but this static method does **not exist** on the `Actions` class. The correct method is `Actions.preferred_display_column_changed(selected_column)` (defined at `store.py:414`). This raises `AttributeError` when the fallback path is triggered, crashing the activity source switch and leaving the plot in a potentially inconsistent state.

**Evidence:**
```python
# seamless_source_switcher.py:299
self.store.dispatch_safe(Actions.preferred_activity_column_changed(selected_column))
```

```python
# store.py:414 -- The actual method name
@staticmethod
def preferred_display_column_changed(column: str) -> Action:
```

Grep confirms only one reference to `preferred_activity_column_changed` in the entire codebase -- at this line. The action factory method was likely renamed without updating this call site.

**Impact:** When the seamless source switch fails (the primary code path catches exceptions and falls back here), the fallback itself crashes. The user would see the activity data source switch fail silently (the exception is caught at line 302), and the plot remains stuck on the old data source with no user feedback about why.

**Fix:** Replace `Actions.preferred_activity_column_changed` with `Actions.preferred_display_column_changed`.

---

## HIGH Issues

### H-1: MARKERS_SAVED action unconditionally clears is_no_sleep_marked, causing data loss

**File:Line:** `sleep_scoring_app/ui/store.py:788`

**Description:** The `MARKERS_SAVED` reducer case unconditionally sets `is_no_sleep_marked=False`. This flag records that the user explicitly marked a date as having "no sleep period". When nonwear-only autosave triggers, it dispatches `markers_saved()` (via `autosave_coordinator.py:244`), which clears the "no sleep" flag even though the user never changed any sleep markers.

**Evidence:**
```python
# store.py:777-789
case ActionType.MARKERS_SAVED:
    return replace(
        state,
        sleep_markers_dirty=False,
        nonwear_markers_dirty=False,
        last_markers_save_time=time.time(),
        last_saved_file=state.current_file,
        last_saved_date=state.available_dates[state.current_date_index]
        if 0 <= state.current_date_index < len(state.available_dates)
        else None,
        # Clear "no sleep" flag when saving markers - saving markers means there IS sleep
        is_no_sleep_marked=False,  # <-- BUG: cleared even on nonwear-only save
    )
```

```python
# autosave_coordinator.py:240-244
# Dispatch markers_saved ONCE after both saves complete
if marker_save_attempted:
    from sleep_scoring_app.ui.store import Actions
    self.store.dispatch(Actions.markers_saved())
```

**Reproduction scenario:**
1. User marks a date as "no sleep" (`is_no_sleep_marked=True`)
2. User modifies nonwear markers on that same date
3. Autosave fires after 500ms debounce, saves only nonwear markers
4. `markers_saved()` is dispatched
5. `is_no_sleep_marked` is silently reset to `False`
6. The "no sleep" record for the date is lost

**Fix:** Either:
- (a) Only clear `is_no_sleep_marked` when sleep markers are being saved (not nonwear-only), or
- (b) Split `MARKERS_SAVED` into `SLEEP_MARKERS_SAVED` and `NONWEAR_MARKERS_SAVED` actions, and only clear the flag in the sleep variant, or
- (c) Preserve the current `is_no_sleep_marked` value in the reducer: `is_no_sleep_marked=state.is_no_sleep_marked if not state.sleep_markers_dirty else False`

---

### H-2: WindowStateManager accesses plot_widget via ServiceContainer protocol which does not define it

**File:Lines:** `sleep_scoring_app/ui/window_state.py:334, 380, 726`

**Description:** `WindowStateManager` receives `services: ServiceContainer` in its constructor and accesses `self.services.plot_widget` in three methods. However, the `ServiceContainer` protocol (in `protocols.py:210-224`) does **not** define a `plot_widget` attribute. This is a Protocol contract violation that breaks type safety and static analysis. At runtime it works because the actual object is the `MainWindow` which does have `plot_widget`, but this masks a real architectural issue.

**Evidence:**
```python
# window_state.py:334
pw = self.services.plot_widget  # ServiceContainer has no plot_widget

# protocols.py:210-224 -- ServiceContainer definition
class ServiceContainer(Protocol):
    """Protocol for objects that provide core application services."""
    data_service: UnifiedDataService
    config_manager: ConfigManager
    db_manager: DatabaseManager
    marker_service: Any
    store: Any
    import_service: Any
    export_manager: Any | None
    autosave_coordinator: Any | None
    compatibility_helper: Any | None
    table_manager: Any | None
    diary_coordinator: Any | None
    # NOTE: plot_widget is NOT listed here
```

Three affected methods:
- `clear_current_markers()` (line 334)
- `mark_no_sleep_period()` (line 380)
- `clear_all_markers()` (line 726)

**Impact:** Any type checker (basedpyright, mypy) will flag these as errors. More importantly, if the `services` object is ever replaced with a proper service container that isn't the MainWindow, these calls will crash with `AttributeError`.

**Fix:** Either add `plot_widget: PlotWidgetProtocol` to the `ServiceContainer` protocol, or refactor these methods to access the plot widget through `self.main_window.plot_widget` (which is already available via `MainWindowProtocol`).

---

### H-3: Duplicate no_sleep_btn manipulation between WindowStateManager and StatusConnector

**File:Lines:** `sleep_scoring_app/ui/window_state.py:652-654` and `sleep_scoring_app/ui/connectors/save_status.py:110-135`

**Description:** Two independent code paths manipulate the same `no_sleep_btn` widget:

1. **StatusConnector** (`save_status.py:110-135`): Subscribes to Redux store state changes and correctly handles all 3 states (has markers, no_sleep_marked, default).
2. **WindowStateManager** (`window_state.py:652-654`): Called via `handle_sleep_markers_changed()` and directly sets button text/style when marker count >= 2.

These two paths can race or produce conflicting results. The `StatusConnector` is the proper Redux-pattern implementation (reacts to state). The `WindowStateManager` code is a legacy bypass that directly manipulates the widget, which can overwrite the connector's state.

**Evidence:**
```python
# window_state.py:650-654
marker_count = daily_sleep_markers.get_marker_count() if daily_sleep_markers else 0
if marker_count >= 2:  # We have complete markers
    self.main_window.no_sleep_btn.setText(ButtonText.MARK_NO_SLEEP)
    self.main_window.no_sleep_btn.setStyleSheet(ButtonStyle.MARK_NO_SLEEP)
```

```python
# save_status.py:120-135 (StatusConnector._update_ui)
if state.current_sleep_markers and state.current_sleep_markers.get_marker_count() >= 2:
    btn.setText(ButtonText.MARK_NO_SLEEP)
    btn.setStyleSheet(ButtonStyle.MARK_NO_SLEEP)
elif state.is_no_sleep_marked:
    btn.setText(ButtonText.NO_SLEEP_MARKED)
    btn.setStyleSheet(ButtonStyle.NO_SLEEP_MARKED)
else:
    btn.setText(ButtonText.MARK_NO_SLEEP)
    btn.setStyleSheet(ButtonStyle.MARK_NO_SLEEP)
```

**Impact:** When `handle_sleep_markers_changed` fires, it sets the button to "MARK_NO_SLEEP" for any date with >= 2 markers, regardless of whether `is_no_sleep_marked` is true. The `StatusConnector` would then also fire (because Redux state changed), potentially resetting the button again. Currently both set the same value for the "has markers" case, so no visible desync occurs. But if the `StatusConnector` logic is updated in the future without removing the `WindowStateManager` code, they could diverge.

**Fix:** Remove the `no_sleep_btn` manipulation from `WindowStateManager.handle_sleep_markers_changed()` (lines 650-654). The `StatusConnector` already handles this correctly through the Redux pattern.

---

## Verification Checklist

- [x] Read CLAUDE.md and understand the Redux pattern and layer rules
- [x] Checked every .py file in `ui/store.py`
- [x] Checked every .py file in `ui/connectors/` (12 files)
- [x] Checked every .py file in `ui/coordinators/` (9 files)
- [x] Checked every .py file in `ui/widgets/` (17 files)
- [x] Checked `ui/main_window.py`
- [x] Checked `ui/protocols.py`
- [x] Checked `ui/window_state.py`
- [x] Each reported issue has a specific file:line reference
- [x] Each issue includes the actual code snippet
- [x] Verified issues are real bugs, not intentional design
- [x] Verified issues are not documented as known in CLAUDE.md
- [x] Zero false positives (initial "double dispatch in _restore_session" candidate was verified to be guarded by the setter check at line 311)

## Files Reviewed

**Store:** `store.py`
**Connectors:** `manager.py`, `plot.py`, `marker.py`, `navigation.py`, `activity.py`, `file.py`, `ui_controls.py`, `settings.py`, `table.py`, `persistence.py`, `save_status.py`, `error.py`
**Coordinators:** `autosave_coordinator.py`, `marker_loading_coordinator.py`, `ui_state_coordinator.py`, `seamless_source_switcher.py`, `import_ui_coordinator.py`, `time_field_coordinator.py`, `diary_integration_coordinator.py`, `diary_table_connector.py`, `analysis_dialog_coordinator.py`
**Widgets:** `activity_plot.py`, `marker_interaction_handler.py`, `plot_marker_renderer.py`, `plot_overlay_renderer.py`, `plot_algorithm_manager.py`, `marker_drawing_strategy.py`, `marker_editor.py`, `plot_metrics_banner.py`, `plot_state_manager.py`, `plot_data_manager.py`, `plot_state_serializer.py`, `file_management_widget.py`, `file_selection_table.py`, `popout_table_window.py`, `drag_drop_list.py`, `no_scroll_widgets.py`, `__init__.py`
**Other:** `main_window.py`, `protocols.py`, `window_state.py`
