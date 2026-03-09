# Test Suite Rationalization Plan

## Goal

Increase confidence in real UI behavior by removing or reclassifying tests that do not simulate human interaction, then rebuilding a smaller set of high-signal E2E tests.

## Current Problem Summary

- Many tests in `tests/gui/e2e/` are mock-driven or direct-store-driven, not user-event-driven.
- Some tests are placeholders (`assert True`, `pass  # Placeholder`) and provide little to no protection.
- Several files marked as E2E are better classified as integration/unit tests.

## File-by-File Action Plan

### Delete Immediately (Low value as E2E)

1. `tests/gui/e2e/test_export_workflow.py` (11 tests)
Reason: uses `mock_main_window`; no real UI event flow.

2. `tests/gui/e2e/test_file_loading_workflow.py` (9 tests)
Reason: mock-driven workflow, "no crash" assertions.

3. `tests/gui/e2e/test_full_analysis_workflow.py` (9 tests)
Reason: mock-driven setup, several `assert True` placeholders.

4. `tests/gui/e2e/test_marker_workflow.py` (12 tests)
Reason: synthetic marker object mutation with mocked methods, no user event path.

5. Remove placeholder-only test blocks in `tests/gui/unit/test_plot_widgets.py` (9 tests)
Reason: placeholder `pass` tests.

### Reclassify / Split (Keep intent, move to correct tier)

1. `tests/gui/e2e/test_complete_workflow.py` (24 tests)
Action: split into:
- integration tests for export/database/service wiring
- unit tests for deterministic dataclass/metrics checks
Reason: almost entirely `mock_main_window` based; not true E2E.

2. `tests/gui/e2e/test_real_e2e_workflow.py` (44 tests)
Action: move to `tests/gui/integration/` and rename.
Reason: manual construction via `SleepScoringMainWindow.__new__` and direct store dispatch dominates.

3. `tests/gui/integration/test_export_tab.py` (13 tests)
Action: keep but rename to reflect synthetic widget scope.
Reason: uses custom "mimic" widget, not real export tab class.

4. `tests/gui/integration/test_main_window_tabs.py` (8 tests)
Action: keep as Qt primitive contract tests, not app integration.
Reason: tests generic `QTabWidget` behavior only.

### Rewrite As True Human-Interaction E2E

Use these as source material, but reduce dispatch shortcuts:

1. `tests/gui/e2e/test_complete_application_workflow.py`
2. `tests/gui/e2e/test_full_user_workflow.py`
3. `tests/gui/e2e/test_true_e2e_workflow.py`
4. `tests/gui/e2e/test_full_workflow_visible.py`
5. `tests/gui/e2e/test_realistic_e2e_workflow.py`

Target end state:
- 6 to 10 E2E tests total.
- Each test covers one critical scenario end-to-end using real UI events.
- No placeholder/no-op assertions.

## New E2E Suite Design

Create these files:

1. `tests/gui/e2e/test_e2e_smoke_startup_navigation.py`
Covers: startup, tab navigation, file selection, date navigation.

2. `tests/gui/e2e/test_e2e_marker_interaction.py`
Covers: marker placement, marker drag, marker validation (onset < offset), save persistence.

3. `tests/gui/e2e/test_e2e_diary_to_marker_and_export.py`
Covers: diary-driven marker placement, save, export, exported data verification.

4. `tests/gui/e2e/test_e2e_settings_persistence.py`
Covers: study/data settings changes persist across app restart.

## Hard Acceptance Criteria For E2E

Each E2E test must satisfy all:

1. Constructs `SleepScoringMainWindow()` normally.
2. Uses user-like actions for core workflow steps.
3. No `mock_main_window`.
4. No `assert True`.
5. No placeholder `pass`.
6. No direct `store.dispatch(...)` for core user steps.
7. Asserts both:
- UI-visible effect.
- persisted/state effect (db/store/export artifact).

## Migration Sequence (Safe Rollout)

### Phase 1: Guardrails

1. Add and enforce policy in `CLAUDE.md`.
2. Add CI grep guard for E2E anti-patterns:
- `assert True`
- placeholder `pass`
- `mock_main_window`
- `__new__` window construction

### Phase 2: Remove/Move Legacy Files

1. Delete the four mock-E2E workflow files.
2. Move/split `test_complete_workflow.py` and `test_real_e2e_workflow.py` into integration/unit.

### Phase 3: Build New E2E Core

1. Implement 3 critical end-to-end tests first:
- startup + load
- marker place/drag/save
- diary-place + export validation

2. Add settings persistence E2E test.

### Phase 4: Stabilize

1. Reduce flaky timing with explicit waits on signals/state transitions.
2. Keep E2E runtime bounded and deterministic.

## Commands

```bash
# fast quality checks
ruff check .
basedpyright

# run new E2E suite only
pytest tests/gui/e2e -q

# anti-pattern scan
rg -n "assert True|pass\\s*#\\s*Placeholder|mock_main_window|__new__\\(|store\\.dispatch\\(" tests/gui/e2e
```

