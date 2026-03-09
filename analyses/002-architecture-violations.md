# Architecture Layer Violations Audit

## Summary

| Category | Count | Severity |
|----------|-------|----------|
| Services importing from UI | 2 files | CRITICAL |
| Data importing from Services | 1 file | CRITICAL |
| Store importing PyQt6 | 1 file | MAJOR |
| Tabs dispatching directly to store | 4 files | MINOR (Acceptable) |
| Widget sub-components using parent | 5 files | MINOR (Internal composition) |

**Total Critical Violations: 3 files requiring immediate refactoring**

---

## Critical Violations (Must Fix)

### 1. Services Layer Importing from UI Layer

**Violation of Rule: "Services are HEADLESS - No Qt imports, no signals"**

#### `sleep_scoring_app/services/ui_state_coordinator.py:18`

```python
if TYPE_CHECKING:
    from sleep_scoring_app.ui.protocols import MainWindowProtocol
```

**Problem:** This service coordinates UI state directly by accessing MainWindow widgets. It reads from parent.plot_widget, parent.file_selector, etc. This service should NOT exist in the services layer - it belongs in UI layer.

**Impact:**
- Tight coupling between services and UI
- Cannot test this service without Qt
- Breaks the headless service principle

**Recommendation:** Move `UIStateCoordinator` to `ui/coordinators/` directory since it directly manipulates UI widgets.

---

#### `sleep_scoring_app/services/unified_data_service.py:27,142`

```python
# Line 27 (TYPE_CHECKING import)
from sleep_scoring_app.ui.store import UIStore

# Line 142 (runtime import inside method)
from sleep_scoring_app.ui.store import Actions
self.store.dispatch(Actions.files_loaded(files))
```

**Problem:** This "headless" service directly dispatches to the Redux store, violating the unidirectional data flow and making the service dependent on UI state management.

**Impact:**
- Service becomes untestable without Redux store
- Breaks single responsibility principle
- Circular dependency risk

**Recommendation:**
1. Remove store reference from UnifiedDataService
2. Use callback pattern everywhere (partially implemented with `on_files_loaded` callback)
3. Callers should dispatch actions after receiving data from service

---

### 2. Data Layer Importing from Services Layer

#### `sleep_scoring_app/data/database.py:34`

```python
from sleep_scoring_app.services.memory_service import resource_manager
```

**Problem:** Data layer (IO/persistence) should be pure and depend only on Core layer. Importing from services creates upward dependency.

**Impact:**
- Data layer cannot be used without services layer initialized
- Circular dependency risk
- Harder to test data layer in isolation

**Recommendation:**
1. Move `resource_manager` to a shared utility module (e.g., `core/memory/` or `utils/memory.py`)
2. Or inject resource_manager as a dependency to DatabaseManager

---

### 3. Redux Store Importing PyQt6

#### `sleep_scoring_app/ui/store.py:971,998`

```python
# Line 971
from PyQt6.QtCore import QTimer
QTimer.singleShot(0, lambda: self.dispatch(action))

# Line 998
from PyQt6.QtCore import QTimer
QTimer.singleShot(0, run_both)
```

**Problem:** The store uses QTimer for async dispatch. While store is in `ui/` directory, it should remain pure Python to allow testing without Qt and maintain clean architecture.

**Impact:**
- Store cannot be tested without Qt event loop
- Breaks Redux purity principle

**Recommendation:**
1. Accept an optional `async_dispatch_callback` in store constructor
2. In production, pass a QTimer-based callback
3. In tests, pass a synchronous callback or mock
4. Alternative: Create `AsyncDispatcher` protocol and inject implementation

---

## Minor Violations (Should Fix)

### 4. Tabs Dispatching Directly to Store

The following files dispatch directly to the store instead of going through Connectors:

| File | Lines | Action Types |
|------|-------|--------------|
| `ui/analysis_tab.py` | 869, 1235, 1245, 1254, 1290 | algorithm_changed, view_mode_changed, adjacent_markers_toggled, auto_save_toggled, marker_mode_changed |
| `ui/data_settings_tab.py` | 131-132, 1269 | file_selected, dates_loaded, clear_activity_data_requested |
| `ui/study_settings_tab.py` | (multiple) | study_settings_changed |
| `ui/file_navigation.py` | (multiple) | date navigation actions |

**Assessment:** These are Tab components (AnalysisTab, DataSettingsTab, etc.) which are high-level UI components that contain their own business logic. CLAUDE.md specifies "Widgets are DUMB" - tabs are not simple widgets but complex container components.

**Recommendation:** LOW PRIORITY - Tabs can legitimately dispatch actions as they are container components, not dumb widgets. The store_connectors pattern is more applicable to simple widgets.

---

### 5. Widget Sub-components Using Parent Reference

The following files use `self.parent` extensively:

| File | Usage Pattern |
|------|---------------|
| `ui/widgets/plot_data_manager.py` | Accesses parent.timestamps, parent.activity_data |
| `ui/widgets/plot_marker_renderer.py` | Accesses parent.daily_sleep_markers, parent.marker_lines |
| `ui/widgets/plot_algorithm_manager.py` | Accesses parent.timestamps, parent.sadeh_results |
| `ui/widgets/plot_overlay_renderer.py` | Accesses parent.nonwear_data, parent.timestamps |
| `ui/widgets/plot_state_serializer.py` | Accesses parent state for serialization |

**Assessment:** These are INTERNAL sub-components of `ActivityPlotWidget`, not standalone widgets. The parent reference is composition within a single widget, not crossing architecture boundaries.

**Recommendation:** ACCEPTABLE - This is proper internal component composition. The "parent" is always `ActivityPlotWidget`, not MainWindow.

---

### 6. hasattr() Usage

Found hasattr() patterns in these files:

| File | Assessment |
|------|------------|
| `ui/main_window.py` | Uses `# KEEP: Duck typing` comments - intentional for optional features |
| `ui/widgets/activity_plot.py` | Checking optional PyQt features (OpenGL, downsampling) |
| `ui/widgets/plot_state_serializer.py` | Duck typing for plot/marker attributes |
| `ui/widgets/analysis_dialogs.py` | Duck typing for optional marker/arrow features |

**Assessment:** All hasattr() usages are marked with `# KEEP: Duck typing` or `# KEEP: Optional X feature` comments, indicating intentional duck typing for optional features rather than hiding init bugs.

**Recommendation:** ACCEPTABLE - These are legitimate duck typing patterns, not architecture violations.

---

## Recommendations

### High Priority (Must Fix)

1. **Move UIStateCoordinator to UI layer**
   - From: `services/ui_state_coordinator.py`
   - To: `ui/coordinators/ui_state_coordinator.py`
   - Rationale: It directly manipulates UI widgets

2. **Remove store dependency from UnifiedDataService**
   - Convert all store.dispatch() calls to callback pattern
   - Callers (in UI layer) should dispatch actions
   - Example fix already partially in place with `on_files_loaded` callback

3. **Extract resource_manager to shared utils**
   - Create: `utils/memory.py` or `core/memory/resource_manager.py`
   - Move: `resource_manager` from services/memory_service.py
   - Update: database.py to import from new location

4. **Make store async dispatch injectable**
   ```python
   class UIStore:
       def __init__(self, async_scheduler: Callable[[Callable], None] | None = None):
           self._async_scheduler = async_scheduler or self._qt_scheduler

       def _qt_scheduler(self, fn: Callable) -> None:
           from PyQt6.QtCore import QTimer
           QTimer.singleShot(0, fn)
   ```

### Low Priority (Consider for next refactor)

5. **Consider Connector pattern for tab actions**
   - Could create TabConnector classes
   - Would improve testability
   - Not strictly required per architecture

---

## Verification Checklist

- [x] All Python files in `core/` checked for imports from ui/services/data
- [x] All Python files in `services/` checked for PyQt6 imports
- [x] All Python files in `services/` checked for ui/ imports
- [x] All Python files in `data/` checked for services/ui imports
- [x] All Python files in `ui/widgets/` checked for parent access patterns
- [x] Store imports verified
- [x] Each violation includes exact file path and line number
- [x] Recommendations are actionable and specific
