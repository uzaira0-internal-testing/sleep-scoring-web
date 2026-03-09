<objective>
Audit the codebase for architecture layer violations as defined in CLAUDE.md.

The architecture has 5 strict layers with unidirectional dependencies:
- UI Layer (PyQt6) → can import from Store, Services, Core
- Redux Store → can import from Core only
- Services Layer → can import from Core only (NO Qt imports)
- Core Layer → imports NOTHING from UI, Services, or Store
- IO Layer → can import from Core only
</objective>

<context>
Read @CLAUDE.md thoroughly first to understand the exact architecture rules.

Key violations to find:
1. Core layer importing from UI, Services, or Store
2. Services importing PyQt6 or Qt-related modules
3. Widgets directly calling services (should go through Connectors)
4. Widgets dispatching to store directly (should go through Connectors)
5. Widgets referencing parent/MainWindow directly
6. Any circular imports between layers
</context>

<analysis_steps>
1. Read CLAUDE.md to understand the architecture rules completely

2. Audit Core layer (`core/`):
   - Check ALL imports in every file
   - Flag any imports from `ui/`, `services/`, `data/`
   - Core must be pure domain logic with NO external dependencies

3. Audit Services layer (`services/`):
   - Check ALL imports in every file
   - Flag any `from PyQt6` or `from PyQt5` imports
   - Flag any Qt signal/slot usage
   - Services must be headless and testable without Qt

4. Audit UI Widgets (`ui/widgets/`):
   - Check for direct `self.parent()` or `self.parent` access
   - Check for `hasattr(self.parent, ...)` patterns
   - Check for direct service calls (should emit signals instead)
   - Check for direct `store.dispatch()` calls (should be in Connectors)

5. Audit Store (`ui/store.py`):
   - Verify it only imports from Core
   - Check reducer logic is pure (no side effects)

6. Check for circular imports:
   - Look for import patterns that create cycles
</analysis_steps>

<output>
Save findings to: `./analyses/002-architecture-violations.md`

Format:
```markdown
# Architecture Layer Violations Audit

## Summary
[Quick overview of violation count by category]

## Critical Violations (Must Fix)
[List each violation with file:line, what's wrong, and why it matters]

## Minor Violations (Should Fix)
[Less critical but still against architecture]

## Recommendations
[Specific refactoring suggestions for each violation]
```
</output>

<verification>
Before completing:
- Every Python file in core/, services/, ui/ has been checked for imports
- Each violation includes the exact file path and line number
- Recommendations are actionable and specific
</verification>
