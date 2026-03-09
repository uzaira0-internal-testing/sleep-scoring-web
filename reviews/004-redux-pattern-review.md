# Redux Pattern & Widget Architecture Review

## Summary

The application demonstrates **strong overall compliance** with its Redux store pattern. The core infrastructure is well-built: the store (`ui/store.py`) is a clean, immutable-state implementation with frozen dataclasses, a pure reducer function, subscriber notification, middleware support, and comprehensive Action creators. The connector layer is extensive (30+ connectors) and follows the subscribe/dispatch pattern correctly.

However, there are **notable architectural violations** at the "seam" between the widget layer and the store pattern. The primary issues are:

1. **Tab widgets (AnalysisTab, StudySettingsTab, DataSettingsTab)** act as hybrid Widget/Connectors -- they hold store references, read state directly, and in StudySettingsTab's case, dispatch actions directly. This is the largest category of violations.
2. **PlotOverlayRenderer** (a widget helper) reads store state directly via properties.
3. **AnalysisDialogManager** (a widget helper) holds store and services references.
4. **FileNavigationManager** dispatches to store and reads state directly -- it functions more as a coordinator/connector than a dumb widget helper.
5. **MainWindow** itself dispatches extensively (expected as the root, but some dispatch could be moved to connectors).

The widget layer for pure UI components (ActivityPlotWidget, FileSelectionTable, FileManagementWidget, marker widgets) is **clean and compliant** -- they use pyqtSignal correctly and do not reference the store.

---

## Store Audit

### Available Actions (from `ui/store.py`)

The store defines 32 ActionTypes organized into these categories:

| Category | Actions |
|----------|---------|
| Initialization | `STATE_INITIALIZED` |
| File/Date Navigation | `FILE_SELECTED`, `FILES_LOADED`, `DATE_SELECTED`, `DATES_LOADED`, `DATE_NAVIGATED` |
| Activity Data | `ACTIVITY_DATA_LOADED`, `SADEH_RESULTS_COMPUTED`, `ACTIVITY_DATA_CLEARED` |
| Algorithm State | `ALGORITHM_CHANGED` |
| Application Mode | `VIEW_MODE_CHANGED`, `DATABASE_MODE_TOGGLED`, `REFRESH_FILES_REQUESTED`, `DELETE_FILES_REQUESTED`, `CLEAR_ACTIVITY_DATA_REQUESTED`, `PENDING_REQUEST_CLEARED`, `AUTO_SAVE_TOGGLED`, `MARKER_MODE_CHANGED`, `ADJACENT_MARKERS_TOGGLED`, `CALIBRATION_TOGGLED`, `IMPUTATION_TOGGLED`, `PREFERRED_DISPLAY_COLUMN_CHANGED` |
| Markers | `SLEEP_MARKERS_CHANGED`, `NONWEAR_MARKERS_CHANGED`, `MARKERS_SAVED`, `MARKERS_LOADED`, `MARKERS_CLEARED`, `SELECTED_PERIOD_CHANGED`, `SELECTED_NONWEAR_CHANGED` |
| Window/UI | `WINDOW_GEOMETRY_CHANGED`, `WINDOW_MAXIMIZED_CHANGED`, `UI_CONTROLS_ENABLED_CHANGED` |
| Settings | `STUDY_SETTINGS_CHANGED`, `STATE_LOADED_FROM_SETTINGS` |
| Error | `ERROR_OCCURRED`, `ERROR_CLEARED` |
| Consensus | `CONSENSUS_FLAG_TOGGLED`, `CONSENSUS_FLAG_LOADED` |
| State Management | `RESET_STATE` |

### UIState Fields (55 fields total)

The state is a frozen dataclass with comprehensive coverage of:
- File/date selection (4 fields)
- Activity data storage (7 fields including timestamps, axis data, sadeh results)
- Algorithm and view mode settings (12 fields)
- Marker state (8 fields)
- Window geometry (5 fields)
- Study settings (14 fields)
- UI control state (1 field)
- Metadata and error state (4 fields)

### Direct State Mutations

**RESULT: NO VIOLATIONS FOUND.**

No instances of `store.state.X = Y` were found anywhere in the codebase. The `UIState` dataclass is correctly `frozen=True`, which prevents direct attribute assignment. All state changes go through `store.dispatch()` -> `ui_reducer()` -> `replace()`.

### Shadow State

**ActivityDataConnector** (`ui/connectors/activity.py:35-36`) maintains:
```python
self._last_date_str: str | None = None
self._last_file: str | None = None
```
This is **acceptable** -- it is a deduplication cache to avoid redundant data loads. The connector uses it to compare with incoming state and skip unnecessary reloads. The canonical data lives in the store.

**NavigationConnector** (`ui/connectors/navigation.py:199`) maintains:
```python
self._last_date_str: str | None = None
```
Same pattern -- acceptable deduplication cache.

**MarkerLoadingCoordinator** (`ui/coordinators/marker_loading_coordinator.py:52-54`) maintains:
```python
self._last_file: str | None = None
self._last_date_str: str | None = None
self._pending_load = False
```
Acceptable for the same reason -- prevents duplicate DB loads.

**ActivityPlotWidget** (`ui/widgets/activity_plot.py:170`) maintains:
```python
self._cached_48h_vm_data = None
```
This is a **rendering-level cache** for pyqtgraph data arrays. Acceptable for a rendering widget. The canonical data is in the store.

---

## Widget Compliance

### Fully Compliant Widgets (PASS)

These widgets correctly emit signals only, do not import the store, do not call services, and do not access parents:

| Widget | File | Status |
|--------|------|--------|
| `ActivityPlotWidget` | `ui/widgets/activity_plot.py` | PASS -- Emits 8 pyqtSignal types, no store import, no dispatch |
| `FileSelectionTable` | `ui/widgets/file_selection_table.py` | PASS -- Emits `fileSelected` signal only |
| `FileManagementWidget` | `ui/widgets/file_management_widget.py` | PASS -- Emits `refreshRequested` and `deleteRequested` signals |
| `DragDropListWidget` | `ui/widgets/drag_drop_list.py` | PASS -- Emits `items_changed` signal |
| `MarkerEditor` | `ui/widgets/marker_editor.py` | PASS -- No store, no service access |
| `PlotMarkerRenderer` | `ui/widgets/plot_marker_renderer.py` | PASS -- No store, no service access |
| `PlotDataManager` | `ui/widgets/plot_data_manager.py` | PASS -- No store, no service access |
| `PlotAlgorithmManager` | `ui/widgets/plot_algorithm_manager.py` | PASS -- No store, no service access |
| `PlotStateSerializer` | `ui/widgets/plot_state_serializer.py` | PASS (minor hasattr noted below) |
| `MarkerInteractionHandler` | `ui/widgets/marker_interaction_handler.py` | PASS |
| `PopOutTableWindow` | `ui/widgets/popout_table_window.py` | PASS |
| `NoScrollComboBox`, `NoScrollSpinBox` | `ui/widgets/no_scroll_widgets.py` | PASS |
| `PlotStateManager` | `ui/widgets/plot_state_manager.py` | PASS |
| `MarkerDrawingStrategy` | `ui/widgets/marker_drawing_strategy.py` | PASS |

### Non-Compliant Widgets

#### V-W01: `PlotOverlayRenderer` reads store state directly
**File:** `ui/widgets/plot_overlay_renderer.py:56-78`
**Violation:** Widget helper reads `store.state` via property accessors.
```python
@property
def store(self) -> UIStore:
    return self._main_window.store

@property
def _timestamps(self) -> tuple:
    return self.store.state.activity_timestamps  # Line 63

@property
def _sadeh_results(self) -> tuple:
    return self.store.state.sadeh_results  # Line 68

@property
def _axis_y_data(self) -> tuple:
    return self.store.state.axis_y_data  # Line 73

@property
def _current_filename(self) -> str | None:
    return self.store.state.current_file  # Line 78
```
**Severity:** MEDIUM. The renderer reads state but does not dispatch or subscribe. It accesses state passively for rendering purposes, which is a pragmatic pattern. However, ideally data should be passed to it by its parent PlotDataConnector.
**Suggested fix:** Pass activity data as method parameters from the connector instead of having the renderer reach into the store.

#### V-W02: `AnalysisDialogManager` holds store and services references
**File:** `ui/widgets/analysis_dialogs.py:70-74`
**Violation:** Widget helper holds direct references to `store`, `services`, `marker_ops`, and `app_state`.
```python
self.store = store        # Line 70
self.marker_ops = marker_ops
self.app_state = app_state
self.services = services  # Line 74
```
At line 564-565, it writes to `services.data_service`:
```python
if self.services.data_service:
    self.services.data_service.custom_dropdown_colors = {...}
```
**Severity:** MEDIUM. The dialog manager is constructed with injected dependencies (not reaching through parent), which is better than using `self.parent()`. But it holds service references that a dumb widget should not have.
**Suggested fix:** Extract service calls to a connector or callback. The color settings could dispatch an action rather than mutating a service attribute directly.

### Tab Widgets (Hybrid Widget/Connectors)

The tab widgets operate as **hybrid components** -- they are both presentation widgets AND they interact with the store. This is the most significant architectural tension in the codebase.

#### V-W03: `AnalysisTab` reads store state directly
**File:** `ui/analysis_tab.py`
**Violations:**
- Line 948: `self.store.state.available_dates`
- Line 948: `self.store.state.current_date_index`
- Line 1237: `self.store.state.current_date_index`
- Line 1251: `self.store.state.view_mode_hours`

These are **read-only guard checks** to prevent redundant signal emissions (e.g., checking if `hours == self.store.state.view_mode_hours` before emitting `viewModeChanged`). The tab correctly emits signals rather than dispatching. This is a **minor violation** -- the guard reads are pragmatic anti-recursion measures.

The tab also directly calls services via protocols:
- Line 808: `self.marker_ops.save_current_markers` (connected to button click)
- Line 816: `self.marker_ops.mark_no_sleep_period`
- Line 823: `self.marker_ops.clear_current_markers`
- Line 898: `self.services.config_manager.config`
- Line 900: `self.app_state.set_activity_data_preferences(...)`
- Line 976-977: `self.services.data_service.get_available_activity_columns(filename)`

**Severity:** MEDIUM. The tab uses protocol-based dependency injection (good), but it directly calls services and reads state rather than going through connectors. Some of these (like button click -> marker_ops) are acceptable bridge patterns.

#### V-W04: `StudySettingsTab` dispatches to store directly (MAJOR)
**File:** `ui/study_settings_tab.py`
**Violations:** ~20 direct `store.dispatch()` calls throughout the file.
Examples:
- Line 359: `self.store.dispatch(Actions.study_settings_changed({"nonwear_algorithm_id": actual_str}))`
- Line 820: `self.store.dispatch(Actions.study_settings_changed({"study_default_group": ""}))`
- Line 905: `self.store.dispatch(Actions.study_settings_changed({"study_default_group": text}))`
- Lines 920-982: Multiple dispatch calls for various settings changes
- Lines 1404-1514: Dispatch calls for paradigm, algorithm, nonwear changes

Also reads state directly:
- Line 248: `self._load_settings_from_state(self.store.state)`
- Line 816: `self.store.state.study_default_group`
- Line 878: `self.store.state.study_default_timepoint`
- Line 1358: `self.store.state.data_paradigm`

**Severity:** HIGH. This is the most significant violation in the codebase. The tab acts as its own connector -- it both subscribes to state (via `_load_settings_from_state`) and dispatches actions. Per CLAUDE.md, widgets should only emit signals, and connectors should handle dispatch.
**Suggested fix:** Extract all dispatch calls to a dedicated `StudySettingsDispatchConnector` that connects to signals from the tab. The tab should emit signals like `settingChanged(field_name, value)` and let the connector build and dispatch the appropriate actions.

#### V-W05: `DataSettingsTab` dispatches to store directly
**File:** `ui/data_settings_tab.py`
**Violations:**
- Line 140: `self.store.dispatch(Actions.file_selected(None))`
- Line 141: `self.store.dispatch(Actions.dates_loaded([]))`
- Line 1290: `self.store.dispatch(Actions.clear_activity_data_requested())`

Also directly calls main_window methods:
- Line 361: `self.epoch_length_spin.valueChanged.connect(self.main_window.on_epoch_length_changed)`
- Line 471: `self.activity_browse_btn.clicked.connect(self.main_window.browse_activity_files)`
- Line 478: `self.activity_import_btn.clicked.connect(self.main_window.start_activity_import)`
- Line 538: `self.clear_markers_btn.clicked.connect(self.app_state.clear_all_markers)`
- Line 569/576: `self.nwt_browse_btn/nwt_import_btn` connects to main_window methods
- Line 1304: `self.services.db_manager.clear_nwt_data()` (direct DB call)

**Severity:** HIGH. The tab mixes presentation with dispatch and direct service calls. This should use the connector pattern with signal emissions.

#### V-W06: `FileNavigationManager` is a misplaced coordinator
**File:** `ui/file_navigation.py`
**Violations:**
- Lines 77, 86, 95: `self.store.dispatch(Actions.date_selected(index))`, `Actions.date_navigated(-/+1)`
- Line 108: `Selectors.is_any_markers_dirty(self.parent.store.state)` -- reads state

This class dispatches to the store and reads state, functioning as a coordinator rather than a widget helper. It also shows a QMessageBox dialog (line 113-118), which is acceptable for navigation guards.
**Severity:** LOW. It is structurally a coordinator, not a widget. It could be renamed and moved to `ui/coordinators/` for clarity.

---

## Connector Compliance

### Pattern Summary

All connectors follow the expected pattern:
```python
class XxxConnector:
    def __init__(self, store, main_window):
        self._unsubscribe = store.subscribe(self._on_state_change)
    def _on_state_change(self, old_state, new_state):
        if old_state.X != new_state.X:
            self._update_widget()
    def disconnect(self):
        self._unsubscribe()
```

### Connector-by-Connector Assessment

| Connector | File | Subscribes | Dispatches | Business Logic | Verdict |
|-----------|------|------------|------------|----------------|---------|
| `ActivityDataConnector` | `connectors/activity.py` | Yes | Yes (ACTIVITY_DATA_LOADED, SADEH_RESULTS_COMPUTED) | Calls data_service.load_unified_activity_data | BORDERLINE -- loads data and dispatches. Documented as intentional architecture. |
| `PlotDataConnector` | `connectors/plot.py` | Yes | No | None | PASS |
| `PlotClickConnector` | `connectors/plot.py` | No (connects signals) | No | None -- delegates to widget methods based on store state | PASS |
| `PlotArrowsConnector` | `connectors/plot.py` | Yes | No | None | PASS |
| `DateDropdownConnector` | `connectors/navigation.py` | Yes | No | Calls db_manager.load_sleep_metrics for coloring | MINOR -- direct DB access for UI coloring |
| `NavigationConnector` | `connectors/navigation.py` | Yes | No | None | PASS |
| `NavigationGuardConnector` | `connectors/navigation.py` | No (connects signals) | Yes (date_navigated, date_selected) | Calls _check_unsaved_markers_before_navigation | PASS -- guard logic is appropriate for connectors |
| `ViewModeConnector` | `connectors/navigation.py` | Yes | No | None | PASS |
| `ConsensusCheckboxConnector` | `connectors/navigation.py` | Yes | Yes (consensus_flag_toggled) | None | PASS |
| `FileListConnector` | `connectors/file.py` | Yes | No | None | PASS |
| `FileManagementConnector` | `connectors/file.py` | Yes | Yes (refresh_files_requested, delete_files_requested) | None | PASS |
| `FileTableConnector` | `connectors/file.py` | Yes | No | None | PASS |
| `FileSelectionLabelConnector` | `connectors/file.py` | Yes | No | None | PASS |
| `MarkersConnector` | `connectors/marker.py` | Yes + signal connections | Yes (selected_period_changed, selected_nonwear_changed, sleep_markers_changed, nonwear_markers_changed) | None | PASS |
| `MarkerModeConnector` | `connectors/marker.py` | Yes | No | Directly manipulates renderer (acceptable for visual state) | PASS |
| `AdjacentMarkersConnector` | `connectors/marker.py` | Yes | No | Calls marker_service for adjacent day data | MINOR -- calls service but for display data |
| `AutoSaveConnector` | `connectors/marker.py` | Yes | No | None (delegates to coordinator) | PASS |
| `SaveButtonConnector` | `connectors/save_status.py` | Yes | No | None | PASS |
| `StatusConnector` | `connectors/save_status.py` | Yes | No | None | PASS |
| `UIControlsConnector` | `connectors/ui_controls.py` | Yes | No | None | PASS |
| `AnalysisTabConnector` | `connectors/ui_controls.py` | No (connects signals) | Yes (dispatches via signal handlers) | None | PASS -- clean signal-to-dispatch bridge |
| `SignalsConnector` | `connectors/ui_controls.py` | No (connects signals) | No (delegates to main_window) | None | PASS |
| `TimeFieldConnector` | `connectors/ui_controls.py` | Yes | No | None | PASS |
| `AlgorithmConfigConnector` | `connectors/settings.py` | Yes | No | None | PASS |
| `AlgorithmDropdownConnector` | `connectors/settings.py` | Yes | No | None | PASS |
| `StudySettingsConnector` | `connectors/settings.py` | Yes | No | Contains side effect logic (algorithm/detector creation, cache clearing, paradigm updates) | CONCERN -- significant business logic in _handle_side_effects |
| `CacheConnector` | `connectors/settings.py` | Yes | No | None | PASS |
| `DiaryTableConnector` | `connectors/table.py` | Yes | No | None | PASS |
| `SideTableConnector` | `connectors/table.py` | Yes | No | None | PASS |
| `PopOutConnector` | `connectors/table.py` | Yes | No | None | PASS |
| `ConfigPersistenceConnector` | `connectors/persistence.py` | Yes | No | Calls config_manager.update_study_settings | ACCEPTABLE -- persistence is a valid connector concern |
| `WindowGeometryConnector` | `connectors/persistence.py` | No (timer polling) | Yes (window_geometry_changed) | None | PASS |
| `ErrorNotificationConnector` | `connectors/error.py` | Yes | No | None | PASS |
| `SideEffectConnector` | `connectors/manager.py` | Yes | Yes (multiple actions) | Calls db_manager.clear_activity_data, data_service.find_available_files, data_service.delete_files | ACCEPTABLE -- documented as the effect handler layer |

### Connector Issues

#### V-C01: `StudySettingsConnector._handle_side_effects` contains business logic
**File:** `ui/connectors/settings.py:163-249`
**Issue:** The method creates algorithm instances, clears caches, calls `load_nonwear_data_for_plot()`, updates table headers, and updates compatibility status. This is orchestration logic that would be better placed in a coordinator or service.
**Severity:** MEDIUM.

#### V-C02: `DateDropdownConnector._update_visuals` directly accesses database
**File:** `ui/connectors/navigation.py:138`
**Issue:** `self.main_window.db_manager.load_sleep_metrics(filename=filename)` -- direct DB query in a connector for UI coloring.
**Severity:** LOW. This is a read-only query for visual display. Could be moved to a service but the pragmatic approach is acceptable.

#### V-C03: `ActivityDataConnector` functions as a side-effect handler
**File:** `ui/connectors/activity.py:69-100+`
**Issue:** This connector both subscribes to state and dispatches actions after calling a service. It is essentially an effect handler wearing a connector's name. It is well-documented as such (comments explain the architectural decision).
**Severity:** LOW -- architecturally justified. Could be renamed to `ActivityDataEffectHandler` for clarity.

---

## Coordinator Compliance

| Coordinator | File | QTimer/QThread | Dispatches | Business Logic | Verdict |
|-------------|------|----------------|------------|----------------|---------|
| `AutosaveCoordinator` | `coordinators/autosave_coordinator.py` | QTimer (debounce) | Yes (markers_saved) | Calls db_manager for saves | PASS -- debounce timer is exactly what coordinators are for |
| `MarkerLoadingCoordinator` | `coordinators/marker_loading_coordinator.py` | QTimer.singleShot(0) | Yes (markers_loaded) | Calls db_manager for marker loading | PASS -- QTimer used to break dispatch cycle |
| `UIStateCoordinator` | `coordinators/ui_state_coordinator.py` | None | Yes (ui_controls_enabled_changed, clear_activity_data_requested) | None | PASS -- thin dispatch wrapper |
| `ImportUICoordinator` | `coordinators/import_ui_coordinator.py` | QTimer, QThread workers | Yes (refresh_files_requested) | Manages import workers, file selection, validation | PASS -- thread management is coordinator territory |
| `DiaryIntegrationCoordinator` | `coordinators/diary_integration_coordinator.py` | None | Yes (sleep_markers_changed, date_navigated) | Diary data loading, marker coordinate mapping, timestamp finding | CONCERN -- contains significant domain logic (timestamp finding, marker creation from diary data) |
| `DiaryTableConnector` (in coordinators/) | `coordinators/diary_table_connector.py` | None | No | Diary table population | PASS -- misnamed but functions correctly |
| `SeamlessSourceSwitcher` | `coordinators/seamless_source_switcher.py` | None | Yes (preferred_display_column_changed) | Plot state save/restore, data reload orchestration | ACCEPTABLE -- complex visual coordination |
| `TimeFieldCoordinator` | `coordinators/time_field_coordinator.py` | QTimer (focus delay) | No | Time field validation and focus handling | PASS |

### Coordinator Issues

#### V-CO01: `DiaryIntegrationCoordinator` contains domain logic
**File:** `ui/coordinators/diary_integration_coordinator.py`
**Issue:** Contains timestamp parsing, marker creation from diary data, date navigation logic, and direct store state reads (lines 107, 272, 304, 336, 375, 486, 603). This should be split: domain logic (timestamp parsing, marker creation) should be in a service, and the coordinator should only handle Qt-level orchestration.
**Severity:** MEDIUM.

---

## Protocol Usage

### Defined Protocols (from `ui/protocols.py`)

| Protocol | Purpose |
|----------|---------|
| `MarkerLineProtocol` | Type-safe marker line attributes |
| `ConfigWithAlgorithmProtocol` | Config with algorithm settings |
| `PlotWidgetProtocol` | ActivityPlotWidget interface (30+ methods/attributes) |
| `AnalysisTabProtocol` | AnalysisTab interface |
| `DataSettingsTabProtocol` | DataSettingsTab interface |
| `ExportTabProtocol` | ExportTab interface |
| `StudySettingsTabProtocol` | StudySettingsTab interface |
| `MarkerTableProtocol` | MarkerTable interface |
| `FileNavigationProtocol` | FileNavigation interface |
| `StateManagerProtocol` | WindowStateManager interface |
| `ServiceContainer` | Core application services |
| `MarkerOperationsInterface` | Marker placement and manipulation |
| `NavigationInterface` | Navigation operations |
| `ImportInterface` | Data import operations |
| `AppStateInterface` | Application-wide state and UI coordination |
| `MainWindowProtocol` | Composed from all above |

### hasattr() Audit

All `hasattr()` calls in the codebase have been annotated with `# KEEP:` comments explaining why they are acceptable:

| File | Line | Pattern | Justification |
|------|------|---------|---------------|
| `main_window.py:1246` | `hasattr(self.onset_table, "table_widget")` | Table duck typing | ACCEPTABLE |
| `main_window.py:1252` | `hasattr(self.offset_table, "table_widget")` | Table duck typing | ACCEPTABLE |
| `main_window.py:1350` | `hasattr(self.plot_widget, "get_selected_marker_period")` | Plot widget duck typing | ACCEPTABLE |
| `main_window.py:1956` | `hasattr(self.export_tab, "export_output_label")` | Tab duck typing | ACCEPTABLE |
| `main_window.py:2110-2145` | Multiple `hasattr(self, ...)` during shutdown | Cleanup during shutdown | ACCEPTABLE -- init order not guaranteed during close |
| `coordinators/diary_table_connector.py:226` | `hasattr(self.diary_table_widget, "diary_columns")` | Table widget duck typing | ACCEPTABLE |
| `coordinators/seamless_source_switcher.py:158,270` | `hasattr(self.plot_widget, "vb")` | pyqtgraph ViewBox duck typing | ACCEPTABLE |
| `widgets/plot_overlay_renderer.py:259` | `hasattr(self.parent, "timestamps")` | Duck typing plot attributes | ACCEPTABLE |
| `widgets/plot_state_serializer.py:392,398` | `hasattr(self.parent, "_algorithm_cache"/"sadeh_results")` | Duck typing plot attributes | ACCEPTABLE |

**RESULT:** All hasattr() usages have been reviewed and annotated. No instances of hasattr() abuse (hiding init-order bugs or replacing proper Protocol usage) were found. The existing uses fall into three legitimate categories: (1) cleanup during shutdown, (2) duck typing for external library objects (pyqtgraph), and (3) optional attributes on widgets.

---

## Signal Wiring

### Correct Wiring (in Connectors)

The following signal connections are properly made in connectors:

- `MarkersConnector`: Connects `plot_widget.sleep_markers_changed`, `nonwear_markers_changed`, `sleep_period_selection_changed`, `nonwear_selection_changed` to dispatch handlers
- `PlotClickConnector`: Connects `plot_widget.plot_left_clicked`, `plot_right_clicked` to dispatch handlers
- `AnalysisTabConnector`: Connects `analysisTab.activitySourceChanged`, `viewModeChanged`, `adjacentMarkersToggled`, `autoSaveToggled`, `markerModeChanged` to dispatch handlers
- `NavigationGuardConnector`: Connects `analysisTab.prevDateRequested`, `nextDateRequested`, `dateSelectRequested` to guarded dispatch handlers
- `SignalsConnector`: Connects `file_selector.fileSelected` to dispatch handler
- `FileManagementConnector`: Connects `widget.refreshRequested`, `deleteRequested` to dispatch handlers

### Signals Wired in Widgets (Violations)

#### V-S01: `AnalysisTab` connects buttons directly to marker_ops methods
**File:** `ui/analysis_tab.py`
- Line 808: `self.save_markers_btn.clicked.connect(self.marker_ops.save_current_markers)`
- Line 816: `self.no_sleep_btn.clicked.connect(self.marker_ops.mark_no_sleep_period)`
- Line 823: `self.clear_markers_btn.clicked.connect(self.marker_ops.clear_current_markers)`

**Issue:** Button clicks bypass the connector pattern entirely, connecting directly to service interface methods. These should emit signals that a connector handles.
**Severity:** MEDIUM.

#### V-S02: `DataSettingsTab` connects buttons directly to main_window methods
**File:** `ui/data_settings_tab.py`
- Line 361: `self.epoch_length_spin.valueChanged.connect(self.main_window.on_epoch_length_changed)`
- Line 471: `self.activity_browse_btn.clicked.connect(self.main_window.browse_activity_files)`
- Line 478: `self.activity_import_btn.clicked.connect(self.main_window.start_activity_import)`
- Line 538: `self.clear_markers_btn.clicked.connect(self.app_state.clear_all_markers)`
- Line 569: `self.nwt_browse_btn.clicked.connect(self.main_window.browse_nonwear_files)`
- Line 576: `self.nwt_import_btn.clicked.connect(self.main_window.start_nonwear_import)`

**Issue:** Buttons connect directly to main_window methods, bypassing the connector layer entirely.
**Severity:** MEDIUM.

#### V-S03: `StudySettingsTab` connects change handlers that dispatch directly
**File:** `ui/study_settings_tab.py`
- Lines 227-233: Combo boxes connect to `_on_*_changed` methods that dispatch to store
- Lines 409-441: List and text widgets connect to change handlers that dispatch to store

**Issue:** The tab's signal handlers dispatch directly to the store. These should emit signals for a connector.
**Severity:** HIGH (same as V-W04).

#### V-S04: `MainWindow` connects signals in __init__
**File:** `ui/main_window.py`
- Line 457: `self.tab_widget.currentChanged.connect(self._on_tab_changed)`
- Line 514: `self.plot_widget.error_occurred.connect(self.handle_plot_error)`
- Line 515: `self.plot_widget.marker_limit_exceeded.connect(self.handle_marker_limit_exceeded)`
- Lines 1248, 1254: Table context menu connections

**Issue:** These connections are in MainWindow rather than in connectors. The error/marker_limit connections could be moved to the ErrorNotificationConnector.
**Severity:** LOW. MainWindow as the root component is an acceptable place for some top-level wiring.

#### V-S05: `ActivityPlotWidget` connects internal signals in __init__
**File:** `ui/widgets/activity_plot.py`
- Line 400: `self.vb.sigRangeChanged.connect(self.enforce_range_limits)` (pyqtgraph internal)
- Line 405: `scene.sigMouseClicked.connect(self.on_plot_clicked)` (pyqtgraph internal)
- Line 410: `self._mouse_move_timer.timeout.connect(self._process_mouse_move)` (internal timer)
- Line 414: `scene.sigMouseMoved.connect(self._on_mouse_move_throttled)` (pyqtgraph internal)

**Assessment:** These are all **internal widget wiring** (pyqtgraph scene events to widget handlers). This is **ACCEPTABLE** -- widgets are allowed to wire their own internal signals.

---

## Prioritized Remediation Recommendations

### HIGH Priority

1. **V-W04/V-S03: StudySettingsTab dispatches directly (~20 dispatch calls)**
   Create a `StudySettingsDispatchConnector` that connects to tab signals. The tab should emit `settingChanged(str, Any)` signals.

2. **V-W05/V-S02: DataSettingsTab dispatches and calls main_window directly**
   Similar treatment -- emit signals for file operations and let connectors handle dispatch and service calls.

### MEDIUM Priority

3. **V-S01: AnalysisTab button-to-service wiring**
   Buttons should emit signals; a connector should bridge to `marker_ops`.

4. **V-W01: PlotOverlayRenderer reads store state**
   Pass data as parameters from PlotDataConnector rather than having the renderer reach into the store.

5. **V-W02: AnalysisDialogManager holds service references**
   Extract service calls to callbacks or a connector.

6. **V-C01: StudySettingsConnector._handle_side_effects contains business logic**
   Move algorithm creation and cache management to a service or coordinator.

7. **V-CO01: DiaryIntegrationCoordinator domain logic**
   Extract timestamp parsing and marker creation to a diary service.

### LOW Priority

8. **V-W06: FileNavigationManager naming/location**
   Rename and move to `ui/coordinators/` for clarity.

9. **V-C02: DateDropdownConnector direct DB access**
   Could be moved to a service method but pragmatically acceptable.

10. **V-C03: ActivityDataConnector naming**
    Consider renaming to `ActivityDataEffectHandler` for architectural clarity.

---

## Verification Checklist

- [x] Read `ui/store.py` -- full Action/State shape cataloged (32 ActionTypes, 55 UIState fields)
- [x] Checked every widget file in `ui/widgets/` for store/service/parent access (14 widget files)
- [x] Checked every tab file (`analysis_tab.py`, `data_settings_tab.py`, `study_settings_tab.py`, `export_tab.py`)
- [x] Checked every connector file in `ui/connectors/` for pattern compliance (11 connector files, 30+ connectors)
- [x] Checked every coordinator file in `ui/coordinators/` (8 coordinator files)
- [x] Searched for `hasattr()` globally -- all instances reviewed and documented
- [x] Searched for direct state mutations (`store.state.X = Y`) -- none found
- [x] Searched for `store.dispatch` in widget files -- violations documented
- [x] Searched for `store.state` reads in widget files -- violations documented
- [x] Searched for `.connect()` calls in widget files -- cross-boundary wiring documented
- [x] Checked `ui/protocols.py` for Protocol coverage
- [x] Checked `ui/main_window.py` for signal wiring
- [x] Checked `ui/file_navigation.py`, `ui/window_state.py`, `ui/shortcut_manager.py`
- [x] Checked `ui/builders/` for store access -- none found
