<objective>
Audit the desktop PyQt6 app (`sleep_scoring_app/`) for violations of the mandatory layered architecture defined in CLAUDE.md. This review ensures no layer boundary crossings exist that would create coupling, make testing harder, or break the separation of concerns.

SCOPE: Only `sleep_scoring_app/` — ignore `sleep_scoring_web/`, `tests/`, and other directories.
</objective>

<context>
This is a PyQt6 desktop application with a strict 5-layer architecture:

```
UI Layer (PyQt6) → Widgets, Connectors, Coordinators
Redux Store      → Actions, Reducer, State, Subscribers
Services Layer   → Headless, no Qt imports, uses callbacks
Core Layer       → Pure domain logic, no UI/Services imports
IO Layer         → CSV/GT3X loaders with DatabaseColumn enum
```

Read CLAUDE.md first for the full architecture rules, then systematically check every file.
</context>

<research>
First, read `./CLAUDE.md` to understand the full layered architecture rules.

Then systematically audit each layer for violations:

1. **Core layer** (`sleep_scoring_app/core/`):
   - Search for ANY imports from `ui/`, `services/`, or PyQt6 in core files
   - Core must have ZERO dependencies on upper layers
   - Check patterns: `from sleep_scoring_app.ui`, `from sleep_scoring_app.services`, `from PyQt6`, `import PyQt6`

2. **Services layer** (`sleep_scoring_app/services/`):
   - Search for ANY PyQt6 imports (signals, QThread, QObject, etc.)
   - Services must be headless — no Qt, no signals, only callbacks
   - Check patterns: `from PyQt6`, `import PyQt6`, `pyqtSignal`, `QThread`, `QObject`

3. **IO layer** (`sleep_scoring_app/io/` or `sleep_scoring_app/sources/`):
   - Should not import from UI or Services
   - Check for coupling to upper layers

4. **UI Widgets** (`sleep_scoring_app/ui/` — widget files, NOT connectors or coordinators):
   - Widgets must NOT reference MainWindow or parent directly
   - Widgets must NOT call services directly
   - Widgets must NOT dispatch to store directly
   - They should ONLY emit signals
   - Check for: `self.parent()`, `hasattr(self.parent`, direct service calls, `store.dispatch`

5. **UI Connectors** (`sleep_scoring_app/ui/connectors/`):
   - These ARE allowed to bridge Widget ↔ Store
   - Verify they follow the pattern: subscribe to store, connect widget signals to dispatch
   - Check they don't contain business logic that belongs in Services

6. **Cross-cutting concerns**:
   - Check if any file imports across layer boundaries in unexpected ways
   - Look for circular import risks
</research>

<output>
Save your findings to: `./reviews/002-layer-architecture-review.md`

Structure the report as:

```markdown
# Layer Architecture Review

## Summary
[Pass/Fail count, severity overview]

## Critical Violations (layer boundary crossings)
[Each violation with file:line, what rule it breaks, and suggested fix]

## Warnings (potential issues)
[Gray areas or borderline cases]

## Layer-by-Layer Status
### Core Layer: [PASS/FAIL]
### Services Layer: [PASS/FAIL]
### IO Layer: [PASS/FAIL]
### UI Widgets: [PASS/FAIL]
### UI Connectors: [PASS/FAIL]
### UI Coordinators: [PASS/FAIL]
```
</output>

<verification>
Before completing:
- Confirm you searched EVERY .py file in each layer directory under `sleep_scoring_app/`
- Confirm you checked both `from X import` and `import X` patterns
- Confirm you checked for indirect violations (e.g., a core module importing a utility that itself imports PyQt6)
</verification>

<success_criteria>
- Every .py file in core/, services/, and io/ has been checked for forbidden imports
- Every widget file has been checked for direct parent/service/store access
- All violations are documented with file path, line number, and specific rule broken
- Each violation includes a concrete suggestion for how to fix it
</success_criteria>
