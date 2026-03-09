# 010 Coding Standards Review

## Summary
- Total findings: 7
- By severity: CRITICAL 0, HIGH 2, MEDIUM 3, LOW 2
- By category:
  - StrEnums for string identifiers: 3
  - Missing type annotations (recently modified files): 2
  - Frozen dataclasses for configs: 1
  - Metrics per-period (not per-date): 1
  - `hasattr()` abuse: 0
  - Dict access instead of dataclass access: 0

## CRITICAL
No CRITICAL findings.

## HIGH
### [HIGH] Mutable configuration dataclasses violate frozen-config rule
- **File**: sleep_scoring_app/core/dataclasses_config.py:55
- **Rule violated**: Frozen dataclasses for configs
- **Current code**: `@dataclass` on `AppConfig` and `ColumnMapping` (line 20) with in-place mutations.
- **Fix**: Convert config dataclasses to `@dataclass(frozen=True)` and update mutation call sites to construct new instances (builder/replace pattern).

### [HIGH] Main sleep metrics are still persisted as date-level fields
- **File**: sleep_scoring_app/services/export_service.py:669
- **Rule violated**: Metrics are PER-PERIOD, not per-date
- **Current code**: Main-sleep branch copies calculated values into top-level `SleepMetrics` fields (`total_sleep_time`, `sleep_efficiency`, etc.) before persisting.
- **Fix**: Persist metrics at period granularity only (via period-level storage) and avoid using top-level date fields as the canonical sink.

## MEDIUM
### [MEDIUM] Reducer uses magic string default for display column
- **File**: sleep_scoring_app/ui/store.py:704
- **Rule violated**: StrEnums for ALL string constants
- **Current code**: `preferred_display_column=payload.get("column", "axis_y")`
- **Fix**: Use `ActivityDataPreference.AXIS_Y` as the default constant.

### [MEDIUM] Plot connector branches on raw string identifier
- **File**: sleep_scoring_app/ui/connectors/plot.py:188
- **Rule violated**: StrEnums for ALL string constants
- **Current code**: `if preferred == "vector_magnitude" and vector_magnitude:`
- **Fix**: Compare against `ActivityDataPreference.VECTOR_MAGNITUDE`.

### [MEDIUM] File service routes activity columns with raw string values
- **File**: sleep_scoring_app/services/file_service.py:114
- **Rule violated**: StrEnums for ALL string constants
- **Current code**: `preferred_col.value == "vector_magnitude"` / `"axis_x"` / `"axis_z"`.
- **Fix**: Compare enum members directly (`preferred_col is ActivityDataPreference.VECTOR_MAGNITUDE`, etc.) or centralize mapping via enum keys.

## LOW
### [LOW] Modified `activity_plot.py` exposes untyped public signatures
- **File**: sleep_scoring_app/ui/widgets/activity_plot.py:1920
- **Rule violated**: Type annotations on new/modified function signatures
- **Current code**: `_convert_choi_results_to_periods(self)` has no return type; `add_visual_marker(self, timestamp, text, ...)` and `on_plot_clicked(self, event)` have untyped parameters.
- **Fix**: Add explicit parameter/return types for these methods.

### [LOW] Modified `main_window.py` still has untyped parameters in public methods
- **File**: sleep_scoring_app/ui/main_window.py:1243
- **Rule violated**: Type annotations on new/modified function signatures
- **Current code**: `update_marker_tables(self, onset_data, offset_data) -> None`, `on_epoch_length_changed(self, value) -> None`, `on_skip_rows_changed(self, value) -> None` use untyped parameters.
- **Fix**: Add concrete parameter annotations for these signatures.
