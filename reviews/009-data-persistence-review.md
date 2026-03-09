# 009 Data Persistence Review

## Summary
- CRITICAL: 0
- HIGH: 3
- MEDIUM: 2
- LOW: 1

## CRITICAL
No CRITICAL findings.

## HIGH
### [HIGH] Autosave writes `sleep_metrics` but can leave stale `sleep_markers_extended` rows
- **File**: sleep_scoring_app/data/repositories/sleep_metrics_repository.py:82
- **Issue**: The autosave path persists via `save_sleep_metrics()` (`_save_permanent_metrics`), which updates `sleep_metrics` only. Period-level rows in `sleep_markers_extended` are maintained by the atomic save path and can become stale.
- **Scenario**: Export/atomic save populates `sleep_markers_extended`, then later marker edits autosave through `save_sleep_metrics()`. Main record updates, but period-level table may still reflect older marker geometry.
- **Fix**: Use an atomic marker save path for autosave, or explicitly clear/sync `sleep_markers_extended` for the same filename/date during non-atomic saves.

### [HIGH] Nonwear autosave does not invalidate marker status cache
- **File**: sleep_scoring_app/ui/main_window.py:1197
- **Issue**: `_autosave_nonwear_markers_to_db()` saves records and returns without cache invalidation, unlike the sleep autosave path that invalidates marker-status cache.
- **Scenario**: Nonwear edits autosave successfully, but file/date completion indicators remain stale until another operation invalidates cache.
- **Fix**: After successful nonwear save, call `state_manager.invalidate_marker_status_cache(filename)` (and any other impacted cache invalidators).

### [HIGH] `clear_current_markers()` is not atomic across sleep and nonwear deletes
- **File**: sleep_scoring_app/ui/window_state.py:302
- **Issue**: Sleep delete and nonwear delete are separate operations. If the first succeeds and the second fails, the method returns early and Redux/widget state is not cleared, leaving UI/DB divergence.
- **Scenario**: Sleep records are removed, nonwear delete fails, user still sees markers in UI until reload; reloading then shows partial deletion.
- **Fix**: Introduce a single transactional delete operation for both domains (or rollback strategy) before returning control to UI.

## MEDIUM
### [MEDIUM] Onset/offset rule mapping mismatch can persist default rule instead of selected rule
- **File**: sleep_scoring_app/data/repositories/sleep_metrics_repository.py:250
- **Issue**: Column-registry lookup uses `onset_offset_rule` naming while serialized metrics use `sleep_period_detector_id`, causing fallback to default in the save mapping path.
- **Scenario**: User selects a non-default detector, autosaves, and later reloads to find default detector metadata persisted.
- **Fix**: Align registry key and serialized key naming (`sleep_period_detector_id` vs `onset_offset_rule`) so mapper resolves the selected value.

### [MEDIUM] Sleep autosave invalidates marker-status cache but not metrics cache
- **File**: sleep_scoring_app/ui/main_window.py:1188
- **Issue**: `_autosave_sleep_markers_to_db()` invalidates marker-status cache only.
- **Scenario**: Marker autosave succeeds, but consumers of cached metrics can display stale metrics until unrelated invalidation.
- **Fix**: Also invalidate metrics cache after successful sleep autosave.

## LOW
### [LOW] `clear_all_markers()` stats undercount deleted rows from `sleep_markers_extended`
- **File**: sleep_scoring_app/data/database.py:580
- **Issue**: The delete result for `sleep_markers_extended` is not included in returned summary totals.
- **Scenario**: Operation succeeds, but reported deletion counts are lower than actual rows removed.
- **Fix**: Capture and report `sleep_markers_extended` rowcount in the returned stats.
