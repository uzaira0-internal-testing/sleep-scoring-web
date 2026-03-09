<objective>
Thoroughly review the sleep-scoring desktop application for architecture and layer violations.
This codebase follows a strict layered architecture (UI -> Redux Store -> Services -> Core -> IO).
Find violations that could cause bugs, coupling issues, or maintenance problems.
</objective>

<context>
Read CLAUDE.md for the full architecture rules. Key constraints:
- Widgets are DUMB (emit signals only, no service calls, no store dispatch, no parent access)
- Connectors bridge Widget <-> Store (in ui/connectors/)
- Services are HEADLESS (no Qt imports, no signals, pure Python)
- Core has NO dependencies on UI or Services
- Coordinators handle Qt-specific glue (QTimer, QThread)

The application lives in:
- `sleep_scoring_app/ui/` - UI layer (widgets, connectors, coordinators, store)
- `sleep_scoring_app/services/` - Service layer
- `sleep_scoring_app/core/` - Core domain logic
- `sleep_scoring_app/data/` - IO/persistence layer
</context>

<requirements>
Search for these specific violation patterns:

1. **Widgets importing or calling services directly** - grep for service imports in ui/widgets/
2. **Widgets dispatching to store directly** - grep for `store.dispatch` in ui/widgets/
3. **Widgets referencing parent with hasattr()** - grep for `hasattr` in ui/widgets/
4. **Services importing Qt** - grep for `PyQt6` imports in services/
5. **Core importing from UI or Services** - grep for `from sleep_scoring_app.ui` or `from sleep_scoring_app.services` in core/
6. **Connectors doing heavy business logic** instead of just bridging
7. **main_window.py doing work that belongs in coordinators or services** - check for business logic in MainWindow methods

Focus on NEW violations (things not already documented in CLAUDE.md "Known Issues").
</requirements>

<output>
Save findings to: `./reviews/007-architecture-layer-review.md`

Format each finding as:
```
### [SEVERITY] Finding title
- **File**: path:line_number
- **Violation**: What rule is broken
- **Impact**: Why this matters
- **Fix**: Suggested remediation
```

Group by severity: CRITICAL > HIGH > MEDIUM > LOW.
Only report findings you are confident about (>80% confidence).
</output>

<verification>
Before completing:
- Verify each finding by reading the actual code (not just grep matches)
- Exclude false positives (e.g., TYPE_CHECKING imports are fine)
- Exclude known issues already documented in CLAUDE.md
- Count total findings per severity level in a summary at the top
</verification>
