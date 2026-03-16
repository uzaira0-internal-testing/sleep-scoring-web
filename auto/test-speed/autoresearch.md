# Autoresearch: Reduce Test Suite Duration

## Objective
Reduce total test suite execution time. The agent runs an autonomous experiment loop: edit → commit → benchmark → keep/discard.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `duration_ms` (ms, lower is better)
- **Secondary**: individual slow test durations

## How to Run
`./auto/test-speed/autoresearch.sh` — runs the test suite 3 times, takes best duration.

## Files in Scope
- `tests/web/conftest.py` — Test fixtures, DB setup/teardown
- `tests/web/*.py` — Test files (may optimize fixture usage, NOT test logic)
- `sleep_scoring_web/db/session.py` — Session factory affects test DB setup
- `sleep_scoring_web/main.py` — App creation (imported by test client)
- `pyproject.toml` — pytest configuration
- `sleep_scoring_web/deps.py` — Dependency overrides in tests

## Off Limits
- Test assertions and test logic — only optimize infrastructure
- Frontend tests
- `auto/` — Autoresearch infrastructure
- Do NOT delete or skip tests

## Constraints
- All tests must still pass
- Test coverage must not decrease
- No changes to what tests verify, only how fast they run
- Use `uv run` for all Python commands

## Strategic Direction
- Run `uv run pytest tests/web/ --durations=20` to find slowest tests
- Session-scoped vs function-scoped fixtures — share expensive setup
- Profile import time of test modules
- Consider pytest-xdist for parallel execution
- Reduce unnecessary database round-trips in fixtures
- Check if any tests do unnecessary I/O or sleeps

## Baseline
- **Commit**: 73784ab
- **duration_ms**: (fill in after first run)

## What's Been Tried

## Current Best
- **duration_ms**: (updated automatically by the loop)
