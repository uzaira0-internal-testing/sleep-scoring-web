<objective>
Review the core domain logic, services layer, and IO layer of the sleep-scoring-demo app for glaring issues.

Focus on bugs, logic errors, data corruption risks, silent failures, and violations of the project's layered architecture. This is NOT a style review — only report issues that could cause incorrect behavior, data loss, or crashes.
</objective>

<context>
This is a PyQt6 desktop application for visual sleep scoring of accelerometer data. Read `./CLAUDE.md` first for the full architecture rules and coding standards.

Key architecture constraint: Core has NO dependencies on UI or Services. Services are headless (no Qt). Violations of this layering are bugs.

The app processes actigraphy data, runs sleep/wake scoring algorithms, and lets users manually place sleep onset/offset markers. Correctness of marker placement, algorithm results, and data persistence is critical — this is research software where wrong results invalidate studies.
</context>

<research>
Thoroughly analyze these directories for glaring issues:

1. `./sleep_scoring_app/core/` — Domain logic, algorithms, dataclasses, constants
   - Check algorithm implementations for off-by-one errors, wrong formulas, edge cases with empty data
   - Check dataclass invariants (e.g., onset must be before offset, marker_index bounds)
   - Check for circular imports or layer violations (core importing from ui/ or services/)

2. `./sleep_scoring_app/services/` — Headless services
   - Check for Qt imports (layer violation)
   - Check for silent failures: methods that return None/empty on error without logging
   - Check database operations for SQL injection, missing error handling, connection leaks
   - Check file operations for path traversal, unclosed handles, encoding issues

3. `./sleep_scoring_app/io/` — Data loaders (CSV, GT3X)
   - Check for data truncation, wrong column mapping, timezone mishandling
   - Check error handling when files are malformed or missing columns
   - Check for memory issues with large files (eager loading vs lazy)

4. `./sleep_scoring_app/data/` — Database and migrations
   - Check migration safety, schema consistency
   - Check for data loss scenarios during migration
</research>

<requirements>
For each issue found, report:
- **Severity**: CRITICAL (data corruption/loss), HIGH (wrong results/crashes), MEDIUM (edge case failures), LOW (minor)
- **File:Line**: Exact location
- **Description**: What's wrong and why it matters
- **Evidence**: The specific code that's problematic

Only report CRITICAL and HIGH issues. Skip style, naming, missing docstrings, and type annotation gaps unless they mask a real bug.

Do NOT report issues that are documented as known in CLAUDE.md (e.g., `flash_processing` import errors, E402 violations in definitions.py).
</requirements>

<output>
Save findings to: `./reviews/012-core-services-io-review.md`
</output>

<verification>
Before completing, verify:
- You read CLAUDE.md and understand the architecture rules
- You checked every .py file in the target directories (not just a sample)
- Each reported issue has a specific file:line reference
- Each issue is reproducible (not speculative)
- You did not report style-only issues
</verification>

<success_criteria>
- All .py files in core/, services/, io/, and data/ have been reviewed
- Zero false positives (every reported issue is a real problem)
- Issues are actionable (clear enough to fix without further investigation)
</success_criteria>
