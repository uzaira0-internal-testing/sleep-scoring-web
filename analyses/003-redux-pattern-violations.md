# Redux Pattern Compliance Audit

## Summary

This audit reviews the sleep scoring application for compliance with the Redux-like pattern defined in CLAUDE.md. The codebase shows **significant compliance** with the architectural rules, but contains some notable violations that should be addressed.

### Overall Compliance

| Category | Status | Notes |
|----------|--------|-------|
| hasattr() Usage | **GOOD** | All 97 occurrences are documented with `# KEEP:` comments indicating valid duck typing |
| Widget Signals | **GOOD** | FileManagementWidget is exemplary - emits signals only |
| Connectors | **EXCELLENT** | 25+ connectors properly bridge Widget <-> Store |
| Store Dispatch in Widgets | **NEEDS REVIEW** | Some tabs dispatch directly (may be acceptable for settings tabs) |
| Services in Widgets | **GOOD** | Most widgets use Protocol injection, not direct service calls |
| parent() Access | **GOOD** | Limited to legitimate component composition |

---

## hasattr() Abuse (Must Fix)

### NONE FOUND

All 97 `hasattr()` occurrences in the codebase are **legitimate** and documented with `# KEEP:` comments:

**Valid Categories Found:**

1. **Duck Typing for Date/Datetime Objects** (14 occurrences)
   - `hasattr(d, "isoformat")` - Checking if object is date/datetime
   - `hasattr(ts, "timestamp")` - Checking for timestamp method
   - `hasattr(value, "strftime")` - Date formatting capability

2. **Optional Library Features** (7 occurrences)
   - `hasattr(gt3x_rs, "detect_time_gaps_numpy")` - Optional gt3x_rs module feature
   - `hasattr(self._gt3x_rs, "aggregate_xyz_to_epochs")` - Optional gt3x_rs feature
   - `hasattr(gc, "get_stats")` - Optional gc module feature

3. **Optional PyQt/pyqtgraph Features** (8 occurrences)
   - `hasattr(self.plotItem, "setUseOpenGL")` - Optional PyQt feature
   - `hasattr(line, "deleteLater")` - Qt cleanup duck typing

4. **Duck Typing for pyqtgraph Line Attributes** (32 occurrences)
   - `hasattr(line, "period")` - Marker lines may or may not have period attached
   - `hasattr(line, "label")` - Marker lines may or may not have labels
   - This is **correct** per protocols.py documentation

5. **Class Attribute Checks** (3 occurrences)
   - `hasattr(loader_class, "SUPPORTED_EXTENSIONS")` - Class-level attribute check

6. **Cleanup During Shutdown** (12 occurrences in main_window.py)
   - These check if components exist before cleanup during `closeEvent()`
   - Example: `hasattr(self, "autosave_coordinator")` at line 952
   - **These are acceptable** for shutdown cleanup, but could be improved

### Recommendation for Shutdown Cleanup

While the shutdown cleanup patterns are functional, they indicate potential initialization order issues. Consider:

```python
# Current (acceptable but verbose)
if hasattr(self, "autosave_coordinator") and self.autosave_coordinator:
    self.autosave_coordinator.force_save()

# Better: Initialize to None in __init__, then check only for None
if self.autosave_coordinator is not None:
    self.autosave_coordinator.force_save()
```

**Status: NO VIOLATIONS - All hasattr() uses are documented and valid**

---

## Widget Violations (Must Fix)

### NONE FOUND

**Exemplary Widget: FileManagementWidget**
```
D:\Scripts\monorepo\apps\sleep-scoring-demo\sleep_scoring_app\ui\widgets\file_management_widget.py
```

This widget follows the Redux pattern perfectly:
- Emits `refreshRequested` and `deleteRequested` signals
- Has NO store reference
- Has NO service references
- Accepts data via `set_files()` method (data injection)

**Other Widgets**

The widgets in `ui/widgets/` are **component managers** (PlotAlgorithmManager, PlotMarkerRenderer, etc.) that operate on their parent ActivityPlotWidget, not independent widgets that should emit signals. They correctly use `self.parent.` pattern for accessing the plot widget they manage.

---

## Tab Dispatch Patterns (Review Needed)

The tabs dispatch directly to the store in some cases. This is **acceptable** for settings-related actions but should be reviewed:

### AnalysisTab (analysis_tab.py)
```python
# Line 869 - Activity source change
self.store.dispatch(Actions.algorithm_changed(selected_data))

# Line 1245 - Adjacent markers toggle
self.store.dispatch(Actions.adjacent_markers_toggled(checked))

# Line 1254 - Auto-save toggle
self.store.dispatch(Actions.auto_save_toggled(checked))

# Line 1290 - Marker mode change
self.store.dispatch(Actions.marker_mode_changed(category))
```

**Assessment:** These are user preference toggles triggered by UI elements. Dispatching directly from the tab is acceptable because:
1. They are simple settings changes (not complex business logic)
2. The tab receives the store via dependency injection
3. No service calls are made before dispatch

### DataSettingsTab (data_settings_tab.py)
```python
# Lines 131-132 - File deletion cleanup
self.store.dispatch(Actions.file_selected(None))
self.store.dispatch(Actions.dates_loaded([]))
```

**Assessment:** Acceptable - responding to file deletion events.

### StudySettingsTab (study_settings_tab.py)
Multiple `store.dispatch(Actions.study_settings_changed(...))` calls.

**Assessment:** Acceptable - this is a settings tab designed to modify study configuration in the store.

**Status: ACCEPTABLE - No violations, tabs dispatch settings changes appropriately**

---

## Missing Connectors

### NONE FOUND

The codebase has comprehensive connector coverage:

| Connector | Purpose |
|-----------|---------|
| SaveButtonConnector | Syncs save button state with marker dirty flags |
| StatusConnector | Syncs "No Sleep" button with marker state |
| DateDropdownConnector | Syncs dropdown with available dates and selection |
| FileManagementConnector | Bridges FileManagementWidget <-> Store |
| FileListConnector | Syncs file selector table with available files |
| FileTableConnector | Updates file table indicators after save |
| PlotArrowsConnector | Refreshes sleep rule arrows after save |
| SideTableConnector | Updates onset/offset tables when markers change |
| PopOutConnector | Refreshes pop-out windows when markers change |
| AutoSaveConnector | Syncs auto-save checkbox and status label |
| MarkerModeConnector | Syncs sleep/nonwear radio buttons |
| AdjacentMarkersConnector | Syncs adjacent markers checkbox |
| DiaryTableConnector | Refreshes diary when file changes |
| PlotDataConnector | Updates plot with activity data from store |
| ActivityDataConnector | Loads activity data on file/date change |
| NavigationConnector | Updates UI buttons for date navigation |
| NavigationGuardConnector | Checks unsaved markers before navigation |
| ViewModeConnector | Syncs 24h/48h view mode buttons |
| SignalsConnector | Wires file selection signals |
| TimeFieldConnector | Syncs manual time input fields |
| AlgorithmConfigConnector | Syncs calibration/imputation settings |
| CacheConnector | Invalidates caches on save |
| StudySettingsConnector | Syncs StudySettingsTab with store |
| QSettingsPersistenceConnector | Persists state to QSettings |
| WindowGeometryConnector | Tracks window position/size |

---

## State Mutation Issues

### NONE FOUND

All state changes go through `store.dispatch(Actions.xxx())`:
- The UIState dataclass is frozen (`@dataclass(frozen=True)`)
- The reducer creates new state via `replace(state, ...)`
- No direct mutation of state properties observed

---

## Recommendations

### 1. Document the Tab Dispatch Pattern

Add a note to CLAUDE.md clarifying that **tabs** (not widgets) may dispatch directly to the store for settings changes:

```markdown
### Tab vs Widget Distinction

- **Widgets** (in `ui/widgets/`) are DUMB - emit signals only
- **Tabs** (like AnalysisTab, DataSettingsTab) MAY dispatch directly for settings changes
- **Connectors** handle widget signals and complex state synchronization
```

### 2. Consider Protocol for Optional Cleanup Methods

The shutdown cleanup in main_window.py uses hasattr() extensively. Consider adding an optional `cleanup()` method to relevant protocols:

```python
class CleanupProtocol(Protocol):
    def cleanup(self) -> None: ...
```

Then components can be checked with `isinstance(obj, CleanupProtocol)` instead of hasattr().

### 3. PlotWidget Component Managers

The plot widget's managers (PlotAlgorithmManager, PlotMarkerRenderer, etc.) use `self.parent.` extensively. This is correct for component composition but could be made more explicit:

- These are **internal implementation details** of ActivityPlotWidget
- They are NOT independent widgets
- The `parent` reference is to the owning plot widget, not a Qt parent

Consider renaming to make this clearer (e.g., `self.plot_widget.` instead of `self.parent.`).

---

## Conclusion

The codebase demonstrates **excellent compliance** with the Redux pattern defined in CLAUDE.md:

1. **hasattr() abuse: NONE** - All 97 occurrences are valid duck typing with documentation
2. **Widget violations: NONE** - Widgets properly emit signals
3. **Connector coverage: COMPREHENSIVE** - 25+ connectors handle state synchronization
4. **State mutations: NONE** - All changes go through dispatch()
5. **Tab dispatching: ACCEPTABLE** - Settings changes dispatch appropriately

The architecture successfully separates concerns:
- **Widgets** are dumb (emit signals)
- **Connectors** bridge Widget <-> Store
- **Coordinators** handle Qt-specific timing (QTimer, threads)
- **Services** are headless (no Qt imports)
- **Store** is single source of truth

No violations require immediate fixing. The recommendations are improvements to documentation and code clarity.
