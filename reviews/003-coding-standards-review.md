# Coding Standards Review

**Date:** 2026-02-02
**Scope:** `sleep_scoring_app/` directory only (desktop PyQt6 app)
**Reference:** CLAUDE.md "MANDATORY CODING STANDARDS" section (7 rules)

## Summary

| Rule | Category | Violation Count |
|------|----------|----------------|
| 1 | Hardcoded Strings (StrEnum violations) | 19 |
| 2 | Dict Access Over Dataclass | 1 |
| 3 | Missing Type Annotations | 14 |
| 4 | Non-Frozen Config Dataclasses | 12 |
| 5 | hasattr() Abuse | 0 (all annotated KEEP) |
| 6 | Backwards Compatibility Code | 14 |
| 7 | Per-Date vs Per-Period Metrics | 1 |
| **Total** | | **61** |

---

## Rule 1: Hardcoded Strings (StrEnum violations)

These are raw string literals where existing StrEnums should be used.

### 1.1 Hardcoded `"choi"`, `"sensor"`, `"combined"` strings in NonwearData

**File:** `sleep_scoring_app/core/nonwear_data.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 174 | `source: str = "combined"` | Should define a StrEnum for nonwear source types (e.g., `NonwearSourceFilter.COMBINED`) |
| 176 | `source == "sensor"` | `NonwearSourceFilter.SENSOR` |
| 178 | `source == "choi"` | `NonwearSourceFilter.CHOI` |
| 182 | `source: str = "combined"` | Same StrEnum as above |

No existing StrEnum covers these values. `NonwearDataSource` has `"Choi Algorithm"`, `"Nonwear Sensor"`, etc., but these are different string values. Either a new StrEnum should be created or `NonwearDataSource` should be extended.

### 1.2 Hardcoded `"epoch"` and `"raw"` data source type strings

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/sadeh.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 409 | `return "epoch"` | Should use a StrEnum (e.g., `AlgorithmDataSourceType.EPOCH`). The `data_source_type` property on the protocol returns raw strings. |

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/cole_kripke.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 431 | `return "epoch"` | Same as above. |

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/protocol.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 52 | `"epoch" or "raw"` in docstring/type | The protocol defines `data_source_type -> str` returning `"epoch"` or `"raw"`. Should return a StrEnum. |

### 1.3 Hardcoded `"Axis1"`, `"Vector Magnitude"` column names

These column names have corresponding StrEnums in `DefaultColumn` (`DefaultColumn.AXIS_Y = "Axis1"`, `DefaultColumn.VECTOR_MAGNITUDE = "Vector Magnitude"`), but raw strings are used instead.

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/sadeh.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 130 | `if "Axis1" not in df.columns` | `DefaultColumn.AXIS_Y` |
| 134 | `df["Axis1"]` | `df[DefaultColumn.AXIS_Y]` |

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/cole_kripke.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 142 | `if "Axis1" not in df.columns` | `DefaultColumn.AXIS_Y` |
| 146 | `df["Axis1"]` | `df[DefaultColumn.AXIS_Y]` |

**File:** `sleep_scoring_app/services/batch_scoring_service.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 555 | `"Vector Magnitude" in activity_df.columns` | `DefaultColumn.VECTOR_MAGNITUDE` |
| 556 | `activity_col = "Vector Magnitude"` | `activity_col = DefaultColumn.VECTOR_MAGNITUDE` |
| 557 | `"Axis1" in activity_df.columns` | `DefaultColumn.AXIS_Y` |
| 558 | `activity_col = "Axis1"` | `activity_col = DefaultColumn.AXIS_Y` |

**File:** `sleep_scoring_app/services/epoching_service.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 149 | `epoch_df.columns = ["datetime", "Axis1"]` | Should use appropriate column enums |
| 152 | `epoch_df["Axis1"]` | `DefaultColumn.AXIS_Y` |

### 1.4 Hardcoded `"csv"` data source type

**File:** `sleep_scoring_app/core/dataclasses_config.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 156 | `data_source_type: str = "csv"` | `DataSourceType.CSV` |
| 160 | `data_source_type_id: str = "csv"` | `DataSourceType.CSV` |

### 1.5 Hardcoded `"48h"` view mode default

**File:** `sleep_scoring_app/core/constants/ui.py`

| Line | Hardcoded String | Should Be |
|------|-----------------|-----------|
| 62 | `DEFAULT_VIEW_MODE = "48h"` | `ViewMode.HOURS_48` (which equals `"48h"`) |

---

## Rule 2: Dict Access Over Dataclass

### 2.1 batch_scoring_service returns dict instead of using SleepMetrics dataclass

**File:** `sleep_scoring_app/services/batch_scoring_service.py`

| Lines | Issue |
|-------|-------|
| 515-530 | `calculate_metrics_for_period()` returns a raw `dict` with keys like `"total_sleep_time"`, `"sadeh_onset"`, etc. |
| 626-643 | Same function returns another raw `dict` with metrics. |

The `SleepMetrics` dataclass exists at `core/dataclasses_markers.py:499` and has all these fields. The function should return a `SleepMetrics` instance instead of a dict, then convert to dict only at the serialization boundary.

**Note:** Most other `.to_dict()` calls in the codebase are used for serialization/export (database storage, JSON, CSV), which is the correct usage per the standard. The `batch_scoring_service` case is the one clear violation where a dict is constructed instead of a dataclass and then accessed with string keys.

---

## Rule 3: Missing Type Annotations

### 3.1 Missing return type annotations

**File:** `sleep_scoring_app/utils/participant_extractor.py`

| Line | Function | Missing |
|------|----------|---------|
| 18 | `def _get_global_config()` | Return type annotation missing. Should be `-> AppConfig \| None` |

**File:** `sleep_scoring_app/ui/analysis_tab.py`

| Line | Function | Missing |
|------|----------|---------|
| 1185 | `def _get_algorithm_config(self)` | Return type missing. Should be `-> AppConfig \| None` |
| 1191 | `def _create_sleep_algorithm(self, algorithm_id, config)` | Return type and parameter types missing |
| 1197 | `def _create_sleep_period_detector(self, detector_id)` | Return type and `detector_id` type missing |
| 1203 | `def _create_nonwear_algorithm(self, algorithm_id)` | Return type and `algorithm_id` type missing |
| 1209 | `def _get_default_sleep_algorithm_id(self)` | Return type missing. Should be `-> str` |
| 1215 | `def _get_default_sleep_period_detector_id(self)` | Return type missing. Should be `-> str` |
| 1337 | `def _deserialize_sleep_period(self, period_data: dict \| None)` | Return type missing. Should be `-> SleepPeriod \| None` |

**File:** `sleep_scoring_app/core/pipeline/detector.py`

| Line | Function | Missing |
|------|----------|---------|
| 341 | `def _get_timestamps_from_df(self, df: pd.DataFrame)` | Return type missing. Should be `-> pd.Series \| None` |

**File:** `sleep_scoring_app/services/data_service.py`

| Line | Function | Missing |
|------|----------|---------|
| 109 | `def load_axis_y_aligned(self, filename: str, target_date: datetime, hours: int = 48)` | Return type missing |

**File:** `sleep_scoring_app/services/metrics_calculation_service.py`

| Line | Function | Missing |
|------|----------|---------|
| 177 | `def _find_closest_data_index(self, x_data, timestamp)` | Return type and parameter types all missing |

**File:** `sleep_scoring_app/services/cache_service.py`

| Line | Function | Missing |
|------|----------|---------|
| 160 | `def _plot_widget(self)` | Return type missing |

**File:** `sleep_scoring_app/ui/coordinators/import_ui_coordinator.py`

| Line | Function | Missing |
|------|----------|---------|
| 69 | `def _get_config(self)` | Return type missing. Should be `-> AppConfig` |

**File:** `sleep_scoring_app/ui/coordinators/seamless_source_switcher.py`

| Line | Function | Missing |
|------|----------|---------|
| 320 | `def _deserialize_sleep_period(self, period_data: dict \| None)` | Return type missing. Should be `-> SleepPeriod \| None` |

### 3.2 Missing parameter type annotations

**File:** `sleep_scoring_app/utils/participant_extractor.py`

| Line | Parameter | Missing Type |
|------|-----------|-------------|
| 30 | `config=None` | Should be `config: AppConfig \| None = None` |

**File:** `sleep_scoring_app/ui/main_window.py`

| Line | Parameter | Missing Type |
|------|-----------|-------------|
| 1238 | `onset_data, offset_data` in `update_marker_tables` | Both parameters lack type annotations |

**File:** `sleep_scoring_app/services/metrics_calculation_service.py`

| Line | Parameter | Missing Type |
|------|-----------|-------------|
| 177 | `x_data` | Missing type (should be `list[float]` or similar) |
| 177 | `timestamp` | Missing type (should be `float` or `datetime`) |

**File:** `sleep_scoring_app/utils/profiling.py`

| Line | Parameter | Missing Types |
|------|-----------|-------------|
| 97 | `def wrapper(*args, **kwargs)` | Inner function, but the decorator lacks typed Callable return |

---

## Rule 4: Non-Frozen Config Dataclasses

The rule states: "Always frozen for configs" using `@dataclass(frozen=True)`.

### 4.1 AppConfig is mutable

**File:** `sleep_scoring_app/core/dataclasses_config.py`

| Line | Class | Issue |
|------|-------|-------|
| 54 | `@dataclass class AppConfig` | This is the primary configuration class and is NOT frozen. It is extensively mutated throughout the codebase (e.g., `from_full_dict` sets attributes on an instance). The config builder even notes: "AppConfig is not actually frozen (no @dataclass(frozen=True))". This is a significant violation since `AppConfig` is the central config object. |

### 4.2 ColumnMapping is mutable

**File:** `sleep_scoring_app/core/dataclasses_config.py`

| Line | Class | Issue |
|------|-------|-------|
| 19 | `@dataclass class ColumnMapping` | Configuration dataclass without `frozen=True` |

### 4.3 Domain dataclasses that could be frozen

These dataclasses represent data containers that are modified in place but could use immutable patterns:

**File:** `sleep_scoring_app/core/dataclasses_markers.py`

| Line | Class | Issue |
|------|-------|-------|
| 26 | `@dataclass class SleepPeriod` | Mutable period data -- attributes are mutated after construction |
| 108 | `@dataclass class NonwearPeriod` | Same issue |
| 167 | `@dataclass class DailySleepMarkers` | Mutable markers container |
| 282 | `@dataclass class ManualNonwearPeriod` | Mutable marker |
| 338 | `@dataclass class DailyNonwearMarkers` | Mutable markers container |
| 499 | `@dataclass class SleepMetrics` | Mutable metrics container |

**File:** `sleep_scoring_app/core/dataclasses_diary.py`

| Line | Class | Issue |
|------|-------|-------|
| 16 | `@dataclass class DiaryColumnMapping` | Configuration mapping, should be frozen |
| 116 | `@dataclass class DiaryFileInfo` | File info, could be frozen |
| 152 | `@dataclass class DiaryEntry` | Data entry, could be frozen |
| 299 | `@dataclass class DiaryImportResult` | Result container, could be frozen |

**File:** `sleep_scoring_app/services/export_service.py`

| Line | Class | Issue |
|------|-------|-------|
| 38 | `@dataclass class ExportResult` | Has mutable methods (`add_warning`) so needs mutation -- but it's a result container, not config. Borderline. |

**Note on severity:** The `AppConfig` and `ColumnMapping` violations are clear and high-severity since these are explicitly configuration classes. The marker/diary dataclasses are more nuanced -- they represent mutable domain objects that are modified in place during scoring workflows. The frozen rule strictly applies to "configs", so `AppConfig`, `ColumnMapping`, and `DiaryColumnMapping` are the primary violators.

---

## Rule 5: hasattr() Abuse

All `hasattr()` uses in the codebase have been annotated with `# KEEP:` comments explaining the legitimate reason (duck typing for external libraries, optional PyQt features, pyqtgraph compatibility, Qt cleanup, date/datetime duck typing, etc.).

**No violations found.** Every instance falls into one of the documented valid categories:
- Optional library features (`hasattr(gt3x_rs, ...)`, `hasattr(plot_item, "setUseOpenGL")`)
- Duck typing for external objects (`hasattr(line, "period")` for pyqtgraph lines)
- PyInstaller detection (`hasattr(sys, "_MEIPASS")`)
- Date/datetime duck typing (`hasattr(value, "strftime")`)
- Shutdown cleanup guards (`hasattr(self, "data_settings_tab")`)

---

## Rule 6: Backwards Compatibility Code

The rule states: "DELETE old code completely", "NO deprecated wrappers or legacy fallbacks".

### 6.1 Deprecated legacy wrapper functions (HIGH SEVERITY)

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/sadeh.py`

| Line | Issue |
|------|-------|
| 197-244 | `score_activity()` -- Explicitly marked `DEPRECATED: This function maintains the old list-based API for backwards compatibility.` Should be deleted; callers should use `sadeh_score()` directly. |
| 332 | `score_array` method docstring says "Score array (legacy API)" |
| 437 | `score_array` method described as "Score sleep/wake from array (legacy API)" |

**File:** `sleep_scoring_app/core/algorithms/nonwear/choi.py`

| Line | Issue |
|------|-------|
| 232-258 | `detect_nonwear()` -- Explicitly marked `DEPRECATED: This function maintains the old list-based API for backwards compatibility.` Should be deleted; callers should use `choi_detect_nonwear()` directly. |

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/cole_kripke.py`

| Line | Issue |
|------|-------|
| 347 | `score_array` method docstring says "Score array (legacy API)" |
| 463 | `score_array` method described as "Score sleep/wake from array (legacy API)" |

### 6.2 Deprecated protocol properties

**File:** `sleep_scoring_app/core/algorithms/sleep_wake/protocol.py`

| Line | Issue |
|------|-------|
| 52 | `data_source_type` property marked `DEPRECATED: Use data_requirement property instead`. Should be deleted. |
| 97-112 | Full deprecated property definition with `"epoch"` / `"raw"` raw strings |
| 101 | Comment: `DEPRECATED: Use data_requirement property instead for type-safe enum.` |
| 151-164 | `score_array` method marked as "legacy API" |

### 6.3 Legacy backward compatibility sections

**File:** `sleep_scoring_app/services/diary_service.py`

| Line | Issue |
|------|-------|
| 152 | Section header: `# BACKWARD COMPATIBILITY - Legacy API` |
| 155-158 | `_progress` property marked "for backward compatibility" |

**File:** `sleep_scoring_app/services/unified_data_service.py`

| Line | Issue |
|------|-------|
| 56-57 | `# Legacy compatibility - expose data_manager` with `self.data_manager = self._file_service.data_manager` |

**File:** `sleep_scoring_app/services/file_service.py`

| Line | Issue |
|------|-------|
| 135 | `# Check if cached data is unified (dict) or legacy (tuple)` |
| 150 | `# Legacy tuple format - no unified data available` -- Legacy format handling kept for backwards compatibility |

**File:** `sleep_scoring_app/ui/main_window.py`

| Line | Issue |
|------|-------|
| 1226-1236 | `update_sleep_info()` marked `DEPRECATED: This method is now a no-op.` with comment "kept for protocol compatibility" |
| 1762-1770 | `load_all_saved_markers_on_startup()` is a no-op with comment: "Keeping this method for backwards compatibility with existing callers" |
| 2173 | Comment: `# Auto-save current markers (legacy - will be replaced by autosave coordinator)` |

**File:** `sleep_scoring_app/ui/coordinators/import_ui_coordinator.py`

| Line | Issue |
|------|-------|
| 52 | Parameter described as "optional for backwards compat" |
| 56 | `# Use provided services or fall back to parent (backwards compatibility)` |

**File:** `sleep_scoring_app/core/constants/database.py`

| Line | Issue |
|------|-------|
| 54 | `# Algorithm-specific values (LEGACY - kept for backward compatibility)` |
| 55-56 | `SADEH_ONSET` and `SADEH_OFFSET` columns marked as legacy |

**File:** `sleep_scoring_app/core/constants/io.py`

| Line | Issue |
|------|-------|
| 80 | `# Algorithm results (LEGACY - kept for Sadeh-specific exports)` |

**File:** `sleep_scoring_app/utils/registries/activity_columns.py`

| Line | Issue |
|------|-------|
| 106 | `# Legacy Sadeh columns (kept for backward compatibility)` |
| 117 | `description="Sleep scoring algorithm value at onset marker (legacy column)"` |
| 131 | `description="Sleep scoring algorithm value at offset marker (legacy column)"` |

**File:** `sleep_scoring_app/ui/widgets/plot_marker_renderer.py`

| Line | Issue |
|------|-------|
| 715 | `NOTE: The markers_saved parameter is DEPRECATED and ignored.` |
| 1257 | Same deprecated parameter on another method |

---

## Rule 7: Per-Date vs Per-Period Metrics

### 7.1 SleepMetrics stores metrics at the date level

**File:** `sleep_scoring_app/core/dataclasses_markers.py`

| Line | Issue |
|------|-------|
| 499-553 | `class SleepMetrics` has `analysis_date: str` as a primary field and stores metrics (`total_sleep_time`, `sleep_efficiency`, `waso`, etc.) directly on the class alongside `daily_sleep_markers`. This means metrics are associated with a date+file combination, not with individual sleep periods. |

The class stores `onset_time`/`offset_time` as top-level string fields (lines 516-517), suggesting these are for the "main sleep" period only. While it does contain `daily_sleep_markers: DailySleepMarkers` (which holds per-period data), the metrics themselves (`total_sleep_time`, `waso`, `awakenings`, etc.) are at the date level, not per-period.

The `DailyData` class (line 36 in `dataclasses_daily.py`) correctly documents "CRITICAL: Metrics are stored PER-PERIOD, NOT at the daily level" (line 43), but then the `SleepMetrics` class contradicts this by putting metrics at the date level.

The `batch_scoring_service.py` also returns metrics as flat dicts (lines 626-643) with a single set of metrics per date rather than per-period, reinforcing this pattern.

**Severity:** This is a structural design issue. The `SleepMetrics` class is the primary export/storage format, and it conflates date-level identity with period-level metrics. When multiple sleep periods exist per date (main sleep + naps), only one set of metrics is stored at the `SleepMetrics` level. The `_dynamic_fields` dict (line 553) and `period_metrics_json` database column partially address this, but the primary dataclass structure violates the rule.

---

## Verification Checklist

- [x] Checked every .py file in `sleep_scoring_app/` (via glob pattern returning 140+ files, then grep across all)
- [x] Read `core/constants/` first to understand all StrEnums (`AlgorithmType`, `MarkerType`, `NonwearAlgorithm`, `DatabaseColumn`, `DatabaseTable`, `DefaultColumn`, `ActivityColumn`, `DataSourceType`, `ViewMode`, etc.)
- [x] Distinguished valid vs invalid `hasattr()` uses (all annotated with `# KEEP:` -- no violations)
- [x] Each violation includes specific file path and line number
