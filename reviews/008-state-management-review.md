# 008 State Management Review

## Summary
- CRITICAL: 0
- HIGH: 2
- MEDIUM: 1
- LOW: 0

## CRITICAL
No CRITICAL findings.

## HIGH
### [HIGH] Nonwear-only unsaved changes can bypass navigation guard in manual-save mode
- **File**: sleep_scoring_app/ui/main_window.py:916
- **Pattern**: Dirty flag asymmetry
- **Impact**: Navigation warning/save flow is gated by `has_complete_markers` computed only from sleep markers (`current_sleep_markers`). If only nonwear markers are dirty, manual mode (`auto_save_enabled=False`) can navigate away without the save/discard prompt, causing nonwear edits to be lost.
- **Fix**: Include nonwear completeness in the guard condition (or gate on dirty flags directly), e.g. treat `current_nonwear_markers.get_complete_periods()` as save-worthy state for manual navigation checks.

### [HIGH] closeEvent performs a redundant second save via widget state after force_save
- **File**: sleep_scoring_app/ui/main_window.py:2180
- **Pattern**: Stale state reads / parallel save paths
- **Impact**: `closeEvent()` calls `autosave_coordinator.force_save()` and then `auto_save_current_markers()`. The second path reads from `plot_widget.daily_sleep_markers` (widget copy), not Redux state, creating duplicate writes and a potential overwrite with stale widget state.
- **Fix**: Remove the second save call from `closeEvent()` and keep one canonical close-save path via `AutosaveCoordinator.force_save()` (Redux-driven).

## MEDIUM
### [MEDIUM] Shadow dirty flag state is maintained outside Redux but never driven true
- **File**: sleep_scoring_app/ui/window_state.py:93
- **Pattern**: Dirty flag asymmetry
- **Impact**: `unsaved_changes_exist` is set `False` in save/load flows but is not set `True` by marker-change flows. This creates misleading parallel state that can drift from Redux dirty flags.
- **Fix**: Remove `unsaved_changes_exist` entirely and rely on `store.state.sleep_markers_dirty` / `store.state.nonwear_markers_dirty` as the sole source of truth.

## LOW
No LOW findings.
