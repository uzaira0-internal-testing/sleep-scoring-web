# Review 012: Core, Services, IO, and Data Layer Review

**Date**: 2026-02-25
**Scope**: `sleep_scoring_app/core/`, `sleep_scoring_app/services/`, `sleep_scoring_app/io/`, `sleep_scoring_app/data/`
**Focus**: Bugs, logic errors, data corruption risks, silent failures, architecture violations
**Standard**: Only CRITICAL and HIGH severity issues

---

## Summary

Reviewed all `.py` files across the four target directories (80+ files). Found 5 actionable issues: 1 CRITICAL (algorithm correctness), 2 HIGH (data loss/wrong results), and 2 HIGH (architecture violations that break testability and can mask bugs).

---

## Issues

### Issue 1: Sadeh Algorithm SD Window Offset Is Backward-Looking Instead of Forward-Looking

**Severity**: CRITICAL (wrong sleep/wake classification for every epoch)
**File**: `sleep_scoring_app/core/algorithms/sleep_wake/sadeh.py:160-168`

**Description**: The Sadeh (1994) paper defines the SD variable as "the standard deviation of the activity counts within a 6-min period starting at the epoch in question" -- a forward-looking window [current, +1, +2, +3, +4, +5]. The implementation computes a backward-looking window instead, using epochs [-5, -4, -3, -2, -1, current]. This means every epoch's SD variable is computed from the wrong 6 epochs, directly affecting the sleep/wake classification formula.

**Evidence**:

```python
# Line 160: Pads 5 zeros at START and 5 at END
padded_activity = np.pad(capped_activity, pad_width=5, mode="constant", constant_values=0)

# Line 164-165: SD window uses padded indices [i : i+6]
for i in range(len(capped_activity)):
    sd_window = padded_activity[i : i + 6]  # BUG: This is backward-looking
```

For original epoch index `i`, the padded array has that value at index `i + 5` (because 5 zeros were prepended). So `padded_activity[i : i + 6]` accesses original indices `[i-5, i-4, i-3, i-2, i-1, i]` -- a backward-looking window. A correct forward-looking window would be `padded_activity[i + 5 : i + 11]`.

Note: The AVG/NATS window (lines 172-174) correctly uses `padded_activity[i : i + 11]` which maps to original indices `[i-5 ... i+5]` -- the centered 11-epoch window. Only the SD window is wrong.

**Impact**: Every epoch's SD value is wrong, which feeds into the Sadeh formula `PS = 7.601 - 0.065*AVG - 1.08*NATS - 0.056*SD - 0.703*LG`. While SD has the smallest coefficient (0.056), this still shifts the sleep/wake threshold for every epoch, causing systematic misclassification. For a research application, any deviation from the published algorithm invalidates results.

**Fix**: Change line 165 to:
```python
sd_window = padded_activity[i + 5 : i + 5 + 6]
```

---

### Issue 2: NonwearPeriod.from_dict Drops Falsy Values for start_index and end_index

**Severity**: HIGH (data loss -- index 0 silently becomes None)
**File**: `sleep_scoring_app/core/dataclasses_markers.py:162-163`

**Description**: The `or` operator is used to fall back between two possible dictionary keys, but `or` also treats falsy values like `0` as missing. When `start_index=0` or `end_index=0` (perfectly valid Choi algorithm indices), the first lookup returns `0` which is falsy, so `or` falls through to the second lookup. If the second key is also absent, the value becomes `None`.

**Evidence**:

```python
start_index=data.get(DatabaseColumn.START_INDEX) or data.get("start_index"),
end_index=data.get(DatabaseColumn.END_INDEX) or data.get("end_index"),
```

Example: `data = {"start_index": 0, "end_index": 1440}` (from the database column names).
- `data.get(DatabaseColumn.START_INDEX)` returns `0` (truthy check fails)
- `0 or data.get("start_index")` evaluates to `data.get("start_index")` which returns `None`
- Result: `start_index=None` instead of `start_index=0`

The same pattern also affects `duration_minutes` (line 161) and `participant_id` (line 159), though empty string `""` for participant_id is a less likely edge case. The `source` field (line 160) would fail with a `ValueError` if `NonwearDataSource("")` were attempted.

**Fix**: Use a helper that distinguishes `None` from falsy:
```python
def _get_first_non_none(data, *keys):
    for key in keys:
        val = data.get(key)
        if val is not None:
            return val
    return None

start_index=_get_first_non_none(data, DatabaseColumn.START_INDEX, "start_index"),
end_index=_get_first_non_none(data, DatabaseColumn.END_INDEX, "end_index"),
```

---

### Issue 3: NonwearDataFactory.clear_cache_for_file Has Race Condition

**Severity**: HIGH (potential KeyError crash in concurrent access)
**File**: `sleep_scoring_app/core/nonwear_data.py:230-236`

**Description**: The method collects cache keys under the lock, then releases the lock and deletes keys outside it. Between releasing the lock and deleting, another thread could modify the cache (add/remove entries), causing a `KeyError` on `del self._cache[key]`.

**Evidence**:

```python
def clear_cache_for_file(self, filename: str) -> None:
    """Clear cached data for specific file."""
    with self._lock:                                              # Lock acquired
        keys_to_remove = [key for key in self._cache if key.startswith(filename)]
    for key in keys_to_remove:                                    # Lock released!
        del self._cache[key]                                      # KeyError if key removed by another thread
```

**Impact**: While the desktop app is primarily single-threaded for UI, background loading and the file watcher service can trigger concurrent cache operations. A `KeyError` would crash the nonwear data loading path.

**Fix**: Move the deletion inside the lock:
```python
def clear_cache_for_file(self, filename: str) -> None:
    with self._lock:
        keys_to_remove = [key for key in self._cache if key.startswith(filename)]
        for key in keys_to_remove:
            del self._cache[key]
```

---

### Issue 4: CacheService Directly Accesses UI Widget Internals (Layer Violation)

**Severity**: HIGH (architecture violation -- service layer coupled to UI widget implementation)
**File**: `sleep_scoring_app/services/cache_service.py:260-281`

**Description**: `CacheService` lives in the services layer, which must be headless (no Qt, no UI references). However, `clear_all_algorithm_caches()` directly accesses plot widget private attributes (`_algorithm_cache`, `main_48h_sadeh_results`, `main_48h_sadeh_timestamps`, `main_48h_axis_y_data`, `main_48h_axis_y_timestamps`). This violates the mandatory layered architecture from CLAUDE.md: "Services are HEADLESS - No Qt imports, no signals."

**Evidence**:

```python
def clear_all_algorithm_caches(self) -> None:
    plot_widget = self._plot_widget           # Gets UI widget reference
    if plot_widget:
        plot_widget._algorithm_cache.clear()  # Reaches into widget internals
        plot_widget.main_48h_sadeh_results = None
        plot_widget.main_48h_sadeh_timestamps = None
        plot_widget.main_48h_axis_y_data = None
        plot_widget.main_48h_axis_y_timestamps = None
```

The `set_ui_components()` method (line 146) allows UI code to inject widget references into the service, but this creates a bidirectional dependency: the service now knows about widget internals, making it impossible to test the service without a real plot widget or a mock that replicates every private attribute.

**Impact**: (1) Cannot unit test CacheService without mocking UI widgets. (2) Any rename/refactor of plot widget attributes silently breaks cache clearing. (3) Violates the project's stated architecture constraint.

**Fix**: The cache clearing should be inverted -- the UI layer should subscribe to a cache invalidation event/callback and clear its own caches. Example:
```python
# In CacheService:
def clear_all_algorithm_caches(self) -> None:
    self.current_date_48h_cache.clear()
    self._file_service.main_48h_data_cache.clear()
    if self._on_algorithm_cache_cleared:
        self._on_algorithm_cache_cleared()  # Callback to UI

# In UI connector setup:
cache_service.set_algorithm_cache_cleared_callback(
    lambda: plot_widget.clear_algorithm_caches()
)
```

---

### Issue 5: Module-Level logging.basicConfig in database.py

**Severity**: HIGH (silently overrides application logging configuration)
**File**: `sleep_scoring_app/data/database.py:47`

**Description**: `logging.basicConfig(level=logging.WARNING)` is called at module import time. In Python, `logging.basicConfig` installs a handler on the root logger only if no handlers exist yet. If `database.py` is imported before the application configures its logging (which is likely since it is imported transitively by services and the main window), it installs a WARNING-level handler on the root logger. This suppresses all DEBUG and INFO log messages from the entire application -- including the diagnostic logging that CLAUDE.md identifies as a known issue needing improvement (silent failures in data loading).

**Evidence**:

```python
# Line 47
logging.basicConfig(level=logging.WARNING)
```

**Impact**: DEBUG/INFO logs from data loading, algorithm execution, and marker operations are silently discarded if this module is imported early. This directly aggravates the "Silent Failures Need Better Logging" known issue documented in CLAUDE.md.

**Fix**: Remove the `logging.basicConfig()` call. Let the application entry point (`__main__.py` or the main window initialization) configure logging once. Individual modules should only use `logger = logging.getLogger(__name__)`.

---

## Files Reviewed

### Core Layer (37 files)
- `core/__init__.py`
- `core/constants/__init__.py`, `database.py`, `algorithms.py`, `io.py`, `ui.py`
- `core/dataclasses.py`, `dataclasses_config.py`, `dataclasses_markers.py`, `dataclasses_daily.py`, `dataclasses_diary.py`, `dataclasses_analysis.py`
- `core/algorithms/__init__.py`, `types.py`, `compatibility.py`
- `core/algorithms/sleep_wake/__init__.py`, `protocol.py`, `factory.py`, `sadeh.py`, `cole_kripke.py`, `utils.py`
- `core/algorithms/nonwear/__init__.py`, `protocol.py`, `factory.py`, `choi.py`
- `core/algorithms/sleep_period/__init__.py`, `protocol.py`, `factory.py`, `config.py`, `consecutive_epochs.py`, `metrics.py`
- `core/algorithms/protocols/__init__.py`, `callbacks.py`
- `core/algorithms/marker_placement/__init__.py`, `extractors.py`, `features.py`, `rules.py`
- `core/backends/__init__.py`, `protocol.py`, `factory.py`, `capabilities.py`, `data_types.py`, `pygt3x_backend.py`, `gt3x_rs_backend.py`
- `core/pipeline/__init__.py`, `types.py`, `exceptions.py`, `orchestrator.py`, `detector.py`
- `core/markers/protocol.py`, `persistence.py`
- `core/validation.py`, `exceptions.py`, `nonwear_data.py`

### Services Layer (29 files)
- `services/protocols.py`, `services/unified_data_service.py`
- `services/data_service.py`, `services/data_loading_service.py`, `services/data_query_service.py`
- `services/file_service.py`, `services/marker_service.py`, `services/export_service.py`, `services/import_service.py`
- `services/metrics_calculation_service.py`, `services/nonwear_service.py`
- `services/algorithm_service.py`, `services/batch_scoring_service.py`
- `services/cache_service.py`, `services/memory_service.py`
- `services/epoching_service.py`, `services/pattern_validation_service.py`
- `services/format_detector.py`, `services/file_format_detector.py`
- `services/csv_data_transformer.py`, `services/import_progress_tracker.py`
- `services/diary_service.py`, `services/diary_mapper.py`
- `services/diary/__init__.py`, `services/diary/query_service.py`, `services/diary/import_orchestrator.py`, `services/diary/data_extractor.py`, `services/diary/progress.py`

### IO Layer (4 files)
- `io/sources/csv_loader.py`, `io/sources/gt3x_loader.py`, `io/sources/gt3x_rs_loader.py`, `io/sources/loader_factory.py`

### Data Layer (11 files)
- `data/database.py`, `data/database_schema.py`, `data/config.py`
- `data/migrations.py`, `data/migrations_registry.py`
- `data/repositories/__init__.py`, `data/repositories/base_repository.py`
- `data/repositories/activity_data_repository.py`, `data/repositories/sleep_metrics_repository.py`
- `data/repositories/diary_repository.py`, `data/repositories/file_registry_repository.py`, `data/repositories/nonwear_repository.py`

---

## Verification Checklist

- [x] Read CLAUDE.md and understood the architecture rules
- [x] Checked every .py file in the target directories (not just a sample)
- [x] Each reported issue has a specific file:line reference
- [x] Each issue is reproducible (not speculative)
- [x] Did not report style-only issues
- [x] Did not report issues documented as known in CLAUDE.md (flash_processing import errors, E402 violations)
