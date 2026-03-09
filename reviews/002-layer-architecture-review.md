# Layer Architecture Review

**Date**: 2026-02-02
**Scope**: `sleep_scoring_app/` (desktop PyQt6 app only)
**Auditor**: Automated architecture audit
**Architecture Reference**: `CLAUDE.md` -- LAYERED ARCHITECTURE (MANDATORY)

## Summary

| Metric | Value |
|--------|-------|
| Total files audited | ~120 .py files across all layers |
| Critical violations | 3 |
| Warnings | 8 |
| Layers passing cleanly | Core, Services, IO (3 of 6) |
| Layers with issues | UI Widgets, UI Tabs/Builders, Utils (3 of 6) |

The lower layers (Core, Services, IO) are **clean** -- they have zero upward dependencies and zero PyQt6 imports where prohibited. The upper layers (UI) have several areas where the intended separation of concerns is blurred, primarily around tab components dispatching directly to the store, widgets accessing store state, and a utility module reaching into the UI layer.

---

## Critical Violations (layer boundary crossings)

### CRITICAL-1: Utils layer imports from UI layer (runtime)

**File**: `sleep_scoring_app/utils/participant_extractor.py:21`
```python
def _get_global_config():
    """Get config from ConfigManager if available (lazy import to avoid circular deps)."""
    try:
        from sleep_scoring_app.ui.utils.config import ConfigManager  # <-- VIOLATION
        config_manager = ConfigManager()
        return config_manager.config
```

**Rule broken**: The `utils/` layer is a shared utility layer that sits below `ui/`. A utility function should never import from `ui/` -- this creates an upward dependency that couples a shared module to the Qt-dependent UI layer.

**Impact**: Any non-UI consumer of `extract_participant_info()` (e.g., the web backend, CLI, tests) transitively pulls in `ConfigManager`, which uses `PyQt6.QtCore.QSettings`. This will fail in headless environments.

**Suggested fix**: Accept config as a required parameter (dependency injection). The function already has a `config` parameter -- make callers pass it instead of falling back to a global UI singleton. Remove `_get_global_config()` entirely.

---

### CRITICAL-2: Widget sub-component accesses Redux store directly

**File**: `sleep_scoring_app/ui/widgets/plot_overlay_renderer.py:56-78`
```python
class PlotOverlayRenderer:
    @property
    def store(self) -> UIStore:
        """Get Redux store from main window."""
        return self._main_window.store

    @property
    def _timestamps(self) -> tuple:
        return self.store.state.activity_timestamps

    @property
    def _sadeh_results(self) -> tuple:
        return self.store.state.sadeh_results

    @property
    def _axis_y_data(self) -> tuple:
        return self.store.state.axis_y_data

    @property
    def _current_filename(self) -> str | None:
        return self.store.state.current_file
```

**Rule broken**: Per CLAUDE.md, widgets must be "dumb" -- they emit signals and receive data, they do NOT access the store directly. `PlotOverlayRenderer` is a widget sub-component (helper class for `ActivityPlotWidget`) but it reads `store.state` properties directly, bypassing the Connector pattern.

**Impact**: The overlay renderer is tightly coupled to the Redux store shape. If store state fields are renamed or restructured, this widget breaks. Data should be passed to it by the `ActivityPlotWidget` or a Connector.

**Suggested fix**: Have the parent `ActivityPlotWidget` (or its Connector) pass timestamps, sadeh_results, axis_y_data, and current_file as parameters to the renderer's methods, rather than the renderer reaching into the store.

---

### CRITICAL-3: Widget sub-component imports UIStore (TYPE_CHECKING)

**File**: `sleep_scoring_app/ui/widgets/analysis_dialogs.py:38`
```python
if TYPE_CHECKING:
    from sleep_scoring_app.ui.store import UIStore
```

**File**: `sleep_scoring_app/ui/widgets/plot_overlay_renderer.py:26`
```python
if TYPE_CHECKING:
    from sleep_scoring_app.ui.store import UIStore
```

**Rule broken**: While TYPE_CHECKING imports do not create runtime dependencies, they indicate that the widget's type signature depends on the store. Widget components in `ui/widgets/` should not reference the store type at all -- they should only know about domain types from `core/`. The `AnalysisDialogManager` constructor accepts `store: UIStore` directly, which means it acts more like a Coordinator than a widget helper.

**Impact**: These widget helpers cannot be tested without the store type. They are effectively mini-coordinators disguised as widgets.

**Suggested fix**: `AnalysisDialogManager` should be moved to `ui/coordinators/` since it takes store, navigation, marker_ops, and services -- it is a coordinator, not a widget. For `PlotOverlayRenderer`, pass data as parameters instead of store references.

---

## Warnings (potential issues)

### WARN-1: Tab components dispatch to store directly

**Files**:
- `sleep_scoring_app/ui/data_settings_tab.py:140-141, 1290` -- dispatches `file_selected`, `dates_loaded`, `clear_activity_data_requested`
- `sleep_scoring_app/ui/study_settings_tab.py:359, 820-982, 1406-1514` -- dispatches `study_settings_changed` (18 locations)
- `sleep_scoring_app/ui/file_navigation.py:77, 86, 95` -- dispatches `date_selected`, `date_navigated`

**Assessment**: Per the architecture, widgets should only emit signals and Connectors should dispatch. However, these tab components are complex top-level containers that straddle the widget/coordinator boundary. The `StudySettingsTab` dispatches settings changes directly rather than emitting signals for a connector to handle. The `FileNavigationManager` is essentially a coordinator (not a widget) and its store dispatch is reasonable.

**Severity**: Medium. The tabs act as both widget and coordinator. This is a pragmatic trade-off but creates coupling that makes the tabs harder to test independently.

**Suggested fix**: For `StudySettingsTab`, have each setting widget emit a signal, and create a `StudySettingsConnector` that subscribes to those signals and dispatches to the store. For `DataSettingsTab`, the same pattern applies.

---

### WARN-2: Tabs import services directly

**Files**:
- `sleep_scoring_app/ui/analysis_tab.py:1193-1217` -- imports `algorithm_service` (5 locations, lazy)
- `sleep_scoring_app/ui/data_settings_tab.py:899, 950, 987, 1023` -- imports `FormatDetector` (4 locations, lazy)
- `sleep_scoring_app/ui/study_settings_tab.py:38` -- imports `algorithm_service` (top-level)
- `sleep_scoring_app/ui/builders/algorithm_section_builder.py:29` -- imports `algorithm_service` (top-level)

**Assessment**: Per the architecture, services should be accessed through dependency injection via the `ServiceContainer` protocol, not imported directly. The lazy imports in `analysis_tab.py` suggest awareness of the coupling issue. The top-level import in `study_settings_tab.py` and `algorithm_section_builder.py` is a stronger violation.

**Severity**: Medium. Direct service imports create tight coupling and make testing harder. However, many of these are factory/registry lookups (stateless) rather than stateful service calls.

**Suggested fix**: Inject `algorithm_service` via the constructor or `ServiceContainer` protocol. For `FormatDetector`, inject it or create a method on an existing service.

---

### WARN-3: hasattr() usage in widget sub-components

**Files**:
- `sleep_scoring_app/ui/widgets/plot_overlay_renderer.py:259` -- `hasattr(self.parent, "timestamps")`
- `sleep_scoring_app/ui/widgets/plot_state_serializer.py:392` -- `hasattr(self.parent, "_algorithm_cache")`
- `sleep_scoring_app/ui/widgets/plot_state_serializer.py:398` -- `hasattr(self.parent, "sadeh_results")`

**Assessment**: Per CLAUDE.md, `hasattr()` should not be used to hide initialization order bugs. These helpers access their parent's attributes defensively. All three have `# KEEP: Duck typing plot/marker attributes` annotations, but since `PlotOverlayRenderer` and `PlotStateSerializer` always receive `ActivityPlotWidget` as their parent (strongly typed), the hasattr checks hide potential bugs rather than providing genuine duck typing.

**Severity**: Low. The code works, but the `# KEEP` comments may mask real init-order issues.

**Suggested fix**: Since the parent type is always `ActivityPlotWidget`, use the `PlotWidgetProtocol` to guarantee these attributes exist rather than defensively checking with `hasattr()`.

---

### WARN-4: hasattr() usage in main_window.py

**Files**:
- `sleep_scoring_app/ui/main_window.py:1246, 1252` -- `hasattr(self.onset_table, "table_widget")`
- `sleep_scoring_app/ui/main_window.py:1350` -- `hasattr(self.plot_widget, "get_selected_marker_period")`
- `sleep_scoring_app/ui/main_window.py:1956` -- `hasattr(self.export_tab, "export_output_label")`
- `sleep_scoring_app/ui/main_window.py:2110-2145` -- Multiple `hasattr(self, ...)` for cleanup

**Assessment**: The cleanup-related `hasattr()` calls (lines 2110-2145) are justified for shutdown safety. The attribute-checking `hasattr()` calls (lines 1246, 1252, 1350, 1956) are working around initialization order or optional tab creation. All have `# KEEP` annotations.

**Severity**: Low. The cleanup uses are valid. The others indicate that the main window's init order is fragile.

---

### WARN-5: ui/services/ directory contains Qt-dependent service

**File**: `sleep_scoring_app/ui/services/session_state_service.py`

**Assessment**: This file imports `PyQt6.QtCore.QSettings` and `PyQt6.QtWidgets.QApplication`. Per the architecture, `services/` should be headless with no Qt imports. However, this file is intentionally placed under `ui/services/` (not `services/`), which is a reasonable location for a Qt-dependent session service.

**Severity**: Low. The placement is deliberate and documented. The naming (`ui/services/`) correctly signals its Qt dependency.

---

### WARN-6: Connectors importing services directly

**File**: `sleep_scoring_app/ui/connectors/settings.py:165`
```python
from sleep_scoring_app.services.algorithm_service import get_algorithm_service
```

**Assessment**: Connectors should bridge Widget and Store. This connector also calls a service directly for side effects (updating algorithm config when settings change). This is a gray area -- the connector is reacting to state change and orchestrating an update, which could be seen as a coordinator responsibility.

**Severity**: Low. The import is lazy (inside a method) and the connector is handling a legitimate side effect.

---

### WARN-7: ConfigManager placed in ui/utils/ but used as shared dependency

**File**: `sleep_scoring_app/ui/utils/config.py`

**Assessment**: `ConfigManager` uses `PyQt6.QtCore.QSettings` for persistence, which ties it to the UI layer. However, it manages `AppConfig` (a core dataclass) and is referenced by the `ServiceContainer` protocol. Its placement in `ui/utils/` is correct given the Qt dependency, but the `participant_extractor.py` (in `utils/`) importing it (CRITICAL-1) shows that lower layers need config access without Qt.

**Severity**: Informational. The config access pattern should be through dependency injection, not global singleton access.

---

### WARN-8: Coordinators directly accessing DatabaseManager

**Files**:
- `sleep_scoring_app/ui/coordinators/autosave_coordinator.py:36` -- runtime import of `DatabaseManager`
- `sleep_scoring_app/ui/coordinators/marker_loading_coordinator.py:22` -- TYPE_CHECKING import of `DatabaseManager`

**Assessment**: Coordinators bypass the service layer and access the database directly. The architecture says services handle data operations. However, coordinators are explicitly allowed to use Qt mechanisms and dispatch to the store, and the autosave/marker-loading use cases are tightly coupled to the store lifecycle.

**Severity**: Low. This is a pragmatic shortcut. Wrapping these in a service would add indirection without clear benefit.

---

## Layer-by-Layer Status

### Core Layer: PASS

**Files audited**: 52 .py files across `core/`, `core/algorithms/`, `core/backends/`, `core/constants/`, `core/markers/`, `core/pipeline/`

**Checks performed**:
- `from sleep_scoring_app.ui` -- 0 matches
- `from sleep_scoring_app.services` -- 0 matches
- `from PyQt6` / `import PyQt6` -- 0 matches
- `import sleep_scoring_app.ui` / `import sleep_scoring_app.services` -- 0 matches

**Notes**: `core/markers/persistence.py:26` imports `DatabaseManager` under `TYPE_CHECKING` only. This is acceptable for type annotations and does not create a runtime dependency.

The core layer is completely clean. No upward dependencies of any kind.

---

### Services Layer: PASS

**Files audited**: 29 .py files in `services/` and `services/diary/`

**Checks performed**:
- `from PyQt6` / `import PyQt6` -- 0 matches
- `pyqtSignal` / `QThread` / `QObject` / `QTimer` -- 0 matches
- `from sleep_scoring_app.ui` -- 0 matches

**Notes**: Services properly import from `data/` (database, repositories) and `core/` (dataclasses, constants). They use callbacks, not signals. This layer is fully headless and testable without Qt.

---

### IO Layer: PASS

**Files audited**: 7 .py files in `io/` and `io/sources/`

**Checks performed**:
- `from sleep_scoring_app.ui` -- 0 matches
- `from sleep_scoring_app.services` -- 0 matches
- `from PyQt6` / `import PyQt6` -- 0 matches

**Notes**: The IO layer only imports from `core/` (constants, dataclasses). Clean separation.

---

### UI Widgets: FAIL (3 violations)

**Files audited**: 18 .py files in `ui/widgets/`

**Violations**:
1. **CRITICAL-2**: `plot_overlay_renderer.py` accesses `store.state` directly (4 properties)
2. **CRITICAL-3**: `analysis_dialogs.py` and `plot_overlay_renderer.py` import `UIStore` type
3. **WARN-3**: `plot_overlay_renderer.py` and `plot_state_serializer.py` use `hasattr()` on typed parent

**Clean widgets** (no violations): `activity_plot.py`, `drag_drop_list.py`, `file_management_widget.py`, `file_selection_table.py`, `marker_drawing_strategy.py`, `marker_editor.py`, `marker_interaction_handler.py`, `no_scroll_widgets.py`, `plot_algorithm_manager.py`, `plot_data_manager.py`, `plot_marker_renderer.py`, `plot_state_manager.py`, `popout_table_window.py`

The `activity_plot.py` widget itself is exemplary -- it uses signals (`sleep_markers_changed`, `nonwear_markers_changed`, etc.) and does not reference the store. The violations are in its helper classes.

---

### UI Connectors: PASS (with note)

**Files audited**: 12 .py files in `ui/connectors/`

**Assessment**: Connectors properly:
- Subscribe to store state changes
- Connect widget signals to dispatch
- Bridge widget <-> store

One connector (`settings.py:165`) imports a service directly for side effects, which is a minor gray area (WARN-6).

---

### UI Coordinators: PASS (with notes)

**Files audited**: 8 .py files in `ui/coordinators/`

**Assessment**: Coordinators appropriately use Qt mechanisms (QTimer, QThread) and dispatch to the store. Two coordinators access `DatabaseManager` directly (WARN-8) rather than through services, which is a pragmatic shortcut.

---

### UI Tabs / Builders / Dialogs: FAIL (warnings)

**Files with issues**:
- `study_settings_tab.py` -- top-level service import, direct store dispatch (18 locations)
- `data_settings_tab.py` -- lazy service imports (4 locations), direct store dispatch (3 locations)
- `analysis_tab.py` -- lazy service imports (5 locations)
- `algorithm_section_builder.py` -- top-level service import

These components act as hybrid widget/coordinators. They build UI, handle events, and dispatch to the store -- all responsibilities that should be split between a dumb widget and a connector.

---

### Utils / Data / Preprocessing: PASS (with 1 critical exception)

**Files audited**: 15 .py files in `utils/`, 14 in `data/`, 3 in `preprocessing/`

**Violations**:
1. **CRITICAL-1**: `utils/participant_extractor.py:21` -- runtime import from `ui.utils.config`

All other files in these layers are clean.

---

## Verification Checklist

- [x] Searched every .py file in `core/` (52 files) for upward imports
- [x] Searched every .py file in `services/` (29 files) for PyQt6 and UI imports
- [x] Searched every .py file in `io/` (7 files) for UI and services imports
- [x] Searched every .py file in `ui/widgets/` (18 files) for store.dispatch, store.state, parent(), hasattr, services imports
- [x] Searched every .py file in `ui/connectors/` (12 files) for services imports and business logic
- [x] Searched every .py file in `ui/coordinators/` (8 files) for layer violations
- [x] Searched every .py file in `ui/builders/` (9 files) for services imports
- [x] Searched every .py file in `ui/dialogs/` (3 files) for violations
- [x] Searched every .py file in `utils/` (15 files), `data/` (14 files), `preprocessing/` (3 files) for cross-layer imports
- [x] Checked both `from X import` and `import X` patterns
- [x] Checked for indirect violations (utility importing UI-layer code)
- [x] Verified TYPE_CHECKING-only imports are not counted as runtime violations
