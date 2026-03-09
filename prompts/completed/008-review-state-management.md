<objective>
Thoroughly review the Redux-style state management implementation for correctness, mutation safety,
and proper patterns. The app uses a custom Redux store (ui/store.py) as single source of truth.
State bugs here cause the hardest-to-debug issues (stale data, phantom markers, dirty flags not clearing).
</objective>

<context>
Read CLAUDE.md for Redux pattern rules. Key constraints:
- UIState is frozen; nested marker dataclasses are mutable but must be treated as immutable snapshots
- Always deep-copy before mutating: `markers = copy.deepcopy(store.state.current_sleep_markers)`
- Connectors bridge Widget signals -> store.dispatch() and store state -> widget updates
- MarkersConnector uses `_widget_dispatched_sleep`/`_widget_dispatched_nonwear` flags to distinguish sources
- AutosaveCoordinator subscribes to store and debounces saves

Key files:
- `sleep_scoring_app/ui/store.py` - Redux store, Actions, UIState, reducer
- `sleep_scoring_app/ui/connectors/` - All connectors
- `sleep_scoring_app/ui/coordinators/autosave_coordinator.py` - Autosave logic
- `sleep_scoring_app/ui/window_state.py` - State management operations
</context>

<requirements>
Search for these specific patterns:

1. **Direct state mutation** - any code that modifies `store.state.*` without dispatching an action
2. **Missing deep copies** - code that gets markers from store and mutates them without `copy.deepcopy()`
3. **Dispatch inside dispatch** - dispatching actions inside a subscriber callback (causes recursion)
4. **Dirty flag asymmetry** - places where dirty flags are set but never cleared, or cleared without saving
5. **Race conditions** - autosave timer firing while navigation is in progress
6. **Stale state reads** - reading store.state before a pending dispatch has been processed
7. **Signal-dispatch loops** - connector updates widget, widget emits signal, connector dispatches again (infinite loop risk)
8. **Autosave early returns** - cases where autosave skips saving but still clears dirty flags (like the bug just fixed in _autosave_sleep_markers_to_db)
</requirements>

<output>
Save findings to: `./reviews/008-state-management-review.md`

Format each finding as:
```
### [SEVERITY] Finding title
- **File**: path:line_number
- **Pattern**: Which anti-pattern this matches
- **Impact**: What bug this could cause
- **Fix**: Suggested remediation
```

Group by severity: CRITICAL > HIGH > MEDIUM > LOW.
Only report findings you are confident about (>80% confidence).
</output>

<verification>
Before completing:
- Trace the full lifecycle for each finding (dispatch -> reducer -> subscriber -> widget)
- Verify the `_widget_dispatched_*` guard logic is correctly preventing loops
- Check that markers_saved() is ONLY dispatched after successful DB writes
- Verify force_save() before navigation covers all dirty state
</verification>
