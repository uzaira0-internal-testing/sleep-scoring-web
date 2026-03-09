<objective>
Review the UI layer (widgets, connectors, coordinators, store) of the sleep-scoring-demo app for glaring issues.

Focus on bugs, state management errors, race conditions, stale data, signal/slot misconnections, and Redux pattern violations. This is NOT a style review — only report issues that could cause incorrect behavior, UI desyncs, or crashes.
</objective>

<context>
This is a PyQt6 desktop application using a Redux-like store pattern. Read `./CLAUDE.md` first for the full architecture rules, Redux pattern, and connector/coordinator responsibilities.

Key architecture rules:
- **Widgets are DUMB**: Emit signals only. No direct service calls, no store dispatch, no hasattr() on parent.
- **Connectors** bridge Widget <-> Store: Subscribe to store, update widgets, connect signals to dispatch.
- **Coordinators** orchestrate complex multi-component flows (can use QTimer, QThread).
- **Store is frozen UIState**: Nested mutable objects (markers) must be deep-copied before mutation.
- **No hasattr() abuse**: Use Protocol interfaces instead.

The most common bugs in this codebase are: stale state after navigation, markers not clearing on date switch, signals firing during initialization, and re-entrancy during Redux dispatch.
</context>

<research>
Thoroughly analyze these directories for glaring issues:

1. `./sleep_scoring_app/ui/store.py` — Redux store, reducer, actions, selectors
   - Check reducer for missed state resets (e.g., flags not cleared on date/file change)
   - Check for mutable state leaking into frozen UIState
   - Check action creators for missing payload fields

2. `./sleep_scoring_app/ui/connectors/` — All connectors
   - Check for stale data: connectors not reacting to date/file changes
   - Check for missing disconnect() cleanup (memory leaks)
   - Check for direct service calls (should go through store)
   - Check for state comparison bugs (identity `is` vs equality `==`)

3. `./sleep_scoring_app/ui/coordinators/` — All coordinators
   - Check for race conditions with QTimer.singleShot ordering
   - Check for re-entrancy bugs during dispatch
   - Check for missing guard clauses

4. `./sleep_scoring_app/ui/widgets/` — All widgets
   - Check for layer violations (widgets calling services directly, dispatching to store)
   - Check for hasattr() abuse
   - Check signal/slot connection issues (wrong signature, missing disconnects)

5. `./sleep_scoring_app/ui/main_window.py` — Main window
   - Check for god-object anti-patterns (methods that should be in coordinators/connectors)
   - Check initialization order bugs
   - Check for uncaught exceptions in signal handlers

6. `./sleep_scoring_app/ui/protocols.py` — Protocol interfaces
   - Check for stale protocol definitions that don't match actual implementations
</research>

<requirements>
For each issue found, report:
- **Severity**: CRITICAL (data loss/corruption), HIGH (wrong UI state/crashes), MEDIUM (edge case), LOW (minor)
- **File:Line**: Exact location
- **Description**: What's wrong and why it matters
- **Evidence**: The specific code that's problematic

Only report CRITICAL and HIGH issues. Skip style, naming, missing docstrings unless they mask a real bug.

Do NOT report issues documented as known in CLAUDE.md.
</requirements>

<output>
Save findings to: `./reviews/013-ui-layer-review.md`
</output>

<verification>
Before completing, verify:
- You read CLAUDE.md and understand the Redux pattern and layer rules
- You checked every .py file in the target directories
- Each reported issue has a specific file:line reference
- Each issue includes the actual code snippet that's problematic
- You verified whether the issue is a real bug vs intentional design
</verification>

<success_criteria>
- All .py files in ui/ have been reviewed
- Zero false positives
- State management issues are clearly explained with the specific state transition that fails
- Issues are actionable
</success_criteria>
