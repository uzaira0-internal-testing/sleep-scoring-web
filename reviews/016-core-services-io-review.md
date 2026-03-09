# Review 016: Core / Services / IO / Data Layer Review

**Date:** 2026-02-25
**Scope:** `sleep_scoring_app/core/`, `sleep_scoring_app/services/`, `sleep_scoring_app/io/`, `sleep_scoring_app/data/`
**Focus:** Bugs, logic errors, data corruption risks, silent failures, layer violations
**Severity levels:** CRITICAL (data corruption/loss), HIGH (wrong results/crashes)

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 2     |
| HIGH     | 5     |

Layer violations: None found. Core has no UI/services imports. Services have no Qt imports.

---

## CRITICAL Issues

### C1. Choi Algorithm Ignores Instance Parameters

**File:** `sleep_scoring_app/core/algorithms/nonwear/choi.py`
**Lines:** 357, 366, 371 (in `ChoiAlgorithm.detect()`)

**Description:** The `ChoiAlgorithm` class accepts configurable parameters (`min_period_length`, `spike_tolerance`, `small_window_length`) via `__init__()` and `set_parameters()`, stores them on `self`, and even validates non-standard values with a warning. However, the `detect()` method uses module-level constants (`MIN_PERIOD_LENGTH=90`, `SPIKE_TOLERANCE=2`, `WINDOW_SIZE=30`) instead of the instance variables. This makes parameter customization silently non-functional.

**Evidence:**
```python
# __init__ stores instance variables (line 266-269):
self._min_period_length = min_period_length
self._spike_tolerance = spike_tolerance
self._small_window_length = small_window_length

# But detect() uses MODULE constants (lines 357, 366, 371):
window_start = max(0, nonwear_continuation - WINDOW_SIZE)        # Should be self._small_window_length
window_end = min(len(counts), nonwear_continuation + WINDOW_SIZE) # Should be self._small_window_length
if nonzero_count > SPIKE_TOLERANCE:                               # Should be self._spike_tolerance
    break
if end_idx - start_idx + 1 >= MIN_PERIOD_LENGTH:                 # Should be self._min_period_length
```

**Impact:** Any caller using non-default Choi parameters gets silently incorrect results. The algorithm always uses the paper defaults regardless of what was configured. The `get_parameters()` and `set_parameters()` methods give the illusion of configurability. If this algorithm is ever used in research with customized parameters, the results would be wrong.

**Fix:** Replace `WINDOW_SIZE`, `SPIKE_TOLERANCE`, and `MIN_PERIOD_LENGTH` in `detect()` with `self._small_window_length`, `self._spike_tolerance`, and `self._min_period_length` respectively.

---

### C2. WASO Calculation Uses Mismatched Counting Scopes

**File:** `sleep_scoring_app/services/metrics_calculation_service.py`
**Lines:** 58-109

**Description:** The WASO (Wake After Sleep Onset) calculation has an inconsistency between how `sleep_minutes` and `sleep_period_length` are counted, which can produce incorrect WASO values.

- `sleep_minutes` counts ALL sleep epochs in `range(onset_idx, offset_idx)` -- this is the onset-to-offset range (exclusive upper bound), which includes sleep epochs BEFORE `first_sleep_idx` and AFTER `last_sleep_idx`.
- `sleep_period_length` is calculated as `last_sleep_idx - first_sleep_idx + 1` -- this is the first-sleep-to-last-sleep range (inclusive).
- `waso = sleep_period_length - sleep_minutes`

Since `sleep_minutes` can include sleep epochs outside the `[first_sleep_idx, last_sleep_idx]` range (e.g., an isolated sleep epoch near `onset_idx` that precedes several wake epochs before the main sleep block), `sleep_minutes` can be LARGER than the actual sleep count within `[first_sleep_idx, last_sleep_idx]`. This makes `waso` underestimated or even negative.

**Evidence:**
```python
# sleep_minutes counts in onset_idx..offset_idx range (line 72):
for i in range(onset_idx, min(offset_idx, len(sadeh_results))):
    if sadeh_results[i] == 1:  # Sleep
        sleep_minutes += 1

# But total_sleep_time counts in first_sleep_idx..last_sleep_idx range (line 102):
total_sleep_time = sum(1 for i in range(first_sleep_idx, last_sleep_idx + 1) if sadeh_results[i] == 1)

# WASO uses sleep_period_length (first-to-last) minus sleep_minutes (onset-to-offset):
sleep_period_length = last_sleep_idx - first_sleep_idx + 1
waso = sleep_period_length - sleep_minutes  # Mismatched scopes!
```

**Impact:** WASO values exported to CSV or shown in the UI may be incorrect. For sleep periods where there is early/late isolated sleep near the onset/offset boundaries (outside the first-to-last range), WASO will be underestimated. Negative WASO values are possible in edge cases, which would be clearly invalid research data.

**Fix:** WASO should be `sleep_period_length - total_sleep_time` since both use the same `[first_sleep_idx, last_sleep_idx]` range. Alternatively, `sleep_minutes` should only count epochs within `[first_sleep_idx, last_sleep_idx]`.

---

## HIGH Issues

### H1. NonwearData Computes Overlap Check but Never Uses It for Filtering

**File:** `sleep_scoring_app/core/nonwear_data.py`
**Lines:** 85-102

**Description:** The `create_for_activity_view()` class method iterates over `raw_sensor_periods`, computes whether each period overlaps with the activity view timeframe (line 93), logs the result (line 94), but then unconditionally appends EVERY period to `sensor_periods` (line 96). The log message on line 102 says "removed filtering" confirming this was intentionally disabled, but the code still computes the overlap, which is dead code that misleads readers into thinking filtering occurs.

**Evidence:**
```python
overlaps = activity_view.timeframe_filter(period_start, period_end)
logger.debug("Period %d overlaps with activity timeframe: %s", i, overlaps)

sensor_periods.append(period)  # Appended regardless of overlaps value
```

**Impact:** Non-overlapping sensor nonwear periods are included in the mask computation. When `_periods_to_mask()` runs on periods outside the activity timeframe, it wastes computation (timestamp-by-timestamp comparison). More importantly, if a sensor period has no index data (`start_index`/`end_index` are None) and falls completely outside the activity view, it still iterates all timestamps for nothing. If the period timestamps accidentally overlap due to timezone issues, incorrect mask values could result.

**Fix:** Either re-enable the overlap filter (`if overlaps: sensor_periods.append(period)`) or remove the dead overlap computation code entirely.

---

### H2. Migration Failure Records Committed Before Re-raise Poisons Version Tracking

**File:** `sleep_scoring_app/data/migrations.py`
**Lines:** 194-207

**Description:** When a migration fails, `run_migration()` records a failure row in `schema_version` with `success=0` and `commits` it, then re-raises the exception. The problem is that `get_current_version()` only looks at `MAX(version) WHERE success = 1`, but `get_pending_migrations()` filters by `version > current`. If the failed migration's version is inserted into `schema_version` with `success=0`, subsequent calls to `migrate_to_latest()` will still consider it "pending" (since its version > current) and attempt to re-run it. This is correct behavior.

However, the real issue is that the failure record is committed **without rolling back the partial DDL changes** from `migration.up(conn)`. SQLite auto-commits DDL statements (like `CREATE TABLE`, `ALTER TABLE`), meaning some schema changes from a partially-executed migration may persist while the version tracking says it failed. On the next run, the migration will be re-attempted against a partially-migrated schema, which may crash with "table already exists" or "column already exists" errors, making the database unrecoverable without manual intervention.

**Evidence:**
```python
try:
    migration.up(conn)       # May partially execute DDL before failure
    # ... record success ...
    conn.commit()
except Exception as e:
    # DDL changes from migration.up() are NOT rolled back
    conn.execute("INSERT INTO schema_version ...")  # Records failure
    conn.commit()                                    # Commits failure record
    raise                                            # Re-raises
```

**Impact:** A partially-failed migration can leave the database in an inconsistent state where the schema is partially modified but the version tracking says it failed. Re-running migrations will attempt the same DDL again, potentially crashing. Recovery requires manual database repair.

**Fix:** Wrap `migration.up(conn)` in a savepoint so that DDL can be rolled back on failure. Or use `IF NOT EXISTS` guards in all migration DDL statements to make them idempotent.

---

### H3. Nonwear Service `get_nonwear_periods_for_file()` Constructs SQL with F-Strings Using Enum Values

**File:** `sleep_scoring_app/services/nonwear_service.py`
**Lines:** 251-278

**Description:** The `get_nonwear_periods_for_file()` method constructs SQL queries using f-strings with `DatabaseTable` and `DatabaseColumn` enum values. While these come from validated StrEnums (not user input), the pattern is fragile:

```python
query = f"""
    SELECT * FROM {table}
    WHERE {DatabaseColumn.PARTICIPANT_ID} = ?
"""
```

The table and column names bypass the `_validate_table_name` / `_validate_column_name` methods that the `DatabaseManager` class provides. If a StrEnum value were ever changed to contain SQL-special characters (unlikely but possible in a refactor), this would become an injection vector.

More critically, the method creates a `BaseRepository` directly (line 245) using `self.db_manager.db_path` and private validation methods (`self.db_manager._validate_table_name`), violating encapsulation. If `BaseRepository` or `DatabaseManager` internals change, this code silently breaks.

**Evidence:**
```python
temp_repo = BaseRepository(
    self.db_manager.db_path,
    self.db_manager._validate_table_name,    # Accessing private method
    self.db_manager._validate_column_name     # Accessing private method
)
```

**Impact:** The direct access to private methods and raw repository creation bypasses the repository pattern that the rest of the codebase uses. If `DatabaseManager` changes its internal validation or repository initialization, this service will break. The f-string SQL is also not validated through the standard path.

**Fix:** Add a `get_nonwear_periods_for_file()` method to `NonwearRepository` (or the relevant repository) and delegate to it from the service, following the same pattern as other database operations.

---

### H4. Export CSV Sanitization Prefixes Legitimate Negative Number Strings with Quote

**File:** `sleep_scoring_app/services/export_service.py`
**Lines:** 90-98

**Description:** The `_sanitize_csv_cell()` method checks if string values start with `-` and prefixes them with a single quote to prevent CSV formula injection. However, this also affects legitimate negative number strings (e.g., timezone offsets like `"-05:00"`, negative values that were converted to strings). While numeric types are passed through unchanged (line 92-93), any column that stores numbers as strings will be corrupted.

**Evidence:**
```python
def _sanitize_csv_cell(self, value: str | float | None) -> str | int | float | None:
    if not isinstance(value, str):
        return value
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value  # "-05:00" becomes "'-05:00"
    return value
```

**Impact:** Any string column in the exported CSV that legitimately starts with `-` will have a spurious `'` prefix in the output file. This is a data integrity issue for downstream consumers of the CSV who expect clean values. The sanitization is applied to ALL string columns (line 170-171, 239-240, 362-363), not just user-input columns.

**Fix:** Only sanitize columns that could contain user-provided text, or use a more targeted check (e.g., only flag strings that start with `=`, `+`, `@`, `\t`, `\r` and leave `-` alone, since `-` alone is not a formula prefix in modern spreadsheets). Alternatively, check for `=-`, `=+`, etc. patterns that are actual formula starters.

---

### H5. `_database_initialized` Module-Level Flag Is Not Path-Aware

**File:** `sleep_scoring_app/data/database.py`
**Line:** 49

**Description:** The `_database_initialized` flag is a module-level boolean that tracks whether the database has been initialized. However, it is not associated with any specific database path. If the application switches between databases (e.g., different participant databases, test vs. production), the flag remains `True` from the first initialization, causing subsequent database opens to skip initialization (schema creation, migrations).

**Evidence:**
```python
# Module-level flag to track if database has been initialized
_database_initialized = False
```

**Impact:** In scenarios where the database path changes at runtime (which the application supports via data folder selection), the new database may not have its schema created or migrations applied. This would cause SQL errors when trying to query tables that don't exist, or worse, silently operate on a schema-less database that stores nothing.

**Fix:** Replace the boolean flag with a set of initialized paths, or move the initialization tracking into the `DatabaseManager` instance (keyed by `db_path`).

---

## Observations (Not Issues)

These are patterns noticed during review that don't rise to CRITICAL/HIGH but are worth noting:

1. **NonwearData._periods_to_mask (line 158):** For periods without index data, the timestamp-matching loop is O(n*m) where n=timestamps and m=periods. Not a correctness issue, but a performance concern for large datasets.

2. **`calculate_overlapping_nonwear_minutes` uses inclusive offset_idx (line 101: `onset_idx : offset_idx + 1`) while `_calculate_sleep_metrics_from_timestamps` loops use exclusive offset_idx (line 66: `range(onset_idx, min(offset_idx, ...))`):** This is a consistent pattern throughout (TIB calculation is also exclusive), but it means nonwear overlap counts one extra minute at the offset boundary compared to the other metrics. This is a minor counting discrepancy (1 minute) that may or may not be intentional.

3. **`datetime.fromtimestamp()` usage without timezone:** Multiple locations use `datetime.fromtimestamp()` without explicit timezone, relying on the system's local timezone. This is fragile across time zones but appears to be a known design decision in this application.
