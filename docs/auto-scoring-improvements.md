# Auto-Scoring & Complexity Improvements

Reviewed 2026-03-05. These are proposed improvements to `marker_placement.py` and `complexity.py` — not yet implemented.

## Auto-Scoring (marker_placement.py)

### 1. Unbounded onset search for main sleep [Medium]

`_find_valid_onset_near` searches the entire epoch array with no distance bound. Offset uses `_find_valid_offset_near_bounded` (max 60 epochs), but onset can pick a sleep run hours before the diary time if no closer candidate exists.

**Fix:** Add bounding to main sleep onset search (e.g., 120 epochs / 2 hours).

### 2. `diary_tolerance_minutes` declared but unused [Low]

`PlacementConfig.diary_tolerance_minutes = 15` exists per CLAUDE.md Rule 6 (choosing between equidistant candidates), but no code references it. Currently tie-breaking uses raw epoch index distance only — no 15-minute preference logic.

### 3. Nap overlap with other naps not checked [Medium]

`place_naps` checks overlap with main sleep but not between naps. Two diary nap periods resolving to the same or overlapping sleep run will both be placed with overlapping markers.

**Fix:** Track placed nap ranges and skip any new nap that overlaps a previously placed one.

### 4. Bounded offset only caps forward, not backward [Low]

`_find_valid_offset_near_bounded` limits `max_idx = center + max_forward_epochs` but doesn't restrict backward search. For nap offsets, it could find an offset far before the diary time. The `before` candidate pool is unrestricted.

### 5. Nonwear data ignored during placement [Medium]

`EpochData.is_choi_nonwear` is populated but never checked during onset/offset search. Per CLAUDE.md Rule 5, Choi-only nonwear with activity spikes can sometimes be ignored, but the algorithm doesn't consider nonwear at all. A sleep run entirely within a nonwear period is treated identically to genuine sleep.

**Fix:** Deprioritize or skip candidates that fall within confirmed nonwear periods. Choi-only nonwear with activity spikes should be treated differently per Rule 5.

### 6. Rule 3 not implemented [Low]

CLAUDE.md Rule 3: extend to the beginning of a typical nap period if there are continuous sleep epochs before the diary marker. Not yet implemented.

### 7. Unused imports [Trivial]

`statistics` (line 18) and `time` from `datetime` (line 20) are imported but never used.

---

## Complexity (complexity.py)

### 1. Night window hardcoded to 21:00-09:00 [Medium]

`_night_window_indices` always uses 21:00-09:00 regardless of the study settings `night_start_hour`/`night_end_hour`. If the study configured different hours, complexity features are computed over the wrong window.

**Fix:** Accept night start/end as parameters, sourced from study settings.

### 2. Post-complexity uses global first/last sleep epoch [Medium]

`compute_post_complexity` (lines 726-732) finds algorithm onset as the very first `sleep_score == 1` in the entire array, and offset as the very last. This could be a daytime nap epoch, not the main sleep boundary.

**Fix:** Use the night window or the nearest boundary to diary times (like `_diary_algorithm_gap_penalty` does for pre-complexity).

### 3. Post-complexity period count is full-day, not night-only [Low]

Lines 758-767 count sleep runs across the entire 24 hours, then compare to the number of placed markers. This inflates the expected count with daytime episodes and triggers a -5 penalty unfairly.

**Fix:** Restrict run counting to the night window.

### 4. Boundary clarity uses first/last epoch, not sleep runs [Low]

`_boundary_clarity_penalty` finds `onset_idx` as the first epoch with `sleep_score == 1` and `offset_idx` as the last, regardless of run length. A single isolated sleep epoch (not a valid 3+ run) could be used.

**Fix:** Use the same 3+ consecutive run logic to find boundary epochs.

### 5. `_build_confirmed_nonwear_mask` is O(n^2) [Low]

Linear scan over all timestamps for each nonwear period. Slow for large datasets.

**Fix:** Use binary search to find epoch range for each nonwear period.

### 6. Activity spike threshold hardcoded at 50.0 [Low]

`_count_activity_spikes` uses `threshold=50.0` which may not generalize across devices or epoch lengths.

**Fix:** Make configurable or derive from data distribution (e.g., percentile-based).

### 7. Flatline check uses magic thresholds [Trivial]

`night_spikes == 0 and choi_night_epochs >= 60` — the 60-epoch threshold is unexplained.

**Fix:** Extract to a named constant with a comment explaining the rationale.
