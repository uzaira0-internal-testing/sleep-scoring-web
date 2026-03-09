<objective>
Verify that all recent popout-related changes are correct, complete, and introduce no regressions or CLAUDE.md violations. Do NOT run tests - instead, read and deeply analyze the actual source code to validate correctness through code comprehension.
</objective>

<context>
Recent changes were made across two commits to fix popout table windows in a PyQt6 sleep scoring application:

**Commit 1 (refactoring - 29 files):**
- Renamed `ActivityPlotWidget.main_window` to `app_state` and removed `parent_window`
- Replaced hardcoded strings with StrEnum constants (ArrowColorKey, DatabaseColumn, ExportUIGroup, DiaryTableColumn)
- Removed `hasattr()` abuse on typed objects (~25 removals)
- Replaced direct `MainWindow` references with injected callbacks
- Added type annotations to multiple files

**Commit 2 (popout fix - 2 files):**
- `analysis_tab.py`: Added immediate `refresh_onset_popout()`/`refresh_offset_popout()` calls after showing popout windows
- `analysis_tab.py`: Removed `if full_data:` guard in refresh methods so popouts always update (prevents stale data on date switch)
- `plot_overlay_renderer.py`: Added null safety for `len(self._timestamps)` when timestamps could be None

The project follows strict CLAUDE.md guidelines including: layered architecture, Redux pattern, Protocol-based interfaces, StrEnum constants, no hasattr abuse, widgets must be dumb (emit signals only).
</context>

<research>
Thoroughly read and analyze these files to verify correctness. Do NOT just scan - read the actual implementation logic:

**Primary files (changed directly):**
1. `sleep_scoring_app/ui/analysis_tab.py` - Focus on: popout button handlers (lines ~1361-1435), refresh methods, plot_widget construction, DiaryTableColumn import, _algorithm_service property
2. `sleep_scoring_app/ui/widgets/activity_plot.py` - Focus on: constructor (main_window→app_state rename, parent_window removal, new callbacks), _get_axis_y_data_for_sadeh, _get_participant_info_for_file, DatabaseColumn usage
3. `sleep_scoring_app/ui/widgets/plot_overlay_renderer.py` - Focus on: _main_window→_app_state rename, _timestamps null safety, verify _app_state is not used elsewhere (dead assignment)
4. `sleep_scoring_app/ui/widgets/plot_algorithm_manager.py` - Focus on: ArrowColorKey usage in create_sleep_onset/offset_marker, hasattr removal on config, DatabaseColumn usage, type annotations
5. `sleep_scoring_app/ui/coordinators/analysis_dialog_coordinator.py` - Focus on: ArrowColorKey in custom_arrow_colors dict, hasattr removals on pw.marker_lines/nonwear_marker_lines/sleep_rule_markers
6. `sleep_scoring_app/ui/main_window.py` - Focus on: all hasattr removals, export_nonwear_separate fix, _hide_progress_components, cleanup method changes

**Popout data flow files (must trace full path):**
7. `sleep_scoring_app/ui/connectors/table.py` - PopOutConnector and SideTableConnector: verify state change detection covers all cases
8. `sleep_scoring_app/ui/marker_table.py` - _update_popout_windows, _update_onset_popout, get_full_48h_data_for_popout: verify these still work correctly
9. `sleep_scoring_app/ui/widgets/popout_table_window.py` - PopOutTableWindow: verify update_table_data handles empty data gracefully

**Protocol/interface files:**
10. `sleep_scoring_app/ui/protocols.py` - Verify AppStateInterface, PlotWidgetProtocol, MarkerOperationsInterface cover all used attributes/methods
11. `sleep_scoring_app/core/constants/ui.py` - Verify ArrowColorKey, ExportUIGroup, DiaryTableColumn definitions
12. `sleep_scoring_app/core/constants/database.py` - Verify DatabaseColumn.VECTOR_MAGNITUDE value
</research>

<requirements>
Perform these verification checks:

### 1. Popout Data Flow Integrity
Trace the COMPLETE popout update flow for these scenarios and verify each step works:
- **Scenario A**: User clicks popout button for first time → window opens → data loads
- **Scenario B**: User switches date → popout updates with new date's data
- **Scenario C**: User moves a marker → popout reflects new marker position
- **Scenario D**: User right-clicks in popout → marker moves on the plot

For each scenario, trace through every function call and verify:
- No AttributeError possible (all attributes exist and are initialized)
- No stale data (data fetched from correct source at correct time)
- No silent failures (exceptions caught and handled properly)

### 2. StrEnum Backward Compatibility
Verify that ALL StrEnum replacements are safe:
- `ArrowColorKey.ONSET`/`OFFSET` used as dict keys: verify both WRITER and READER use same type
- `DatabaseColumn.VECTOR_MAGNITUDE` comparisons: verify both sides match
- `ExportUIGroup.NONWEAR_MARKERS` comparisons with `col.ui_group`: verify column registry values match
- `DiaryTableColumn` import location change: verify all importers updated

### 3. hasattr Removal Safety
For EACH hasattr removal, verify the attribute is ALWAYS initialized before the code path executes:
- Check `__init__` methods for attribute initialization
- Check for any code path where the object could be in a partially initialized state
- Verify Protocol definitions match the attributes accessed

### 4. MainWindow→app_state Rename
Verify NO external code accesses `plot_widget.main_window` or `plot_widget.parent_window`:
- Search all files in `sleep_scoring_app/` for these patterns
- Check sub-managers (PlotAlgorithmManager, PlotMarkerRenderer, PlotOverlayRenderer, PlotDataManager, PlotStateSerializer) for `parent.main_window` or `parent.parent_window`
- Check connectors that interact with plot_widget

### 5. Callback Injection Correctness
Verify the two new callbacks on ActivityPlotWidget work correctly:
- `get_axis_y_data_for_sadeh`: Compare old path (`self.main_window._get_axis_y_data_for_sadeh()`) with new path (`self._get_axis_y_data_for_sadeh_cb()`)
- `get_selected_file`: Compare old path (`self.parent_window.selected_file`) with new path (`self._get_selected_file()`)
- Verify the callbacks are passed correctly from analysis_tab.py constructor

### 6. CLAUDE.md Compliance
Check these CLAUDE.md rules against all changed files:
- **Widgets are DUMB**: Do any widgets now directly call services or dispatch to store?
- **No hasattr abuse**: Are remaining hasattr uses valid (Optional library features, duck typing)?
- **StrEnum for ALL constants**: Are there any NEW hardcoded strings introduced?
- **Type annotations on ALL function signatures**: Do new/modified functions have proper types?
- **Protocols replace hasattr**: Are Protocol interfaces complete for all accessed attributes?
</requirements>

<output>
Save your findings to: `./reviews/008-popout-fix-verification.md`

Structure the review as:

```markdown
# Popout Fix Verification Review

## Summary
[Overall assessment: PASS/FAIL with brief explanation]

## Popout Data Flow Verification
[Results for each scenario A-D]

## StrEnum Compatibility
[Results for each StrEnum replacement]

## hasattr Removal Safety
[Results for each removal, with file:line references]

## Rename Safety
[Results of external reference search]

## Callback Injection
[Results of callback verification]

## CLAUDE.md Compliance
[Results for each rule checked]

## Issues Found
[Any issues, ordered by severity: CRITICAL > HIGH > MEDIUM > LOW]

## Recommendations
[Any suggested improvements, if applicable]
```
</output>

<constraints>
- Do NOT run any tests, linters, or type checkers - this is purely a code reading exercise
- Do NOT modify any code - only read and report
- Be thorough: read actual implementations, don't just check function signatures
- When tracing data flow, follow the ACTUAL code path, not just what you think it does
- Report findings with specific file:line references
- If you find a potential issue, verify it by reading the surrounding code before reporting it as a bug
</constraints>

<success_criteria>
- All 4 popout scenarios traced completely with no gaps
- Every hasattr removal verified against attribute initialization
- Every StrEnum replacement verified for writer/reader consistency
- No external references to removed attributes found (or all documented)
- Clear PASS/FAIL verdict with evidence
</success_criteria>
