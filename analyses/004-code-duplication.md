# Code Duplication and Redundancy Audit

## Summary

This audit identified several significant sources of code duplication and redundancy in the sleep-scoring-demo application:

1. **CRITICAL: Duplicate UI Constants File** - Two identical 732-line files exist
2. **HIGH: Adjacent Day Marker Functions** - Duplicated across two files (~100 lines each)
3. **MEDIUM: Algorithm Name Retrieval** - Multiple similar implementations across 4 files
4. **MEDIUM: Path-to-Filename Extraction** - Repeated pattern in 35+ locations
5. **LOW: Date String Formatting** - Repeated `strftime("%Y-%m-%d")` pattern (40+ occurrences)
6. **LOW: sadeh_results Access Pattern** - Repeated getattr pattern for accessing algorithm results

---

## Duplicate Patterns (Must Consolidate)

### 1. CRITICAL: Duplicate UI Constants File

**Description:** The entire UI constants module is duplicated between two locations.

**Locations:**
- `sleep_scoring_app/core/constants/ui.py` (731 lines)
- `sleep_scoring_app/ui/constants/ui.py` (731 lines)

**Difference:** Only one line differs - the import statement:
```python
# core/constants/ui.py
from .io import ActivityDataPreference

# ui/constants/ui.py
from sleep_scoring_app.core.constants.io import ActivityDataPreference
```

**Impact:**
- 731 lines of redundant code (1462 total lines for same content)
- Maintenance burden (changes must be made in two places)
- High risk of drift between files
- Confusion about canonical location

**Context:**
- The comment in `core/constants/__init__.py:127` says: "UI constants (DEPRECATED - import from sleep_scoring_app.ui.constants instead)"
- BUT per CLAUDE.md architecture, core should have NO dependencies on UI layer
- The `ui/constants/__init__.py` docstring claims it was "Moved from core.constants.ui to maintain proper layer boundaries"
- HOWEVER, ui constants are used by core layer (e.g., TimeFormat in dataclasses)

**Recommendation:**
1. KEEP `sleep_scoring_app/core/constants/ui.py` as canonical (core can't depend on ui)
2. DELETE `sleep_scoring_app/ui/constants/ui.py` and `sleep_scoring_app/ui/constants/__init__.py`
3. REMOVE the "DEPRECATED" comment from `core/constants/__init__.py`
4. UI layer imports from core, not vice versa (per architecture)
5. GREP to ensure no remaining references: `from sleep_scoring_app.ui.constants`

---

### 2. HIGH: Adjacent Day Marker Functions Duplicated

**Description:** The logic for loading, displaying, and clearing adjacent day markers is duplicated almost identically between MainWindow and UIStateCoordinator.

**Locations:**
| Function | main_window.py | ui_state_coordinator.py |
|----------|----------------|-------------------------|
| `_load_and_display_adjacent_day_markers` | Lines 1806-1857 | Lines 182-228 |
| `_load_markers_for_date` | Lines 1859-1898 | Lines 230-272 |
| `_clear_adjacent_day_markers` | Lines 1900-1903 | Lines 274-279 |

**Evidence of Duplication:**
Both files contain nearly identical code blocks for:
- Checking date indices
- Loading markers from prev/next day
- Setting adjacent_date and is_adjacent_day on markers
- Calling plot widget methods

**Recommendation:**
1. KEEP only the `ui_state_coordinator.py` implementation (it's in services layer)
2. REMOVE the duplicate methods from `main_window.py`
3. Have `main_window.py` delegate to `ui_state_coordinator` via:
   ```python
   # main_window.py already does this correctly:
   def toggle_adjacent_day_markers(self, show: bool) -> None:
       self.ui_state_coordinator.toggle_adjacent_day_markers(show)
   ```
4. DELETE unused private methods `_load_and_display_adjacent_day_markers`, `_load_markers_for_date`, and `_clear_adjacent_day_markers` from `main_window.py`

---

### 3. MEDIUM: Algorithm Name Retrieval Duplicated

**Description:** Logic to get the display name for the current sleep algorithm is duplicated.

**Locations:**
| File | Method | Lines |
|------|--------|-------|
| `ui/main_window.py` | `get_sleep_algorithm_display_name()` | 2008-2029 |
| `ui/analysis_tab.py` | `_get_sleep_algorithm_display_name()` | 1144-1158 |
| `ui/marker_table.py` | `get_current_sleep_algorithm_name()` | 79-105 |

**Pattern:**
All three implementations:
1. Try to get algorithm_id from config/store
2. Call `get_algorithm_service().get_available_sleep_algorithms()`
3. Return "Sadeh" as fallback

**Recommendation:**
1. CREATE a centralized method in `services/algorithm_service.py`:
   ```python
   def get_display_name_for_algorithm(algorithm_id: str | None) -> str:
       """Get display name for algorithm ID, with fallback to Sadeh."""
   ```
2. UPDATE all three locations to use this single implementation
3. UPDATE `ui/protocols.py` AppStateInterface to require only this delegating method

---

### 4. MEDIUM: Path-to-Filename Extraction Pattern

**Description:** The pattern `Path(value).name` is repeated 35+ times across the codebase to extract filename from path.

**Sample Locations (not exhaustive):**
- `ui/main_window.py:306` - `filename = Path(value).name if value else None`
- `ui/main_window.py:388` - `last_file_name = Path(last_file_path).name`
- `ui/main_window.py:654` - `filename=Path(self.selected_file).name if self.selected_file else ""`
- `ui/main_window.py:674` - `current_filename = Path(self.selected_file).name if self.selected_file else ""`
- `ui/main_window.py:1089` - `filename = Path(self.selected_file).name`
- `ui/main_window.py:1160` - `filename = Path(self.selected_file).name`
- `ui/window_state.py:201` - `filename = Path(self.navigation.selected_file).name`
- `ui/store.py:476` - `filename = Path(filename).name`
- `ui/store.py:673` - `loaded_file = Path(loaded_file).name`
- `services/file_service.py:95` - `filename = Path(selected_file).name if selected_file else None`
- `services/unified_data_service.py:221` - `filename = Path(selected_file).name`
- `services/unified_data_service.py:244` - `filename = Path(selected_file).name`
- (and 23+ more locations)

**Recommendation:**
1. CREATE utility function in `utils/path_helpers.py`:
   ```python
   def extract_filename(path: str | Path | None) -> str | None:
       """Extract filename from path, handling None and empty values."""
       if not path:
           return None
       return Path(path).name
   ```
2. REPLACE all occurrences with this utility
3. This also aligns with CLAUDE.md convention that database uses filename only

---

### 5. LOW: sadeh_results Access Pattern

**Description:** The pattern `getattr(widget, "main_48h_sadeh_results", getattr(widget, "sadeh_results", []))` appears multiple times.

**Locations:**
| File | Line |
|------|------|
| `utils/table_helpers.py` | 511 |
| `utils/table_helpers.py` | 519 |
| `ui/marker_table.py` | 423 |
| `ui/marker_table.py` | 430 |
| `ui/marker_table.py` | 513 |
| `ui/marker_table.py` | 518 |

**Recommendation:**
1. CREATE accessor method on plot widget or add to PlotWidgetInterface protocol:
   ```python
   def get_sleep_score_results(self) -> list[int]:
       """Get current sleep score results (main_48h or regular)."""
       return self.main_48h_sadeh_results or self.sadeh_results or []
   ```
2. UPDATE all usages to use this single accessor

---

### 6. LOW: Date String Formatting Pattern

**Description:** The pattern `date.strftime("%Y-%m-%d")` appears 40+ times but is already defined as a constant.

**Existing Constant:**
```python
# In core/constants/ui.py
class TimeFormat(StrEnum):
    DATE_ONLY = "%Y-%m-%d"
```

**Sample Locations Not Using Constant:**
- `core/markers/persistence.py:92` - `date.strftime("%Y-%m-%d")`
- `core/markers/persistence.py:132` - `date.strftime("%Y-%m-%d")`
- `ui/main_window.py:348` - `d.strftime("%Y-%m-%d")`
- `ui/main_window.py:1088` - `current_date.strftime("%Y-%m-%d")`
- `services/diary_mapper.py:203` - `value.strftime("%Y-%m-%d")`
- (and 35+ more locations)

**Recommendation:**
1. REPLACE all hardcoded `"%Y-%m-%d"` with `TimeFormat.DATE_ONLY`
2. Consider creating utility function:
   ```python
   def format_date_iso(d: date | datetime) -> str:
       return d.strftime(TimeFormat.DATE_ONLY)
   ```

---

## Dead/Unused Code (Must Delete)

### 1. Orphaned Private Methods in main_window.py

The following methods in `main_window.py` appear to be duplicates that should be removed since `ui_state_coordinator.py` already has working implementations:

| Method | Lines | Status |
|--------|-------|--------|
| `_load_and_display_adjacent_day_markers` | 1806-1857 | DELETE - duplicate of ui_state_coordinator |
| `_load_markers_for_date` | 1859-1898 | DELETE - duplicate of ui_state_coordinator |
| `_clear_adjacent_day_markers` | 1900-1903 | DELETE - duplicate of ui_state_coordinator |

**Verification Performed:**
1. Searched entire codebase for calls to `_load_and_display_adjacent_day_markers`
2. **Result:** Only `ui_state_coordinator.py:177` calls its own version; main_window's version is NEVER called
3. The public method `toggle_adjacent_day_markers()` at line 1802-1804 correctly delegates to `ui_state_coordinator.toggle_adjacent_day_markers(show)`
4. **Conclusion:** The three private methods in main_window.py are 100% dead code and can be safely deleted

### 2. Dead Code Block in ui_state_coordinator.py

**Location:** `services/ui_state_coordinator.py:240-243`

```python
if False:  # Keep original indentation for cursor lines (dead code)
    cursor = None  # type: ignore
    available_dates = [row[0] for row in cursor.fetchall()]
    logger.info(f"Available dates in database for {filename}: {available_dates}")
```

This is explicit dead code that should be removed.

---

## Overly Complex Code (Should Simplify)

### 1. hasattr() Pattern for Optional Attributes

**Problem:** Multiple files use `hasattr()` to check for optional attributes where a Protocol or proper initialization would be cleaner.

**Example Patterns:**
```python
# Seen in multiple places:
if hasattr(self.parent, "sadeh_results"):  # KEEP: Duck typing
    ...
if hasattr(line, "period") and line.period:  # KEEP: Duck typing
    ...
```

**Count:** 90+ hasattr() usages across the codebase

**Note:** Many are marked with `# KEEP:` comments indicating they are intentional duck typing. However, some could be replaced with:
- Proper Protocol definitions
- Optional attributes with default values
- Proper initialization order

---

## Recommendations (Priority Ordered)

### Priority 1 - Critical (Must Fix)

1. **DELETE duplicate UI constants file**
   - Remove: `sleep_scoring_app/ui/constants/ui.py`
   - Update: All imports to use `sleep_scoring_app.core.constants.ui`
   - Effort: Low (1 hour)

### Priority 2 - High (Should Fix Soon)

2. **Remove duplicate adjacent day marker methods from main_window.py**
   - Delete: Lines 1806-1903 in `main_window.py`
   - Verify: `toggle_adjacent_day_markers()` delegation works correctly
   - Effort: Low (30 min)

3. **Delete dead code block in ui_state_coordinator.py**
   - Delete: Lines 240-243
   - Effort: Trivial (5 min)

### Priority 3 - Medium (Fix During Related Work)

4. **Centralize algorithm name retrieval**
   - Create: `AlgorithmService.get_display_name_for_algorithm()`
   - Update: 3 calling locations
   - Effort: Medium (2 hours)

5. **Create filename extraction utility**
   - Create: `utils/path_helpers.py` with `extract_filename()`
   - Update: 35+ calling locations
   - Effort: Medium (3 hours) - mostly mechanical

### Priority 4 - Low (Nice to Have)

6. **Use TimeFormat.DATE_ONLY constant**
   - Update: 40+ hardcoded date format strings
   - Effort: Low but tedious (2 hours)

7. **Centralize sadeh_results accessor**
   - Create: Method on plot widget
   - Update: 6 calling locations
   - Effort: Low (1 hour)

---

## Verification Checklist

- [x] All major modules scanned for duplication
- [x] Each duplication includes file:line references
- [x] Recommendations are specific and actionable
- [x] Dead code verified as unreachable (delegation pattern confirms orphaned methods)
- [x] Priority levels assigned based on impact and effort
