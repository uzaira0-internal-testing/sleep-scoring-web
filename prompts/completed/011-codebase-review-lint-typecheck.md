<objective>
Perform a comprehensive codebase review of the sleep-scoring-demo desktop application (Python/PyQt6),
fix all basedpyright type errors and ruff lint violations, and run the test suite ONLY at the very end
after all fixes are applied.

This is a quality pass to catch bugs, type errors, dead code, and lint issues before they accumulate.
</objective>

<context>
This is a PyQt6 desktop application for visual sleep scoring of accelerometer data.
It follows a strict layered architecture (see CLAUDE.md):
  - Core layer: Pure domain logic, algorithms, dataclasses
  - Services layer: Headless business logic (no Qt)
  - UI layer: Widgets (dumb), Connectors (store↔widget bridge), Coordinators (Qt glue)
  - Redux store: Single source of truth for all state

Tech stack: Python 3.11+, PyQt6, pyqtgraph, polars, uv package manager.
Type checker: basedpyright. Linter/formatter: ruff.

Read CLAUDE.md thoroughly first — it contains mandatory coding standards, architecture rules,
and known issues that inform what counts as a real problem vs intentional design.
</context>

<requirements>
Complete each phase in order. Do NOT run tests until Phase 4.

## Phase 1: Codebase Review (READ-ONLY — do not edit files yet)

Thoroughly analyze the following directories for issues:

```
sleep_scoring_app/core/         — Domain logic, algorithms, dataclasses, constants
sleep_scoring_app/services/     — Headless services (no Qt imports allowed)
sleep_scoring_app/io/           — Data loaders (CSV, GT3X)
sleep_scoring_app/ui/           — Widgets, connectors, coordinators, store, protocols
sleep_scoring_app/utils/        — Utility functions
sleep_scoring_app/data/         — Database and migrations
```

Look for:
- **Architecture violations**: Services importing Qt, widgets accessing store directly,
  connectors doing business logic, hasattr() abuse (see CLAUDE.md rules)
- **Type safety issues**: Missing annotations on new/modified functions, incorrect types,
  `Any` used where a concrete type is known
- **Dead code**: Unused imports, unreachable branches, methods never called
- **Logic bugs**: Off-by-one errors, None checks missing, race conditions in Qt signals
- **CLAUDE.md violations**: Magic strings (should be StrEnum), dict access (should be dataclass),
  mutable state read from store without deep copy, backwards-compat shims
- **Silent failures**: Empty except blocks, swallowed errors, missing logging on failure paths

Produce a mental inventory of issues found. Do NOT write a review file — proceed directly to fixing.

## Phase 2: Fix basedpyright Errors

Run basedpyright and fix ALL errors:

```bash
cd apps/sleep-scoring-demo && basedpyright 2>&1
```

Common fixes (reference CLAUDE.md):
- Do NOT type-annotate `context` parameter in Dagster assets with `from __future__ import annotations`
  (this project is not Dagster, but the principle applies: check if annotations break runtime behavior)
- Add missing type annotations to function signatures
- Fix incompatible types, missing attributes, incorrect return types
- Replace `Any` with concrete types where the actual type is obvious
- Fix Protocol mismatches between `ui/protocols.py` and implementations

If basedpyright produces hundreds of errors, prioritize:
1. Actual bugs (wrong types that would cause runtime errors)
2. Missing return types on public API methods
3. Type narrowing issues (None checks)
4. Leave cosmetic-only issues (e.g., deeply nested generics) for last

## Phase 3: Fix ruff Lint and Format Issues

Run ruff check and fix violations:

```bash
cd apps/sleep-scoring-demo && ruff check . 2>&1
cd apps/sleep-scoring-demo && ruff format --check . 2>&1
```

Then auto-fix what's safe:

```bash
cd apps/sleep-scoring-demo && ruff check --fix .
cd apps/sleep-scoring-demo && ruff format .
```

Review any remaining violations that couldn't be auto-fixed and fix manually.

Known acceptable violations (do NOT "fix" these):
- E402 in files that call `load_dotenv()` before imports (intentional)

## Phase 4: Run Tests (ONLY after all fixes are complete)

```bash
cd apps/sleep-scoring-demo && pytest tests/ -v --tb=short 2>&1
```

If tests fail:
- Determine if the failure is caused by YOUR changes (fix it)
- Or if it was pre-existing (note it but don't chase unrelated failures)
- Re-run failed tests individually to confirm fixes

Also run the frontend typecheck (CLAUDE.md mandatory pre-push check):

```bash
cd apps/sleep-scoring-demo/frontend && bun run typecheck 2>&1
```
</requirements>

<constraints>
- Do NOT run tests until Phase 4. Running tests early wastes time if you're still making changes.
- Do NOT add docstrings, comments, or type annotations to code you didn't change for other reasons.
  Only fix what's broken or violating rules.
- Do NOT refactor working code that isn't violating any rules. This is a quality pass, not a rewrite.
- Do NOT create new files unless absolutely necessary (e.g., a missing __init__.py).
- Do NOT modify test files to make them pass — fix the source code instead.
- Preserve all existing behavior. Every fix should be behavior-preserving unless fixing a genuine bug.
- When fixing imports, grep for ALL usages of the old name before deleting/renaming.
</constraints>

<verification>
Before declaring complete, confirm:
1. `basedpyright` produces zero errors (or only pre-existing ones you documented)
2. `ruff check .` produces zero violations
3. `ruff format --check .` shows no formatting changes needed
4. `pytest tests/ -v` passes (note any pre-existing failures separately)
5. `cd frontend && bun run typecheck` passes
</verification>

<success_criteria>
- All basedpyright errors are resolved or explicitly documented as pre-existing
- All ruff violations are resolved
- Code is properly formatted
- Test suite passes
- No new functionality was added, removed, or changed — only quality improvements
- CLAUDE.md rules are not violated by any fix
</success_criteria>
