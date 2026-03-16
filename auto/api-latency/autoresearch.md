# Autoresearch: Reduce API Latency

## Objective
Reduce p99 API response time. The agent runs an autonomous experiment loop: edit → commit → benchmark → keep/discard.
Each change is validated before benchmarking. Changes that regress correctness or the primary metric are reverted immediately.

## Stopping Condition
Stop when improvement is <5% after 3 consecutive cycles.

## Metrics
- **Primary (optimization target)**: `p99_ms` (ms, lower is better)
- **Secondary**: individual endpoint response times

## How to Run
`./auto/api-latency/autoresearch.sh` — runs pre-checks, then the benchmark, outputs `METRIC p99_ms=number`.

## Files in Scope
- `sleep_scoring_web/main.py` — FastAPI app entry, middleware stack
- `sleep_scoring_web/db/session.py` — Database session/connection pool config
- `sleep_scoring_web/api/files.py` — File listing/CRUD endpoints
- `sleep_scoring_web/api/markers.py` — Marker CRUD endpoints
- `sleep_scoring_web/api/markers_autoscore.py` — Auto-scoring endpoint
- `sleep_scoring_web/api/markers_tables.py` — Table data endpoints
- `sleep_scoring_web/api/activity.py` — Activity data endpoints
- `sleep_scoring_web/api/studies.py` — Study/participant endpoints
- `sleep_scoring_web/api/consensus.py` — Consensus endpoints
- `sleep_scoring_web/services/` — All service layer files
- `sleep_scoring_web/models/` — SQLAlchemy models (indexes, relationships)
- `sleep_scoring_web/middleware/` — Middleware (query profiler, etc.)
- `sleep_scoring_web/deps.py` — Dependency injection

## Off Limits
- `tests/` — Test files must not be modified
- `frontend/` — Frontend code
- `auto/` — Autoresearch infrastructure
- Database schema changes that require migrations

## Constraints
- All existing tests must pass (`uv run pytest tests/web/ -x -q`)
- No new dependencies without strong justification
- No breaking API contract changes
- Use `uv run` for all Python commands
- Semantic correctness must be preserved

## Strategic Direction
- Profile with `SLOW_QUERY_THRESHOLD_MS=0` to find slow queries
- Focus on N+1 query patterns and missing eager loads
- Connection pool tuning (SQLAlchemy async pool_size, max_overflow)
- Consider response compression middleware
- Consider orjson for faster serialization
- Look at SQLAlchemy relationship loading strategies

## Baseline
- **Commit**: 73784ab
- **p99_ms**: (fill in after first run)

## What's Been Tried

## Current Best
- **p99_ms**: (updated automatically by the loop)
