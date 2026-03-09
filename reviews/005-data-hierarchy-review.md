# Data Hierarchy & Domain Model Review

**Date:** 2026-02-02
**Scope:** `sleep_scoring_app/` (desktop PyQt6 app only)
**Rule Reference:** `CLAUDE.md` data hierarchy: `Study -> Participant -> Date -> (Sleep + Nonwear Markers) -> Period -> Metrics`

---

## Summary

The data hierarchy is **largely compliant** with the rules defined in CLAUDE.md. The core dataclass architecture is well-designed: `DailyData` contains both sleep and nonwear markers, metrics are calculated per-period via `SleepPeriod`, and nonwear is treated as a first-class citizen throughout most of the codebase. However, there are several **structural tensions and minor violations** that create fragility. The main issue is a **dual model problem**: `SleepMetrics` (the legacy per-date container) holds top-level metric fields that duplicate what should be exclusively per-period data, and the metrics calculation pipeline uses **raw display strings as dictionary keys** instead of enums, creating a brittle coupling between layers.

---

## Data Hierarchy

### DailyData Structure: PASS

**File:** `sleep_scoring_app/core/dataclasses_daily.py`

`DailyData` correctly contains both sleep and nonwear markers as required:

```python
@dataclass
class DailyData:
    sleep_date: date
    filename: str
    sleep_markers: DailySleepMarkers = field(default_factory=DailySleepMarkers)
    nonwear_markers: DailyNonwearMarkers = field(default_factory=DailyNonwearMarkers)
```

The full hierarchy is properly implemented:
- `StudyData` -> `ParticipantData` -> `DailyData` -> (`DailySleepMarkers` + `DailyNonwearMarkers`) -> `SleepPeriod` / `ManualNonwearPeriod`
- `DailyData.get_complete_sleep_periods()` delegates to `sleep_markers.get_complete_periods()`
- `DailyData.has_nonwear_overlap()` checks `nonwear_markers.get_complete_periods()`
- Serialization (`to_dict`/`from_dict`) handles both marker types symmetrically
- `StudyData.export_sleep_rows()` and `StudyData.export_nonwear_rows()` export separately, as required

### Metrics Attachment: CONDITIONAL PASS (see findings below)

Metrics are calculated per-period in the `MetricsCalculationService.calculate_sleep_metrics_for_period()` method, which takes a `SleepPeriod` as input. The `SleepMetrics.store_period_metrics()` method stores per-period metrics in `_dynamic_fields` keyed by `period_{marker_index}_metrics`. The `to_export_dict_list()` method correctly emits one row per complete period.

**However**, `SleepMetrics` also contains **top-level metric fields** (`total_sleep_time`, `sleep_efficiency`, `waso`, etc.) that represent the *main sleep period's* metrics at the date level. This creates a dual representation that is a source of confusion.

---

## Per-Period Metrics Violations

### Finding 1: MEDIUM -- SleepMetrics has date-level metric fields alongside per-period storage

**File:** `sleep_scoring_app/core/dataclasses_markers.py` (lines 500-707)

The `SleepMetrics` dataclass docstring says "Complete sleep metrics for a single analysis date" (line 502), which contradicts the CLAUDE.md rule that "Metrics are PER-PERIOD, NOT per-date." The class holds both:

1. **Per-period metrics** via `_dynamic_fields` (correct pattern -- `store_period_metrics()` at line 676)
2. **Top-level date-level fields** like `total_sleep_time`, `sleep_efficiency`, `waso`, `awakenings`, etc. (lines 519-530)

In the export pipeline (`export_service.py` lines 665-681), when the main sleep period is detected, these top-level fields are populated:
```python
if period == main_sleep_period:
    metrics.total_sleep_time = period_metrics.get("Total Sleep Time (TST)")
    metrics.sleep_efficiency = period_metrics.get("Efficiency")
    # ... etc
```

This means the top-level fields on `SleepMetrics` are effectively a denormalized copy of the main sleep period's metrics. While not a functional bug (the per-period system works correctly), it creates a **structural ambiguity** where the same data exists in two places.

**Recommendation:** Document clearly that top-level fields on `SleepMetrics` are legacy/convenience fields that always reflect the main sleep period, and that `_dynamic_fields` with `period_{N}_metrics` keys are the canonical per-period metrics. Consider adding a `TODO(refactor)` comment.

### Finding 2: LOW -- MetricsCalculationService returns raw display-string-keyed dictionaries

**File:** `sleep_scoring_app/services/metrics_calculation_service.py` (lines 143-171)

The internal metrics calculation returns a dictionary with human-readable display string keys:
```python
return {
    "Full Participant ID": participant_info.full_id,
    "Total Sleep Time (TST)": round(total_sleep_time, 1),
    "Efficiency": round(efficiency, 2),
    "Wake After Sleep Onset (WASO)": round(waso, 1),
    ...
}
```

These raw strings are then referenced throughout the codebase (`export_service.py` lines 646-681) using `.get("Total Sleep Time (TST)")` instead of an enum. While the `ExportColumn` enum exists with matching values, the *dictionary keys produced by the calculation service* are raw strings, not `ExportColumn` references. This creates a fragile coupling: if any display string changes, multiple `.get()` calls across files would silently return `None`.

**Affected files:**
- `sleep_scoring_app/services/metrics_calculation_service.py` (lines 143-171) -- produces the strings
- `sleep_scoring_app/services/export_service.py` (lines 646-681) -- consumes with raw `.get()` calls
- `sleep_scoring_app/data/repositories/sleep_metrics_repository.py` (lines 524-549) -- consumes with raw `.get()` calls

**Recommendation:** The calculation service should return dictionaries keyed by `ExportColumn` enum values (or a dedicated `MetricKey` enum) instead of display strings. This would make the pipeline type-safe.

### Finding 3: LOW -- SleepMetrics docstring says "single analysis date" instead of acknowledging per-period design

**File:** `sleep_scoring_app/core/dataclasses_markers.py` (line 502)

```python
class SleepMetrics:
    """
    Complete sleep metrics for a single analysis date.
    """
```

This docstring is misleading given the per-period architecture. It should clarify that while the object is keyed by date, the actual metrics are stored per-period in `_dynamic_fields`, and the top-level fields reflect the main sleep period only.

---

## Nonwear First-Class Status

### Overall Assessment: PASS

Nonwear is comprehensively handled throughout the codebase:

1. **Data Model:** `DailyNonwearMarkers` (line 339 of `dataclasses_markers.py`) supports up to 10 manual nonwear periods, with full overlap detection, slot management, and serialization -- on par with `DailySleepMarkers`.

2. **Redux Store:** `UIState` in `store.py` (lines 110-112) carries `current_nonwear_markers` alongside `current_sleep_markers`, with parallel `nonwear_markers_dirty` flag.

3. **Store Actions:** `Actions.nonwear_markers_changed()` and `Actions.markers_loaded(sleep=..., nonwear=...)` handle both marker types symmetrically.

4. **Connectors:** The `MarkerConnector` in `ui/connectors/marker.py` subscribes to both sleep and nonwear state changes. The `SaveStatusConnector` checks both dirty flags.

5. **Autosave:** `AutosaveCoordinator` (lines 163-300 of `autosave_coordinator.py`) handles nonwear autosave alongside sleep autosave.

6. **Visualization:** The plot widget (`activity_plot.py`) has full nonwear marker rendering, placement, deletion, overlap checking, and visibility toggling.

7. **Export:** Both `StudyData.export_nonwear_rows()` and `AppConfig.export_nonwear_separate` support separate nonwear export.

8. **Database:** Dedicated tables exist for nonwear: `NONWEAR_SENSOR_PERIODS`, `CHOI_ALGORITHM_PERIODS`, `MANUAL_NWT_MARKERS`, `DIARY_NONWEAR_PERIODS`.

### Finding 4: LOW -- PlotWidgetProtocol types `daily_nonwear_markers` as `DailySleepMarkers`

**File:** `sleep_scoring_app/ui/protocols.py` (line 70)

```python
class PlotWidgetProtocol(Protocol):
    daily_nonwear_markers: DailySleepMarkers  # WRONG TYPE
```

This should be `DailyNonwearMarkers`, not `DailySleepMarkers`. The actual implementation in `activity_plot.py` correctly uses `DailyNonwearMarkers`, so this is a Protocol definition mismatch only. No runtime impact since Protocol is only used for static type checking, but it is technically incorrect.

### Finding 5: LOW -- `_current_nonwear_marker_being_placed` typed as `SleepPeriod` in Protocol

**File:** `sleep_scoring_app/ui/protocols.py` (line 80)

```python
_current_nonwear_marker_being_placed: SleepPeriod | None
```

The nonwear marker being placed should use `ManualNonwearPeriod`, not `SleepPeriod`. The actual widget likely uses `ManualNonwearPeriod` for the nonwear marker placement workflow.

---

## Filename vs Path Violations

### Overall Assessment: PASS (with defensive coding patterns)

The codebase has **strong defensive guards** against the filename/path confusion issue documented in CLAUDE.md's Known Issues. Multiple layers catch and correct path-to-filename conversion:

1. **Store Reducer** (`store.py` lines 543-554): `FILE_SELECTED` action checks for `/` and `\\` in filename and extracts `Path(filename).name`.

2. **Settings Load** (`store.py` lines 744-751): `STATE_LOADED_FROM_SETTINGS` action applies the same filename extraction.

3. **Data Loading Service** (`data_loading_service.py` lines 116-129, 349-354, 389-397): Three separate methods validate filename format and extract the name if a path is detected.

4. **All database repositories** use `InputValidator.validate_string(filename, min_length=1)` on filename inputs.

### Finding 6: LOW -- Navigation connector still applies Path().name extraction defensively

**File:** `sleep_scoring_app/ui/connectors/navigation.py` (lines 134, 508, 548)

Multiple places in the navigation connector do:
```python
filename = Path(state.current_file).name
```

Since the store reducer already guarantees `current_file` is filename-only, these `Path().name` calls are redundant but harmless. They serve as defensive programming but indicate a lack of trust in the store's invariant. This is a code smell rather than a bug.

### Finding 7: LOW -- main_window.py applies Path().name on selected_file

**File:** `sleep_scoring_app/ui/main_window.py` (lines 706, 2177)

```python
current_filename = Path(self.selected_file).name if self.selected_file else ""
```

Same defensive pattern. Redundant if `selected_file` always comes from the store's `current_file`, which is already sanitized.

### No Violations Found

No instances were found where a full path is incorrectly passed to a database query or stored in `current_file` without sanitization. The defensive guards are comprehensive.

---

## DatabaseColumn Enum Violations

### Overall Assessment: PASS (with notable exceptions in metrics pipeline)

The database layer is well-structured:

1. **BaseRepository** (`data/repositories/base_repository.py`): Defines `VALID_TABLES` and `VALID_COLUMNS` sets exclusively using `DatabaseTable` and `DatabaseColumn` enums.

2. **Schema Manager** (`data/database_schema.py`): Uses `DatabaseTable` and `DatabaseColumn` enums for all table/column references.

3. **All Repositories**: Use `DatabaseColumn` enum for column references in SQL queries. Table names are validated via `_validate_table_name()`.

4. **DiaryEntry** (`dataclasses_diary.py`): `to_database_dict()` and `from_database_dict()` use `DatabaseColumn` enum consistently.

5. **NonwearPeriod** (`dataclasses_markers.py`): `to_dict()` and `from_dict()` use `DatabaseColumn` enum for keys.

### Finding 8: MEDIUM -- MetricsCalculationService uses raw display strings as dictionary keys

**File:** `sleep_scoring_app/services/metrics_calculation_service.py` (lines 143-171)

As noted in Finding 2, the calculation service returns dictionaries with display-string keys like `"Total Sleep Time (TST)"` and `"Efficiency"` instead of using `ExportColumn` or `DatabaseColumn` enum values. While these are not direct database column names (they are export display names), they are used as the internal interchange format between the metrics calculation layer and the export/storage layers.

The consuming code in `export_service.py` and `sleep_metrics_repository.py` then uses `.get("Total Sleep Time (TST)")` which matches the `ExportColumn.TOTAL_SLEEP_TIME` value but does NOT use the enum. This means the coupling is through **string identity** rather than **enum reference**.

### Finding 9: LOW -- `_validate_export_data` uses raw `"filename"` string

**File:** `sleep_scoring_app/data/repositories/sleep_metrics_repository.py` (line 78)

```python
if "filename" not in data or not data["filename"]:
```

This should use `DatabaseColumn.FILENAME` (which equals `"filename"`) for consistency. The value happens to match, so no functional issue, but it breaks the enum-everywhere convention.

---

## Findings Summary Table

| # | Severity | Category | File(s) | Description |
|---|----------|----------|---------|-------------|
| 1 | MEDIUM | Per-Period Metrics | `dataclasses_markers.py` | `SleepMetrics` has both top-level date fields and per-period `_dynamic_fields` -- dual representation |
| 2 | LOW | Per-Period Metrics | `metrics_calculation_service.py`, `export_service.py` | Metrics pipeline uses raw display strings as dict keys instead of enums |
| 3 | LOW | Per-Period Metrics | `dataclasses_markers.py:502` | `SleepMetrics` docstring says "single analysis date" -- misleading |
| 4 | LOW | Nonwear First-Class | `protocols.py:70` | `PlotWidgetProtocol.daily_nonwear_markers` typed as `DailySleepMarkers` instead of `DailyNonwearMarkers` |
| 5 | LOW | Nonwear First-Class | `protocols.py:80` | `_current_nonwear_marker_being_placed` typed as `SleepPeriod` instead of `ManualNonwearPeriod` |
| 6 | LOW | Filename Convention | `navigation.py` (3 places) | Redundant `Path().name` extraction on already-sanitized `current_file` |
| 7 | LOW | Filename Convention | `main_window.py` (2 places) | Redundant `Path().name` extraction on `selected_file` |
| 8 | MEDIUM | DatabaseColumn Enum | `metrics_calculation_service.py` | Raw display strings used as interchange keys between calculation and storage layers |
| 9 | LOW | DatabaseColumn Enum | `sleep_metrics_repository.py:78` | Raw `"filename"` string instead of `DatabaseColumn.FILENAME` |

---

## Verification Checklist

- [x] Read all dataclass definitions in `core/`: `dataclasses.py`, `dataclasses_daily.py`, `dataclasses_markers.py`, `dataclasses_analysis.py`, `dataclasses_config.py`, `dataclasses_diary.py`
- [x] Traced the metrics calculation pipeline end-to-end: `MetricsCalculationService.calculate_sleep_metrics_for_period()` -> raw dict -> `export_service.py` -> `SleepMetrics.store_period_metrics()` -> `to_export_dict_list()`
- [x] Searched for path separator characters in store/database-related code: Store reducer sanitizes, data_loading_service validates, navigation connectors defensively extract
- [x] Checked nonwear handling in parallel with sleep handling: Redux state, autosave, connectors, visualization, export, and database tables all handle both symmetrically
- [x] Checked DatabaseColumn enum usage: Base repository validates all column names; metrics pipeline is the main gap
