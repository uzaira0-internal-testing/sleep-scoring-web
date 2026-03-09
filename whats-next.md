<original_task>
Implement the plan "Fix All Desktop Issues from Reviews 016" — fix all 5 CRITICAL, 16 HIGH, and 13 MEDIUM/LOW issues identified in three fresh code reviews (core/services/IO, UI layer, test coverage) of the desktop application.
</original_task>

<work_completed>
## All 4 phases are complete and committed.

### Commit `141340c` — fix(sleep-scoring): Fix all desktop issues from reviews 016
25 files changed, 334 insertions, 773 deletions.

### Phase 1: CRITICAL Bug Fixes (5 items)
- **1A** Choi algorithm uses instance parameters (`self._small_window_length`, etc.) instead of module constants
- **1B** WASO calculation uses `total_sleep_time` (correct scope) instead of `sleep_minutes`
- **1C** FILE_SELECTED reducer resets markers, dirty flags, selected indices, sadeh_results, activity_timestamps
- **1D** Removed double dispatch of FILE_SELECTED in `main_window.py` (2 locations: `_restore_session` and `on_file_selected_from_table`)
- **1E** Fixed frozen dataclass mutation in test fixtures, rewrote `real_main_window` to use normal constructor

### Phase 2: HIGH Fixes (11 items)
- **2A** Compound `STATE_CLEARED` action replaces 5 sequential dispatches in `manager.py`
- **2B** `SeamlessSourceSwitcher` syncs restored markers back to Redux store
- **2C** `AutosaveCoordinator` captures date at request time, adds `pause()`/`resume()`
- **2D** Removed marker clearing from `NavigationConnector` (MarkersConnector's job)
- **2E** Removed dirty flag from `DateDropdownConnector` color update trigger
- **2F** `PopOutConnector` refreshes on `last_markers_save_time`, not `last_marker_update_time`
- **2G** `WindowGeometryConnector` uses Qt event filter instead of 500ms polling timer
- **2H** Autosave paused around modal dialogs to prevent deferred dispatch
- **2I** Re-enabled nonwear overlap filter in `nonwear_data.py`
- **2J** Added SAVEPOINT to migration DDL in `migrations.py`
- **2K** Removed `-` from CSV formula injection sanitization

### Phase 3: Test Cleanup (9 items)
- **3A-3C** Retagged 3 integration files from `@pytest.mark.e2e` to `@pytest.mark.integration`
- **3D** Deleted no-op mock tests from `test_complete_workflow.py`
- **3E** Fixed bare `pass` in error tests with proper assertions
- **3F** Deleted `test_export_tab.py` (fabricated widget tests)
- **3G** Deleted `test_main_window_tabs.py` (generic Qt tests)
- **3H** Added `np.random.seed(42)` to all E2E test CSV generators
- **3I** Added `test_custom_parameters_affect_detection` to Choi tests

### Phase 4: Moderate Complexity (2 items)
- **4A** `_database_initialized` changed from `bool` to `set[str]` for path-aware DB init (committed in prior session)
- **4B** `NonwearService` delegates to `NonwearRepository.get_periods_for_file()`/`save_periods()` instead of ad-hoc `BaseRepository` with private method access

### Test Counts (final)
- Unit: 2426 passed, 7 skipped
- GUI: 131 passed, 1 skipped
- Lint: 0 errors (in our code; 3 pre-existing in web layer)
</work_completed>

<work_remaining>
The original task is **COMPLETE**. All items from the plan are implemented, tested, and committed as `141340c`.

No work remains on this task.
</work_remaining>

<context>
## Key Commits
- `141340c` — All remaining plan items (Phase 1-3 code changes + Phase 4B service refactor + test updates)
- Prior session committed: `database.py` (4A), `migrations.py` (2J), `nonwear_repository.py` (4B repo methods)

## Deferred Items (per plan, with justification)
- GAP-01 (E2E export test): Export depends on external paths/format assumptions
- GAP-02 (Error feedback tests): Requires UI error handling infrastructure that doesn't exist yet
- GAP-03 (Keyboard shortcut key events): QShortcut sequences don't reliably fire via QTest.keyClick headless
- GAP-04 (Marker drag tests): Requires fragile pyqtgraph mouse simulation

## Gotchas
- `tests/unit/data/` is gitignored by monorepo root `.gitignore` line 73 (`data/`). New files there need `git add -f`.
- The `_GeometryFilter` inner class was extracted to module level to avoid ruff N805 (self naming conflict in nested classes).
- `nonwear_repository.py`, `database.py`, `migrations.py` were committed in a prior session — they don't appear in the final commit diff.

## Review Files
- `reviews/016-core-services-io-review.md`
- `reviews/016-ui-layer-review.md`
- `reviews/016-test-coverage-review.md`
- Plan file: `C:\Users\u248361\.claude\plans\wise-stargazing-lamport.md`
</context>
