# Architecture Review: Sleep Scoring Demo

**Date:** 2026-01-01
**Reviewed By:** Claude Code
**Codebase:** `D:\Scripts\monorepo\apps\sleep-scoring-demo\sleep_scoring_app`

---

## Executive Summary

**Overall Health Rating: 7.5/10**

The codebase demonstrates strong architectural patterns in key areas, with clear improvements from recent refactoring. The Redux-style state management is well-implemented, layer boundaries are mostly respected, and there is extensive use of protocols and StrEnums for type safety.

### Most Critical Issues (Top 5)

1. **MEDIUM** - Coordinators with mixed responsibilities: Some coordinators do more than "QThread/QTimer glue" (e.g., `DiaryIntegrationManager` directly manipulates plot widgets)
2. **MEDIUM** - Managers in coordinators directory: Several "Manager" classes live in `ui/coordinators/` but don't follow coordinator patterns
3. **LOW** - Qt imports in utils: `utils/config.py`, `utils/table_helpers.py`, `utils/thread_safety.py` have Qt dependencies, blurring layer boundaries
4. **LOW** - Non-frozen mutable dataclasses: Several domain dataclasses (markers, config) are not frozen, allowing unintended mutation
5. **LOW** - hasattr() usage is extensive but appropriately documented: All ~100 hasattr() uses have `# KEEP:` comments explaining why

---

## Layer Boundary Violations

### Clean Layers (No Violations)

| Layer | Import Rule | Status |
|-------|-------------|--------|
| Services | No Qt imports | PASS |
| Core | No UI/Service imports | PASS |
| IO | No Qt imports | PASS |
| Data | No Qt imports | PASS |

### Minor Violations in Utils Layer

| File | Violation | Severity |
|------|-----------|----------|
| `utils/config.py:29` | `from PyQt6.QtCore import QSettings` | LOW |
| `utils/table_helpers.py:12-14` | PyQt6 imports (QEvent, QColor, etc.) | LOW |
| `utils/thread_safety.py:14,19` | QThread, QTimer, QWidget imports | LOW |
| `utils/qt_context_managers.py:14` | QWidget import | LOW |

**Analysis:** These utils are Qt-specific helpers. Consider moving them to `ui/utils/` for cleaner separation, or accepting them as "Qt utilities" that are separate from core utils.

---

## Redux Pattern Compliance

### Store Implementation (EXCELLENT)

**File:** `sleep_scoring_app/ui/store.py`

- `UIState` is properly frozen dataclass (line 55)
- `Action` is frozen dataclass (line 216)
- All state changes go through `ui_reducer()` (pure function)
- Proper subscription mechanism with `StateChangeCallback`
- Good use of `Selectors` for derived state

**Rating:** 10/10

### Connectors (EXCELLENT)

**File:** `sleep_scoring_app/ui/store_connectors.py`

Found 33 connectors, all following the pattern:
- Subscribe to store state changes
- Update widgets based on state
- Do not directly dispatch (except for user actions via signals)

Sample compliant connectors:
- `SaveButtonConnector` (line 40) - Updates button based on dirty state
- `DateDropdownConnector` (line 237) - Manages dropdown from state
- `ActivityDataConnector` (line 1260) - Loads data on navigation changes

**Rating:** 9/10 - Minor deduction for some connectors being quite large (could be split)

### Widgets (EXCELLENT)

**Directory:** `sleep_scoring_app/ui/widgets/`

- Widgets do NOT import store or dispatch directly
- No `store.dispatch()` calls found in widgets
- No direct service calls in widgets

**Rating:** 10/10

---

## Coordinator Analysis

### Correct Coordinator Usage

| Coordinator | Uses Qt Mechanisms | Purpose |
|-------------|-------------------|---------|
| `AutosaveCoordinator` | QTimer | Debounced autosave |
| `MarkerLoadingCoordinator` | QTimer.singleShot(0) | Async marker loading outside dispatch |
| `ImportUICoordinator` | QThread workers | Async file imports |

### Misnamed/Misplaced "Managers"

| Class | Current Location | Issue |
|-------|------------------|-------|
| `SessionStateManager` | `ui/coordinators/` | Not a coordinator - manages QSettings persistence |
| `TimeFieldManager` | `ui/coordinators/` | Actually uses QTimer - correct location but naming |
| `DiaryTableManager` | `ui/coordinators/` | Table population logic - should be Connector |
| `DiaryIntegrationManager` | `ui/coordinators/` | Complex diary logic with widget manipulation |
| `SeamlessSourceSwitcher` | `ui/coordinators/` | Data switching with timing - acceptable |

### Architectural Concern: DiaryIntegrationManager

**File:** `sleep_scoring_app/ui/coordinators/diary_integration_manager.py`

This coordinator does more than QThread/QTimer glue:
- Line 98: Accesses `self.main_window.plot_widget` directly
- Line 433-446: Manipulates plot widget methods (`_update_marker_visual_state`, `redraw_markers`)
- Line 163: Shows QMessageBox dialogs

**Recommendation:** Split into:
1. A DiaryConnector (store subscription, widget updates)
2. Keep DiaryIntegrationManager for complex time/marker coordination

---

## Constants and Enums Audit

### StrEnum Coverage (EXCELLENT)

**Directory:** `sleep_scoring_app/core/constants/`

Found comprehensive StrEnums:
- `AlgorithmType` - All algorithm identifiers
- `MarkerType` - Marker types (MAIN_SLEEP, NAP, etc.)
- `MarkerCategory` - SLEEP, NONWEAR
- `DatabaseColumn`, `DatabaseTable` - All DB constants
- `ButtonText`, `ButtonStyle` - UI strings
- 60+ other StrEnums in 4 modules

### Magic Strings Found

Most algorithm/marker strings properly use enums. Found some cases where string literals appear in comments/docstrings (acceptable) and dict keys for serialization (also acceptable).

**Examples of proper StrEnum usage:**
```python
# From ui/store.py:92
current_algorithm: str = AlgorithmType.SADEH_1994_ACTILIFE

# From core/constants/algorithms.py:128-131
SADEH_1994_ORIGINAL = "sadeh_1994_original"
SADEH_1994_ACTILIFE = "sadeh_1994_actilife"
```

**Rating:** 9/10

---

## Dataclass Review

### Frozen Dataclasses (Configs)

Found 43 frozen dataclasses - excellent for immutable configs:

| Category | Examples |
|----------|----------|
| State | `UIState` (store.py:55), `Action` (store.py:216) |
| Config | `AutosaveConfig` (autosave_coordinator.py:57), `SleepPeriodDetectorConfig` |
| Results | `SleepMetrics`, `CalibrationResult`, `NonwearPeriod` |
| Data Types | All 10 backend data types in `core/backends/data_types.py` |

### Non-Frozen Dataclasses (Mutable Domain Objects)

Found 28 non-frozen dataclasses:

| File | Classes | Reason |
|------|---------|--------|
| `core/dataclasses_markers.py` | `SleepPeriod`, `DailySleepMarkers`, `DailyNonwearMarkers` | Need mutation for marker editing |
| `core/dataclasses_daily.py` | `DailyData`, `ParticipantData`, `StudyData` | Container objects with updates |
| `core/dataclasses_config.py` | `AppConfig`, `FileInfo` | Runtime config changes |
| `core/dataclasses_diary.py` | `DiaryEntry`, `DiaryConfig` | Parsed diary data |

**Assessment:** Non-frozen markers are acceptable since they're actively edited. However, `AppConfig` should ideally be immutable with copy-on-change.

### to_dict() Usage

Found 23 `to_dict()` calls - all in appropriate serialization contexts:

| Location | Purpose |
|----------|---------|
| `data/repositories/*.py` | Database persistence |
| `services/marker_service.py` | JSON serialization |
| `core/dataclasses_*.py` | Internal to_dict methods |
| `utils/config.py` | Config file writing |

No instances of unnecessary `to_dict()` for attribute access.

---

## hasattr() Audit

### Total hasattr() Uses: ~100

### All Uses Are Documented

Every `hasattr()` call in the codebase has a `# KEEP:` comment explaining why it's valid:

```python
# Examples from the codebase:
hasattr(loader_class, "SUPPORTED_EXTENSIONS")  # KEEP: Class attribute check
hasattr(data, "lux")  # KEEP: Optional gt3x_rs data field
hasattr(d, "isoformat")  # KEEP: Duck typing for date/datetime objects
hasattr(gc, "get_stats")  # KEEP: Optional gc feature
```

### Categories of Valid hasattr() Uses

| Category | Count | Example |
|----------|-------|---------|
| Optional library features | ~15 | PyQt6 optional methods, gt3x_rs fields |
| Duck typing date/datetime | ~10 | `hasattr(d, "strftime")` |
| Duck typing external objects | ~25 | pyqtgraph line attributes, pandas methods |
| Optional config attributes | ~10 | Config duck typing |
| Cleanup/shutdown checks | ~10 | `hasattr(self, "autosave_coordinator")` |
| Plot/marker attributes | ~30 | `hasattr(line, "period")` |

### Invalid hasattr() Uses Found: 0

All uses are appropriately documented and fall into valid categories.

**Rating:** 10/10 (excellent refactoring work)

---

## Protocol Coverage

### Defined Protocols

**File:** `sleep_scoring_app/ui/protocols.py`

| Protocol | Purpose | Status |
|----------|---------|--------|
| `MarkerLineProtocol` | pyqtgraph line attributes | Well-documented |
| `ConfigWithAlgorithmProtocol` | Algorithm config | Simple, effective |
| `PlotWidgetProtocol` | Plot widget interface | Comprehensive (25+ members) |
| `AnalysisTabProtocol` | Analysis tab interface | Good coverage |
| `DataSettingsTabProtocol` | Data settings interface | Minimal |
| `ExportTabProtocol` | Export tab interface | Minimal |
| `StudySettingsTabProtocol` | Study settings interface | Minimal |
| `MarkerTableProtocol` | Marker table interface | Single member |
| `StateManagerProtocol` | Window state manager | 5 methods |
| `ServiceContainer` | Core services | 12 services |
| `MarkerOperationsInterface` | Marker ops | 11 methods |
| `NavigationInterface` | Navigation | 10 methods |
| `ImportInterface` | Import ops | 7 methods |
| `AppStateInterface` | App state | 12 methods |
| `MainWindowProtocol` | Full main window | Composed protocol |

### Protocol Usage Assessment

**Strengths:**
- `MainWindowProtocol` is properly composed from smaller protocols
- `MarkerLineProtocol` has excellent documentation explaining hasattr() necessity
- All protocols are `@runtime_checkable`

**Gaps:**
- No protocol for individual widgets beyond `PlotWidgetProtocol`
- Coordinator interfaces not defined as protocols

---

## File Organization Issues

### Directory Structure (Good)

```
sleep_scoring_app/
  core/           # Pure domain logic - CLEAN
  data/           # Database layer - CLEAN
  io/             # File loading - CLEAN
  preprocessing/  # Data preprocessing - CLEAN
  services/       # Business logic - CLEAN
  ui/             # PyQt6 UI
    builders/     # UI builders
    commands/     # Command pattern
    coordinators/ # QThread/QTimer coordinators + Managers (MIXED)
    dialogs/      # Dialog windows
    widgets/      # Custom widgets
    workers/      # QThread workers
  utils/          # Mixed pure + Qt utilities (MINOR ISSUE)
```

### Deleted Files Not Cleaned Up (From Git Status)

The following files appear deleted but may have stale references:
- `sleep_scoring_app/services/ui_state_coordinator.py` (moved to ui/coordinators)
- `sleep_scoring_app/ui/constants/ui.py` (content moved to core/constants/ui.py)
- `sleep_scoring_app/ui/managers/` (entire directory deleted, content in coordinators)

### Naming Inconsistencies

| Current Name | Suggested Name | Location |
|--------------|----------------|----------|
| `DiaryTableManager` | `DiaryTableConnector` | ui/coordinators/ |
| `TimeFieldManager` | Keep (uses QTimer) | ui/coordinators/ |
| `SessionStateManager` | Move to `ui/services/` | ui/coordinators/ |
| `FileNavigationManager` | Keep but clarify role | ui/file_navigation.py |

---

## Prioritized Improvement Plan

### 1. CRITICAL - Must Fix Immediately

None identified. The codebase is in good shape.

### 2. HIGH - Should Fix Soon

**H1. Clean up deleted files from git**
- Remove any remaining references to deleted manager files
- Run `git clean` to remove untracked cached files if needed

**H2. Move SessionStateManager**
- Location: `ui/coordinators/session_state_manager.py`
- Issue: Not a coordinator, manages QSettings
- Action: Move to `ui/services/session_state_service.py` or `utils/`

### 3. MEDIUM - Improve When Touching These Files

**M1. Split DiaryIntegrationManager**
- Location: `ui/coordinators/diary_integration_manager.py`
- Issue: Does widget manipulation, not just coordination
- Action: Extract DiaryConnector for state→widget updates

**M2. Rename DiaryTableManager to DiaryTableConnector**
- Location: `ui/coordinators/diary_table_manager.py`
- Issue: Functions as a connector
- Action: Move to `store_connectors.py` or rename in place

**M3. Move Qt utilities from utils/**
- Files: `qt_context_managers.py`, `table_helpers.py`, `thread_safety.py`
- Action: Create `ui/utils/` and move there

**M4. Consider freezing AppConfig**
- Location: `core/dataclasses_config.py`
- Issue: Mutable config allows unexpected changes
- Action: Use `replace()` for updates, make frozen

### 4. LOW - Nice to Have

**L1. Add protocols for coordinators**
- Create `CoordinatorProtocol` for type safety

**L2. Consolidate store_connectors.py**
- File is 2600+ lines
- Consider splitting by domain (navigation, markers, files)

**L3. Add more granular widget protocols**
- Currently only `PlotWidgetProtocol` is detailed
- Add protocols for table widgets, dialogs

**L4. Document architectural decisions**
- Add ADR (Architecture Decision Records) for:
  - Why markers are mutable
  - Redux pattern choice
  - Coordinator vs Connector distinction

---

## Summary Statistics

| Category | Count | Status |
|----------|-------|--------|
| Python files | 140+ | - |
| StrEnums defined | 60+ | Excellent |
| Protocols defined | 15 | Good |
| Frozen dataclasses | 43 | Good |
| Mutable dataclasses | 28 | Acceptable |
| Connectors | 33 | Excellent |
| Coordinators | 6 | Good |
| hasattr() uses | ~100 | All documented |
| Layer violations | 4 (minor) | Low severity |

---

## Conclusion

The sleep-scoring-demo codebase demonstrates strong adherence to its documented architecture. The Redux pattern implementation is particularly well done, with clear separation between store, connectors, and widgets. The recent refactoring has successfully:

1. Eliminated hasattr() abuse (all uses are documented and valid)
2. Established clear layer boundaries (services are headless, core is pure)
3. Created comprehensive protocols for type safety
4. Used StrEnums consistently for constants

The main areas for improvement are organizational (file placement, naming) rather than architectural. The codebase is maintainable and follows its documented patterns with only minor deviations.
