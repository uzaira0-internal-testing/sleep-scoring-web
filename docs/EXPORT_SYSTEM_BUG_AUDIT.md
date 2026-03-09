# Export System Bug Audit Report

**Date:** 2026-01-09
**Auditor:** Claude Code (claude.ai/code)
**Scope:** Sleep Scoring Export Pipeline
**Status:** READ-ONLY Investigation

---

## Executive Summary

This audit was triggered by the discovery of two critical bugs in the export pipeline that slipped through existing tests:

1. **Activity Data Caching Bug (Fixed):** Cache loaded activity data only for the first date's time range, causing metrics calculation to fail for other dates
2. **Key Mismatch Bug (Fixed):** Period metrics stored with lowercase keys but export expected ExportColumn keys, causing naps to show main sleep metrics

The investigation identified **8 potential bugs** (2 Critical, 3 High, 2 Medium, 1 Low) and **6 suspicious code patterns** that warrant attention. The existing test suite has significant coverage gaps, particularly around multi-period scenarios and edge cases involving period indexing.

---

## Investigation Scope

### Files Analyzed

| File | Purpose | Lines |
|------|---------|-------|
| `sleep_scoring_app/services/export_service.py` | Core export logic | 1046 |
| `sleep_scoring_app/core/dataclasses_markers.py` | Data classes, export methods | 687 |
| `sleep_scoring_app/core/constants/io.py` | ExportColumn enum | 339 |
| `sleep_scoring_app/data/repositories/sleep_metrics_repository.py` | Database layer | 622 |
| `sleep_scoring_app/data/database.py` | Database manager | 587 |
| `sleep_scoring_app/services/data_service.py` | Data service facade | 247 |
| `sleep_scoring_app/services/metrics_calculation_service.py` | Metrics calculation | 382 |
| `sleep_scoring_app/data/repositories/activity_data_repository.py` | Activity data loading | 275 |
| `tests/unit/services/test_export_service.py` | Export tests | 986 |

### Data Flow Traced

```
User Request (Export)
    |
    v
ExportManager.perform_direct_export()
    |
    v
_ensure_metrics_calculated_for_export()
    |-- DatabaseManager.load_raw_activity_data()
    |-- AlgorithmFactory.create().score_array()
    |-- NonwearAlgorithmFactory.create().detect_mask()
    |-- DataManager.calculate_sleep_metrics_for_period()
    |       |
    |       v
    |   MetricsCalculationService._calculate_sleep_metrics_from_timestamps()
    |
    v
SleepMetrics.store_period_metrics()
    |
    v
SleepMetrics.to_export_dict_list()
    |-- to_export_dict() [base row]
    |-- row.update(_dynamic_fields[f"period_{i}_metrics"])
    |
    v
pandas.DataFrame() -> CSV
```

---

## Confirmed Bugs (Already Fixed)

### Bug A: Activity Data Caching - Date Range Issue

- **Location:** `export_service.py:500-521` (fixed)
- **Description:** The activity data cache was populated with data constrained to the first date's time range. When processing subsequent dates for the same file, the cached data only contained epochs from the first date, causing metrics calculation to fail silently (empty indices array).
- **Impact:** Metrics for all dates except the first would be incorrect or missing
- **Fix Applied:** Load ALL activity data for the entire file without time constraints (`start_time=None, end_time=None`), then filter per-period during iteration

### Bug B: Key Mismatch in Period Metrics Storage

- **Location:** `export_service.py:642-657` (fixed)
- **Description:** `calculate_sleep_metrics_for_period()` returns a dictionary with human-readable keys like `"Total Sleep Time (TST)"`, but `to_export_dict()` returns keys using `ExportColumn` enum values (also human-readable but as StrEnum). When `to_export_dict_list()` called `row.update(period_metrics)`, the keys didn't match because the stored metrics used different key strings.
- **Impact:** Nap periods would show the main sleep metrics instead of their own calculated values
- **Fix Applied:** Transform period metrics to use `ExportColumn` keys before storing via `store_period_metrics()`

---

## Potential Bugs Identified

### Bug 1: Period Index Mismatch Between Storage and Retrieval

- **Severity:** CRITICAL
- **Location:**
  - `dataclasses_markers.py:640-642` (storage lookup)
  - `dataclasses_markers.py:666-676` (retrieval in store_period_metrics)
- **Description:** `to_export_dict_list()` iterates over `complete_periods` using `enumerate(complete_periods, 1)` and creates a key `f"period_{i}_metrics"`. However, `store_period_metrics()` also uses `enumerate(complete_periods, 1)` to find the period index. The problem arises when:
  1. A period is deleted (e.g., period_2), leaving period_1 and period_3
  2. `get_complete_periods()` returns `[period_1, period_3]`
  3. `store_period_metrics()` stores period_3's metrics as `period_2_metrics` (since it's the 2nd in the list)
  4. Later, `to_export_dict_list()` correctly looks up `period_2_metrics` for the 2nd complete period
  5. **BUT** if periods are added/removed between store and export, indices will be wrong
- **Trigger Conditions:**
  - Non-contiguous period slots (period_1, period_3 exist but not period_2)
  - Adding/removing periods between metrics calculation and export
- **Impact:** Wrong metrics associated with wrong periods in export
- **Test Coverage:** No tests for non-contiguous period scenarios
- **Recommended Fix:** Use `period.marker_index` as the key instead of enumeration index, or use timestamp-based keys

### Bug 2: Main Sleep Detection Tie-Breaking is Non-Deterministic

- **Severity:** HIGH
- **Location:** `dataclasses_markers.py:181-186`
- **Description:** `get_main_sleep()` uses `max(complete_periods, key=lambda p: p.duration_seconds or 0)`. When two periods have identical durations, Python's `max()` returns the first one encountered. However, `get_complete_periods()` returns periods in slot order (period_1, period_2, period_3, period_4), not chronological order. This means:
  1. Two naps with identical 90-minute durations
  2. If nap_1 is in slot 2 and nap_2 is in slot 1, slot 1's period becomes "main sleep"
  3. This is counter-intuitive (users expect the longest OR earliest to be main)
- **Trigger Conditions:** Two or more periods with exactly the same duration
- **Impact:** Inconsistent main sleep classification
- **Test Coverage:** `check_duration_tie()` exists but doesn't specify behavior
- **Recommended Fix:** Add secondary sort by `onset_timestamp` (earliest wins tie)

### Bug 3: `_load_period_metrics_for_sleep_metrics` Uses marker_index from DB, Not List Position

- **Severity:** HIGH
- **Location:** `sleep_metrics_repository.py:469-478`
- **Description:** When loading from database, period metrics are stored using `marker_index` from the database record:
  ```python
  marker_index = row[0]  # From DB
  period_key = f"period_{marker_index}_metrics"
  metrics._dynamic_fields[period_key] = period_metrics
  ```
  But `to_export_dict_list()` uses enumeration position:
  ```python
  for i, period in enumerate(complete_periods, 1):
      period_key = f"period_{i}_metrics"  # Position-based
  ```
  If `marker_index` in DB is 1, 3 (skipping 2), but `enumerate` produces 1, 2, then period_3's metrics stored as `period_3_metrics` won't be found when looking for `period_2_metrics`.
- **Trigger Conditions:** Loading saved metrics from database when periods were non-contiguous
- **Impact:** Lost period metrics after database round-trip
- **Test Coverage:** Tests use contiguous periods only
- **Recommended Fix:** Either store using enumeration position consistently, or look up using `marker_index` everywhere

### Bug 4: Silent Failure When Period Not Found in `store_period_metrics`

- **Severity:** HIGH
- **Location:** `dataclasses_markers.py:656-676`
- **Description:** The method searches for the period in `complete_periods` and if not found, falls back to using `period.marker_index` directly. However, if the period genuinely doesn't exist (e.g., was deleted), it silently stores metrics under a potentially wrong key without warning.
- **Trigger Conditions:**
  - Period deleted between calculation and storage
  - Period reference mismatch (different object with same timestamps)
- **Impact:** Metrics stored but never retrieved during export
- **Test Coverage:** Only tests happy path
- **Recommended Fix:** Log warning when falling back to marker_index

### Bug 5: Timestamp Type Inconsistency in Filtering

- **Severity:** MEDIUM
- **Location:** `export_service.py:538-542`
- **Description:** The code filters cached data using:
  ```python
  for i, ts in enumerate(cached_timestamps):
      ts_dt = ts if isinstance(ts, datetime) else datetime.fromtimestamp(ts)
  ```
  But `cached_timestamps` comes from `load_raw_activity_data()` which returns `list[datetime]` according to its type signature. The `isinstance` check suggests uncertainty about the actual type. If the database returns Unix timestamps instead of datetime objects, the conversion `datetime.fromtimestamp(ts)` will fail for timestamps that are already datetime objects.
- **Trigger Conditions:** Inconsistent timestamp types between database and cache
- **Impact:** Incorrect filtering or runtime errors
- **Test Coverage:** Mocked - doesn't test actual type handling
- **Recommended Fix:** Normalize timestamps at data loading boundary

### Bug 6: `_find_closest_data_index` O(n) Linear Search

- **Severity:** MEDIUM
- **Location:** `metrics_calculation_service.py:176-190`
- **Description:** Uses linear search through entire x_data array to find closest timestamp:
  ```python
  for i, data_timestamp in enumerate(x_data):
      diff = abs(data_timestamp - timestamp)
  ```
  Meanwhile, `activity_plot.py:1507-1528` uses binary search (`np.searchsorted`). This inconsistency means the same operation has O(n) vs O(log n) complexity depending on code path.
- **Trigger Conditions:** Large files (millions of epochs)
- **Impact:** Performance degradation during bulk export
- **Test Coverage:** Not performance tested
- **Recommended Fix:** Use binary search consistently

### Bug 7: Nonwear Export Uses Wrong Timestamp Attribute

- **Severity:** LOW
- **Location:** `export_service.py:740-744`
- **Description:** The code accesses `period.start_timestamp` and `period.end_timestamp` for `ManualNonwearPeriod` objects. These are the correct attribute names, but the guard:
  ```python
  if period.start_timestamp is None or period.end_timestamp is None:
      continue
  ```
  is redundant since `get_complete_periods()` already filters for complete periods (both timestamps set). This suggests defensive coding against a type that was previously problematic.
- **Trigger Conditions:** N/A - guard is just defensive
- **Impact:** Minor: Unnecessary check, potential confusion
- **Test Coverage:** Not specifically tested
- **Recommended Fix:** Remove redundant check or add comment explaining why it's needed

### Bug 8: Exception Handler Continues After Critical Failures

- **Severity:** LOW
- **Location:** `export_service.py:684-692`
- **Description:** When metrics calculation fails for a file, the exception is caught, logged, and iteration continues:
  ```python
  except Exception as e:
      warning_msg = f"Error calculating metrics for {metrics.filename}: {e}"
      warnings.append(warning_msg)
      logger.warning(warning_msg)
      continue  # Continue with export even if calculation fails
  ```
  This is intentional (comment says so), but it means partial exports can occur without the user realizing some files failed.
- **Trigger Conditions:** Any exception during metrics calculation
- **Impact:** Partial exports may go unnoticed
- **Test Coverage:** Tests mock `_ensure_metrics_calculated_for_export`
- **Recommended Fix:** Return failure count alongside warnings; UI should show prominently

---

## Suspicious Code Patterns

### Pattern 1: Multiple Enumeration Strategies

The codebase uses three different strategies for iterating over periods:

1. **Position-based (to_export_dict_list):** `enumerate(complete_periods, 1)`
2. **Slot-based (save_sleep_metrics_atomic):** `enumerate([period_1, period_2, period_3, period_4], 1)`
3. **Marker-index-based (store_period_metrics fallback):** `period.marker_index`

This inconsistency creates opportunities for index mismatch bugs.

### Pattern 2: Empty Data Fallback to Empty List

```python
if filename not in activity_data_cache:
    # ...load data...
    if not timestamps or not axis_y_values:
        activity_data_cache[filename] = ([], [], [])
        continue
```

Storing empty lists in cache means subsequent lookups will find "cached" data but it's empty. The code does check `if not cached_timestamps: continue` later, but this pattern could mask data loading failures.

### Pattern 3: Type Annotations vs Runtime Reality

Several methods have type annotations that don't match runtime behavior:
- `load_raw_activity_data` claims to return `tuple[list[datetime], list[float]]`
- But code elsewhere checks `isinstance(ts, datetime)` suggesting uncertainty

### Pattern 4: try/except with Bare continue

Multiple locations catch exceptions and continue without accumulating errors:
```python
except Exception as e:
    logger.warning(...)
    continue
```

This pattern makes it easy to miss systematic failures.

### Pattern 5: Mixing Dictionary Keys and Enum Values

The codebase inconsistently uses:
- Raw strings: `"Total Sleep Time (TST)"`
- ExportColumn enum: `ExportColumn.TOTAL_SLEEP_TIME`
- DatabaseColumn enum: `DatabaseColumn.TOTAL_SLEEP_TIME`

These often have the same string value but using different reference types creates type confusion.

### Pattern 6: Object Identity vs Value Equality

```python
if period == main_sleep_period:
    # Update top-level metrics
```

Using `==` for SleepPeriod comparison relies on default dataclass equality (all fields must match). If timestamps have floating-point precision differences, this comparison could fail unexpectedly.

---

## Test Coverage Gaps

### Scenarios NOT Tested

1. **Non-contiguous periods:** period_1 and period_3 exist, period_2 deleted
2. **Duration ties:** Two periods with identical duration
3. **Large files:** Performance testing with millions of epochs
4. **Database round-trip:** Load -> modify -> save -> load -> export
5. **Concurrent exports:** Two export operations on same data
6. **Unicode filenames:** Participant IDs or filenames with non-ASCII characters
7. **Timezone handling:** Timestamps crossing DST boundaries
8. **Empty activity data:** File imported but no activity records
9. **Period deletion during export:** User modifies data while export running
10. **Memory pressure:** Export with insufficient memory for full cache

### Tests That Mock Critical Components

The export tests extensively mock `_ensure_metrics_calculated_for_export`, which is the function where Bug A and Bug B lived. This means the tests never exercise the actual metrics calculation flow during export.

### Happy Path Bias

Most tests create clean scenarios:
- Contiguous periods (period_1, period_2)
- Complete data
- Successful operations

No chaos testing or fuzzing.

---

## Recommendations

### Immediate Actions (P0)

1. **Fix Bug 1 (Period Index Mismatch):** Use consistent indexing strategy. Recommended: always use `period.marker_index` as the key, not enumeration position.

2. **Add integration test for database round-trip:** Create test that:
   - Creates metrics with multiple periods
   - Saves to database
   - Loads from database
   - Exports to CSV
   - Verifies each period has correct metrics

3. **Remove mocking of `_ensure_metrics_calculated_for_export` in critical paths:** At least one integration test should exercise the full flow.

### Short-Term Actions (P1)

4. **Fix Bug 2 (Tie-Breaking):** Add secondary sort by `onset_timestamp` in `get_main_sleep()`:
   ```python
   return max(complete_periods, key=lambda p: (p.duration_seconds or 0, -(p.onset_timestamp or 0)))
   ```

5. **Add logging for period metrics storage failures:** In `store_period_metrics`, log when falling back to marker_index.

6. **Normalize timestamp types at boundary:** Ensure `load_raw_activity_data` always returns datetime objects, not mixed types.

### Medium-Term Actions (P2)

7. **Standardize enumeration strategy:** Create a `PeriodIterator` that yields `(key, period)` tuples with consistent key generation.

8. **Add performance tests:** Benchmark export with 10-day files (~14,400 epochs) and 30-day files (~43,200 epochs).

9. **Improve error accumulation:** Replace individual warnings with structured error collection that can be displayed to user.

10. **Consider immutable period references:** Once calculated, period metrics should be stored with an immutable key (e.g., `f"{onset_timestamp}_{offset_timestamp}"`).

---

## Appendix: Code Snippets for Reference

### A. Period Index Mismatch Demonstration

```python
# Scenario: period_1 and period_3 exist, period_2 was deleted

# In store_period_metrics:
complete_periods = [period_1, period_3]  # 2 items
for i, p in enumerate(complete_periods, 1):  # i = 1, 2
    if p == period:
        period_key = f"period_{i}_metrics"  # period_3 stored as "period_2_metrics"

# In to_export_dict_list:
for i, period in enumerate(complete_periods, 1):  # i = 1, 2
    period_key = f"period_{i}_metrics"  # Looks for "period_2_metrics" for period_3
    # This works! But only because enumeration is consistent within same process

# BUT in _load_period_metrics_for_sleep_metrics (from DB):
marker_index = row[0]  # From DB: actual marker_index = 3
period_key = f"period_{marker_index}_metrics"  # "period_3_metrics"
# MISMATCH: stored as period_3_metrics but lookup uses period_2_metrics
```

### B. Tie-Breaking Issue

```python
# Two 90-minute naps in non-chronological slot order
period_1 = SleepPeriod(onset=14:00, offset=15:30, marker_index=1)  # Later nap
period_2 = SleepPeriod(onset=10:00, offset=11:30, marker_index=2)  # Earlier nap

complete_periods = [period_1, period_2]  # Slot order

main = max(complete_periods, key=lambda p: p.duration_seconds)
# main = period_1 (first in list with max duration)
# User might expect period_2 (earlier) to be main sleep
```

---

## Verification Checklist

- [x] All core export files read and analyzed
- [x] Data flow traced end-to-end
- [x] 10+ distinct edge cases considered
- [x] Report saved to correct location
- [x] Findings prioritized by severity
