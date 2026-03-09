<objective>
Review the test suite of the sleep-scoring-demo app for coverage gaps, broken tests, and test quality issues.

Focus on identifying untested critical paths, tests that pass but don't actually verify anything, and tests that would miss real regressions. This is NOT about reaching a coverage percentage — it's about whether the tests catch the bugs that matter.
</objective>

<context>
This is a PyQt6 desktop + FastAPI web application. Read `./CLAUDE.md` for the test policy, tier definitions, and hygiene rules.

Key test rules from CLAUDE.md:
- `tests/gui/e2e/` = real user workflow tests (real MainWindow, user-like events, no mock_main_window)
- `tests/gui/integration/` = component integration (real widgets, limited scope)
- `tests/unit/` = isolated unit tests
- E2E tests must NOT use `assert True`, `pass`, `mock_main_window`, `__new__`, or direct `store.dispatch` for core interactions
- Every test must assert observable outcomes

The app's most critical paths are: marker placement/editing/saving, date navigation with marker persistence, algorithm scoring, and data export.
</context>

<research>
Thoroughly analyze the test suite:

1. `./tests/` — All test directories
   - Run the hygiene check from CLAUDE.md:
     ```
     rg -n "assert True|pass\s*#\s*Placeholder|mock_main_window|__new__\(|store\.dispatch\(" tests/gui/e2e
     ```
   - Identify tests that violate the E2E rules (belong in unit/ or integration/)
   - Identify tests that assert nothing meaningful

2. **Critical path coverage gaps** — Check if these scenarios have tests:
   - Marker placement (onset + offset click) and persistence across date navigation
   - Marker deletion and persistence
   - No-sleep-day marking and its effects on nap/main-sleep creation
   - Algorithm scoring with edge cases (empty data, all-sleep, all-wake)
   - Data export correctness
   - File loading for all supported formats (CSV, GT3X)
   - Database migration safety
   - Web API endpoints (auth, file upload, data retrieval)

3. **Test quality** — Look for:
   - Tests that mock too aggressively (mocking the thing being tested)
   - Tests with wrong assertions (testing implementation details instead of behavior)
   - Flaky patterns (timing-dependent, order-dependent, shared mutable state)
   - Missing edge cases in parametrized tests

4. **Pre-existing failures** — Run `uv run pytest tests/ -q --tb=no 2>&1 | tail -5` to check current state
</research>

<requirements>
For each finding, report:
- **Type**: COVERAGE_GAP (untested critical path), BROKEN_TEST (fails or tests nothing), QUALITY (test exists but is weak), VIOLATION (breaks test policy)
- **Location**: File path or "missing" for coverage gaps
- **Description**: What's wrong and what should exist instead
- **Priority**: Based on risk of the untested/broken path

Focus on the highest-risk gaps first. A missing test for marker persistence across navigation is more important than a missing test for a tooltip string.
</requirements>

<output>
Save findings to: `./reviews/015-test-coverage-review.md`
</output>

<verification>
Before completing, verify:
- You actually ran the hygiene check command
- You checked each critical path listed above
- Coverage gaps are specific (not "needs more tests" but "no test for X scenario")
- Existing test failures are noted with their error messages
</verification>

<success_criteria>
- All test files reviewed for quality
- Critical path coverage gaps identified with specific scenarios
- E2E test policy violations flagged
- Current test suite pass/fail state documented
</success_criteria>
