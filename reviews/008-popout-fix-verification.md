# Popout Fix Verification Review

## Summary

**Overall Assessment: PASS with one MEDIUM-severity finding.**

The popout fix changes are correct and complete. The immediate `refresh_onset_popout()`/`refresh_offset_popout()` calls after showing popout windows ensure users see data immediately. The removal of the `if full_data:` guard prevents stale data on date switches. The `_app_state` assignment in `PlotOverlayRenderer` is a dead assignment but harmless. One null-safety gap exists in `_plot_nonwear_periods` where `self._timestamps` could theoretically be `None`, though in practice this path is guarded by upstream callers. All StrEnum replacements, hasattr removals, and callback injections are verified correct.

---

## Popout Data Flow Verification

### Scenario A: User clicks popout button for first time -> window opens -> data loads

**Traced path:**
1. User clicks "Pop Out" button -> `self.onset_popout_button.clicked` signal fires (`analysis_tab.py:268`)
2. `_on_onset_popout_clicked()` executes (`analysis_tab.py:1361-1377`)
3. `self.onset_popout_window is None` -> creates `PopOutTableWindow(parent=parent_widget, title=..., table_type="onset")` (`analysis_tab.py:1363-1366`)
4. Right-click handler connected via `customContextMenuRequested` (`analysis_tab.py:1368`)
5. Window shown: `show()`, `raise_()`, `activateWindow()` (`analysis_tab.py:1372-1374`)
6. **Immediate data population**: `self.refresh_onset_popout()` called (`analysis_tab.py:1377`)
7. In `refresh_onset_popout()` (`analysis_tab.py:1398-1415`):
   - Checks `self.onset_popout_window` exists and is visible -> True (just shown)
   - Gets `selected_period` from `self.plot_widget.get_selected_marker_period()` (`analysis_tab.py:1404`)
   - `get_selected_marker_period()` delegates to `marker_renderer.get_selected_marker_period()` (`activity_plot.py:1710-1712`)
   - Calls `self.app_state._get_full_48h_data_for_popout(marker_timestamp=onset_timestamp)` (`analysis_tab.py:1408`)
   - `_get_full_48h_data_for_popout` on `main_window.py:1242-1244` delegates to `table_manager.get_full_48h_data_for_popout(marker_timestamp)` (`marker_table.py:469+`)
   - `update_table_data(full_data)` called unconditionally (`analysis_tab.py:1410`) -- **even if data is empty, stale data is cleared**
   - If data and onset_timestamp present, scrolls to marker row (`analysis_tab.py:1411-1415`)

**Verdict: PASS.** No AttributeError possible. All attributes initialized in `__init__`. Data fetched correctly from table_manager through app_state interface. Empty data handled gracefully by `update_table_data`.

### Scenario B: User switches date -> popout updates with new date's data

**Traced path:**
1. User changes date -> Redux store dispatches `date_selected` action
2. `PopOutConnector._on_state_change()` fires (`connectors/table.py:193-211`)
3. Detects `old_state.current_date_index != new_state.current_date_index` -> `markers_changed = True` (`connectors/table.py:200`)
4. Calls `self._refresh_popouts()` (`connectors/table.py:210-211`)
5. `_refresh_popouts()` calls `tab.refresh_onset_popout()` and `tab.refresh_offset_popout()` (`connectors/table.py:213-220`)
6. In `refresh_onset_popout()`:
   - Checks visibility: if popout closed/hidden, returns early (`analysis_tab.py:1400-1401`)
   - Gets new data via `app_state._get_full_48h_data_for_popout()` (which uses the current 48h data from plot_widget)
   - **Always calls `update_table_data(full_data)`** even if `full_data` is empty/`[]` (`analysis_tab.py:1410`)
   - This correctly clears stale data when navigating to a date before data loads

**Additionally**, the `MarkerTableManager._update_popout_windows()` (`marker_table.py:175-195`) is also called via `update_marker_tables()` when side tables update after data loads, providing a second update path.

**Verdict: PASS.** The removal of the `if full_data:` guard is correct -- it ensures popouts always update to reflect the current state, even clearing to empty on date switch before new data loads. The `PopOutConnector` subscription covers `current_date_index` changes.

### Scenario C: User moves a marker -> popout reflects new marker position

**Traced path:**
1. User drags or nudges a marker -> `sleep_markers_changed` signal emitted -> store updated
2. `PopOutConnector._on_state_change()` fires:
   - `old_state.current_sleep_markers is not new_state.current_sleep_markers` -> True
   - OR `old_state.last_marker_update_time != new_state.last_marker_update_time` -> True
3. `_refresh_popouts()` calls both `refresh_onset_popout()` and `refresh_offset_popout()`
4. Both methods re-fetch full 48h data with updated marker_timestamp
5. `update_table_data()` applies the updated marker highlight
6. Scroll-to-marker positions the new marker row

**Additionally**, `MarkerTableManager._update_popout_windows()` (`marker_table.py:175-195`) is also called from `update_marker_tables()` during marker changes via `SideTableConnector`. It checks `_marker_drag_in_progress` (`marker_table.py:184`) to skip updates during active drag for performance.

**Verdict: PASS.** Dual update paths ensure marker changes propagate to popouts. The throttle in `_update_popout_windows()` prevents excessive updates during drag.

### Scenario D: User right-clicks in popout -> marker moves on the plot

**Traced path:**
1. User right-clicks in popout table -> `customContextMenuRequested` signal fires
2. Lambda calls `_on_popout_table_right_clicked("onset", pos)` (`analysis_tab.py:1368`)
3. `_on_popout_table_right_clicked()` (`analysis_tab.py:1436-1464`):
   - Gets the correct window (`onset_popout_window` or `offset_popout_window`)
   - Gets clicked item via `window.table.itemAt(pos)` -- returns `None` if no item, handled with early return
   - Gets timestamp via `window.get_timestamp_for_row(row)` (`popout_table_window.py:156-159`)
   - `get_timestamp_for_row` reads from `self._table_data[row].get("timestamp")` -- stored during last `update_table_data()` call
   - Calls `self.marker_ops.move_marker_to_timestamp(table_type, timestamp)` (`analysis_tab.py:1463`)
   - This delegates to `main_window.move_marker_to_timestamp()` which moves the marker on the plot
4. After marker moves, scenario C kicks in to refresh the popout with updated marker position

**Verdict: PASS.** The `_table_data` is populated correctly in `update_table_data()` at `popout_table_window.py:136`. The timestamp data is stored with each row in `marker_table.py:457`. The right-click handler has proper null checks at each step.

---

## StrEnum Compatibility

### ArrowColorKey.ONSET / OFFSET

**Writer** (`analysis_dialog_coordinator.py:511-513`):
```python
pw.custom_arrow_colors = {
    ArrowColorKey.ONSET: onset_arrow_color,
    ArrowColorKey.OFFSET: offset_arrow_color,
}
```

**Reader** (`plot_algorithm_manager.py:560`):
```python
custom_arrow_colors = getattr(self.parent, "custom_arrow_colors", {})
onset_arrow_color = custom_arrow_colors.get(ArrowColorKey.ONSET, "#0066CC")
```
And (`plot_algorithm_manager.py:603`):
```python
offset_arrow_color = custom_arrow_colors.get(ArrowColorKey.OFFSET, "#FFA500")
```

**Analysis:** Both writer and reader use `ArrowColorKey.ONSET` and `ArrowColorKey.OFFSET`. Since `ArrowColorKey` extends `StrEnum`, these are string-equivalent values (`"onset"` and `"offset"`). Dict key lookup works correctly.

**Verdict: PASS.**

### DatabaseColumn.VECTOR_MAGNITUDE

**Writer sites:** Used as DataFrame column names during import (`csv_loader.py:444-447`, `gt3x_loader.py:359+`, `gt3x_rs_loader.py:347+`).

**Reader sites:**
- `activity_plot.py:560`: `if activity_column_type == DatabaseColumn.VECTOR_MAGNITUDE` -- compares column type string
- `activity_plot.py:870`: same pattern
- `plot_algorithm_manager.py:252`: `if column_type == DatabaseColumn.VECTOR_MAGNITUDE` -- same comparison
- `plot.py:190`: `column_type = DatabaseColumn.VECTOR_MAGNITUDE` -- sets column type

**Analysis:** `DatabaseColumn.VECTOR_MAGNITUDE` is `"VECTOR_MAGNITUDE"`. The `activity_column_type` attribute on the widget is set from the same enum value in the connector (`plot.py:190`). All comparisons are enum-to-enum or enum-to-string where the string matches.

**Verdict: PASS.**

### ExportUIGroup.NONWEAR_MARKERS

**Writer** (`nonwear_columns.py:21+`): Sets `ui_group=ExportUIGroup.NONWEAR_MARKERS` on column definitions.

**Reader** (`export_dialog.py:166`): `if col.ui_group != ExportUIGroup.NONWEAR_MARKERS`
And (`export_dialog.py:210`): `if col.ui_group == ExportUIGroup.NONWEAR_MARKERS`

**Analysis:** Both sides use `ExportUIGroup.NONWEAR_MARKERS` = `"Nonwear Markers"`. The comparison is enum-to-enum.

**Verdict: PASS.**

### DiaryTableColumn import location

**Import sources:**
- `analysis_tab.py:53`: `from sleep_scoring_app.core.constants import DiaryTableColumn` (via `__init__.py`)
- `diary_integration_coordinator.py`: Uses `DiaryTableColumn` imported from same path
- `diary_table_connector.py`: Uses `DiaryTableColumn` imported from same path

**Analysis:** `DiaryTableColumn` is defined in `core/constants/ui.py:117-141` and exported via `core/constants/__init__.py:88,154`. All importers use `from sleep_scoring_app.core.constants import DiaryTableColumn`.

**Verdict: PASS.**

---

## hasattr Removal Safety

### Remaining hasattr uses in the UI layer (verified as valid):

| File:Line | Pattern | Justification |
|-----------|---------|---------------|
| `analysis_dialog_coordinator.py:543` | `hasattr(pw, "plot_nonwear_periods") and hasattr(pw, "nonwear_regions")` | `pw` comes from `self.services.plot_widget` which could be `None` or a different type via `ServiceContainer` protocol. However, this is a **valid duck-typing check** on an external object from a protocol. |
| `marker_interaction_handler.py:60,103,138,156,208,248,299,316` | `hasattr(line, "period")` | **Documented as correct** in `protocols.py:35-55` -- incomplete markers do NOT have `period` attribute monkey-patched. |
| `marker_drawing_strategy.py:190,198,199` | `hasattr(marker, "label")` | Same pattern -- not all line objects have `label` attribute. |
| `plot_marker_renderer.py:476,496,507,524,525,541,1016,1063,1076` | `hasattr(line, "period")`, `hasattr(line, "marker_type")`, `hasattr(line, "label")` | Same documented pattern for monkey-patched attributes on InfiniteLine objects. |
| `activity_plot.py:311,319,321,323,331` | `hasattr(plot_item, "setUseOpenGL")` etc. | **Valid**: Optional pyqtgraph features that may not exist in all versions. |
| `activity_plot.py:466,475` | `hasattr(line, "deleteLater")`, `hasattr(marker, "deleteLater")` | **Valid**: Duck-typing check on Qt objects being cleaned up. |
| `activity_plot.py:750` | `hasattr(activity_data, "__iter__")` | **Valid**: Duck-typing for iterable check. |
| `main_window.py:93` | `hasattr(main_module, "_global_splash")` | **Valid**: Optional module attribute for splash screen. |
| `main_window.py:351` | `hasattr(d, "strftime")` | **Valid**: Duck-typing for date-like objects. |
| `store.py:569` | `hasattr(d, "isoformat")` | **Valid**: Duck-typing for date serialization. |
| `export_tab.py:170,172` | Justified in comments | **Valid**: Metrics structure may vary by version. |
| `config_dialog.py:609` | `hasattr(config, attr_name)` | **Valid**: Dynamic attribute lookup on configuration object. |
| `seamless_source_switcher.py:159,271` | `hasattr(self.plot_widget, "vb")` | **Valid**: Optional pyqtgraph ViewBox attribute. |
| `table_helpers.py:401` | `hasattr(table_container, "table_widget")` | **Valid**: Container type check. |
| `diary_table_connector.py:206` | `hasattr(self.diary_table_widget, "diary_columns")` | **Valid**: Dynamic attribute set on QWidget in `analysis_tab.py:1107`. |
| `plot_state_serializer.py:143-145,229-230` | Various `hasattr` on pen/marker | **Valid**: Optional attributes on pyqtgraph objects. |
| `plot_algorithm_manager.py:241,260,266,431,432,548,554` | Various `hasattr` on timestamps | **Valid**: Duck-typing for datetime protocol. |

**All remaining `hasattr` uses are justified** under the CLAUDE.md exceptions: optional library features, duck typing for external objects, or documented monkey-patched attributes.

**Verdict: PASS.**

---

## Rename Safety

### `plot_widget.main_window` -> `plot_widget.app_state`

**Search results for `.main_window` in `sleep_scoring_app/ui/widgets/`:** No matches found for the old pattern. The grep confirms that all references within the widgets directory now use `app_state` or the parameter name `main_window` only as a constructor parameter name (not as an attribute access pattern).

**Specific verification:**
- `activity_plot.py:87`: Parameter `main_window: "AppStateInterface"` -- this is the constructor parameter name, stored as `self.app_state = main_window` on line 134.
- `activity_plot.py:127`: `PlotOverlayRenderer(self, main_window)` -- passes the parameter, not accessing an attribute.
- `plot_overlay_renderer.py:47`: Parameter `main_window: AppStateInterface` stored as `self._app_state = main_window` on line 50.

### `plot_widget.parent_window` removal

**Search results for `.parent_window` in `sleep_scoring_app/`:** No matches found anywhere in the codebase.

### Sub-manager verification:
- `PlotAlgorithmManager` (`plot_algorithm_manager.py`): No references to `parent.main_window` or `parent.parent_window`. Uses `self.parent` to access widget data directly.
- `PlotOverlayRenderer` (`plot_overlay_renderer.py`): Uses `self._app_state` (stored from constructor param). No references to `parent.main_window`.
- `PlotMarkerRenderer`: No grep hits for `main_window` or `parent_window`.
- `PlotStateSerializer`: No grep hits for `main_window` or `parent_window`.
- `PlotDataManager`: Not referenced in the files examined (likely doesn't exist as a separate class).

**Verdict: PASS.** No external code references the removed attributes.

---

## Callback Injection

### `get_axis_y_data_for_sadeh`

**Old path:** `self.main_window._get_axis_y_data_for_sadeh()`

**New path:** `self._get_axis_y_data_for_sadeh_cb()` stored from constructor param.

**Injection site** (`analysis_tab.py:160`):
```python
get_axis_y_data_for_sadeh=self.app_state._get_axis_y_data_for_sadeh,
```

Where `self.app_state` is the `AppStateInterface` which is `main_window` (cast in `main_window.py:169`).

**Usage in widget** (`activity_plot.py:1600-1602`):
```python
if self._get_axis_y_data_for_sadeh_cb is not None:
    return self._get_axis_y_data_for_sadeh_cb()
```

**Analysis:** The callback is bound to `main_window._get_axis_y_data_for_sadeh` at AnalysisTab construction time. This is the same method that was previously accessed via `self.main_window._get_axis_y_data_for_sadeh()`. The callback is stored as `self._get_axis_y_data_for_sadeh_cb` and called in the same context.

**Verdict: PASS.**

### `get_selected_file`

**Old path:** `self.parent_window.selected_file`

**New path:** `self._get_selected_file()` stored from constructor param.

**Injection site** (`analysis_tab.py:161`):
```python
get_selected_file=lambda: self.app_state.selected_file,
```

**Usage in widget** (`activity_plot.py:1624-1625`):
```python
if self._get_selected_file is not None:
    selected_file = self._get_selected_file()
```

**Analysis:** The lambda captures `self.app_state.selected_file` which returns `self.store.state.current_file` via the Redux store property on `main_window.py:293-295`. This is equivalent to the old `self.parent_window.selected_file` which accessed the same property.

**Verdict: PASS.**

---

## CLAUDE.md Compliance

### Widgets are DUMB (no direct service calls, no store dispatch)

**`AnalysisTab`**: Emits signals for all user actions (`prevDateRequested`, `nextDateRequested`, `activitySourceChanged`, `viewModeChanged`, etc.). Does NOT dispatch to store directly -- signals are handled by `AnalysisTabConnector`. The popout button handlers (`_on_onset_popout_clicked`, `_on_offset_popout_clicked`) create windows and call `refresh_*_popout()` methods. The refresh methods access `self.app_state._get_full_48h_data_for_popout()` which goes through the protocol interface. The `_on_popout_table_right_clicked` calls `self.marker_ops.move_marker_to_timestamp()` which is the protocol-mandated interface. **Compliant.**

**`ActivityPlotWidget`**: Emits signals (`sleep_markers_changed`, `plot_left_clicked`, etc.) for all user interactions. Uses injected callbacks for algorithm/service access. Does not import or call services directly. **Compliant.**

**`PopOutTableWindow`**: Pure display widget. No store access, no service calls. **Compliant.**

### No hasattr abuse

All remaining `hasattr` uses verified as justified (see section above). No new abusive `hasattr` patterns introduced.

**Compliant.**

### StrEnum for ALL constants

No new hardcoded strings introduced in changed files. All constant strings use StrEnum values:
- `ArrowColorKey.ONSET`/`OFFSET` for arrow color dict keys
- `DatabaseColumn.VECTOR_MAGNITUDE` for column comparisons
- `DiaryTableColumn.*` for diary table column IDs
- `ExportUIGroup.NONWEAR_MARKERS` for export grouping

**Compliant.**

### Type annotations on ALL function signatures

Verified all new/modified functions have type annotations:
- `_on_onset_popout_clicked(self) -> None` (analysis_tab.py:1361)
- `_on_offset_popout_clicked(self) -> None` (analysis_tab.py:1380)
- `refresh_onset_popout(self) -> None` (analysis_tab.py:1398)
- `refresh_offset_popout(self) -> None` (analysis_tab.py:1417)
- `_on_popout_table_right_clicked(self, table_type: str, pos) -> None` (analysis_tab.py:1436) -- Note: `pos` lacks type annotation
- `cleanup_tab(self) -> None` (analysis_tab.py:1466)
- `ActivityPlotWidget.__init__` has full callback type annotations (activity_plot.py:85-99)
- `PlotOverlayRenderer.__init__(self, parent: ActivityPlotWidget, main_window: AppStateInterface) -> None` (plot_overlay_renderer.py:47)

**Minor note:** `pos` parameter in `_on_popout_table_right_clicked` (`analysis_tab.py:1436`) lacks a type annotation. It should be `QPoint` from PyQt6. This is a pre-existing pattern from the lambda connection.

**Mostly compliant** -- one missing type on `pos` parameter.

### Protocols replace hasattr

`AnalysisTabProtocol` (`protocols.py:117-153`) includes:
- `onset_popout_window: Any | None`
- `offset_popout_window: Any | None`
- `refresh_onset_popout(self) -> None`
- `refresh_offset_popout(self) -> None`

`AppStateInterface` (`protocols.py:270-285`) includes:
- `_get_full_48h_data_for_popout(self, marker_timestamp: float | None = None) -> list[dict]`

**Compliant.**

---

## Issues Found

### MEDIUM: Null safety gap in `_plot_nonwear_periods` (plot_overlay_renderer.py:198)

**File:** `D:\Scripts\monorepo\apps\sleep-scoring-demo\sleep_scoring_app\ui\widgets\plot_overlay_renderer.py`
**Line:** 198

```python
def _plot_nonwear_periods(self, sensor_mask, choi_mask, ...):
    n_timestamps = len(self._timestamps)  # Crashes if self._timestamps is None
```

`self._timestamps` is a property that returns `self.parent.timestamps`, which is initialized to `None` at `activity_plot.py:180`. While the caller `plot_nonwear_periods()` (line 128) checks `self.parent.nonwear_data` before calling, it does NOT check `self._timestamps` for `None`. If `nonwear_data` is set but `timestamps` is still `None` (a timing edge case during initialization), this would raise `TypeError: object of type 'NoneType' has no len()`.

**In practice**, this is unlikely because `set_nonwear_data` (line 84) is called only after data is loaded (which sets timestamps), and the upstream methods `update_choi_overlay_only` (line 280) and `update_choi_overlay_async` (line 340) both guard with `if not self._timestamps`. However, `plot_nonwear_periods()` (line 128) which is also called from `analysis_dialog_coordinator.py:544` (color changes) lacks this guard.

**Severity:** MEDIUM. The code path is unlikely but not impossible.

### LOW: Dead assignment `_app_state` in PlotOverlayRenderer (plot_overlay_renderer.py:50)

**File:** `D:\Scripts\monorepo\apps\sleep-scoring-demo\sleep_scoring_app\ui\widgets\plot_overlay_renderer.py`
**Line:** 50

```python
self._app_state = main_window
```

This attribute is assigned but never read anywhere in the file (grep confirms only one reference at line 50). It was renamed from `_main_window` during the refactoring but is effectively dead code. It does not cause any bugs but adds unnecessary memory retention of the `main_window` reference.

**Severity:** LOW. No functional impact.

### LOW: Missing type annotation on `pos` parameter (analysis_tab.py:1436)

**File:** `D:\Scripts\monorepo\apps\sleep-scoring-demo\sleep_scoring_app\ui\analysis_tab.py`
**Line:** 1436

```python
def _on_popout_table_right_clicked(self, table_type: str, pos) -> None:
```

The `pos` parameter should be typed as `QPoint` from `PyQt6.QtCore`. This is a minor CLAUDE.md compliance issue (type annotations on ALL function signatures).

**Severity:** LOW. No functional impact.

### LOW: hasattr on `pw` in analysis_dialog_coordinator.py:543

**File:** `D:\Scripts\monorepo\apps\sleep-scoring-demo\sleep_scoring_app\ui\coordinators\analysis_dialog_coordinator.py`
**Line:** 543

```python
if hasattr(pw, "plot_nonwear_periods") and hasattr(pw, "nonwear_regions"):
    pw.plot_nonwear_periods()
```

`pw` comes from `self.services.plot_widget` which is typed as `Any | None` in `ServiceContainer`. If `pw` is not None, it is always an `ActivityPlotWidget` which always has `plot_nonwear_periods` and `nonwear_regions`. A simple `if pw:` guard would suffice. However, this may be intentional defensiveness since `plot_widget` is a dynamic property (`main_window.py:360-364`).

**Severity:** LOW. Not technically abuse since the object type is not statically guaranteed.

---

## Recommendations

1. **Add a null guard to `plot_nonwear_periods()`** at `plot_overlay_renderer.py:128`:
   ```python
   if not self._timestamps:
       logger.debug("No timestamps available for nonwear visualization")
       return
   ```
   This would make the method defensive against the edge case identified above.

2. **Remove the dead `_app_state` assignment** at `plot_overlay_renderer.py:50` to clean up the dead reference. If `_app_state` is truly not used, the constructor parameter can also be removed (though it would require updating the call site at `activity_plot.py:127`).

3. **Add type annotation** to `pos` parameter at `analysis_tab.py:1436`:
   ```python
   from PyQt6.QtCore import QPoint
   def _on_popout_table_right_clicked(self, table_type: str, pos: QPoint) -> None:
   ```

4. **Consider simplifying** the `hasattr` check at `analysis_dialog_coordinator.py:543` to `if pw:` since the plot_widget property always returns an `ActivityPlotWidget` or `None`.
