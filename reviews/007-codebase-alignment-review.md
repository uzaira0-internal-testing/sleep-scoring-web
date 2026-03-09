# Codebase Alignment Review

**Date**: 2026-02-06
**Scope**: `sleep_scoring_app/` (desktop PyQt6 app only)
**Auditors**: Claude Code (primary) + OpenAI Codex CLI (independent second reviewer)
**Reference**: `CLAUDE.md` -- All mandatory rules and architecture

## Summary

| Metric | Value |
|--------|-------|
| Total files audited | ~130 .py files across all layers |
| High priority findings | 8 |
| Medium priority findings | 11 |
| Low priority findings | 7 |
| Categories covered | 7 (layer, redux, strenum, hasattr, types, hierarchy, compat) |
| Clean areas | Core layer (no upward deps), Redux state (frozen, no mutation), Services (no Qt imports) |

Both reviewers agree: the **lower layers are clean** -- Core has zero imports from UI or Services, Services have zero Qt imports, and Redux state is properly frozen with no direct mutation. The violations concentrate in the **UI layer** (widgets calling services directly, storing parent references, hasattr abuse) and scattered **StrEnum non-compliance** across multiple layers.

---

## High Priority Findings

### HIGH-1: Widgets directly import and call services (Layer Violation)

**Rule**: "Widgets are DUMB -- They do NOT call services directly"
**Found by**: Both reviewers

Multiple QWidget subclasses import from `sleep_scoring_app.services` at runtime:

| File | Lines | Service imported |
|------|-------|-----------------|
| `ui/analysis_tab.py` | 797, 903, 981-982, 1192-1193, 1198, 1204, 1210, 1216, 1222, 1278-1279 | `config_manager`, `data_service`, `get_algorithm_service` (18 call sites) |
| `ui/export_tab.py` | 127, 130-136, 160, 210-217, 261-301, 336-338 | `config_manager`, `db_manager`, service state (20 call sites) |
| `ui/data_settings_tab.py` | 95, 103, 766, 775, 850, 875, 883, 905, 1160, 1188, 1234 | `config_manager`, `data_service` (11 call sites) |
| `ui/study_settings_tab.py` | 38, 543, 552, 558, 1038, 1041, 1081, 1084, 1339, 1342 | `config_manager`, `db_manager` (10 call sites) |
| `ui/marker_table.py` | 588-593 | `self.services.data_service` |

```python
# ui/analysis_tab.py:1198 -- Widget directly calling service
def _create_sleep_algorithm(self, algorithm_id: str, config: AppConfig | None) -> SleepScoringAlgorithm:
    from sleep_scoring_app.services.algorithm_service import get_algorithm_service
    return get_algorithm_service().create_sleep_algorithm(algorithm_id, config)
```

**Impact**: Widgets are tightly coupled to service implementations. Changes to service APIs break widget code directly. Widgets cannot be tested without service dependencies.

**Fix**: Move service calls into Connectors or Coordinators. Widgets should emit signals; Connectors handle service orchestration.

---

### HIGH-2: ActivityPlotWidget stores and calls MainWindow directly (Layer Violation)

**Rule**: "Widgets do NOT reference MainWindow or parent directly"
**Found by**: Both reviewers

`ui/widgets/activity_plot.py` stores direct references to MainWindow and parent:

```python
# activity_plot.py:129-130
self.main_window = main_window
self.parent_window = parent  # Store reference to parent widget
```

These references are used for direct method calls:

| File:Line | Usage |
|-----------|-------|
| `activity_plot.py:1598` | `self.main_window._get_axis_y_data_for_sadeh()` (calls private method!) |
| `activity_plot.py:1620` | `self.parent_window.selected_file` (accesses parent state) |

```python
# activity_plot.py:1598 -- Widget calling MainWindow private method
return self.main_window._get_axis_y_data_for_sadeh()
```

**Impact**: Bidirectional coupling between widget and MainWindow. The widget depends on MainWindow's internal API (private `_` method). This makes both components untestable in isolation.

**Fix**: Use signals/callbacks or Protocol interfaces. The data should flow through the store or via injected callbacks.

---

### HIGH-3: PlotOverlayRenderer stores MainWindow reference (Layer Violation)

**Rule**: "Widgets do NOT reference MainWindow or parent directly"
**Found by**: Both reviewers

```python
# plot_overlay_renderer.py:47-50
def __init__(self, parent: ActivityPlotWidget, main_window: AppStateInterface) -> None:
    self.parent = parent
    self._main_window = main_window
```

And uses hasattr on the typed parent:

```python
# plot_overlay_renderer.py:253
len(self._timestamps) if hasattr(self.parent, "timestamps") else 0,
```

**Impact**: Sub-component tightly coupled to MainWindow. The `self.parent` is typed as `ActivityPlotWidget` yet hasattr is used to check for known attributes.

**Fix**: Access `self._timestamps` (already defined as a property at line 55) instead of checking `hasattr(self.parent, "timestamps")`.

---

### HIGH-4: Backwards compatibility fallback with hasattr in MainWindow

**Rule**: "NO Backwards Compatibility When Refactoring -- DELETE old code completely"
**Found by**: Claude Code

```python
# main_window.py:1652-1655
if not hasattr(plot, "add_sleep_marker"):
    # Fallback to old method
    plot.sleep_markers = [onset_timestamp]
    plot.redraw_markers()
else:
    plot.add_sleep_marker(onset_timestamp)
```

**Impact**: Dead code path. The "old method" should have been deleted when `add_sleep_marker` was introduced. This hides potential bugs if the old API is accidentally invoked.

**Fix**: Delete the `if not hasattr` branch entirely. The plot widget is typed and `add_sleep_marker` is guaranteed to exist.

---

### HIGH-5: hasattr() abuse on typed objects (14 instances in MainWindow)

**Rule**: "NO hasattr() Abuse -- Protocol guarantees attribute exists"
**Found by**: Both reviewers

`main_window.py` uses `hasattr()` on objects with well-defined types throughout:

| Line(s) | Target | Attribute checked |
|---------|--------|-------------------|
| 1196 | `self.onset_table` | `table_widget` |
| 1202 | `self.offset_table` | `table_widget` |
| 1300 | `self.plot_widget` | `get_selected_marker_period` |
| 1703 | `plot` | `load_daily_nonwear_markers` |
| 1882 | `tab` | `separate_nonwear_file_checkbox` |
| 1894 | `self.export_tab` | `export_output_label` |
| 1941 | `self` | `separate_nonwear_file_checkbox` |
| 2046-2051 | `self`, `tab` | `data_settings_tab`, `activity_progress_label`, `activity_progress_bar` |
| 2058-2062 | `self`, `tab` | `data_settings_tab`, `nwt_progress_label`, `nwt_progress_bar` |
| 2075-2082 | `self` | `analysis_tab`, `cleanup_tab`, `plot_widget`, `cleanup_widget` |
| 2088 | `plot` | `main_48h_axis_y_data` |

**Impact**: Hides initialization order bugs. If an attribute is missing, the code silently does nothing instead of failing fast. Makes debugging significantly harder.

**Fix**: Use Protocols to guarantee attributes exist. For cleanup/progress methods, ensure all attributes are initialized in `__init__` (even as None) so hasattr is unnecessary.

---

### HIGH-6: hasattr() on typed AppConfig in PlotAlgorithmManager

**Rule**: "NO hasattr() Abuse"
**Found by**: Both reviewers

```python
# plot_algorithm_manager.py:101
if config and hasattr(config, "sleep_algorithm_id") and config.sleep_algorithm_id:

# plot_algorithm_manager.py:148
if config and hasattr(config, "onset_offset_rule_id") and config.onset_offset_rule_id:
```

`AppConfig` is a well-defined dataclass at `core/dataclasses_config.py:56`. Both `sleep_algorithm_id` and `onset_offset_rule_id` are declared attributes. The hasattr check is redundant.

**Fix**: Remove hasattr checks. Use `if config and config.sleep_algorithm_id:` directly.

---

### HIGH-7: hasattr() abuse in analysis_dialog_coordinator

**Rule**: "NO hasattr() Abuse"
**Found by**: Claude Code

```python
# analysis_dialog_coordinator.py:503
if hasattr(pw, "marker_lines") and pw.marker_lines:
# analysis_dialog_coordinator.py:507
if hasattr(pw, "marker_renderer") and hasattr(pw.marker_renderer, "nonwear_marker_lines"):
# analysis_dialog_coordinator.py:517
if hasattr(pw, "sleep_rule_markers") and pw.sleep_rule_markers:
# analysis_dialog_coordinator.py:543
if hasattr(pw, "plot_nonwear_periods") and hasattr(pw, "nonwear_regions"):
```

`pw` is the plot widget (typed). All checked attributes (`marker_lines`, `marker_renderer`, `sleep_rule_markers`, `nonwear_regions`) are known attributes of `ActivityPlotWidget`.

**Fix**: Remove all hasattr checks. Access attributes directly.

---

### HIGH-8: "VECTOR_MAGNITUDE" hardcoded string comparisons

**Rule**: "StrEnums for ALL String Constants"
**Found by**: Both reviewers

```python
# activity_plot.py:556
if activity_column_type == "VECTOR_MAGNITUDE":

# activity_plot.py:866
if new_column_type == "VECTOR_MAGNITUDE":

# plot_algorithm_manager.py:244
data_type = "vm" if column_type == "VECTOR_MAGNITUDE" else "axis_y" if column_type else "unknown"
```

`ActivityDataPreference` StrEnum exists in `core/constants/` with `VECTOR_MAGNITUDE` as a member. These string comparisons should use the enum.

**Fix**: Replace `"VECTOR_MAGNITUDE"` with `ActivityDataPreference.VECTOR_MAGNITUDE` throughout.

---

## Medium Priority Findings

### MED-1: "onset"/"offset" dict keys instead of StrEnum

**Rule**: "StrEnums for ALL String Constants"
**Found by**: Claude Code

```python
# plot_algorithm_manager.py:552
onset_arrow_color = custom_arrow_colors.get("onset", "#0066CC")
# plot_algorithm_manager.py:595
offset_arrow_color = custom_arrow_colors.get("offset", "#FFA500")

# analysis_dialog_coordinator.py:511-513
pw.custom_arrow_colors = {
    "onset": onset_arrow_color,
    "offset": offset_arrow_color,
}
```

`SleepMarkerEndpoint` StrEnum exists in `core/constants/` (or should be created). These dict keys should use it.

**Fix**: Use `SleepMarkerEndpoint.ONSET` and `SleepMarkerEndpoint.OFFSET` as dict keys.

---

### MED-2: "Nonwear Markers" hardcoded string in export_dialog

**Rule**: "StrEnums for ALL String Constants"
**Found by**: Claude Code

```python
# export_dialog.py:166
if col.export_column and col.ui_group != "Nonwear Markers" and not col.is_always_exported:
# export_dialog.py:210
if col.export_column and col.ui_group == "Nonwear Markers":
# export_dialog.py:282
if col.is_always_exported and col.ui_group == "Nonwear Markers" and col.export_column ...
```

The string `"Nonwear Markers"` is used 3 times. Should be a StrEnum member.

**Fix**: Create or use an existing `UIGroup` StrEnum with `NONWEAR_MARKERS = "Nonwear Markers"`.

---

### MED-3: Hardcoded column name strings in batch_scoring_service

**Rule**: "StrEnums for ALL String Constants"
**Found by**: Claude Code

```python
# batch_scoring_service.py:391-392
onset_columns = ["sleep_onset_time", "bedtime", "in_bed_time", "onset"]
offset_columns = ["sleep_offset_time", "wake_time", "out_of_bed_time", "offset"]
```

These are diary column names that exist as `DiaryColumn` StrEnum members.

**Fix**: Use `DiaryColumn` enum values instead of hardcoded strings.

---

### MED-4: Hardcoded config key strings in ColumnMapping.to_dict()

**Rule**: "StrEnums for ALL String Constants"
**Found by**: Claude Code

```python
# dataclasses_config.py:43
result["datetime_column"] = self.datetime_column
# dataclasses_config.py:47
result["axis_x_column"] = self.axis_x_column
# dataclasses_config.py:49
result["axis_z_column"] = self.axis_z_column
# dataclasses_config.py:51
result["vector_magnitude_column"] = self.vector_magnitude_column
```

Lines 39-41 correctly use `ConfigKey.DATE_COLUMN`, `ConfigKey.TIME_COLUMN`, and `ConfigKey.ACTIVITY_COLUMN`. The remaining 4 keys are hardcoded strings instead of using ConfigKey enum.

**Fix**: Add missing members to `ConfigKey` StrEnum and use them consistently.

---

### MED-5: DiaryTableColumn StrEnum defined in wrong layer

**Rule**: "All StrEnums in core/constants/"
**Found by**: Claude Code

```python
# ui/coordinators/diary_table_connector.py:22-46
class DiaryTableColumn(StrEnum):
    DATE = "date"
    BEDTIME = "bedtime"
    # ... 19 more members
```

This StrEnum is defined in a UI coordinator file instead of `core/constants/`.

**Fix**: Move `DiaryTableColumn` to `core/constants/diary.py` or similar.

---

### MED-6: Missing return type annotations on 10+ properties

**Rule**: "Type Annotations on ALL Function Signatures"
**Found by**: Both reviewers

`plot_algorithm_manager.py` has numerous properties without return type annotations:

```python
# plot_algorithm_manager.py:51-66
@property
def timestamps(self):        # Missing -> list | None
    return self.parent.timestamps

@property
def x_data(self):             # Missing -> list | None
    return self.parent.x_data

@property
def activity_data(self):      # Missing -> list | None
    return getattr(self.parent, "activity_data", None)

@property
def sadeh_results(self):      # Missing -> list | None
    return getattr(self.parent, "sadeh_results", None)
```

Additional properties at lines 178, 183, 188, 193, 198, 203, 208, 213, 218 also lack return types.

**Fix**: Add return type annotations to all property definitions.

---

### MED-11: Widespread missing type annotations (~100+ functions)

**Rule**: "Type Annotations on ALL Function Signatures"
**Found by**: Codex CLI (comprehensive scan)

Codex identified ~100+ functions across the codebase missing argument or return type annotations. The heaviest offenders by file:

| File | Missing annotations |
|------|-------------------|
| `ui/widgets/activity_plot.py` | 15+ (init args, event handlers, plot methods) |
| `ui/widgets/plot_algorithm_manager.py` | 12+ (properties, plot methods) |
| `ui/widgets/plot_overlay_renderer.py` | 8+ (render methods, callbacks) |
| `ui/main_window.py` | 12+ (event handlers, progress callbacks) |
| `services/data_service.py` | 6+ (load/query methods with complex params) |
| `services/metrics_calculation_service.py` | 4+ (calculation methods) |
| `ui/coordinators/import_ui_coordinator.py` | 4+ (progress callbacks) |
| `ui/config_dialog.py` | 3+ (init parent, apply methods) |

Notable patterns:
- Event handlers consistently miss `event` parameter types
- `parent` parameters on `__init__` methods frequently untyped
- Service methods with multiple data params (lists, DataFrames) untyped
- `*args, **kwargs` on NoScrollWidgets subclasses all untyped

**Fix**: Prioritize services and core first (API surface), then UI layer. Consider running `basedpyright` to get a complete list.

---

### MED-7: Missing parameter type annotation in diary_table_connector

**Rule**: "Type Annotations on ALL Function Signatures"
**Found by**: Both reviewers

```python
# diary_table_connector.py:53
def __init__(self, store: "UIStore", data_service: "UnifiedDataProtocol",
             diary_coordinator: "DiaryIntegrationCoordinator | None",
             diary_table_widget) -> None:  # <-- missing type
```

**Fix**: Add type annotation for `diary_table_widget` parameter (likely `QTableWidget`).

---

### MED-8: Missing return type on services/__init__.py __getattr__

**Rule**: "Type Annotations on ALL Function Signatures"
**Found by**: Codex CLI

```python
# services/__init__.py:31
def __getattr__(name: str):  # Missing -> type[...]
    """Lazy import to avoid circular dependencies."""
```

**Fix**: Add `-> type` or `-> Any` return type annotation.

---

### MED-9: Missing return type on algorithm_compatibility_ui

**Rule**: "Type Annotations on ALL Function Signatures"
**Found by**: Claude Code

```python
# algorithm_compatibility_ui.py:179
def get_current_compatibility_result(self):  # Missing return type
```

**Fix**: Add return type annotation.

---

### MED-10: hasattr() on NonwearPeriod for always-present attributes

**Rule**: "NO hasattr() Abuse"
**Found by**: Claude Code

```python
# core/nonwear_data.py:147
if hasattr(period, "start_index") and hasattr(period, "end_index"):
    start_idx = period.start_index
    end_idx = period.end_index
    if start_idx is not None and end_idx is not None:
```

`NonwearPeriod` always has `start_index` and `end_index` attributes (they may be `None`). The hasattr check is redundant -- the `is not None` check on line 150 is the correct guard.

**Fix**: Remove hasattr checks. Keep only `if period.start_index is not None and period.end_index is not None:`.

---

## Low Priority Findings

### LOW-1: Backward compatibility wrapper functions (dead code)

**Rule**: "NO Backwards Compatibility When Refactoring -- DELETE old code"
**Found by**: Claude Code

```python
# diary_mapper.py:966-991
# Convenience functions for backward compatibility and ease of use

def parse_comma_separated_columns(column_names: str | None) -> list[str]:
    """Convenience function for parsing comma-separated columns."""
    return DiaryMappingHelpers.parse_comma_separated_columns(column_names)

def extract_multiple_values_from_columns(...) -> str | None:
    return DiaryMappingHelpers.extract_multiple_values_from_columns(...)

def parse_time_string(time_str: str | None) -> str | None:
    return DiaryMappingHelpers.parse_time_string(time_str)

def parse_date_string(date_str: str | None) -> str | None:
    return DiaryMappingHelpers.parse_date_string(date_str)

def is_auto_calculated_column(...) -> bool:
    return DiaryMappingHelpers.is_auto_calculated_column(...)
```

Five wrapper functions that only delegate to `DiaryMappingHelpers` static methods. If no external consumers use these, they should be deleted.

**Fix**: Grep for usages. If only internal, delete and update imports to use `DiaryMappingHelpers.*` directly.

---

### LOW-2: Legacy short-name mapping in config.py

**Rule**: "NO Backwards Compatibility When Refactoring"
**Found by**: Claude Code

```python
# ui/utils/config.py:451-458
attr_mapping = {
    # Short names (legacy)
    "participant_id_patterns": "study_participant_id_patterns",
    "timepoint_pattern": "study_timepoint_pattern",
    "group_pattern": "study_group_pattern",
    "valid_groups": "study_valid_groups",
    "valid_timepoints": "study_valid_timepoints",
    "default_group": "study_default_group",
    "default_timepoint": "study_default_timepoint",
    "unknown_value": "study_unknown_value",
    # Redux field names (full names)
    ...
}
```

The "short names (legacy)" entries map old names to current names. If nothing uses the short names, they should be removed.

**Fix**: Grep for short name usage. If unused, delete the legacy entries.

---

### LOW-3: gt3x_rs_loader.py backward compatibility class

**Rule**: "NO Backwards Compatibility When Refactoring"
**Found by**: Claude Code

```python
# io/sources/gt3x_rs_loader.py:82-85
# Note:
#     This loader directly uses gt3x-rs library and does not use the backend abstraction.
#     It exists for backward compatibility. New code should use GT3XDataSourceLoader with
#     a backend parameter instead.
```

The entire `GT3XRsLoader` class is kept for backward compatibility when `GT3XDataSourceLoader` is the preferred approach.

**Fix**: Grep for usage. If only used internally, migrate callers to `GT3XDataSourceLoader` and delete `GT3XRsLoader`.

---

### LOW-4: Legacy autosave comment in closeEvent

**Rule**: "NO Backwards Compatibility When Refactoring"
**Found by**: Claude Code

```python
# main_window.py:2109
# Auto-save current markers (legacy - will be replaced by autosave coordinator)
self.auto_save_current_markers()
```

The comment explicitly acknowledges this is legacy code awaiting replacement.

**Fix**: Complete the autosave coordinator migration and remove `auto_save_current_markers()`.

---

### LOW-5: Hardcoded strings in core algorithm files

**Rule**: "StrEnums for ALL String Constants"
**Found by**: Codex CLI

Various algorithm files in `core/` contain hardcoded strings that match StrEnum values:

- `"axis_y"` and `"epoch_based"` used as identifiers
- `"actilife"` used as format identifier
- `"S"`, `"W"`, `"Sleep"` used as sleep/wake labels in algorithm output

These are domain-level string constants that should use the corresponding StrEnums (e.g., `ActivityDataPreference`, `AlgorithmType`, `SleepLabel`).

**Fix**: Audit each usage and replace with appropriate StrEnum member.

---

### LOW-6: Missing return type on _convert_choi_results_to_periods

**Rule**: "Type Annotations on ALL Function Signatures"
**Found by**: Claude Code

```python
# activity_plot.py:1926
def _convert_choi_results_to_periods(self):  # Missing return type
```

**Fix**: Add return type annotation (likely `-> list[NonwearPeriod]`).

---

### LOW-7: Missing parameter types on add_visual_marker

**Rule**: "Type Annotations on ALL Function Signatures"
**Found by**: Claude Code

```python
# activity_plot.py:1930
def add_visual_marker(self, ...):  # Multiple params missing types
```

**Fix**: Add type annotations for all parameters.

---

## Verified Clean Areas

Both reviewers confirmed these areas are compliant:

| Area | Status | Verification |
|------|--------|-------------|
| **Core layer isolation** | PASS | Zero imports from `ui/` or `services/` (Grep verified) |
| **Services headless** | PASS | Zero `PyQt6` imports in `services/` (Grep verified) |
| **Redux state immutability** | PASS | `UIState` is `frozen=True`; `_state` only set in `__init__` and `dispatch` |
| **No direct state mutation** | PASS | Zero instances of `store.state.X = Y` |
| **Widgets don't dispatch directly** | PASS | No `store.dispatch()` calls in `ui/widgets/` directory |
| **Data hierarchy** | PASS | Metrics are per-period (via `SleepPeriod.metrics`), not per-date |
| **Frozen configs** | PASS | `AlgorithmConfig` and similar are `frozen=True` |

---

## Reviewer Disagreements

None significant. Codex CLI findings were a subset of Claude Code findings. The only notable difference:

- **Codex flagged** `self.parent` references in PlotAlgorithmManager/PlotDataManager as potential violations. **Claude Code clarified** these are **composition pattern references** (the sub-component referencing its owning `ActivityPlotWidget`), not `QWidget.parent()` calls, and are architecturally acceptable.

- **Codex flagged** `hasattr(line, "period")` patterns in marker_interaction_handler.py. **Claude Code verified** these are explicitly documented as acceptable in `protocols.py:53` because incomplete markers don't have the monkey-patched `period` attribute.

---

## Recommendations (Ordered by Priority)

1. **Extract service calls from widgets** (HIGH-1): Create dedicated Coordinators or Connectors for `analysis_tab.py`, `data_settings_tab.py`, `study_settings_tab.py`, `export_tab.py`, and `marker_table.py`. This is the single largest architectural violation.

2. **Remove MainWindow references from widgets** (HIGH-2, HIGH-3): Replace `self.main_window` and `self.parent_window` in `activity_plot.py` and `plot_overlay_renderer.py` with signal/callback patterns or Protocol-based injection.

3. **Eliminate all hasattr() on typed objects** (HIGH-5, HIGH-6, HIGH-7): ~25 instances across `main_window.py`, `plot_algorithm_manager.py`, `analysis_dialog_coordinator.py`, and `nonwear_data.py`. Replace with direct attribute access, Protocols, or proper None checks.

4. **Delete backwards compatibility code** (HIGH-4, LOW-1, LOW-2, LOW-3, LOW-4): Remove the hasattr fallback in main_window:1652, wrapper functions in diary_mapper:966-991, legacy short names in config:451-458, and GT3XRsLoader backward compat class.

5. **Replace all hardcoded strings with StrEnums** (HIGH-8, MED-1 through MED-5, LOW-5): Systematic sweep for `"VECTOR_MAGNITUDE"`, `"onset"/"offset"`, `"Nonwear Markers"`, config keys, and algorithm labels. Create missing StrEnum members where needed.

6. **Add missing type annotations** (MED-6 through MED-9, MED-11, LOW-6, LOW-7): ~100+ functions affected. Focus on services layer first (API surface), then plot_algorithm_manager.py properties (10+ missing), then UI event handlers. Run `basedpyright` for a complete inventory.

7. **Move DiaryTableColumn to core/constants/** (MED-5): Small refactor with high signal -- StrEnums should live in the core constants layer per CLAUDE.md.

---

## Methodology

**Claude Code analysis**: Systematic Grep/Glob/Read across all `.py` files in `sleep_scoring_app/`, checking each of the 7 categories against CLAUDE.md rules. Every finding was verified by reading the actual source at the reported line.

**Codex CLI analysis**: Three independent commands (gpt-5.2-codex, read-only sandbox, high reasoning effort) targeting (1) general codebase review across all 4 focus areas with line-by-line detail (~112k tokens), (2) widget-specific layer violations with source inspection (~97k tokens), and (3) core layer isolation with comprehensive string literal matching (~144k tokens). Results were deduplicated against Claude Code findings.

**Deduplication**: Findings reported by both reviewers are noted as "Found by: Both reviewers". Unique findings are attributed to their discoverer. No phantom findings were included -- every line reference was verified against actual source code.
