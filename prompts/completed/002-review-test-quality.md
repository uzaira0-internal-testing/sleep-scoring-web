<objective>
Critically review the test suite quality across the ENTIRE codebase to verify tests are meaningful and test real use cases, not superficial "method exists" assertions.

Be skeptical - assume tests might be low-quality padding until proven otherwise. The goal is to identify systemic patterns of good or bad testing, not review every single test individually.
</objective>

<context>
This is a PyQt6 sleep scoring application with 102 test files across these categories:

```
tests/
├── demo_data/          # Data loading tests
├── edge_cases/         # Error scenario tests
├── gui/
│   ├── e2e/           # End-to-end workflow tests
│   ├── integration/   # GUI integration tests
│   └── unit/          # GUI unit tests
├── integration/        # System integration tests
└── unit/
    ├── core/          # Algorithm & domain logic tests
    ├── data/          # Repository & database tests
    ├── io/            # File loading tests
    ├── services/      # Service layer tests
    └── ui/            # UI widget tests
```

Real application use cases include:
- Loading accelerometer data (CSV, GT3X files) and displaying 48-hour activity plots
- Interactive sleep marker placement (onset/offset times) with drag-and-drop
- Running sleep scoring algorithms (Sadeh, Cole-Kripke) on activity data
- Detecting nonwear periods using Choi algorithm
- Exporting sleep metrics to CSV with integrated diary data
- Managing multiple sleep periods per night (main sleep + naps)
</context>

<analysis_approach>
## Strategy: Sample and Pattern Detection

Rather than reviewing all 102 files, thoroughly examine representative samples from each category:

### Phase 1: Sample Selection (read these files)
From each category, read 2-3 test files that represent core functionality:

**Unit/Core (algorithm logic):**
- `tests/unit/core/test_sadeh.py` - Core sleep scoring algorithm
- `tests/unit/core/test_choi_algorithm.py` - Nonwear detection
- `tests/unit/core/test_dataclasses.py` - Domain models

**Unit/Services (business logic):**
- `tests/unit/services/test_batch_scoring_service.py` - Batch processing
- `tests/unit/services/test_data_loading_service.py` - Data loading
- `tests/unit/services/test_marker_service.py` - Marker management

**Unit/Data (persistence):**
- `tests/unit/data/test_database_manager.py` - Database facade
- `tests/unit/data/test_sleep_metrics_repository.py` - Metrics storage

**Unit/UI (widgets):**
- `tests/unit/ui/widgets/test_plot_data_manager.py` - Plot data
- `tests/unit/ui/widgets/test_marker_interaction_handler.py` - Marker interaction

**Integration:**
- `tests/integration/test_export_integration.py` - Export workflow
- `tests/integration/test_seamless_switching_workflows.py` - Data switching

**E2E:**
- `tests/gui/e2e/test_real_e2e_workflow.py` - Full workflow

### Phase 2: Quality Analysis

For each sampled file, evaluate:

1. **Assertion Quality**
   - Are assertions testing meaningful behavior or just "not None"?
   - Do tests verify correct values, not just that something was returned?
   - Are edge cases covered (empty data, boundaries, None inputs)?

2. **Mock Usage**
   - Is mocking excessive? (mocking everything = testing nothing)
   - Are mocks verifying HOW methods are called, not just THAT they're called?
   - Does the test actually exercise the code under test?

3. **Real Use Case Coverage**
   - Would this test catch a bug a user would experience?
   - Does it test the happy path AND failure modes?
   - Are integration points tested?

4. **Test Independence**
   - Could tests pass with broken code?
   - Are tests actually running the code they claim to test?

### Phase 3: Pattern Detection

Identify SYSTEMIC issues across the codebase:
- Are certain test categories consistently weak?
- Is there a pattern of superficial tests (e.g., all UI tests just check mocks)?
- Are critical paths consistently untested?
- Is there good coverage of error handling?
</analysis_approach>

<red_flags>
Watch for these anti-patterns:
- `assert result is not None` without checking the actual value
- `mock.assert_called_once()` without verifying call arguments matter
- Tests that don't make any assertions
- Tests where the setup does all the work and the test just calls a method
- Excessive `@patch` decorators that bypass all real logic
- Tests named "test_something_works" with trivial assertions
- Tests that would pass even if the implementation was completely wrong
</red_flags>

<output_format>
Create a detailed analysis saved to `./analyses/test-quality-review.md`:

```markdown
# Test Suite Quality Review

## Executive Summary
[2-3 sentences: Overall assessment - are these tests trustworthy?]
[Quality Grade: A/B/C/D/F with justification]

## Category Analysis

### Unit/Core Tests
**Sample reviewed:** [files]
**Quality: [A-F]**

**Strengths:**
- [specific example of good testing]

**Weaknesses:**
- [specific example of superficial test with file:line reference]

**Missing critical tests:**
- [scenario that should be tested]

### Unit/Services Tests
[Same structure]

### Unit/Data Tests
[Same structure]

### Unit/UI Tests
[Same structure]

### Integration Tests
[Same structure]

### E2E Tests
[Same structure]

## Systemic Issues
[Patterns of problems across the codebase]

1. **[Issue name]**: [Description with examples]

## Specific Tests to Fix or Remove
| File | Test | Problem | Fix |
|------|------|---------|-----|
| [path] | [test_name] | [issue] | [recommendation] |

## Missing Test Coverage (Critical)
[Top 5 scenarios that MUST be tested but aren't]

## Recommendations
1. [Highest priority action]
2. [...]
```
</output_format>

<verification>
Before completing, verify:
- You READ actual test code from at least 10 different test files
- You checked ASSERTIONS, not just test function names
- You compared at least 3 tests against their source code
- You found specific examples of both good and bad tests
- Your criticisms include file paths and line numbers where possible
- Your "missing tests" are based on real app functionality, not theoretical concerns
</verification>

<success_criteria>
- Review covers all major test categories with specific examples
- Distinguishes clearly between valuable tests and superficial padding
- Identifies systemic patterns, not just individual bad tests
- Recommendations are specific and actionable
- Would help improve test reliability if followed
</success_criteria>
