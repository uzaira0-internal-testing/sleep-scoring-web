<objective>
Thoroughly review all data persistence paths (save, load, delete, autosave) for correctness
and symmetry. The application saves sleep markers and nonwear markers to SQLite via a repository
pattern. A recent bug showed that autosave could silently skip DB writes, causing deleted markers
to reappear. Find any remaining instances of this class of bug.
</objective>

<context>
Read CLAUDE.md for persistence rules. The data flow is:

Save paths:
- Manual save: window_state.save_current_markers() -> _autosave_sleep_markers_to_db()
- Autosave: AutosaveCoordinator -> _save_sleep_markers() -> _autosave_sleep_markers_to_db()
- Force save: before navigation -> autosave_coordinator.force_save()
- Clear: window_state.clear_current_markers() -> db_manager.delete_sleep_metrics_for_date()

Load path:
- window_state.load_saved_markers() -> db_manager.load_sleep_metrics()

Key files:
- `sleep_scoring_app/ui/main_window.py` - _autosave_sleep_markers_to_db, _autosave_nonwear_markers_to_db
- `sleep_scoring_app/ui/window_state.py` - save_current_markers, clear_current_markers, load_saved_markers
- `sleep_scoring_app/ui/coordinators/autosave_coordinator.py` - _execute_save, _save_sleep_markers
- `sleep_scoring_app/data/repositories/sleep_metrics_repository.py` - DB operations
- `sleep_scoring_app/data/repositories/nonwear_repository.py` - Nonwear DB operations
</context>

<requirements>
Search for these specific issues:

1. **Save/load asymmetry** - data saved in one format but loaded expecting a different format
2. **Silent failures** - try/except blocks that swallow errors and return empty results
3. **Early returns that skip DB operations** - like the recently-fixed autosave bug
4. **Missing cache invalidation** - saving to DB without invalidating marker_status_cache or metrics_cache
5. **Orphaned DB records** - save paths that INSERT but never DELETE (accumulating stale records)
6. **Transaction safety** - operations that should be atomic but aren't wrapped in transactions
7. **Nonwear save/load parity** - verify nonwear markers follow the same DELETE-then-INSERT pattern consistently
8. **"No Sleep" marker handling** - verify the NO_SLEEP sentinel value is correctly saved and loaded
9. **File key consistency** - verify all DB operations use filename-only (not full path) as the key
</requirements>

<output>
Save findings to: `./reviews/009-data-persistence-review.md`

Format each finding as:
```
### [SEVERITY] Finding title
- **File**: path:line_number
- **Issue**: What's wrong
- **Scenario**: When this would manifest as a bug
- **Fix**: Suggested remediation
```

Group by severity: CRITICAL > HIGH > MEDIUM > LOW.
Only report findings you are confident about (>80% confidence).
</output>

<verification>
Before completing:
- Trace EVERY save path end-to-end (dispatch -> callback -> DB write -> cache invalidation)
- Trace EVERY load path (DB read -> deserialization -> dispatch to store)
- Verify that delete operations clean up ALL related tables (sleep_metrics + sleep_markers_extended)
- Check that return values from save callbacks propagate correctly to AutosaveCoordinator
</verification>
