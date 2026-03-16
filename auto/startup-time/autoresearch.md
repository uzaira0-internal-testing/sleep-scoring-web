# Autoresearch: Reduce Backend Startup Time

## Objective
Reduce time from process start to first healthy response. The agent runs an autonomous experiment loop: edit → commit → benchmark → keep/discard.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `startup_ms` (ms, lower is better)
- **Secondary**: import time breakdown

## How to Run
`./auto/startup-time/autoresearch.sh` — starts backend on port 8599, measures time to healthy.

## Files in Scope
- `sleep_scoring_web/main.py` — App creation, middleware registration, router includes
- `sleep_scoring_web/api/__init__.py` — Router registration
- `sleep_scoring_web/api/*.py` — Individual route modules (import cost)
- `sleep_scoring_web/db/session.py` — DB engine creation
- `sleep_scoring_web/models/` — SQLAlchemy model definitions
- `sleep_scoring_web/services/` — Service layer imports
- `sleep_scoring_web/deps.py` — Dependency injection
- `sleep_scoring_web/middleware/` — Middleware

## Off Limits
- `tests/` — Test files
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure

## Constraints
- All tests must still pass
- App must function correctly after startup
- No removing necessary initialization
- Use `uv run` for all Python commands

## Strategic Direction
- Profile with `python -X importtime -c "import sleep_scoring_web.main"` to find slow imports
- Lazy-load heavy modules (defer imports to first use)
- Consider `importlib.import_module()` for rarely-used services
- Check if SQLAlchemy metadata creation is slow
- Defer Sentry/monitoring init to background
- Look at uvicorn startup overhead
- Check if Pydantic model validation at import time is expensive

## Baseline
- **Commit**: 73784ab
- **startup_ms**: (fill in after first run)

## What's Been Tried

## Current Best
- **startup_ms**: (updated automatically by the loop)
